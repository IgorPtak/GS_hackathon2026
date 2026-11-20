import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from alerting_contracts.common import Severity
from alerting_contracts.config import SchemaProfile
from alerting_contracts.events import EventEnvelope, SourceType
from alerting_core.events import (
    ProfileMatcher,
    compute_fingerprint,
    is_unknown_shape,
    key_paths,
    normalize_event,
    select_schema_profile,
    shape_hash,
)
from alerting_core.events.normalize import parse_timestamp

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "contracts" / "fixtures" / "events"


def _load_profiles() -> list[SchemaProfile]:
    return [
        SchemaProfile.model_validate(yaml.safe_load(p.read_text()))
        for p in sorted((ROOT / "config" / "schemas").glob("*.yaml"))
    ]


PROFILES = _load_profiles()
MATCHER = ProfileMatcher(PROFILES)


def _envelope(payload: dict[str, Any]) -> EventEnvelope:
    return EventEnvelope(
        event_id="01J0000000000000000000000A",
        source_id="test",
        source_type=SourceType.webhook,
        received_at=datetime(2026, 11, 20, tzinfo=UTC),
        payload=payload,
    )


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def _alertmanager(name: str) -> dict[str, Any]:
    # Ingest splits the batch; each alert is one event.
    return _fixture(name)["alerts"][0]


CASES = [
    ("pricing_price_stale.json", None, "pricing-log", "pricing.log", Severity.error, "EURUSD"),
    (
        "rates_trade_rejected.json",
        None,
        "trade-rejected",
        "trade.rejected.v1",
        Severity.error,
        "T-20261120-000417",
    ),
    (
        "settlements_workflow_failed.json",
        None,
        "workflow-failed",
        "WORKFLOW_FAILED",
        Severity.critical,
        "wf-settle-20261120-0042",
    ),
    (
        "alertmanager_firing.json",
        "am",
        "alertmanager",
        "ExporterDown",
        Severity.critical,
        "exporter:9100",
    ),
    ("unknown_payments.json", None, "generic", "unknown", Severity.warning, None),
]


@pytest.mark.parametrize(("name", "kind", "profile_id", "type_", "severity", "entity"), CASES)
def test_fixture_is_mapped(name, kind, profile_id, type_, severity, entity):
    payload = _alertmanager(name) if kind == "am" else _fixture(name)
    profile = select_schema_profile(payload, PROFILES)
    assert profile.id == profile_id
    normalized = normalize_event(_envelope(payload), profile)
    assert (normalized.type, normalized.severity, normalized.entity) == (type_, severity, entity)
    assert normalized.occurred_at is not None
    assert len(normalized.fingerprint) == 64
    assert normalized.is_resolution is False


def test_unknown_payments_is_generic_and_unknown_shape():
    payload = _fixture("unknown_payments.json")
    assert select_schema_profile(payload, PROFILES).id == "generic"
    assert is_unknown_shape(payload, PROFILES) is True
    assert is_unknown_shape(_fixture("rates_trade_rejected.json"), MATCHER) is False


def test_generic_heuristics_fill_severity_and_time():
    normalized = normalize_event(
        _envelope(_fixture("unknown_payments.json")),
        MATCHER.select(_fixture("unknown_payments.json")),
    )
    assert normalized.source == "generic-webhook"
    assert normalized.severity is Severity.warning
    assert normalized.occurred_at == datetime(2026, 11, 20, 9, 30, tzinfo=UTC)


def test_generic_heuristics_nested_label_and_epoch():
    payload = {"labels": {"severity": "CRIT"}, "ts": 1795168502}
    normalized = normalize_event(_envelope(payload), MATCHER.select(payload))
    assert normalized.schema_profile_id == "generic"
    assert normalized.severity is Severity.critical
    assert normalized.occurred_at is not None and normalized.occurred_at.year == 2026


def test_no_match_returns_generic():
    payload = {"hello": "world"}
    assert select_schema_profile(payload, PROFILES).id == "generic"
    assert select_schema_profile(payload, []).id == "generic"
    assert is_unknown_shape(payload, PROFILES) is True


def test_highest_priority_wins():
    low = SchemaProfile.model_validate(
        {
            "id": "low",
            "priority": 1,
            "match": {"field": "a", "op": "exists"},
            "fields": {},
            "fingerprint": ["a"],
        }
    )
    high = low.model_copy(update={"id": "high", "priority": 5})
    assert select_schema_profile({"a": 1}, [low, high]).id == "high"


def test_resolution_detected():
    payload = _alertmanager("alertmanager_resolved.json")
    profile = select_schema_profile(payload, MATCHER)
    assert normalize_event(_envelope(payload), profile).is_resolution is True
    firing = _alertmanager("alertmanager_firing.json")
    assert (
        normalize_event(_envelope(firing), profile).fingerprint
        == normalize_event(_envelope(payload), profile).fingerprint
    )


