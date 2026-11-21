"""Cheap reachability probe for the LLM endpoint (used by the Settings screen)."""

import time

import httpx

from .client import LlmClient

PROBE_TIMEOUT_SECONDS = 3.0


async def probe_llm(client: LlmClient) -> tuple[bool, int]:
    """GET {base}/models with the client's auth; return (is_reachable, latency_ms).

    Any HTTP error, timeout or non-2xx status counts as unreachable; never raises.
    """
    headers = (
        {"Authorization": f"Bearer {client._config.api_key}"} if client._config.api_key else {}
    )
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_SECONDS) as http:
            response = await http.get(f"{client._base_url}/models", headers=headers)
        is_reachable = response.is_success
    except httpx.HTTPError:
        is_reachable = False
    return is_reachable, round((time.perf_counter() - started) * 1000)
