"""Routes tagged `phone-simulator` in contracts/openapi.yaml (B-12)."""

import re
from typing import Annotated

from alerting_contracts.api import PhoneMessage, PhoneReplyRequest, PhoneReplyResult
from alerting_contracts.common import Actor
from alerting_contracts.runbooks import ApprovalDecision, ApprovalVia
from alerting_core.logging import get_logger
from alerting_core.publishing import publish_alert_change
from alerting_core.storage import (
    AlertNotFoundError,
    InvalidTransitionError,
    acknowledge_alert,
)
from fastapi import APIRouter, Query

from .. import approvals_store as store
from ..dependencies import PoolDep, RedisDep, RegistryDep
from .approvals import AlreadyDecidedError, ApprovalNotFoundError, decide_approval

log = get_logger(__name__)

router = APIRouter(tags=["phone-simulator"])

HELP = "Reply APPROVE <code>, REJECT <code> or ACK."
_DECIDE = re.compile(r"\s*(approve|reject)\s+(\d{4})\s*", re.IGNORECASE)
_ACK = re.compile(r"\s*ack\s*", re.IGNORECASE)


def parse_reply(text: str) -> tuple[str, str | None] | None:
    """('approve'|'reject', code) or ('ack', None); None for anything else."""
    decide = _DECIDE.fullmatch(text)
    if decide:
        return decide.group(1).lower(), decide.group(2)
    if _ACK.fullmatch(text):
        return "ack", None
    return None


def _no(message: str) -> PhoneReplyResult:
    return PhoneReplyResult(is_understood=False, message=message)


@router.get("/api/v1/phone-simulator/messages")
async def list_messages_route(
    pool: PoolDep, recipient_id: Annotated[str | None, Query()] = None
) -> list[PhoneMessage]:
    """Mock SMS and calls, newest first (at most 200)."""
    return await store.list_messages(pool, recipient_id)


@router.post("/api/v1/phone-simulator/replies")
async def reply_route(
    body: PhoneReplyRequest, pool: PoolDep, redis: RedisDep, registry: RegistryDep
) -> PhoneReplyResult:
    """Act on `APPROVE <code>`, `REJECT <code>` or `ACK` typed by a recipient."""
    parsed = parse_reply(body.text)
    if parsed is None:
        return _no(f"Sorry, I did not understand that. {HELP}")
    actor = Actor(id=body.recipient_id)
    command, code = parsed
    if command == "ack":
        return await _acknowledge(pool, redis, body.recipient_id, actor)
    assert code is not None
    if registry is None:
        return _no("Configuration is unavailable right now, try again shortly.")
    recipient = registry.recipients().get(body.recipient_id)
    if recipient is None:
        return _no(f"Unknown recipient {body.recipient_id}.")
    async with pool.acquire() as connection:
        request = await store.find_pending_by_code(connection, code)
        if request is None or request.team not in recipient.teams:
            # Same answer for "no such code" and "other team's code": do not leak other teams.
            return _no(f"No pending approval with code {code} for your teams.")
        channel = await store.latest_channel_for_code(connection, body.recipient_id, code)
    via = ApprovalVia.phone if channel == "phone" else ApprovalVia.sms
    decision = ApprovalDecision(command)
    try:
        await decide_approval(pool, redis, request.id, decision, actor, via)
    except (ApprovalNotFoundError, AlreadyDecidedError):
        return _no(f"Approval {code} was already decided.")
    verb = "approved" if decision is ApprovalDecision.approve else "rejected"
    return PhoneReplyResult(
        is_understood=True, message=f"Approval {code} {verb}.", approval_request_id=request.id
    )


async def _acknowledge(
    pool: PoolDep, redis: RedisDep, recipient_id: str, actor: Actor
) -> PhoneReplyResult:
    async with pool.acquire() as connection:
        alert_id = await store.latest_open_alert_id(connection, recipient_id)
        if alert_id is None:
            return _no("No open alert to acknowledge.")
        try:
            alert, audit = await acknowledge_alert(connection, alert_id, actor)
        except (AlertNotFoundError, InvalidTransitionError):
            return _no("No open alert to acknowledge.")
    await publish_alert_change(redis, alert, [audit])
    return PhoneReplyResult(is_understood=True, message=f"Alert {alert.title} acknowledged.")
