"""Event generator: sends a configurable mix of fixture events to ingest at a target rate.

Open-loop pacing: send times are computed from the start time, never from response times,
so a slow ingest shows up as latency/queueing instead of silently lowering the offered rate.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import random
import sys
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).parent / "fixtures"
INSTRUMENTS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "EURGBP", "NZDUSD", "USDCAD"]
RATES_REASONS = ["LIMIT_BREACH", "CREDIT_CHECK_FAILED", "INVALID_INSTRUMENT", "STALE_PRICE"]
FEEDS = ["reuters", "bloomberg"]
SOURCE_BY_KIND = {
    "rates": "rates-oms",
    "settlements": "settlements-engine",
    "unknown": "generic-webhook",
    "pricing": "generic-webhook",  # only used with --pricing-via-http
}
Unit = tuple[str, list[dict[str, Any]]]


@dataclass
class Item:
    """One message to send: an HTTP payload for a source, or a log line for the tailed file."""

    kind: str
    source_id: str | None
    payload: dict[str, Any] | None = None
    log_line: str | None = None


@dataclass
class Stats:
    """Counters and latencies collected by workers."""

    sent: int = 0
    accepted: int = 0
    log_lines: int = 0
    errors: Counter[str] = field(default_factory=Counter)
    latencies_ms: list[float] = field(default_factory=list)


def parse_mix(text: str) -> dict[str, float]:
    """Parse `rates:1,settlements:2` into weights; names must be rates|settlements|pricing."""
    mix: dict[str, float] = {}
    for part in text.split(","):
        name, _, weight = part.partition(":")
        name = name.strip()
        if name not in ("rates", "settlements", "pricing"):
            raise ValueError(f"unknown mix entry: {name!r}")
        mix[name] = float(weight or 1)
    if not mix or sum(mix.values()) <= 0:
        raise ValueError("mix must have a positive total weight")
    return mix


def percentile(values: list[float], pct: float) -> float:
    """Return the nearest-rank percentile of values (0 when empty)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * len(ordered)) - 1))
    return ordered[index]


