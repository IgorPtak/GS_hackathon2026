"""Measure cgroup CPU time per accepted event per service over repeated in-network steady runs.

Usage: uv run python loadtest/cpu_bench.py [--rate 500] [--duration 30] [--runs 3]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
import scenario_stack as stack  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
RESULTS = Path(__file__).parent / "results"
PROJECT = "alerting"
_DEFAULT_SERVICES_STR = "ingest processor outbox-relay delivery mock-gateway postgres redis"
DEFAULT_SERVICES = tuple(_DEFAULT_SERVICES_STR.split())


def parse_cpu_stat(text: str) -> dict[str, int]:
    """Parse `/sys/fs/cgroup/cpu.stat` lines into integer counters."""
    stats = {p[0]: int(p[1]) for ln in text.splitlines() if len(p := ln.split()) == 2}
    if "usage_usec" not in stats:
        raise ValueError("missing 'usage_usec' in cpu.stat output")
    return stats


def _rate_fields(delta_usec: int, accepted: int, wall_s: float) -> dict[str, Any]:
    return {
        "delta_usec": delta_usec,
        "usec_per_event": round(delta_usec / accepted, 1),
        "avg_cpu_pct": round(delta_usec / (wall_s * 10_000), 1),
    }


def compute_cpu_per_event(
    before: dict[str, dict[str, int]],
    after: dict[str, dict[str, int]],
    container_to_service: dict[str, str],
    accepted: int,
    wall_s: float,
) -> dict[str, Any]:
    """Compute per-container, per-service and total CPU microseconds per accepted event."""
    if accepted <= 0 or wall_s <= 0:
        raise ValueError(f"accepted ({accepted}) and wall_s ({wall_s}) must be > 0")
    by_container: dict[str, dict[str, Any]] = {}
    svc_acc: dict[str, dict[str, int]] = {}
    for name in sorted(container_to_service):
        if name not in before or name not in after:
            raise ValueError(f"missing cpu.stat snapshot for container '{name}'")
        delta = after[name]["usage_usec"] - before[name]["usage_usec"]
        if delta < 0:
            raise ValueError(f"negative usage_usec delta ({delta}) for '{name}'; did it restart?")
        svc = container_to_service[name]
        by_container[name] = {
            "service": svc, **_rate_fields(delta, accepted, wall_s),
            "user_usec": after[name].get("user_usec", 0) - before[name].get("user_usec", 0),
            "system_usec": after[name].get("system_usec", 0) - before[name].get("system_usec", 0),
        }  # fmt: skip
        acc = svc_acc.setdefault(svc, {"replicas": 0, "delta_usec": 0})
        acc["replicas"] += 1
        acc["delta_usec"] += delta
    by_service = {
        s: {"replicas": a["replicas"], **_rate_fields(a["delta_usec"], accepted, wall_s)}
        for s, a in svc_acc.items()
    }
    total_delta = sum(acc["delta_usec"] for acc in svc_acc.values())
    return {
        "wall_s": round(wall_s, 3), "total_delta_usec": total_delta,
        "total_usec_per_event": round(total_delta / accepted, 1),
        "by_service": by_service, "by_container": by_container,
    }  # fmt: skip


def _median_or_none(values: list[float]) -> float | None:
    return round(statistics.median(values), 1) if values else None


def _series_summary(vals: list[float], cpus: list[float]) -> dict[str, Any]:
    return {
        "runs_usec_per_event": vals,
        "median_usec_per_event": _median_or_none(vals),
        "median_avg_cpu_pct": _median_or_none(cpus),
    }


def summarize_runs(runs: list[dict[str, Any]], services: Sequence[str]) -> dict[str, Any]:
    """Aggregate per-run CPU/event and latency into medians across runs."""
    by_svc = [r["cpu_per_event"]["by_service"] for r in runs]
    by_service = {
        s: _series_summary(
            [m[s]["usec_per_event"] for m in by_svc], [m[s]["avg_cpu_pct"] for m in by_svc]
        )
        for s in services
    }
    totals = [r["cpu_per_event"]["total_usec_per_event"] for r in runs]
    tot_cpus = [sum(m[s]["avg_cpu_pct"] for s in services) for m in by_svc]
    return {
        "by_service": by_service, "total": _series_summary(totals, tot_cpus),
        "median_p50_ms": _median_or_none([r["p50_ms"] for r in runs if r["p50_ms"] is not None]),
        "median_p99_ms": _median_or_none([r["p99_ms"] for r in runs if r["p99_ms"] is not None]),
        "all_zero_lost": all(r["lost"] == 0 and r["is_settled"] for r in runs),
    }  # fmt: skip


async def discover_containers(project: str, services: Sequence[str]) -> dict[str, str]:
    """Return sorted `{container_name: service_name}` for running compose containers."""
    out = await stack.run_cmd(
        "docker", "ps", "--filter", f"label=com.docker.compose.project={project}",
        "--format", '{{.Names}}\t{{.Label "com.docker.compose.service"}}',
    )  # fmt: skip
    wanted = set(services)
    mapping = {
        parts[0]: parts[1]
        for line in out.splitlines()
        if len(parts := line.split("\t")) == 2 and parts[1] in wanted
    }
    missing = sorted(wanted - set(mapping.values()))
    if missing:
        raise RuntimeError(f"missing running containers for services: {', '.join(missing)}")
    return dict(sorted(mapping.items()))


async def snapshot_cpu(containers: Sequence[str]) -> dict[str, dict[str, int]]:
    """Read `/sys/fs/cgroup/cpu.stat` concurrently for every container."""
    outputs = await asyncio.gather(
        *(stack.run_cmd("docker", "exec", n, "cat", "/sys/fs/cgroup/cpu.stat") for n in containers)
    )
    return {name: parse_cpu_stat(out) for name, out in zip(containers, outputs, strict=True)}


def _build_load_cmd(args: argparse.Namespace) -> list[str]:
    db = "postgresql://alerting:change-me-local-only@postgres:5432/alerting"
    return [
        "docker", "run", "--rm", "-i", "--network", args.network, "-v", f"{REPO}:/work",
        "-w", "/work", "-e", "INGEST_URL=http://ingest:8001", "-e", f"LOADTEST_DATABASE_URL={db}",
        "-e", "LOADTEST_REDIS_URL=redis://redis:6379/0", args.image, "python",
        "loadtest/scenarios.py", "steady", "--rate", str(args.rate),
        "--duration", str(args.duration), "--concurrency", str(args.concurrency), "--sync-stdin",
    ]  # fmt: skip


async def _drive_steady_process(
    proc: asyncio.subprocess.Process, names: Sequence[str]
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]], float, str, list[str]]:
    assert proc.stdin is not None and proc.stdout is not None
    before = after = None
    t0 = t1 = 0.0
    steady_filename: str | None = None
    lines: list[str] = []
    async for raw in proc.stdout:
        line = raw.decode(errors="replace").rstrip("\r\n")
        lines.append(line)
        if line.startswith("BENCH_READY "):
            before = await snapshot_cpu(names)
            t0 = time.monotonic()
            proc.stdin.write(b"\n")
            await proc.stdin.drain()
        elif line.startswith("BENCH_SETTLED "):
            t1 = time.monotonic()
            after = await snapshot_cpu(names)
        elif line.startswith("wrote "):
            steady_filename = Path(line.removeprefix("wrote ").strip()).name
        elif line.startswith("[steady"):
            print(line, flush=True)
    if before is None or after is None or steady_filename is None:
        raise RuntimeError("missing handshake/output from scenarios.py:\n" + "\n".join(lines))
    return before, after, t1 - t0, steady_filename, lines


async def run_once(args: argparse.Namespace, containers: dict[str, str]) -> dict[str, Any]:
    """Run one synchronized steady pass inside the compose network and attach CPU/event."""
    proc = await asyncio.create_subprocess_exec(
        *_build_load_cmd(args), cwd=REPO, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )  # fmt: skip
    try:
        before, after, wall_s, steady_file, lines = await _drive_steady_process(
            proc, list(containers)
        )
        rc = await proc.wait()
    except BaseException:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        raise
    finally:
        if proc.stdin and not proc.stdin.is_closing():
            proc.stdin.close()
    if rc != 0:
        raise RuntimeError(f"steady failed (exit {rc}):\n" + "\n".join(lines))
    steady_path = RESULTS / steady_file
    steady_data = json.loads(steady_path.read_text())
    step = steady_data["steps"][0]
    cpu = compute_cpu_per_event(before, after, containers, int(step["accepted"]), wall_s)
    step["cpu_per_event"] = cpu
    steady_path.write_text(json.dumps(steady_data, indent=2))
    lat = step["latency_ms"].get("all", {})
    return {
        "run_id": step["run_id"], "steady_file": steady_file,
        "accepted": step["accepted"], "achieved_ingest_msg_s": step["achieved_ingest_msg_s"],
        "lost": step["lost"], "is_settled": step["is_settled"], "p50_ms": lat.get("p50"),
        "p99_ms": lat.get("p99"), "wall_s": round(wall_s, 3), "cpu_per_event": cpu,
    }  # fmt: skip


async def git_info() -> dict[str, Any]:
    """Best-effort git commit, branch and dirty status."""
    try:
        dirty = await stack.run_cmd("git", "status", "--porcelain", "--untracked-files=no")
        return {
            "commit": await stack.run_cmd("git", "rev-parse", "--short", "HEAD"),
            "branch": await stack.run_cmd("git", "rev-parse", "--abbrev-ref", "HEAD"),
            "is_dirty": bool(dirty),
        }
    except RuntimeError:
        return {"commit": "unknown", "branch": "unknown", "is_dirty": None}


def format_table(summary: dict[str, Any], services: Sequence[str], replicas: dict[str, int]) -> str:
    """Format raw runs and medians as an ASCII table."""
    n = len(summary["total"]["runs_usec_per_event"])
    run_hdr = " ".join(f"{'run' + str(i + 1):>8}" for i in range(n))
    lines = [f"{'service':<14} {'rep':>3} {run_hdr} {'median us':>10} {'med CPU%':>9}"]
    for svc in [*services, "total"]:
        row = summary["total"] if svc == "total" else summary["by_service"][svc]
        rep = sum(replicas.values()) if svc == "total" else replicas[svc]
        vals = " ".join(f"{v:8.1f}" for v in row["runs_usec_per_event"])
        med_u, med_c = row["median_usec_per_event"], row["median_avg_cpu_pct"]
        lines.append(f"{svc:<14} {rep:>3} {vals} {med_u:>10.1f} {med_c:>8.1f}%")
    p50, p99, ok = summary["median_p50_ms"], summary["median_p99_ms"], summary["all_zero_lost"]
    lines.append(f"median p50={p50} ms  median p99={p99} ms  all_zero_lost={ok}")
    return "\n".join(lines)


def _positive_int(raw: str) -> int:
    if (value := int(raw)) < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def _csv(raw: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in raw.split(",") if x.strip())


def build_parser() -> argparse.ArgumentParser:
    """CLI parser."""
    p = argparse.ArgumentParser(description=__doc__)
    for flag, typ, default in (
        ("--rate", float, 500.0), ("--duration", float, 30.0), ("--runs", _positive_int, 3),
        ("--concurrency", _positive_int, 16), ("--cooldown", float, 3.0),
        ("--services", _csv, DEFAULT_SERVICES), ("--image", str, "alerting-python:dev"),
        ("--network", str, "alerting_default"), ("--label", str, ""),
    ):  # fmt: skip
        p.add_argument(flag, type=typ, default=default)
    return p


async def main_async(args: argparse.Namespace) -> int:
    """Run `--runs` steady passes, measure cgroup CPU/event, write summary JSON."""
    started = datetime.now(UTC)
    containers = await discover_containers(PROJECT, args.services)
    replicas = {svc: sum(1 for s in containers.values() if s == svc) for svc in args.services}
    runs_detail: list[dict[str, Any]] = []
    for idx in range(args.runs):
        if idx > 0 and args.cooldown > 0:
            await asyncio.sleep(args.cooldown)
        print(f"--- run {idx + 1}/{args.runs} ({args.rate}/s, {args.duration}s) ---", flush=True)
        runs_detail.append(await run_once(args, containers))
    summary = summarize_runs(runs_detail, args.services)
    payload = {
        "started_at": started.isoformat(), "git": await git_info(), "label": args.label,
        "rate": args.rate, "duration_s": args.duration, "concurrency": args.concurrency,
        "runs": args.runs, "services": list(args.services), "replicas": replicas,
        "summary": summary, "runs_detail": runs_detail,
    }  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    out_path = RESULTS / f"cpu-bench-{started:%Y%m%dT%H%M%S}.json"
    out_path.write_text(json.dumps(payload, indent=2))
    print(format_table(summary, args.services, replicas) + f"\nwrote {out_path}")
    return 0 if summary["all_zero_lost"] else 1


def main() -> None:
    """CLI entry point."""
    sys.exit(asyncio.run(main_async(build_parser().parse_args())))


if __name__ == "__main__":
    main()
