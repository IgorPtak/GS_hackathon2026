"""Batch writes of the processor hot path: one statement per batch, never one per event.

Rows travel as one jsonb array and are expanded server side (`jsonb_populate_recordset` /
`jsonb_to_recordset`), so a batch of 100 events costs a fixed number of round trips.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg
from alerting_contracts.alerts import Alert, AlertStatus, AuditEntry, AuditVerb
from alerting_contracts.api import UnknownSchemaSample
from alerting_contracts.common import Actor

from .rows import ALERT_SELECT, alert_from_row, row_to_dict

_INSERT_ALERTS = f"""
    INSERT INTO alerts ({ALERT_SELECT})
    SELECT {ALERT_SELECT} FROM jsonb_populate_recordset(NULL::alerts, $1::jsonb)
    ON CONFLICT (id) DO NOTHING
    RETURNING id
"""
_SELECT_STATES = "SELECT id, status, resolved_at FROM alerts WHERE id = ANY($1::uuid[])"
_SELECT_OPEN_BY_KEY = """
    SELECT DISTINCT ON (a.rule_id, a.fingerprint) a.rule_id, a.fingerprint, a.id
    FROM alerts a
    JOIN unnest($1::text[], $2::text[]) AS k(rule_id, fingerprint)
      ON a.rule_id = k.rule_id AND a.fingerprint = k.fingerprint
    WHERE a.status <> 'resolved'
    ORDER BY a.rule_id, a.fingerprint, a.first_seen DESC
"""
_INSERT_AUDIT = """
    INSERT INTO audit_entries (alert_id, actor, verb, outcome, detail)
    SELECT alert_id, actor, verb, outcome, detail
    FROM jsonb_to_recordset($1::jsonb)
      AS x(alert_id uuid, actor jsonb, verb text, outcome text, detail jsonb)
    RETURNING id, alert_id, at, actor, verb, outcome, detail
"""
# last_event follows the newest event only; updated_at is bumped on every flush (contract).
_APPLY_FOLDS = f"""
    UPDATE alerts a SET
        count = a.count + u.delta,
        last_event = CASE WHEN u.last_seen >= a.last_seen THEN u.last_event ELSE a.last_event END,
        last_seen = greatest(a.last_seen, u.last_seen),
        updated_at = greatest(now(), a.updated_at)
    FROM jsonb_to_recordset($1::jsonb)
      AS u(id uuid, delta int, last_seen timestamptz, last_event jsonb)
    WHERE a.id = u.id
    RETURNING {", ".join(f"a.{column}" for column in ALERT_SELECT.split(", "))}
"""
_UPSERT_SAMPLES = """
    INSERT INTO unknown_schema_samples AS s
        (shape_hash, source_id, key_paths, sample_event, event_count, first_seen, last_seen)
    SELECT shape_hash, source_id, key_paths, sample_event, event_count, seen, seen
    FROM jsonb_to_recordset($1::jsonb) AS x(
        shape_hash text, source_id text, key_paths text[], sample_event jsonb,
        event_count int, seen timestamptz)
    ON CONFLICT (shape_hash) DO UPDATE SET
        event_count = s.event_count + EXCLUDED.event_count,
        last_seen = greatest(s.last_seen, EXCLUDED.last_seen)
    RETURNING s.*, (xmax = 0) AS is_new
"""


@dataclass(frozen=True, slots=True)
class FoldUpdate:
    """Events folded into an existing alert since the last flush."""

    alert_id: str
    delta: int
    last_seen: datetime
    last_event: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AuditRow:
    alert_id: str
    actor: Actor
    verb: AuditVerb
    detail: dict[str, Any]
    outcome: str = "ok"


async def insert_alerts(connection: asyncpg.Connection, alerts: Sequence[Alert]) -> set[str]:
    """Insert alerts whose id is new; returns the ids actually inserted (others already existed).

    Inside a transaction a concurrent insert of the same id blocks until that transaction ends,
    so exactly one writer sees each id returned and owns its side effects (outbox, audit).
    """
    if not alerts:
        return set()
    ordered = sorted(alerts, key=lambda alert: alert.id)  # one lock order on every replica
    rows = await connection.fetch(_INSERT_ALERTS, [a.model_dump(mode="json") for a in ordered])
    return {str(row["id"]) for row in rows}


@dataclass(frozen=True, slots=True)
class AlertState:
    status: AlertStatus
    resolved_at: datetime | None


async def fetch_alert_states(
    connection: asyncpg.Connection, alert_ids: Sequence[str]
) -> dict[str, AlertState]:
    if not alert_ids:
        return {}
    rows = await connection.fetch(_SELECT_STATES, list(alert_ids))
    return {
        str(row["id"]): AlertState(AlertStatus(row["status"]), row["resolved_at"]) for row in rows
    }


async def find_open_alerts(
    connection: asyncpg.Connection, keys: Sequence[tuple[str, str]]
) -> dict[tuple[str, str], str]:
    """Newest open alert id per (rule_id, fingerprint), for re-arming an expired dedup window."""
    if not keys:
        return {}
    rule_ids = [rule_id for rule_id, _ in keys]
    fingerprints = [fingerprint for _, fingerprint in keys]
    rows = await connection.fetch(_SELECT_OPEN_BY_KEY, rule_ids, fingerprints)
    return {(row["rule_id"], row["fingerprint"]): str(row["id"]) for row in rows}


async def insert_audit_entries(
    connection: asyncpg.Connection, entries: Sequence[AuditRow]
) -> list[AuditEntry]:
    if not entries:
        return []
    payload = [
        {
            "alert_id": entry.alert_id,
            "actor": entry.actor.model_dump(mode="json"),
            "verb": entry.verb.value,
            "outcome": entry.outcome,
            "detail": entry.detail,
        }
        for entry in entries
    ]
    rows = await connection.fetch(_INSERT_AUDIT, payload)
    return [AuditEntry.model_validate(row_to_dict(row)) for row in rows]


async def apply_folds(connection: asyncpg.Connection, updates: Sequence[FoldUpdate]) -> list[Alert]:
    """Add fold deltas to `alerts.count`; returns the updated alerts (missing ids are absent)."""
    if not updates:
        return []
    ordered = sorted(updates, key=lambda update: update.alert_id)
    payload = [
        {
            "id": update.alert_id,
            "delta": update.delta,
            "last_seen": update.last_seen.isoformat(),
            "last_event": update.last_event,
        }
        for update in ordered
    ]
    rows = await connection.fetch(_APPLY_FOLDS, payload)
    return [alert_from_row(row) for row in rows]


async def upsert_unknown_samples(
    connection: asyncpg.Connection, samples: Sequence[UnknownSchemaSample]
) -> list[UnknownSchemaSample]:
    """Count unknown-shape events per shape_hash; returns only shapes seen for the first time."""
    if not samples:
        return []
    payload = [
        {
            "shape_hash": sample.shape_hash,
            "source_id": sample.source_id,
            "key_paths": sample.key_paths,
            "sample_event": sample.sample_event,
            "event_count": sample.event_count,
            "seen": sample.last_seen.isoformat(),
        }
        for sample in sorted(samples, key=lambda sample: sample.shape_hash)
    ]
    rows = await connection.fetch(_UPSERT_SAMPLES, payload)
    return [
        UnknownSchemaSample.model_validate({k: v for k, v in dict(row).items() if k != "is_new"})
        for row in rows
        if row["is_new"]
    ]
