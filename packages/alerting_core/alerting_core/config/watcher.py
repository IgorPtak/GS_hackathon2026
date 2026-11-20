"""Watch `config/` and push edited files through the same save path as the API."""

from pathlib import Path

import asyncpg
from alerting_contracts.common import Actor
from redis.asyncio import Redis
from watchfiles import Change, awatch

from ..logging import get_logger
from .kinds import kind_for_directory
from .loader import LoadedDocument, load_config_file
from .store import canonical_document, save_config_document

log = get_logger(__name__)

DEFAULT_ACTOR = Actor(id="system:config-watcher")


async def handle_config_file_change(
    file: Path,
    pool: asyncpg.Pool,
    redis: Redis,
    actor: Actor = DEFAULT_ACTOR,
) -> bool:
    """Validate one changed file and save it. Returns True when a new version was written.

    Invalid files are logged as `config_file_invalid` and never saved. A file whose content
    already equals the stored document is skipped so editor saves do not bump versions.
    """
    spec = kind_for_directory(file.parent.name)
    if spec is None or file.suffix not in spec.suffixes:
        return False
    outcome = load_config_file(spec, file)
    if not isinstance(outcome, LoadedDocument):
        for error in outcome:
            log.error(
                "config_file_invalid",
                extra={"file": error.file, "path": error.path, "error": error.message},
            )
        return False
    stored = await pool.fetchval(
        "SELECT document FROM config_documents WHERE kind = $1 AND id = $2",
        outcome.kind,
        outcome.id,
    )
    if stored == canonical_document(outcome.model):
        return False
    await save_config_document(pool, redis, outcome.kind, outcome.model, actor)
    return True


async def watch_config_directory(
    path: Path | str,
    pool: asyncpg.Pool,
    redis: Redis,
    actor: Actor = DEFAULT_ACTOR,
) -> None:
    """Run until cancelled, saving every added or modified file under `path`."""
    async for changes in awatch(Path(path)):
        for change, changed_path in changes:
            if change is Change.deleted:
                continue  # deleting a file never deletes a document; use the API for that
            await handle_config_file_change(Path(changed_path), pool, redis, actor)
