"""Alert repository, transitions, audit and outbox helpers against real Postgres."""

import asyncio
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from alerting_contracts.alerts import (
    AlertStatus,
    AuditVerb,
    DeliveryJob,
    ResolutionReason,
    RunbookJob,
)
from alerting_contracts.common import Actor
from alerting_core.ids import new_uuid7
from alerting_core.outbox import enqueue_delivery, enqueue_outbox_rows, enqueue_runbook_job
from alerting_core.storage import (
    AlertNotFoundError,
    InvalidCursorError,
    InvalidTransitionError,
    acknowledge_alert,
    alert_from_row,
    append_audit,
    get_alert_detail,
    list_alerts,
    resolve_alert,
)

ANNA = Actor(id="anna")


async def test_pagination_has_no_duplicates_or_gaps(pool, insert_alert) -> None:
    base = datetime.now(UTC)
    expected: list[str] = []
    for index in range(7):
        # Two alerts share a last_seen so the id tie-break is exercised.
        seen = base - timedelta(minutes=index // 2)
        alert = await insert_alert(last_seen=seen)
        expected.append(alert.id)
    await insert_alert(team="other")
    expected.sort(key=lambda alert_id: alert_id, reverse=True)

    seen_ids: list[str] = []
    cursor = None
    pages = 0
    while True:
        page = await list_alerts(pool, "rates", limit=3, cursor=cursor)
        seen_ids.extend(item.id for item in page.items)
        pages += 1
        cursor = page.next_cursor
        if cursor is None:
            break
    assert pages == 3
    assert len(seen_ids) == len(set(seen_ids)) == 7
    assert set(seen_ids) == set(expected)
    # Newest activity first.
    all_alerts = (await list_alerts(pool, "rates", limit=50)).items
    keys = [(a.last_seen, a.id) for a in all_alerts]
    assert keys == sorted(keys, reverse=True)


async def test_list_filters_by_status(pool, insert_alert) -> None:
    await insert_alert()
    acked = await insert_alert(status=AlertStatus.acknowledged)
    page = await list_alerts(pool, "rates", status=[AlertStatus.acknowledged])
    assert [item.id for item in page.items] == [acked.id]
    assert page.next_cursor is None


async def test_invalid_cursor_is_rejected(pool) -> None:
    with pytest.raises(InvalidCursorError):
        await list_alerts(pool, "rates", cursor="not-a-cursor")


async def test_acknowledge_then_resolve_writes_audit(pool, insert_alert) -> None:
    alert = await insert_alert(last_seen=datetime.now(UTC) - timedelta(hours=1))
    async with pool.acquire() as connection:
        acked, ack_audit = await acknowledge_alert(connection, alert.id, ANNA)
        assert acked.status is AlertStatus.acknowledged
        assert acked.acknowledged_by == ANNA
        assert acked.acknowledged_at is not None
        assert acked.updated_at > alert.updated_at
        assert ack_audit.verb is AuditVerb.alert_acknowledged

        resolved, resolve_audit = await resolve_alert(connection, alert.id, ANNA, comment="fixed")
    assert resolved.status is AlertStatus.resolved
    assert resolved.resolved_by == ANNA
    assert resolved.resolved_at is not None
    assert resolved.resolution_reason is ResolutionReason.manual
    assert resolve_audit.detail == {"reason": "manual", "comment": "fixed"}

    detail = await get_alert_detail(pool, alert.id)
    assert detail.alert.status is AlertStatus.resolved
    assert [entry.verb for entry in detail.audit_entries] == [
        AuditVerb.alert_acknowledged,
        AuditVerb.alert_resolved,
    ]
    assert detail.rendered_runbook is None
    assert detail.deliveries == [] and detail.action_runs == [] and detail.approval_requests == []


@pytest.mark.parametrize(
    ("start", "action", "is_allowed"),
    [
        (AlertStatus.open, "ack", True),
        (AlertStatus.acknowledged, "ack", False),
        (AlertStatus.resolved, "ack", False),
        (AlertStatus.open, "resolve", True),
        (AlertStatus.acknowledged, "resolve", True),
        (AlertStatus.resolved, "resolve", False),
    ],
)
async def test_transition_matrix(pool, insert_alert, start, action, is_allowed) -> None:
    alert = await insert_alert(status=start)
    operation = acknowledge_alert if action == "ack" else resolve_alert
    async with pool.acquire() as connection:
        if is_allowed:
            await operation(connection, alert.id, ANNA)
        else:
            with pytest.raises(InvalidTransitionError):
                await operation(connection, alert.id, ANNA)
    if not is_allowed:
        assert (
            await pool.fetchval(
                "SELECT count(*) FROM audit_entries WHERE alert_id = $1::uuid", alert.id
            )
            == 0
        )


async def test_resolve_accepts_reason(pool, insert_alert) -> None:
    alert = await insert_alert()
    async with pool.acquire() as connection:
        resolved, _ = await resolve_alert(
            connection,
            alert.id,
            Actor(id="system:processor"),
            reason=ResolutionReason.source_resolved,
        )
    assert resolved.resolution_reason is ResolutionReason.source_resolved


async def test_unknown_alert_raises_not_found(pool) -> None:
    async with pool.acquire() as connection:
        with pytest.raises(AlertNotFoundError):
            await acknowledge_alert(connection, new_uuid7(), ANNA)


async def test_concurrent_acknowledge_has_exactly_one_winner(pool, insert_alert) -> None:
    alert = await insert_alert()

    async def attempt() -> bool:
        async with pool.acquire() as connection:
            try:
                await acknowledge_alert(connection, alert.id, ANNA)
            except InvalidTransitionError:
                return False
            return True

    results = await asyncio.gather(*[attempt() for _ in range(6)])
    assert results.count(True) == 1
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM audit_entries WHERE alert_id = $1::uuid", alert.id
        )
        == 1
    )


