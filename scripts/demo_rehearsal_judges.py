"""Rehearsal scene `judges_path`: live-judging flow with an unknown schema and free-text runbook."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import demo_rehearsal_helpers as h
import httpx
from alerting_contracts import alerts, api, config
from alerting_contracts.common import Actor
from alerting_contracts.proposals import SchemaProfileProposal
from alerting_contracts.runbooks import Runbook, RunbookFormat, RunbookStep
from alerting_core.events.shape import shape_hash
from pydantic import BaseModel

DISCRIMINATOR_FIELD, JUDGES_TEAM, JUDGES_RECIPIENT = "schema_kind", "platform", "marek"
LLM_TIMEOUT, ESCALATE_KEYWORDS = 60.0, ("escalat", "page", "paging")
JUDGES_ACTOR = Actor(id="marek", display_name="Marek Dabrowski")
JUDGES_RUNBOOK_SOURCE = (
    "First check if the robot service is healthy, then retry the workflow job, "
    "and if it is still broken page the on-call manager (ask before paging!)."
)


def judges_resource_id(run_id: str) -> str:
    """Return the per-run config id (`judges-<sfx>`) shared by profile, rule, and runbook."""
    return f"judges-{run_id.lower()}"


def judges_discriminator(run_id: str) -> str:
    """Return the per-run top-level discriminator value so no prior profile matches."""
    return f"warehouse-robot-{run_id.lower()}"


def build_robot_event(
    run_id: str, robot_id: str, fault_level: str, fault_code: str = "DRIVE_STALL", ts: str = ""
) -> dict[str, Any]:
    """Build a synthetic warehouse-robot event in an unseen nested schema."""
    return {
        DISCRIMINATOR_FIELD: judges_discriminator(run_id),
        "robot": {"id": robot_id, "bay": "B4"},
        "fault": {"code": fault_code, "level": fault_level},
        "ts": ts or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "site": f"wh-{run_id.lower()}",
    }


def build_judges_samples(run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build the onboarding sample and live events (FATAL, WARN, FATAL on one `robot.id`)."""
    sfx, base, fmt = run_id.lower(), datetime.now(UTC), "%Y-%m-%dT%H:%M:%SZ"
    sample = build_robot_event(sfx, f"bot-{sfx}-sample", "FATAL", ts=base.strftime(fmt))
    bot, specs = (
        f"bot-{sfx}-live",
        (("FATAL", "DRIVE_STALL", 1), ("WARN", "BATTERY_LOW", 2), ("FATAL", "DRIVE_STALL", 3)),
    )
    live = [
        build_robot_event(sfx, bot, lv, cd, (base + timedelta(seconds=s)).strftime(fmt))
        for lv, cd, s in specs
    ]
    return sample, live


def prepare_proposed_profile(
    proposal: SchemaProfileProposal, profile_id: str, discriminator: str
) -> config.SchemaProfile:
    """Validate the proposed profile, force its id, and scope its match to this run's tag."""
    p = config.SchemaProfile.model_validate(proposal.profile.model_dump(mode="json"))
    leaf = config.ConditionLeaf(
        field=DISCRIMINATOR_FIELD, op=config.ConditionOperator.eq, value=discriminator
    )
    clauses = list(p.match.all) if isinstance(p.match, config.ConditionAll) else [p.match]
    if leaf not in clauses:
        clauses.append(leaf)
    scoped = p.model_copy(update={"id": profile_id, "match": config.ConditionAll(all=clauses)})
    return config.SchemaProfile.model_validate(scoped.model_dump(mode="json"))


