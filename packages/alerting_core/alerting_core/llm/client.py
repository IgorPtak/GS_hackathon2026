"""LLM client: redacted prompt -> OpenAI-compatible endpoint -> Pydantic-validated model."""

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ValidationError

from .cache import LlmCache
from .errors import LlmHostNotAllowedError, LlmOutputInvalidError, LlmUnavailableError
from .redaction import redact_secrets

if TYPE_CHECKING:
    from ..settings import Settings

logger = logging.getLogger("alerting_core.llm")

DEFAULT_ALLOWED_HOSTS = ("ollama", "localhost", "127.0.0.1")
_THINK = re.compile(r"^\s*<think>.*?</think>", re.DOTALL)


@dataclass(frozen=True)
class LlmConfig:
    """LLM connection settings; services build it with `from_settings(get_settings())`."""

    base_url: str = "http://ollama:11434/v1"
    api_key: str | None = None
    model: str = "qwen2.5:7b-instruct"
    timeout_seconds: float = 30
    allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS

    def __repr__(self) -> str:
        key = "set" if self.api_key else "none"
        return f"LlmConfig(base_url={self.base_url!r}, model={self.model!r}, api_key=<{key}>)"

    @classmethod
    def from_settings(cls, settings: "Settings") -> "LlmConfig":
        """Build from the shared process settings (A-02), the normal path inside services."""
        hosts = tuple(h.strip() for h in settings.llm_allowed_hosts.split(",") if h.strip())
        return cls(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.strip() or None,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            allowed_hosts=hosts or DEFAULT_ALLOWED_HOSTS,
        )

    @classmethod
    def from_env(cls) -> "LlmConfig":
        """Read LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT_SECONDS, LLM_ALLOWED_HOSTS."""
        default = cls()
        hosts = os.environ.get("LLM_ALLOWED_HOSTS", "").strip()
        return cls(
            base_url=os.environ.get("LLM_BASE_URL", "").strip() or default.base_url,
            api_key=os.environ.get("LLM_API_KEY", "").strip() or None,
            model=os.environ.get("LLM_MODEL", "").strip() or default.model,
            timeout_seconds=float(
                os.environ.get("LLM_TIMEOUT_SECONDS", "").strip() or default.timeout_seconds
            ),
            allowed_hosts=tuple(h.strip() for h in hosts.split(",") if h.strip())
            or default.allowed_hosts,
        )


def _log(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, default=str))


def _snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


class LlmClient:
    """Async client returning validated Pydantic models from an OpenAI-compatible endpoint."""

    def __init__(
        self,
        config: LlmConfig | None = None,
        *,
        cache: LlmCache | None = None,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        self._config = config or LlmConfig.from_env()
        host = urlparse(self._config.base_url).hostname
        if host is None or host not in self._config.allowed_hosts:
            raise LlmHostNotAllowedError(
                f"LLM host {host!r} is not in allowed hosts {list(self._config.allowed_hosts)}"
            )
        self._host = host
        self._base_url = self._config.base_url.rstrip("/")
        self._cache = cache
        self._cache_ttl = cache_ttl_seconds

    @property
    def model(self) -> str:
        """Model name, for Runbook.llm_model."""
        return self._config.model

    @property
    def base_host(self) -> str:
        """Host part of the base URL."""
        return self._host

    def _cache_key(self, system: str | None, prompt: str, schema_json: str) -> str:
        raw = "\n".join([self.model, system or "", prompt, schema_json])
        return "llm-cache:" + hashlib.sha256(raw.encode()).hexdigest()

    async def generate(
        self, prompt: str, response_model: type[BaseModel], *, system: str | None = None
    ) -> BaseModel:
        """Return the model's answer validated as response_model (one retry on invalid output)."""
        prompt = redact_secrets(prompt)
        system = redact_secrets(system) if system is not None else None
        schema = response_model.model_json_schema()
        schema_json = json.dumps(schema, sort_keys=True)
        key = self._cache_key(system, prompt, schema_json)

        if self._cache is not None:
            cached = await self._cache.get(key)
            if cached is not None:
                try:
                    result = response_model.model_validate_json(cached)
                except ValidationError:
                    result = None
                if result is not None:
                    _log(
                        "llm_cache_hit",
                        model=self.model,
                        schema=response_model.__name__,
                    )
                    return result

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": _snake_case(response_model.__name__),
                "schema": schema,
                "strict": False,
            },
        }

        content = await self._call(messages, response_format)
        try:
            result = response_model.model_validate_json(content)
        except ValidationError as error:
            _log(
                "llm_retry",
                model=self.model,
                schema=response_model.__name__,
                error_count=error.error_count(),
            )
            messages = [
                *messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        f"Your previous answer failed validation:\n{error}\n"
                        "Return corrected JSON only."
                    ),
                },
            ]
            content = await self._call(messages, response_format)
            try:
                result = response_model.model_validate_json(content)
            except ValidationError as second:
                raise LlmOutputInvalidError(
                    f"LLM output invalid after retry: {second.error_count()} errors"
                ) from second

        if self._cache is not None:
            await self._cache.set(key, result.model_dump_json(), self._cache_ttl)
        return result

    async def _call(self, messages: list[dict[str, str]], response_format: dict[str, Any]) -> str:
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": messages,
            "response_format": response_format,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        headers = (
            {"Authorization": f"Bearer {self._config.api_key}"} if self._config.api_key else {}
        )
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as http:
                response = await http.post(
                    f"{self._base_url}/chat/completions", json=body, headers=headers
                )
        except httpx.TimeoutException as error:
            raise LlmUnavailableError(
                f"LLM request timed out after {self._config.timeout_seconds}s"
            ) from error
        except httpx.HTTPError as error:
            raise LlmUnavailableError(f"LLM request failed: {type(error).__name__}") from error
        latency_ms = round((time.perf_counter() - started) * 1000)
        _log(
            "llm_call",
            model=self.model,
            host=self._host,
            status=response.status_code,
            latency_ms=latency_ms,
        )
        if not response.is_success:
            raise LlmUnavailableError(f"LLM endpoint returned HTTP {response.status_code}")
        try:
            content = response.json()["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise LlmUnavailableError("LLM endpoint returned a malformed response") from error
        return _THINK.sub("", content).strip()
