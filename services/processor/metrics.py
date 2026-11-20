"""Processor metrics; stream-level counters come from alerting_core.metrics."""

from alerting_core.metrics import LATENCY_BUCKETS
from prometheus_client import Counter, Histogram

EVENTS_PROCESSED = Counter(
    "processor_events_total", "Events handled by the processor.", ["outcome"]
)
ALERTS_CREATED = Counter("processor_alerts_created_total", "Alerts created by the processor.")
EVENT_TO_ALERT_SECONDS = Histogram(
    "processor_event_to_alert_seconds",
    "From ingest (received_at) to the alert's commit.",
    buckets=LATENCY_BUCKETS,
)
