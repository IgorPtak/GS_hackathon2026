"""Ingest endpoint tests against a real Redis (DB 15, flushed per test)."""

import statistics
import time
from collections.abc import Iterator
from pathlib import Path

import orjson
import pytest
import redis
import yaml
from alerting_contracts.config import SourceConfig
from alerting_contracts.events import SourceType
from alerting_core.settings import Settings
from fastapi.testclient import TestClient
from ulid import ULID

from plugins.sources import HttpSourcePlugin, get_source_plugin, register_source_plugin
from services.ingest.main import create_app
from services.ingest.sources import load_sources

REDIS_URL = "redis://localhost:6379/15"
EXAMPLES = Path(__file__).resolve().parents[3] / "contracts" / "examples" / "sources"


@pytest.fixture
def sync_redis() -> Iterator[redis.Redis]:
    client = redis.Redis.from_url(REDIS_URL)
    try:
        client.flushdb()
    except redis.ConnectionError:
        pytest.skip("Redis not reachable on localhost:6379")
    yield client
    client.flushdb()
    client.close()


@pytest.fixture
def config_dir(tmp_path: Path) -> str:
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "rates-oms.yaml").write_text((EXAMPLES / "rates-oms.yaml").read_text())
    (sources / "pricing-log.yaml").write_text((EXAMPLES / "pricing-log.yaml").read_text())
    (sources / "keyed.yaml").write_text(
        yaml.safe_dump(
            {"id": "keyed", "type": "webhook", "settings": {"idempotency_key_path": "order.id"}}
        )
    )
    (sources / "off.yaml").write_text(
        yaml.safe_dump({"id": "off", "type": "webhook", "enabled": False})
    )
    return str(tmp_path)


@pytest.fixture
def client(sync_redis: redis.Redis, config_dir: str) -> Iterator[TestClient]:
    with TestClient(
        create_app(Settings(redis_url=REDIS_URL, config_dir=config_dir))
    ) as test_client:
        yield test_client


def entries(sync_redis: redis.Redis) -> list[dict]:
    return [orjson.loads(f[b"envelope"]) for _, f in sync_redis.xrange("events")]


def test_accepts_event_and_appends_envelope(client: TestClient, sync_redis: redis.Redis) -> None:
    response = client.post("/api/v1/ingest/rates-oms", json={"a": 1})
    assert response.status_code == 202
    body = response.json()
    assert body["duplicate_count"] == 0
    assert sync_redis.xlen("events") == 1
    envelope = entries(sync_redis)[0]
    assert envelope["event_id"] == body["event_ids"][0]
    ULID.from_str(envelope["event_id"])
    assert envelope["payload"] == {"a": 1}
    assert envelope["source_type"] == "webhook"
    assert envelope["idempotency_key"] is None


def test_unknown_disabled_and_non_http_source_return_404(client: TestClient) -> None:
    for source_id in ("nope", "off", "pricing-log"):
        response = client.post(f"/api/v1/ingest/{source_id}", json={})
        assert response.status_code == 404
        assert response.json()["error"] == "not_found"


def test_non_json_body_returns_422(client: TestClient, sync_redis: redis.Redis) -> None:
    response = client.post("/api/v1/ingest/rates-oms", content=b"not json")
    assert response.status_code == 422
    assert response.json()["error"] == "validation_failed"
    assert client.post("/api/v1/ingest/rates-oms", json=[1]).status_code == 422
    assert client.post("/api/v1/ingest/rates-oms/batch", json={"a": 1}).status_code == 422
    assert sync_redis.xlen("events") == 0


def test_sent_at_header_is_mapped_and_invalid_is_422(
    client: TestClient, sync_redis: redis.Redis
) -> None:
    sent = "2026-01-01T10:00:00+00:00"
    assert (
        client.post("/api/v1/ingest/rates-oms", json={}, headers={"X-Sent-At": sent}).status_code
        == 202
    )
    assert entries(sync_redis)[0]["sent_at"].startswith("2026-01-01T10:00:00")
    bad = client.post("/api/v1/ingest/rates-oms", json={}, headers={"X-Sent-At": "yesterday"})
    assert bad.status_code == 422


