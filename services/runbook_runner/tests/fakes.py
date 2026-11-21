"""In-memory store, notifier and plugins for the pure step-walk tests."""

from datetime import UTC, datetime
from typing import Any

from alerting_contracts.alerts import Alert, AuditEntry, AuditVerb
from alerting_contracts.common import Actor, Severity
from alerting_contracts.config import ActionConfig
from alerting_contracts.runbooks import (
    ActionRun,
    ActionRunStatus,
    ApprovalRequest,
    RenderedRunbook,
    RenderedRunbookStep,
    RunbookFormat,
    RunIf,
    StepKind,
)
from alerting_core.ids import new_uuid7

from plugins.actions import ActionPlugin, ActionResult

ALERT_ID = "0197c9a0-0000-7000-8000-000000000001"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def make_alert(alert_id: str = ALERT_ID) -> Alert:
    return Alert(
        id=alert_id,
        rule_id="rule",
        team="settlements",
        schema_profile_id="p",
        source_id="s",
        fingerprint="f",
        severity=Severity.error,
        title="Workflow failed",
        first_seen=NOW,
        last_seen=NOW,
        last_event={},
        updated_at=NOW,
    )


def step(
    index: int,
    *,
    action: str | None = "act",
    automatic: bool = True,
    approval: bool = False,
    run_if: RunIf = RunIf.always,
    max_attempts: int = 1,
    kind: StepKind = StepKind.action,
) -> RenderedRunbookStep:
    return RenderedRunbookStep(
        index=index,
        kind=kind,
        text=f"step {index}",
        action=action,
        params={"p": str(index)},
        requires_approval=approval,
        is_automatic=automatic,
        run_if=run_if,
        max_attempts=max_attempts,
    )


def rendered(*steps: RenderedRunbookStep) -> RenderedRunbook:
    return RenderedRunbook(
        runbook_id="rb",
        alert_id=ALERT_ID,
        title="rb",
        format=RunbookFormat.yaml,
        source="",
        steps=list(steps),
    )


def action_config(action_id: str = "act", type_: str = "fake") -> ActionConfig:
    return ActionConfig(id=action_id, type=type_)


class FakeStore:
    """Mirrors PgStore semantics without a database."""

    def __init__(self) -> None:
        self.runs: dict[str, ActionRun] = {}
        self.audits: list[AuditEntry] = []
        self.approvals: list[ApprovalRequest] = []

    async def has_audit(self, alert_id: str, verb: AuditVerb, runbook_id: str) -> bool:
        return any(
            e.alert_id == alert_id and e.verb is verb and e.detail.get("runbook_id") == runbook_id
            for e in self.audits
        )

    async def append_audit(
        self, alert_id: str, verb: AuditVerb, detail: dict[str, Any], outcome: str = "ok"
    ) -> AuditEntry:
        entry = AuditEntry(
            id=len(self.audits) + 1,
            alert_id=alert_id,
            at=NOW,
            actor=Actor(id="system:runbook-runner"),
            verb=verb,
            outcome=outcome,
            detail=detail,
        )
        self.audits.append(entry)
        return entry

    async def runs_for_step(
        self, alert_id: str, runbook_id: str, step_index: int
    ) -> list[ActionRun]:
        found = [
            r
            for r in self.runs.values()
            if (r.alert_id, r.runbook_id, r.step_index) == (alert_id, runbook_id, step_index)
        ]
        return sorted(found, key=lambda r: r.attempt)

    async def get_run(self, run_id: str, for_update: bool = False) -> ActionRun | None:
        return self.runs.get(run_id)

    async def create_run(
        self,
        alert_id: str,
        runbook_id: str,
        step_index: int,
        action_id: str,
        params: dict[str, str],
        status: ActionRunStatus,
        attempt: int = 1,
        requested_by: Actor | None = None,
    ) -> ActionRun:
        run = ActionRun(
            id=new_uuid7(),
            alert_id=alert_id,
            runbook_id=runbook_id,
            step_index=step_index,
            action_id=action_id,
            params=params,
            status=status,
            attempt=attempt,
            requested_by=requested_by or Actor(id="system:runbook-runner"),
            created_at=NOW,
            updated_at=NOW,
        )
        self.runs[run.id] = run
        return run

    async def update_run(
        self,
        run_id: str,
        status: ActionRunStatus,
        attempt: int,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ActionRun:
        run = self.runs[run_id].model_copy(
            update={"status": status, "attempt": attempt, "result": result, "error": error}
        )
        self.runs[run_id] = run
        return run

    async def create_approval(self, run: ActionRun, team: str, summary: str) -> ApprovalRequest:
        approval = ApprovalRequest(
            id=new_uuid7(),
            action_run_id=run.id,
            alert_id=run.alert_id,
            team=team,
            runbook_id=run.runbook_id,
            step_index=run.step_index,
            action_id=run.action_id,
            params=run.params,
            summary=summary,
            approval_code=f"{len(self.approvals) + 1:04d}",
            requested_at=NOW,
        )
        self.approvals.append(approval)
        return approval

    def statuses(self, step_index: int) -> list[tuple[int, str]]:
        runs = sorted(
            (r for r in self.runs.values() if r.step_index == step_index), key=lambda r: r.attempt
        )
        return [(r.attempt, r.status.value) for r in runs]


class FakeNotifier:
    def __init__(self) -> None:
        self.notified: list[ApprovalRequest] = []

    async def notify(self, alert: Alert, approval: ApprovalRequest) -> int:
        self.notified.append(approval)
        return 1


class ScriptedPlugin(ActionPlugin):
    """Returns scripted outcomes in order (True/False, or an exception to raise)."""

    type = "fake"

    def __init__(self, script: list[bool | Exception]) -> None:
        super().__init__()
        self.script = list(script)
        self.calls: list[dict[str, str]] = []

    async def _run(self, params: dict[str, str], config: ActionConfig) -> ActionResult:
        self.calls.append(params)
        outcome = self.script.pop(0) if self.script else True
        if isinstance(outcome, Exception):
            raise outcome
        return ActionResult(is_success=outcome, detail="ok" if outcome else "boom")
