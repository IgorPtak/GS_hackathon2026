"""Runbook runner worker: consumes `runbook-jobs`; serves /healthz and /metrics on 9104."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from alerting_core.config.registry import ConfigRegistry
from alerting_core.config.store import sync_config_files
from alerting_core.connections import create_database_pool, create_redis_client
from alerting_core.logging import configure_logging
from alerting_core.metrics import render_metrics
from alerting_core.runbooks.store import register_runbook_kind
from alerting_core.settings import Settings, get_settings
from alerting_core.streams import StreamConsumer, default_consumer_name
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from .runner import RunbookRunner

JOBS_STREAM = "runbook-jobs"
CONSUMER_GROUP = "runbook-runners"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; the consumer runs for the app's lifetime."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings or get_settings()
        configure_logging("runbook-runner", resolved.log_level)
        pool = await create_database_pool(resolved)
        redis = create_redis_client(resolved)
        # The runbook kind must be known before the first load, or runbooks would be dropped.
        register_runbook_kind()
        # Runbook files reach the DB only through a loader that knows the kind; the processor
        # does not register it, so sync here (atomic per document, safe next to other replicas).
        await sync_config_files(pool, redis, resolved.config_dir)
        registry = ConfigRegistry()
        await registry.start(pool, redis)
        runner = RunbookRunner(pool, redis, registry, resolved)
        consumer = StreamConsumer(
            redis,
            JOBS_STREAM,
            CONSUMER_GROUP,
            default_consumer_name("runbook-runner"),
            runner.handle_batch,
            # A job holds the alert lock for up to lock_timeout (120 s) plus plugin calls; stay
            # above that so entries are not reclaimed while still being worked on.
            batch_size=10,
            min_idle_seconds=180.0,
        )
        runner.dead_letter = consumer.dead_letter
        stop = asyncio.Event()
        app.state.tasks = [asyncio.create_task(consumer.run(stop))]
        yield
        stop.set()
        with suppress(asyncio.CancelledError, TimeoutError):
            await asyncio.wait_for(asyncio.gather(*app.state.tasks), timeout=15)
        await registry.stop()
        await redis.aclose()
        await pool.close()

    app = FastAPI(lifespan=lifespan)

    @app.get("/healthz", response_model=None)
    async def healthz() -> dict[str, str] | JSONResponse:
        """Liveness probe: 503 once the consumer loop has died."""
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
