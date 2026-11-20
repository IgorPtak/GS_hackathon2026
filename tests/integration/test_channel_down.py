"""Integration test: SMS channel recovers after a mock-gateway outage without dead-lettering."""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest

from tests.integration.conftest import (
    IntegrationStack,
    compose,
    database_epoch,
    fetch_run_delivery_stats,
    post_events,
    wait_for_http_ok,
)

pytestmark = pytest.mark.integration

EVENT_COUNT = 200
OUTAGE_SECONDS = 20.0
RECOVERY_TIMEOUT_SECONDS = 90.0


async def test_channel_down_recovers_all_sms_deliveries(stack: IntegrationStack) -> None:
    """Stop mock-gateway, send 200 events, restore after 20 s; all 200 SMS deliveries succeed."""
    run_id = f"channel-down-{uuid.uuid4().hex[:8]}"
    since_epoch = await database_epoch(stack.pool) - 5.0
    health_url = f"{stack.mock_gateway_url}/healthz"

    await compose("stop", "mock-gateway")
    try:
        accepted = await post_events(stack.ingest_url, run_id, EVENT_COUNT)
        assert accepted == EVENT_COUNT

        await asyncio.sleep(OUTAGE_SECONDS)

        deadline = time.monotonic() + RECOVERY_TIMEOUT_SECONDS
        await compose("start", "mock-gateway")
        await wait_for_http_ok(health_url, timeout_seconds=30.0)

        stats = await fetch_run_delivery_stats(stack.pool, run_id, since_epoch)
        while time.monotonic() < deadline:
            if (
                stats.alerts == EVENT_COUNT
                and stats.by_channel_status.get(("sms", "delivered"), 0) == EVENT_COUNT
            ):
                break
            await asyncio.sleep(1.0)
            stats = await fetch_run_delivery_stats(stack.pool, run_id, since_epoch)

        assert stats.alerts == EVENT_COUNT, f"expected {EVENT_COUNT} alerts, got {stats}"
        assert stats.by_channel_status.get(("sms", "delivered"), 0) == EVENT_COUNT, (
            f"expected {EVENT_COUNT} delivered sms rows within {RECOVERY_TIMEOUT_SECONDS}s, "
            f"got {stats}"
        )
        assert stats.dead_lettered_total == 0, f"expected zero dead_lettered rows, got {stats}"
        assert stats.fallback_total == 0, f"expected zero fallback rows, got {stats}"
    finally:
        await compose("start", "mock-gateway")
        await wait_for_http_ok(health_url, timeout_seconds=30.0)
