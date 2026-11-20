"""Shared helpers and fixtures for recovery integration tests against the compose stack."""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import pytest
from alerting_core.config.watcher import handle_config_file_change
from alerting_core.connections import create_database_pool, create_redis_client
from alerting_core.settings import Settings
from redis.asyncio import Redis
from redis.exceptions import RedisError

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PROJECT = "alerting"
INGEST_URL = os.environ.get("INGEST_URL", "http://localhost:8001").rstrip("/")
SOURCE_ID = "generic-webhook"
RULE_ID = "loadtest-events"
LOADTEST_RULE_PATH = REPO_ROOT / "config" / "rules" / "loadtest-events.yaml"

_RUN_ALERTS_CTE = """
    run_alerts AS (
        SELECT id FROM alerts
        WHERE rule_id = $1
          AND first_seen >= to_timestamp($3)
          AND last_event->>'run_id' = $2
    )
"""


@dataclass(frozen=True, slots=True)
class IntegrationStack:
    """Connections and URLs for the running compose stack."""

    pool: asyncpg.Pool
    redis: Redis
    ingest_url: str
    mock_gateway_url: str


@dataclass(frozen=True, slots=True)
class RunDeliveryStats:
    """Alert and delivery row counts in Postgres for one test run."""

    alerts: int
    total_deliveries: int
    distinct_alert_channels: int
    delivered_total: int
    dead_lettered_total: int
    fallback_total: int
    by_channel_status: dict[tuple[str, str], int]


async def run_command(*args: str, timeout_seconds: float = 30.0) -> str:
    """Run a command from the repository root and return stdout."""
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=REPO_ROOT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except TimeoutError as error:
        process.kill()
        await process.wait()
        raise RuntimeError(f"{' '.join(args)} timed out after {timeout_seconds}s") from error
    if process.returncode != 0:
        detail = stderr.decode().strip() or stdout.decode().strip()
        raise RuntimeError(f"{' '.join(args)} exited {process.returncode}: {detail}")
    return stdout.decode().strip()


async def compose(*args: str, timeout_seconds: float = 60.0) -> str:
    """Run `docker compose -p alerting ...` without touching unrelated services."""
    return await run_command(
        "docker", "compose", "-p", COMPOSE_PROJECT, *args, timeout_seconds=timeout_seconds
    )


async def running_containers(service: str) -> list[str]:
    """Return container IDs of running replicas for a compose service."""
    output = await compose("ps", "-q", "--status", "running", service)
    return [line for line in output.splitlines() if line]


async def wait_for_http_ok(url: str, *, timeout_seconds: float = 30.0) -> None:
    """Poll an HTTP endpoint until it returns 200 or the timeout elapses."""
    deadline = time.monotonic() + timeout_seconds
    last_error = "no response"
    async with httpx.AsyncClient(timeout=3.0) as client:
        while time.monotonic() < deadline:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    return
                last_error = f"HTTP {response.status_code}"
            except httpx.HTTPError as error:
                last_error = f"{type(error).__name__}: {error}"
            await asyncio.sleep(0.5)
    raise TimeoutError(f"{url} did not return 200 within {timeout_seconds}s ({last_error})")


def build_event(run_id: str, sequence: int) -> dict[str, Any]:
    """Build one unique event matching `config/rules/loadtest-events.yaml`."""
    return {
        "loadtest": True,
        "run_id": run_id,
        "seq": sequence,
        "evt": f"{run_id}-{sequence}",
        "svc": "loadtest",
        "severity": "error",
        "sent_ms": time.time() * 1000,
    }


async def _post_one(
    client: httpx.AsyncClient,
    endpoint: str,
    payload: dict[str, Any],
    errors: list[str],
) -> bool:
    headers = {
        "X-Sent-At": datetime.now(UTC).isoformat(),
        "Content-Type": "application/json",
    }
    try:
        response = await client.post(endpoint, content=json.dumps(payload), headers=headers)
        if response.status_code == 202:
            return True
        errors.append(f"HTTP {response.status_code}")
    except httpx.HTTPError as error:
        errors.append(f"{type(error).__name__}: {error}")
    return False


