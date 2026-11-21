"""Step-walk semantics with fake plugins and a fake store (no I/O)."""

import asyncio
from unittest import mock

from alerting_contracts.alerts import AuditVerb
from alerting_contracts.runbooks import ActionRunStatus, RenderedRunbook, RunIf, StepKind
from alerting_contracts.sse import ActionRunUpdatedEvent, ApprovalRequestedEvent

from services.runbook_runner import runner as runner_module
from services.runbook_runner.runner import RunbookWalker

from .fakes import (
    FakeNotifier,
    FakeStore,
    ScriptedPlugin,
    action_config,
    make_alert,
    rendered,
    step,
)


def build(
    runbook: RenderedRunbook, plugin: ScriptedPlugin, store: FakeStore | None = None
) -> tuple[RunbookWalker, FakeStore, FakeNotifier]:
    store = store or FakeStore()
    notifier = FakeNotifier()
    walker = RunbookWalker(
        store,
        notifier,
        make_alert(),
        runbook,
        {"act": action_config()},
        lambda _type: plugin,
    )
    return walker, store, notifier


def verbs(store: FakeStore) -> list[AuditVerb]:
    return [entry.verb for entry in store.audits]


async def test_automatic_steps_run_and_text_and_manual_steps_are_skipped() -> None:
    plugin = ScriptedPlugin([True])
    runbook = rendered(
        step(0, kind=StepKind.text, action=None),
        step(1, automatic=False),
        step(2),
    )
    walker, store, _ = build(runbook, plugin)
    await walker.start()
    assert store.statuses(0) == [] and store.statuses(1) == []
    assert store.statuses(2) == [(1, "succeeded")]
    assert verbs(store) == [
        AuditVerb.runbook_started,
        AuditVerb.action_run_started,
        AuditVerb.action_run_succeeded,
    ]


async def test_run_if_previous_succeeded_runs_after_success() -> None:
    plugin = ScriptedPlugin([True, True])
    walker, store, _ = build(rendered(step(0), step(1, run_if=RunIf.previous_succeeded)), plugin)
    await walker.start()
    assert store.statuses(1) == [(1, "succeeded")]


async def test_run_if_previous_succeeded_skips_after_failure() -> None:
    plugin = ScriptedPlugin([False])
    walker, store, _ = build(rendered(step(0), step(1, run_if=RunIf.previous_succeeded)), plugin)
    await walker.start()
    assert store.statuses(1) == [(1, "skipped")]
    assert len(plugin.calls) == 1
    assert verbs(store).count(AuditVerb.action_run_skipped) == 1


async def test_run_if_previous_failed_both_ways() -> None:
    plugin = ScriptedPlugin([False, True])
    walker, store, _ = build(rendered(step(0), step(1, run_if=RunIf.previous_failed)), plugin)
    await walker.start()
    assert store.statuses(1) == [(1, "succeeded")]

    plugin = ScriptedPlugin([True])
    walker, store, _ = build(rendered(step(0), step(1, run_if=RunIf.previous_failed)), plugin)
    await walker.start()
    assert store.statuses(1) == [(1, "skipped")]


async def test_run_if_conditional_on_first_step_is_skipped() -> None:
    walker, store, _ = build(rendered(step(0, run_if=RunIf.previous_failed)), ScriptedPlugin([]))
    await walker.start()
    assert store.statuses(0) == [(1, "skipped")]


async def test_max_attempts_retries_then_succeeds() -> None:
    plugin = ScriptedPlugin([False, True])
    walker, store, _ = build(rendered(step(0, max_attempts=3)), plugin)
    await walker.start()
    assert store.statuses(0) == [(1, "failed"), (2, "succeeded")]
    assert len(plugin.calls) == 2


async def test_max_attempts_exhausted_is_failed() -> None:
    plugin = ScriptedPlugin([False, False])
    walker, store, _ = build(rendered(step(0, max_attempts=2)), plugin)
    await walker.start()
    assert store.statuses(0) == [(1, "failed"), (2, "failed")]


async def test_plugin_exception_is_recorded_as_failed() -> None:
    plugin = ScriptedPlugin([RuntimeError("bug")])
    walker, store, _ = build(rendered(step(0), step(1, run_if=RunIf.previous_failed)), plugin)
    await walker.start()
    failed = next(r for r in store.runs.values() if r.step_index == 0)
    assert failed.status is ActionRunStatus.failed
    assert failed.error == "RuntimeError: bug"
    assert store.statuses(1) == [(1, "succeeded")]


async def test_unknown_action_is_a_failed_run() -> None:
    walker, store, _ = build(rendered(step(0, action="nope")), ScriptedPlugin([]))
    await walker.start()
    run = next(iter(store.runs.values()))
    assert run.status is ActionRunStatus.failed and "unknown action" in (run.error or "")


async def test_approval_stops_the_walk() -> None:
    plugin = ScriptedPlugin([])
    walker, store, notifier = build(
        rendered(step(0, approval=True, automatic=False), step(1)), plugin
    )
    await walker.start()
    assert store.statuses(0) == [(1, "pending_approval")]
    assert store.statuses(1) == []
    assert plugin.calls == []
    assert len(store.approvals) == 1 and len(notifier.notified) == 1
    assert verbs(store)[-1] is AuditVerb.approval_requested
    assert any(isinstance(e, ApprovalRequestedEvent) for e in walker.events)


