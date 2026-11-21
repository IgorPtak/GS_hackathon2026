"""GET /api/v1/channels/health: circuit breaker state and unfinished deliveries per channel."""

from datetime import UTC, datetime

import asyncpg
from alerting_contracts.api import ChannelHealth, CircuitState
from alerting_contracts.config import ChannelConfig
from alerting_core.logging import get_logger
from fastapi import APIRouter, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from ..dependencies import ConfigSourceDep, RedisDep

log = get_logger(__name__)
router = APIRouter(tags=["ops"])

# Same definition of "not finished" as the deliveries_unfinished_idx partial index (track A).
UNFINISHED_SQL = """
SELECT channel_id, count(*) FROM deliveries
WHERE status = ANY (ARRAY['pending', 'sent', 'failed'])
GROUP BY channel_id
"""


def circuit_key(channel_id: str) -> str:
    """Redis key of a channel's breaker, as written by the delivery service (storage.md)."""
    return f"circuit:{channel_id}"


def parse_circuit(raw: dict[str, str]) -> tuple[CircuitState, int, datetime | None]:
    """Read-only view of the breaker hash; unknown or missing values mean a closed circuit."""
    try:
        state = CircuitState(raw.get("state", "closed"))
    except ValueError:
        state = CircuitState.closed
    try:
        failures = max(0, int(raw.get("failures", "0")))
    except ValueError:
        failures = 0
    opened_at: datetime | None = None
    if state is not CircuitState.closed:
        try:
            opened_at = datetime.fromtimestamp(int(raw["opened_at"]) / 1000, tz=UTC)
        except (KeyError, ValueError, OverflowError):
            opened_at = None
    return state, failures, opened_at


async def read_circuits(
    redis: Redis, channels: list[ChannelConfig]
) -> dict[str, tuple[CircuitState, int, datetime | None]]:
    """All breaker hashes in one pipeline; Redis being down reads as "no circuit recorded"."""
    try:
        async with redis.pipeline(transaction=False) as pipe:
            for channel in channels:
                pipe.hgetall(circuit_key(channel.id))
            results = await pipe.execute()
    except (RedisError, OSError) as error:
        log.warning("channel_health_redis_unavailable", extra={"error": str(error)})
        results = [{} for _ in channels]
    circuits = {}
    for channel, raw in zip(channels, results, strict=True):
        decoded = {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in (raw or {}).items()
        }
        circuits[channel.id] = parse_circuit(decoded)
    return circuits


async def count_unfinished(request: Request) -> dict[str, int]:
    """Unfinished deliveries per channel; empty with a warning while Postgres is unreachable."""
    try:
        pool = request.app.state.pool
        if pool is None:
            connect = getattr(request.app.state, "connect_database", None)
            pool = await connect() if connect is not None else None
        if pool is None:
            return {}
        async with pool.acquire() as connection:
            rows = await connection.fetch(UNFINISHED_SQL)
        return {row[0]: int(row[1]) for row in rows}
    except (asyncpg.PostgresError, OSError) as error:
        log.warning("channel_health_database_unavailable", extra={"error": str(error)})
        return {}


@router.get("/api/v1/channels/health")
async def get_channel_health(
    request: Request, redis: RedisDep, config_source: ConfigSourceDep
) -> list[ChannelHealth]:
    """Every configured channel with its breaker state and how many deliveries wait for it."""
    channels = sorted(config_source.get_config_lists().channels, key=lambda c: c.id)
    circuits = await read_circuits(redis, channels)
    waiting = await count_unfinished(request)
    return [
        ChannelHealth(
            channel_id=channel.id,
            channel_type=channel.type,
            state=circuits[channel.id][0],
            failures=circuits[channel.id][1],
            opened_at=circuits[channel.id][2],
            waiting_deliveries=waiting.get(channel.id, 0),
        )
        for channel in channels
    ]
