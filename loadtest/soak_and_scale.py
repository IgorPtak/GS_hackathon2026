"""Scale sweep and steady soak profiler with cgroup memory/CPU and Redis lag sampling.

Usage: uv run python loadtest/soak_and_scale.py --mode {scale,soak} [--rate R] [--duration S]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

sys.path.insert(0, str(Path(__file__).parent))
import cpu_bench  # noqa: E402
import profile_backends as pb  # noqa: E402
import scenario_stack as stack  # noqa: E402
from scenario_send import GROUPS  # noqa: E402

PROJECT, RESULTS, MIB = cpu_bench.PROJECT, cpu_bench.RESULTS, 1024 * 1024
_LAG_KEYS = ("events_lag", "events_pending", "deliveries_lag", "deliveries_pending")
_STEP_KEYS = "run_id accepted achieved_ingest_msg_s processed_msg_s lost is_settled".split()


def parse_scale_pairs(raw: str) -> list[tuple[int, int, int, int]]:
    """Parse `processor:delivery[:ingest[:outbox-relay]]` steps like `'1:1,2:2:2,4:4:3:2'`.

    Missing ingest and outbox-relay counts default to 1, so plain `p:d` pairs keep working.
    """
    steps = []
    for item in (p.strip() for p in raw.split(",") if p.strip()):
        parts = item.split(":")
        if not 2 <= len(parts) <= 4:
            raise ValueError(f"invalid scale step '{item}'; expected 'p:d[:i[:r]]'")
        counts = [int(x) for x in parts] + [1] * (4 - len(parts))
        if min(counts) < 1:
            raise ValueError(f"invalid scale step '{item}'; every replica count must be >= 1")
        steps.append((counts[0], counts[1], counts[2], counts[3]))
    if not steps:
        raise ValueError("at least one processor:delivery step is required")
    return steps


def parse_cgroup_sample(text: str) -> dict[str, int]:
    """Parse combined `memory.current` and `cpu.stat` output separated by `---`."""
    mem_raw, sep, cpu_raw = text.partition("---")
    if not sep:
        raise ValueError("missing '---' separator between memory.current and cpu.stat")
    return {"memory_bytes": int(mem_raw.strip()),
            "usage_usec": cpu_bench.parse_cpu_stat(cpu_raw)["usage_usec"]}  # fmt: skip


def linear_slope(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Compute ordinary least-squares slope of `ys` vs `xs` (0.0 when degenerate)."""
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    return 0.0 if denom <= 0 else num / denom


def _summarize_series(ts: Sequence[float], mems: Sequence[int], cpus: Sequence[int]) -> dict:
    mem_mb, t_min, iv_cpu = [b / MIB for b in mems], [t / 60.0 for t in ts], []
    for i in range(1, len(ts)):
        dt, du = ts[i] - ts[i - 1], cpus[i] - cpus[i - 1]
        if du < 0:
            raise ValueError(f"negative CPU usage_usec delta ({du}); did container restart?")
        if dt > 0:
            iv_cpu.append(du / (dt * 10_000))
    tot_dt = ts[-1] - ts[0]
    avg_cpu = (cpus[-1] - cpus[0]) / (tot_dt * 10_000) if tot_dt > 0 else 0.0
    return {"min_mb": round(min(mem_mb), 2), "max_mb": round(max(mem_mb), 2),
            "start_mb": round(mem_mb[0], 2), "end_mb": round(mem_mb[-1], 2),
            "growth_mb": round(mem_mb[-1] - mem_mb[0], 2), "avg_cpu_pct": round(avg_cpu, 1),
            "slope_mb_per_min": round(linear_slope(t_min, mem_mb), 3),
            "peak_cpu_pct": round(max(iv_cpu), 1) if iv_cpu else 0.0}  # fmt: skip


def summarize_soak_samples(samples: Sequence[dict[str, Any]], c2s: dict[str, str]) -> dict:
    """Summarize memory min/max/growth/slope MB, CPU%, and stream lag across soak samples."""
    if not samples:
        raise ValueError("at least one soak sample is required")
    times, svc_names = [float(s["t_s"]) for s in samples], {}
    for cname, svc in sorted(c2s.items()):
        svc_names.setdefault(svc, []).append(cname)

    def _agg(ns: Sequence[str]) -> dict[str, Any]:
        m = [sum(int(s["containers"][n]["memory_bytes"]) for n in ns) for s in samples]
        c = [sum(int(s["containers"][n]["usage_usec"]) for n in ns) for s in samples]
        return _summarize_series(times, m, c)

    return {"sample_count": len(samples), "duration_sampled_s": round(times[-1] - times[0], 2),
            "by_service": {s: {"replicas": len(ns), **_agg(ns)} for s, ns in svc_names.items()},
            "total": _agg(sorted(c2s)),
            "lag": {f"max_{k}": max((int(s["lag"].get(k, 0)) for s in samples), default=0)
                    for k in _LAG_KEYS}}  # fmt: skip


