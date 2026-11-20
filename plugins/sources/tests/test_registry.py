"""Source plugin registry tests."""

from alerting_contracts.config import SourceConfig
from alerting_contracts.events import SourceType

from plugins.sources import get_source_plugin


def test_webhook_plugin_returns_body_as_single_payload() -> None:
    plugin = get_source_plugin(SourceType.webhook)
    assert plugin is not None
    source = SourceConfig(id="s", type=SourceType.webhook)
    assert plugin.extract_payloads({"a": 1}, source) == [{"a": 1}]


def test_log_tail_has_no_http_plugin() -> None:
    assert get_source_plugin(SourceType.log_tail) is None
