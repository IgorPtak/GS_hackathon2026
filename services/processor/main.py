"""Processor worker: consumes `events`, creates alerts; serves /healthz and /metrics on 9101."""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from alerting_core.config.registry import ConfigRegistry
from alerting_core.config.store import sync_config_files
from alerting_core.connections import create_database_pool, create_redis_client
from alerting_core.logging import configure_logging, get_logger
from alerting_core.metrics import render_metrics
from alerting_core.runbooks.store import register_runbook_kind
from alerting_core.settings import Settings, get_settings
from alerting_core.streams import StreamConsumer, default_consumer_name
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError

from .batch import EventProcessor
from .folds import FoldTracker

log = get_logger(__name__)

EVENTS_STREAM = "events"
CONSUMER_GROUP = "processors"
# Entries older than this are trimmed; by then they were processed or dead-lettered long ago.
EVENTS_RETENTION_MS = 2 * 60 * 60 * 1000
TRIM_INTERVAL_SECONDS = 60.0


async def trim_events(redis: Redis, stop: asyncio.Event) -> None:
    """XTRIM `events` by MINID (now - 2 h) every minute."""
    while not stop.is_set():
        min_id = f"{int(time.time() * 1000) - EVENTS_RETENTION_MS}-0"
        try:
            await redis.xtrim(EVENTS_STREAM, minid=min_id, approximate=True)
        except RedisError:
            log.exception("events_trim_failed")
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=TRIM_INTERVAL_SECONDS)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; consumer, fold flusher and trimmer run for the app's lifetime."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings or get_settings()
        configure_logging("processor", resolved.log_level)
        pool = await create_database_pool(resolved)
        redis = create_redis_client(resolved)
        # Before the sync, so config/runbooks lands in config_documents (B-07 renders steps).
        register_runbook_kind()
        # Atomic per document, so every replica may run it; the api's watcher handles later edits.
        await sync_config_files(pool, redis, resolved.config_dir)
        registry = ConfigRegistry()
        await registry.start(pool, redis)
        folds = FoldTracker(pool, redis)
        processor = EventProcessor(pool, redis, registry, resolved, folds)
        consumer = StreamConsumer(
            redis,
            EVENTS_STREAM,
            CONSUMER_GROUP,
            default_consumer_name("processor"),
            processor.handle_batch,
        )
        processor.dead_letter = consumer.dead_letter
        stop = asyncio.Event()
        tasks = [
            asyncio.create_task(consumer.run(stop)),
            asyncio.create_task(folds.run(stop)),
            asyncio.create_task(trim_events(redis, stop)),
        ]
        app.state.tasks = tasks
        yield
        stop.set()
        with suppress(asyncio.CancelledError, TimeoutError):
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
        # The consumer may fold after the flusher's last pass; flush once more after it stopped.
        # A SIGKILL still leaves up to one second of folds in Redis until the key folds again.
        with suppress(Exception):
            await folds.flush()
        await registry.stop()
        await redis.aclose()
        await pool.close()

    app = FastAPI(lifespan=lifespan)

    @app.get("/healthz", response_model=None)
    async def healthz() -> dict[str, str] | JSONResponse:
        """Liveness probe: 503 once any background loop has died."""
        tasks: list[asyncio.Task[None]] = getattr(app.state, "tasks", [])
        if any(task.done() for task in tasks):
            return JSONResponse({"status": "worker_stopped"}, status_code=503)
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics() -> Response:
        """Prometheus exposition."""
        body, content_type = render_metrics()
        return Response(body, media_type=content_type)

    return app


app = create_app()
