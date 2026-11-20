"""Pure helpers, HTTP wrappers, and formatting for the automated demo rehearsal."""

from __future__ import annotations

import copy
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
from alerting_contracts.api import AlertDetail, AlertPage, IngestAccepted
from smoke_test import fixture as load_fixture

DELIVERED_STATUSES = frozenset({"sent", "delivered"})


class RehearsalError(Exception):
    """Raised when a rehearsal check fails with a human-readable reason."""


class FatalPollError(RehearsalError):
    """Raised inside a poll probe to stop polling immediately instead of waiting for timeout."""


@dataclass(frozen=True, slots=True)
class SceneResult:
    """Outcome of one rehearsal scene."""

    name: str
    passed: bool
    detail: str
    duration: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize for `--json` output."""
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "duration": round(self.duration, 3),
        }


@dataclass
class RehearsalContext:
    """Shared URLs, HTTP client, run identifier, and cross-scene state."""

    api_url: str
    ingest_url: str
    gateway_url: str
    mailpit_url: str
    timeout: float
    run_id: str
    client: httpx.Client
    state: dict[str, Any] = field(default_factory=dict)


def run_scene(name: str, body: Callable[[], str]) -> SceneResult:
    """Time one scene body and convert rehearsal or HTTP errors into a SceneResult."""
    started = time.monotonic()
    try:
        detail = body()
        return SceneResult(
            name=name, passed=True, detail=detail, duration=time.monotonic() - started
        )
    except (RehearsalError, httpx.HTTPError, ValueError, KeyError) as exc:
        return SceneResult(
            name=name, passed=False, detail=str(exc), duration=time.monotonic() - started
        )


def fresh_rates_event(run_id: str, label: str = "alert") -> tuple[dict[str, Any], str, str]:
    """Build a rates trade-rejected event with a unique fingerprint (`payload.reason`)."""
    event = load_fixture("rates_trade_rejected.json")
    reason = f"LIMIT_BREACH_{label.upper()}_{run_id}"
    trade_id = f"T-REHEARSAL-{label.upper()}-{run_id}"
    event["payload"]["reason"] = reason
    event["payload"]["tradeId"] = trade_id
    return event, reason, trade_id


def fresh_settlements_event(run_id: str, label: str = "outage") -> tuple[dict[str, Any], str]:
    """Build a settlements WORKFLOW_FAILED event with a unique `workflowId`."""
    event = load_fixture("settlements_workflow_failed.json")
    workflow_id = f"wf-rehearsal-{label}-{run_id}"
    event["workflowId"] = workflow_id
    return event, workflow_id


def fresh_alertmanager_events(run_id: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Build matching Alertmanager firing and resolved payloads with fresh instance and key."""
    instance = f"exporter-rehearsal-{run_id}:9100"
    am_fingerprint = f"{run_id}00a1b2c3"
    firing = load_fixture("alertmanager_firing.json")
    resolved = load_fixture("alertmanager_resolved.json")
    for payload in (firing, resolved):
        item = payload["alerts"][0]
        item["labels"]["instance"] = instance
        item["annotations"]["summary"] = f"Exporter {instance} is down"
        item["fingerprint"] = am_fingerprint
    return firing, resolved, instance


def make_stricter_rates_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the rates rule with a stricter `payload.notional` threshold."""
    stricter = copy.deepcopy(rule)
    clauses = stricter.get("when", {}).get("all", [])
    updated = False
    for clause in clauses:
        if isinstance(clause, dict) and clause.get("field") == "payload.notional":
            current = clause.get("value", 10_000_000)
            clause["value"] = max(int(current) * 10, 100_000_000)
            updated = True
    if not updated:
        raise RehearsalError("rates rule has no payload.notional clause to tighten")
    return stricter


def build_batches(
    event: dict[str, Any], total: int, batch_size: int = 100
) -> list[list[dict[str, Any]]]:
    """Split `total` copies of `event` into batches of at most `batch_size`."""
    if total < 0:
        raise ValueError("total must be non-negative")
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    batches: list[list[dict[str, Any]]] = []
    remaining = total
    while remaining > 0:
        size = min(batch_size, remaining)
        batches.append([copy.deepcopy(event) for _ in range(size)])
        remaining -= size
    return batches


def poll_until[T](
    probe: Callable[[], T | None],
    *,
    timeout: float,
    interval: float = 0.5,
    reason: str,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Poll `probe` until it returns a truthy value or `timeout` seconds elapse."""
    deadline = clock() + timeout
    last_error = ""
    while True:
        try:
            value = probe()
            if value:
                return value
        except FatalPollError:
            raise
        except (httpx.HTTPError, ValueError, RehearsalError) as exc:
            last_error = f" ({type(exc).__name__}: {exc})"
        remaining = deadline - clock()
        if remaining <= 0:
            raise RehearsalError(f"{reason} within {timeout:g}s{last_error}")
        sleep(min(interval, remaining))


