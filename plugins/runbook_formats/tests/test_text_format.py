import pytest
from alerting_contracts.config import ActionConfig, ActionParamSpec, ApprovalPolicy
from alerting_contracts.runbooks import RunbookStep, StepKind

from plugins.runbook_formats.text_format import TextRunbookFormat, validate_llm_steps

ACTIONS = {
    "restart-pricing-adapter": ActionConfig(
        id="restart-pricing-adapter",
        type="webhook",
        approval=ApprovalPolicy.required,
        params={"feed": ActionParamSpec()},
    ),
    "open-ticket": ActionConfig(
        id="open-ticket", type="webhook", params={"summary": ActionParamSpec()}
    ),
}


def step(index, text="do it", **kw):
    return RunbookStep(index=index, kind=kw.pop("kind", StepKind.action), text=text, **kw)


def test_unknown_action_becomes_text_step():
    [result] = validate_llm_steps(
        [step(0, "call vendor", action="call-vendor", params={"x": "1"})], ACTIONS
    )
    assert result.kind is StepKind.text and result.action is None
    assert result.text == "call vendor" and result.params == {}


def test_action_kind_without_action_becomes_text():
    [result] = validate_llm_steps([step(0)], ACTIONS)
    assert result.kind is StepKind.text


def test_approval_required_is_forced_and_not_automatic():
    [result] = validate_llm_steps(
        [
            step(
                0,
                action="restart-pricing-adapter",
                params={"feed": "{{feed}}"},
                approval=ApprovalPolicy.none,
                is_automatic=True,
            )
        ],
        ACTIONS,
    )
    assert result.approval is ApprovalPolicy.required and not result.is_automatic
    assert result.action == "restart-pricing-adapter"


def test_missing_required_params_keeps_the_action():
    [result] = validate_llm_steps([step(0, action="open-ticket")], ACTIONS)
    assert result.action == "open-ticket" and result.kind is StepKind.action


def test_indexes_renumbered_and_blank_dropped():
    result = validate_llm_steps([step(5, "a"), step(2, "  "), step(9, "b")], ACTIONS)
    assert [(s.index, s.text) for s in result] == [(0, "a"), (1, "b")]


def test_empty_result():
    assert validate_llm_steps([], ACTIONS) == []


def test_plugin_fallback_is_one_text_step():
    [result] = TextRunbookFormat().normalize(" hello ", ACTIONS)
    assert result.text == "hello" and result.kind is StepKind.text
    with pytest.raises(ValueError):
        TextRunbookFormat().normalize(" ", ACTIONS)
