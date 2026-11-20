"""Alert creation, dedup folding and crash/concurrency semantics of the processor batch."""

import asyncio
import copy

import asyncpg
from alerting_contracts.alerts import DeliveryJob, RunbookJob
from alerting_core.config.registry import ConfigSnapshot
from alerting_core.dedup import dedup_key
from alerting_core.ids import new_uuid7

from .conftest import fixture_payload, message

RULE_ID = "rates-large-rejections"


def rates_event(notional: int = 25_000_000, trade_id: str = "T-1") -> dict:
    payload = copy.deepcopy(fixture_payload("rates_trade_rejected.json"))
    payload["payload"]["notional"] = notional
    payload["payload"]["tradeId"] = trade_id
    return payload


async def alert_rows(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch("SELECT * FROM alerts ORDER BY first_seen")


async def test_first_event_creates_alert_audit_and_outbox(pool, redis, make_processor) -> None:
    processor = make_processor()

    assert await processor.handle_batch([message(rates_event())]) == {}

    [alert] = await alert_rows(pool)
    assert alert["rule_id"] == RULE_ID
    assert alert["title"] == "Rejected EUR 25000000 — LIMIT_BREACH"
    assert alert["count"] == 1
    assert alert["runbook_id"] == "trade-limit-breach"
    verbs = await pool.fetch("SELECT verb FROM audit_entries WHERE alert_id = $1", alert["id"])
    assert [row["verb"] for row in verbs] == ["alert_created"]
    rows = await pool.fetch("SELECT kind, payload FROM outbox ORDER BY id")
    deliveries = [DeliveryJob.model_validate(r["payload"]) for r in rows if r["kind"] == "delivery"]
    assert {d.channel_type for d in deliveries} >= {"ui"}
    assert all(d.content.alert_url.endswith(str(alert["id"])) for d in deliveries)
    [runbook] = [
        RunbookJob.model_validate(r["payload"]) for r in rows if r["kind"] == "runbook_job"
    ]
    assert runbook.runbook_id == "trade-limit-breach"


async def test_identical_events_in_one_batch_make_one_alert(pool, redis, make_processor) -> None:
    await make_processor().handle_batch([message(rates_event()) for _ in range(5)])

    [alert] = await alert_rows(pool)
    assert alert["count"] == 5


async def test_later_events_fold_and_flush_counts(pool, redis, make_processor) -> None:
    processor = make_processor()
    await processor.handle_batch([message(rates_event())])
    outbox_before = await pool.fetchval("SELECT count(*) FROM outbox")

    await processor.handle_batch([message(rates_event()) for _ in range(3)])
    await processor._folds.flush()

    [alert] = await alert_rows(pool)
    assert alert["count"] == 4
    assert await pool.fetchval("SELECT count(*) FROM outbox") == outbox_before


async def test_redelivered_batch_only_increments_count(pool, redis, make_processor) -> None:
    processor = make_processor()
    batch = [message(rates_event())]
    await processor.handle_batch(batch)
    outbox_before = await pool.fetchval("SELECT count(*) FROM outbox")

    await processor.handle_batch(batch)  # crash between commit and XACK
    await processor._folds.flush()

    [alert] = await alert_rows(pool)
    assert alert["count"] == 2
    assert await pool.fetchval("SELECT count(*) FROM outbox") == outbox_before


async def test_alert_lost_after_set_nx_is_recreated_with_key_id(
    pool, redis, make_processor
) -> None:
    processor = make_processor()
    await processor.handle_batch([message(rates_event())])
    [first] = await alert_rows(pool)
    lost_id = new_uuid7()
    await pool.execute("TRUNCATE alerts, outbox, audit_entries")
    await redis.set(dedup_key(RULE_ID, first["fingerprint"]), lost_id, px=60_000)

    await processor.handle_batch([message(rates_event())])

    [alert] = await alert_rows(pool)
    assert str(alert["id"]) == lost_id
    assert await pool.fetchval("SELECT count(*) FROM outbox") > 0


async def test_resolved_alert_is_not_reopened(pool, redis, make_processor) -> None:
    processor = make_processor()
    await processor.handle_batch([message(rates_event())])
    await pool.execute("UPDATE alerts SET status = 'resolved'")

    await processor.handle_batch([message(rates_event())])

    rows = await alert_rows(pool)
    assert [row["status"] for row in rows] == ["resolved", "open"]
    [fingerprint] = {row["fingerprint"] for row in rows}
    assert (await redis.get(dedup_key(RULE_ID, fingerprint))).decode() == str(rows[1]["id"])


async def test_expired_window_folds_into_open_alert(pool, redis, make_processor) -> None:
    processor = make_processor()
    await processor.handle_batch([message(rates_event())])
    await redis.flushdb()  # the dedup window expired

    await processor.handle_batch([message(rates_event())])
    await processor._folds.flush()

    [alert] = await alert_rows(pool)
    assert alert["count"] == 2
    assert (await redis.get(dedup_key(RULE_ID, alert["fingerprint"]))).decode() == str(alert["id"])


async def test_concurrent_processors_create_one_alert(pool, redis, make_processor) -> None:
    processors = [make_processor() for _ in range(4)]
    batches = [[message(rates_event()) for _ in range(25)] for _ in processors]

    await asyncio.gather(*(p.handle_batch(b) for p, b in zip(processors, batches, strict=True)))
    for processor in processors:
        await processor._folds.flush()

    [alert] = await alert_rows(pool)
    assert alert["count"] == 100
    created = await pool.fetchval("SELECT count(*) FROM audit_entries WHERE verb = 'alert_created'")
    assert created == 1


async def test_distinct_fingerprints_create_distinct_alerts(pool, redis, make_processor) -> None:
    events = [message(rates_event(trade_id=f"T-{i}")) for i in range(3)]
    await make_processor().handle_batch(events)

    rows = await alert_rows(pool)
    assert len({row["fingerprint"] for row in rows}) == len(rows) >= 1


async def test_non_matching_event_creates_nothing(pool, redis, make_processor) -> None:
    await make_processor().handle_batch([message(rates_event(notional=5))])

    assert await alert_rows(pool) == []


async def test_invalid_envelope_is_dead_lettered(pool, redis, make_processor) -> None:
    processor = make_processor()
    dead: list[str] = []

    async def dead_letter(messages, error) -> None:  # noqa: ANN001
        dead.extend(m.id for m in messages)

    processor.dead_letter = dead_letter
    broken = message(rates_event())
    broken.fields[b"envelope"] = b"{not json"

    assert await processor.handle_batch([broken]) == {}
    assert dead == [broken.id]


async def test_unknown_shape_is_sampled_once_per_shape(pool, redis, make_processor) -> None:
    payload = fixture_payload("unknown_payments.json")
    await make_processor().handle_batch([message(payload, "generic-webhook") for _ in range(3)])

    [sample] = await pool.fetch("SELECT * FROM unknown_schema_samples")
    assert sample["event_count"] == 3
    assert sample["source_id"] == "generic-webhook"


async def test_rule_set_follows_config_reload(pool, redis, make_processor) -> None:
    processor = make_processor()
    for callback in processor._registry.on_reload:
        callback(ConfigSnapshot())  # every rule removed

    await processor.handle_batch([message(rates_event())])

    assert await alert_rows(pool) == []
