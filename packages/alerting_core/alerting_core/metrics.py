"""Prometheus helpers shared by every service; service-specific metrics live next to their code.

Workers serve `render_metrics()` on GET /metrics of their metrics port; HTTP services on their main
port. Metric names follow `<area>_<what>_<unit>` (e.g. `stream_messages_total`).
"""

from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, Histogram, generate_latest

# Seconds; dense below 100 ms because the hot path targets p50 < 50 ms, sparse up to retries.
LATENCY_BUCKETS: tuple[float, ...] = (
    0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0,
)  # fmt: skip

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
    """Body and content type for a GET /metrics response."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
