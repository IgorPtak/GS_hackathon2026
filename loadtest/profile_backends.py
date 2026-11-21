"""Profile Postgres and Redis per accepted event around an in-network steady load run.

Usage: uv run python loadtest/profile_backends.py [--rate 250] [--duration 30]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
import cpu_bench  # noqa: E402
import scenario_stack as stack  # noqa: E402

REPO, RESULTS = cpu_bench.REPO, cpu_bench.RESULTS
_TBL_COLS = (
    "seq_scan", "seq_tup_read", "idx_scan", "idx_tup_fetch",
    "n_tup_ins", "n_tup_upd", "n_tup_del", "n_tup_hot_upd",
)  # fmt: skip
_PG_STMT_SQL = (
    "SELECT coalesce(json_agg(t),'[]'::json) FROM (SELECT queryid::text AS queryid, "
    "min(regexp_replace(trim(query),'\\s+',' ','g')) AS query, sum(calls)::bigint AS calls, "
    "sum(total_exec_time)::float8 AS total_exec_time, sum(rows)::bigint AS rows FROM "
    "pg_stat_statements WHERE dbid=(SELECT oid FROM pg_database WHERE datname=current_database()) "
    "GROUP BY queryid) t"
)  # fmt: skip
_PG_TBL_SQL = (
    "SELECT coalesce(json_agg(t),'[]'::json) FROM (SELECT relname, "
    + ", ".join(f"coalesce({c},0)::bigint AS {c}" for c in _TBL_COLS)
    + ", coalesce(n_live_tup,0)::bigint AS n_live_tup, coalesce(n_dead_tup,0)::bigint "
    "AS n_dead_tup FROM pg_stat_user_tables ORDER BY relname) t"
)  # fmt: skip


def parse_redis_commandstats(text: str) -> dict[str, dict[str, int]]:
    """Parse `redis-cli INFO commandstats` output into `{command: {calls, usec, ...}}`."""
    stats: dict[str, dict[str, int]] = {}
    for raw in text.splitlines():
        if (line := raw.strip()).startswith("cmdstat_") and ":" in line:
            name, _, fields = line.partition(":")
            p = {k: int(v) for it in fields.split(",") for k, s, v in [it.partition("=")]
                 if s and k in ("calls", "usec", "rejected_calls", "failed_calls")}  # fmt: skip
            if "calls" in p and "usec" in p:
                stats[name.removeprefix("cmdstat_")] = p
    return stats


def compute_redis_delta(
    before: dict[str, dict[str, int]], after: dict[str, dict[str, int]],
    accepted: int, top_n: int = 15,
) -> dict[str, Any]:  # fmt: skip
    """Compute per-command Redis call and time deltas normalized by accepted events."""
    if accepted <= 0:
        raise ValueError(f"accepted ({accepted}) must be > 0")
    rows: list[dict[str, Any]] = []
    for cmd, cur in after.items():
        prev = before.get(cmd, {})
        c, u = cur["calls"] - prev.get("calls", 0), cur["usec"] - prev.get("usec", 0)
        if c < 0 or u < 0:
            raise ValueError(f"negative commandstats delta for '{cmd}'; did Redis restart?")
        if c > 0:
            rows.append({"command": cmd, "calls": c, "usec": u, "usec_per_call": round(u / c, 2),
                         "calls_per_event": round(c / accepted, 3),
                         "usec_per_event": round(u / accepted, 2)})  # fmt: skip
    rows.sort(key=lambda r: (-r["usec"], -r["calls"], r["command"]))
    tc, tu = sum(r["calls"] for r in rows), sum(r["usec"] for r in rows)
    return {"total_calls": tc, "total_usec": tu, "commands": rows[:top_n],
            "total_calls_per_event": round(tc / accepted, 3),
            "total_usec_per_event": round(tu / accepted, 2)}  # fmt: skip


def compute_pg_statements_delta(
    before: Sequence[dict[str, Any]], after: Sequence[dict[str, Any]],
    accepted: int, top_n: int = 15,
) -> list[dict[str, Any]]:  # fmt: skip
    """Compute top-N `pg_stat_statements` deltas sorted by total execution ms."""
    if accepted <= 0:
        raise ValueError(f"accepted ({accepted}) must be > 0")
    prev_map, rows = {str(r["queryid"]): r for r in before}, []
    for cur in after:
        qid, prev = str(cur["queryid"]), prev_map.get(str(cur["queryid"]), {})
        c = int(cur["calls"]) - int(prev.get("calls", 0))
        if c < 0:
            raise ValueError(f"negative pg_stat_statements delta for queryid '{qid}'")
        if c > 0:
            ms = max(0.0, float(cur["total_exec_time"]) - float(prev.get("total_exec_time", 0.0)))
            rd = max(0, int(cur.get("rows", 0)) - int(prev.get("rows", 0)))
            rows.append({"queryid": qid, "query": str(cur["query"]), "calls": c, "rows": rd,
                         "calls_per_event": round(c / accepted, 3), "total_ms": round(ms, 3),
                         "mean_ms": round(ms / c, 3), "ms_per_event": round(ms / accepted, 3),
                         "rows_per_call": round(rd / c, 2)})  # fmt: skip
    rows.sort(key=lambda r: (-r["total_ms"], -r["calls"], r["queryid"]))
    return rows[:top_n]


def compute_pg_tables_delta(
    before: Sequence[dict[str, Any]], after: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Compute per-table scan and tuple mutation deltas from `pg_stat_user_tables`."""
    prev_map, out = {str(r["relname"]): r for r in before}, []
    for cur in after:
        name, prev = str(cur["relname"]), prev_map.get(str(cur["relname"]), {})
        d = {k: max(0, int(cur.get(k, 0)) - int(prev.get(k, 0))) for k in _TBL_COLS}
        act = d["seq_scan"] + d["idx_scan"] + d["n_tup_ins"] + d["n_tup_upd"] + d["n_tup_del"]
        if act > 0:
            out.append({"table": name, **d, "activity": act,
                        "n_live_tup": int(cur.get("n_live_tup", 0)),
                        "n_dead_tup": int(cur.get("n_dead_tup", 0))})  # fmt: skip
    out.sort(key=lambda r: (-r["activity"], r["table"]))
    return out


