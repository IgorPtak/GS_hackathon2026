"""Manual runbook step runs (A-44): executed once, no walk, redelivery is a no-op."""

from typing import Any
from unittest import mock

import pytest
from alerting_contracts.alerts import RunbookJob
from alerting_contracts.runbooks import ActionRunStatus, Runbook, RunbookFormat

from services.runbook_runner import runner as runner_module
from services.runbook_runner.runner import RunbookRunner, RunbookWalker

from .fakes import (
    ALERT_ID,
    FakeNotifier,
    FakeStore,
    ScriptedPlugin,
    action_config,
    make_alert,
    rendered,
    step,
)


async def test_manual_run_executes_once_and_does_not_walk_other_steps() -> None:
    runbook = rendered(step(0, automatic=False), step(1))
    plugin = ScriptedPlugin([True, True])
    store = FakeStore()
    run = await store.create_run(ALERT_ID, "rb", 0, "act", {"p": "0"}, ActionRunStatus.approved)
    walker = RunbookWalker(
        store, FakeNotifier(), make_alert(), runbook, {"act": action_config()}, lambda _t: plugin
    )
    await walker.execute_approved(run)
    assert store.statuses(0) == [(1, "succeeded")]
    assert store.statuses(1) == []  # the automatic step 1 was not started
    assert len(plugin.calls) == 1


async def test_redelivered_manual_job_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    store = FakeStore()
    run = await store.create_run(ALERT_ID, "rb", 0, "act", {}, ActionRunStatus.approved)
    plugin = ScriptedPlugin([True])
    runbook = Runbook(
        id="rb",
        title="rb",
        format=RunbookFormat.yaml,
        source="",
        team="settlements",
        steps=[{"index": 0, "kind": "action", "text": "go", "action": "act"}],
        normalized_by="parser",
    )

    async def fake_get_alert(connection: Any, alert_id: str) -> Any:
        return make_alert()

    monkeypatch.setattr(runner_module, "get_alert", fake_get_alert)
    monkeypatch.setattr(runner_module, "PgStore", lambda connection: store)
    registry = mock.Mock()
    registry.get.return_value = runbook
    registry.actions.return_value = {"act": action_config()}
    runner = RunbookRunner(mock.Mock(), mock.Mock(), registry, mock.Mock(), lambda _t: plugin)
    job = RunbookJob(
        job_type="execute_action_run", alert_id=ALERT_ID, runbook_id="rb", action_run_id=run.id
    )
    connection = mock.Mock(execute=mock.AsyncMock())
    first = await runner._process(connection, job, runbook)
    second = await runner._process(connection, job, runbook)
    assert first[0] == "handled" and second[0] == "skipped"
    assert len(plugin.calls) == 1
    assert store.runs[run.id].status is ActionRunStatus.succeeded
