"""Template rendering: placeholders, missing data, value formatting, presentation."""

import json
from pathlib import Path

import yaml
from alerting_contracts.config import Rule
from alerting_core.rules import build_context
from alerting_core.templating import render_presentation, render_template

ROOT = Path(__file__).resolve().parents[3]


def test_render_template_fills_whitespace_tolerant_placeholders() -> None:
    result = render_template("a {{x}} b {{  y.z }}!", {"x": 1, "y": {"z": "q"}})
    assert result.text == "a 1 b q!"
    assert result.missing_fields == []


def test_missing_placeholders_become_empty_and_are_listed() -> None:
    result = render_template("[{{a}}|{{b.c}}|{{a}}]", {})
    assert result.text == "[||]"
    assert result.missing_fields == ["a", "b.c", "a"]


def test_value_formatting() -> None:
    context = {"f": 25000000.0, "g": 1.5, "d": {"k": [1, "é"]}, "l": [1, 2], "t": True, "n": None}
    text = render_template("{{f}} {{g}} {{d}} {{l}} {{t}} [{{n}}]", context)
    assert text.text == '25000000 1.5 {"k":[1,"é"]} [1,2] true []'
    assert text.missing_fields == []


def test_template_without_placeholders_and_context_layers() -> None:
    assert render_template("plain", {}).text == "plain"
    context = build_context({"v": 1}, {"severity": "critical"}, {"id": "A1", "count": 3})
    result = render_template("{{normalized.severity}} {{alert.id}} x{{alert.count}} {{v}}", context)
    assert result.text == "critical A1 x3 1"


def test_real_rule_presentation_renders_expected_title() -> None:
    rule = Rule.model_validate(
        yaml.safe_load((ROOT / "config/rules/rates-large-rejections.yaml").read_text())
    )
    payload = json.loads((ROOT / "contracts/fixtures/events/rates_trade_rejected.json").read_text())
    title, body, fields = render_presentation(rule.present, build_context(payload, {}))
    assert title == "Rejected EUR 25000000 — LIMIT_BREACH"
    assert body == "Trade T-20261120-000417 for CPTY-0042 was rejected."
    assert [(f.path, f.value) for f in fields] == [
        ("payload.tradeId", "T-20261120-000417"),
        ("payload.desk", "rates"),
    ]


def test_presentation_missing_field_value_is_none() -> None:
    rule = Rule.model_validate(
        yaml.safe_load((ROOT / "config/rules/pricing-stale-feed.yaml").read_text())
    )
    title, _, fields = render_presentation(
        rule.present, build_context({"instrument": "EURUSD"}, {})
    )
    assert title == "Stale price EURUSD on "
    assert [(f.path, f.value) for f in fields] == [
        ("instrument", "EURUSD"),
        ("feed", None),
        ("age_ms", None),
    ]
