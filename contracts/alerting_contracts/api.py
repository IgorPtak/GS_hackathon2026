"""HTTP request and response bodies referenced by contracts/openapi.yaml."""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .alerts import Alert, AlertStatus, AuditEntry, Delivery
from .common import Actor, ConfigId, ContractModel, Duration, Severity
from .config import (
    ActionConfig,
    ChannelConfig,
    ChannelPreference,
    ChannelType,
    Recipient,
    Rule,
    SchemaProfile,
    SourceConfig,
    Team,
)
from .events import NormalizedFields
from .proposals import FixProposal
from .runbooks import (
    ActionRun,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalVia,
    RenderedRunbook,
    RunbookFormat,
)

# ---------------------------------------------------------------- ingest


class IngestAccepted(ContractModel):
    event_ids: list[str]
    duplicate_count: int = Field(description="Events skipped by ingest idempotency.")


# ---------------------------------------------------------------- alerts


class AlertPage(ContractModel):
    items: list[Alert]
    next_cursor: str | None = None


class AlertDetail(ContractModel):
    alert: Alert
    audit_entries: list[AuditEntry]
    deliveries: list[Delivery]
    rendered_runbook: RenderedRunbook | None = None
    action_runs: list[ActionRun] = Field(default_factory=list)
    approval_requests: list[ApprovalRequest] = Field(default_factory=list)
    fix_proposals: list[FixProposal] = Field(default_factory=list)


class AlertAcknowledgeRequest(ContractModel):
    actor: Actor


class AlertResolveRequest(ContractModel):
    actor: Actor
    comment: str | None = None


class StepRunRequest(ContractModel):
    actor: Actor


# ---------------------------------------------------------------- config documents


ConfigKind = Literal["rule", "schema_profile", "recipient", "team", "channel", "action", "source", "runbook"]


class ConfigRecord(ContractModel):
    """Metadata shared by every stored config document."""

    kind: ConfigKind
    id: ConfigId
    yaml: str = Field(description="Canonical YAML serialized by the server.")
    version: int
    updated_at: datetime
    updated_by: Actor | None = None


class RuleRecord(ConfigRecord):
    rule: Rule


class RuleWrite(ContractModel):
    rule: Rule
    actor: Actor


class SchemaProfileRecord(ConfigRecord):
    schema_profile: SchemaProfile


class SchemaProfileWrite(ContractModel):
    schema_profile: SchemaProfile
    actor: Actor


class ConfigValidationRequest(ContractModel):
    kind: ConfigKind
    yaml: str


class ConfigValidationError(ContractModel):
    path: str = Field(description="Dot path into the document, '' for the root.")
    message: str


class ConfigValidationResult(ContractModel):
    is_valid: bool
    errors: list[ConfigValidationError] = Field(default_factory=list)
    document: dict[str, Any] | None = Field(default=None, description="Parsed document when valid.")


class ConfigLists(ContractModel):
    """GET /api/v1/config: read-only config used by UI dropdowns."""

    teams: list[Team]
    recipients: list[Recipient]
    channels: list[ChannelConfig]
    actions: list[ActionConfig]
    sources: list[SourceConfig]


# ---------------------------------------------------------------- rule preview


class RulePreviewRequest(ContractModel):
    rule: Rule
    window: Duration = "1h"
    max_events: int = Field(default=50_000, ge=1, le=500_000)


class PreviewDeliveryCount(ContractModel):
    recipient_id: ConfigId | None
    channel_id: ConfigId
    count: int


class PreviewAlert(ContractModel):
    title: str
    severity: Severity
    fingerprint: str
    group_key: str | None = None
    is_group_summary: bool = False
    member_count: int = Field(default=0, ge=0, description="Distinct fingerprints in a group summary.")
    count: int
    first_seen: datetime


class RulePreview(ContractModel):
    window_start: datetime
    window_end: datetime
    events_scanned: int
    events_matched: int
    alerts_created: int = Field(description="After dedup and grouping.")
    deliveries: list[PreviewDeliveryCount]
    sample_alerts: list[PreviewAlert] = Field(max_length=20)
    duration_ms: int
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- schema profiles and unknown schemas


