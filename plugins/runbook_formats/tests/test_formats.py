from pathlib import Path

import pytest
import yaml
from alerting_contracts.config import ActionConfig
from alerting_contracts.runbooks import RunbookFormat, StepKind
from pydantic import ValidationError

from plugins.runbook_formats import UnknownRunbookFormatError, get_runbook_format

ACTIONS = {
    i: ActionConfig(id=i, type="webhook")
    for i in (
        "http-health-check",
        "retry-workflow",
        "escalate",
        "open-ticket",
        "restart-pricing-adapter",
    )
}


def md(source: str, actions=ACTIONS):
    return get_runbook_format("markdown").normalize(source, actions)


def test_registry_unknown_and_builtins():
    for fmt in RunbookFormat:
        assert get_runbook_format(fmt).format == fmt
    with pytest.raises(UnknownRunbookFormatError):
        get_runbook_format("docx")


def test_markdown_keywords_and_placeholders():
    steps = md(
        "# Title\n1. Check health of {{service}}\n2. Retry it\n- Escalate now\n"
        "- Open a ticket\n- Restart the adapter\n- Call someone"
    )
    assert [s.kind for s in steps] == [
        StepKind.text,
        StepKind.check,
        StepKind.action,
        StepKind.action,
        StepKind.action,
        StepKind.action,
        StepKind.text,
    ]
    assert [s.action for s in steps] == [
        None,
        "http-health-check",
        "retry-workflow",
        "escalate",
        "open-ticket",
        "restart-pricing-adapter",
        None,
    ]
    assert steps[1].text == "Check health of {{service}}"
    assert steps[4].params == {"summary": "Open a ticket"}
    assert all(s.approval is None for s in steps)
    assert [s.index for s in steps] == list(range(7))


def test_markdown_unknown_action_is_text():
    assert md("1. Retry it", actions={})[0].kind == StepKind.text


def test_markdown_nested_and_continuation():
    steps = md("- Parent\n  - Child retry\n    more words\n")
    assert [s.text for s in steps] == ["Parent", "Child retry more words"]
    assert steps[1].action == "retry-workflow"


def test_markdown_headings_only():
    steps = md("# A\n## B\n")
    assert [(s.kind, s.text) for s in steps] == [(StepKind.text, "A"), (StepKind.text, "B")]


@pytest.mark.parametrize("source", ["", "  \n", "just a paragraph"])
def test_markdown_empty_is_error(source):
    with pytest.raises(ValueError):
        md(source)


def test_text_fallback_and_llm_seam():
    plugin = get_runbook_format("text")
    steps = plugin.normalize("  do things {{x}}\n", {})
    assert len(steps) == 1 and steps[0].kind == StepKind.text and steps[0].text == "do things {{x}}"
    with pytest.raises(ValueError):
        plugin.normalize(" ", {})
    from plugins.runbook_formats.text_format import TextRunbookFormat

    sentinel = steps
    assert TextRunbookFormat(lambda t, a: sentinel).normalize("x", {}) is sentinel


YAML_OK = (
    "id: r\ntitle: T\nsteps:\n  - {index: 0, kind: text, text: a}\n"
    "  - {index: 1, kind: text, text: b}\n"
)


def test_yaml_ok():
    steps = get_runbook_format("yaml").normalize(YAML_OK, ACTIONS)
    assert [s.index for s in steps] == [0, 1]


def test_yaml_invalid_has_path():
    bad = "id: r\ntitle: T\nsteps:\n  - {index: 0, kind: nope, text: a}\n"
    with pytest.raises(ValidationError) as exc:
        get_runbook_format("yaml").normalize(bad, ACTIONS)
    assert exc.value.errors()[0]["loc"][:3] == ("steps", 0, "kind")


def test_yaml_non_contiguous_indexes():
    bad = YAML_OK.replace("index: 1", "index: 3")
    with pytest.raises(ValidationError) as exc:
        get_runbook_format("yaml").normalize(bad, ACTIONS)
    assert exc.value.errors()[0]["loc"] == ("steps", 1, "index")


def test_yaml_not_a_mapping():
    with pytest.raises(ValueError):
        get_runbook_format("yaml").normalize("- a", ACTIONS)


def _real_actions():
    root = Path(__file__).resolve().parents[3] / "config"
    return {
        p.stem: ActionConfig.model_validate(yaml.safe_load(p.read_text()))
        for p in (root / "actions").glob("*.yaml")
    }


def test_markdown_inline_action_params_and_approval():
    steps = md(
        "1. Retry the workflow `retry_workflow workflowId={{workflowId}}`\n"
        "2. Escalate `escalate workflow_id={{workflowId}}"
        ' reason="stale feed, again" approval=required`\n'
        "3. Open it `open-ticket summary=x approval=none`\n",
        actions=_real_actions(),
    )
    assert steps[0].action == "retry-workflow"
    assert steps[0].text == "Retry the workflow"
    assert steps[0].params == {"workflow_id": "{{workflowId}}"}
    assert steps[1].params == {"workflow_id": "{{workflowId}}", "reason": "stale feed, again"}
    assert steps[1].approval == "required"
    assert steps[2].approval == "none"
    assert not any(s.is_automatic for s in steps)


def test_markdown_missing_required_params_becomes_text():
    steps = md("1. Retry the workflow\n2. Escalate now", actions=_real_actions())
    assert [s.kind for s in steps] == [StepKind.text, StepKind.text]
    assert all(s.action is None for s in steps)


def test_markdown_prose_needs_approval():
    steps = md("1. Restart it (needs approval from the lead)\n2. Plain step")
    assert steps[0].approval == "required"
    assert steps[1].approval is None


def test_appendix_b_markdown_runbook():
    actions = _real_actions()
    path = Path(__file__).resolve().parents[3] / "config/runbooks/trade-limit-breach.md"
    steps = md(path.read_text(), actions=actions)
    by_text = {s.text.split(" ")[0]: s for s in steps}
    assert by_text["Confirm"].approval == "required"
    assert by_text["If"].action == "open-ticket"
    assert by_text["If"].params["team"] == "risk"
    for step in steps:
        if step.action:
            required = {n for n, p in actions[step.action].params.items() if p.is_required}
            assert required <= set(step.params)