def build_judges_rule(run_id: str, *, enabled: bool = True) -> config.Rule:
    """Build the `judges-<sfx>` rule matching FATAL robot faults with dedup on `robot.id`."""
    rid, disc = judges_resource_id(run_id), judges_discriminator(run_id)
    when = [
        {"field": "fault.level", "op": "eq", "value": "FATAL"},
        {"field": DISCRIMINATOR_FIELD, "op": "eq", "value": disc},
    ]
    return config.Rule.model_validate(
        {
            "id": rid,
            "team": JUDGES_TEAM,
            "enabled": enabled,
            "runbook": rid,
            "description": f"Judges path warehouse robot fatal faults ({run_id})",
            "when": {"all": when},
            "present": {
                "title": "Robot {{robot.id}} fault {{fault.code}} at {{site}}",
                "body": "Warehouse robot {{robot.id}} reported {{fault.level}} {{fault.code}}.",
                "fields": ["robot.id", "fault.code", "fault.level", "site"],
                "color": "red",
            },
            "route": {"recipients": [JUDGES_RECIPIENT], "channels": ["ui", "email"]},
            "dedup": {"window": "60s", "fingerprint": ["robot.id"]},
        }
    )


def build_judges_runbook_write(run_id: str) -> api.RunbookWrite:
    """Build the PUT `/api/v1/runbooks/{id}` request model for the free-text runbook."""
    return api.RunbookWrite(
        id=judges_resource_id(run_id),
        title=f"Warehouse robot recovery ({run_id})",
        team=JUDGES_TEAM,
        format=RunbookFormat.text,
        source=JUDGES_RUNBOOK_SOURCE,
        actor=JUDGES_ACTOR,
    )


def assert_profile_test_matched_sample(result: api.SchemaProfileTestResult) -> None:
    """Assert `/schema-profiles/test` matched the submitted `sample_event` (`event_id is None`)."""
    if not any(sample.event_id is None for sample in result.samples):
        raise h.RehearsalError(f"schema-profiles/test did not match sample_event ({result})")


def step_requires_approval(
    step: RunbookStep, known_actions: Mapping[str, config.ActionConfig]
) -> bool:
    """Return True if a runbook step requires approval explicitly or via its action config."""
    if step.approval is config.ApprovalPolicy.required:
        return True
    action = known_actions.get(step.action) if step.approval is None and step.action else None
    return action is not None and action.approval is config.ApprovalPolicy.required


def assert_normalized_runbook(
    runbook: Runbook, known_actions: Mapping[str, config.ActionConfig]
) -> None:
    """Assert normalized free-text runbook has >= 2 steps, a known action, and gated escalation."""
    if len(runbook.steps) < 2:
        raise h.RehearsalError(f"runbook {runbook.id} needs >= 2 steps, got {len(runbook.steps)}")
    if not any(step.action in known_actions for step in runbook.steps):
        raise h.RehearsalError(f"runbook {runbook.id} mapped no known action")
    escalate = [s for s in runbook.steps if s.action == "escalate"] or [
        s for s in runbook.steps if any(k in s.text.lower() for k in ESCALATE_KEYWORDS)
    ]
    if not escalate or not all(step_requires_approval(s, known_actions) for s in escalate):
        raise h.RehearsalError(f"runbook {runbook.id} escalate/page step does not require approval")


def assert_judges_alert(alert: alerts.Alert, rid: str) -> None:
    """Assert the live alert matched the saved profile, rule, dedup count, and runbook."""
    checks = (("rule_id", rid), ("count", 2), ("schema_profile_id", rid), ("runbook_id", rid))
    for name, expected in checks:
        if (actual := getattr(alert, name)) != expected:
            raise h.RehearsalError(f"alert {name}={actual!r}, expected {expected!r}")


def format_judges_detail(
    rid: str, gen: str, steps: int, norm: str, count: int, *, warnings: Sequence[str] = ()
) -> str:
    """Format the concise PASS detail line for `judges_path`."""
    head = f"profile {rid} ({gen}), rule saved"
    base = f"{head}, runbook {steps} steps ({norm}, escalate needs approval), alert count={count}"
    return f"{base}; warning: {'; '.join(warnings)}" if warnings else base


