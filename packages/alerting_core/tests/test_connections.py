import pytest
from alerting_core.connections import create_database_pool, create_redis_client
from alerting_core.settings import Settings

pytestmark = pytest.mark.integration


async def test_redis_client_pings() -> None:
    redis = create_redis_client(Settings())
    try:
        assert await redis.ping()
    finally:
        await redis.aclose()


async def test_database_pool_round_trips_jsonb() -> None:
    pool = await create_database_pool(Settings())
    try:
        value = await pool.fetchval("select $1::jsonb", {"count": 2, "fields": ["a"]})
        assert value == {"count": 2, "fields": ["a"]}
    finally:
        await pool.close()
