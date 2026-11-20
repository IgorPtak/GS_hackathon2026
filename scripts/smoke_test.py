"""Per-gate smoke test against the running compose stack.

Usage: uv run python scripts/smoke_test.py --gate {3h,7h,11h,14h} [--timeout 15]

Gates are cumulative: --gate 7h runs the 3h checks too. Every check prints one line and a
failed check exits non-zero with its one-line reason.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from alerting_contracts.api import AlertDetail, AlertPage, IngestAccepted, PhoneReplyResult

FIXTURES = Path(__file__).resolve().parent.parent / "contracts" / "fixtures" / "events"
GATES = ["3h", "7h", "11h", "14h"]
RATES_SOURCE = "rates-oms"
RATES_RULE_ID = "rates-large-rejections"
SETTLEMENTS_SOURCE = "settlements-engine"
RATES_RULE_ID = "rates-large-rejections"
WORKFLOW_ID = "wf-settle-20261120-0042"
ACTOR = {"id": "system:smoke-test"}
WORKERS = {"processor": 9101, "outbox-relay": 9102, "delivery": 9103, "runbook-runner": 9104}


class CheckFailed(Exception):
    """Raised by a check with the one-line reason."""


class CheckSkipped(Exception):
    """Raised by a check that cannot run in the current setup."""


@dataclass
class Ctx:
    base_url: str
    ingest_url: str
    mailpit_url: str
    gateway_url: str
    timeout: float
    log_file: str | None
    run_id: str
    client: httpx.Client
    state: dict[str, Any]


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def poll(ctx: Ctx, probe: Callable[[], Any], reason: str) -> Any:
    """Call probe until it returns a truthy value or the timeout passes."""
    deadline = time.monotonic() + ctx.timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            value = probe()
            if value:
                return value
        except (httpx.HTTPError, ValueError, CheckFailed) as exc:
            last = f" ({type(exc).__name__}: {exc})"
        time.sleep(0.5)
    raise CheckFailed(f"{reason} within {ctx.timeout:g}s{last}")


def get_json(ctx: Ctx, url: str, **params: Any) -> Any:
    response = ctx.client.get(url, params=params)
    if response.status_code != 200:
        raise CheckFailed(f"GET {url} returned {response.status_code}")
    return response.json()


def post_event(ctx: Ctx, source_id: str, payload: dict[str, Any], times: int = 1) -> None:
    # No Idempotency-Key: contracts v1 only drops duplicates when a key is present.
    for _ in range(times):
        try:
            response = ctx.client.post(f"{ctx.ingest_url}/api/v1/ingest/{source_id}", json=payload)
        except httpx.HTTPError as exc:
            raise CheckFailed(f"POST ingest/{source_id} failed: {type(exc).__name__}") from exc
        if response.status_code != 202:
            raise CheckFailed(
                f"POST ingest/{source_id} returned {response.status_code}, expected 202"
            )
        IngestAccepted.model_validate(response.json())


def rates_event(ctx: Ctx, label: str) -> tuple[dict[str, Any], str]:
    """Rates fixture with a fresh tradeId, so dedup from earlier runs cannot collide."""
    event = fixture("rates_trade_rejected.json")
    trade_id = f"T-SMOKE-{ctx.run_id}-{label}"
    event["payload"]["tradeId"] = trade_id
    return event, trade_id


def settlements_event(ctx: Ctx) -> dict[str, Any]:
    event = fixture("settlements_workflow_failed.json")
    # Same workflowId on purpose (the runbook check needs it); vary a harmless field.
    event["error"]["message"] = f"{event['error']['message']} [smoke {ctx.run_id}]"
    return event


def find_alert(ctx: Ctx, team: str, matches: Callable[[dict[str, Any]], bool]) -> Any:
    page = AlertPage.model_validate(
        get_json(ctx, f"{ctx.base_url}/api/v1/alerts", team=team, limit=200)
    )
    found = [a for a in page.items if matches(a.last_event)]
    return max(found, key=lambda a: a.updated_at) if found else None


def alert_detail(ctx: Ctx, alert_id: str) -> AlertDetail:
    return AlertDetail.model_validate(get_json(ctx, f"{ctx.base_url}/api/v1/alerts/{alert_id}"))


def trade_matcher(trade_id: str) -> Callable[[dict[str, Any]], bool]:
    return lambda event: event.get("payload", {}).get("tradeId") == trade_id


def workflow_matcher(ctx: Ctx) -> Callable[[dict[str, Any]], bool]:
    marker = f"[smoke {ctx.run_id}]"
    return lambda event: (
        event.get("workflowId") == WORKFLOW_ID
        and marker in event.get("error", {}).get("message", "")
    )


# ---------------------------------------------------------------- 3h


def make_healthz_check(url: str) -> Callable[[Ctx], str]:
    def check(ctx: Ctx) -> str:
        try:
            response = ctx.client.get(url)
        except httpx.HTTPError as exc:
            raise CheckFailed(f"{url} unreachable ({type(exc).__name__})") from exc
        if response.status_code != 200:
            raise CheckFailed(f"{url} returned {response.status_code}")
        return "ok"

    return check


def make_worker_healthz_check(service: str, port: int) -> Callable[[Ctx], str]:
    """Worker ports are not published to the host, so ask from inside the container."""

    def check(ctx: Ctx) -> str:
        url = f"http://127.0.0.1:{port}/healthz"
        code = f"import urllib.request; urllib.request.urlopen('{url}', timeout=2)"
        cmd = ["docker", "compose", "-p", "alerting", "exec", "-T", service, "python", "-c", code]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=20, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise CheckSkipped(f"docker compose exec unavailable ({type(exc).__name__})") from exc
        if result.returncode != 0:
            raise CheckFailed(f"{service} /healthz on :{port} failed (container down or unhealthy)")
        return "ok"

    return check


def resolve_open_alerts(ctx: Ctx, team: str, rule_id: str) -> int:
    """Resolve earlier runs' alerts of one rule (best effort; the api may not exist at a gate).

    The fixtures' fingerprints are stable across runs, so without this the smoke event would
    fold into an alert from a previous run: no new notification, no new runbook run.
    """
    try:
        page = AlertPage.model_validate(
            get_json(ctx, f"{ctx.base_url}/api/v1/alerts", team=team, status="open", limit=200)
        )
    except (CheckFailed, httpx.HTTPError, ValueError):
        return 0
    resolved = 0
    for alert in page.items:
        if alert.rule_id != rule_id:
            continue
        url = f"{ctx.base_url}/api/v1/alerts/{alert.id}/resolve"
        body = {"actor": {"id": "smoke-test"}, "comment": f"smoke {ctx.run_id}"}
        try:
            if ctx.client.post(url, json=body).status_code == 200:
                resolved += 1
        except httpx.HTTPError:
            pass
    return resolved


def resolve_open_rates_alerts(ctx: Ctx) -> int:
    return resolve_open_alerts(ctx, "rates", RATES_RULE_ID)


def check_post_rates_fixture(ctx: Ctx) -> str:
    resolve_open_rates_alerts(ctx)
    event, trade_id = rates_event(ctx, "main")
    ctx.state["rates_trade_id"] = trade_id
    post_event(ctx, RATES_SOURCE, event)
    return f"202, tradeId {trade_id}"


def check_post_settlements_fixture(ctx: Ctx) -> str:
    resolve_open_alerts(ctx, "settlements", "settlements-workflow-failed")
    post_event(ctx, SETTLEMENTS_SOURCE, settlements_event(ctx))
    return "202"


def check_log_tail_line(ctx: Ctx) -> str:
    try:
        sources = get_json(ctx, f"{ctx.base_url}/api/v1/config").get("sources", [])
    except CheckFailed as exc:
        raise CheckSkipped("log-tail not configured (config endpoint unavailable)") from exc
    if not any(s.get("id") == "pricing-log" for s in sources):
        raise CheckSkipped("log-tail not configured")
    if not ctx.log_file:
        raise CheckSkipped("pricing-log configured but --log-file not given")
    line = (FIXTURES / "pricing_engine.log").read_text().splitlines()[0]
    with open(ctx.log_file, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return "line appended"


def check_events_recent(ctx: Ctx) -> str:
    trade_id = ctx.state.get("rates_trade_id")
    if trade_id is None:
        raise CheckFailed("rates fixture was not posted")

    def probe() -> bool:
        events = get_json(ctx, f"{ctx.base_url}/api/v1/events/recent", limit=500)
        payloads = [e.get("payload", {}) for e in events]
        has_rates = any(p.get("payload", {}).get("tradeId") == trade_id for p in payloads)
        has_settlements = any(p.get("workflowId") == WORKFLOW_ID for p in payloads)
        return has_rates and has_settlements

    poll(ctx, probe, "events/recent does not list both posted fixtures")
    return "both fixtures listed"


# ---------------------------------------------------------------- 7h


def check_rates_alert_title(ctx: Ctx) -> str:
    # The title needs the fixture values, so only tradeId (not in the title) was varied.
    trade_id = ctx.state["rates_trade_id"]
    alert = poll(ctx, lambda: find_alert(ctx, "rates", trade_matcher(trade_id)), "no rates alert")
    ctx.state["rates_alert_id"] = alert.id
    expected = "Rejected EUR 25000000 — LIMIT_BREACH"
    if alert.title != expected:
        raise CheckFailed(f"rates alert title is {alert.title!r}, expected {expected!r}")
    return alert.title


def check_settlements_alert(ctx: Ctx) -> str:
    alert = poll(
        ctx, lambda: find_alert(ctx, "settlements", workflow_matcher(ctx)), "no settlements alert"
    )
    ctx.state["settlements_alert_id"] = alert.id
    return alert.title


def check_mailpit_email(ctx: Ctx) -> str:
    trade_id = ctx.state["rates_trade_id"]

    def probe() -> bool:
        data = get_json(ctx, f"{ctx.mailpit_url}/api/v1/search", query=trade_id)
        return data.get("messages_count", len(data.get("messages", []))) > 0

    poll(ctx, probe, f"Mailpit has no email mentioning {trade_id}")
    return "email found"


def check_delivery_delivered(ctx: Ctx) -> str:
    alert_id = ctx.state["rates_alert_id"]

    def probe() -> bool:
        detail = alert_detail(ctx, alert_id)
        return any(d.status.value == "delivered" for d in detail.deliveries)

    poll(ctx, probe, "no delivery with status delivered for the rates alert")
    return "delivered"


# ---------------------------------------------------------------- 11h


def check_dedup_count(ctx: Ctx) -> str:
    resolve_open_rates_alerts(ctx)  # same fingerprint as earlier checks: start a fresh alert
    event, trade_id = rates_event(ctx, "dedup")
    post_event(ctx, RATES_SOURCE, event, times=5)

    def probe() -> Any:
        alert = find_alert(ctx, "rates", trade_matcher(trade_id))
        return alert if alert and alert.count >= 5 else None

    alert = poll(ctx, probe, "alert with count 5 not seen")
    if alert.count != 5:
        raise CheckFailed(f"alert count is {alert.count}, expected 5")
    page = AlertPage.model_validate(
        get_json(ctx, f"{ctx.base_url}/api/v1/alerts", team="rates", limit=200)
    )
    matching = [a for a in page.items if trade_matcher(trade_id)(a.last_event)]
    if len(matching) != 1:
        raise CheckFailed(f"{len(matching)} alerts for 5 identical events, expected 1")
    return "one alert, count 5"


def check_rule_hot_reload(ctx: Ctx) -> str:
    url = f"{ctx.base_url}/api/v1/rules/{RATES_RULE_ID}"
    original = get_json(ctx, url)["rule"]
    changed = copy.deepcopy(original)
    marker = f"Smoke {ctx.run_id}"
    changed["present"]["title"] = f"{marker} {{{{payload.currency}}}} {{{{payload.reason}}}}"
    try:
        response = ctx.client.put(url, json={"rule": changed, "actor": ACTOR})
        if response.status_code != 200:
            raise CheckFailed(f"PUT {url} returned {response.status_code}")
        resolve_open_rates_alerts(ctx)  # otherwise the event folds into an older alert
        event, trade_id = rates_event(ctx, "reload")
        post_event(ctx, RATES_SOURCE, event)
        alert = poll(
            ctx,
            lambda: find_alert(ctx, "rates", trade_matcher(trade_id)),
            "no alert after rule change",
        )
        if not alert.title.startswith(marker):
            raise CheckFailed(f"title {alert.title!r} does not use the changed rule")
    finally:
        restore = ctx.client.put(url, json={"rule": original, "actor": ACTOR})
        if restore.status_code != 200:
            print(
                f"warning: could not restore rule {RATES_RULE_ID} ({restore.status_code})",
                file=sys.stderr,
            )
    return "next alert used the new title"


def check_anna_sms(ctx: Ctx) -> str:
    alert_id = ctx.state["settlements_alert_id"]

    def probe() -> bool:
        messages = get_json(
            ctx, f"{ctx.base_url}/api/v1/phone-simulator/messages", recipient_id="anna"
        )
        return any(m["alert_id"] == alert_id and m["channel_type"] == "sms" for m in messages)

    poll(
        ctx,
        probe,
        "no SMS for anna in the phone simulator (she gets SMS only 08:00-20:00 Europe/Warsaw)",
    )
    return "sms listed"


# ---------------------------------------------------------------- 14h


def check_rendered_runbook(ctx: Ctx) -> str:
    alert_id = ctx.state["settlements_alert_id"]

    def probe() -> Any:
        detail = alert_detail(ctx, alert_id)
        return detail if detail.rendered_runbook else None

    detail = poll(ctx, probe, "alert detail has no rendered runbook")
    steps = detail.rendered_runbook.steps
    if not any(WORKFLOW_ID in step.text for step in steps):
        raise CheckFailed(f"no runbook step text contains {WORKFLOW_ID}")
    missing = [f for step in steps for f in step.missing_fields]
    if missing:
        raise CheckFailed(f"runbook has unfilled placeholders: {missing}")
    return f"{len(steps)} steps rendered"


def check_approval_request(ctx: Ctx) -> str:
    alert_id = ctx.state["settlements_alert_id"]

    def probe() -> Any:
        approvals = get_json(
            ctx, f"{ctx.base_url}/api/v1/approvals", team="settlements", is_pending="true"
        )
        mine = [a for a in approvals if a["alert_id"] == alert_id and a["action_id"] == "escalate"]
        return mine[0] if mine else None

    approval = poll(ctx, probe, "no pending approval request for the escalate step")
    ctx.state["approval"] = approval
    return f"code {approval['approval_code']}"


def check_phone_approve(ctx: Ctx) -> str:
    approval = ctx.state["approval"]
    response = ctx.client.post(
        f"{ctx.base_url}/api/v1/phone-simulator/replies",
        # Replies are checked against the sender's teams: settlements is on-call piotr.
        json={"recipient_id": "piotr", "text": f"APPROVE {approval['approval_code']}"},
    )
    if response.status_code != 200:
        raise CheckFailed(f"phone reply returned {response.status_code}")
    result = PhoneReplyResult.model_validate(response.json())
    if not result.is_understood:
        raise CheckFailed(f"phone reply not understood: {result.message}")

    def probe() -> bool:
        detail = alert_detail(ctx, approval["alert_id"])
        return any(
            r.step_index == approval["step_index"] and r.status.value == "succeeded"
            for r in detail.action_runs
        )

    poll(ctx, probe, "escalate action run not succeeded after APPROVE")
    return "action run succeeded"


def check_audit_entry(ctx: Ctx) -> str:
    detail = alert_detail(ctx, ctx.state["settlements_alert_id"])
    if not any(e.verb.value == "approval_decided" for e in detail.audit_entries):
        raise CheckFailed("no approval_decided audit entry")
    return "approval_decided recorded"


# ---------------------------------------------------------------- runner

Check = tuple[str, Callable[[Ctx], str]]


def checks_for(gate: str, ctx: Ctx) -> list[Check]:
    checks: list[Check] = [
        ("healthz api", make_healthz_check(f"{ctx.base_url}/healthz")),
        ("healthz ingest", make_healthz_check(f"{ctx.ingest_url}/healthz")),
        ("healthz mock-gateway", make_healthz_check(f"{ctx.gateway_url}/healthz")),
    ]
    checks += [(f"healthz {s}", make_worker_healthz_check(s, p)) for s, p in WORKERS.items()]
    checks += [
        ("post rates fixture", check_post_rates_fixture),
        ("post settlements fixture", check_post_settlements_fixture),
        ("append log-tail line", check_log_tail_line),
        ("events/recent lists fixtures", check_events_recent),
    ]
    level = GATES.index(gate)
    if level >= 1:
        checks += [
            ("rates alert title", check_rates_alert_title),
            ("settlements alert exists", check_settlements_alert),
            ("mailpit email", check_mailpit_email),
            ("delivery delivered", check_delivery_delivered),
        ]
    if level >= 2:
        checks += [
            ("dedup 5x -> count 5", check_dedup_count),
            ("rule hot reload", check_rule_hot_reload),
            ("anna sms in phone simulator", check_anna_sms),
        ]
    if level >= 3:
        checks += [
            ("runbook rendered", check_rendered_runbook),
            ("approval request for escalate", check_approval_request),
            ("phone APPROVE runs action", check_phone_approve),
            ("audit entry exists", check_audit_entry),
        ]
    return checks


def run_check(ctx: Ctx, check: Callable[[Ctx], str]) -> tuple[str, str]:
    try:
        return "PASS", check(ctx)
    except CheckSkipped as exc:
        return "SKIP", str(exc)
    except CheckFailed as exc:
        return "FAIL", str(exc)
    except KeyError as exc:
        return "FAIL", f"depends on an earlier check that did not pass (missing {exc})"
    except (httpx.HTTPError, ValueError) as exc:
        return "FAIL", f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", choices=GATES, required=True)
    parser.add_argument(
        "--timeout", type=float, default=15.0, help="seconds to wait for async effects"
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--ingest-url", default="http://localhost:8001")
    parser.add_argument("--mailpit-url", default="http://localhost:8025")
    parser.add_argument("--gateway-url", default="http://localhost:8090")
    parser.add_argument("--log-file", default=None, help="file tailed by the pricing-log source")
    args = parser.parse_args()

    failures = 0
    with httpx.Client(timeout=5.0) as client:
        ctx = Ctx(
            base_url=args.base_url.rstrip("/"),
            ingest_url=args.ingest_url.rstrip("/"),
            mailpit_url=args.mailpit_url.rstrip("/"),
            gateway_url=args.gateway_url.rstrip("/"),
            timeout=args.timeout,
            log_file=args.log_file,
            run_id=uuid.uuid4().hex[:8],
            client=client,
            state={},
        )
        checks = checks_for(args.gate, ctx)
        width = max(len(name) for name, _ in checks)
        for name, check in checks:
            status, reason = run_check(ctx, check)
            failures += status == "FAIL"
            print(f"{status:<4}  {name:<{width}}  {reason}")
    print(f"\ngate {args.gate}: {failures} of {len(checks)} checks failed (run {ctx.run_id})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
