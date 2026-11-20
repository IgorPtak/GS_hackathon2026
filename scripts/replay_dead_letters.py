"""Replay dead-lettered deliveries from `deliveries-dlq` back onto `deliveries`.

Usage: uv run python scripts/replay_dead_letters.py (--delivery-id N ... | --all) [--dry-run]
       [--redis-url redis://localhost:6379/0]

Each replayed job starts again at attempt 0. Delivery stays idempotent by delivery id
(`delivery-done:<id>`), so replaying a job that was already sent is a no-op; a dead-lettered
row becomes `delivered` when the replay succeeds. Its fallback, if any, was already queued.
The entry is removed from the DLQ only after the job is back on `deliveries`.
"""

import argparse
import asyncio
import sys

from alerting_contracts.alerts import DeliveryJob
from pydantic import ValidationError
from redis.asyncio import Redis

DEAD_LETTER_STREAM = "deliveries-dlq"
DELIVERIES_STREAM = "deliveries"
_PAGE = 500


async def replay(redis: Redis, delivery_ids: set[int] | None, is_dry_run: bool) -> int:
    """Move matching DLQ entries back to `deliveries`; returns how many were replayed."""
    replayed = 0
    cursor = "-"
    while True:
        entries = await redis.xrange(DEAD_LETTER_STREAM, min=cursor, count=_PAGE)
        if cursor != "-":
            entries = entries[1:]  # the cursor entry was handled on the previous page
        if not entries:
            return replayed
        for entry_id, fields in entries:
            try:
                job = DeliveryJob.model_validate_json(fields.get(b"job", b""))
            except ValidationError:
                continue  # garbage that never was a job: leave it for inspection
            if delivery_ids is not None and job.delivery_id not in delivery_ids:
                continue
            fresh = job.model_copy(update={"attempt": 0, "not_before": None})
            print(f"replay delivery {job.delivery_id} ({job.channel_id}): {fields.get(b'error')!r}")
            if not is_dry_run:
                await redis.xadd(DELIVERIES_STREAM, {"job": fresh.model_dump_json()})
                await redis.xdel(DEAD_LETTER_STREAM, entry_id)
            replayed += 1
        cursor = entries[-1][0].decode()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--delivery-id", type=int, action="append", dest="delivery_ids")
    target.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    args = parser.parse_args()
    redis = Redis.from_url(args.redis_url)
    try:
        ids = None if args.all else set(args.delivery_ids)
        count = await replay(redis, ids, args.dry_run)
    finally:
        await redis.aclose()
    print(f"{'would replay' if args.dry_run else 'replayed'} {count} job(s)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