class SchemaProfileProposeRequest(ContractModel):
    sample_event: dict[str, Any]
    profile_id: ConfigId | None = None


class SchemaProfileTestRequest(ContractModel):
    schema_profile: SchemaProfile
    window: Duration = "1h"
    sample_event: dict[str, Any] | None = Field(default=None, description="Also test this event.")


class SchemaProfileTestSample(ContractModel):
    event_id: str | None
    normalized: NormalizedFields


class SchemaProfileTestResult(ContractModel):
    events_scanned: int
    events_matched: int
    samples: list[SchemaProfileTestSample] = Field(max_length=20)


class UnknownSchemaSample(ContractModel):
    """Table unknown_schema_samples; one row per distinct key shape."""

    shape_hash: str
    source_id: ConfigId
    key_paths: list[str]
    sample_event: dict[str, Any]
    event_count: int
    first_seen: datetime
    last_seen: datetime


# ---------------------------------------------------------------- runbooks


class RunbookWrite(ContractModel):
    id: ConfigId
    title: str
    team: ConfigId | None = None
    format: RunbookFormat
    source: str = Field(min_length=1)
    actor: Actor


class RunbookNormalizeRequest(ContractModel):
    """Body of POST /runbooks/normalize: preview before the runbook has an id or is saved."""

    format: RunbookFormat
    source: str = Field(min_length=1)


class RunbookSummary(ContractModel):
    id: ConfigId
    title: str
    team: ConfigId | None
    format: RunbookFormat
    step_count: int
    normalized_by: Literal["parser", "llm", "fallback"]
    llm_model: str | None = None
    version: int


# ---------------------------------------------------------------- approvals and phone simulator


class ApprovalDecisionRequest(ContractModel):
    decision: ApprovalDecision
    actor: Actor
    via: ApprovalVia = ApprovalVia.ui
    comment: str | None = None


class FixProposalDecisionRequest(ContractModel):
    decision: Literal["accept", "reject"]
    actor: Actor
    comment: str | None = None


class PhoneMessage(ContractModel):
    """A mock SMS or phone call as shown in the phone simulator."""

    id: str
    recipient_id: ConfigId
    channel_type: Literal[ChannelType.sms, ChannelType.phone]
    to: str
    text: str
    alert_id: str
    delivery_id: int
    approval_code: str | None = None
    at: datetime


class PhoneReplyRequest(ContractModel):
    """Reply typed in the phone simulator, e.g. 'APPROVE 4821', 'REJECT 4821', 'ACK'."""

    recipient_id: ConfigId
    text: str = Field(min_length=1)


class PhoneReplyResult(ContractModel):
    is_understood: bool
    message: str
    approval_request_id: str | None = None


# ---------------------------------------------------------------- recipients


class ChannelPreferencesWrite(ContractModel):
    channel_preferences: list[ChannelPreference]
    actor: Actor


# ---------------------------------------------------------------- metrics


class MetricsSummary(ContractModel):
    """Read from Prometheus by the api service; null when Prometheus has no data yet."""

    ingest_rate_per_second: float | None
    processed_rate_per_second: float | None
    events_stream_lag: int | None
    deliveries_stream_lag: int | None
    e2e_latency_p50_seconds: float | None
    e2e_latency_p99_seconds: float | None
    retries_total: int | None
    dead_lettered_total: int | None
    open_alert_count: int


class AlertQuery(ContractModel):
    """Query parameters of GET /api/v1/alerts (documentation only)."""

    team: ConfigId | None = None
    status: AlertStatus | None = None
    limit: int = 50
    cursor: str | None = None


class ErrorResponse(ContractModel):
    error: str = Field(examples=["not_found", "invalid_transition", "validation_failed", "llm_unavailable"])
    message: str
    details: list[ConfigValidationError] = Field(default_factory=list)
