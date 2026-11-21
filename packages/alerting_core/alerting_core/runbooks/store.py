"""Runbooks as a registered config kind (`config/runbooks/*.yaml|md|txt`)."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import asyncpg
import yaml
from alerting_contracts.common import Actor
from alerting_contracts.config import ActionConfig
from alerting_contracts.runbooks import Runbook, RunbookFormat
from redis.asyncio import Redis

from plugins.runbook_formats.markdown_format import heading_text

from ..config import register_kind, save_config_document
from ..config.store import NORMALIZE_TEXT_WITH_LLM
from ..llm import LlmCache, LlmClient, LlmConfig, LlmError, RedisLlmCache
from ..logging import get_logger
from ..settings import get_settings
from .normalize import normalize_runbook, normalize_runbook_with_llm

log = get_logger(__name__)

KIND = "runbook"
DIRECTORY = "runbooks"
_FORMAT_BY_SUFFIX = {
    ".yaml": RunbookFormat.yaml,
    ".yml": RunbookFormat.yaml,
    ".md": RunbookFormat.markdown,
    ".txt": RunbookFormat.text,
}


def _sibling_actions(runbook_file: Path) -> dict[str, ActionConfig]:
    """Actions from `<config>/actions/`, next to the runbooks directory.

    A-03's `load_file(path)` receives only the file path, so actions are read from the sibling
    directory at load time; unreadable action files are skipped (the loader reports them).
    """
    actions: dict[str, ActionConfig] = {}
    directory = runbook_file.parent.parent / "actions"
    if not directory.is_dir():
        return actions
    for file in sorted(directory.glob("*.y*ml")):
        try:
            action = ActionConfig.model_validate(yaml.safe_load(file.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 - one broken action file must not hide the runbooks
            continue
        actions[action.id] = action
    return actions


LLM_SYNC_TIMEOUT_SECONDS = 15.0  # one slow endpoint must not stall the sync of other documents
LLM_CACHE_TTL_SECONDS = 7 * 24 * 3600


class _BestEffortCache:
    """Redis cache that never raises: a cache outage only costs one more LLM call."""

    def __init__(self, inner: LlmCache) -> None:
        self._inner = inner

    async def get(self, key: str) -> str | None:
        try:
            return await self._inner.get(key)
        except Exception:  # noqa: BLE001 - cache is optional
            return None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            await self._inner.set(key, value, ttl_seconds)
        except Exception:  # noqa: BLE001 - cache is optional
            return None


def create_sync_llm_client(cache: LlmCache) -> LlmClient | None:
    """LLM client from process settings; None when the host is not allowed (host check stays)."""
    try:
        return LlmClient(
            LlmConfig.from_settings(get_settings()),
            cache=cache,
            cache_ttl_seconds=LLM_CACHE_TTL_SECONDS,
        )
    except LlmError as error:
        log.warning("runbook_llm_disabled", extra={"error": str(error)})
        return None


async def _normalize_text(
    id: str,
    title: str,
    team: str | None,
    source: str,
    actions: dict[str, ActionConfig],
    client: LlmClient | None,
) -> Runbook:
    redis: Redis | None = None
    if client is None:
        # The cache is keyed by content hash inside LlmClient, so an unchanged file costs no call.
        redis = Redis.from_url(get_settings().redis_url)
        cache: LlmCache = _BestEffortCache(RedisLlmCache(redis))
        client = create_sync_llm_client(cache)
    try:
        return await asyncio.wait_for(
            normalize_runbook_with_llm(
                id, title, team, RunbookFormat.text, source, actions, client
            ),
            timeout=LLM_SYNC_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        log.warning("runbook_llm_timeout", extra={"runbook": id})
        return normalize_runbook(id, title, team, RunbookFormat.text, source, actions)
    finally:
        if redis is not None:
            await redis.aclose()


def normalize_text_file(
    id: str,
    title: str,
    team: str | None,
    source: str,
    actions: dict[str, ActionConfig],
    client: LlmClient | None = None,
) -> Runbook:
    """Normalize a free-text runbook file with the LLM; falls back to one text step, never raises
    for LLM trouble. The config loader is synchronous, so the call runs on a worker thread with
    its own event loop (safe whether or not the caller already runs a loop).
    """
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            lambda: asyncio.run(_normalize_text(id, title, team, source, actions, client))
        )
        try:
            return future.result()
        except ValueError:
            raise
        except Exception:  # noqa: BLE001 - config sync must survive any LLM-side failure
            log.warning("runbook_llm_failed", extra={"runbook": id}, exc_info=True)
            return normalize_runbook(id, title, team, RunbookFormat.text, source, actions)


def load_runbook_file(path: Path, normalize_text_with_llm: bool | None = None) -> Runbook:
    """Read one runbook file and normalize it. id = file stem.

    Free-text files call the LLM only when `normalize_text_with_llm` is true (None reads the
    config-sync opt-in, default off); otherwise they become one text step. This blocks, so async
    callers must run it in a thread.
    """
    if normalize_text_with_llm is None:
        normalize_text_with_llm = NORMALIZE_TEXT_WITH_LLM.get()
    format = _FORMAT_BY_SUFFIX.get(path.suffix)
    if format is None:
        raise ValueError(f"unsupported runbook file extension {path.suffix!r}")
    source = path.read_text(encoding="utf-8")
    title: str = path.stem
    team: str | None = None
    if format is RunbookFormat.yaml:
        data = yaml.safe_load(source)
        if isinstance(data, dict):
            if data.get("id") not in (None, path.stem):
                raise ValueError(f"id {data['id']!r} does not match file name {path.stem!r}")
            title = str(data.get("title") or title)
            team = data.get("team")
    elif format is RunbookFormat.markdown:
        title = heading_text(source) or title
    actions = _sibling_actions(path)
    if format is RunbookFormat.text and source.strip() and normalize_text_with_llm:
        return normalize_text_file(path.stem, title, team, source, actions)
    return normalize_runbook(path.stem, title, team, format, source, actions)


def register_runbook_kind() -> None:
    """Register the `runbook` kind with A-03. Idempotent: a second call replaces the same spec."""
    register_kind(
        KIND,
        DIRECTORY,
        load_runbook_file,
        Runbook.model_validate,
        suffixes=frozenset(_FORMAT_BY_SUFFIX),
    )


async def save_runbook(pool: asyncpg.Pool, redis: Redis, runbook: Runbook, actor: Actor) -> int:
    """Validate and store a runbook; returns the new version."""
    return await save_config_document(pool, redis, KIND, runbook, actor)