async def test_append_audit_returns_entry(pool, insert_alert) -> None:
    alert = await insert_alert()
    async with pool.acquire() as connection:
        entry = await append_audit(
            connection,
            alert.id,
            Actor(id="llm"),
            AuditVerb.fix_proposed,
            outcome="pending",
            detail={"k": 1},
        )
    assert entry.alert_id == alert.id
    assert entry.actor.id == "llm"
    assert entry.outcome == "pending"
    assert entry.detail == {"k": 1}


def delivery_job(alert_id: str) -> DeliveryJob:
    return DeliveryJob.model_validate(
        {
            "delivery_id": 0,
            "alert_id": alert_id,
            "team": "rates",
            "recipient_id": "anna",
            "channel_id": "email",
            "channel_type": "email",
            "purpose": "alert",
            "content": {
                "title": "t",
                "severity": "error",
                "alert_url": "http://localhost:5173/alerts/x",
            },
        }
    )


async def test_enqueue_helpers_write_rows_the_relay_accepts(
    pool: asyncpg.Pool, insert_alert
) -> None:
    alert = await insert_alert()
    async with pool.acquire() as connection:
        delivery_id = await enqueue_delivery(connection, delivery_job(alert.id))
        runbook_id = await enqueue_runbook_job(
            connection, RunbookJob(job_type="start_runbook", alert_id=alert.id, runbook_id="rb")
        )
    rows = await pool.fetch(
        "SELECT id, kind, alert_id, payload, relayed_at FROM outbox ORDER BY id"
    )
    assert [row["id"] for row in rows] == [delivery_id, runbook_id]
    assert [row["kind"] for row in rows] == ["delivery", "runbook_job"]
    assert all(str(row["alert_id"]) == alert.id and row["relayed_at"] is None for row in rows)
    assert DeliveryJob.model_validate(rows[0]["payload"]).channel_id == "email"
    assert RunbookJob.model_validate(rows[1]["payload"]).runbook_id == "rb"


async def test_enqueue_outbox_rows_batch(pool: asyncpg.Pool, insert_alert) -> None:
    alert = await insert_alert()
    jobs = [delivery_job(alert.id).model_copy(update={"channel_id": f"c{i}"}) for i in range(5)]
    from alerting_contracts.alerts import OutboxKind

    async with pool.acquire() as connection:
        assert await enqueue_outbox_rows(connection, []) == []
        ids = await enqueue_outbox_rows(
            connection,
            [(OutboxKind.delivery, alert.id, job.model_dump(mode="json")) for job in jobs],
        )
    rows = await pool.fetch("SELECT id, payload FROM outbox ORDER BY id")
    assert [row["id"] for row in rows] == ids
    assert [row["payload"]["channel_id"] for row in rows] == [f"c{i}" for i in range(5)]


async def test_alert_from_row_roundtrip(pool, insert_alert) -> None:
    alert = await insert_alert()
    record = await pool.fetchrow("SELECT * FROM alerts WHERE id = $1::uuid", alert.id)
    assert alert_from_row(record) == alert


async def test_list_alerts_without_team_lists_every_team(pool, insert_alert) -> None:  # noqa: ANN001
    await insert_alert(team="rates")
    await insert_alert(team="other")

    every_team = {alert.team for alert in (await list_alerts(pool, None, limit=200)).items}
    rates_only = {alert.team for alert in (await list_alerts(pool, "rates", limit=200)).items}

    assert every_team == {"rates", "other"}
    assert rates_only == {"rates"}
