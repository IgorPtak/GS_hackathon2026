import json
import logging

import pytest
from alerting_core.logging import JsonFormatter
from alerting_core.settings import Settings


def test_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/1")
    monkeypatch.setenv("SERVICE_NAME", "processor")
    settings = Settings()
    assert settings.redis_url == "redis://redis:6379/1"
    assert settings.service_name == "processor"


def test_json_formatter_emits_event_service_and_ids() -> None:
    record = logging.makeLogRecord(
        {"name": "test", "levelname": "INFO", "msg": "alert_created", "alert_id": "a-1", "count": 3}
    )
    entry = json.loads(JsonFormatter("processor").format(record))
    assert entry["event"] == "alert_created"
    assert entry["service"] == "processor"
    assert entry["alert_id"] == "a-1"
    assert entry["rule_id"] is None
    assert entry["count"] == 3
