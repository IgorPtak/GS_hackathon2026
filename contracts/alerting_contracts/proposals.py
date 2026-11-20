"""Human-approved proposals: fix proposals, LLM schema profile proposals, runbook revisions."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from .common import Actor, ConfigId, ContractModel
from .config import Rule, SchemaProfile
from .runbooks import RunbookStep


class FixKind(StrEnum):
    threshold = "threshold"
    fields = "fields"
    dedup_window = "dedup_window"
    runbook_step = "runbook_step"
    other = "other"


class ProposalStatus(StrEnum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"


class FixProposalCreate(ContractModel):
    kind: FixKind
    description: str = Field(min_length=1)
    proposed_rule: Rule | None = Field(default=None, description="Full rule after the change.")
    proposed_runbook_step: RunbookStep | None = None
    proposed_by: Actor


class FixProposal(ContractModel):
    """Table fix_proposals. Created from an alert, decided by the rule's owner team."""

    id: str
    alert_id: str
    rule_id: ConfigId
    runbook_id: ConfigId | None = None
    owner_team: ConfigId
    kind: FixKind
    description: str
    proposed_rule: Rule | None = None
    proposed_runbook_step: RunbookStep | None = None
    proposed_by: Actor
    status: ProposalStatus = ProposalStatus.pending
    decided_by: Actor | None = None
    decided_at: datetime | None = None
    decision_comment: str | None = None
    created_at: datetime


class SchemaProfileProposal(ContractModel):
    """Draft profile for a sample event. Never saved until a human submits it."""

    profile: SchemaProfile
    generated_by: Literal["llm", "heuristic"]
    model: str | None = None
    notes: list[str] = Field(default_factory=list)


class RunbookRevisionProposal(ContractModel):
    """Optional (cut-1): steps skipped and actions taken outside the runbook -> new version."""

    id: str
    runbook_id: ConfigId
    based_on_alert_ids: list[str]
    summary: str
    proposed_steps: list[RunbookStep]
    status: ProposalStatus = ProposalStatus.pending
    created_at: datetime
