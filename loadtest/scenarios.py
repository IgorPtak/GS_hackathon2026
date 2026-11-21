"""Load-test scenarios with lost/p50/p99 measurement.

Usage: uv run python loadtest/scenarios.py {steady,saturation,dup-storm,gateway-down,kill-processor}
       [--rate R] [--duration S]
Each run writes loadtest/results/<name>-<timestamp>.json. See docs/load-test-results.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
from alerting_core.connections import _init_connection
from redis.asyncio import Redis

sys.path.insert(0, str(Path(__file__).parent))
import scenario_measure as measure  # noqa: E402
import scenario_stack as stack  # noqa: E402
from scenario_send import EXPECTED_PER_ALERT, LagSampler, build_event, send_events  # noqa: E402

RESULTS = Path(__file__).parent / "results"
SCENARIOS = ["steady", "saturation", "dup-storm", "gateway-down", "kill-processor"]
DOCKER_SCENARIOS = frozenset({"saturation", "gateway-down", "kill-processor"})
P99_LIMIT_MS = 2000.0
DRAIN_LIMIT_S = 5.0


@dataclass
class Ctx:
    """Connections and settings shared by every scenario."""

    pool: asyncpg.Pool
    redis: Redis
    base_url: str
    concurrency: int = 16
    sync_stdin: bool = False


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (0 for an empty list)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(pct / 100 * len(ordered)) - 1))]


async def run_step(
    ctx: Ctx,
    name: str,
    rate: float,
    duration: float,
    *,
    batch_size: int = 1,
    settle_timeout: float = 90.0,
    is_duplicate_storm: bool = False,
    total: int | None = None,
    side_actions: Callable[[], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Send one load step, wait for it to settle and measure it. `side_actions` runs alongside."""
    run_id = f"{name}-{uuid.uuid4().hex[:8]}"
    count = total if total is not None else int(rate * duration)
    since = time.time() - 30
    offset = await measure.clock_offset_s(ctx.pool)
    if ctx.sync_stdin:
        print(f"BENCH_READY {run_id}", flush=True)
        await asyncio.to_thread(sys.stdin.readline)
    sampler = LagSampler(ctx.redis)
    sampler.start()
    evt = f"{run_id}-dup" if is_duplicate_storm else None
    side = asyncio.create_task(side_actions()) if side_actions else None
    try:
        sent = await send_events(
            ctx.base_url,
            count,
            rate,
            lambda seq: build_event(run_id, seq, evt),
            batch_size=batch_size,
            concurrency=ctx.concurrency,
        )
        if side:
            await side
        expected_alerts = 1 if is_duplicate_storm else sent.accepted
        counts, is_settled = await measure.wait_settled(
            ctx.pool, run_id, since, expected_alerts, sent.accepted, settle_timeout
        )
    finally:
        if side and not side.done():
            side.cancel()
        await sampler.stop()
    if ctx.sync_stdin:
        print(f"BENCH_SETTLED {run_id}", flush=True)
    return await _assemble(
        ctx, run_id, rate, duration, batch_size, sent, sampler, counts, is_settled,
        expected_alerts, since, offset,
    )  # fmt: skip


async def _assemble(
    ctx: Ctx, run_id: str, rate: float, duration: float, batch_size: int, sent: Any,
    sampler: LagSampler, counts: dict[str, Any], is_settled: bool, expected_alerts: int,
    since: float, offset: float,
) -> dict[str, Any]:  # fmt: skip
    expected = EXPECTED_PER_ALERT * expected_alerts
    covered = counts["dead_lettered_covered_by_delivered_fallback"]
    span = (counts["last_alert_at"] or 0) - (counts["first_alert_at"] or 0)
    latency = await measure.latency_ms(ctx.pool, run_id, since, offset)
    lag = sampler.summary(since, sent.ended_wall)
    p99 = latency.get("all", {}).get("p99")
    return {
        "run_id": run_id,
        "target_rate": rate,
        "duration_s": duration,
        "batch_size": batch_size,
        "concurrency": ctx.concurrency,
        "sent": sent.sent,
        "accepted": sent.accepted,
        "http_errors": dict(sent.errors),
        "ingest_http_ms": {
            "p50": round(percentile(sent.http_ms, 50), 1),
            "p99": round(percentile(sent.http_ms, 99), 1),
        },
        "achieved_ingest_msg_s": round(sent.achieved_msg_s, 1),
        "processed_alerts": counts["alerts"],
        "processed_events": counts["folded_events"],
        "processed_msg_s": round(counts["alerts"] / span, 1) if span > 1 else None,
        "expected_deliveries": expected,
        "delivered": counts["delivered_primary"],
        "covered_by_fallback": covered,
        "lost": expected - counts["delivered_primary"] - covered,
        "lost_strict_without_fallback": expected - counts["delivered_primary"],
        "is_settled": is_settled,
        "counts": counts,
        "latency_ms": latency,
        "lag": lag,
        "is_drained_within_limit": (
            lag["events_drained_after_s"] is not None
            and lag["events_drained_after_s"] <= DRAIN_LIMIT_S
        ),
        "is_p99_under_limit": p99 is not None and p99 < P99_LIMIT_MS,
        "prometheus_e2e_p99_s": await measure.prometheus_p99_s(),
    }


