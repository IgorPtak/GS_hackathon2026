"""Pure-logic unit tests for `scripts/reset_demo.py` (no live stack)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alerting_contracts.alerts import AlertStatus

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from demo_rehearsal_helpers import RehearsalContext  # noqa: E402
from reset_demo import (  # noqa: E402
    build_parser,
    build_seed_platform_warning,
    build_seed_pricing_event,
    build_seed_rates_event,
    list_all_alerts,
    run_reset,
)

NOW_ISO = datetime(2026, 11, 20, 12, 0, tzinfo=UTC).isoformat()


@dataclass
class FakeResponse:
    """Minimal httpx.Response stand-in for unit tests."""

    status_code: int
    payload: Any

    def json(self) -> Any:
        return self.payload


class FakeClient:
    """In-memory HTTP client recording every method, URL, params, and body."""

    def __init__(self, handler: Callable[[str, str, dict[str, Any], Any], FakeResponse]) -> None:
        self.handler = handler
        self.calls: list[tuple[str, str, dict[str, Any], Any]] = []

    def get(self, url: str, params: dict[str, Any] | None = None) -> FakeResponse:
        call_params = dict(params or {})
        self.calls.append(("GET", url, call_params, None))
        return self.handler("GET", url, call_params, None)

    def post(self, url: str, json: Any = None) -> FakeResponse:
        self.calls.append(("POST", url, {}, json))
        return self.handler("POST", url, {}, json)

    def delete(self, url: str) -> FakeResponse:
        self.calls.append(("DELETE", url, {}, None))
        return self.handler("DELETE", url, {}, None)


def _alert(alert_id: str, *, team: str = "rates", status: str = "open") -> dict[str, Any]:
    return {
        "id": alert_id,
        "rule_id": "rates-large-rejections",
        "team": team,
        "schema_profile_id": "trade-rejected",
        "source_id": "rates-oms",
        "fingerprint": f"fp-{alert_id}",
        "severity": "error",
        "title": f"Alert {alert_id}",
        "count": 1,
        "first_seen": NOW_ISO,
        "last_seen": NOW_ISO,
        "status": status,
        "last_event": {},
        "updated_at": NOW_ISO,
    }


def _ctx(client: FakeClient, run_id: str = "abcd1234") -> RehearsalContext:
    return RehearsalContext(
        api_url="http://api.test",
        ingest_url="http://ingest.test",
        gateway_url="http://gateway.test",
        mailpit_url="http://mailpit.test",
        timeout=5.0,
        run_id=run_id,
        client=client,  # type: ignore[arg-type]
    )


def _approval(approval_id: str, team: str = "settlements") -> dict[str, Any]:
    return {
        "id": approval_id,
        "action_run_id": "run-1",
        "alert_id": "alert-1",
        "team": team,
        "runbook_id": "workflow-failed",
        "step_index": 2,
        "action_id": "escalate",
        "params": {},
        "summary": "Escalate workflow",
        "approval_code": "1234",
        "requested_at": NOW_ISO,
    }


def _proposal(proposal_id: str, team: str = "rates") -> dict[str, Any]:
    return {
        "id": proposal_id,
        "alert_id": "alert-2",
        "rule_id": "rates-large-rejections",
        "owner_team": team,
        "kind": "other",
        "description": "Tune threshold",
        "proposed_by": {"id": "anna"},
        "status": "pending",
        "created_at": NOW_ISO,
    }


def _pricing_rule() -> dict[str, Any]:
    return {
        "kind": "rule",
        "id": "pricing-stale-feed",
        "yaml": "id: pricing-stale-feed\n",
        "version": 1,
        "updated_at": NOW_ISO,
        "rule": {
            "id": "pricing-stale-feed",
            "team": "pricing",
            "enabled": True,
            "when": {"field": "level", "op": "eq", "value": "ERROR"},
            "route": {"channels": ["ui"]},
            "present": {"title": "Stale price {{instrument}}"},
        },
    }


def test_list_all_alerts_pages_through_cursors_and_deduplicates() -> None:
    pages: dict[str | None, dict[str, Any]] = {
        None: {"items": [_alert("a1"), _alert("a2")], "next_cursor": "c2"},
        "c2": {"items": [_alert("a2"), _alert("a3")], "next_cursor": "c3"},
        "c3": {"items": [_alert("a4")], "next_cursor": None},
    }

    def handler(method: str, url: str, params: dict[str, Any], body: Any) -> FakeResponse:
        assert (method, url) == ("GET", "http://api.test/api/v1/alerts")
        assert params["status"] == "open" and params["team"] == "rates" and params["limit"] == 2
        return FakeResponse(200, pages[params.get("cursor")])

    client = FakeClient(handler)
    alerts = list_all_alerts(_ctx(client), team="rates", status=AlertStatus.open, limit=2)
    assert [a.id for a in alerts] == ["a1", "a2", "a3", "a4"]
    assert len(client.calls) == 3


def test_list_all_alerts_guards_against_repeated_cursor() -> None:
    client = FakeClient(
        lambda *_: FakeResponse(200, {"items": [_alert("a1")], "next_cursor": "stuck"})
    )
    alerts = list_all_alerts(_ctx(client), status=AlertStatus.open)
    assert [a.id for a in alerts] == ["a1"]
    assert len(client.calls) == 2


def test_seed_event_builders_produce_fresh_ids_and_valid_shapes() -> None:
    rates_a, reason_a, trade_a = build_seed_rates_event("1111aaaa")
    rates_b, reason_b, trade_b = build_seed_rates_event("2222bbbb")
    assert reason_a != reason_b and trade_a != trade_b
    assert rates_a["payload"]["desk"] == "rates" and rates_a["payload"]["notional"] > 10_000_000

    pricing_a, inst_a = build_seed_pricing_event("1111aaaa")
    pricing_b, inst_b = build_seed_pricing_event("2222bbbb")
    assert inst_a != inst_b and pricing_a["instrument"] == inst_a
    assert pricing_a["service"] == "pricing-engine" and pricing_a["level"] == "ERROR"
    assert pricing_a["msg"].startswith("Price stale") and inst_a in pricing_a["raw_line"]

    am_a, host_a = build_seed_platform_warning("1111aaaa")
    am_b, host_b = build_seed_platform_warning("2222bbbb")
    assert host_a != host_b and am_a["status"] == "firing"
    assert am_a["alerts"][0]["labels"]["instance"] == host_a
    assert am_a["alerts"][0]["labels"]["severity"] == "warning"
    assert am_a["alerts"][0]["fingerprint"] != am_b["alerts"][0]["fingerprint"]


def _config_payload(*teams: str) -> dict[str, Any]:
    return {
        "teams": [{"id": t, "display_name": f"Team {t}", "on_call": []} for t in teams],
        "recipients": [],
        "channels": [],
        "actions": [],
        "sources": [],
    }


def test_dry_run_makes_no_post_or_delete_calls() -> None:
    def handler(method: str, url: str, params: dict[str, Any], body: Any) -> FakeResponse:
        if method != "GET":
            raise AssertionError(f"unexpected mutating call: {method} {url}")
        routes: dict[str, Any] = {
            "http://gateway.test/admin/outage": {"is_down": True, "channels": ["sms"]},
            "http://api.test/api/v1/config": _config_payload("rates", "settlements"),
            "http://mailpit.test/api/v1/messages": {"total": 4, "messages": []},
            "http://api.test/api/v1/rules": [_pricing_rule()],
        }
        if url in routes:
            return FakeResponse(200, routes[url])
        if url == "http://api.test/api/v1/approvals":
            return FakeResponse(
                200, [_approval("ap-1")] if params.get("team") == "settlements" else []
            )
        if url == "http://api.test/api/v1/fix-proposals":
            return FakeResponse(200, [_proposal("fp-1")] if params.get("team") == "rates" else [])
        if url == "http://api.test/api/v1/alerts":
            item = (
                _alert("a-open")
                if params.get("status") == "open"
                else _alert("a-ack", status="acknowledged")
            )
            return FakeResponse(200, {"items": [item], "next_cursor": None})
        raise AssertionError(f"unexpected GET {url} {params}")

    client = FakeClient(handler)
    lines: list[str] = []
    assert run_reset(_ctx(client), seed=True, dry_run=True, printer=lines.append) is True
    assert len(lines) == 6
    assert all(method == "GET" for method, _, _, _ in client.calls)
    assert "would reject 1 approval(s) and 1 fix proposal(s)" in lines[1]
    assert "would resolve 2 alert(s)" in lines[2]
    assert "would delete 4 Mailpit message(s)" in lines[3]
    assert "would seed 3x rates" in lines[4]


def test_real_run_no_seed_sends_expected_actor_and_comment() -> None:
    def handler(method: str, url: str, params: dict[str, Any], body: Any) -> FakeResponse:
        if method == "POST":
            return FakeResponse(200, {})
        if method == "DELETE" and url == "http://mailpit.test/api/v1/messages":
            return FakeResponse(200, {"ok": True})
        if url == "http://api.test/api/v1/config":
            return FakeResponse(200, _config_payload("rates"))
        if url == "http://api.test/api/v1/approvals":
            return FakeResponse(200, [_approval("ap-1", team="rates")])
        if url == "http://api.test/api/v1/fix-proposals":
            return FakeResponse(200, [_proposal("fp-1", team="rates")])
        if url == "http://api.test/api/v1/alerts":
            items = [_alert("a-1")] if params.get("status") == "open" else []
            return FakeResponse(200, {"items": items, "next_cursor": None})
        if url == "http://gateway.test/admin/outage":
            return FakeResponse(200, {"is_down": False, "channels": []})
        raise AssertionError(f"unexpected call: {method} {url}")

    client = FakeClient(handler)
    lines: list[str] = []
    assert run_reset(_ctx(client), seed=False, dry_run=False, printer=lines.append) is True
    assert "skipped (--no-seed)" in lines[4]
    posts = {url: body for method, url, _, body in client.calls if method == "POST"}
    assert posts["http://gateway.test/admin/outage"] == {"is_down": False}
    assert posts["http://api.test/api/v1/approvals/ap-1/decision"]["actor"] == {
        "id": "system:reset-demo"
    }
    assert posts["http://api.test/api/v1/approvals/ap-1/decision"]["comment"] == "Reset before demo"
    assert posts["http://api.test/api/v1/fix-proposals/fp-1/decision"]["decision"] == "reject"
    assert posts["http://api.test/api/v1/alerts/a-1/resolve"] == {
        "actor": {"id": "system:reset-demo"},
        "comment": "Reset before demo",
    }


def test_cli_parser_defaults_and_flags() -> None:
    parser = build_parser()
    defaults = parser.parse_args([])
    assert defaults.seed is True and defaults.dry_run is False
    custom = parser.parse_args(["--no-seed", "--dry-run", "--api", "http://x:8000"])
    assert custom.seed is False and custom.dry_run is True and custom.api == "http://x:8000"
