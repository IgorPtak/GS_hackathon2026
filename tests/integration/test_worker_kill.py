"""Integration test: killing one delivery worker mid-run still delivers every alert once."""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest

from tests.integration.conftest import (
    IntegrationStack,
    RunDeliveryStats,
    compose,
    database_epoch,
    fetch_run_delivery_stats,
    post_events,
    run_command,
    running_containers,
)

pytestmark = pytest.mark.integration

EXPECTED_REPLICAS = 2
EVENT_COUNT = 1000
TARGET_RATE_PER_SECOND = 200.0
KILL_DELAY_SECONDS = 2.0
SETTLE_TIMEOUT_SECONDS = 120.0
EXPECTED_CHANNELS = ("ui", "sms")


async def _wait_for_delivery_replicas(expected: int, *, timeout_seconds: float = 30.0) -> list[str]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        containers = await running_containers("delivery")
        if len(containers) == expected:
            return containers
        await asyncio.sleep(0.5)
    containers = await running_containers("delivery")
    raise TimeoutError(
        f"expected {expected} running delivery replicas, found {len(containers)} "
        f"within {timeout_seconds}s"
    )


async def _ensure_delivery_replicas(expected: int, *, settle_seconds: float = 3.0) -> list[str]:
    containers = await running_containers("delivery")
    if len(containers) == expected:
        return containers
    await compose(
        "up",
        "-d",
        "--no-recreate",
        "--no-deps",
        "--scale",
        f"delivery={expected}",
        "delivery",
    )
    containers = await _wait_for_delivery_replicas(expected)
    if settle_seconds > 0:
        await asyncio.sleep(settle_seconds)
    return containers


async def _kill_one_delivery_mid_run(delay_seconds: float) -> str:
    await asyncio.sleep(delay_seconds)
    containers = await running_containers("delivery")
    assert len(containers) >= EXPECTED_REPLICAS, (
        f"expected at least {EXPECTED_REPLICAS} running delivery replicas before kill, "
        f"found {len(containers)}"
    )
    target = containers[-1]
    await run_command("docker", "kill", target)
    return target


async def _wait_for_all_delivered(
    stack: IntegrationStack,
    run_id: str,
    since_epoch: float,
    expected_deliveries: int,
) -> RunDeliveryStats:
    deadline = time.monotonic() + SETTLE_TIMEOUT_SECONDS
    stats = await fetch_run_delivery_stats(stack.pool, run_id, since_epoch)
    while time.monotonic() < deadline:
        if (
            stats.alerts == EVENT_COUNT
            and stats.delivered_total == expected_deliveries
            and stats.total_deliveries == expected_deliveries
        ):
            return stats
        await asyncio.sleep(1.0)
        stats = await fetch_run_delivery_stats(stack.pool, run_id, since_epoch)
    return stats


def _assert_delivered_exactly_once(stats: RunDeliveryStats, expected_deliveries: int) -> None:
    assert stats.alerts == EVENT_COUNT, f"expected {EVENT_COUNT} alerts, got {stats}"
    assert stats.total_deliveries == expected_deliveries, (
        f"expected {expected_deliveries} delivery rows, got {stats}"
    )
    assert stats.distinct_alert_channels == expected_deliveries, (
        f"duplicate delivery row per alert and channel detected: {stats}"
    )
    assert stats.delivered_total == expected_deliveries, (
        f"expected all {expected_deliveries} deliveries delivered within "
        f"{SETTLE_TIMEOUT_SECONDS}s, got {stats}"
    )
    assert stats.dead_lettered_total == 0, f"expected zero dead_lettered rows, got {stats}"
    assert stats.fallback_total == 0, f"expected zero fallback rows, got {stats}"
    for channel_id in EXPECTED_CHANNELS:
        assert stats.by_channel_status.get((channel_id, "delivered"), 0) == EVENT_COUNT, (
            f"expected {EVENT_COUNT} delivered rows on channel {channel_id!r}, got {stats}"
        )


async def test_worker_kill_delivers_every_alert_exactly_once(stack: IntegrationStack) -> None:
    """Kill one of two delivery workers mid-run; every alert+channel is delivered once."""
    containers = await _ensure_delivery_replicas(EXPECTED_REPLICAS)
    assert len(containers) == EXPECTED_REPLICAS

    run_id = f"worker-kill-{uuid.uuid4().hex[:8]}"
    since_epoch = await database_epoch(stack.pool) - 5.0
    expected_deliveries = EVENT_COUNT * len(EXPECTED_CHANNELS)
    kill_task = asyncio.create_task(_kill_one_delivery_mid_run(KILL_DELAY_SECONDS))

    try:
        accepted = await post_events(
            stack.ingest_url,
            run_id,
            EVENT_COUNT,
            rate_per_second=TARGET_RATE_PER_SECOND,
        )
        killed_container = await kill_task
        assert accepted == EVENT_COUNT
        assert killed_container

        await compose("up", "-d", "--no-recreate", "--no-deps", "delivery")
        await _wait_for_delivery_replicas(EXPECTED_REPLICAS)

        stats = await _wait_for_all_delivered(stack, run_id, since_epoch, expected_deliveries)
        _assert_delivered_exactly_once(stats, expected_deliveries)
    finally:
        if not kill_task.done():
            kill_task.cancel()
            await asyncio.gather(kill_task, return_exceptions=True)
        await compose(
            "up",
            "-d",
            "--no-recreate",
            "--no-deps",
            "--scale",
            f"delivery={EXPECTED_REPLICAS}",
            "delivery",
        )
        await _wait_for_delivery_replicas(EXPECTED_REPLICAS)
