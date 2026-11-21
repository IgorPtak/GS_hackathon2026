import pytest
from alerting_contracts.runbooks import RenderedRunbookStep, RunbookStep, StepKind
from pydantic import ValidationError


@pytest.mark.parametrize("model", [RunbookStep, RenderedRunbookStep])
def test_max_attempts_is_capped(model: type) -> None:
    # A runbook or an LLM proposal must not retry an action without bound.
    base = {"index": 0, "kind": StepKind.action, "text": "Retry", "action": "retry-workflow"}
    assert model(**base, max_attempts=10).max_attempts == 10
    with pytest.raises(ValidationError):
        model(**base, max_attempts=11)
