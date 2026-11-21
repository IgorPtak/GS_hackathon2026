"""`runRunbookStep` (A-44): start a manual runbook step for an alert.

One transaction: lock the alert row (a concurrent resolve waits, like A-47), insert the
action run, append the audit entry, then either enqueue an `execute_action_run` job or, when the
step requires approval, create the approval request. SSE events follow the commit.
"""

from datetime import UTC, datetime
from typing import Annotated

import asyncpg
from alerting_contracts.alerts import Alert, AuditVerb, RunbookJob
from alerting_contracts.api import StepRunRequest
from alerting_contracts.runbooks import (
    ActionRun,
    ActionRunStatus,
    ApprovalRequest,
    RenderedRunbookStep,
    StepKind,
)
from alerting_contracts.sse import (
    ActionRunUpdatedEvent,
    ApprovalRequestedEvent,
    AuditAppendedEvent,
)
from alerting_core.config import ConfigRegistry
from alerting_core.logging import get_logger
from alerting_core.outbox import enqueue_runbook_job
from alerting_core.publishing import publish_team_event
from alerting_core.runbooks.rendering import render_runbook
from alerting_core.storage.alerts_read import get_alert
from alerting_core.storage.audit import append_audit
from alerting_core.storage.transitions import AlertNotFoundError
from fastapi import APIRouter, Path, Request
from pydantic import BaseModel

from services.runbook_runner.approvals import OutboxApprovalNotifier
from services.runbook_runner.store import PgStore, latest

from .. import approvals_store
from ..dependencies import PoolDep, RedisDep, RegistryDep
from ..errors import ApiError
from .runbooks import CatalogDep, RunbookCatalog

log = get_logger(__name__)

router = APIRouter(tags=["runbooks"])


def _alert_not_found(alert_id: str) -> ApiError:
    return ApiError(404, "not_found", f"alert {alert_id} not found")


async def _load_alert(connection: asyncpg.Connection, alert_id: str) -> Alert:
    try:
        return await get_alert(connection, alert_id)
    except AlertNotFoundError as error:
        raise _alert_not_found(alert_id) from error


def _find_step(alert: Alert, step_index: int, catalog: RunbookCatalog) -> RenderedRunbookStep:
    """The rendered step; 404 when alert has no runbook or step, 422 when it has no action."""
    runbook = catalog.get(alert.runbook_id) if alert.runbook_id else None
    if runbook is None:
        raise ApiError(404, "not_found", f"alert {alert.id} has no loaded runbook")
    rendered = render_runbook(runbook, alert, catalog.actions())
    step = next((s for s in rendered.steps if s.index == step_index), None)
    if step is None:
        raise ApiError(404, "not_found", f"step {step_index} not found in {runbook.id}")
    if step.kind is StepKind.text or step.action is None:
        raise ApiError(422, "validation_failed", f"step {step_index} has no action to run")
    return step


async def _request_approval(
    connection: asyncpg.Connection,
    registry: ConfigRegistry,
    public_base_url: str,
    alert: Alert,
    run: ActionRun,
    step: RenderedRunbookStep,
) -> ApprovalRequest:
    """Create the approval request and its deliveries through the runner's own helpers."""
    approval = await PgStore(connection).create_approval(run, alert.team, step.text)
    notifier = OutboxApprovalNotifier(
        connection,
        rules=registry.rules(),
        teams=registry.teams(),
        recipients=registry.recipients(),
        channels=registry.channels(),
        public_base_url=public_base_url,
        clock=lambda: datetime.now(UTC),
    )
    await notifier.notify(alert, approval)
    return approval


@router.post("/api/v1/alerts/{alert_id}/runbook/steps/{step_index}/run", status_code=202)
async def run_runbook_step_route(
    alert_id: Annotated[str, Path(description="Alert id (uuid)")],
    step_index: int,
    body: StepRunRequest,
    request: Request,
    pool: PoolDep,
    redis: RedisDep,
    catalog: CatalogDep,
    registry: RegistryDep,
) -> ActionRun:
    """Create the action run for a manual step and queue it (or ask for approval first)."""
    if not approvals_store.is_uuid(alert_id):
        raise _alert_not_found(alert_id)
    events: list[BaseModel] = []
    async with pool.acquire() as connection, connection.transaction():
        status = await approvals_store.lock_alert_status(connection, alert_id)
        if status is None:
            raise _alert_not_found(alert_id)
        if status == "resolved":
            raise ApiError(409, "alert_resolved", "the alert is already resolved")
        alert = await _load_alert(connection, alert_id)
        step = _find_step(alert, step_index, catalog)
        assert step.action is not None and alert.runbook_id is not None
        if step.requires_approval and registry is None:
            raise ApiError(503, "unavailable", "configuration is not loaded; cannot ask approval")
        store = PgStore(connection)
        previous = latest(await store.runs_for_step(alert_id, alert.runbook_id, step_index))
        if previous is not None and previous.status is not ActionRunStatus.failed:
            raise ApiError(409, "step_already_run", f"step {step_index} already has a run")
        # `approved` for a plain manual step: the runner only executes approved runs.
        run = await store.create_run(
            alert_id,
            alert.runbook_id,
            step_index,
            step.action,
            step.params,
            ActionRunStatus.pending_approval
            if step.requires_approval
            else ActionRunStatus.approved,
            previous.attempt + 1 if previous is not None else 1,
            requested_by=body.actor,
        )
        events.append(ActionRunUpdatedEvent(at=datetime.now(UTC), action_run=run))
        detail = {
            "event": "runbook_step_run_requested",
            "runbook_id": run.runbook_id,
            "step_index": step_index,
            "action_id": step.action,
            "action_run_id": run.id,
        }
        if step.requires_approval:
            assert registry is not None
            base_url = request.app.state.settings.public_base_url
            approval = await _request_approval(connection, registry, base_url, alert, run, step)
            detail["approval_request_id"] = approval.id
            events.append(ApprovalRequestedEvent(at=datetime.now(UTC), approval_request=approval))
        else:
            await enqueue_runbook_job(
                connection,
                RunbookJob(
                    job_type="execute_action_run",
                    alert_id=alert_id,
                    runbook_id=run.runbook_id,
                    action_run_id=run.id,
                ),
            )
        # The audit enum has no `runbook_step_run_requested`; these are the closest verbs.
        verb = (
            AuditVerb.approval_requested if step.requires_approval else AuditVerb.action_run_started
        )
        entry = await append_audit(
            connection, alert_id, body.actor, verb, outcome="pending", detail=detail
        )
        events.append(AuditAppendedEvent(at=datetime.now(UTC), entry=entry))
    for event in events:
        await publish_team_event(redis, alert.team, event)
    log.info(
        "runbook_step_run_requested",
        extra={"alert_id": alert_id, "runbook_id": run.runbook_id, "step_index": step_index},
    )
    return run