def _api[T: BaseModel](
    ctx: h.RehearsalContext, verb: str, path: str, body: BaseModel, cls: type[T], t: float = 10.0
) -> T:
    url, data = f"{ctx.api_url}/api/v1{path}", body.model_dump(mode="json")
    resp = ctx.client.request(verb, url, json=data, timeout=t)
    if resp.status_code != 200:
        raise h.RehearsalError(f"{verb} {path} returned {resp.status_code}: {resp.text[:200]}")
    return cls.model_validate(resp.json())


def _step_unknown_and_profile(
    ctx: h.RehearsalContext, sample: dict[str, Any], rid: str, disc: str
) -> tuple[str, list[str]]:
    target, url = shape_hash(sample), f"{ctx.api_url}/api/v1/unknown-schemas"
    before = ctx.client.get(url)
    if before.status_code not in (200, 404):
        raise h.RehearsalError(f"GET /api/v1/unknown-schemas returned {before.status_code}")
    raw = before.json() if before.status_code == 200 else []
    prev = next((int(x["event_count"]) for x in raw if x.get("shape_hash") == target), 0)
    acc = h.post_ingest(ctx, "generic-webhook", sample)
    if len(acc.event_ids) != 1 or acc.duplicate_count != 0:
        raise h.RehearsalError(f"unexpected sample ingest: {acc.model_dump()}")
    warns: list[str] = []
    if before.status_code == 404:
        warns.append("unknown-schemas inbox endpoint unavailable")
    else:

        def in_inbox() -> api.UnknownSchemaSample | None:
            items = [api.UnknownSchemaSample.model_validate(x) for x in h.get_json(ctx, url)]
            return next((s for s in items if s.shape_hash == target and s.event_count > prev), None)

        h.poll_until(in_inbox, timeout=ctx.timeout, reason=f"sample {target[:8]} not in inbox")
    req = api.SchemaProfileProposeRequest(sample_event=sample, profile_id=rid)
    prop = _api(ctx, "POST", "/schema-profiles/propose", req, SchemaProfileProposal, LLM_TIMEOUT)
    if prop.generated_by == "heuristic":
        warns.append("profile generated by heuristic")
    profile = prepare_proposed_profile(prop, rid, disc)
    treq = api.SchemaProfileTestRequest(schema_profile=profile, window="1h", sample_event=sample)
    tres = _api(ctx, "POST", "/schema-profiles/test", treq, api.SchemaProfileTestResult)
    assert_profile_test_matched_sample(tres)
    wreq = api.SchemaProfileWrite(schema_profile=profile, actor=JUDGES_ACTOR)
    _api(ctx, "PUT", f"/schema-profiles/{rid}", wreq, api.SchemaProfileRecord)
    return prop.generated_by, warns


def _step_rule_runbook_reload(ctx: h.RehearsalContext, run_id: str, cln: dict[str, Any]) -> Runbook:
    rule = build_judges_rule(run_id)
    _api(ctx, "POST", "/rules/preview", api.RulePreviewRequest(rule=rule), api.RulePreview)
    wreq = api.RuleWrite(rule=rule, actor=JUDGES_ACTOR)
    cln["rule"] = _api(ctx, "PUT", f"/rules/{rule.id}", wreq, api.RuleRecord).rule
    cfg = api.ConfigLists.model_validate(h.get_json(ctx, f"{ctx.api_url}/api/v1/config"))
    rb_w = build_judges_runbook_write(run_id)
    rb = _api(ctx, "PUT", f"/runbooks/{rule.id}", rb_w, Runbook, LLM_TIMEOUT)
    assert_normalized_runbook(rb, {a.id: a for a in cfg.actions})

    def is_reloaded() -> bool:
        base = f"{ctx.api_url}/api/v1"
        if not any(x["id"] == rule.id for x in h.get_json(ctx, f"{base}/schema-profiles")):
            raise h.RehearsalError(f"schema profile {rule.id} not visible")
        rec = api.RuleRecord.model_validate(h.get_json(ctx, f"{base}/rules/{rule.id}"))
        if not rec.rule.enabled:
            raise h.RehearsalError(f"rule {rule.id} not enabled")
        return bool(Runbook.model_validate(h.get_json(ctx, f"{base}/runbooks/{rule.id}")))

    h.poll_until(is_reloaded, timeout=ctx.timeout, reason=f"hot reload did not pick up {rule.id}")
    return rb


