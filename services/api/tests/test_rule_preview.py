"""POST /api/v1/rules/preview with a fake Redis stream and the repository config snapshot."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml
from alerting_core.config import load_config_directory
from alerting_core.config.registry import ConfigSnapshot
from alerting_core.settings import Settings
from fastapi.testclient import TestClient

from services.api.dependencies import get_redis, get_registry
from services.api.main import create_app

ROOT = Path(__file__).resolve().parents[3]
RULE = yaml.safe_load((ROOT / "config/rules/rates-large-rejections.yaml").read_text())


def _snapshot() -> ConfigSnapshot:
    docs: dict[str, dict[str, Any]] = {}
    for doc in load_config_directory(ROOT / "config").documents:
        docs.setdefault(doc.kind, {})[doc.id] = doc.model
    return ConfigSnapshot(documents=docs)


class SpyRedis:
    """Serves `xrange` from memory and records every command; fails on anything but reads."""

    READS = {"xrange"}

    def __init__(self, entries: list[tuple[str, dict[str, str]]]) -> None:
        self.entries = entries
        self.calls: list[str] = []

    async def xrange(self, name: str, min: str, max: str, count: int) -> list[Any]:  # noqa: A002
        self.calls.append("xrange")
        return self.entries

    def __getattr__(self, name: str) -> Any:
        async def forbidden(*_: Any, **__: Any) -> None:
            self.calls.append(name)
            raise AssertionError(f"write/unknown redis command {name}")

        return forbidden


def _entry(i: int, notional: int) -> tuple[str, dict[str, str]]:
    envelope = {
        "event_id": f"01H{i:023d}",
        "source_id": "rates-oms",
        "source_type": "webhook",
        "received_at": (datetime.now(UTC) - timedelta(minutes=10 - i)).isoformat(),
        "payload": {
            "meta": {"schema": "trade.rejected.v1", "producer": "rates-oms", "ts": 1795168502123},
            "payload": {
                "tradeId": f"T-{i}",
                "desk": "rates",
                "reason": "LIMIT_BREACH",
                "currency": "EUR",
                "notional": notional,
                "counterparty": f"CPTY-{i}",
                "trader": "jdoe",
            },
        },
    }
    return f"{i}-0", {"envelope": json.dumps(envelope)}


def make(redis: SpyRedis, *, registry: bool = True) -> TestClient:
    app = create_app(
        Settings(config_dir=str(ROOT / "config"), database_url="postgresql://x@127.0.0.1:1/x")
    )
    app.dependency_overrides[get_redis] = lambda: redis
    snapshot = _snapshot()
    app.dependency_overrides[get_registry] = lambda: (
        SimpleNamespace(snapshot=snapshot) if registry else None
    )
    return TestClient(app)


def test_happy_path_counts_samples_and_deliveries() -> None:
    redis = SpyRedis([_entry(1, 25_000_000), _entry(2, 30_000_000), _entry(3, 5_000_000)])
    with make(redis) as client:
        r = client.post("/api/v1/rules/preview", json={"rule": RULE, "window": "1h"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["events_scanned"] == 3
    assert body["events_matched"] == 2
    assert 1 <= body["alerts_created"] <= 2  # same-fingerprint events share a dedup window
    assert sum(a["count"] for a in body["sample_alerts"]) == 2
    assert body["deliveries"] and all(d["count"] >= 1 for d in body["deliveries"])
    assert all(a["title"].startswith("Rejected EUR") for a in body["sample_alerts"])


def test_lower_threshold_changes_count() -> None:
    redis = SpyRedis([_entry(1, 25_000_000), _entry(2, 5_000_000)])
    draft = json.loads(json.dumps(RULE))
    draft["when"]["all"][2]["value"] = 1_000_000
    with make(redis) as client:
        base = client.post("/api/v1/rules/preview", json={"rule": RULE}).json()
        lowered = client.post("/api/v1/rules/preview", json={"rule": draft}).json()
    assert (base["events_matched"], lowered["events_matched"]) == (1, 2)


def test_invalid_rule_is_422_with_dot_paths() -> None:
    bad = {**RULE, "when": {"all": [{"field": "a", "op": "bogus", "value": 1}]}}
    with make(SpyRedis([])) as client:
        r = client.post("/api/v1/rules/preview", json={"rule": bad})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_failed"
    assert any(d["path"].startswith("rule.when.all.0") for d in body["details"])


def test_compile_error_is_422_pointing_at_when() -> None:
    bad = {**RULE, "when": {"all": [{"field": "payload.x", "op": "regex", "value": "("}]}}
    with make(SpyRedis([])) as client:
        r = client.post("/api/v1/rules/preview", json={"rule": bad})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_failed"
    assert body["details"][0]["path"] == "rule.when"


def test_registry_none_is_503() -> None:
    with make(SpyRedis([]), registry=False) as client:
        r = client.post("/api/v1/rules/preview", json={"rule": RULE})
    assert r.status_code == 503 and r.json()["error"] == "unavailable"


def test_preview_only_reads_redis() -> None:
    redis = SpyRedis([_entry(1, 25_000_000)])
    with make(redis) as client:
        r = client.post("/api/v1/rules/preview", json={"rule": RULE})
    assert r.status_code == 200
    assert redis.calls and set(redis.calls) <= SpyRedis.READS
