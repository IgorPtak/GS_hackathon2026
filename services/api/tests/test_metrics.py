"""Metrics summary: Prometheus mocked with respx, Postgres faked."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.api.routers.metrics import QUERIES, router

PROM = "http://prom.test:9090"


class FakeConnection:
    async def fetchval(self, query: str) -> int:
        assert "status = 'open'" in query
        return 7


class FakePool:
    @asynccontextmanager
    async def acquire(self):
        yield FakeConnection()


def make_client(pool: object | None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.pool = pool
    app.state.settings = SimpleNamespace(prometheus_url=PROM)
    return TestClient(app)


def vector(value: str) -> dict:
    return {
        "status": "success",
        "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1, value]}]},
    }


EMPTY = {"status": "success", "data": {"resultType": "vector", "result": []}}


@respx.mock
def test_all_fields_filled() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]
        if "lag" in query:
            return httpx.Response(200, json=vector("12.4"))
        if query == QUERIES["retries_total"]:
            return httpx.Response(200, json=vector("3"))
        return httpx.Response(200, json=vector("0.25"))

    respx.get(f"{PROM}/api/v1/query").mock(side_effect=answer)
    body = make_client(FakePool()).get("/api/v1/metrics/summary").json()
    assert body["ingest_rate_per_second"] == 0.25
    assert body["events_stream_lag"] == 12
    assert body["deliveries_stream_lag"] == 12
    assert body["retries_total"] == 3
    assert body["e2e_latency_p99_seconds"] == 0.25
    assert body["open_alert_count"] == 7
    assert all(value is not None for value in body.values())


@respx.mock
def test_empty_results_give_nulls() -> None:
    respx.get(f"{PROM}/api/v1/query").mock(return_value=httpx.Response(200, json=EMPTY))
    response = make_client(FakePool()).get("/api/v1/metrics/summary")
    body = response.json()
    assert response.status_code == 200
    assert body["ingest_rate_per_second"] is None
    assert body["dead_lettered_total"] is None
    assert body["open_alert_count"] == 7


@respx.mock
@pytest.mark.parametrize("failure", ["connect", "status", "garbage"])
def test_prometheus_down_gives_nulls(failure: str) -> None:
    route = respx.get(f"{PROM}/api/v1/query")
    if failure == "connect":
        route.mock(side_effect=httpx.ConnectError("down"))
    elif failure == "status":
        route.mock(return_value=httpx.Response(500))
    else:
        route.mock(return_value=httpx.Response(200, text="not json"))
    response = make_client(FakePool()).get("/api/v1/metrics/summary")
    assert response.status_code == 200
    body = response.json()
    assert all(body[field] is None for field in QUERIES)


@respx.mock
def test_nan_and_inf_give_null() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        nan = "histogram_quantile" in request.url.params["query"]
        return httpx.Response(200, json=vector("NaN" if nan else "+Inf"))

    respx.get(f"{PROM}/api/v1/query").mock(side_effect=answer)
    body = make_client(FakePool()).get("/api/v1/metrics/summary").json()
    assert all(body[field] is None for field in QUERIES)


@respx.mock
def test_pool_absent_gives_zero_open_alerts() -> None:
    respx.get(f"{PROM}/api/v1/query").mock(return_value=httpx.Response(200, json=vector("1")))
    response = make_client(None).get("/api/v1/metrics/summary")
    assert response.status_code == 200
    assert response.json()["open_alert_count"] == 0
