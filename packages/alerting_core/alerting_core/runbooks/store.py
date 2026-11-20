"""Runbooks as a registered config kind (`config/runbooks/*.yaml|md|txt`)."""

from pathlib import Path

import asyncpg
import yaml
from alerting_contracts.common import Actor
from alerting_contracts.config import ActionConfig
from alerting_contracts.runbooks import Runbook, RunbookFormat
from redis.asyncio import Redis

from plugins.runbook_formats.markdown_format import heading_text

from ..config import register_kind, save_config_document
from ..logging import get_logger
from .normalize import normalize_runbook

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


def load_runbook_file(path: Path) -> Runbook:
    """Read one runbook file and normalize it. id = file stem."""
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
    return normalize_runbook(path.stem, title, team, format, source, _sibling_actions(path))


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
