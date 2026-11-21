"""Automated demo rehearsal walking every scene in docs/demo.md against the running stack.

Usage:
  uv run python scripts/demo_rehearsal.py [--only scene1,scene2] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import yaml
from alerting_contracts.api import RulePreview, RuleRecord
from demo_rehearsal_helpers import (
    DELIVERED_STATUSES,
    FatalPollError,
    RehearsalContext,
    RehearsalError,
    SceneResult,
    build_batches,
    format_markdown_table,
    fresh_rates_event,
    get_alert_detail,
    get_json,
    list_team_alerts,
    make_stricter_rates_rule,
    parse_only_scenes,
    poll_until,
    post_ingest,
    post_ingest_batch,
    run_scene,
)
from demo_rehearsal_judges import scene_judges_path
from demo_rehearsal_scenes import (
    scene_alertmanager_resolve,
    scene_metrics_summary,
    scene_runbook_approval_by_code,
    scene_sms_outage_no_loss,
)

RATES_RULE_ID = "rates-large-rejections"
DEDUP_TOTAL = 500
DEDUP_BATCH_SIZE = 100
DEDUP_TIMEOUT_SECONDS = 60.0


def scene_health(ctx: RehearsalContext) -> SceneResult:
    """Scene 1: verify api, ingest, mock-gateway, and Mailpit answer 200."""

    def body() -> str:
        targets = [
            ("api", f"{ctx.api_url}/healthz"),
            ("ingest", f"{ctx.ingest_url}/healthz"),
            ("mock-gateway", f"{ctx.gateway_url}/healthz"),
            ("mailpit", f"{ctx.mailpit_url}/api/v1/messages"),
        ]
        failures: list[str] = []
        for label, url in targets:
            try:
                response = ctx.client.get(url)
                if response.status_code != 200:
                    failures.append(f"{label}={response.status_code}")
            except httpx.HTTPError as exc:
                failures.append(f"{label}={type(exc).__name__}")
        if failures:
            raise RehearsalError(f"unhealthy endpoints: {', '.join(failures)}")
        return "api, ingest, mock-gateway, mailpit all 200"

    return run_scene("health", body)


def _find_open_rates_alert(ctx: RehearsalContext, reason: str) -> Any:
    page = list_team_alerts(ctx, "rates", status="open")
    matches = [a for a in page.items if a.last_event.get("payload", {}).get("reason") == reason]
    return matches[0] if matches else None


def anna_expects_email(now: datetime | None = None) -> bool:
    """Anna gets rates errors by sms/phone 08:00-20:00 Europe/Warsaw, email otherwise.

    Mirrors config/recipients/anna.yaml so the scene passes at any time of day (we record by day).
    """
    local = (now or datetime.now(UTC)).astimezone(ZoneInfo("Europe/Warsaw"))
    return not (8 <= local.hour < 20)


def _probe_channel_delivered(ctx: RehearsalContext, alert_id: str, channel: str) -> bool:
    detail = get_alert_detail(ctx, alert_id)
    if any(
        d.channel_type.value == channel and d.status.value in DELIVERED_STATUSES
        for d in detail.deliveries
    ):
        return True
    seen = [f"{d.channel_type.value}:{d.status.value}" for d in detail.deliveries]
    raise RehearsalError(f"no delivered {channel}; seen deliveries={seen}")


def _probe_mailpit_query(ctx: RehearsalContext, query: str) -> bool:
    data = get_json(ctx, f"{ctx.mailpit_url}/api/v1/search", query=query)
    return int(data.get("messages_count", len(data.get("messages", [])))) > 0


def scene_rates_alert_and_email(ctx: RehearsalContext) -> SceneResult:
    """Scene 2: ingest fresh rates event, check open alert, email delivery, and Mailpit message."""

    def body() -> str:
        event, reason, trade_id = fresh_rates_event(ctx.run_id, "email")
        accepted = post_ingest(ctx, "rates-oms", event)
        if len(accepted.event_ids) != 1 or accepted.duplicate_count != 0:
            raise RehearsalError(f"unexpected ingest response: {accepted.model_dump()}")
        alert = poll_until(
            lambda: _find_open_rates_alert(ctx, reason),
            timeout=ctx.timeout,
            reason=f"open rates alert for {reason} not found",
        )
        channel = "email" if anna_expects_email() else "sms"
        poll_until(
            lambda: _probe_channel_delivered(ctx, alert.id, channel),
            timeout=ctx.timeout,
            reason=f"no delivered {channel} for rates alert {alert.id}",
        )
        if channel == "sms":  # working hours: Anna's preference routes to sms/phone, no email
            return f"alert {alert.id[-8:]} open, sms delivered (Anna's working hours)"
        poll_until(
            lambda: _probe_mailpit_query(ctx, trade_id),
            timeout=ctx.timeout,
            reason=f"no Mailpit email mentioning {trade_id}",
        )
        return f"alert {alert.id[-8:]} open, email delivered, Mailpit matched {trade_id}"

    return run_scene("rates_alert_and_email", body)


def scene_rule_preview(ctx: RehearsalContext) -> SceneResult:
    """Scene 3: preview current rates YAML (>= 1 match) and a stricter threshold (<= matches)."""

    def body() -> str:
        record = RuleRecord.model_validate(
            get_json(ctx, f"{ctx.api_url}/api/v1/rules/{RATES_RULE_ID}")
        )
        current_rule = yaml.safe_load(record.yaml)
        stricter_rule = make_stricter_rates_rule(current_rule)
        url = f"{ctx.api_url}/api/v1/rules/preview"

        base_resp = ctx.client.post(url, json={"rule": current_rule, "window": "1h"})
        if base_resp.status_code != 200:
            raise RehearsalError(f"baseline preview returned {base_resp.status_code}")
        baseline = RulePreview.model_validate(base_resp.json())
        if baseline.events_matched < 1:
            raise RehearsalError(
                f"baseline events_matched={baseline.events_matched}, expected >= 1 "
                f"(scanned={baseline.events_scanned})"
            )
        strict_resp = ctx.client.post(url, json={"rule": stricter_rule, "window": "1h"})
        if strict_resp.status_code != 200:
            raise RehearsalError(f"stricter preview returned {strict_resp.status_code}")
        stricter = RulePreview.model_validate(strict_resp.json())
        if stricter.events_matched > baseline.events_matched:
            raise RehearsalError(
                f"stricter matched {stricter.events_matched} > baseline {baseline.events_matched}"
            )
        return (
            f"matched={baseline.events_matched}, stricter={stricter.events_matched} "
            f"(scanned={baseline.events_scanned})"
        )

    return run_scene("rule_preview", body)


def _probe_dedup_settled(ctx: RehearsalContext, reason: str, expected: int) -> Any:
    page = list_team_alerts(ctx, "rates")
    matches = [a for a in page.items if a.last_event.get("payload", {}).get("reason") == reason]
    if len(matches) > 1:
        raise FatalPollError(f"expected 1 alert for {reason}, got {len(matches)}")
    if len(matches) == 1 and matches[0].count > expected:
        raise FatalPollError(f"alert count exceeded {expected}: {matches[0].count}")
    if len(matches) == 1 and matches[0].count == expected:
        return matches[0]
    counts = [a.count for a in matches]
    raise RehearsalError(f"last seen {len(matches)} alert(s), counts={counts}")


def scene_dedup_500(ctx: RehearsalContext) -> SceneResult:
    """Scene 4: ingest 500 identical events via batch endpoint and assert 1 alert with count 500."""

    def body() -> str:
        event, reason, _ = fresh_rates_event(ctx.run_id, "dedup500")
        batches = build_batches(event, total=DEDUP_TOTAL, batch_size=DEDUP_BATCH_SIZE)
        accepted_total = 0
        duplicate_total = 0
        for batch in batches:
            res = post_ingest_batch(ctx, "rates-oms", batch)
            accepted_total += len(res.event_ids)
            duplicate_total += res.duplicate_count
        if accepted_total != DEDUP_TOTAL or duplicate_total != 0:
            raise RehearsalError(
                f"batch ingest accepted={accepted_total}, duplicates={duplicate_total}"
            )
        alert = poll_until(
            lambda: _probe_dedup_settled(ctx, reason, DEDUP_TOTAL),
            timeout=DEDUP_TIMEOUT_SECONDS,
            reason=f"expected 1 alert with count {DEDUP_TOTAL}",
        )
        return f"1 alert ({alert.id[-8:]}), count={alert.count} across {len(batches)} batches"

    return run_scene("dedup_500", body)


SCENES: dict[str, Callable[[RehearsalContext], SceneResult]] = {
    "health": scene_health,
    "rates_alert_and_email": scene_rates_alert_and_email,
    "rule_preview": scene_rule_preview,
    "dedup_500": scene_dedup_500,
    "sms_outage_no_loss": scene_sms_outage_no_loss,
    "runbook_approval_by_code": scene_runbook_approval_by_code,
    "metrics_summary": scene_metrics_summary,
    "alertmanager_resolve": scene_alertmanager_resolve,
    "judges_path": scene_judges_path,
}


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", default=None, help="comma-separated scene names to run")
    parser.add_argument("--api", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--ingest", default="http://localhost:8001", help="Ingest base URL")
    parser.add_argument("--gateway", default="http://localhost:8090", help="Mock gateway URL")
    parser.add_argument("--mailpit", default="http://localhost:8025", help="Mailpit base URL")
    parser.add_argument("--json", dest="json_path", default=None, help="Write JSON report to path")
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-poll timeout in seconds")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint returning 0 only when every selected scene passes."""
    args = build_parser().parse_args(argv)
    try:
        selected = parse_only_scenes(args.only, list(SCENES))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    run_id = uuid.uuid4().hex[:8]
    with httpx.Client(timeout=10.0) as client:
        ctx = RehearsalContext(
            api_url=args.api.rstrip("/"),
            ingest_url=args.ingest.rstrip("/"),
            gateway_url=args.gateway.rstrip("/"),
            mailpit_url=args.mailpit.rstrip("/"),
            timeout=args.timeout,
            run_id=run_id,
            client=client,
        )
        results = [SCENES[name](ctx) for name in selected]

    print(format_markdown_table(results))
    if args.json_path:
        report = {
            "run_id": run_id,
            "passed": all(r.passed for r in results),
            "scenes": [r.to_dict() for r in results],
        }
        Path(args.json_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
