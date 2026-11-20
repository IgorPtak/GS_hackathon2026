"""Delivery status, audit entries and fallback rows, written in one transaction per outcome.

The relay XADDs before it commits, so the `deliveries` row may not be visible yet when a job
arrives: every write here is an upsert built from the job itself. A `delivered` row is never
downgraded by a late or duplicate job.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg
from alerting_contracts.alerts import AuditEntry, AuditVerb, Delivery, DeliveryJob, DeliveryStatus
from alerting_contracts.common import Actor
from alerting_contracts.config import ChannelConfig
from alerting_core.outbox import enqueue_delivery
from alerting_core.storage.audit import append_audit
from alerting_core.storage.rows import row_to_dict

DELIVERY_ACTOR = Actor(id="system:delivery")

_UPSERT = """
    INSERT INTO deliveries (
        id, alert_id, team, recipient_id, channel_id, channel_type, purpose, is_fallback,
        status, attempt, last_error, delivered_at
    ) VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
    ON CONFLICT (id) DO UPDATE SET
        status = EXCLUDED.status,
        attempt = greatest(deliveries.attempt, EXCLUDED.attempt),
        last_error = EXCLUDED.last_error,
        delivered_at = coalesce(deliveries.delivered_at, EXCLUDED.delivered_at),
        updated_at = now()
    WHERE deliveries.status <> 'delivered'
    RETURNING *
"""


@dataclass(frozen=True, slots=True)
class Outcome:
    """What happened to one attempt, as stored and audited."""

    status: DeliveryStatus
    verb: AuditVerb
    attempt: int
    error: str | None = None
    delivered_at: datetime | None = None


@dataclass(slots=True)
class RecordedOutcome:
    delivery: Delivery | None  # None when nothing changed (already delivered/dead-lettered)
    audit: list[AuditEntry]


async def delivery_age_seconds(pool: asyncpg.Pool, delivery_id: int) -> float:
    """Seconds since the delivery row was created; 0 when the relay has not committed it yet."""
    age = await pool.fetchval(
        "SELECT extract(epoch FROM now() - created_at) FROM deliveries WHERE id = $1", delivery_id
    )
    return float(age or 0.0)


async def record_outcome(
    pool: asyncpg.Pool,
    job: DeliveryJob,
    outcome: Outcome,
    fallback: ChannelConfig | None = None,
) -> RecordedOutcome:
    """Upsert the delivery row, audit it and, for a dead letter, queue the fallback delivery."""
    async with pool.acquire() as connection, connection.transaction():
        previous = await connection.fetchval(
            "SELECT status FROM deliveries WHERE id = $1 FOR UPDATE", job.delivery_id
        )
        if previous == DeliveryStatus.dead_lettered and outcome.status == previous:
            # A redelivered entry that was already dead-lettered: one fallback, one audit.
            return RecordedOutcome(delivery=None, audit=[])
        row = await connection.fetchrow(
            _UPSERT,
            job.delivery_id,
            job.alert_id,
            job.team,
            job.recipient_id,
            job.channel_id,
            job.channel_type.value,
            job.purpose.value,
            job.is_fallback,
            outcome.status.value,
            outcome.attempt,
            outcome.error,
            outcome.delivered_at,
        )
        if row is None:
            return RecordedOutcome(delivery=None, audit=[])
        detail: dict[str, Any] = {
            "delivery_id": job.delivery_id,
            "channel_id": job.channel_id,
            "recipient_id": job.recipient_id,
            "attempt": outcome.attempt,
        }
        if outcome.error:
            detail["error"] = outcome.error[:500]
        status_ok = "ok" if outcome.status == DeliveryStatus.delivered else "error"
        entries = [
            await append_audit(
                connection, job.alert_id, DELIVERY_ACTOR, outcome.verb, status_ok, detail
            )
        ]
        if fallback is not None:
            fallback_job = fallback_job_for(job, fallback)
            outbox_id = await enqueue_delivery(connection, fallback_job)
            fallback_detail = {**detail, "fallback_channel_id": fallback.id, "outbox_id": outbox_id}
            entries.append(
                await append_audit(
                    connection,
                    job.alert_id,
                    DELIVERY_ACTOR,
                    AuditVerb.delivery_fallback,
                    "ok",
                    fallback_detail,
                )
            )
        return RecordedOutcome(delivery=Delivery.model_validate(row_to_dict(row)), audit=entries)


def fallback_job_for(job: DeliveryJob, fallback: ChannelConfig) -> DeliveryJob:
    """Same content on the fallback channel; ui is team-wide, so it has no recipient."""
    return job.model_copy(
        update={
            "delivery_id": 0,  # stamped by the relay
            "channel_id": fallback.id,
            "channel_type": fallback.type,
            "recipient_id": None if fallback.type == "ui" else job.recipient_id,
            "attempt": 0,
            "not_before": None,
            "is_fallback": True,
        }
    )
