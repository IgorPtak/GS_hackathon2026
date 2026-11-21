"""Channel health: breaker hashes from a fake Redis, unfinished deliveries from a fake pool."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from alerting_contracts.api import CircuitState, ConfigLists
from alerting_contracts.config import ChannelConfig, ChannelType
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from services.api.routers.channel_health import UNFINISHED_SQL, parse_circuit, router

CHANNELS = [
    ChannelConfig(id="sms", type=ChannelType.sms),
    ChannelConfig(id="email", type=ChannelType.email),
]


class FakePipeline:
    def __init__(self, hashes: dict[str, dict[bytes, bytes]], is_down: bool) -> None:
        self._hashes, self._is_down, self._keys = hashes, is_down, []

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def hgetall(self, key: str) -> None:
        self._keys.append(key)

    async def execute(self) -> list[dict[bytes, bytes]]:
        if self._is_down:
            raise RedisConnectionError("down")
        return [self._hashes.get(key, {}) for key in self._keys]


class FakeRedis:
    def __init__(self, hashes: dict[str, dict[bytes, bytes]], is_down: bool = False) -> None:
        self._hashes, self._is_down = hashes, is_down

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self._hashes, self._is_down)


class FakeConnection:
    async def fetch(self, query: str) -> list[tuple[str, int]]:
        assert query == UNFINISHED_SQL
        return [("sms", 5)]


class FakePool:
    @asynccontextmanager
    async def acquire(self) -> Any:
        yield FakeConnection()


class FakeConfigSource:
    def get_config_lists(self) -> ConfigLists:
        return ConfigLists(teams=[], recipients=[], channels=CHANNELS, actions=[], sources=[])


def make_client(redis: FakeRedis, pool: object | None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.redis = redis
    app.state.pool = pool
    app.state.config_source = FakeConfigSource()
    return TestClient(app)


OPENED_MS = 1_795_200_000_000


def test_open_sms_circuit_and_waiting_deliveries() -> None:
    redis = FakeRedis(
        {
            "circuit:sms": {
                b"state": b"open",
                b"failures": b"5",
                b"opened_at": str(OPENED_MS).encode(),
            }
        }
    )
    body = make_client(redis, FakePool()).get("/api/v1/channels/health").json()
    assert [item["channel_id"] for item in body] == ["email", "sms"]
    email, sms = body
    assert email == {
        "channel_id": "email",
        "channel_type": "email",
        "state": "closed",
        "failures": 0,
        "opened_at": None,
        "waiting_deliveries": 0,
    }
    assert sms["state"] == "open" and sms["failures"] == 5 and sms["waiting_deliveries"] == 5
    assert sms["opened_at"].startswith("2026-")


def test_redis_and_database_down_read_as_closed_and_zero() -> None:
    body = make_client(FakeRedis({}, is_down=True), None).get("/api/v1/channels/health").json()
    assert {item["state"] for item in body} == {"closed"}
    assert {item["waiting_deliveries"] for item in body} == {0}


def test_parse_circuit_tolerates_garbage() -> None:
    assert parse_circuit({"state": "weird", "failures": "x"}) == (CircuitState.closed, 0, None)
    state, failures, opened = parse_circuit(
        {"state": "half_open", "failures": "2", "opened_at": str(OPENED_MS)}
    )
    assert state is CircuitState.half_open and failures == 2
    assert opened == datetime.fromtimestamp(OPENED_MS / 1000, tz=UTC)