async def _psql(container: str, user: str, db: str, sql: str) -> Any:
    cmd = ["docker", "exec", container, "psql", "-U", user, "-d", db, "-X", "-A", "-t"]
    out = await stack.run_cmd(*cmd, "-v", "ON_ERROR_STOP=1", "-c", sql)
    return json.loads(out) if out.strip().startswith("[") else out


async def _snapshot_backends(args: argparse.Namespace, init_ext: bool = False) -> dict[str, Any]:
    init_error = None
    if init_ext:
        try:
            ext = "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;"
            await _psql(args.postgres_container, args.pg_user, args.pg_db, ext)
        except RuntimeError as exc:  # keep the reason; the statements query below reports it
            init_error = str(exc)
    r_raw, pg_tbl = await asyncio.gather(
        stack.run_cmd("docker", "exec", args.redis_container, "redis-cli", "INFO", "commandstats"),
        _psql(args.postgres_container, args.pg_user, args.pg_db, _PG_TBL_SQL),
    )
    pg_stmts, pg_note = None, None
    try:
        pg_stmts = await _psql(args.postgres_container, args.pg_user, args.pg_db, _PG_STMT_SQL)
    except RuntimeError as exc:
        pg_note = f"pg_stat_statements unavailable (not preloaded?): {exc}"
        if init_error:
            pg_note += f"; CREATE EXTENSION failed: {init_error}"
    return {"redis": parse_redis_commandstats(r_raw), "pg_statements": pg_stmts,
            "pg_statements_note": pg_note, "pg_tables": pg_tbl}  # fmt: skip


async def run_steady_synced(
    args: argparse.Namespace,
    on_ready: Callable[[], Awaitable[Any]] | None = None,
    on_settled: Callable[[], Awaitable[Any]] | None = None,
) -> tuple[Any, Any, float, str, int]:
    """Run in-network `steady --sync-stdin` and invoke hooks at READY and SETTLED."""
    proc = await asyncio.create_subprocess_exec(
        *cpu_bench._build_load_cmd(args), cwd=REPO, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )  # fmt: skip
    assert proc.stdin is not None and proc.stdout is not None
    before = after = steady_file = None
    t0, t1, lines = 0.0, 0.0, []
    try:
        async for raw in proc.stdout:
            lines.append(line := raw.decode(errors="replace").rstrip("\r\n"))
            if line.startswith("BENCH_READY "):
                before, t0 = (await on_ready() if on_ready else True), time.monotonic()
                proc.stdin.write(b"\n")
                await proc.stdin.drain()
            elif line.startswith("BENCH_SETTLED "):
                t1, after = time.monotonic(), await on_settled() if on_settled else True
            elif line.startswith("wrote "):
                steady_file = Path(line.removeprefix("wrote ").strip()).name
            elif line.startswith("[steady"):
                print(line, flush=True)
        rc = await proc.wait()
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        proc.stdin.close()
    if before is None or after is None or steady_file is None:
        raise RuntimeError("missing handshake/output from scenarios.py:\n" + "\n".join(lines))
    return before, after, t1 - t0, steady_file, rc


