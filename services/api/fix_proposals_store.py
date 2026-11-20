"""SQL helpers for fix proposals (table `fix_proposals`).

Every function takes a pool or a connection; nothing here commits. Decision writes must run in
the caller's transaction after `lock_proposal`.
"""

import json
from typing import Any
from uuid import UUID, uuid4

import asyncpg
from alerting_contracts.alerts import Alert
from alerting_contracts.common import Actor
from alerting_contracts.proposals import FixProposal, FixProposalCreate, ProposalStatus
from alerting_core.storage.rows import row_to_dict

PROPOSAL_LIMIT = 200


def is_uuid(value: str) -> bool:
    """True when `value` parses as a uuid (a malformed id is simply 'not found')."""
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _proposal(record: asyncpg.Record) -> FixProposal:
    data = row_to_dict(record)
    for key in ("proposed_rule", "proposed_runbook_step", "proposed_by", "decided_by"):
        data[key] = _json(data[key])
    return FixProposal.model_validate(data)


def _dump(model: Any) -> Any:
    return model.model_dump(mode="json", by_alias=True) if model is not None else None


async def insert_proposal(
    connection: asyncpg.Connection, alert: Alert, owner_team: str, body: FixProposalCreate
) -> FixProposal:
    """Insert a pending proposal for `alert` owned by `owner_team`."""
    record = await connection.fetchrow(
        "INSERT INTO fix_proposals (id, alert_id, rule_id, runbook_id, owner_team, kind, "
        "description, proposed_rule, proposed_runbook_step, proposed_by) "
        "VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING *",
        str(uuid4()),
        alert.id,
        alert.rule_id,
        alert.runbook_id,
        owner_team,
        body.kind.value,
        body.description,
        _dump(body.proposed_rule),
        _dump(body.proposed_runbook_step),
        body.proposed_by.model_dump(mode="json"),
    )
    if record is None:
        raise RuntimeError("fix proposal insert returned no row")
    return _proposal(record)


async def list_proposals(
    pool: asyncpg.Pool, team: str | None, status: ProposalStatus | None
) -> list[FixProposal]:
    """Proposals of one owner team and/or status, newest first (at most 200)."""
    records = await pool.fetch(
        "SELECT * FROM fix_proposals WHERE ($1::text IS NULL OR owner_team = $1) "
        "AND ($2::text IS NULL OR status = $2) ORDER BY created_at DESC, id DESC LIMIT $3",
        team,
        status.value if status else None,
        PROPOSAL_LIMIT,
    )
    return [_proposal(record) for record in records]


async def lock_proposal(connection: asyncpg.Connection, proposal_id: str) -> FixProposal | None:
    """Select one proposal `FOR UPDATE`; concurrent deciders serialize on this lock."""
    record = await connection.fetchrow(
        "SELECT * FROM fix_proposals WHERE id = $1::uuid FOR UPDATE", proposal_id
    )
    return _proposal(record) if record else None


async def mark_decided(
    connection: asyncpg.Connection,
    proposal_id: str,
    status: ProposalStatus,
    actor: Actor,
    comment: str | None,
) -> FixProposal:
    """Stamp the decision on a pending proposal already locked by `lock_proposal`."""
    record = await connection.fetchrow(
        "UPDATE fix_proposals SET status = $2, decided_by = $3, decided_at = now(), "
        "decision_comment = $4 WHERE id = $1::uuid AND status = 'pending' RETURNING *",
        proposal_id,
        status.value,
        actor.model_dump(mode="json"),
        comment,
    )
    if record is None:
        raise RuntimeError("fix proposal update returned no row")
    return _proposal(record)


async def get_rule_document(pool: asyncpg.Pool, rule_id: str) -> tuple[dict[str, Any], int] | None:
    """Stored canonical document and version of a rule, or None when it does not exist."""
    record = await pool.fetchrow(
        "SELECT document, version FROM config_documents WHERE kind = 'rule' AND id = $1", rule_id
    )
    if record is None:
        return None
    return _json(record["document"]), int(record["version"])