def test_idempotency_key_header_duplicate_is_counted_not_added(
    client: TestClient, sync_redis: redis.Redis
) -> None:
    headers = {"Idempotency-Key": "k1"}
    first = client.post("/api/v1/ingest/rates-oms", json={"a": 1}, headers=headers)
    second = client.post("/api/v1/ingest/rates-oms", json={"a": 1}, headers=headers)
    assert first.json()["duplicate_count"] == 0
    assert second.status_code == 202
    assert second.json() == {"event_ids": [], "duplicate_count": 1}
    assert sync_redis.xlen("events") == 1
    assert 0 < sync_redis.ttl("ingest-idempotency:k1") <= 86400


def test_identical_payloads_without_key_all_reach_stream(
    client: TestClient, sync_redis: redis.Redis
) -> None:
    for _ in range(2):
        assert client.post("/api/v1/ingest/rates-oms", json={"a": 1}).status_code == 202
    assert sync_redis.xlen("events") == 2


def test_idempotency_key_path_is_used(client: TestClient, sync_redis: redis.Redis) -> None:
    payload = {"order": {"id": "o-7"}}
    client.post("/api/v1/ingest/keyed", json=payload)
    second = client.post("/api/v1/ingest/keyed", json=payload)
    assert second.json()["duplicate_count"] == 1
    assert sync_redis.xlen("events") == 1
    assert entries(sync_redis)[0]["idempotency_key"] == "o-7"
    # Path missing in the payload -> no key -> never deduplicated.
    client.post("/api/v1/ingest/keyed", json={})
    client.post("/api/v1/ingest/keyed", json={})
    assert sync_redis.xlen("events") == 3


def test_batch_appends_all_events_and_counts_duplicates(
    client: TestClient, sync_redis: redis.Redis
) -> None:
    response = client.post(
        "/api/v1/ingest/keyed/batch", json=[{"order": {"id": "b"}}, {"x": 1}, {"x": 1}]
    )
    assert response.status_code == 202
    assert len(response.json()["event_ids"]) == 3
    again = client.post("/api/v1/ingest/keyed/batch", json=[{"order": {"id": "b"}}, {"x": 2}])
    assert again.json()["duplicate_count"] == 1
    assert len(again.json()["event_ids"]) == 1
    assert sync_redis.xlen("events") == 4


def test_metrics_endpoint_exposes_counters(client: TestClient) -> None:
    client.post("/api/v1/ingest/rates-oms", json={})
    text = client.get("/metrics").text
    assert "ingest_events_total" in text
    assert "ingest_request_seconds" in text


@pytest.mark.slow  # wall-clock threshold: informational in CI
def test_p50_latency_note(client: TestClient) -> None:
    durations = []
    for _ in range(200):
        started = time.perf_counter()
        client.post("/api/v1/ingest/rates-oms", json={"a": 1})
        durations.append((time.perf_counter() - started) * 1000)
    p50 = statistics.median(durations)
    print(f"ingest p50 over 200 sequential requests: {p50:.2f} ms")
    assert p50 < 20  # loose in-process bound; the real target is < 5 ms


