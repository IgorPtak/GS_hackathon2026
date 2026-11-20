"""Runbooks, their normalized steps, action runs and approval requests."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from .common import Actor, ConfigId, ContractModel, Template
from .config import ApprovalPolicy


class RunbookFormat(StrEnum):
    yaml = "yaml"
    markdown = "markdown"
    text = "text"


class StepKind(StrEnum):
    text = "text"
    check = "check"
    action = "action"


class RunIf(StrEnum):
    always = "always"
    previous_failed = "previous_failed"
    previous_succeeded = "previous_succeeded"


class RunbookStep(ContractModel):
    """One normalized step. `text` and `params` are templates filled from the alert."""

    index: int = Field(ge=0)
    kind: StepKind
    text: Template
    action: ConfigId | None = Field(default=None, description="Action id; required for check/action steps that execute.")
    params: dict[str, Template] = Field(default_factory=dict)
    approval: ApprovalPolicy | None = Field(
        default=None, description="None = inherit from the action config."
    )
    is_automatic: bool = Field(default=False, description="Runs without a click when the alert opens.")
    run_if: RunIf = RunIf.always
    max_attempts: int = Field(default=1, ge=1)


class RunbookYamlDocument(ContractModel):
    """Content of a `yaml`-format runbook file (config/runbooks/<id>.yaml)."""

    id: ConfigId
    title: str
    team: ConfigId | None = None
    steps: list[RunbookStep] = Field(min_length=1)


class Runbook(ContractModel):
    """A runbook as stored: original source plus normalized steps."""

    id: ConfigId
    title: str
    team: ConfigId | None = None
    format: RunbookFormat
    source: str = Field(description="Original text, always shown next to the steps.")
    steps: list[RunbookStep]
    normalized_by: Literal["parser", "llm", "fallback"] = Field(
        description="fallback = LLM unavailable, whole text kept as one text step."
    )
    version: int = 1
    updated_at: datetime | None = None


class RenderedRunbookStep(ContractModel):
    index: int
    kind: StepKind
    text: str
    action: ConfigId | None = None
    params: dict[str, str] = Field(default_factory=dict)
    requires_approval: bool = False
    is_automatic: bool = False
    missing_fields: list[str] = Field(default_factory=list, description="Placeholders that had no value.")


class RenderedRunbook(ContractModel):
    runbook_id: ConfigId
    alert_id: str
    title: str
    format: RunbookFormat
    source: str
    steps: list[RenderedRunbookStep]


class ActionRunStatus(StrEnum):
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"


class ActionRun(ContractModel):
    """One execution of a runbook step's action for an alert (table action_runs)."""

    id: str
    alert_id: str
    runbook_id: ConfigId
    step_index: int
    action_id: ConfigId
    params: dict[str, str]
    status: ActionRunStatus
    attempt: int = 1
    result: dict[str, Any] | None = None
    error: str | None = None
    requested_by: Actor
    created_at: datetime
    updated_at: datetime


class ApprovalDecision(StrEnum):
    approve = "approve"
    reject = "reject"


class ApprovalVia(StrEnum):
    ui = "ui"
    sms = "sms"
    phone = "phone"


class ApprovalRequest(ContractModel):
    """A human decision gating an action run (table approval_requests)."""

    id: str
    action_run_id: str
    alert_id: str
    team: ConfigId
    summary: str = Field(description="Rendered step text shown to the approver.")
    approval_code: str = Field(pattern=r"^[0-9]{4}$", description="Reply 'APPROVE <code>' or 'REJECT <code>'.")
    requested_at: datetime
    decision: ApprovalDecision | None = None
    decided_by: Actor | None = None
    decided_via: ApprovalVia | None = None
    decided_at: datetime | None = None
    comment: str | None = None
