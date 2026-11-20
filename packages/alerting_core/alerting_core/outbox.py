"""Transactional outbox writers; call inside the transaction of the change that causes the row.

`delivery_id` in a DeliveryJob payload may be 0: the outbox relay stamps it with the outbox id.
"""

from typing import Any

import asyncpg
from alerting_contracts.alerts import DeliveryJob, OutboxKind, RunbookJob

OutboxRow = tuple[OutboxKind, str, dict[str, Any]]


async def enqueue_delivery(connection: asyncpg.Connection, job: DeliveryJob) -> int:
    """Insert a `delivery` outbox row and return its id (the future delivery id)."""
    return await _enqueue(
        connection, OutboxKind.delivery, job.alert_id, job.model_dump(mode="json")
    )


async def enqueue_runbook_job(connection: asyncpg.Connection, job: RunbookJob) -> int:
    """Insert a `runbook_job` outbox row and return its id."""
    return await _enqueue(
        connection, OutboxKind.runbook_job, job.alert_id, job.model_dump(mode="json")
    )


async def _enqueue(
    connection: asyncpg.Connection, kind: OutboxKind, alert_id: str, payload: dict[str, Any]
) -> int:
    outbox_id = await connection.fetchval(
        "INSERT INTO outbox (kind, alert_id, payload) VALUES ($1, $2::uuid, $3) RETURNING id",
        kind.value,
        alert_id,
        payload,
    )
    return int(outbox_id)


async def enqueue_outbox_rows(connection: asyncpg.Connection, rows: list[OutboxRow]) -> list[int]:
    """Insert many rows in one statement (processor hot path); returns ids in input order."""
    if not rows:
        return []
    records = await connection.fetch(
        "INSERT INTO outbox (kind, alert_id, payload) "
        "SELECT kind, alert_id, payload FROM unnest($1::text[], $2::uuid[], $3::jsonb[]) "
        "WITH ORDINALITY AS t(kind, alert_id, payload, position) ORDER BY position RETURNING id",
        [kind.value for kind, _, _ in rows],
        [alert_id for _, alert_id, _ in rows],
        [payload for _, _, payload in rows],
    )
    return sorted(int(record["id"]) for record in records)
