"""Schema-profile routes, unknown-schema inbox and the heuristic proposal (fakes, no services)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from alerting_contracts.config import SchemaProfile
from alerting_core.events.compiled import compile_profile
from alerting_core.settings import Settings
from fastapi.testclient import TestClient

from services.api.dependencies import get_pool, get_redis
from services.api.main import create_app
from services.api.schema_proposal import propose_profile_heuristic

ROOT = Path(__file__).resolve().parents[3]
PAYMENTS = json.loads((ROOT / "contracts/fixtures/events/unknown_payments.json").read_text())
PROFILE = yaml.safe_load((ROOT / "config/schemas/trade-rejected.yaml").read_text())
ACTOR = {"id": "anna"}


class FakePool:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}
        self.unknown: list[dict[str, Any]] = []

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        if sql.lstrip().startswith("INSERT INTO config_documents"):
            kind, doc_id, team, document, text, actor = args
            old = self.rows.get((kind, doc_id))
            version = old["version"] + 1 if old else 1
            self.rows[(kind, doc_id)] = {
                "id": doc_id, "team": team, "document": document, "yaml": text,
                "version": version, "updated_at": datetime.now(UTC), "updated_by": actor,
            }  # fmt: skip
            return {"version": version}
        return self.rows.get(("schema_profile", args[0]))

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        if "unknown_schema_samples" in sql:
            return sorted(self.unknown, key=lambda r: r["last_seen"], reverse=True)
        return [r for (k, _), r in sorted(self.rows.items()) if k == "schema_profile"]


class SpyRedis:
    READS = {"xrange"}

    def __init__(self, entries: list[tuple[str, dict[str, str]]]) -> None:
        self.entries = entries
        self.calls: list[str] = []
        self.published: list[tuple[str, str]] = []

    async def xrange(self, name: str, min: str, max: str, count: int) -> list[Any]:  # noqa: A002
        self.calls.append("xrange")
        return self.entries

    async def publish(self, channel: str, payload: str) -> None:
        self.published.append((channel, payload))

    def __getattr__(self, name: str) -> Any:
        async def forbidden(*_: Any, **__: Any) -> None:
            self.calls.append(name)
            raise AssertionError(f"unexpected redis command {name}")

        return forbidden


def _entry(i: int, payload: dict[str, Any]) -> tuple[str, dict[str, str]]:
    envelope = {
        "event_id": f"01H{i:023d}",
        "source_id": "generic-webhook",
        "source_type": "webhook",
        "received_at": (datetime.now(UTC) - timedelta(minutes=10 - i)).isoformat(),
        "payload": payload,
    }
    return f"{i}-0", {"envelope": json.dumps(envelope)}


def make(redis: SpyRedis | None = None) -> tuple[TestClient, FakePool, SpyRedis]:
    app = create_app(
        Settings(config_dir=str(ROOT / "config"), database_url="postgresql://x@127.0.0.1:1/x")
    )
    pool, redis = FakePool(), redis or SpyRedis([])
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_redis] = lambda: redis
    return TestClient(app), pool, redis


def test_heuristic_on_payments_sample_is_deterministic_and_valid() -> None:
    first = propose_profile_heuristic(PAYMENTS)
    assert first == propose_profile_heuristic(PAYMENTS)
    assert first.generated_by == "heuristic" and first.model is None and first.notes
    profile = first.profile
    SchemaProfile.model_validate(profile.model_dump(mode="json"))
    fields = profile.fields.model_dump(exclude_none=True)
    assert fields["type"] == "evt" and fields["source"] == "svc"
    assert fields["severity"]["path"] == "lvl"
    assert fields["occurred_at"] == {"path": "at", "format": "iso8601", "value_map": {}}
    assert fields["entity"] == "data.paymentId"
    assert profile.fingerprint == ["evt", "svc"]
    assert compile_profile(profile).match(PAYMENTS)


def test_severity_value_map_and_explicit_id() -> None:
    mapping = propose_profile_heuristic(PAYMENTS, "payments-v1").profile.fields.severity
    assert mapping is not None and not isinstance(mapping, str)
    assert mapping.value_map["warn"] == "warning" and mapping.value_map["fatal"] == "critical"
    assert mapping.value_map["err"] == "error" and mapping.value_map["ok"] == "info"
    numeric = propose_profile_heuristic({"level": 3, "foo": {"bar": 1}}).profile.fields.severity
    assert numeric is not None and not isinstance(numeric, str) and not numeric.value_map


def test_propose_endpoint() -> None:
    client, _, _ = make()
    with client:
        r = client.post("/api/v1/schema-profiles/propose", json={"sample_event": PAYMENTS})
        bad = client.post("/api/v1/schema-profiles/propose", json={"profile_id": "x"})
    assert r.status_code == 200 and r.json()["generated_by"] == "heuristic"
    assert bad.status_code == 422 and bad.json()["details"][0]["path"] == "sample_event"


def test_put_list_and_version_bump() -> None:
    client, _, redis = make()
    with client:
        r = client.put(
            "/api/v1/schema-profiles/trade-rejected",
            json={"schema_profile": PROFILE, "actor": ACTOR},
        )
        assert r.status_code == 200, r.text
        assert r.json()["kind"] == "schema_profile" and r.json()["version"] == 1
        r2 = client.put(
            "/api/v1/schema-profiles/trade-rejected",
            json={"schema_profile": {**PROFILE, "description": "x"}, "actor": ACTOR},
        )
        assert r2.json()["version"] == 2
        listed = client.get("/api/v1/schema-profiles").json()
    assert [p["id"] for p in listed] == ["trade-rejected"]
    assert listed[0]["schema_profile"]["fingerprint"] == PROFILE["fingerprint"]
    assert "config.changed" in {c for c, _ in redis.published}


def test_put_validation_errors() -> None:
    client, pool, _ = make()
    with client:
        mismatch = client.put(
            "/api/v1/schema-profiles/other", json={"schema_profile": PROFILE, "actor": ACTOR}
        )
        bad = {**PROFILE, "match": {"field": "a", "op": "bogus", "value": 1}}
        invalid = client.put(
            "/api/v1/schema-profiles/trade-rejected", json={"schema_profile": bad, "actor": ACTOR}
        )
        empty_fp = client.put(
            "/api/v1/schema-profiles/trade-rejected",
            json={"schema_profile": {**PROFILE, "fingerprint": []}, "actor": ACTOR},
        )
    assert mismatch.status_code == 422
    assert mismatch.json()["details"][0]["path"] == "schema_profile.id"
    assert invalid.status_code == 422 and invalid.json()["error"] == "validation_failed"
    assert any(d["path"].startswith("schema_profile.match") for d in invalid.json()["details"])
    assert empty_fp.json()["details"][0]["path"] == "schema_profile.fingerprint"
    assert not pool.rows


def test_unknown_schemas_newest_first() -> None:
    client, pool, _ = make()
    now = datetime.now(UTC)
    for i, name in enumerate(["old", "new"]):
        pool.unknown.append(
            {
                "shape_hash": name, "source_id": "generic-webhook", "key_paths": ["a", "b"],
                "sample_event": json.dumps({"a": 1}), "event_count": 2,
                "first_seen": now - timedelta(hours=5), "last_seen": now - timedelta(hours=5 - i),
            }
        )  # fmt: skip
    with client:
        body = client.get("/api/v1/unknown-schemas").json()
    assert [s["shape_hash"] for s in body] == ["new", "old"]
    assert body[0]["key_paths"] == ["a", "b"] and body[0]["sample_event"] == {"a": 1}


def test_test_endpoint_counts_and_sample() -> None:
    proposal = propose_profile_heuristic(PAYMENTS).profile.model_dump(
        mode="json", exclude_none=True
    )
    other = {"meta": {"schema": "x"}, "foo": 1}
    redis = SpyRedis([_entry(1, PAYMENTS), _entry(2, other), _entry(3, PAYMENTS)])
    client, _, _ = make(redis)
    with client:
        r = client.post(
            "/api/v1/schema-profiles/test",
            json={"schema_profile": proposal, "window": "1h", "sample_event": PAYMENTS},
        )
        none = client.post("/api/v1/schema-profiles/test", json={"schema_profile": proposal})
    body = r.json()
    assert r.status_code == 200, r.text
    assert (body["events_scanned"], body["events_matched"]) == (3, 2)
    assert body["samples"][0]["event_id"] is None and len(body["samples"]) == 3
    norm = body["samples"][1]["normalized"]
    assert norm["type"] == "payment.declined" and norm["severity"] == "warning"
    assert norm["entity"] == "P-99812" and norm["schema_profile_id"] == proposal["id"]
    assert none.json()["samples"][0]["event_id"] == "01H" + "1".zfill(23)


def test_test_endpoint_caps_samples_and_is_read_only() -> None:
    proposal = propose_profile_heuristic(PAYMENTS).profile.model_dump(
        mode="json", exclude_none=True
    )
    redis = SpyRedis([_entry(i, PAYMENTS) for i in range(1, 31)])
    client, pool, _ = make(redis)
    with client:
        r = client.post("/api/v1/schema-profiles/test", json={"schema_profile": proposal})
    body = r.json()
    assert body["events_matched"] == 30 and len(body["samples"]) == 20
    assert redis.calls and set(redis.calls) <= SpyRedis.READS
    assert not pool.rows


def test_test_endpoint_invalid_is_422() -> None:
    client, _, _ = make()
    with client:
        missing = client.post("/api/v1/schema-profiles/test", json={})
        regex = client.post(
            "/api/v1/schema-profiles/test",
            json={
                "schema_profile": {**PROFILE, "match": {"field": "a", "op": "regex", "value": "("}}
            },
        )
    assert missing.status_code == 422 and missing.json()["details"][0]["path"] == "schema_profile"
    assert regex.status_code == 422 and regex.json()["details"][0]["path"] == "schema_profile.match"


# ---------------------------------------------------------------- LLM proposal (B-21)

LLM_PROFILE = {
    "id": "payments-llm",
    "description": "Payments declines",
    "priority": 5,
    "match": {"all": [{"field": "evt", "op": "exists", "value": True}]},
    "fields": {
        "type": "evt",
        "source": "svc",
        "severity": {"path": "lvl", "value_map": {"WARN": "warning"}},
        "occurred_at": {"path": "at", "format": "iso8601"},
        "entity": "data.paymentId",
    },
    "fingerprint": ["evt", "data.paymentId"],
}


class FakeLlm:
    """Duck-typed LlmClient: records prompts, returns a canned answer or raises."""

    model = "fake-model"

    def __init__(self, profile: dict[str, Any] | None = None, error: Exception | None = None):
        self.profile, self.error, self.prompts = profile, error, []

    async def generate(self, prompt: str, response_model: Any, *, system: str | None = None):
        self.prompts.append(prompt + (system or ""))
        if self.error is not None:
            raise self.error
        return response_model.model_validate({"profile": self.profile, "notes": ["ok"]})


def _propose(llm: Any, sample: dict[str, Any] | None = None) -> dict[str, Any]:
    client, _, _ = make()
    with client:
        client.app.state.llm = llm  # type: ignore[attr-defined]
        r = client.post(
            "/api/v1/schema-profiles/propose", json={"sample_event": sample or PAYMENTS}
        )
    assert r.status_code == 200, r.text
    return r.json()


def test_llm_proposal_is_used_and_validated() -> None:
    fake = FakeLlm(LLM_PROFILE)
    body = _propose(fake)
    assert body["generated_by"] == "llm" and body["model"] == "fake-model"
    assert body["profile"]["id"] == "payments-llm" and body["notes"] == ["ok"]
    SchemaProfile.model_validate(body["profile"])
    assert "Heuristic proposal" in fake.prompts[0] and "Existing profile ids" in fake.prompts[0]


def test_llm_unavailable_falls_back_to_heuristic() -> None:
    from alerting_core.llm import LlmUnavailableError

    assert _propose(FakeLlm(error=LlmUnavailableError("down")))["generated_by"] == "heuristic"
    assert _propose(None)["generated_by"] == "heuristic"


def test_llm_invalid_output_falls_back_to_heuristic() -> None:
    from alerting_core.llm import LlmOutputInvalidError

    assert _propose(FakeLlm(error=LlmOutputInvalidError("bad")))["generated_by"] == "heuristic"
    # schema-valid but the profile does not match the sample
    nomatch = {**LLM_PROFILE, "match": {"field": "evt", "op": "eq", "value": "other"}}
    assert _propose(FakeLlm(nomatch))["generated_by"] == "heuristic"


def test_llm_nonexistent_mapping_path_is_dropped() -> None:
    profile = {**LLM_PROFILE, "fields": {**LLM_PROFILE["fields"], "entity": "data.missing"}}
    body = _propose(FakeLlm(profile))
    assert body["generated_by"] == "llm" and body["profile"]["fields"].get("entity") is None
    assert any("entity" in n for n in body["notes"])
    # a match path that is absent cannot be repaired
    bad = {**LLM_PROFILE, "match": {"field": "nope", "op": "exists", "value": True}}
    assert _propose(FakeLlm(bad))["generated_by"] == "heuristic"


def test_llm_prompt_redacts_secret_values() -> None:
    sample = {**PAYMENTS, "api_token": "sk-live-9f8e7d6c5b4a3210", "password": "hunter2hunter2"}
    fake = FakeLlm(LLM_PROFILE)
    _propose(fake, sample)
    assert fake.prompts
    assert "sk-live-9f8e7d6c5b4a3210" not in fake.prompts[0]
    assert "hunter2hunter2" not in fake.prompts[0]


def test_llm_existing_profile_ids_reach_prompt_and_avoid_collision() -> None:
    class Registry:
        async def stop(self) -> None:
            return None

        def schema_profiles(self) -> dict[str, Any]:
            return {"payments-llm": object(), "trade-rejected": object()}

    fake = FakeLlm(LLM_PROFILE)
    client, _, _ = make()
    with client:
        client.app.state.llm = fake  # type: ignore[attr-defined]
        client.app.state.registry = Registry()  # type: ignore[attr-defined]
        r = client.post("/api/v1/schema-profiles/propose", json={"sample_event": PAYMENTS})
    assert r.json()["generated_by"] == "llm" and r.json()["profile"]["id"] == "payments-llm-2"
    assert "payments-llm, trade-rejected" in fake.prompts[0]
