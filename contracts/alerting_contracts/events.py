"""Raw events as they travel through the `events` stream, and the normalized view of them."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from .common import ConfigId, ContractModel, Severity


class SourceType(StrEnum):
    webhook = "webhook"
    alertmanager = "alertmanager"
    log_tail = "log_tail"


class EventEnvelope(ContractModel):
    """One raw event plus ingest metadata.

    Stored in stream `events` as a single field `envelope` holding this model as JSON (orjson).
    `payload` is the raw event exactly as received (a parsed log line for `log_tail`).
    """

    event_id: str = Field(description="ULID assigned by ingest; sortable by time.")
    idempotency_key: str | None = Field(
        default=None,
        description=(
            "Idempotency-Key header, else the value at the source's idempotency_key_path, else None. "
            "Never a payload hash: identical events must reach dedup to be counted."
        ),
    )
    source_id: ConfigId
    source_type: SourceType
    received_at: datetime
    sent_at: datetime | None = Field(
        default=None,
        description="Producer send time (X-Sent-At header); used for alert_e2e_latency_seconds.",
    )
    payload: dict[str, Any]


class NormalizedFields(ContractModel):
    """Shared fields extracted by a schema profile. Rules address them as `normalized.<name>`."""

    schema_profile_id: ConfigId
    type: str | None = None
    source: str | None = None
    severity: Severity = Severity.warning
    occurred_at: datetime | None = None
    entity: str | None = None
    fingerprint: str = Field(description="sha256 hex of the profile's fingerprint field values.")
    is_resolution: bool = Field(
        default=False, description="True when the profile's resolution condition matched."
    )
