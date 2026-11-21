"""POST /api/v1/config/validate: dot paths for every kind."""

from pathlib import Path

import pytest
from alerting_core.settings import Settings
from fastapi.testclient import TestClient

from services.api.main import create_app

ROOT = Path(__file__).resolve().parents[3]


def validate(kind: str, text: str) -> dict:
    app = create_app(
        Settings(config_dir=str(ROOT / "config"), database_url="postgresql://x@127.0.0.1:1/x")
    )
    with TestClient(app) as client:
        r = client.post("/api/v1/config/validate", json={"kind": kind, "yaml": text})
    assert r.status_code == 200
    return r.json()


def test_valid_rule_returns_document() -> None:
    out = validate("rule", (ROOT / "config/rules/platform-alertmanager.yaml").read_text())
    assert out["is_valid"] is True and out["errors"] == []
    assert out["document"]["id"] == "platform-alertmanager"


def test_yaml_syntax_error_has_root_path() -> None:
    out = validate("rule", "id: [unclosed\n")
    assert out["is_valid"] is False
    assert len(out["errors"]) == 1 and out["errors"][0]["path"] == ""


def test_non_mapping_is_root_error() -> None:
    out = validate("rule", "- a\n- b\n")
    assert out["errors"][0]["path"] == ""


def test_rule_dot_path_for_bad_operator() -> None:
    text = (
        (ROOT / "config/rules/platform-alertmanager.yaml")
        .read_text()
        .replace("op: exists", "op: bogus")
    )
    out = validate("rule", text)
    assert out["is_valid"] is False
    assert any(e["path"].startswith("when.all.0") for e in out["errors"])
    assert out["document"] is None


def test_runbook_yaml_document() -> None:
    ok = validate(
        "runbook",
        "id: rb\ntitle: T\nsteps:\n  - index: 0\n    kind: text\n    text: hi\n",
    )
    bad = validate("runbook", "id: rb\ntitle: T\nsteps: []\n")
    assert bad["is_valid"] is False and bad["errors"][0]["path"] == "steps"
    assert ok["is_valid"] is True, ok


@pytest.mark.parametrize(
    "kind", ["schema_profile", "recipient", "team", "channel", "action", "source"]
)
def test_every_kind_reports_missing_fields(kind: str) -> None:
    out = validate(kind, "foo: 1\n")
    assert out["is_valid"] is False and out["errors"]
    assert all(e["path"] for e in out["errors"])


def test_invalid_regex_rule_fails_with_when_path() -> None:
    import yaml

    rule = yaml.safe_load((ROOT / "config/rules/platform-alertmanager.yaml").read_text())
    rule["when"] = {"all": [{"field": "a", "op": "regex", "value": "("}]}
    out = validate("rule", yaml.safe_dump(rule))
    assert out["is_valid"] is False
    assert out["errors"][0]["path"] == "when"
