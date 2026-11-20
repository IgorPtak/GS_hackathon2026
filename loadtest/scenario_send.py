"""Load-test building blocks: unique events, an open-loop sender and a stream-lag sampler."""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from redis.asyncio import Redis

# Ingest reads `config/sources/` only at startup, so reuse a source that always exists.
SOURCE_ID = "generic-webhook"
RULE_ID = "loadtest-events"
# The rule routes to ui (one team-wide row) and sms (one row for the platform on-call).
EXPECTED_PER_ALERT = 2
GROUPS = {"events": "processors", "deliveries": "delivery-workers"}


def build_event(run_id: str, seq: int, evt: str | None = None) -> dict[str, Any]:
    """One load event; `evt` is the dedup fingerprint, unique per event unless overridden.

    `sent_ms` is the host wall clock at build time; it is the start of the e2e latency.
    """
    return {
        "loadtest": True,
        "run_id": run_id,
        "seq": seq,
        "evt": evt or f"{run_id}-{seq}",
        "svc": "loadtest",
        "severity": "error",
        "sent_ms": time.time() * 1000,
    }


@dataclass
class SendResult:
    """Outcome of one open-loop send."""

    sent: int = 0
    accepted: int = 0
    errors: Counter[str] = field(default_factory=Counter)
    http_ms: list[float] = field(default_factory=list)
    started_wall: float = 0.0
    ended_wall: float = 0.0
    send_loop_s: float = 0.0

    @property
    def achieved_msg_s(self) -> float:
        """Accepted messages per second from the first send to the last response."""
        return self.accepted / max(self.ended_wall - self.started_wall, 1e-9)


async def _post(
    client: httpx.AsyncClient, url: str, bodies: list[dict[str, Any]], result: SendResult
) -> None:
    path = f"{url}/api/v1/ingest/{SOURCE_ID}" + ("/batch" if len(bodies) > 1 else "")
    headers = {"X-Sent-At": datetime.now(UTC).isoformat(), "Content-Type": "application/json"}
    started = time.perf_counter()
    try:
        response = await client.post(
            path, content=json.dumps(bodies if len(bodies) > 1 else bodies[0]), headers=headers
        )
        status = str(response.status_code)
    except httpx.HTTPError as exc:
        status = type(exc).__name__
    result.http_ms.append((time.perf_counter() - started) * 1000)
    result.sent += len(bodies)
    if status == "202":
        result.accepted += len(bodies)
    else:
        result.errors[status] += len(bodies)


async def send_events(
    base_url: str,
    total: int,
    rate: float,
    make_event: Callable[[int], dict[str, Any]],
    *,
    batch_size: int = 1,
    concurrency: int = 16,
) -> SendResult:
    """Send `total` events at `rate` msg/s. Open loop: send times come from the start time."""
    result = SendResult()
    queue: asyncio.Queue[list[dict[str, Any]] | None] = asyncio.Queue()
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(limits=limits, timeout=15.0) as client:

        async def worker() -> None:
            while (bodies := await queue.get()) is not None:
                await _post(client, base_url, bodies, result)

        workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
        result.started_wall = time.time()
        start = time.perf_counter()
        buffer: list[dict[str, Any]] = []
        for seq in range(total):
            delay = start + seq / rate - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            elif seq % 50 == 0:
                await asyncio.sleep(0)  # let workers run when the loop is behind schedule
            buffer.append(make_event(seq))
            if len(buffer) >= batch_size:
                queue.put_nowait(buffer)
                buffer = []
        if buffer:
            queue.put_nowait(buffer)
        result.send_loop_s = time.perf_counter() - start
        for _ in workers:
            queue.put_nowait(None)
        await asyncio.gather(*workers)
        result.ended_wall = time.time()
    return result


class LagSampler:
    """Samples `XINFO GROUPS` of `events` and `deliveries` until stopped."""

    def __init__(self, redis: Redis, interval: float = 0.25) -> None:
        self._redis = redis
        self._interval = interval
        self._task: asyncio.Task[None] | None = None
        self.samples: list[dict[str, float]] = []

    async def _sample(self) -> dict[str, float]:
        row: dict[str, float] = {"t": time.time()}
        for stream, group in GROUPS.items():
            for info in await self._redis.xinfo_groups(stream):
                if info["name"] == group:
                    row[f"{stream}_lag"] = float(info.get("lag") or 0)
                    row[f"{stream}_pending"] = float(info.get("pending") or 0)
        return row

    async def _loop(self) -> None:
        while True:
            try:
                self.samples.append(await self._sample())
            except Exception as exc:  # noqa: BLE001 - a failed sample must not stop the run
                self.samples.append({"t": time.time(), "error": 1.0})
                print(f"lag sample failed: {exc}", flush=True)
            await asyncio.sleep(self._interval)

    def start(self) -> None:
        """Begin sampling in the background."""
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop sampling."""
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    def summary(self, since: float, send_end: float) -> dict[str, Any]:
        """Max backlog during the run and seconds from `send_end` until `events` is drained."""
        rows = [r for r in self.samples if r["t"] >= since and "error" not in r]
        drained_at = next(
            (
                r["t"]
                for r in rows
                if r["t"] >= send_end
                and r.get("events_lag", 0) == 0
                and r.get("events_pending", 0) == 0
            ),
            None,
        )
        step = max(1, len(rows) // 240)
        return {
            "max_events_lag": max((r.get("events_lag", 0) for r in rows), default=0),
            "max_events_pending": max((r.get("events_pending", 0) for r in rows), default=0),
            "max_deliveries_lag": max((r.get("deliveries_lag", 0) for r in rows), default=0),
            "max_deliveries_pending": max(
                (r.get("deliveries_pending", 0) for r in rows), default=0
            ),
            "events_drained_after_s": None
            if drained_at is None
            else round(drained_at - send_end, 2),
            "samples": [{k: round(v, 2) for k, v in r.items()} for r in rows[::step]],
        }