async def steady(ctx: Ctx, args: argparse.Namespace) -> dict[str, Any]:
    """Constant load; every alert must end up delivered."""
    return {"steps": [await run_step(ctx, "steady", args.rate, args.duration)]}


async def dup_storm(ctx: Ctx, args: argparse.Namespace) -> dict[str, Any]:
    """N identical events must fold into one alert with count N and one delivery per channel."""
    total = args.total
    step = await run_step(
        ctx, "dup-storm", args.rate, total / args.rate, total=total, is_duplicate_storm=True,
        settle_timeout=60.0,
    )  # fmt: skip
    # The alert keeps only the last event's sent_ms, so e2e latency is not defined for a fold.
    step["latency_ms"] = {}
    step["latency_note"] = "not measured: one alert for N events"
    step["is_dedup_correct"] = (
        step["processed_alerts"] == 1
        and step["processed_events"] == step["accepted"]
        and step["delivered"] == EXPECTED_PER_ALERT
    )
    return {"steps": [step]}


async def gateway_down(ctx: Ctx, args: argparse.Namespace) -> dict[str, Any]:
    """Stop mock-gateway during load; sms deliveries must end delivered or via fallback."""
    events: list[dict[str, Any]] = []

    async def outage() -> None:
        await asyncio.sleep(args.down_after)
        await stack.compose("stop", "mock-gateway")
        events.append({"action": "stop", "at": time.time()})
        await asyncio.sleep(args.down_for)
        await stack.compose("start", "mock-gateway")
        events.append({"action": "start", "at": time.time()})

    try:
        step = await run_step(
            ctx, "gateway-down", args.rate, args.duration, settle_timeout=180.0,
            side_actions=outage,
        )  # fmt: skip
    finally:
        await stack.compose("start", "mock-gateway")
    step["side_events"] = events
    return {"steps": [step]}


async def kill_processor(ctx: Ctx, args: argparse.Namespace) -> dict[str, Any]:
    """Two processors under load; kill one mid-run. Redelivery (XAUTOCLAIM) must recover."""
    events: list[dict[str, Any]] = []
    await stack.scale("processor", 2)

    async def kill() -> None:
        await asyncio.sleep(args.kill_after)
        container = await stack.kill_one("processor")
        events.append({"action": "docker kill", "container": container, "at": time.time()})

    step = await run_step(
        ctx, "kill-processor", args.rate, args.duration, settle_timeout=150.0, side_actions=kill
    )
    step["side_events"] = events
    return {"steps": [step], "processor_replicas": 2}


async def saturation(ctx: Ctx, args: argparse.Namespace) -> dict[str, Any]:
    """Rate steps for each processor replica count; stops climbing after the first failed step."""
    table: list[dict[str, Any]] = []
    await stack.scale("delivery", args.delivery_replicas, settle_s=3)
    for replicas in args.replicas:
        await stack.scale("processor", replicas)
        for rate in args.rates:
            batch = args.batch_size if rate >= args.batch_from else 1
            step = await run_step(
                ctx, f"sat-p{replicas}-r{int(rate)}", rate, args.duration, batch_size=batch,
                settle_timeout=90.0,
            )  # fmt: skip
            step["processor_replicas"] = replicas
            step["delivery_replicas"] = args.delivery_replicas
            step["is_sustainable"] = (
                step["is_drained_within_limit"]
                and step["is_p99_under_limit"]
                and step["lost"] == 0
                and step["http_errors"] == {}
            )
            table.append(step)
            print_step(step)
            if not step["is_sustainable"]:
                break
    best = {
        str(r): max(
            (
                s["target_rate"]
                for s in table
                if s["processor_replicas"] == r and s["is_sustainable"]
            ),
            default=None,
        )
        for r in args.replicas
    }
    return {"steps": table, "max_sustainable_msg_s_by_processor_replicas": best}