def test_epoch_ms_and_value_map_case_insensitive():
    payload = _fixture("rates_trade_rejected.json")
    normalized = normalize_event(_envelope(payload), MATCHER.select(payload))
    assert normalized.occurred_at == datetime.fromtimestamp(1795168502.123, UTC)
    profile = SchemaProfile.model_validate(
        {
            "id": "p",
            "match": {"field": "s", "op": "exists"},
            "fields": {
                "severity": {"path": "s", "value_map": {"Crit": "critical"}, "default": "info"},
                "entity": "e.0.id",
                "type": {"path": "missing", "default": "fallback"},
            },
            "fingerprint": ["s"],
        }
    )
    got = normalize_event(_envelope({"s": "CRIT", "e": [{"id": 7}]}), profile)
    assert (got.severity, got.entity, got.type) == (Severity.critical, "7", "fallback")
    assert normalize_event(_envelope({"s": "bogus"}), profile).severity is Severity.info


def test_parse_timestamp_never_raises():
    assert parse_timestamp("not a date", "iso8601") is None
    assert parse_timestamp({"x": 1}, "epoch_ms") is None
    assert parse_timestamp(10**30, "epoch_s") is None
    assert parse_timestamp("1795168502", "epoch_s") is not None
    assert parse_timestamp("2026-11-20T10:00:00", "iso8601") == datetime(
        2026, 11, 20, 10, tzinfo=UTC
    )


def test_fingerprint_is_canonical_and_stable():
    a = {"x": {"b": 1, "a": 2}, "y": None}
    b = {"y": None, "x": {"a": 2, "b": 1}}
    assert compute_fingerprint(a, ["x", "y"]) == compute_fingerprint(b, ["x", "y"])
    assert compute_fingerprint(a, ["y"]) == compute_fingerprint({}, ["y"])  # missing == null
    assert compute_fingerprint(a, ["x", "y"]) != compute_fingerprint(a, ["y", "x"])


def test_shape_hash_and_key_paths():
    a = {"k": {"v": 1}, "l": [{"id": 1}, {"id": 2}]}
    b = {"l": [{"id": 9}], "k": {"v": "x"}}
    assert key_paths(a) == ["k", "k.v", "l", "l[].id"]
    assert shape_hash(a) == shape_hash(b)
    assert shape_hash(a) != shape_hash({"k": 1})


def test_benchmark_100k_selections_and_normalizations():
    envelopes = [
        _envelope(_alertmanager("alertmanager_firing.json")),
        *(
            _envelope(_fixture(n))
            for n in (
                "pricing_price_stale.json",
                "rates_trade_rejected.json",
                "settlements_workflow_failed.json",
                "unknown_payments.json",
            )
        ),
    ]
    start = time.perf_counter()
    for i in range(100_000):
        envelope = envelopes[i % len(envelopes)]
        profile, _ = MATCHER.select_with_flag(envelope.payload)
        MATCHER.normalize(envelope, profile)
    assert time.perf_counter() - start < 3.0


def test_fingerprint_canonicalizes_numbers_and_keys():
    assert compute_fingerprint({"n": 25000000}, ["n"]) == compute_fingerprint(
        {"n": 25000000.0}, ["n"]
    )
    assert compute_fingerprint({"n": 1.5}, ["n"]) != compute_fingerprint({"n": 1}, ["n"])
    assert compute_fingerprint({"n": True}, ["n"]) != compute_fingerprint({"n": 1}, ["n"])
    assert compute_fingerprint({"d": {"a": 1, "b": 2.0}}, ["d"]) == compute_fingerprint(
        {"d": {"b": 2, "a": 1}}, ["d"]
    )
    assert compute_fingerprint({"l": [1.0, True]}, ["l"]) == compute_fingerprint(
        {"l": [1, True]}, ["l"]
    )


def test_fingerprint_never_raises():
    assert len(compute_fingerprint({"n": 10**40}, ["n"])) == 64
    assert len(compute_fingerprint({"d": {1: "a", 2: "b"}}, ["d"])) == 64
    assert len(compute_fingerprint({"n": float("nan")}, ["n"])) == 64
    assert len(compute_fingerprint({"n": float("inf")}, ["n"])) == 64


def test_superscript_digit_is_not_a_list_index():
    assert compute_fingerprint({"a": ["x", "y"]}, ["a.\u00b2"]) == compute_fingerprint({}, ["z"])


def test_select_with_flag_single_pass():
    profile, unknown = MATCHER.select_with_flag(_fixture("unknown_payments.json"))
    assert (profile.id, unknown) == ("generic", True)
    profile, unknown = MATCHER.select_with_flag(_fixture("rates_trade_rejected.json"))
    assert (profile.id, unknown) == ("trade-rejected", False)


def test_high_priority_generic_still_known_when_specific_matches():
    generic = next(p for p in PROFILES if p.id == "generic").model_copy(update={"priority": 99})
    matcher = ProfileMatcher([generic, *(p for p in PROFILES if p.id != "generic")])
    payload = {"severity": "x", "eventType": "WORKFLOW_FAILED", "workflowId": "w"}
    profile, unknown = matcher.select_with_flag(payload)
    assert (profile.id, unknown) == ("generic", False)


def test_uncompilable_profile_is_skipped(caplog):
    bad = SchemaProfile.model_validate(
        {
            "id": "bad",
            "priority": 50,
            "match": {"field": "a", "op": "regex", "value": "("},
            "fields": {},
            "fingerprint": ["a"],
        }
    )
    matcher = ProfileMatcher([bad, *PROFILES])
    assert matcher.select({"a": "x"}).id != "bad"
    assert matcher.select(_fixture("rates_trade_rejected.json")).id == "trade-rejected"
