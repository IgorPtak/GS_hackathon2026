"""Measurement from Postgres: processed, delivered, lost and e2e latency for one run id."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import asyncpg
import httpx
from scenario_send import EXPECTED_PER_ALERT, RULE_ID

# Alerts of a run are found by the run id stored in `last_event`; first_seen bounds the scan.
_RUN_ALERTS = """
    run_alerts AS (
        SELECT id, count, first_seen FROM alerts
        WHERE rule_id = $1 AND first_seen >= to_timestamp($3) AND last_event->>'run_id' = $2
    )
"""
_TERMINAL = ("delivered", "dead_lettered", "suppressed")


async def clock_offset_s(pool: asyncpg.Pool) -> float:
    """Postgres clock minus host clock in seconds (Docker VM drift), midpoint-corrected."""
    before = time.time()
    database = float(await pool.fetchval("SELECT extract(epoch FROM clock_timestamp())"))
    after = time.time()
    return database - (before + after) / 2


async def delivery_counts(pool: asyncpg.Pool, run_id: str, since: float) -> dict[str, Any]:
    """Alert and delivery counters for the run; `lost` is computed by the caller."""
    args = (RULE_ID, run_id, since)
    alerts = await pool.fetchrow(
        f"WITH {_RUN_ALERTS} SELECT count(*) AS alerts, coalesce(sum(count), 0) AS folded, "
        "extract(epoch FROM min(first_seen)) AS first_at, "
        "extract(epoch FROM max(first_seen)) AS last_at FROM run_alerts",
        *args,
    )
    rows = await pool.fetch(
        f"WITH {_RUN_ALERTS} SELECT d.channel_type, d.is_fallback, d.status, count(*) AS n "
        "FROM deliveries d JOIN run_alerts ra ON ra.id = d.alert_id GROUP BY 1, 2, 3",
        *args,
    )
    covered = await pool.fetchval(
        f"WITH {_RUN_ALERTS} SELECT count(*) FROM deliveries p JOIN run_alerts ra "
        "ON ra.id = p.alert_id WHERE p.status = 'dead_lettered' AND NOT p.is_fallback "
        "AND EXISTS (SELECT 1 FROM deliveries f WHERE f.alert_id = p.alert_id "
        "AND f.is_fallback AND f.status = 'delivered')",
        *args,
    )
    by_status: dict[str, int] = {}
    delivered_primary = fallback_rows = fallback_delivered = non_terminal = 0
    for row in rows:
        kind = "fallback" if row["is_fallback"] else "primary"
        key = f"{kind}/{row['channel_type']}/{row['status']}"
        by_status[key] = int(row["n"])
        if row["is_fallback"]:
            fallback_rows += row["n"]
            fallback_delivered += row["n"] if row["status"] == "delivered" else 0
        elif row["status"] == "delivered":
            delivered_primary += row["n"]
        if row["status"] not in _TERMINAL:
            non_terminal += row["n"]
    return {
        "alerts": int(alerts["alerts"]),
        "folded_events": int(alerts["folded"]),
        "first_alert_at": alerts["first_at"],
        "last_alert_at": alerts["last_at"],
        "delivered_primary": int(delivered_primary),
        "dead_lettered_covered_by_delivered_fallback": int(covered),
        "fallback_rows": int(fallback_rows),
        "fallback_delivered": int(fallback_delivered),
        "non_terminal_rows": int(non_terminal),
        "rows_by_channel_status": by_status,
    }


def is_settled(counts: dict[str, Any], expected_alerts: int, expected_folded: int) -> bool:
    """All alerts exist, every delivery row is terminal and every dead letter has its fallback."""
    dead_primary = sum(
        n
        for key, n in counts["rows_by_channel_status"].items()
        if key.startswith("primary/") and key.endswith("/dead_lettered")
    )
    return (
        counts["alerts"] >= expected_alerts
        and counts["folded_events"] >= expected_folded
        and counts["non_terminal_rows"] == 0
        and counts["delivered_primary"] + dead_primary >= EXPECTED_PER_ALERT * expected_alerts
        and counts["fallback_rows"] >= dead_primary
    )


async def wait_settled(
    pool: asyncpg.Pool,
    run_id: str,
    since: float,
    expected_alerts: int,
    expected_folded: int,
    wait_s: float,
) -> tuple[dict[str, Any], bool]:
    """Poll until settled or `wait_s` seconds pass; returns (counts, is_settled)."""
    deadline = time.monotonic() + wait_s
    while True:
        counts = await delivery_counts(pool, run_id, since)
        if is_settled(counts, expected_alerts, expected_folded):
            return counts, True
        if time.monotonic() > deadline:
            return counts, False
        await asyncio.sleep(1.0)


async def latency_ms(
    pool: asyncpg.Pool, run_id: str, since: float, offset_s: float
) -> dict[str, Any]:
    """e2e latency = delivered_at - sent_ms of the event, primary deliveries only, in ms."""
    rows = await pool.fetch(
        f"""WITH {_RUN_ALERTS},
        lat AS (
            SELECT d.channel_type,
                   (extract(epoch FROM d.delivered_at) - $4
                    - (a.last_event->>'sent_ms')::float8 / 1000) * 1000 AS ms
            FROM deliveries d JOIN run_alerts ra ON ra.id = d.alert_id
            JOIN alerts a ON a.id = ra.id
            WHERE d.status = 'delivered' AND NOT d.is_fallback)
        SELECT channel_type, count(*) AS n,
               percentile_cont(ARRAY[0.5, 0.95, 0.99]) WITHIN GROUP (ORDER BY ms) AS q,
               max(ms) AS max_ms
        FROM lat GROUP BY GROUPING SETS ((), (channel_type))""",
        RULE_ID,
        run_id,
        since,
        offset_s,
    )
    out: dict[str, Any] = {}
    for row in rows:
        p50, p95, p99 = row["q"]
        out[row["channel_type"] or "all"] = {
            "n": int(row["n"]),
            "p50": round(p50, 1),
            "p95": round(p95, 1),
            "p99": round(p99, 1),
            "max": round(row["max_ms"], 1),
        }
    return out


async def prometheus_p99_s(url: str = "http://localhost:9090") -> float | None:
    """Best-effort `alert_e2e_latency_seconds` p99 over 5 minutes; None when unreachable."""
    query = "histogram_quantile(0.99, sum(rate(alert_e2e_latency_seconds_bucket[5m])) by (le))"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            data = (await client.get(f"{url}/api/v1/query", params={"query": query})).json()
        result = data["data"]["result"]
        return float(result[0]["value"][1]) if result else None
    except (httpx.HTTPError, KeyError, ValueError, IndexError):
        return None