async def post_events(
    ingest_url: str,
    run_id: str,
    total: int,
    *,
    rate_per_second: float | None = None,
    concurrency: int = 16,
) -> int:
    """Post `total` unique events to the ingest webhook source and verify every HTTP 202."""
    endpoint = f"{ingest_url}/api/v1/ingest/{SOURCE_ID}"
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    errors: list[str] = []
    accepted = 0
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)

    async with httpx.AsyncClient(limits=limits, timeout=15.0) as client:

        async def sender() -> None:
            nonlocal accepted
            while (payload := await queue.get()) is not None:
                if await _post_one(client, endpoint, payload, errors):
                    accepted += 1

        workers = [asyncio.create_task(sender()) for _ in range(concurrency)]
        started = time.perf_counter()
        for sequence in range(total):
            if rate_per_second is not None:
                delay = started + sequence / rate_per_second - time.perf_counter()
                if delay > 0:
                    await asyncio.sleep(delay)
                elif sequence % 50 == 0:
                    await asyncio.sleep(0)
            queue.put_nowait(build_event(run_id, sequence))
        for _ in workers:
            queue.put_nowait(None)
        await asyncio.gather(*workers)

    assert not errors, f"ingest failed for {len(errors)}/{total} events (first: {errors[0]})"
    return accepted


async def database_epoch(pool: asyncpg.Pool) -> float:
    """Return Postgres current Unix epoch to avoid host vs Docker VM clock drift."""
    return float(await pool.fetchval("SELECT extract(epoch FROM clock_timestamp())"))


async def fetch_run_delivery_stats(
    pool: asyncpg.Pool, run_id: str, since_epoch: float
) -> RunDeliveryStats:
    """Count alerts and deliveries in Postgres for one `run_id`."""
    args = (RULE_ID, run_id, since_epoch)
    summary = await pool.fetchrow(
        f"""WITH {_RUN_ALERTS_CTE}
        SELECT
            (SELECT count(*) FROM run_alerts) AS alerts,
            count(d.id) AS total_deliveries,
            count(DISTINCT (d.alert_id, d.channel_id)) AS distinct_alert_channels,
            count(*) FILTER (WHERE d.status = 'delivered') AS delivered_total,
            count(*) FILTER (WHERE d.status = 'dead_lettered') AS dead_lettered_total,
            count(*) FILTER (WHERE d.is_fallback) AS fallback_total
        FROM deliveries d
        JOIN run_alerts ra ON ra.id = d.alert_id""",
        *args,
    )
    grouped = await pool.fetch(
        f"""WITH {_RUN_ALERTS_CTE}
        SELECT d.channel_id, d.status, count(*) AS row_count
        FROM deliveries d
        JOIN run_alerts ra ON ra.id = d.alert_id
        GROUP BY d.channel_id, d.status""",
        *args,
    )
    by_channel_status = {
        (str(row["channel_id"]), str(row["status"])): int(row["row_count"]) for row in grouped
    }
    return RunDeliveryStats(
        alerts=int(summary["alerts"]),
        total_deliveries=int(summary["total_deliveries"]),
        distinct_alert_channels=int(summary["distinct_alert_channels"]),
        delivered_total=int(summary["delivered_total"]),
        dead_lettered_total=int(summary["dead_lettered_total"]),
        fallback_total=int(summary["fallback_total"]),
        by_channel_status=by_channel_status,
    )


async def _check_http_health(url: str) -> None:
    async with httpx.AsyncClient(timeout=3.0) as client:
        response = await client.get(url)
        if response.status_code != 200:
            raise RuntimeError(f"{url} returned {response.status_code}")


@pytest.fixture
async def stack() -> AsyncIterator[IntegrationStack]:
    """Connect to the running `alerting` compose stack, or skip if unreachable."""
    settings = Settings()
    mock_gateway_url = settings.mock_gateway_url.rstrip("/")
    pool: asyncpg.Pool | None = None
    redis: Redis | None = None
    try:
        await _check_http_health(f"{INGEST_URL}/healthz")
        await _check_http_health(f"{mock_gateway_url}/healthz")
        pool = await create_database_pool(settings)
        await pool.fetchval("SELECT 1")
        redis = create_redis_client(settings)
        await redis.ping()
        if not await running_containers("processor"):
            raise RuntimeError("no running processor container")
        if not await running_containers("delivery"):
            raise RuntimeError("no running delivery container")
    except (
        httpx.HTTPError,
        OSError,
        asyncpg.PostgresError,
        RedisError,
        RuntimeError,
        TimeoutError,
    ) as error:
        if redis is not None:
            await redis.aclose()
        if pool is not None:
            await pool.close()
        pytest.skip(f"alerting compose stack is not reachable: {error}")

    if await handle_config_file_change(LOADTEST_RULE_PATH, pool, redis):
        await asyncio.sleep(1.5)  # allow processor ConfigRegistry to reload the rule

    try:
        yield IntegrationStack(
            pool=pool,
            redis=redis,
            ingest_url=INGEST_URL,
            mock_gateway_url=mock_gateway_url,
        )
    finally:
        await redis.aclose()
        await pool.close()