def _step_live_events(
    ctx: h.RehearsalContext, rid: str, events: list[dict[str, Any]], cln: dict[str, Any]
) -> alerts.Alert:
    for event in events:
        acc = h.post_ingest(ctx, "generic-webhook", event)
        if len(acc.event_ids) != 1 or acc.duplicate_count != 0:
            raise h.RehearsalError(f"unexpected live ingest: {acc.model_dump()}")

    def probe_alert() -> alerts.Alert | None:
        matches = [
            a for a in h.list_team_alerts(ctx, JUDGES_TEAM, status="open").items if a.rule_id == rid
        ]
        if len(matches) > 1 or (len(matches) == 1 and matches[0].count > 2):
            raise h.FatalPollError(f"bad alert state for {rid}: {[a.count for a in matches]}")
        if len(matches) == 1:
            cln["alert_id"] = matches[0].id
            if matches[0].count == 2:
                return matches[0]
        raise h.RehearsalError(f"open alerts for {rid}: {[a.count for a in matches]}")

    alert = h.poll_until(probe_alert, timeout=ctx.timeout, reason=f"alert {rid} count != 2")
    assert_judges_alert(alert, rid)

    def probe_delivered() -> bool:
        dels = h.get_alert_detail(ctx, alert.id).deliveries
        if any(d.status is alerts.DeliveryStatus.dead_lettered for d in dels):
            raise h.FatalPollError(f"delivery dead-lettered for alert {alert.id}")
        if dels and all(d.status.value in h.DELIVERED_STATUSES for d in dels):
            return True
        raise h.RehearsalError(f"pending: {[d.status.value for d in dels]}")

    h.poll_until(probe_delivered, timeout=ctx.timeout, reason=f"deliveries for {alert.id} pending")
    return alert


def scene_judges_path(ctx: h.RehearsalContext) -> h.SceneResult:
    """Scene 9: simulate judges bringing an unseen schema and free-text runbook end-to-end."""

    def body() -> str:
        rid, disc = judges_resource_id(ctx.run_id), judges_discriminator(ctx.run_id)
        sample, live = build_judges_samples(ctx.run_id)
        cln: dict[str, Any] = {"rule": None, "alert_id": None}
        try:
            gen, warns = _step_unknown_and_profile(ctx, sample, rid, disc)
            rb = _step_rule_runbook_reload(ctx, ctx.run_id, cln)
            alert = _step_live_events(ctx, rid, live, cln)
            return format_judges_detail(
                rid, gen, len(rb.steps), rb.normalized_by, alert.count, warnings=warns
            )
        finally:
            calls: list[tuple[str, str, BaseModel]] = []
            if (r := cln["rule"]) is not None:
                rw = api.RuleWrite(rule=r.model_copy(update={"enabled": False}), actor=JUDGES_ACTOR)
                calls.append(("PUT", f"/rules/{r.id}", rw))
            if (aid := cln["alert_id"]) is not None:
                res = api.AlertResolveRequest(actor=JUDGES_ACTOR, comment="judges_path cleanup")
                calls.append(("POST", f"/alerts/{aid}/resolve", res))
            for verb, path, payload in calls:
                try:
                    url, data = f"{ctx.api_url}/api/v1{path}", payload.model_dump(mode="json")
                    ctx.client.request(verb, url, json=data)
                except httpx.HTTPError:
                    pass

    return h.run_scene("judges_path", body)
