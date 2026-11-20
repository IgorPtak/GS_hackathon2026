"""GET /api/v1/metrics/summary: a few PromQL queries plus the open alert count."""

import asyncio
import math
from typing import Any

import asyncpg
import httpx
from alerting_contracts.api import MetricsSummary
from alerting_core.logging import get_logger
from alerting_core.settings import Settings, get_settings
from fastapi import APIRouter, Request

log = get_logger(__name__)
router = APIRouter(tags=["ops"])

PROMETHEUS_TIMEOUT_SECONDS = 2.0

_LATENCY = "sum by (le) (rate(alert_e2e_latency_seconds_bucket[1m]))"

# Same expressions as deploy/grafana/dashboards/alerting.json; keys are MetricsSummary fields.
QUERIES: dict[str, str] = {
    "ingest_rate_per_second": "sum(rate(events_ingested_total[1m]))",
    "processed_rate_per_second": "sum(rate(events_processed_total[1m]))",
    "events_stream_lag": 'sum(max by (stream, group) (stream_lag{stream="events"}))',
    "deliveries_stream_lag": 'sum(max by (stream, group) (stream_lag{stream="deliveries"}))',
    "e2e_latency_p50_seconds": f"histogram_quantile(0.5, {_LATENCY})",
    "e2e_latency_p99_seconds": f"histogram_quantile(0.99, {_LATENCY})",
    "retries_total": "sum(delivery_retries_total)",
    "dead_lettered_total": "sum(dead_lettered_total)",
}
INTEGER_FIELDS = frozenset(
    {"events_stream_lag", "deliveries_stream_lag", "retries_total", "dead_lettered_total"}
)


def _parse_value(payload: Any) -> float | None:
    """First sample of an instant-query response; None when empty, NaN or infinite."""
    try:
        raw = payload["data"]["result"][0]["value"][1]
        value = float(raw)
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


async def _query_one(client: httpx.AsyncClient, base_url: str, field: str) -> float | int | None:
    """Run one PromQL query; any failure yields None so Prometheus never breaks the endpoint."""
    try:
        response = await client.get(f"{base_url}/api/v1/query", params={"query": QUERIES[field]})
        response.raise_for_status()
        value = _parse_value(response.json())
    except (httpx.HTTPError, ValueError) as error:
        log.warning("metrics_query_failed", extra={"field": field, "error": str(error)})
        return None
    if value is not None and field in INTEGER_FIELDS:
        return round(value)
    return value


async def _count_open_alerts(request: Request) -> int:
    """Open alerts from Postgres; 0 with a warning when the database is not reachable."""
    try:
        pool = request.app.state.pool
        if pool is None:
            connect = getattr(request.app.state, "connect_database", None)
            pool = await connect() if connect is not None else None
        if pool is None:
            log.warning("metrics_open_alerts_unavailable", extra={"reason": "no_pool"})
            return 0
        async with pool.acquire() as connection:
            count = await connection.fetchval("SELECT count(*) FROM alerts WHERE status = 'open'")
        return int(count or 0)
    except (asyncpg.PostgresError, OSError, AttributeError) as error:
        log.warning("metrics_open_alerts_unavailable", extra={"reason": str(error)})
        return 0


def _resolve_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


@router.get("/api/v1/metrics/summary")
async def get_metrics_summary(request: Request) -> MetricsSummary:
    """Live numbers for the Metrics tab; fields are null while Prometheus has no data."""
    base_url = _resolve_settings(request).prometheus_url.rstrip("/")
    async with httpx.AsyncClient(timeout=PROMETHEUS_TIMEOUT_SECONDS) as client:
        fields = list(QUERIES)
        values, open_count = await asyncio.gather(
            asyncio.gather(*(_query_one(client, base_url, field) for field in fields)),
            _count_open_alerts(request),
        )
    return MetricsSummary(**dict(zip(fields, values, strict=True)), open_alert_count=open_count)