def _format_report(p: dict[str, Any]) -> str:
    rd, qs, pt = p["redis"], p["pg_statements"], p["pg_tables"]
    q_sec = [f"\nPostgres pg_stat_statements: {p['pg_statements_note']}"] if qs is None else [
        "\nPostgres pg_stat_statements (top by total_ms):",
        f"{'calls':>7} {'calls/evt':>9} {'total_ms':>9} {'mean_ms':>8} {'ms/evt':>7}  query",
        *[f"{q['calls']:>7} {q['calls_per_event']:>9.3f} {q['total_ms']:>9.2f} "
          f"{q['mean_ms']:>8.3f} {q['ms_per_event']:>7.3f}  "
          f"{q['query'][:69] + '...' if len(q['query']) > 72 else q['query']}" for q in qs],
    ]  # fmt: skip
    return "\n".join([
        f"Redis (acc={p['accepted']}, calls/evt={rd['total_calls_per_event']}, "
        f"usec/evt={rd['total_usec_per_event']}):",
        f"{'command':<18} {'calls':>8} {'calls/evt':>9} {'usec':>9} {'usec/evt':>8} {'us/call':>7}",
        *[f"{r['command']:<18} {r['calls']:>8} {r['calls_per_event']:>9.3f} {r['usec']:>9} "
          f"{r['usec_per_event']:>8.2f} {r['usec_per_call']:>7.2f}" for r in rd["commands"]],
        *q_sec, "\nPostgres pg_stat_user_tables deltas:",
        f"{'table':<18} {'seq':>6} {'idx':>8} {'ins':>7} {'upd':>7} {'del':>5} {'live':>7}",
        *[f"{t['table']:<18} {t['seq_scan']:>6} {t['idx_scan']:>8} {t['n_tup_ins']:>7} "
          f"{t['n_tup_upd']:>7} {t['n_tup_del']:>5} {t['n_live_tup']:>7}" for t in pt],
    ])  # fmt: skip


def build_parser() -> argparse.ArgumentParser:
    """CLI parser."""
    p = argparse.ArgumentParser(description=__doc__)
    u, db = os.environ.get("POSTGRES_USER", "alerting"), os.environ.get("POSTGRES_DB", "alerting")
    for f, t, d in (
        ("--rate", float, 250.0), ("--duration", float, 30.0), ("--label", str, ""),
        ("--concurrency", cpu_bench._positive_int, 16), ("--top", cpu_bench._positive_int, 15),
        ("--image", str, "alerting-python:dev"), ("--network", str, "alerting_default"),
        ("--redis-container", str, "alerting-redis-1"), ("--pg-user", str, u), ("--pg-db", str, db),
        ("--postgres-container", str, "alerting-postgres-1"),
    ):  # fmt: skip
        p.add_argument(f, type=t, default=d)
    return p


async def main_async(args: argparse.Namespace) -> int:
    """Run one synchronized steady pass, snapshot Redis & Postgres stats, and write JSON."""
    started = datetime.now(UTC)
    before, after, wall_s, steady_file, rc = await run_steady_synced(
        args, lambda: _snapshot_backends(args, True), lambda: _snapshot_backends(args)
    )
    step = json.loads((RESULTS / steady_file).read_text())["steps"][0]
    acc, lat = int(step["accepted"]), step["latency_ms"].get("all", {})
    b_s, a_s = before["pg_statements"], after["pg_statements"]
    pg_s = None if None in (b_s, a_s) else compute_pg_statements_delta(b_s, a_s, acc, args.top)
    payload = {
        **{k: step[k] for k in ("run_id", "achieved_ingest_msg_s", "lost", "is_settled")},
        "started_at": started.isoformat(), "git": await cpu_bench.git_info(), "label": args.label,
        "steady_file": steady_file, "rate": args.rate, "duration_s": args.duration,
        "wall_s": round(wall_s, 3), "accepted": acc, "p50_ms": lat.get("p50"),
        "p99_ms": lat.get("p99"), "pg_statements": pg_s,
        "redis": compute_redis_delta(before["redis"], after["redis"], acc, args.top),
        "pg_statements_note": after["pg_statements_note"] or before["pg_statements_note"],
        "pg_tables": compute_pg_tables_delta(before["pg_tables"], after["pg_tables"]),
    }  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"backend-profile-{started:%Y%m%dT%H%M%S}.json"
    out.write_text(json.dumps(payload, indent=2))
    print(_format_report(payload) + f"\nwrote {out}")
    return 0 if (rc == 0 and step["lost"] == 0 and step["is_settled"]) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async(build_parser().parse_args())))
