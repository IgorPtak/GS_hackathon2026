"""Auto-resolve wiring: resolution events close alerts; new alerts get silence deadlines."""

from alerting_core.auto_resolve import SILENCE_DEADLINES_KEY
from alerting_core.settings import Settings

from services.processor.auto_resolution import make_resolution_hook
from services.processor.batch import EventProcessor
from services.processor.folds import FoldTracker
from services.processor.groups import GroupFlusher

from .conftest import FakeRegistry, fixture_payload, message
from .test_group_flush import later_ms, stale


def alertmanager(name: str) -> dict:
    body = fixture_payload(name)
    return {**body["alerts"][0], "status": body["alerts"][0]["status"]}


def processor_with_hook(pool, redis, snapshot) -> EventProcessor:  # noqa: ANN001
    registry = FakeRegistry(snapshot)
    hook = make_resolution_hook(pool, redis, registry)  # type: ignore[arg-type]
    return EventProcessor(
        pool,
        redis,
        registry,
        Settings(),
        FoldTracker(pool, redis),
        hook,  # type: ignore[arg-type]
    )


async def test_resolved_alertmanager_event_resolves_the_firing_alert(pool, redis, snapshot) -> None:
    processor = processor_with_hook(pool, redis, snapshot)

    await processor.handle_batch(
        [message(alertmanager("alertmanager_firing.json"), "alertmanager")]
    )
    assert await pool.fetchval("SELECT status FROM alerts") == "open"

    await processor.handle_batch(
        [message(alertmanager("alertmanager_resolved.json"), "alertmanager")]
    )

    row = await pool.fetchrow("SELECT status, resolution_reason FROM alerts")
    assert (row["status"], row["resolution_reason"]) == ("resolved", "source_resolved")


async def test_group_summary_with_after_silence_gets_a_deadline(
    pool, redis, make_processor, snapshot
) -> None:
    await make_processor().handle_batch([message(stale("EURUSD"), "pricing-log")])
    flusher = GroupFlusher(pool, redis, FakeRegistry(snapshot), Settings())  # type: ignore[arg-type]

    await flusher.flush_due(later_ms(11))

    alert_id = str(await pool.fetchval("SELECT id FROM alerts WHERE is_group_summary"))
    deadline = await redis.zscore(SILENCE_DEADLINES_KEY, alert_id)
    assert deadline is not None and deadline > later_ms(15 * 60)


async def test_firing_after_resolution_in_one_batch_keeps_the_alert_open(
    pool, redis, snapshot
) -> None:
    processor = processor_with_hook(pool, redis, snapshot)
    firing = alertmanager("alertmanager_firing.json")
    await processor.handle_batch([message(firing, "alertmanager")])

    await processor.handle_batch(
        [
            message(alertmanager("alertmanager_resolved.json"), "alertmanager"),
            message(firing, "alertmanager"),  # received later: the problem is back
        ]
    )

    assert await pool.fetchval("SELECT status FROM alerts") == "open"


async def test_failing_resolution_hook_does_not_fail_the_batch(pool, redis, snapshot) -> None:
    async def broken_hook(_outcomes) -> None:  # noqa: ANN001
        raise ConnectionError("postgres down")

    processor = EventProcessor(
        pool,
        redis,
        FakeRegistry(snapshot),
        Settings(),
        FoldTracker(pool, redis),
        broken_hook,  # type: ignore[arg-type]
    )

    failures = await processor.handle_batch(
        [message(alertmanager("alertmanager_resolved.json"), "alertmanager")]
    )

    assert failures == {}
