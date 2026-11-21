"""YAML configuration documents under config/ (and their copies in table config_documents).

Every document has an `id`; the file name is `<id>.yaml` (runbooks: `<id>.yaml|.md|.txt`).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from .common import (
    ConfigId,
    ContractModel,
    Duration,
    FieldPath,
    Severity,
    Template,
    TimeOfDayRange,
)
from .events import SourceType

# ---------------------------------------------------------------- conditions


class ConditionOperator(StrEnum):
    eq = "eq"
    ne = "ne"
    gt = "gt"
    gte = "gte"
    lt = "lt"
    lte = "lte"
    in_ = "in"
    glob = "glob"
    regex = "regex"
    exists = "exists"
    # Ranks both sides by SEVERITY_ORDER (aliases such as WARN, ERR, FATAL accepted), so "WARN or above" works.
    severity_gte = "severity_gte"
    # value is a TimeOfDayRange "HH:MM-HH:MM" (UTC, may wrap midnight) or {range: "HH:MM-HH:MM", timezone: <IANA>}.
    time_between = "time_between"


class ConditionLeaf(ContractModel):
    """Compare one field. A missing field never matches, except `exists` with value false."""

    field: FieldPath
    op: ConditionOperator
    value: Any = None


class ConditionAll(ContractModel):
    all: list[Condition] = Field(min_length=1)


class ConditionAny(ContractModel):
    any: list[Condition] = Field(min_length=1)


class ConditionNot(ContractModel):
    not_: Condition = Field(alias="not")


Condition = ConditionAll | ConditionAny | ConditionNot | ConditionLeaf

ConditionAll.model_rebuild()
ConditionAny.model_rebuild()
ConditionNot.model_rebuild()

# ---------------------------------------------------------------- sources


class SourceConfig(ContractModel):
    """config/sources/<id>.yaml. Ingest URL for HTTP sources: POST /api/v1/ingest/<id>."""

    id: ConfigId
    type: SourceType
    description: str = ""
    team: ConfigId | None = Field(default=None, description="Default owning team, informational.")
    enabled: bool = True
    settings: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Plugin-specific. log_tail: path, line_format (json|regex), line_pattern (regex with "
            "named groups), start_at (end|beginning). webhook: idempotency_key_path (optional)."
        ),
    )


# ---------------------------------------------------------------- schema profiles


class FieldMappingSpec(ContractModel):
    """Extract one normalized field. Exactly one of `path` or `const` must be set."""

    path: FieldPath | None = None
    const: str | None = None
    format: Literal["iso8601", "epoch_ms", "epoch_s"] | None = Field(
        default=None, description="Only for occurred_at."
    )
    value_map: dict[str, str] = Field(
        default_factory=dict, description="Raw value -> normalized value, e.g. {CRIT: critical}."
    )
    default: str | None = None


# A bare string is shorthand for {path: <string>}.
FieldMapping = FieldPath | FieldMappingSpec


class NormalizedFieldMappings(ContractModel):
    type: FieldMapping | None = None
    source: FieldMapping | None = None
    severity: FieldMapping | None = None
    occurred_at: FieldMapping | None = None
    entity: FieldMapping | None = None


class SchemaProfile(ContractModel):
    """config/schemas/<id>.yaml. Recognises an event shape and maps shared fields; never filters."""

    id: ConfigId
    description: str = ""
    priority: int = Field(default=0, description="Higher wins when several profiles match.")
    match: Condition
    fields: NormalizedFieldMappings
    fingerprint: list[FieldPath] = Field(min_length=1)
    resolution: Condition | None = Field(
        default=None, description="When it matches, the event resolves the open alert with the same fingerprint."
    )


# ---------------------------------------------------------------- rules


class Route(ContractModel):
    teams: list[ConfigId] = Field(
        default_factory=list, description="On-call recipients of these teams. Empty = the rule's team."
    )
    recipients: list[ConfigId] = Field(default_factory=list)
    channels: list[ConfigId] = Field(
        default_factory=lambda: ["ui", "email"],
        description="Used for a recipient with no matching channel preference.",
    )


class Presentation(ContractModel):
    title: Template
    body: Template = ""
    fields: list[FieldPath] = Field(default_factory=list)
    color: Literal["gray", "blue", "green", "yellow", "orange", "red", "purple"] = "orange"


class DedupPolicy(ContractModel):
    window: Duration = "60s"
    fingerprint: list[FieldPath] | None = Field(
        default=None, description="Overrides the schema profile fingerprint for this rule."
    )


class GroupPolicy(ContractModel):
    by: list[FieldPath] = Field(min_length=1)
    window: Duration


class ThrottlePolicy(ContractModel):
    max_deliveries: int = Field(ge=1, description="Per recipient, per rule, per period.")
    per: Duration


class AutoResolvePolicy(ContractModel):
    on_resolution_event: bool = True
    after_silence: Duration | None = None


class Rule(ContractModel):
    """config/rules/<id>.yaml."""

    id: ConfigId
    team: ConfigId
    description: str = ""
    enabled: bool = True
    when: Condition
    severity: Severity | None = Field(default=None, description="Overrides normalized severity.")
    route: Route = Field(default_factory=Route)
    present: Presentation
    dedup: DedupPolicy = Field(default_factory=DedupPolicy)
    group: GroupPolicy | None = None
    throttle: ThrottlePolicy | None = None
    auto_resolve: AutoResolvePolicy = Field(default_factory=AutoResolvePolicy)
    runbook: ConfigId | None = None


# ---------------------------------------------------------------- recipients and teams


class Contacts(ContractModel):
    email: str | None = None
    sms: str | None = None
    phone: str | None = None


class PreferenceMatch(ContractModel):
    severities: list[Severity] = Field(default_factory=list, description="Empty = any.")
    sources: list[str] = Field(default_factory=list, description="normalized.source values; empty = any.")


class ChannelPreference(ContractModel):
    """First matching preference wins. Outside working_hours, `otherwise` channels are used."""

    when: PreferenceMatch = Field(default_factory=PreferenceMatch)
    channels: list[ConfigId] = Field(min_length=1)
    working_hours: TimeOfDayRange | None = None
    timezone: str = "Europe/Warsaw"
    otherwise: list[ConfigId] = Field(default_factory=list)


class Recipient(ContractModel):
    """config/recipients/<id>.yaml."""

    id: ConfigId
    display_name: str
    teams: list[ConfigId] = Field(default_factory=list)
    contacts: Contacts = Field(default_factory=Contacts)
    channel_preferences: list[ChannelPreference] = Field(default_factory=list)


class Team(ContractModel):
    """config/teams/<id>.yaml."""

    id: ConfigId
    display_name: str
    on_call: list[ConfigId] = Field(default_factory=list, description="Recipient ids.")


# ---------------------------------------------------------------- channels


class ChannelType(StrEnum):
    ui = "ui"
    email = "email"
    sms = "sms"
    phone = "phone"
    webhook = "webhook"


class RetryPolicy(ContractModel):
    max_attempts: int = Field(default=5, ge=1)
    initial_backoff: Duration = "1s"
    max_backoff: Duration = "30s"


class ChannelConfig(ContractModel):
    """config/channels/<id>.yaml."""

    id: ConfigId
    type: ChannelType
    description: str = ""
    enabled: bool = True
    runbook_presentation: Literal["full", "link", "none"] = Field(
        default="full", description="Email/UI show full steps; SMS/phone send a link."
    )
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    fallback_channel_id: ConfigId | None = None
    settings: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Plugin-specific. email: smtp_host, smtp_port, from_address. sms/phone: gateway_url. "
            "webhook: url, method, headers, body_template (Template rendered to JSON text)."
        ),
    )


# ---------------------------------------------------------------- actions


class ApprovalPolicy(StrEnum):
    none = "none"
    required = "required"


class ActionParamSpec(ContractModel):
    description: str = ""
    is_required: bool = True


class ActionConfig(ContractModel):
    """config/actions/<id>.yaml. `type` names the plugin; `webhook` actions need no code."""

    id: ConfigId
    type: str = Field(examples=["http_get", "webhook", "retry_workflow", "restart_service", "open_ticket", "escalate"])
    description: str = ""
    approval: ApprovalPolicy = ApprovalPolicy.none
    timeout: Duration = "10s"
    params: dict[str, ActionParamSpec] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(
        default_factory=dict, description="webhook: url, method, headers, body_template."
    )
