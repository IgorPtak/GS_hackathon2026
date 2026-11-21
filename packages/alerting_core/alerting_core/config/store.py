"""Persist configuration documents in Postgres and announce changes.

Startup rule (YAML files have no version field): a file is upserted into `config_documents` when
its canonical content differs from the stored `document` AND the file's mtime is newer than the
row's `updated_at`; otherwise the database copy (edited through the UI/API) wins. Compare and
write happen in one SQL statement, so concurrent workers cannot race. Note that touching files
(for example `git checkout`) gives them a fresh mtime, so they then win over UI edits.
"""

import asyncio
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
import yaml
from alerting_contracts.common import Actor
from alerting_contracts.sse import ConfigChangedEvent
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis

from ..logging import get_logger
from .kinds import get_kind
from .loader import LoadResult, load_config_directory

CONFIG_CHANGED_CHANNEL = "config.changed"
BROADCAST_CHANNEL = "broadcast"

log = get_logger(__name__)

_UPSERT_SQL = """
INSERT INTO config_documents
    (kind, id, team, document, yaml, version, updated_at, updated_by)
VALUES ($1, $2, $3, $4, $5, 1, now(), $6)
ON CONFLICT (kind, id) DO UPDATE SET
    team = EXCLUDED.team, document = EXCLUDED.document, yaml = EXCLUDED.yaml,
    version = config_documents.version + 1, updated_at = now(),
    updated_by = EXCLUDED.updated_by
{guard}
RETURNING version
"""
_FILE_GUARD = """WHERE config_documents.document IS DISTINCT FROM EXCLUDED.document
    AND config_documents.updated_at < $7"""


def canonical_document(model: BaseModel) -> dict[str, Any]:
    """The JSON form stored in `config_documents.document` (defaults omitted, aliases used)."""
    return model.model_dump(mode="json", exclude_defaults=True, by_alias=True)


def canonical_yaml(model: BaseModel) -> str:
    """Canonical YAML text of a document, as stored in `config_documents.yaml`."""
    return yaml.safe_dump(canonical_document(model), sort_keys=False, allow_unicode=True)


async def publish_config_changed(redis: Redis, kind: str, document_id: str, version: int) -> None:
    """Publish the same ConfigChangedEvent for workers (reload) and the API (SSE)."""
    event = ConfigChangedEvent(at=datetime.now(UTC), kind=kind, id=document_id, version=version)
    payload = event.model_dump_json()
    await redis.publish(CONFIG_CHANGED_CHANNEL, payload)
    await redis.publish(BROADCAST_CHANNEL, payload)


def _validated(kind: str, document: BaseModel | dict[str, Any]) -> BaseModel:
    """Re-validate through the kind's model; a model of another kind is a ValueError."""
    spec = get_kind(kind)
    if isinstance(document, BaseModel):
        try:
            return spec.validate_document(canonical_document(document))
        except ValidationError as exc:
            raise ValueError(f"{type(document).__name__} is not a valid {kind!r} document") from exc
    return spec.validate_document(document)


async def _upsert(
    pool: asyncpg.Pool,
    kind: str,
    model: BaseModel,
    actor: Actor,
    file_mtime: datetime | None = None,
) -> int | None:
    """Write one document; with `file_mtime` only if it differs from and is newer than the DB."""
    args: list[Any] = [
        kind,
        str(model.id),  # type: ignore[attr-defined]
        getattr(model, "team", None),
        canonical_document(model),
        canonical_yaml(model),
        actor.model_dump(mode="json", exclude_none=True),
    ]
    if file_mtime is not None:
        args.append(file_mtime)
    sql = _UPSERT_SQL.format(guard=_FILE_GUARD if file_mtime is not None else "")
    row = await pool.fetchrow(sql, *args)
    return int(row["version"]) if row else None


async def _publish_after_write(redis: Redis, kind: str, document_id: str, version: int) -> None:
    # The DB write succeeded; a lost notification is repaired by the registry's reconcile loop.
    try:
        await publish_config_changed(redis, kind, document_id, version)
    except Exception:  # noqa: BLE001
        log.exception("config_publish_failed", extra={"kind": kind, "config_id": document_id})


async def save_config_document(
    pool: asyncpg.Pool,
    redis: Redis,
    kind: str,
    document: BaseModel | dict[str, Any],
    actor: Actor,
) -> int:
    """Validate, serialize to canonical YAML, bump `version`, write the DB and publish.

    A dict (or a model) is validated with the kind's model first; an invalid dict raises
    pydantic.ValidationError, a model of the wrong kind raises ValueError, and nothing is
    written. Returns the new version.
    """
    model = _validated(kind, document)
    version = await _upsert(pool, kind, model, actor)
    if version is None:  # the unguarded upsert always returns a row
        raise RuntimeError(f"saving {kind}/{model.id} returned no version")  # type: ignore[attr-defined]
    document_id = str(model.id)  # type: ignore[attr-defined]
    await _publish_after_write(redis, kind, document_id, version)
    log.info(
        "config_document_saved",
        extra={"kind": kind, "config_id": document_id, "version": version, "actor": actor.id},
    )
    return version


# Why a ContextVar: file loaders are registered as `loader_fn(path)`, so the opt-in for LLM
# normalization of free-text runbooks travels with the context (copied into to_thread workers).
NORMALIZE_TEXT_WITH_LLM: ContextVar[bool] = ContextVar("normalize_text_with_llm", default=False)


def _load_with_llm(config_dir: Path | str) -> LoadResult:
    NORMALIZE_TEXT_WITH_LLM.set(True)  # only affects this worker thread's context copy
    return load_config_directory(config_dir)


def _modified_at(file: Path) -> datetime:
    return datetime.fromtimestamp(file.stat().st_mtime, UTC)


async def sync_config_files(
    pool: asyncpg.Pool,
    redis: Redis,
    config_dir: Path | str,
    actor: Actor | None = None,
) -> LoadResult:
    """Upsert files that win over the DB (see module docstring); invalid files are logged."""
    actor = actor or Actor(id="system:config-loader")
    # Off the event loop: free-text runbook files may wait on the LLM (only config sync allows it).
    result = await asyncio.to_thread(_load_with_llm, config_dir)
    for error in result.errors:
        log.error(
            "config_file_invalid",
            extra={"file": error.file, "path": error.path, "error": error.message},
        )
    for loaded in result.documents:
        modified = _modified_at(loaded.file)
        version = await _upsert(pool, loaded.kind, loaded.model, actor, modified)
        if version is not None:
            await _publish_after_write(redis, loaded.kind, loaded.id, version)
    return result
