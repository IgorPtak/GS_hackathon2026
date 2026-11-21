from alerting_contracts.config import ActionConfig, ApprovalPolicy
from alerting_contracts.runbooks import RunbookStep, StepKind

from plugins.runbook_formats.text_format import guard_llm_steps

ACTIONS = {
    "ticket": ActionConfig(
        id="ticket", type="webhook", approval=ApprovalPolicy.none, params={"summary": {}}
    ),
    "retry-it": ActionConfig(id="retry-it", type="webhook", approval=ApprovalPolicy.none),
    "page": ActionConfig(id="page", type="webhook", approval=ApprovalPolicy.required),
}


def step(action: str, params: dict[str, str] | None = None) -> RunbookStep:
    return RunbookStep(
        index=0,
        kind=StepKind.action,
        text="do it",
        action=action,
        params=params or {},
        is_automatic=True,
    )


def test_safe_action_with_params_stays_automatic():
    [result] = guard_llm_steps([step("ticket", {"summary": "x"})], ACTIONS)
    assert result.action == "ticket" and result.is_automatic and result.approval is None


def test_blank_required_param_becomes_manual_text_step():
    [result] = guard_llm_steps([step("ticket", {"summary": "  "})], ACTIONS)
    assert result.kind is StepKind.text and result.action is None


def test_risky_name_or_required_policy_forces_approval():
    for action in ("retry-it", "page"):
        [result] = guard_llm_steps([step(action)], ACTIONS)
        assert result.approval is ApprovalPolicy.required and not result.is_automatic
