"""`webhook` channel: renders a YAML `body_template` to JSON and sends it (Slack and similar)."""

import json
import re
from typing import Any

import httpx
from alerting_contracts.alerts import DeliveryJob
from alerting_contracts.config import ChannelConfig, ChannelType, Recipient

from .base import (
    ChannelContext,
    ChannelPlugin,
    ChannelRejectedError,
    ChannelUnavailableError,
    check_host_allowed,
    classify_http_status,
)
from .registry import register_channel_plugin

TIMEOUT_SECONDS = 5.0
_PLACEHOLDER = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def _lookup(context: dict[str, Any], path: str) -> str:
    value: Any = context
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    if value is None:
        return ""
    return value if isinstance(value, str) else json.dumps(value)


def render_body(template: str, context: dict[str, Any]) -> str:
    """Substitute `{{path}}` placeholders.

    Values are JSON-escaped (outer quotes stripped) so they are safe inside a JSON string.
    Replace with alerting_core.templating.render_template once A-08 is merged.
    """
    return _PLACEHOLDER.sub(lambda match: json.dumps(_lookup(context, match[1]))[1:-1], template)


def build_context(job: DeliveryJob, recipient: Recipient | None) -> dict[str, Any]:
    """Template context: `alert` (content + alert_id/team), `job` and `recipient`."""
    alert = job.content.model_dump(mode="json")
    alert["alert_id"] = job.alert_id
    alert["team"] = job.team
    return {
        "alert": alert,
        "job": job.model_dump(mode="json"),
        "recipient": recipient.model_dump(mode="json") if recipient else None,
    }


class WebhookChannel(ChannelPlugin):
    """Sends the rendered JSON body to `settings.url`."""

    channel_type = ChannelType.webhook

    async def send(
        self,
        job: DeliveryJob,
        recipient: Recipient | None,
        config: ChannelConfig,
        context: ChannelContext,
    ) -> None:
        settings = config.settings
        url = settings.get("url")
        template = settings.get("body_template", "{}")
        headers = settings.get("headers", {})
        method = settings.get("method", "POST")
        if not isinstance(url, str) or not url:
            raise ChannelRejectedError("webhook channel has no settings.url")
        if not isinstance(template, str):
            raise ChannelRejectedError("webhook body_template must be a string")
        if not isinstance(headers, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in headers.items()
        ):
            raise ChannelRejectedError("webhook headers must be a mapping of strings")
        if not isinstance(method, str):
            raise ChannelRejectedError("webhook method must be a string")
        check_host_allowed(url, context)
        body = render_body(template, build_context(job, recipient))
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as error:
            raise ChannelRejectedError(
                f"body_template did not render valid JSON: {error}"
            ) from error
        if not isinstance(parsed, dict):
            raise ChannelRejectedError("body_template must render a JSON object")
        try:
            response = await context.http.request(
                method,
                url,
                content=body.encode(),
                headers={"Content-Type": "application/json"} | headers,
                timeout=TIMEOUT_SECONDS,
            )
        except (httpx.InvalidURL, httpx.UnsupportedProtocol) as error:
            raise ChannelRejectedError(f"invalid webhook url: {error}") from error
        except httpx.HTTPError as error:
            raise ChannelUnavailableError(f"webhook unreachable: {error!r}") from error
        classify_http_status(response.status_code)


register_channel_plugin(WebhookChannel())
