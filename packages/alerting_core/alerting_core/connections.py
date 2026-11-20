"""Factories for the Postgres pool and the Redis client shared by every service."""

import asyncpg
import orjson
from redis.asyncio import Redis

from .settings import Settings


async def _init_connection(connection: asyncpg.Connection) -> None:
    # jsonb columns hold contract models; decode them straight to dicts with orjson.
    await connection.set_type_codec(
        "jsonb",
        encoder=lambda value: orjson.dumps(value).decode(),
        decoder=orjson.loads,
        schema="pg_catalog",
    )
    await connection.set_type_codec(
        "json",
        encoder=lambda value: orjson.dumps(value).decode(),
        decoder=orjson.loads,
        schema="pg_catalog",
    )


async def create_database_pool(settings: Settings) -> asyncpg.Pool:
    """Create the asyncpg pool with jsonb <-> Python codecs installed on every connection."""
    return await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=settings.database_pool_min_size,
        max_size=settings.database_pool_max_size,
        init=_init_connection,
    )


def create_redis_client(settings: Settings) -> Redis:
    """Create the async Redis client. Responses stay bytes: stream payloads are orjson bytes."""
    return Redis.from_url(settings.redis_url, decode_responses=False, health_check_interval=30)
