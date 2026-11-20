"""Action plugin contract.

An action plugin executes one runbook step against the outside world (usually over HTTP).
Contract:
- ``execute`` never raises for business failures (HTTP errors, timeouts, non-2xx, missing
  params); it returns ``ActionResult(is_success=False, detail=...)`` with a short detail.
- Required params (``config.params[*].is_required``) are validated before any I/O.
- The timeout comes from ``config.timeout``.
"""

from __future__ import annotations

import abc
import json
import os
import re
import time
from typing import Any
from urllib.parse import quote

import httpx
from alerting_contracts.config import ActionConfig
from pydantic import BaseModel, Field

DEFAULT_MOCK_GATEWAY_URL = "http://mock-gateway:8090"

_UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}


def parse_duration_seconds(value: str) -> float:
    """Parse "5s", "1m", "250ms" into seconds.

    Tiny local parser; A-02's durations module replaces it.
    """
    m = re.fullmatch(r"([0-9]+)(ms|s|m|h|d)", value)
    if not m:
        raise ValueError(f"invalid duration: {value!r}")
    return int(m.group(1)) * _UNITS[m.group(2)]


def mock_gateway_url() -> str:
    return os.environ.get("MOCK_GATEWAY_URL", DEFAULT_MOCK_GATEWAY_URL).rstrip("/")


class ActionResult(BaseModel):
    """Outcome of one action execution. ``data`` is stored in ActionRun.result."""

    is_success: bool
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)


def render_template(template: str, params: dict[str, str], *, json_escape: bool = False) -> str:
    """Replace ``{{name}}`` with params values; unknown/absent params become "".

    With ``json_escape`` values are escaped for embedding inside a JSON string literal.
    """

    def sub(m: re.Match[str]) -> str:
        value = str(params.get(m.group(1), ""))
        return json.dumps(value, ensure_ascii=False)[1:-1] if json_escape else value

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", sub, template)


def render_url(template: str, params: dict[str, str]) -> str:
    """Render a URL template, percent-encoding substituted values."""
    return re.sub(
        r"\{\{\s*(\w+)\s*\}\}",
        lambda m: quote(str(params.get(m.group(1), "")), safe=""),
        template,
    )


class ActionPlugin(abc.ABC):
    """Base class of all action plugins. Set ``type`` and implement ``_run``."""

    type: str

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """``client`` is injectable for tests; otherwise one client is created per call."""
        self._client = client

    @staticmethod
    def missing_required(params: dict[str, str], config: ActionConfig) -> list[str]:
        return [
            name
            for name, spec in config.params.items()
            if spec.is_required and not str(params.get(name, "")).strip()
        ]

    async def execute(self, params: dict[str, str], config: ActionConfig) -> ActionResult:
        """Validate required params, then run the action. Never raises for business failures."""
        missing = self.missing_required(params, config)
        if missing:
            return ActionResult(
                is_success=False,
                detail=f"missing required params: {', '.join(missing)}",
            )
        try:
            return await self._run(params, config)
        except httpx.HTTPError as exc:  # safety net for anything not handled in send()
            return ActionResult(is_success=False, detail=f"http error: {type(exc).__name__}")

    @abc.abstractmethod
    async def _run(self, params: dict[str, str], config: ActionConfig) -> ActionResult:
        """Do the work; params are already validated."""

    async def send(
        self,
        method: str,
        url: str,
        config: ActionConfig,
        *,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> ActionResult:
        """One HTTP call with the config timeout; maps errors and non-2xx to failures."""
        timeout = parse_duration_seconds(config.timeout)
        started = time.monotonic()
        try:
            if self._client is not None:
                resp = await self._client.request(
                    method, url, headers=headers, content=content, timeout=timeout
                )
            else:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.request(method, url, headers=headers, content=content)
        except httpx.TimeoutException:
            return ActionResult(is_success=False, detail=f"timeout after {config.timeout}")
        except httpx.HTTPError as exc:
            return ActionResult(is_success=False, detail=f"request failed: {type(exc).__name__}")
        elapsed_ms = int((time.monotonic() - started) * 1000)
        data: dict[str, Any] = {
            "status_code": resp.status_code,
            "elapsed_ms": elapsed_ms,
        }
        if resp.is_success:
            return ActionResult(is_success=True, detail=f"HTTP {resp.status_code}", data=data)
        return ActionResult(is_success=False, detail=f"HTTP {resp.status_code}", data=data)
