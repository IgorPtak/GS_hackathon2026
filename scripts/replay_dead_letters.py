"""Replay dead-lettered deliveries from `deliveries-dlq` back onto `deliveries`.

Usage: uv run python scripts/replay_dead_letters.py (--delivery-id N ... | --all) [--dry-run]
       [--redis-url URL] [--database-url URL]

Each replayed job starts again at attempt 0. Delivery stays idempotent by delivery id
(`delivery-done:<id>`), so replaying a job that was already sent is a no-op; a dead-lettered
row becomes `delivered` when the replay succeeds. Its fallback, if any, was already queued and
is never queued again. The row's `created_at` is reset so the replay gets a fresh outage
budget (MAX_OUTAGE_SECONDS). The entry leaves the DLQ only after the job is on `deliveries`.
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass

import asyncpg
from alerting_contracts.alerts import DeliveryJob
from alerting_core.settings import Settings
from pydantic import ValidationError
from redis.asyncio import Redis

DEAD_LETTER_STREAM = "deliveries-dlq"
DELIVERIES_STREAM = "deliveries"
_PAGE = 500


@dataclass
class ReplayResult:
    replayed: int = 0
    skipped_invalid: int = 0


async def replay(
    redis: Redis, pool: asyncpg.Pool, delivery_ids: set[int] | None, is_dry_run: bool
) -> ReplayResult:
    """Move matching DLQ entries back to `deliveries`."""
    result = ReplayResult()
    cursor = "-"
    while entries := await redis.xrange(DEAD_LETTER_STREAM, min=cursor, count=_PAGE):
        for entry_id, fields in entries:
            try:
                job = DeliveryJob.model_validate_json(fields.get(b"job", b""))
            except ValidationError:
                result.skipped_invalid += 1  # never was a job: left for inspection
                continue
            if delivery_ids is not None and job.delivery_id not in delivery_ids:
                continue
            fresh = job.model_copy(update={"attempt": 0, "not_before": None})
            print(f"replay delivery {job.delivery_id} ({job.channel_id}): {fields.get(b'error')!r}")
            if not is_dry_run:
                await pool.execute(
                    "UPDATE deliveries SET created_at = now() WHERE id = $1", job.delivery_id
                )
                await redis.xadd(DELIVERIES_STREAM, {"job": fresh.model_dump_json()})
                await redis.xdel(DEAD_LETTER_STREAM, entry_id)
            result.replayed += 1
        # Exclusive: the last entry may have been deleted, so never re-read or skip past it.
        cursor = "(" + entries[-1][0].decode()
    return result


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--delivery-id", type=int, action="append", dest="delivery_ids")
    target.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--redis-url", default=Settings().redis_url)
    parser.add_argument("--database-url", default=Settings().database_url)
    args = parser.parse_args()
    redis = Redis.from_url(args.redis_url)
    pool = await asyncpg.create_pool(args.database_url, min_size=1, max_size=2)
    try:
        ids = None if args.all else set(args.delivery_ids)
        result = await replay(redis, pool, ids, args.dry_run)
    finally:
        await redis.aclose()
        await pool.close()
    verb = "would replay" if args.dry_run else "replayed"
    print(f"{verb} {result.replayed} job(s), skipped {result.skipped_invalid} invalid entr(ies)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
