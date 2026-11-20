"""Crash, retry and concurrency semantics the processor review asked to pin down."""

import asyncio
from types import MappingProxyType
from unittest import mock

import pytest
from alerting_contracts.config import ThrottlePolicy
from alerting_core.config.registry import ConfigSnapshot

from services.processor import batch as batch_module

from .conftest import message
from .test_processor import RULE_ID, alert_rows, rates_event


async def resolve_all(pool) -> None:  # noqa: ANN001
    await pool.execute("UPDATE alerts SET status = 'resolved', resolved_at = now()")


async def test_redelivery_after_resolve_creates_one_successor(pool, redis, make_processor) -> None:
    processor = make_processor()
    await processor.handle_batch([message(rates_event())])
    await resolve_all(pool)
    batch = [message(rates_event())]

    with mock.patch.object(batch_module, "rearm_dedup_keys", side_effect=ConnectionError):
        with pytest.raises(ConnectionError):
            await processor.handle_batch(batch)  # committed, then the re-arm failed
    await processor.handle_batch(batch)  # redelivery

    rows = await alert_rows(pool)
    assert [row["status"] for row in rows] == ["resolved", "open"]
    created = await pool.fetchval("SELECT count(*) FROM audit_entries WHERE verb = 'alert_created'")
    assert created == 2


async def test_concurrent_replicas_on_resolved_key_create_one_successor(
    pool, redis, make_processor
) -> None:
    await make_processor().handle_batch([message(rates_event())])
    await resolve_all(pool)
    processors = [make_processor() for _ in range(4)]

    await asyncio.gather(*(p.handle_batch([message(rates_event())]) for p in processors))
    for processor in processors:
        await processor._folds.flush()

    rows = await alert_rows(pool)
    assert [row["status"] for row in rows] == ["resolved", "open"]
    assert rows[1]["count"] == 4


async def test_successor_of_resolved_successor_is_followed(pool, redis, make_processor) -> None:
    processor = make_processor()
    await processor.handle_batch([message(rates_event())])
    await resolve_all(pool)
    with mock.patch.object(batch_module, "rearm_dedup_keys", side_effect=ConnectionError):
        with pytest.raises(ConnectionError):
            await processor.handle_batch([message(rates_event())])
    await resolve_all(pool)  # the successor is resolved too, and the key still names the first

    await processor.handle_batch([message(rates_event())])

    assert [row["status"] for row in await alert_rows(pool)] == ["resolved", "resolved", "open"]


async def test_overlapping_batches_in_opposite_order_do_not_deadlock(
    pool, redis, make_processor
) -> None:
    events = [rates_event(reason=f"REASON_{i}") for i in range(20)]
    first, second = make_processor(), make_processor()

    for _ in range(5):
        await asyncio.gather(
            first.handle_batch([message(e) for e in events]),
            second.handle_batch([message(e) for e in reversed(events)]),
        )
    await first._folds.flush()
    await second._folds.flush()

    rows = await alert_rows(pool)
    assert len(rows) == 20
    assert sum(row["count"] for row in rows) == 200


async def test_failed_transaction_writes_nothing(pool, redis, make_processor) -> None:
    processor = make_processor()
    with mock.patch.object(batch_module, "enqueue_outbox_rows", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            await processor.handle_batch([message(rates_event())])

    assert await alert_rows(pool) == []
    assert await pool.fetchval("SELECT count(*) FROM audit_entries") == 0

    await processor.handle_batch([message(rates_event())])  # the retry creates it once
    assert len(await alert_rows(pool)) == 1


async def test_evaluation_error_fails_only_that_entry(pool, redis, make_processor) -> None:
    processor = make_processor()
    good, bad = message(rates_event()), message(rates_event(trade_id="T-bad"))
    real = batch_module.evaluate_event

    def flaky(rule_set, envelope):  # noqa: ANN001, ANN202
        if envelope.payload["payload"]["tradeId"] == "T-bad":
            raise RuntimeError("bug")
        return real(rule_set, envelope)

    with mock.patch.object(batch_module, "evaluate_event", side_effect=flaky):
        failures = await processor.handle_batch([good, bad])

    assert list(failures) == [bad.id]
    assert len(await alert_rows(pool)) == 1


async def test_failed_fold_flush_keeps_counts(pool, redis, make_processor) -> None:
    processor = make_processor()
    await processor.handle_batch([message(rates_event())])
    await processor.handle_batch([message(rates_event()) for _ in range(3)])

    with mock.patch("services.processor.folds.apply_folds", side_effect=OSError("db down")):
        with pytest.raises(OSError):
            await processor._folds.flush()
    await processor._folds.flush()

    [alert] = await alert_rows(pool)
    assert alert["count"] == 4


async def test_throttled_targets_are_audited_as_suppressed(
    pool, redis, make_processor, snapshot
) -> None:
    rules = dict(snapshot.of_kind("rule"))
    throttle = ThrottlePolicy(max_deliveries=1, per="1h")
    rules[RULE_ID] = rules[RULE_ID].model_copy(update={"throttle": throttle})
    documents = {**snapshot.documents, "rule": MappingProxyType(rules)}
    processor = make_processor()
    processor._rebuild_rule_set(ConfigSnapshot(documents=MappingProxyType(documents)))

    for reason in ("FIRST", "SECOND"):  # two alerts for the same on-call recipient
        await processor.handle_batch([message(rates_event(reason=reason))])

    assert len(await alert_rows(pool)) == 2
    suppressed = await pool.fetch(
        "SELECT detail FROM audit_entries WHERE verb = 'delivery_suppressed'"
    )
    assert suppressed
    assert {row["detail"]["recipient_id"] for row in suppressed} == {"anna"}
