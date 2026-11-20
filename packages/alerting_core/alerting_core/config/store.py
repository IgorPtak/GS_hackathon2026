"""Persist configuration documents in Postgres and announce changes.

Startup rule (YAML files have no version field): a file is upserted into `config_documents` when
its canonical content differs from the stored `document` AND the file's mtime is newer than the
row's `updated_at`; otherwise the database copy (edited through the UI/API) wins.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
import yaml
from alerting_contracts.common import Actor
from alerting_contracts.sse import ConfigChangedEvent
from pydantic import BaseModel
from redis.asyncio import Redis

from ..logging import get_logger
from .kinds import get_kind
from .loader import LoadedDocument, LoadResult, load_config_directory

CONFIG_CHANGED_CHANNEL = "config.changed"
BROADCAST_CHANNEL = "broadcast"

log = get_logger(__name__)


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


async def save_config_document(
    pool: asyncpg.Pool,
    redis: Redis,
    kind: str,
    document: BaseModel | dict[str, Any],
    actor: Actor,
) -> int:
    """Validate, serialize to canonical YAML, bump `version`, write the DB and publish.

    A dict is validated with the kind's model first; an invalid document raises
    pydantic.ValidationError and nothing is written. Returns the new version.
    """
    model = (
        document if isinstance(document, BaseModel) else get_kind(kind).validate_document(document)
    )
    document_id = str(model.id)  # type: ignore[attr-defined]
    row = await pool.fetchrow(
        """
        INSERT INTO config_documents
            (kind, id, team, document, yaml, version, updated_at, updated_by)
        VALUES ($1, $2, $3, $4, $5, 1, now(), $6)
        ON CONFLICT (kind, id) DO UPDATE SET
            team = EXCLUDED.team, document = EXCLUDED.document, yaml = EXCLUDED.yaml,
            version = config_documents.version + 1, updated_at = now(),
            updated_by = EXCLUDED.updated_by
        RETURNING version
        """,
        kind,
        document_id,
        getattr(model, "team", None),
        canonical_document(model),
        canonical_yaml(model),
        actor.model_dump(mode="json", exclude_none=True),
    )
    version = int(row["version"])
    await publish_config_changed(redis, kind, document_id, version)
    log.info(
        "config_document_saved",
        extra={"kind": kind, "config_id": document_id, "version": version, "actor": actor.id},
    )
    return version


async def _is_file_newer(pool: asyncpg.Pool, loaded: LoadedDocument) -> bool:
    row = await pool.fetchrow(
        "SELECT document, updated_at FROM config_documents WHERE kind = $1 AND id = $2",
        loaded.kind,
        loaded.id,
    )
    if row is None:
        return True
    if row["document"] == canonical_document(loaded.model):
        return False
    modified = datetime.fromtimestamp(loaded.file.stat().st_mtime, UTC)
    return modified > row["updated_at"]


async def sync_config_files(
    pool: asyncpg.Pool,
    redis: Redis,
    config_dir: Path | str,
    actor: Actor | None = None,
) -> LoadResult:
    """Upsert files that win over the DB (see module docstring); invalid files are logged."""
    actor = actor or Actor(id="system:config-loader")
    result = load_config_directory(config_dir)
    for error in result.errors:
        log.error(
            "config_file_invalid",
            extra={"file": error.file, "path": error.path, "error": error.message},
        )
    for loaded in result.documents:
        if await _is_file_newer(pool, loaded):
            await save_config_document(pool, redis, loaded.kind, loaded.model, actor)
    return result