def test_redis_failure_returns_503_and_retry_lands(
    client: TestClient, sync_redis: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = {"Idempotency-Key": "retry-me"}
    with monkeypatch.context() as patch:

        async def broken_execute(self, *args, **kwargs):
            raise redis.exceptions.ConnectionError("down")

        patch.setattr(redis.asyncio.client.Pipeline, "execute", broken_execute)
        response = client.post("/api/v1/ingest/rates-oms", json={"a": 1}, headers=headers)
    assert response.status_code == 503
    assert response.json()["error"] == "unavailable"
    assert sync_redis.xlen("events") == 0
    retry = client.post("/api/v1/ingest/rates-oms", json={"a": 1}, headers=headers)
    assert retry.status_code == 202
    assert retry.json()["duplicate_count"] == 0
    assert sync_redis.xlen("events") == 1


class TwoPayloadSource(HttpSourcePlugin):
    def extract_payloads(self, body: dict, source: SourceConfig) -> list[dict]:
        return [{"n": 1}, {"n": 2}]


def test_header_key_with_several_payloads_is_suffixed(
    client: TestClient, sync_redis: redis.Redis, config_dir: str
) -> None:
    (Path(config_dir) / "sources" / "multi.yaml").write_text(
        yaml.safe_dump({"id": "multi", "type": "alertmanager"})
    )
    client.app.state.sources.update(load_sources(config_dir))
    previous = get_source_plugin(SourceType.alertmanager)
    register_source_plugin(SourceType.alertmanager, TwoPayloadSource())
    try:
        headers = {"Idempotency-Key": "am-1"}
        first = client.post("/api/v1/ingest/multi", json={}, headers=headers)
        assert len(first.json()["event_ids"]) == 2
        second = client.post("/api/v1/ingest/multi", json={}, headers=headers)
        assert second.json() == {"event_ids": [], "duplicate_count": 2}
    finally:
        if previous is not None:
            register_source_plugin(SourceType.alertmanager, previous)
    keys = sorted(envelope["idempotency_key"] for envelope in entries(sync_redis))
    assert keys == ["am-1:0", "am-1:1"]


def test_blank_idempotency_key_header_is_ignored(
    client: TestClient, sync_redis: redis.Redis
) -> None:
    for _ in range(2):
        client.post("/api/v1/ingest/rates-oms", json={}, headers={"Idempotency-Key": "  "})
    assert sync_redis.xlen("events") == 2
    assert entries(sync_redis)[0]["idempotency_key"] is None


def test_naive_sent_at_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ingest/rates-oms", json={}, headers={"X-Sent-At": "2026-01-01T10:00:00"}
    )
    assert response.status_code == 422
    assert "timezone" in response.json()["message"]


def test_invalid_envelope_returns_422_not_500(client: TestClient) -> None:
    # A source id that fails ConfigId validation cannot be built into an envelope.
    client.app.state.sources["Bad Id"] = SourceConfig.model_construct(
        id="Bad Id", type=SourceType.webhook, enabled=True, settings={}
    )
    response = client.post("/api/v1/ingest/Bad Id", json={})
    assert response.status_code == 422
    assert response.json()["error"] == "validation_failed"


def test_alertmanager_batch_is_split_and_resends_are_dropped(
    sync_redis: redis.Redis, tmp_path: Path
) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "alertmanager.yaml").write_text(
        yaml.safe_dump({"id": "alertmanager", "type": "alertmanager"})
    )
    alerts = [
        {"fingerprint": "a", "startsAt": "t0", "labels": {}},
        {"fingerprint": "b", "startsAt": "t0", "labels": {}},
    ]
    body = {"status": "firing", "receiver": "r", "alerts": alerts}
    resolved = {"status": "resolved", "alerts": [{**alerts[0], "status": "resolved"}]}
    app = create_app(Settings(redis_url=REDIS_URL, config_dir=str(tmp_path)))
    with TestClient(app) as test_client:
        first = test_client.post("/api/v1/ingest/alertmanager", json=body).json()
        again = test_client.post("/api/v1/ingest/alertmanager", json=body).json()
        test_client.post("/api/v1/ingest/alertmanager", json=resolved)
    assert len(first["event_ids"]) == 2
    assert again["duplicate_count"] == 2
    assert sync_redis.xlen("events") == 3
    assert entries(sync_redis)[0]["payload"]["status"] == "firing"
