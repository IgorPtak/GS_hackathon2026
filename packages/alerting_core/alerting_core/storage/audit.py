"""Append-only audit trail."""

from typing import Any

import asyncpg
from alerting_contracts.alerts import AuditEntry, AuditVerb
from alerting_contracts.common import Actor

from .rows import row_to_dict


async def append_audit(
    connection: asyncpg.Connection,
    alert_id: str,
    actor: Actor,
    verb: AuditVerb,
    outcome: str = "ok",
    detail: dict[str, Any] | None = None,
) -> AuditEntry:
    """Insert one audit entry and return it; call inside the transaction of the recorded change."""
    record = await connection.fetchrow(
        "INSERT INTO audit_entries (alert_id, actor, verb, outcome, detail) "
        "VALUES ($1::uuid, $2, $3, $4, $5) "
        "RETURNING id, alert_id, at, actor, verb, outcome, detail",
        alert_id,
        actor.model_dump(mode="json"),
        verb.value,
        outcome,
        detail or {},
    )
    if record is None:
        raise RuntimeError("audit insert returned no row")
    return AuditEntry.model_validate(row_to_dict(record))