async def test_replay_does_not_rerun_succeeded_step_nor_duplicate_approval() -> None:
    runbook = rendered(step(0), step(1, approval=True, automatic=False))
    plugin = ScriptedPlugin([True])
    walker, store, notifier = build(runbook, plugin)
    await walker.start()

    replay, store, notifier2 = build(runbook, plugin, store)
    await replay.start()
    assert len(plugin.calls) == 1
    assert len(store.approvals) == 1 and notifier2.notified == []
    assert verbs(store).count(AuditVerb.runbook_started) == 1
    assert replay.events == []


async def test_replay_does_not_rerun_finally_failed_or_skipped_steps() -> None:
    runbook = rendered(step(0), step(1, run_if=RunIf.previous_succeeded))
    plugin = ScriptedPlugin([False])
    walker, store, _ = build(runbook, plugin)
    await walker.start()
    replay, _, _ = build(runbook, plugin, store)
    await replay.start()
    assert len(plugin.calls) == 1
    assert verbs(store).count(AuditVerb.action_run_skipped) == 1


async def test_execute_approved_runs_step_then_continues_the_walk() -> None:
    runbook = rendered(
        step(0, approval=True, automatic=False),
        step(1, run_if=RunIf.previous_succeeded),
        step(2, run_if=RunIf.previous_failed),
    )
    plugin = ScriptedPlugin([True, True])
    walker, store, _ = build(runbook, plugin)
    await walker.start()
    run = next(iter(store.runs.values()))
    await store.update_run(run.id, ActionRunStatus.approved, run.attempt)

    approved = await store.get_run(run.id)
    assert approved is not None
    resume, _, _ = build(runbook, plugin, store)
    await resume.execute_approved(approved)
    assert store.statuses(0) == [(1, "succeeded")]  # same row reused
    assert store.statuses(1) == [(1, "succeeded")]
    assert store.statuses(2) == [(1, "skipped")]
    assert len(plugin.calls) == 2
    updates = [e for e in resume.events if isinstance(e, ActionRunUpdatedEvent)]
    assert updates and updates[0].action_run.status is ActionRunStatus.running


async def test_replay_while_pending_or_rejected_stops_without_new_work() -> None:
    runbook = rendered(step(0, approval=True, automatic=False), step(1))
    plugin = ScriptedPlugin([])
    walker, store, _ = build(runbook, plugin)
    await walker.start()
    run = next(iter(store.runs.values()))
    await store.update_run(run.id, ActionRunStatus.rejected, run.attempt)
    replay, _, _ = build(runbook, plugin, store)
    await replay.start()
    assert store.statuses(1) == [] and plugin.calls == []


async def test_replay_after_partial_attempts_continues_numbering() -> None:
    runbook = rendered(step(0, max_attempts=3))
    plugin = ScriptedPlugin([True])
    walker, store, _ = build(runbook, plugin)
    await store.create_run(
        "0197c9a0-0000-7000-8000-000000000001", "rb", 0, "act", {}, ActionRunStatus.failed
    )
    walker, store, _ = build(runbook, plugin, store)
    await walker.start()
    assert store.statuses(0) == [(1, "failed"), (2, "succeeded")]


async def test_approval_step_with_unsatisfied_run_if_is_skipped_without_approval() -> None:
    runbook = rendered(
        step(0), step(1, approval=True, automatic=False, run_if=RunIf.previous_failed)
    )
    walker, store, notifier = build(runbook, ScriptedPlugin([True]))
    await walker.start()
    assert store.statuses(1) == [(1, "skipped")]
    assert store.approvals == [] and notifier.notified == []


async def test_plugin_timeout_is_a_failed_run() -> None:
    class Slow(ScriptedPlugin):
        async def _run(self, params, config):  # noqa: ANN001, ANN202
            await asyncio.sleep(10)

    walker, store, _ = build(rendered(step(0)), Slow([]))
    with mock.patch.object(runner_module, "PLUGIN_TIMEOUT_MARGIN_SECONDS", -9.9):
        await walker.start()
    run = next(iter(store.runs.values()))
    assert run.status is ActionRunStatus.failed and "timed out" in (run.error or "")


async def test_automatic_step_that_requires_approval_never_runs_without_one() -> None:
    plugin = ScriptedPlugin([True])
    walker, store, notifier = build(
        rendered(step(0, approval=True, automatic=True), step(1)), plugin
    )
    await walker.start()
    assert plugin.calls == []
    assert store.statuses(0) == [(1, "pending_approval")]
    assert len(store.approvals) == 1 and len(notifier.notified) == 1


async def test_retry_after_failure_of_an_approval_step_asks_again() -> None:
    runbook = rendered(step(0, approval=True, automatic=True, max_attempts=3))
    plugin = ScriptedPlugin([True])
    walker, store, _ = build(runbook, plugin)
    await store.create_run(
        "0197c9a0-0000-7000-8000-000000000001", "rb", 0, "act", {}, ActionRunStatus.failed
    )
    walker, store, _ = build(runbook, plugin, store)
    await walker.start()
    assert plugin.calls == []
    assert store.statuses(0) == [(1, "failed"), (2, "pending_approval")]