async def scale_pair(
    processor: int, delivery: int, ingest: int = 1, relay: int = 1, settle_s: float = 5.0
) -> None:
    """Scale the pipeline services, wait for healthy status, and let consumers join.

    Ingest replicas sit behind `proxy`, which re-resolves compose DNS every 5 s, so settle_s
    (default 5 s) also covers the proxy picking up new ingest replicas.
    """
    wanted = {"processor": processor, "delivery": delivery, "ingest": ingest, "outbox-relay": relay}
    scale_args = [arg for svc, n in wanted.items() for arg in ("--scale", f"{svc}={n}")]
    await stack.compose(
        "up", "-d", "--no-recreate", "--no-deps", "--no-build", *scale_args, *wanted
    )  # fmt: skip
    fmt = "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}"
    for _ in range(90):
        ids = {svc: await stack.running_containers(svc) for svc in wanted}
        if all(len(ids[svc]) == n for svc, n in wanted.items()):
            out = await stack.run_cmd("docker", "inspect", "--format", fmt, *sum(ids.values(), []))
            if all(s.strip() in ("healthy", "running") for s in out.splitlines() if s.strip()):
                break
        await asyncio.sleep(1.0)
    else:
        raise RuntimeError(f"timed out waiting for healthy replicas ({wanted})")
    await asyncio.sleep(max(settle_s, 0.0))


async def _take_soak_sample(ns: Sequence[str], redis: Redis, t0: float) -> dict[str, Any]:
    cmd = "cat /sys/fs/cgroup/memory.current && echo --- && cat /sys/fs/cgroup/cpu.stat"
    outs = await asyncio.gather(*(stack.run_cmd("docker", "exec", n, "sh", "-c", cmd) for n in ns))
    lag = dict.fromkeys(_LAG_KEYS, 0)
    for stream, group in GROUPS.items():
        with suppress(RedisError):
            for info in await redis.xinfo_groups(stream):
                if info["name"] == group:
                    lag[f"{stream}_lag"] = int(info.get("lag") or 0)
                    lag[f"{stream}_pending"] = int(info.get("pending") or 0)
    return {
        "t_s": round(time.monotonic() - t0, 2), "lag": lag,
        "containers": {n: parse_cgroup_sample(o) for n, o in zip(ns, outs, strict=True)},
    }  # fmt: skip


async def run_scale(args: argparse.Namespace) -> dict[str, Any]:
    """Sweep replica steps and always restore the compose defaults."""
    steps: list[dict[str, Any]] = []
    try:
        for p_rep, d_rep, i_rep, r_rep in args.pairs:
            print(f"--- scaling processor={p_rep} delivery={d_rep} ingest={i_rep} "
                  f"outbox-relay={r_rep} ---", flush=True)  # fmt: skip
            await scale_pair(p_rep, d_rep, i_rep, r_rep, args.settle_s)
            _, _, wall_s, s_file, rc = await pb.run_steady_synced(args)
            step = json.loads((RESULTS / s_file).read_text())["steps"][0]
            lat, lg = step["latency_ms"].get("all", {}), step["lag"]
            steps.append({"processor_replicas": p_rep, "delivery_replicas": d_rep,
                          "ingest_replicas": i_rep, "outbox_relay_replicas": r_rep,
                          "steady_file": s_file, "returncode": rc, "wall_s": round(wall_s, 3),
                          "p50_ms": lat.get("p50"), "p99_ms": lat.get("p99"),
                          "max_events_lag": lg["max_events_lag"],
                          "max_deliveries_lag": lg["max_deliveries_lag"],
                          "events_drained_after_s": lg["events_drained_after_s"],
                          **{k: step[k] for k in _STEP_KEYS}})  # fmt: skip
    finally:
        await stack.restore_stack()
    return {"steps": steps, "all_zero_lost": all(s["lost"] == 0 and s["is_settled"] for s in steps)}


