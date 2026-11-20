"""`deliveries-dlq` writes (fields `job`, `error`, `attempts`; contracts/storage.md)."""

from alerting_core.logging import get_logger
from redis.asyncio import Redis
from redis.exceptions import RedisError

log = get_logger(__name__)

DEAD_LETTER_STREAM = "deliveries-dlq"
_DEAD_LETTER_MAXLEN = 100_000


async def dead_letter_job(redis: Redis, job: bytes, error: str, attempts: int) -> None:
    """Best effort: the `deliveries` row (status dead_lettered) is the record of truth, and
    failing here would retry the job and queue its fallback twice."""
    try:
        await redis.xadd(
            DEAD_LETTER_STREAM,
            {"job": job, "error": error[:1000], "attempts": str(attempts)},
            maxlen=_DEAD_LETTER_MAXLEN,
            approximate=True,
        )
    except RedisError:
        log.exception("delivery_dead_letter_write_failed", extra={"error": error[:200]})
