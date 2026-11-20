"""Result cache for LLM calls: a Protocol, an in-memory and a Redis implementation."""

import time
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from redis.asyncio import Redis


class LlmCache(Protocol):
    """Stores validated JSON strings by key."""

    async def get(self, key: str) -> str | None:
        """Return the cached value or None."""
        ...

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store a value for ttl_seconds."""
        ...


class InMemoryLlmCache:
    """Process-local cache with TTL, for tests and single-process use."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[float, str]] = {}

    async def get(self, key: str) -> str | None:
        """Return the cached value unless it expired."""
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at <= time.monotonic():
            del self._items[key]
            return None
        return value

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store a value for ttl_seconds."""
        self._items[key] = (time.monotonic() + ttl_seconds, value)


class RedisLlmCache:
    """Cache backed by an injected redis.asyncio-compatible client (decode_responses optional)."""

    def __init__(self, redis: "Redis") -> None:
        self._redis = redis

    async def get(self, key: str) -> str | None:
        """Return the cached value or None."""
        value = await self._redis.get(key)
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store a value for ttl_seconds."""
        await self._redis.set(key, value, ex=ttl_seconds)
