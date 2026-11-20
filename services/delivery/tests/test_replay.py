"""scripts/replay_dead_letters.py: a dead-lettered job delivers after replay, exactly once."""

import importlib.util
from pathlib import Path

from plugins.channels.base import ChannelRejectedError

from .conftest import email_job, stream_message

_SPEC = importlib.util.spec_from_file_location(
    "replay_dead_letters", Path(__file__).parents[3] / "scripts/replay_dead_letters.py"
)
replay_module = importlib.util.module_from_spec(_SPEC)  # type: ignore[arg-type]
_SPEC.loader.exec_module(replay_module)  # type: ignore[union-attr]


async def test_replayed_dead_letter_is_delivered_without_a_second_fallback(
    pool, redis, plugin, worker
) -> None:
    plugin.failures = [ChannelRejectedError("mailbox full")]
    job = email_job()
    await worker.handle_batch([stream_message(job)])
    assert await redis.xlen("deliveries-dlq") == 1

    assert await replay_module.replay(redis, {job.delivery_id}, is_dry_run=False) == 1
    [(_, fields)] = await redis.xrange("deliveries")
    await worker.handle_batch([stream_message(job.model_validate_json(fields[b"job"]))])

    status = await pool.fetchval("SELECT status FROM deliveries WHERE id = $1", job.delivery_id)
    assert status == "delivered"
    assert await redis.xlen("deliveries-dlq") == 0
    assert await pool.fetchval("SELECT count(*) FROM outbox") == 1  # the original fallback only


async def test_dry_run_and_filter_leave_the_dlq_untouched(pool, redis, plugin, worker) -> None:
    plugin.failures = [ChannelRejectedError("x")]
    await worker.handle_batch([stream_message(email_job())])

    assert await replay_module.replay(redis, {999}, is_dry_run=False) == 0
    assert await replay_module.replay(redis, None, is_dry_run=True) == 1
    assert await redis.xlen("deliveries-dlq") == 1
