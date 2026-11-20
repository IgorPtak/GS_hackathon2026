"""Alert queries for the API and the UI: keyset-paginated list and the detail view."""

import base64
import binascii
from datetime import datetime

import asyncpg
import orjson
from alerting_contracts.alerts import Alert, AlertStatus, AuditEntry, Delivery
from alerting_contracts.api import AlertDetail, AlertPage
from alerting_contracts.runbooks import ActionRun, ApprovalRequest

from .rows import ALERT_SELECT, alert_from_row, row_to_dict
from .transitions import AlertNotFoundError

MAX_PAGE_SIZE = 200


class InvalidCursorError(ValueError):
    """The cursor is not one produced by `list_alerts` (API: 422)."""


def encode_cursor(last_seen: datetime, alert_id: str) -> str:
    """Opaque cursor: base64 of [last_seen iso, id]."""
    return base64.urlsafe_b64encode(orjson.dumps([last_seen.isoformat(), alert_id])).decode()


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Inverse of `encode_cursor`; raises InvalidCursorError on garbage."""
    try:
        last_seen_text, alert_id = orjson.loads(base64.urlsafe_b64decode(cursor.encode()))
        last_seen = datetime.fromisoformat(last_seen_text)
    except (ValueError, TypeError, binascii.Error) as error:
        raise InvalidCursorError("invalid cursor") from error
    if last_seen.tzinfo is None:  # timestamptz comparison needs an aware value
        raise InvalidCursorError("invalid cursor")
    return last_seen, str(alert_id)


async def list_alerts(
    connection: asyncpg.Connection | asyncpg.Pool,
    team: str,
    status: list[AlertStatus] | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> AlertPage:
    """One page of a team's alerts, newest activity first (keyset on last_seen desc, id desc)."""
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    arguments: list[object] = [team]
    conditions = ["team = $1"]
    if status:
        arguments.append([item.value for item in status])
        conditions.append(f"status = ANY(${len(arguments)}::text[])")
    if cursor:
        last_seen, alert_id = decode_cursor(cursor)
        arguments.extend([last_seen, alert_id])
        conditions.append(f"(last_seen, id) < (${len(arguments) - 1}, ${len(arguments)}::uuid)")
    arguments.append(limit + 1)  # one extra row tells whether another page exists
    try:
        records = await connection.fetch(
            f"SELECT {ALERT_SELECT} FROM alerts WHERE {' AND '.join(conditions)} "
            f"ORDER BY last_seen DESC, id DESC LIMIT ${len(arguments)}",
            *arguments,
        )
    except (asyncpg.DataError, asyncpg.InvalidTextRepresentationError) as error:
        raise InvalidCursorError("invalid cursor") from error
    items = [alert_from_row(record) for record in records[:limit]]
    next_cursor = encode_cursor(items[-1].last_seen, items[-1].id) if len(records) > limit else None
    return AlertPage(items=items, next_cursor=next_cursor)


async def get_alert(connection: asyncpg.Connection | asyncpg.Pool, alert_id: str) -> Alert:
    """Fetch one alert or raise AlertNotFoundError."""
    record = await connection.fetchrow(
        f"SELECT {ALERT_SELECT} FROM alerts WHERE id = $1::uuid", alert_id
    )
    if record is None:
        raise AlertNotFoundError(alert_id)
    return alert_from_row(record)


async def get_alert_detail(
    connection: asyncpg.Connection | asyncpg.Pool, alert_id: str
) -> AlertDetail:
    """The alert with audit trail, deliveries, action runs and approval requests.

    `rendered_runbook` stays None; the API adds it (B-07).
    """
    alert = await get_alert(connection, alert_id)
    audit = await connection.fetch(
        "SELECT id, alert_id, at, actor, verb, outcome, detail FROM audit_entries "
        "WHERE alert_id = $1::uuid ORDER BY id",
        alert_id,
    )
    deliveries = await connection.fetch(
        "SELECT * FROM deliveries WHERE alert_id = $1::uuid ORDER BY id", alert_id
    )
    runs = await connection.fetch(
        "SELECT * FROM action_runs WHERE alert_id = $1::uuid ORDER BY step_index, created_at",
        alert_id,
    )
    approvals = await connection.fetch(
        "SELECT * FROM approval_requests WHERE alert_id = $1::uuid ORDER BY requested_at", alert_id
    )
    return AlertDetail(
        alert=alert,
        audit_entries=[AuditEntry.model_validate(row_to_dict(r)) for r in audit],
        deliveries=[Delivery.model_validate(row_to_dict(r)) for r in deliveries],
        action_runs=[ActionRun.model_validate(row_to_dict(r)) for r in runs],
        approval_requests=[ApprovalRequest.model_validate(row_to_dict(r)) for r in approvals],
    )
