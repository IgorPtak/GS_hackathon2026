"""GET /api/v1/llm/status: is the LLM configured and reachable (cached for 60 s)."""

import time
from datetime import UTC, datetime

from alerting_contracts.api import LlmStatus
from alerting_core.llm.health import probe_llm
from fastapi import APIRouter, Request

router = APIRouter(tags=["ops"])

CACHE_SECONDS = 60.0
PRIVACY_NOTE = (
    "Data is redacted before it is sent and the LLM is used only when you save or ask for a "
    "draft; alerts never wait for it."
)


@router.get("/api/v1/llm/status", operation_id="getLlmStatus", response_model=LlmStatus)
async def get_llm_status(request: Request) -> LlmStatus:
    """Report LLM state; the reachability probe result is cached in app.state for 60 s."""
    state = request.app.state
    client = getattr(state, "llm", None)
    if client is None:
        return LlmStatus(
            is_enabled=False,
            model=None,
            provider_host=None,
            is_reachable=None,
            latency_ms=None,
            checked_at=None,
            privacy_note=PRIVACY_NOTE,
        )
    cached = getattr(state, "llm_status_cache", None)
    if cached is None or time.monotonic() - cached[0] >= CACHE_SECONDS:
        is_reachable, latency_ms = await probe_llm(client)
        cached = (
            time.monotonic(),
            LlmStatus(
                is_enabled=True,
                model=client.model,
                provider_host=client.base_host,
                is_reachable=is_reachable,
                latency_ms=latency_ms,
                checked_at=datetime.now(UTC),
                privacy_note=PRIVACY_NOTE,
            ),
        )
        state.llm_status_cache = cached
    return cached[1]
