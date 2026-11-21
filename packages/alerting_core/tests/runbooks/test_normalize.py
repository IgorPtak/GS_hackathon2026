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


class FakeLlm:
    model = "fake-model"

    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    async def generate(self, prompt, response_model, *, system=None):
        self.calls.append((prompt, system))
        if self.error:
            raise self.error
        return self.result


def _steps(*items):
    from alerting_contracts.runbooks import RunbookStep
    from alerting_core.runbooks.normalize import StepsResponse

    return StepsResponse(steps=[RunbookStep(index=i, **item) for i, item in enumerate(items)])


PRICING_STEPS = (
    {"kind": "check", "text": "Is the whole feed down?"},
    {
        "kind": "action",
        "text": "Restart adapter for {{feed}}",
        "action": "restart-pricing-adapter",
        "params": {"feed": "{{feed}}"},
    },
    {"kind": "action", "text": "Call the vendor", "action": "call-vendor"},
    {"kind": "text", "text": "Switch to backup feed"},
    {"kind": "text", "text": "Tell the traders"},
)


async def run_llm(config_dir, actions, client, fmt=RunbookFormat.text, source=None):
    from alerting_core.runbooks.normalize import normalize_runbook_with_llm

    source = source or read(config_dir, "pricing-stale-feed.txt")
    return await normalize_runbook_with_llm("pricing", "T", "pricing", fmt, source, actions, client)


@pytest.mark.asyncio
async def test_llm_happy_path_and_prompt(config_dir, actions):
    client = FakeLlm(_steps(*PRICING_STEPS))
    rb = await run_llm(config_dir, actions, client)
    assert rb.normalized_by == "llm" and rb.llm_model == "fake-model"
    assert len(rb.steps) >= 4 and [s.index for s in rb.steps] == list(range(len(rb.steps)))
    restart = next(s for s in rb.steps if s.action == "restart-pricing-adapter")
    assert restart.approval == "required"
    unknown = rb.steps[2]
    assert unknown.kind == StepKind.text and unknown.action is None
    prompt, system = client.calls[0]
    assert "stale" in prompt
    for action_id in actions:
        assert action_id in system
    assert "feed (required: Feed whose adapter is restarted)" in system
    assert "instrument (optional" in system and "approval required" in system
    assert "<<ACTIONS>>" not in system


@pytest.mark.asyncio
async def test_llm_unavailable_invalid_missing_and_empty_fall_back(config_dir, actions):
    from alerting_core.llm import LlmOutputInvalidError, LlmUnavailableError
    from alerting_core.runbooks.normalize import StepsResponse

    for client in (
        FakeLlm(error=LlmUnavailableError("down")),
        FakeLlm(error=LlmOutputInvalidError("bad")),
        FakeLlm(StepsResponse(steps=[])),
        None,
    ):
        rb = await run_llm(config_dir, actions, client)
        assert rb.normalized_by == "fallback" and rb.llm_model is None
        assert len(rb.steps) == 1 and rb.steps[0].text == rb.source.strip()


@pytest.mark.asyncio
async def test_llm_not_used_for_parsed_formats(config_dir, actions):
    client = FakeLlm(_steps(*PRICING_STEPS))
    rb = await run_llm(
        config_dir,
        actions,
        client,
        RunbookFormat.yaml,
        read(config_dir, "workflow-failed.yaml"),
    )
    assert rb.normalized_by == "parser" and client.calls == []


UNSAFE_YAML = """\
id: unsafe
title: Unsafe
steps:
  - index: 0
    kind: action
    text: "Restart {{feed}}"
    action: restart-pricing-adapter
    params: { feed: "{{feed}}" }
    approval: none
    is_automatic: true
  - index: 1
    kind: action
    text: "Escalate {{workflowId}}"
    action: escalate
    params: { workflow_id: "{{workflowId}}" }
    approval: none
    is_automatic: true
"""


def test_yaml_approval_none_cannot_loosen_required_actions(actions):
    rb = normalize_runbook("unsafe", "Unsafe", None, RunbookFormat.yaml, UNSAFE_YAML, actions)
    assert [s.approval.value for s in rb.steps] == ["required", "required"]


def test_step_requires_approval_ignores_a_loosening_step(actions):
    from alerting_contracts.config import ApprovalPolicy
    from alerting_contracts.runbooks import RunbookStep
    from alerting_core.runbooks.approval_policy import step_requires_approval

    loose = RunbookStep(
        index=0,
        kind=StepKind.action,
        text="x",
        action="escalate",
        approval=ApprovalPolicy.none,
        is_automatic=True,
    )
    assert step_requires_approval(loose, actions) is True
    open_ticket = loose.model_copy(update={"action": "open-ticket"})
    assert step_requires_approval(open_ticket, actions) is False
    assert step_requires_approval(
        open_ticket.model_copy(update={"approval": ApprovalPolicy.required}), actions
    )
