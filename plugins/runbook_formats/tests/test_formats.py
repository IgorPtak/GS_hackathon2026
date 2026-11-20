import pytest
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
