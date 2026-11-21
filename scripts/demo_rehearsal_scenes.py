"""Rehearsal scenes 5-8: SMS outage recovery, runbook approval, metrics, Alertmanager resolve."""

from __future__ import annotations

from typing import Any

from alerting_contracts.alerts import AlertStatus, DeliveryStatus
from alerting_contracts.api import MetricsSummary, PhoneReplyResult
from alerting_contracts.runbooks import ActionRunStatus, ApprovalRequest
from demo_rehearsal_helpers import (
    DELIVERED_STATUSES,
    FatalPollError,
    RehearsalContext,
    RehearsalError,
    SceneResult,
    fresh_alertmanager_events,
    fresh_settlements_event,
    get_alert_detail,
    get_json,
    list_team_alerts,
    poll_until,
    post_ingest,
    run_scene,
    set_gateway_outage,
    set_service_health,
)

OUTAGE_RECOVERY_TIMEOUT_SECONDS = 45.0


def _find_settlements_alert(ctx: RehearsalContext, workflow_id: str) -> Any:
    page = list_team_alerts(ctx, "settlements")
    matches = [a for a in page.items if a.last_event.get("workflowId") == workflow_id]
    return matches[0] if matches else None


def _probe_sms_held_during_outage(ctx: RehearsalContext, alert_id: str) -> bool:
    detail = get_alert_detail(ctx, alert_id)
    sms = [
        d for d in detail.deliveries if d.channel_type.value == "sms" and d.recipient_id == "piotr"
    ]
    if not sms:
        raise RehearsalError("no piotr sms delivery created yet")
    if any(d.status.value in DELIVERED_STATUSES for d in sms):
        raise FatalPollError("sms delivery succeeded while sms outage was active")
    if any(d.status is DeliveryStatus.failed or d.attempt >= 1 for d in sms):
        return True
    statuses = [f"{d.status.value}(attempt={d.attempt})" for d in sms]
    raise RehearsalError(f"sms not yet attempted: {statuses}")


def _probe_all_deliveries_sent(ctx: RehearsalContext, alert_id: str) -> list[Any] | None:
    detail = get_alert_detail(ctx, alert_id)
    if not detail.deliveries:
        return None
    if any(d.status is DeliveryStatus.dead_lettered for d in detail.deliveries):
        raise FatalPollError("a delivery was dead-lettered after outage recovery")
    has_piotr_sms = any(
        d.channel_type.value == "sms" and d.recipient_id == "piotr" for d in detail.deliveries
    )
    if has_piotr_sms and all(d.status.value in DELIVERED_STATUSES for d in detail.deliveries):
        return detail.deliveries
    pending = [
        f"{d.channel_type.value}:{d.status.value}"
        for d in detail.deliveries
        if d.status.value not in DELIVERED_STATUSES
    ]
    raise RehearsalError(f"still pending: {pending}")


def scene_sms_outage_no_loss(ctx: RehearsalContext) -> SceneResult:
    """Scene 5: simulate SMS outage, verify retry without loss, restore gateway in finally."""

    def body() -> str:
        event, workflow_id = fresh_settlements_event(ctx.run_id, "outage")
        try:
            set_service_health(ctx, "settlement-engine", is_healthy=True)
            set_gateway_outage(ctx, is_down=True, channels=["sms"])
            post_ingest(ctx, "settlements-engine", event)
            alert = poll_until(
                lambda: _find_settlements_alert(ctx, workflow_id),
                timeout=ctx.timeout,
                reason=f"settlements alert for {workflow_id} not found",
            )
            ctx.state["settlements_alert_id"] = alert.id
            ctx.state["settlements_workflow_id"] = workflow_id
            poll_until(
                lambda: _probe_sms_held_during_outage(ctx, alert.id),
                timeout=ctx.timeout,
                reason="piotr sms delivery did not enter retrying/failed state during outage",
            )
            set_gateway_outage(ctx, is_down=False, channels=["sms"])
            deliveries = poll_until(
                lambda: _probe_all_deliveries_sent(ctx, alert.id),
                timeout=max(ctx.timeout, OUTAGE_RECOVERY_TIMEOUT_SECONDS),
                reason=f"not all deliveries for {alert.id} reached sent/delivered after recovery",
            )
            return f"alert {alert.id[-8:]}, {len(deliveries)}/{len(deliveries)} delivered, 0 DLQ"
        finally:
            set_gateway_outage(ctx, is_down=False)

    return run_scene("sms_outage_no_loss", body)


def _ensure_settlements_alert(ctx: RehearsalContext) -> str:
    """Reuse scene 5's settlements alert or create a fresh one for standalone runs."""
    existing = ctx.state.get("settlements_alert_id")
    if isinstance(existing, str):
        return existing
    event, workflow_id = fresh_settlements_event(ctx.run_id, "runbook")
    post_ingest(ctx, "settlements-engine", event)
    alert = poll_until(
        lambda: _find_settlements_alert(ctx, workflow_id),
        timeout=ctx.timeout,
        reason=f"settlements alert for {workflow_id} not found",
    )
    ctx.state["settlements_alert_id"] = alert.id
    return str(alert.id)


def _probe_runbook_gate(ctx: RehearsalContext, alert_id: str) -> bool:
    runs = get_alert_detail(ctx, alert_id).action_runs
    if any(r.action_id == "retry-workflow" and r.status is ActionRunStatus.succeeded for r in runs):
        raise FatalPollError("retry-workflow unexpectedly succeeded; escalate never triggered")
    health_ok = any(
        r.action_id == "http-health-check" and r.status is ActionRunStatus.succeeded for r in runs
    )
    retry_failed = any(
        r.action_id == "retry-workflow" and r.status is ActionRunStatus.failed for r in runs
    )
    escalate_pending = any(
        r.action_id == "escalate" and r.status is ActionRunStatus.pending_approval for r in runs
    )
    if health_ok and retry_failed and escalate_pending:
        return True
    summary = [(r.action_id, r.status.value) for r in runs]
    raise RehearsalError(f"action runs so far: {summary}")