def parse_only_scenes(raw: str | None, valid_names: Sequence[str]) -> list[str]:
    """Parse `--only scene1,scene2` preserving canonical order and validating names."""
    if not raw:
        return list(valid_names)
    requested = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [name for name in requested if name not in valid_names]
    if unknown:
        valid = ", ".join(valid_names)
        raise ValueError(f"unknown scene(s): {', '.join(unknown)} (valid: {valid})")
    return [name for name in valid_names if name in requested]


def _escape_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def format_markdown_table(results: Sequence[SceneResult]) -> str:
    """Format scene results as a GitHub-flavored Markdown PASS/FAIL table."""
    lines = [
        "| Scene | Status | Duration | Detail |",
        "| --- | --- | ---: | --- |",
    ]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"| {result.name} | {status} | {result.duration:.2f}s | {_escape_cell(result.detail)} |"
        )
    passed_count = sum(1 for result in results if result.passed)
    lines.append("")
    lines.append(f"Result: {passed_count}/{len(results)} scenes passed.")
    return "\n".join(lines)


def get_json(ctx: RehearsalContext, url: str, **params: Any) -> Any:
    """GET `url` and require HTTP 200 JSON."""
    response = ctx.client.get(url, params=params)
    if response.status_code != 200:
        raise RehearsalError(f"GET {url} returned {response.status_code}")
    return response.json()


def post_ingest(ctx: RehearsalContext, source_id: str, payload: dict[str, Any]) -> IngestAccepted:
    """POST one event to ingest and require HTTP 202 `IngestAccepted`."""
    url = f"{ctx.ingest_url}/api/v1/ingest/{source_id}"
    response = ctx.client.post(url, json=payload)
    if response.status_code != 202:
        raise RehearsalError(f"POST {url} returned {response.status_code}, expected 202")
    return IngestAccepted.model_validate(response.json())


def post_ingest_batch(
    ctx: RehearsalContext, source_id: str, events: list[dict[str, Any]]
) -> IngestAccepted:
    """POST an array of events to the batch ingest endpoint and require HTTP 202."""
    url = f"{ctx.ingest_url}/api/v1/ingest/{source_id}/batch"
    response = ctx.client.post(url, json=events)
    if response.status_code != 202:
        raise RehearsalError(f"POST {url} returned {response.status_code}, expected 202")
    return IngestAccepted.model_validate(response.json())


def list_team_alerts(ctx: RehearsalContext, team: str, *, status: str | None = None) -> AlertPage:
    """Fetch up to 200 alerts for `team` (optionally filtered by status)."""
    params: dict[str, Any] = {"team": team, "limit": 200}
    if status is not None:
        params["status"] = status
    return AlertPage.model_validate(get_json(ctx, f"{ctx.api_url}/api/v1/alerts", **params))


def get_alert_detail(ctx: RehearsalContext, alert_id: str) -> AlertDetail:
    """Fetch full alert detail (deliveries, action runs, approvals, audit)."""
    return AlertDetail.model_validate(get_json(ctx, f"{ctx.api_url}/api/v1/alerts/{alert_id}"))


def set_gateway_outage(
    ctx: RehearsalContext, *, is_down: bool, channels: list[str] | None = None
) -> dict[str, Any]:
    """Toggle simulated channel outage on mock-gateway."""
    body: dict[str, Any] = {"is_down": is_down}
    if channels is not None:
        body["channels"] = channels
    response = ctx.client.post(f"{ctx.gateway_url}/admin/outage", json=body)
    if response.status_code != 200:
        raise RehearsalError(f"POST /admin/outage returned {response.status_code}")
    return dict(response.json())


def set_service_health(
    ctx: RehearsalContext, service_name: str, *, is_healthy: bool
) -> dict[str, Any]:
    """Set a service's health response on mock-gateway."""
    url = f"{ctx.gateway_url}/admin/services/{service_name}/health"
    response = ctx.client.post(url, json={"is_healthy": is_healthy})
    if response.status_code != 200:
        raise RehearsalError(
            f"POST /admin/services/{service_name}/health -> {response.status_code}"
        )
    return dict(response.json())
