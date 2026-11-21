"""File free-text runbooks are normalized by the LLM at sync time and guarded (A-46)."""

import asyncio
import json

import httpx
import respx
from alerting_contracts.config import ApprovalPolicy
from alerting_contracts.runbooks import StepKind
from alerting_core.llm import InMemoryLlmCache, LlmClient, LlmConfig, LlmUnavailableError
from alerting_core.runbooks import store
from alerting_core.runbooks.store import load_runbook_file, normalize_text_file

SOURCE = "Restart the adapter if one feed is stale, then call the vendor."


def steps_json(*steps: dict) -> str:
    return json.dumps({"steps": list(steps)})


RESTART = {
    "index": 0,
    "kind": "action",
    "text": "Restart the adapter",
    "action": "restart-pricing-adapter",
    "params": {"feed": "{{feed}}"},
    "is_automatic": True,
}


class FakeLlm:
    model = "fake-model"

    def __init__(self, answer: str | Exception, delay: float = 0) -> None:
        self.answer, self.delay = answer, delay

    async def generate(self, prompt, response_model, *, system=None):
        if self.delay:
            await asyncio.sleep(self.delay)
        if isinstance(self.answer, Exception):
            raise self.answer
        return response_model.model_validate_json(self.answer)


def run(actions, client):
    return normalize_text_file("rb", "rb", None, SOURCE, actions, client)


def test_valid_restart_step_is_kept_and_needs_approval(actions):
    runbook = run(actions, FakeLlm(steps_json(RESTART)))
    assert runbook.normalized_by == "llm" and runbook.llm_model == "fake-model"
    [step] = runbook.steps
    assert step.action == "restart-pricing-adapter"
    assert step.approval is ApprovalPolicy.required and not step.is_automatic


def test_unknown_action_and_missing_params_become_text_steps(actions):
    unknown = {**RESTART, "action": "format-disk"}
    missing = {**RESTART, "index": 1, "params": {}}
    runbook = run(actions, FakeLlm(steps_json(unknown, missing)))
    assert [s.kind for s in runbook.steps] == [StepKind.text, StepKind.text]
    assert all(s.action is None and not s.is_automatic for s in runbook.steps)


def test_risky_action_with_policy_none_still_needs_approval(actions):
    retry = {
        "index": 0,
        "kind": "action",
        "text": "Retry",
        "action": "retry-workflow",
        "params": {"workflow_id": "{{workflow_id}}"},
        "is_automatic": True,
    }
    ticket = {
        "index": 1,
        "kind": "action",
        "text": "Ticket",
        "action": "open-ticket",
        "params": {"summary": "x"},
        "is_automatic": True,
    }
    first, second = run(actions, FakeLlm(steps_json(retry, ticket))).steps
    assert first.approval is ApprovalPolicy.required and not first.is_automatic
    assert second.action == "open-ticket" and second.is_automatic


def test_timeout_and_errors_fall_back(actions, monkeypatch):
    monkeypatch.setattr(store, "LLM_SYNC_TIMEOUT_SECONDS", 0.05)
    for client in (FakeLlm(steps_json(RESTART), delay=1), FakeLlm(LlmUnavailableError("down"))):
        runbook = run(actions, client)
        assert runbook.normalized_by == "fallback" and len(runbook.steps) == 1
        assert runbook.steps[0].kind == StepKind.text


def test_slow_llm_does_not_fail_loading_other_documents(config_dir, monkeypatch):
    monkeypatch.setattr(store, "LLM_SYNC_TIMEOUT_SECONDS", 0.05)
    slow = FakeLlm(steps_json(RESTART), delay=1)
    monkeypatch.setattr(store, "create_sync_llm_client", lambda cache: slow)
    text = load_runbook_file(config_dir / "runbooks" / "pricing-stale-feed.txt")
    other = load_runbook_file(config_dir / "runbooks" / "workflow-failed.yaml")
    assert text.normalized_by == "fallback" and other.normalized_by == "parser"


@respx.mock
def test_cache_hit_makes_no_second_call(actions):
    route = respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": steps_json(RESTART)}}]}
        )
    )
    client = LlmClient(LlmConfig(base_url="http://localhost:11434/v1"), cache=InMemoryLlmCache())
    first = run(actions, client)
    second = run(actions, client)
    assert route.call_count == 1
    assert first.steps == second.steps and second.normalized_by == "llm"