def _find_pending_escalate_approval(ctx: RehearsalContext, alert_id: str) -> ApprovalRequest | None:
    raw = get_json(ctx, f"{ctx.api_url}/api/v1/approvals", team="settlements", is_pending="true")
    items = [ApprovalRequest.model_validate(item) for item in raw]
    mine = [a for a in items if a.alert_id == alert_id and a.action_id == "escalate"]
    return mine[0] if mine else None


def _probe_escalate_succeeded(ctx: RehearsalContext, alert_id: str, step_index: int) -> bool:
    runs = get_alert_detail(ctx, alert_id).action_runs
    return any(
        r.step_index == step_index
        and r.action_id == "escalate"
        and r.status is ActionRunStatus.succeeded
        for r in runs
    )


def scene_runbook_approval_by_code(ctx: RehearsalContext) -> SceneResult:
    """Scene 6: verify runbook steps, approve via phone-simulator code, assert 409 on repeat."""

    def body() -> str:
        set_service_health(ctx, "settlement-engine", is_healthy=True)
        set_gateway_outage(ctx, is_down=False)
        alert_id = _ensure_settlements_alert(ctx)
        poll_until(
            lambda: _probe_runbook_gate(ctx, alert_id),
            timeout=ctx.timeout,
            reason=f"runbook for {alert_id} did not reach pending_approval on escalate",
        )
        approval = poll_until(
            lambda: _find_pending_escalate_approval(ctx, alert_id),
            timeout=ctx.timeout,
            reason=f"pending approval for {alert_id} not found",
        )
        reply = ctx.client.post(
            f"{ctx.api_url}/api/v1/phone-simulator/replies",
            json={"recipient_id": "piotr", "text": f"approve {approval.approval_code}"},
        )
        if reply.status_code != 200:
            raise RehearsalError(f"phone-simulator reply returned {reply.status_code}")
        parsed = PhoneReplyResult.model_validate(reply.json())
        if not parsed.is_understood:
            raise RehearsalError(f"phone reply not understood: {parsed.message}")
        poll_until(
            lambda: _probe_escalate_succeeded(ctx, alert_id, approval.step_index),
            timeout=ctx.timeout,
            reason="escalate action run did not succeed",
        )
        repeat = ctx.client.post(
            f"{ctx.api_url}/api/v1/approvals/{approval.id}/decision",
            json={"decision": "approve", "actor": {"id": "piotr"}, "via": "ui"},
        )
        if repeat.status_code != 409:
            raise RehearsalError(f"second approval decision returned {repeat.status_code}, not 409")
        return f"code {approval.approval_code} approved by piotr, escalate succeeded, repeat 409"

    return run_scene("runbook_approval_by_code", body)


def scene_metrics_summary(ctx: RehearsalContext) -> SceneResult:
    """Scene 7: verify GET /api/v1/metrics/summary returns 200 with all keys; warn on nulls."""

    def body() -> str:
        response = ctx.client.get(f"{ctx.api_url}/api/v1/metrics/summary")
        if response.status_code != 200:
            raise RehearsalError(f"GET /api/v1/metrics/summary returned {response.status_code}")
        data = response.json()
        expected_keys = set(MetricsSummary.model_fields)
        missing = sorted(expected_keys - set(data))
        if missing:
            raise RehearsalError(f"missing keys in metrics summary: {', '.join(missing)}")
        summary = MetricsSummary.model_validate(data)
        null_fields = sorted(k for k in expected_keys if data.get(k) is None)
        if null_fields:
            return (
                f"200 ok (open={summary.open_alert_count}); "
                f"warning: null fields: {', '.join(null_fields)}"
            )
        return (
            f"200 ok, all {len(expected_keys)} fields populated (open={summary.open_alert_count})"
        )

    return run_scene("metrics_summary", body)


def scene_alertmanager_resolve(ctx: RehearsalContext) -> SceneResult:
    """Scene 8: post Alertmanager firing then resolved payload and verify alert ends resolved."""

    def body() -> str:
        firing, resolved, instance = fresh_alertmanager_events(ctx.run_id)
        fire_res = post_ingest(ctx, "alertmanager", firing)
        if len(fire_res.event_ids) != 1 or fire_res.duplicate_count != 0:
            raise RehearsalError(f"firing ingest unexpected: {fire_res.model_dump()}")

        def find_open() -> Any:
            page = list_team_alerts(ctx, "platform", status="open")
            matches = [
                a for a in page.items if a.last_event.get("labels", {}).get("instance") == instance
            ]
            return matches[0] if matches else None

        alert = poll_until(
            find_open, timeout=ctx.timeout, reason=f"open alertmanager alert for {instance} missing"
        )
        res_resp = post_ingest(ctx, "alertmanager", resolved)
        if len(res_resp.event_ids) != 1 or res_resp.duplicate_count != 0:
            raise RehearsalError(f"resolved ingest unexpected: {res_resp.model_dump()}")

        def is_resolved() -> Any:
            detail = get_alert_detail(ctx, alert.id)
            return detail.alert if detail.alert.status is AlertStatus.resolved else None

        final_alert = poll_until(
            is_resolved, timeout=ctx.timeout, reason=f"alert {alert.id} did not resolve"
        )
        reason_text = final_alert.resolution_reason.value if final_alert.resolution_reason else None
        return f"alert {alert.id[-8:]} ({instance}) resolved ({reason_text})"

    return run_scene("alertmanager_resolve", body)
