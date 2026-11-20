"""FastAPI dependencies; tests replace them with app.dependency_overrides."""

from typing import Annotated

import asyncpg
from alerting_core.config import ConfigRegistry
from fastapi import Depends, HTTPException, Request
from redis.asyncio import Redis

from .config_source import ConfigSource


def get_redis(request: Request) -> Redis:
    """The shared Redis client."""
    return request.app.state.redis


async def get_pool(request: Request) -> asyncpg.Pool:
    """The Postgres pool; reconnects lazily, 503 while the database is unreachable."""
    pool = request.app.state.pool
    if pool is None:
        connect = getattr(request.app.state, "connect_database", None)
        pool = await connect() if connect is not None else None
    if pool is None:
        raise HTTPException(503, "database unavailable")
    return pool


def get_config_source(request: Request) -> ConfigSource:
    """RegistryConfigSource, or DirectoryConfigSource when Postgres was down at startup."""
    return request.app.state.config_source


def get_registry(request: Request) -> ConfigRegistry | None:
    """The ConfigRegistry, or None when Postgres was down at startup."""
    return request.app.state.registry


RedisDep = Annotated[Redis, Depends(get_redis)]
PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]
ConfigSourceDep = Annotated[ConfigSource, Depends(get_config_source)]
RegistryDep = Annotated[ConfigRegistry | None, Depends(get_registry)]
