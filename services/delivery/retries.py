"""Delayed retries: failed jobs wait in the `delivery-retries` zset (score = due ms).

The poller moves due jobs back to `deliveries` with one Lua script, so a job is either in the
zset or in the stream, never in neither (contracts/storage.md).
"""

import asyncio
import random
import time
from contextlib import suppress

from alerting_contracts.alerts import DeliveryJob
from alerting_core.logging import get_logger
from redis.asyncio import Redis
from redis.commands.core import AsyncScript
from redis.exceptions import RedisError

log = get_logger(__name__)

RETRIES_KEY = "delivery-retries"
DELIVERIES_STREAM = "deliveries"
_STREAM_MAXLEN = 1_000_000

MOVE_DUE_SCRIPT = """
local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, tonumber(ARGV[2]))
for _, member in ipairs(due) do
  redis.call('ZREM', KEYS[1], member)
  redis.call('XADD', KEYS[2], 'MAXLEN', '~', ARGV[3], '*', 'job', member)
end
return #due
"""


def backoff_ms(attempt: int, initial_ms: int, max_ms: int) -> int:
    """Exponential backoff with full jitter for the `attempt`-th failure (1-based)."""
    ceiling = min(max_ms, initial_ms * 2 ** max(attempt - 1, 0))
    return random.randint(max(ceiling // 2, 1), max(ceiling, 1))


async def schedule_retry(redis: Redis, job: DeliveryJob, due_ms: int) -> None:
    """Park the job until `due_ms`; the member is the job JSON (unique per attempt)."""
    await redis.zadd(RETRIES_KEY, {job.model_dump_json(): due_ms})


async def move_due_retries(redis: Redis, script: AsyncScript, batch_size: int = 500) -> int:
    return int(
        await script(
            keys=[RETRIES_KEY, DELIVERIES_STREAM],
            args=[int(time.time() * 1000), batch_size, _STREAM_MAXLEN],
        )
    )


async def run_retry_poller(
    redis: Redis, stop: asyncio.Event, interval_seconds: float = 0.5
) -> None:
    """Move due retries back to the stream until stopped; again at once after a full batch."""
    script = redis.register_script(MOVE_DUE_SCRIPT)
    while not stop.is_set():
        moved = 0
        try:
            moved = await move_due_retries(redis, script)
        except RedisError:
            log.exception("delivery_retry_poll_failed")
        if moved >= 500:
            continue
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
