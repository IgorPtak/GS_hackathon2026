"""Reset and optionally seed the Beacon demo environment via public HTTP APIs.

Usage:
  uv run python scripts/reset_demo.py [--seed/--no-seed] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import demo_rehearsal_helpers as h
import httpx
from alerting_contracts import alerts, api, common, proposals, runbooks

RESET_ACTOR = common.Actor(id="system:reset-demo")
RESET_COMMENT = "Reset before demo"
GATEWAY_SERVICES = ("settlement-engine", "pricing-adapter", "pricing-engine")
RATES_SEED_COUNT = 3
PRICING_GROUP_TIMEOUT_SECONDS = 25.0


def list_all_alerts(
    ctx: h.RehearsalContext,
    *,
    team: str | None = None,
    status: alerts.AlertStatus | None = None,
    limit: int = 200,
) -> list[alerts.Alert]:
    """Page through `GET /api/v1/alerts` until `next_cursor` is exhausted."""
    items, seen_ids, seen_cursors, cursor = [], set(), set(), None
    url = f"{ctx.api_url}/api/v1/alerts"
    base_params: dict[str, Any] = {"limit": limit}
    if team is not None:
        base_params["team"] = team
    if status is not None:
        base_params["status"] = status.value
    while True:
        params = base_params | ({"cursor": cursor} if cursor is not None else {})
        page = api.AlertPage.model_validate(h.get_json(ctx, url, **params))
        for item in page.items:
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                items.append(item)
        if not page.next_cursor or page.next_cursor in seen_cursors:
            break
        seen_cursors.add(page.next_cursor)
        cursor = page.next_cursor
    return items


def build_seed_rates_event(run_id: str) -> tuple[dict[str, Any], str, str]:
    """Build a fresh rates trade-rejected event for seeding."""
    return h.fresh_rates_event(run_id, "seed")


def build_seed_pricing_event(run_id: str) -> tuple[dict[str, Any], str]:
    """Build a fresh pricing stale-feed event with a unique instrument."""
    event = h.load_fixture("pricing_price_stale.json")
    inst, now = f"EURUSD-{run_id}", datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = (
        f"{now} ERROR pricing-engine instrument={inst} "
        f'feed={event["feed"]} age_ms={event["age_ms"]} msg="{event["msg"]}"'
    )
    event.update(timestamp=now, instrument=inst, raw_line=line)
    return event, inst


def build_seed_platform_warning(run_id: str) -> tuple[dict[str, Any], str]:
    """Build a fresh firing Alertmanager warning payload for Team Platform."""
    firing, _, instance = h.fresh_alertmanager_events(run_id)
    firing["alerts"][0]["labels"]["severity"] = "warning"
    return firing, instance


def _team_ids(ctx: h.RehearsalContext) -> list[str]:
    cfg = api.ConfigLists.model_validate(h.get_json(ctx, f"{ctx.api_url}/api/v1/config"))
    return [team.id for team in cfg.teams]


def _post_idempotent(ctx: h.RehearsalContext, url: str, body: dict[str, Any]) -> bool:
    """POST `body` to `url`; return True on 200, False on 409 (already done), raise otherwise."""
    response = ctx.client.post(url, json=body)
    if response.status_code in (200, 409):
        return response.status_code == 200
    raise h.RehearsalError(f"POST {url} returned {response.status_code}")


def step_restore_gateway(ctx: h.RehearsalContext, *, dry_run: bool) -> str:
    """Step 1: clear mock-gateway outage and mark known services healthy."""
    services = ", ".join(GATEWAY_SERVICES)
    if dry_run:
        is_down = h.get_json(ctx, f"{ctx.gateway_url}/admin/outage").get("is_down")
        return f"[dry-run] would set outage=false (current={is_down}), healthy=[{services}]"
    h.set_gateway_outage(ctx, is_down=False)
    for name in GATEWAY_SERVICES:
        h.set_service_health(ctx, name, is_healthy=True)
    return f"outage=off, healthy=[{services}]"


def step_reject_pending(ctx: h.RehearsalContext, *, dry_run: bool) -> str:
    """Step 2: reject pending approvals and fix proposals across every team."""
    base, teams = f"{ctx.api_url}/api/v1", _team_ids(ctx)
    ap_ids = {
        runbooks.ApprovalRequest.model_validate(r).id
        for t in teams
        for r in h.get_json(ctx, f"{base}/approvals", team=t, is_pending="true")
    }
    fp_ids = {
        proposals.FixProposal.model_validate(r).id
        for t in teams
        for r in h.get_json(ctx, f"{base}/fix-proposals", team=t, status="pending")
    }
    if dry_run:
        return (
            f"[dry-run] would reject {len(ap_ids)} approval(s) and "
            f"{len(fp_ids)} fix proposal(s) across {len(teams)} team(s)"
        )
    ap_body = api.ApprovalDecisionRequest(
        decision=runbooks.ApprovalDecision.reject,
        actor=RESET_ACTOR,
        via=runbooks.ApprovalVia.ui,
        comment=RESET_COMMENT,
    ).model_dump(mode="json", exclude_none=True)
    fp_body = api.FixProposalDecisionRequest(
        decision="reject", actor=RESET_ACTOR, comment=RESET_COMMENT
    ).model_dump(mode="json", exclude_none=True)
    n_ap = sum(_post_idempotent(ctx, f"{base}/approvals/{i}/decision", ap_body) for i in ap_ids)
    n_fp = sum(_post_idempotent(ctx, f"{base}/fix-proposals/{i}/decision", fp_body) for i in fp_ids)
    return f"rejected {n_ap} approval(s), {n_fp} fix proposal(s)"


def step_resolve_alerts(ctx: h.RehearsalContext, *, dry_run: bool) -> str:
    """Step 3: resolve every open or acknowledged alert via the public API."""
    open_a = list_all_alerts(ctx, status=alerts.AlertStatus.open)
    ack_a = list_all_alerts(ctx, status=alerts.AlertStatus.acknowledged)
    active, counts = open_a + ack_a, f"({len(open_a)} open, {len(ack_a)} acknowledged)"
    if dry_run:
        return f"[dry-run] would resolve {len(active)} alert(s) {counts}"
    body = api.AlertResolveRequest(actor=RESET_ACTOR, comment=RESET_COMMENT).model_dump(
        mode="json", exclude_none=True
    )
    n = sum(
        _post_idempotent(ctx, f"{ctx.api_url}/api/v1/alerts/{a.id}/resolve", body) for a in active
    )
    return f"resolved {n} alert(s) {counts}"


def step_clear_mailpit(ctx: h.RehearsalContext, *, dry_run: bool) -> str:
    """Step 4: clear the Mailpit demo inbox."""
    url = f"{ctx.mailpit_url}/api/v1/messages"
    if dry_run:
        data = h.get_json(ctx, url)
        total = int(data.get("total", len(data.get("messages", []))))
        return f"[dry-run] would delete {total} Mailpit message(s)"
    response = ctx.client.delete(url)
    if response.status_code not in (200, 204):
        raise h.RehearsalError(f"DELETE {url} returned {response.status_code}")
    return "cleared mailbox"


def _wait_seeded(ctx: h.RehearsalContext, reason: str, inst: str | None, host: str) -> list[str]:
    def wait(
        team: str, pred: Callable[[alerts.Alert], bool], timeout: float, why: str
    ) -> alerts.Alert:
        return h.poll_until(
            lambda: next(
                (a for a in h.list_team_alerts(ctx, team, status="open").items if pred(a)), None
            ),
            timeout=timeout,
            reason=why,
        )

    rates = wait(
        "rates",
        lambda a: (
            a.last_event.get("payload", {}).get("reason") == reason and a.count == RATES_SEED_COUNT
        ),
        ctx.timeout,
        f"seeded rates ({reason}) count!={RATES_SEED_COUNT}",
    )
    plat = wait(
        "platform",
        lambda a: (
            a.last_event.get("labels", {}).get("instance") == host
            and a.severity is common.Severity.warning
        ),
        ctx.timeout,
        f"seeded platform warning ({host}) missing",
    )
    parts = [f"rates={rates.id[-8:]}(x{rates.count})", f"platform={plat.id[-8:]}(warning)"]
    if inst is not None:
        pr = wait(
            "pricing",
            lambda a: a.group_key == inst or a.last_event.get("instrument") == inst,
            max(ctx.timeout, PRICING_GROUP_TIMEOUT_SECONDS),
            f"seeded pricing ({inst}) missing",
        )
        parts.append(f"pricing={pr.id[-8:]}({pr.severity.value})")
    return parts


def step_seed_events(ctx: h.RehearsalContext, *, seed: bool, dry_run: bool) -> str:
    """Step 5: optionally seed fresh rates, pricing, and platform warning alerts."""
    if not seed:
        return "skipped (--no-seed)"
    rates_evt, reason, _ = build_seed_rates_event(ctx.run_id)
    has_pricing = any(
        api.RuleRecord.model_validate(r).rule.enabled
        for r in h.get_json(ctx, f"{ctx.api_url}/api/v1/rules", team="pricing")
    )
    pricing_pair = build_seed_pricing_event(ctx.run_id) if has_pricing else None
    plat_evt, host = build_seed_platform_warning(ctx.run_id)
    if dry_run:
        p_desc = f"1 pricing ({pricing_pair[1]})" if pricing_pair else "0 pricing (no rule)"
        return (
            f"[dry-run] would seed {RATES_SEED_COUNT}x rates ({reason}), "
            f"{p_desc}, 1 platform warning ({host})"
        )
    for _ in range(RATES_SEED_COUNT):
        h.post_ingest(ctx, "rates-oms", rates_evt)
    if pricing_pair is not None:
        h.post_ingest(ctx, "generic-webhook", pricing_pair[0])
    h.post_ingest(ctx, "alertmanager", plat_evt)
    return ", ".join(_wait_seeded(ctx, reason, pricing_pair[1] if pricing_pair else None, host))


def step_report_state(ctx: h.RehearsalContext) -> str:
    """Step 6: report open alerts per team, pending approvals, and gateway state."""
    teams = _team_ids(ctx)
    counts = dict.fromkeys(teams, 0)
    for alert in list_all_alerts(ctx, status=alerts.AlertStatus.open):
        counts[alert.team] = counts.get(alert.team, 0) + 1
    pending = sum(
        len(h.get_json(ctx, f"{ctx.api_url}/api/v1/approvals", team=t, is_pending="true"))
        for t in teams
    )
    gw = "down" if h.get_json(ctx, f"{ctx.gateway_url}/admin/outage").get("is_down") else "healthy"
    per_team = ", ".join(f"{t}={counts[t]}" for t in sorted(counts))
    return f"open_alerts=[{per_team}], pending_approvals={pending}, gateway={gw}"


def run_reset(
    ctx: h.RehearsalContext,
    *,
    seed: bool = True,
    dry_run: bool = False,
    printer: Callable[[str], None] = print,
) -> bool:
    """Execute all 6 reset steps, printing one line per step; return True iff all succeed."""
    steps = (
        ("Restore gateway", lambda: step_restore_gateway(ctx, dry_run=dry_run)),
        ("Reject pending approvals", lambda: step_reject_pending(ctx, dry_run=dry_run)),
        ("Resolve open alerts", lambda: step_resolve_alerts(ctx, dry_run=dry_run)),
        ("Clear Mailpit", lambda: step_clear_mailpit(ctx, dry_run=dry_run)),
        ("Seed demo events", lambda: step_seed_events(ctx, seed=seed, dry_run=dry_run)),
        ("Final state", lambda: step_report_state(ctx)),
    )
    all_ok = True
    for i, (label, fn) in enumerate(steps, start=1):
        try:
            printer(f"[{i}/{len(steps)}] {label}: {fn()}")
        except (h.RehearsalError, httpx.HTTPError, ValueError, KeyError) as exc:
            all_ok = False
            printer(f"[{i}/{len(steps)}] {label}: FAIL - {exc}")
    return all_ok


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--ingest", default="http://localhost:8001")
    p.add_argument("--gateway", default="http://localhost:8090")
    p.add_argument("--mailpit", default="http://localhost:8025")
    p.add_argument("--timeout", type=float, default=20.0)
    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint returning 0 only when every reset step succeeds."""
    args = build_parser().parse_args(argv)
    urls = (args.api, args.ingest, args.gateway, args.mailpit)
    with httpx.Client(timeout=10.0) as client:
        ctx = h.RehearsalContext(
            *(u.rstrip("/") for u in urls), args.timeout, uuid.uuid4().hex[:8], client
        )
        return 0 if run_reset(ctx, seed=args.seed, dry_run=args.dry_run) else 1


if __name__ == "__main__":
    sys.exit(main())
