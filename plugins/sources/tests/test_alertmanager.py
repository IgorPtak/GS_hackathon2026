"""Alertmanager source: one event per alert, status/receiver/groupKey copied in."""

import json
from pathlib import Path

from alerting_contracts.config import SourceConfig

from plugins.sources import get_source_plugin
from plugins.sources.alertmanager import AlertmanagerSource

FIXTURES = Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "events"
SOURCE = SourceConfig(id="alertmanager", type="alertmanager")


def test_registered_for_alertmanager() -> None:
    assert isinstance(get_source_plugin(SOURCE.type), AlertmanagerSource)


def test_firing_batch_becomes_one_payload_per_alert() -> None:
    body = json.loads((FIXTURES / "alertmanager_firing.json").read_text())
    payloads = AlertmanagerSource().extract_payloads(body, SOURCE)
    assert len(payloads) == len(body["alerts"])
    assert payloads[0]["status"] == "firing"
    assert payloads[0]["receiver"] == body["receiver"]
    assert payloads[0]["groupKey"] == body["groupKey"]
    assert payloads[0]["labels"]["alertname"] == "ExporterDown"


def test_item_status_wins_over_top_level() -> None:
    body = {"status": "firing", "alerts": [{"status": "resolved"}, {"labels": {}}]}
    payloads = AlertmanagerSource().extract_payloads(body, SOURCE)
    assert [p["status"] for p in payloads] == ["resolved", "firing"]


def test_idempotency_key_separates_firing_and_resolved() -> None:
    plugin = AlertmanagerSource()
    firing = {"fingerprint": "ab", "status": "firing", "startsAt": "t0"}
    resolved = {**firing, "status": "resolved"}
    assert plugin.idempotency_key(firing, SOURCE) == plugin.idempotency_key(dict(firing), SOURCE)
    assert plugin.idempotency_key(firing, SOURCE) != plugin.idempotency_key(resolved, SOURCE)
    assert plugin.idempotency_key(firing, SOURCE) == "alertmanager:ab:firing:t0"
    assert plugin.idempotency_key({"status": "firing"}, SOURCE) is None


def test_missing_alerts_yields_nothing() -> None:
    assert AlertmanagerSource().extract_payloads({"status": "firing"}, SOURCE) == []
