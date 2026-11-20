"""Routes tagged `approvals` in contracts/openapi.yaml (B-12).

`decide_approval` is the single decision path: the HTTP route and the phone-simulator reply
both call it. It decides in one transaction, then publishes after commit.
"""

from datetime import UTC, datetime
from typing import Annotated

import asyncpg
from alerting_contracts.alerts import AuditVerb, RunbookJob
from alerting_contracts.api import ApprovalDecisionRequest
from alerting_contracts.common import Actor
from alerting_contracts.runbooks import (
    ActionRunStatus,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalVia,
)
from alerting_contracts.sse import (
    ActionRunUpdatedEvent,
    ApprovalDecidedEvent,
    AuditAppendedEvent,
)
from alerting_core.logging import get_logger
from alerting_core.outbox import enqueue_runbook_job
from alerting_core.publishing import publish_team_event
from alerting_core.storage.audit import append_audit
from fastapi import APIRouter, Path, Query
from redis.asyncio import Redis

from .. import approvals_store as store
from ..dependencies import PoolDep, RedisDep
from ..errors import ApiError

log = get_logger(__name__)

router = APIRouter(tags=["approvals"])


class ApprovalNotFoundError(LookupError):
    """No approval request with that id (API: 404)."""


class AlreadyDecidedError(ValueError):
    """The request already has a decision (API: 409 already_decided)."""


async def decide_approval(
    pool: asyncpg.Pool,
    redis: Redis,
    approval_id: str,
    decision: ApprovalDecision,
    actor: Actor,
    via: ApprovalVia,
    comment: str | None = None,
) -> ApprovalRequest:
    """Decide a request atomically, then publish; raises ApprovalNotFoundError/AlreadyDecidedError.

    One transaction: lock the row, stamp the decision, set the action run to approved/rejected,
    enqueue exactly one `execute_action_run` job on approve, and append the audit entry.
    """
    if not store.is_uuid(approval_id):
        raise ApprovalNotFoundError(approval_id)
    async with pool.acquire() as connection, connection.transaction():
        current = await store.lock_approval(connection, approval_id)
        if current is None:
            raise ApprovalNotFoundError(approval_id)
        if current.decision is not None:
            raise AlreadyDecidedError(approval_id)
        updated = await store.record_decision(
            connection, approval_id, decision, actor, via, comment
        )
        approved = decision is ApprovalDecision.approve
        run = await store.set_run_status(
            connection,
            current.action_run_id,
            ActionRunStatus.approved if approved else ActionRunStatus.rejected,
        )
        if approved:
            await enqueue_runbook_job(
                connection,
                RunbookJob(
                    job_type="execute_action_run",
                    alert_id=current.alert_id,
                    runbook_id=current.runbook_id,
                    action_run_id=current.action_run_id,
                ),
            )
        audit = await append_audit(
            connection,
            current.alert_id,
            actor,
            AuditVerb.approval_decided,
            detail={
                "approval_request_id": approval_id,
                "decision": decision.value,
                "decided_via": via.value,
                "code": current.approval_code,
            },
        )
    now = datetime.now(UTC)
    await publish_team_event(
        redis, updated.team, ApprovalDecidedEvent(at=now, approval_request=updated)
    )
    if run is not None:
        await publish_team_event(redis, updated.team, ActionRunUpdatedEvent(at=now, action_run=run))
    await publish_team_event(redis, updated.team, AuditAppendedEvent(at=now, entry=audit))
    log.info(
        "approval_decided",
        extra={"approval_request_id": approval_id, "decision": decision.value, "via": via.value},
    )
    return updated


@router.get("/api/v1/approvals")
async def list_approvals_route(
    pool: PoolDep,
    team: Annotated[str | None, Query()] = None,
    is_pending: Annotated[bool, Query()] = True,
) -> list[ApprovalRequest]:
    """Pending (is_pending=true) or decided requests, newest first."""
    return await store.list_approvals(pool, team, is_pending)


@router.post("/api/v1/approvals/{approval_request_id}/decision")
async def decide_approval_route(
    approval_request_id: Annotated[str, Path()],
    body: ApprovalDecisionRequest,
    pool: PoolDep,
    redis: RedisDep,
) -> ApprovalRequest:
    """Approve (queues the action run) or reject a pending request."""
    try:
        return await decide_approval(
            pool,
            redis,
            approval_request_id,
            body.decision,
            body.actor,
            body.via,
            body.comment,
        )
    except ApprovalNotFoundError as error:
        raise ApiError(
            404, "not_found", f"approval request {approval_request_id} not found"
        ) from error
    except AlreadyDecidedError as error:
        raise ApiError(
            409, "already_decided", f"approval request {approval_request_id} is already decided"
        ) from error
