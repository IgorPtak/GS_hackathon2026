"""Source config for ingest: file loader (tests, fallback) and the hot-reloading log-tail set."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

import yaml
from alerting_contracts.config import SourceConfig
from alerting_contracts.events import SourceType
from alerting_core.logging import get_logger

log = get_logger(__name__)


def load_sources(config_dir: str) -> dict[str, SourceConfig]:
    """Read `<config_dir>/sources/*.yaml`; invalid files are logged and skipped."""
    sources: dict[str, SourceConfig] = {}
    for path in sorted(Path(config_dir, "sources").glob("*.yaml")):
        try:
            source = SourceConfig.model_validate(yaml.safe_load(path.read_text()))
        except (OSError, ValueError, yaml.YAMLError) as error:
            log.error("source_config_invalid", extra={"path": str(path), "error": str(error)})
            continue
        sources[source.id] = source
    return sources


class LogTailSet:
    """Keeps one background tail task per enabled `log_tail` source, in step with the config.

    `reconcile` is synchronous (registry callbacks are) and only touches the sources whose config
    changed: a new source starts, a removed or disabled one stops, an edited one restarts alone.
    """

    def __init__(self, start_tail: Callable[[SourceConfig], Awaitable[None]]) -> None:
        self._start_tail = start_tail
        self._tails: dict[str, tuple[SourceConfig, asyncio.Task[None]]] = {}

    @property
    def source_ids(self) -> list[str]:
        """Ids of the sources that currently have a tail task."""
        return sorted(self._tails)

    def reconcile(self, sources: Mapping[str, SourceConfig]) -> None:
        """Start, stop or restart tail tasks so they match `sources`."""
        wanted = {
            source_id: source
            for source_id, source in sources.items()
            if source.type == SourceType.log_tail and source.enabled
        }
        for source_id in [i for i in self._tails if i not in wanted]:
            self._tails.pop(source_id)[1].cancel()
            log.info("log_tail_stopped", extra={"source_id": source_id})
        for source_id, source in wanted.items():
            current = self._tails.get(source_id)
            if current is not None and current[0] == source:
                continue
            previous = current[1] if current is not None else None
            if previous is not None:
                previous.cancel()
            task = asyncio.create_task(
                self._run_after(previous, source), name=f"log-tail-{source_id}"
            )
            self._tails[source_id] = (source, task)
            log.info(
                "log_tail_started",
                extra={"source_id": source_id, "is_restart": previous is not None},
            )

    async def _run_after(self, previous: asyncio.Task[None] | None, source: SourceConfig) -> None:
        # Wait for the old runner to release its Redis lock so the new one takes it at once.
        # asyncio.wait never raises the old task's cancellation, so a cancel aimed at this task
        # (a newer reconcile or stop()) still propagates and no untracked tail is started.
        if previous is not None:
            await asyncio.wait([previous])
        await self._start_tail(source)

    async def stop(self) -> None:
        """Cancel every tail task and wait for them."""
        tasks = [task for _, task in self._tails.values()]
        self._tails.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