async def run_soak(args: argparse.Namespace) -> dict[str, Any]:
    """Run steady load while sampling container cgroups and Redis lag periodically."""
    containers = await cpu_bench.discover_containers(PROJECT, args.services)
    names, url = list(containers), os.environ.get("LOADTEST_REDIS_URL", "redis://localhost:6379/0")
    redis = Redis.from_url(url, decode_responses=True)
    samples, stop, state = [], asyncio.Event(), [0.0, None]

    async def _loop() -> None:
        while not stop.is_set():
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=args.sample_interval)
                return
            samples.append(await _take_soak_sample(names, redis, state[0]))

    async def _on_ready() -> bool:
        state[:] = [time.monotonic(), asyncio.create_task(_loop())]
        samples.append(await _take_soak_sample(names, redis, state[0]))
        return True

    try:
        _, _, wall_s, s_file, rc = await pb.run_steady_synced(args, _on_ready)
        stop.set()
        await state[1]
        samples.append(await _take_soak_sample(names, redis, state[0]))
    finally:
        stop.set()
        if state[1] and not state[1].done():
            state[1].cancel()
            await asyncio.gather(state[1], return_exceptions=True)
        await redis.aclose()
    step = json.loads((RESULTS / s_file).read_text())["steps"][0]
    lat = step["latency_ms"].get("all", {})
    return {"steady_file": s_file, "returncode": rc, "wall_s": round(wall_s, 3), "samples": samples,
            "p50_ms": lat.get("p50"), "p99_ms": lat.get("p99"), "steady_lag": step["lag"],
            "summary": summarize_soak_samples(samples, containers),
            **{k: step[k] for k in _STEP_KEYS}}  # fmt: skip


def _format_output(mode: str, data: dict[str, Any]) -> str:
    if mode == "scale":
        hdr = (f"{'proc':>4} {'del':>3} {'ing':>3} {'rel':>3} {'ing/s':>7} {'p50':>6} {'p99':>7} "
               f"{'lag':>6} {'lost':>4}")  # fmt: skip
        rows = [f"{s['processor_replicas']:>4} {s['delivery_replicas']:>3} "
                f"{s['ingest_replicas']:>3} {s['outbox_relay_replicas']:>3} "
                f"{s['achieved_ingest_msg_s']:>7.1f} {str(s['p50_ms']):>6} {str(s['p99_ms']):>7} "
                f"{s['max_deliveries_lag']:>6} {s['lost']:>4}" for s in data["steps"]]  # fmt: skip
        return "\n".join([hdr, *rows, f"all_zero_lost={data['all_zero_lost']}"])
    sm, lg = data["summary"], data["summary"]["lag"]
    tot_r = sum(x["replicas"] for x in sm["by_service"].values())
    hdr = f"{'svc':<13} {'rep':>3} {'minMB':>7} {'maxMB':>7} {'grow':>6} {'MB/m':>6} {'cpu%':>6}"
    rows = [f"{svc:<13} {tot_r if svc == 'total' else r['replicas']:>3} {r['min_mb']:>7.2f} "
            f"{r['max_mb']:>7.2f} {r['growth_mb']:>6.2f} {r['slope_mb_per_min']:>6.3f} "
            f"{r['avg_cpu_pct']:>5.1f}%"
            for svc, r in [*sm["by_service"].items(), ("total", sm["total"])]]  # fmt: skip
    return "\n".join([
        hdr, *rows, f"lag_max(ev={lg['max_events_lag']}, dlv={lg['max_deliveries_lag']}) "
        f"p50={data['p50_ms']}ms p99={data['p99_ms']}ms lost={data['lost']}",
    ])  # fmt: skip


def build_parser() -> argparse.ArgumentParser:
    """CLI parser."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--mode", choices=["scale", "soak"], required=True)
    p.add_argument("--pairs", type=parse_scale_pairs, default=parse_scale_pairs("1:1,1:2,2:2,2:4"))
    for f, t, d in (
        ("--rate", float, None), ("--duration", float, None), ("--sample-interval", float, 15.0),
        ("--settle-s", float, 5.0), ("--concurrency", cpu_bench._positive_int, 16),
        ("--services", cpu_bench._csv, cpu_bench.DEFAULT_SERVICES), ("--label", str, ""),
        ("--image", str, "alerting-python:dev"), ("--network", str, "alerting_default"),
        ("--ingest-url", str, cpu_bench.DEFAULT_INGEST_URL),
    ):  # fmt: skip
        p.add_argument(f, type=t, default=d)
    return p


async def main_async(args: argparse.Namespace) -> int:
    """Execute `--mode scale` or `--mode soak` and write JSON to `loadtest/results/`."""
    started = datetime.now(UTC)
    args.rate = args.rate if args.rate is not None else (500.0 if args.mode == "scale" else 250.0)
    args.duration = args.duration or (20.0 if args.mode == "scale" else 120.0)
    res = await (run_scale(args) if args.mode == "scale" else run_soak(args))
    payload = {"mode": args.mode, "started_at": started.isoformat(), "label": args.label,
               "git": await cpu_bench.git_info(), "rate": args.rate, "duration_s": args.duration,
               **res}  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{args.mode}-{started:%Y%m%dT%H%M%S}.json"
    out.write_text(json.dumps(payload, indent=2))
    print(_format_output(args.mode, res) + f"\nwrote {out}")
    ok = res["all_zero_lost"] if args.mode == "scale" else (res["lost"] == 0 and res["is_settled"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async(build_parser().parse_args())))