def print_step(step: dict[str, Any]) -> None:
    """One summary line per step."""
    lat = step["latency_ms"].get("all", {})
    print(
        f"[{step['run_id']}] sent={step['sent']} accepted={step['accepted']} "
        f"alerts={step['processed_alerts']} delivered={step['delivered']}/"
        f"{step['expected_deliveries']} fallback={step['covered_by_fallback']} lost={step['lost']} "
        f"ingest={step['achieved_ingest_msg_s']}/s processed={step['processed_msg_s']}/s "
        f"p50={lat.get('p50')}ms p99={lat.get('p99')}ms "
        f"drain={step['lag']['events_drained_after_s']}s settled={step['is_settled']}",
        flush=True,
    )


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def build_parser() -> argparse.ArgumentParser:
    """CLI parser."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("scenario", choices=SCENARIOS)
    p.add_argument("--rate", type=float, help="msg/s (default depends on the scenario)")
    p.add_argument("--duration", type=float, help="seconds of load")
    p.add_argument("--base-url", default=os.environ.get("INGEST_URL", "http://localhost:8001"))
    # 16 keeps Docker Desktop port forwarding error-free; inside the network more is fine.
    p.add_argument(
        "--concurrency", type=_positive_int, default=16, help="HTTP connections to ingest"
    )
    p.add_argument(
        "--sync-stdin",
        action="store_true",
        help="Wait for stdin newline at BENCH_READY and emit BENCH_SETTLED after settling",
    )
    p.add_argument("--total", type=int, default=5000, help="dup-storm: identical events")
    p.add_argument("--down-after", type=float, default=10.0, help="gateway-down: stop at t=")
    p.add_argument("--down-for", type=float, default=60.0, help="gateway-down: outage seconds")
    p.add_argument("--kill-after", type=float, default=20.0, help="kill-processor: kill at t=")
    p.add_argument("--replicas", type=lambda s: [int(x) for x in s.split(",")], default=[1, 2, 4])
    p.add_argument(
        "--rates", type=lambda s: [float(x) for x in s.split(",")], default=[250, 500, 1000, 2000]
    )
    p.add_argument("--delivery-replicas", type=int, default=1)
    p.add_argument("--batch-size", type=int, default=10, help="saturation: batch at high rates")
    p.add_argument("--batch-from", type=float, default=1000, help="saturation: rate for batching")
    return p


DEFAULTS = {
    "steady": (200.0, 60.0),
    "dup-storm": (1000.0, 5.0),
    "gateway-down": (100.0, 90.0),
    "kill-processor": (200.0, 60.0),
    "saturation": (0.0, 20.0),
}


async def _collect_hardware() -> dict[str, Any]:
    return await stack.hardware(
        {
            # None when generated inside the compose network (no docker CLI to count with).
            "processor": len(await stack.running_containers("processor"))
            if stack.has_docker()
            else None,
            "delivery": len(await stack.running_containers("delivery"))
            if stack.has_docker()
            else None,
            "ingest_workers": int(os.environ.get("INGEST_WORKERS", "2")),
        }
    )


async def main_async(args: argparse.Namespace) -> int:
    """Run one scenario, always restore the stack, write the JSON; non-zero exit if lost != 0."""
    if args.scenario in DOCKER_SCENARIOS and not stack.has_docker():
        print(
            f"error: scenario '{args.scenario}' requires the docker CLI on the host",
            file=sys.stderr,
        )
        return 2
    rate, duration = DEFAULTS[args.scenario]
    args.rate = args.rate or rate
    args.duration = args.duration or duration
    dsn = os.environ.get(
        "LOADTEST_DATABASE_URL",
        "postgresql://alerting:change-me-local-only@localhost:5432/alerting",
    )
    redis = Redis.from_url(
        os.environ.get("LOADTEST_REDIS_URL", "redis://localhost:6379/0"), decode_responses=True
    )
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4, init=_init_connection)
    ctx = Ctx(pool, redis, args.base_url, args.concurrency, getattr(args, "sync_stdin", False))
    started = datetime.now(UTC)
    runners = {
        "steady": steady, "saturation": saturation, "dup-storm": dup_storm,
        "gateway-down": gateway_down, "kill-processor": kill_processor,
    }  # fmt: skip
    try:
        await stack.install_loadtest_config(pool, redis)
        await asyncio.sleep(2)
        result = await runners[args.scenario](ctx, args)
        result["hardware"] = await _collect_hardware()
    finally:
        await stack.restore_stack()
        await redis.aclose()
        await pool.close()
    result |= {"scenario": args.scenario, "started_at": started.isoformat()}
    path = RESULTS / f"{args.scenario}-{started:%Y%m%dT%H%M%S}.json"
    RESULTS.mkdir(exist_ok=True)
    path.write_text(json.dumps(result, indent=2, default=str))
    for step in result["steps"]:
        print_step(step)
    print(f"wrote {path}")
    if args.scenario == "saturation":
        return 0
    return 0 if all(s["lost"] == 0 and s["is_settled"] for s in result["steps"]) else 1


def main() -> None:
    """CLI entry point."""
    sys.exit(asyncio.run(main_async(build_parser().parse_args())))


if __name__ == "__main__":
    main()
