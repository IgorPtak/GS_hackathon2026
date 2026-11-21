"""Delivery metrics; `alert_e2e_latency_seconds` is the glossary's end-to-end latency."""

from alerting_core.metrics import E2E_LATENCY_BUCKETS, LATENCY_BUCKETS
from prometheus_client import Counter, Histogram

DELIVERY_ATTEMPTS = Counter(
    "delivery_attempts_total", "Delivery attempts by outcome.", ["channel_type", "outcome"]
)
SEND_SECONDS = Histogram(
    "delivery_send_seconds",
    "Duration of one channel send.",
    ["channel_type"],
    buckets=LATENCY_BUCKETS,
)
E2E_LATENCY_SECONDS = Histogram(
    "alert_e2e_latency_seconds",
    "Producer send time (or ingest time) to delivered.",
    ["channel_type"],
    buckets=E2E_LATENCY_BUCKETS,
)
DELIVERY_POST_RELAY_SECONDS = Histogram(
    "delivery_post_relay_seconds",
    "From relay XADD (stream entry timestamp) to delivered; first attempts, non-fallback only.",
    ["channel_type"],
    buckets=E2E_LATENCY_BUCKETS,
)
