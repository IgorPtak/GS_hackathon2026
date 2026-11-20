import pytest
from alerting_contracts.runbooks import RunbookFormat, StepKind
from alerting_core.runbooks.normalize import normalize_runbook
from pydantic import ValidationError


def read(config_dir, name):
    return (config_dir / "runbooks" / name).read_text()


def test_workflow_failed_yaml(config_dir, actions):
    rb = normalize_runbook(
        "workflow-failed",
        "Settlement workflow failed",
        "settlements",
        RunbookFormat.yaml,
        read(config_dir, "workflow-failed.yaml"),
        actions,
    )
    assert rb.normalized_by == "parser" and rb.llm_model is None
    assert [s.action for s in rb.steps] == ["http-health-check", "retry-workflow", "escalate", None]


def test_trade_limit_breach_markdown(config_dir, actions):
    rb = normalize_runbook(
        "trade-limit-breach",
        "Trade limit breach",
        None,
        RunbookFormat.markdown,
        read(config_dir, "trade-limit-breach.md"),
        actions,
    )
    assert len(rb.steps) >= 3 and rb.normalized_by == "parser"
    assert any(s.action == "open-ticket" for s in rb.steps)
    assert "{{payload.counterparty}}" in rb.steps[1].text


def test_pricing_stale_feed_text(config_dir, actions):
    rb = normalize_runbook(
        "pricing-stale-feed",
        "pricing-stale-feed",
        None,
        RunbookFormat.text,
        read(config_dir, "pricing-stale-feed.txt"),
        actions,
    )
    assert len(rb.steps) == 1 and rb.steps[0].kind == StepKind.text
    assert rb.normalized_by == "fallback" and rb.llm_model is None


def test_invalid_yaml_and_empty_markdown(actions):
    with pytest.raises(ValidationError):
        normalize_runbook("x", "x", None, RunbookFormat.yaml, "id: x\ntitle: t\nsteps: []", actions)
    with pytest.raises(ValueError):
        normalize_runbook("x", "x", None, RunbookFormat.markdown, "", actions)