def _iso_ms(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class PayloadFactory:
    """Builds varied payloads from the fixtures; deterministic for a given seed."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.counter = 0
        files = {
            "rates": "rates_trade_rejected",
            "settlements": "settlements_workflow_failed",
            "unknown": "unknown_payments",
            "pricing": "pricing_price_stale",
        }
        self.templates = {
            name: json.loads((FIXTURES / f"{file}.json").read_text())
            for name, file in files.items()
        }

    def build(self, kind: str, via_http_pricing: bool = False) -> Item:
        """Build one fresh (non-duplicate) item of the given kind."""
        self.counter += 1
        n = self.counter
        now = datetime.now(UTC)
        body = copy.deepcopy(self.templates[kind])
        if kind == "rates":
            body["meta"]["ts"] = int(now.timestamp() * 1000)
            body["payload"]["tradeId"] = f"T-{now:%Y%m%d}-{n:06d}"
            body["payload"]["reason"] = self.rng.choice(RATES_REASONS)
        elif kind == "settlements":
            body["workflowId"] = f"wf-settle-{now:%Y%m%d}-{n:06d}"
            body["timestamp"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        elif kind == "unknown":
            body["at"] = now.isoformat(timespec="seconds")
            body["data"]["paymentId"] = f"P-{n:06d}"
        else:
            instrument = self.rng.choice(INSTRUMENTS)
            feed = self.rng.choice(FEEDS)
            age = self.rng.randint(30, 60)
            msg = f"Price stale for {age}s"
            line = (
                f"{_iso_ms(now)} ERROR pricing-engine instrument={instrument} feed={feed} "
                f'age_ms={age * 1000} msg="{msg}"'
            )
            if not via_http_pricing:
                return Item("pricing", None, log_line=line)
            body.update(
                timestamp=_iso_ms(now),
                instrument=instrument,
                feed=feed,
                age_ms=str(age * 1000),
                msg=msg,
                raw_line=line,
            )
        return Item(kind, SOURCE_BY_KIND[kind], payload=body)


class Pacer:
    """Chooses the next item: a duplicate of an earlier one, an unknown event, or a mix item."""

    def __init__(
        self,
        factory: PayloadFactory,
        mix: dict[str, float],
        duplicate_ratio: float,
        unknown_ratio: float,
        pricing_via_http: bool,
    ) -> None:
        self.factory = factory
        self.rng = factory.rng
        self.kinds = list(mix)
        self.weights = list(mix.values())
        self.duplicate_ratio = duplicate_ratio
        self.unknown_ratio = unknown_ratio
        self.pricing_via_http = pricing_via_http
        self.history: deque[Item] = deque(maxlen=200)

    def next_item(self) -> Item:
        """Return the next item; duplicates are exact copies without an Idempotency-Key."""
        if self.history and self.rng.random() < self.duplicate_ratio:
            return self.rng.choice(self.history)
        if self.rng.random() < self.unknown_ratio:
            item = self.factory.build("unknown")
        else:
            kind = self.rng.choices(self.kinds, self.weights)[0]
            item = self.factory.build(kind, self.pricing_via_http)
        self.history.append(item)
        return item


async def send_unit(client: httpx.AsyncClient, base_url: str, unit: Unit, stats: Stats) -> None:
    """POST one message (or one batch) and record status and latency."""
    source_id, payloads = unit
    path = f"/api/v1/ingest/{source_id}" + ("/batch" if len(payloads) > 1 else "")
    body = payloads if len(payloads) > 1 else payloads[0]
    headers = {"X-Sent-At": datetime.now(UTC).isoformat(), "Content-Type": "application/json"}
    started = time.perf_counter()
    try:
        response = await client.post(base_url + path, content=json.dumps(body), headers=headers)
        status = str(response.status_code)
    except httpx.HTTPError as exc:
        status = type(exc).__name__
    stats.latencies_ms.append((time.perf_counter() - started) * 1000)
    stats.sent += len(payloads)
    if status == "202":
        stats.accepted += len(payloads)
    else:
        stats.errors[status] += len(payloads)


async def worker(
    queue: asyncio.Queue[Unit | None], client: httpx.AsyncClient, base_url: str, stats: Stats
) -> None:
    """Consume send units until a None sentinel arrives."""
    while (unit := await queue.get()) is not None:
        await send_unit(client, base_url, unit, stats)


def summary_line(stats: Stats, elapsed: float, prefix: str = "final") -> str:
    """Format counters, achieved msg/s and latency percentiles."""
    total = stats.sent + stats.log_lines
    return (
        f"[{prefix}] t={elapsed:.1f}s sent={total} (http={stats.sent} accepted={stats.accepted} "
        f"log_lines={stats.log_lines}) errors={dict(stats.errors)} "
        f"achieved={total / max(elapsed, 1e-9):.1f} msg/s "
        f"p50={percentile(stats.latencies_ms, 50):.1f}ms "
        f"p99={percentile(stats.latencies_ms, 99):.1f}ms"
    )


async def report_progress(stats: Stats, start: float, interval: float) -> None:
    """Print a progress line every `interval` seconds."""
    while True:
        await asyncio.sleep(interval)
        print(summary_line(stats, time.perf_counter() - start, prefix="progress"), flush=True)


async def run(args: argparse.Namespace) -> int:
    """Run the load; return the process exit code."""
    pacer = Pacer(
        PayloadFactory(random.Random(args.seed)),
        parse_mix(args.mix),
        args.duplicate_ratio,
        args.unknown_ratio,
        args.pricing_via_http,
    )
    stats = Stats()
    queue: asyncio.Queue[Unit | None] = asyncio.Queue()
    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    limits = httpx.Limits(
        max_connections=args.concurrency, max_keepalive_connections=args.concurrency
    )
    total = int(args.rate * args.duration)
    buffers: dict[str, list[dict[str, Any]]] = {}
    async with httpx.AsyncClient(limits=limits, http2=False, timeout=10.0) as client:
        # Tiny line-buffered local append; blocking is negligible next to HTTP I/O.
        with log_path.open("a", encoding="utf-8") as log_file:  # noqa: ASYNC230
            workers = [
                asyncio.create_task(worker(queue, client, args.base_url, stats))
                for _ in range(args.concurrency)
            ]
            start = time.perf_counter()
            progress = asyncio.create_task(report_progress(stats, start, args.progress))
            for i in range(total):
                delay = start + i / args.rate - time.perf_counter()
                if delay > 0:
                    await asyncio.sleep(delay)
                item = pacer.next_item()
                if item.log_line is not None:
                    log_file.write(item.log_line + "\n")
                    log_file.flush()
                    stats.log_lines += 1
                    continue
                assert item.source_id is not None and item.payload is not None
                buf = buffers.setdefault(item.source_id, [])
                buf.append(item.payload)
                if len(buf) >= args.batch_size:
                    queue.put_nowait((item.source_id, buf))
                    buffers[item.source_id] = []
            for source_id, buf in buffers.items():
                if buf:
                    queue.put_nowait((source_id, buf))
            for _ in workers:
                queue.put_nowait(None)
            await asyncio.gather(*workers)
            progress.cancel()
            elapsed = time.perf_counter() - start
    print(summary_line(stats, elapsed), flush=True)
    error_count = sum(stats.errors.values())
    return 1 if stats.sent and error_count / stats.sent > 0.01 else 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    p = argparse.ArgumentParser(description="Send a mix of fixture events to ingest.")
    p.add_argument("--base-url", default="http://localhost:8001")
    p.add_argument("--rate", type=float, default=100.0, help="target messages per second")
    p.add_argument("--duration", type=float, default=10.0, help="seconds")
    p.add_argument("--duplicate-ratio", type=float, default=0.0)
    p.add_argument("--unknown-ratio", type=float, default=0.0)
    p.add_argument("--mix", default="rates:1,settlements:1,pricing:1")
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--concurrency", type=int, default=32)
    p.add_argument("--log-file", default="data/logs/pricing_engine.log")
    p.add_argument("--pricing-via-http", action="store_true")
    p.add_argument("--progress", type=float, default=5.0)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--dry-run", action="store_true", help="print sample payloads and exit")
    return p


def dry_run(args: argparse.Namespace) -> None:
    """Print a few sample items without sending anything."""
    pacer = Pacer(
        PayloadFactory(random.Random(args.seed)),
        parse_mix(args.mix),
        args.duplicate_ratio,
        args.unknown_ratio,
        args.pricing_via_http,
    )
    for _ in range(6):
        item = pacer.next_item()
        print(item.source_id or "log-file", item.log_line or json.dumps(item.payload))


def main() -> None:
    """CLI entry point."""
    args = build_parser().parse_args()
    if args.dry_run:
        dry_run(args)
        return
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
