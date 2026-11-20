"""SQL helpers for approval requests, their action runs and the phone simulator.

Every function takes a pool or a connection; nothing here commits. Decision writes must run
inside the caller's transaction after `lock_approval`.
"""

from typing import Any
from uuid import UUID

import asyncpg
from alerting_contracts.api import PhoneMessage
from alerting_contracts.common import Actor
from alerting_contracts.runbooks import (
    ActionRun,
    ActionRunStatus,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalVia,
)
from alerting_core.storage.rows import row_to_dict

MESSAGE_LIMIT = 200
APPROVAL_LIMIT = 200


def is_uuid(value: str) -> bool:
    """True when `value` parses as a uuid (a malformed id is simply 'not found')."""
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _approval(record: asyncpg.Record) -> ApprovalRequest:
    data = row_to_dict(record)
    data["approval_code"] = str(data["approval_code"]).strip()
    return ApprovalRequest.model_validate(data)


async def list_approvals(
    pool: asyncpg.Pool, team: str | None, is_pending: bool
) -> list[ApprovalRequest]:
    """Pending (or decided) requests, optionally of one team, newest first."""
    records = await pool.fetch(
        "SELECT * FROM approval_requests "
        "WHERE (($1::boolean AND decision IS NULL) OR (NOT $1::boolean AND decision IS NOT NULL)) "
        "AND ($2::text IS NULL OR team = $2) ORDER BY requested_at DESC LIMIT $3",
        is_pending,
        team,
        APPROVAL_LIMIT,
    )
    return [_approval(record) for record in records]


async def lock_approval(connection: asyncpg.Connection, approval_id: str) -> ApprovalRequest | None:
    """Select one request `FOR UPDATE`; concurrent deciders serialize on this lock."""
    record = await connection.fetchrow(
        "SELECT * FROM approval_requests WHERE id = $1::uuid FOR UPDATE", approval_id
    )
    return _approval(record) if record else None


async def find_pending_by_code(connection: asyncpg.Connection, code: str) -> ApprovalRequest | None:
    """The one pending request with this code (partial unique index), or None."""
    record = await connection.fetchrow(
        "SELECT * FROM approval_requests WHERE approval_code = $1 AND decision IS NULL", code
    )
    return _approval(record) if record else None


async def record_decision(
    connection: asyncpg.Connection,
    approval_id: str,
    decision: ApprovalDecision,
    actor: Actor,
    via: ApprovalVia,
    comment: str | None,
) -> ApprovalRequest:
    """Stamp the decision on a request already locked by `lock_approval`."""
    record = await connection.fetchrow(
        "UPDATE approval_requests SET decision = $2, decided_by = $3, decided_via = $4, "
        "decided_at = now(), comment = $5 WHERE id = $1::uuid AND decision IS NULL RETURNING *",
        approval_id,
        decision.value,
        actor.model_dump(mode="json"),
        via.value,
        comment,
    )
    if record is None:
        raise RuntimeError("approval update returned no row")
    return _approval(record)


async def set_run_status(
    connection: asyncpg.Connection, run_id: str, status: ActionRunStatus
) -> ActionRun | None:
    """Move an action run to `approved` or `rejected`; None when the run no longer exists."""
    record = await connection.fetchrow(
        "UPDATE action_runs SET status = $2, updated_at = now() WHERE id = $1::uuid RETURNING *",
        run_id,
        status.value,
    )
    return ActionRun.model_validate(row_to_dict(record)) if record else None


async def list_messages(pool: asyncpg.Pool, recipient_id: str | None) -> list[PhoneMessage]:
    """Mock SMS and calls, newest first, at most 200."""
    records = await pool.fetch(
        'SELECT id, recipient_id, channel_type, "to", text, alert_id, delivery_id, '
        "approval_code, at FROM phone_messages "
        "WHERE ($1::text IS NULL OR recipient_id = $1) ORDER BY at DESC LIMIT $2",
        recipient_id,
        MESSAGE_LIMIT,
    )
    messages: list[PhoneMessage] = []
    for record in records:
        data: dict[str, Any] = row_to_dict(record)
        if data["approval_code"] is not None:
            data["approval_code"] = str(data["approval_code"]).strip()
        messages.append(PhoneMessage.model_validate(data))
    return messages


async def latest_channel_for_code(
    connection: asyncpg.Connection, recipient_id: str, code: str
) -> str | None:
    """channel_type of the latest message to this recipient carrying `code`, or None."""
    value = await connection.fetchval(
        "SELECT channel_type FROM phone_messages WHERE recipient_id = $1 AND approval_code = $2 "
        "ORDER BY at DESC LIMIT 1",
        recipient_id,
        code,
    )
    return str(value) if value else None


async def latest_open_alert_id(connection: asyncpg.Connection, recipient_id: str) -> str | None:
    """Most recent open alert that a message went to this recipient about, or None."""
    value = await connection.fetchval(
        "SELECT a.id FROM phone_messages m JOIN alerts a ON a.id = m.alert_id "
        "WHERE m.recipient_id = $1 AND a.status = 'open' ORDER BY m.at DESC LIMIT 1",
        recipient_id,
    )
    return str(value) if value else None
