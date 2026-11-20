"""Prometheus helpers shared by every service; service-specific metrics live next to their code.

Workers serve `render_metrics()` on GET /metrics of their metrics port; HTTP services on their main
port. Metric names follow `<area>_<what>_<unit>` (e.g. `stream_messages_total`).
"""

import asyncio
import os
from collections.abc import Mapping
from contextlib import suppress
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)
from redis.asyncio import Redis
from redis.exceptions import RedisError

from .logging import get_logger

log = get_logger(__name__)

# Seconds; dense below 100 ms because the hot path targets p50 < 50 ms, sparse up to retries.
LATENCY_BUCKETS: tuple[float, ...] = (
    0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0,
)  # fmt: skip

# 5 ms to 30 s: the dashboard's p50/p95/p99 interpolate inside these, so they bracket the SLO.
E2E_LATENCY_BUCKETS: tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0,
)  # fmt: skip

# Pipeline counters named after the dashboard; each is incremented by exactly one service.
EVENTS_INGESTED = Counter("events_ingested_total", "Events accepted by ingest.")
EVENTS_PROCESSED = Counter("events_processed_total", "Events the processor finished.")
ALERTS_CREATED = Counter("alerts_created_total", "Alerts created by the processor.")
DELIVERIES = Counter(
    "deliveries_total",
    "Delivery outcomes per attempt; status is delivered, failed or dead_lettered.",
    ["channel", "status"],
)
DELIVERY_RETRIES = Counter("delivery_retries_total", "Delivery retries scheduled.")
DEAD_LETTERED = Counter(
    "dead_lettered_total", "Entries and deliveries moved to a dead-letter stream."
)

# (stream, group) pairs whose backlog the dashboard shows.
LAG_GROUPS: tuple[tuple[str, str], ...] = (
    ("events", "processors"),
    ("deliveries", "delivery-workers"),
    ("runbook-jobs", "runbook-runners"),
)
STREAM_LAG = Gauge(
    "stream_lag",
    "Entries not yet delivered to the group (XINFO GROUPS lag); pending when lag is unknown.",
    ["stream", "group"],
    multiprocess_mode="max",
)
LAG_INTERVAL_SECONDS = 2.0

# outcome: acked | failed | claimed | dead_lettered | dropped_trimmed
STREAM_MESSAGES = Counter(
    "stream_messages_total",
    "Stream entries handled by a consumer group, by outcome.",
    ["stream", "group", "outcome"],
)
STREAM_BATCH_SECONDS = Histogram(
    "stream_batch_seconds",
    "Time spent in the batch handler.",
    ["stream", "group"],
    buckets=LATENCY_BUCKETS,
)


def render_metrics() -> tuple[bytes, str]:
    """Body and content type for a GET /metrics response.

    When PROMETHEUS_MULTIPROC_DIR is set (services running several uvicorn workers, like ingest)
    the per-process values are aggregated; without it each worker would answer with its own
    counters and rate() would see them jump between scrapes.
    """
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry), CONTENT_TYPE_LATEST
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def parse_group_lags(groups: list[Mapping[Any, Any]]) -> dict[str, int]:
    """Map group name to lag from an XINFO GROUPS reply; nil lag falls back to pending."""
    lags: dict[str, int] = {}
    for info in groups:
        fields = {_text(key): value for key, value in info.items()}
        name = _text(fields.get("name"))
        value = fields.get("lag")
        if value is None:
            value = fields.get("pending", 0)
        lags[name] = int(value)
    return lags


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


async def update_stream_lag(redis: Redis) -> None:
    """Set `stream_lag` for every group in LAG_GROUPS; missing streams read as zero."""
    for stream, group in LAG_GROUPS:
        try:
            lags = parse_group_lags(await redis.xinfo_groups(stream))
        except RedisError:
            # The stream does not exist before its first event; Redis is down otherwise.
            lags = {}
        STREAM_LAG.labels(stream, group).set(lags.get(group, 0))


async def run_stream_lag_collector(redis: Redis, stop: asyncio.Event) -> None:
    """Refresh `stream_lag` every 2 s until stopped. Run it in exactly one service."""
    while not stop.is_set():
        try:
            await update_stream_lag(redis)
        except Exception:  # a metrics loop must never take its service down
            log.exception("stream_lag_update_failed")
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=LAG_INTERVAL_SECONDS)
