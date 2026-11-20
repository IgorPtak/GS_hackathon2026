"""Delivery worker: consumes `deliveries`, sends through channel plugins; /healthz, /metrics."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import httpx
from alerting_core.config.registry import ConfigRegistry
from alerting_core.connections import create_database_pool, create_redis_client
from alerting_core.logging import configure_logging
from alerting_core.metrics import render_metrics
from alerting_core.settings import Settings, get_settings
from alerting_core.streams import StreamConsumer, default_consumer_name
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

import plugins.channels  # noqa: F401  (registers the built-in channel plugins)
from plugins.channels.base import ChannelContext

from .retries import DELIVERIES_STREAM, run_retry_poller
from .worker import MAX_CONCURRENT_SENDS, DeliveryWorker

CONSUMER_GROUP = "delivery-workers"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; the consumer and the retry poller run for the app's lifetime."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings or get_settings()
        configure_logging("delivery", resolved.log_level)
        pool = await create_database_pool(resolved)
        redis = create_redis_client(resolved)
        # Redirects are never followed: a 3xx from a channel endpoint is not a delivery.
        http = httpx.AsyncClient(timeout=5.0, follow_redirects=False)
        registry = ConfigRegistry()
        await registry.start(pool, redis)
        context = ChannelContext(redis=redis, http=http, settings=resolved, database=pool)
        worker = DeliveryWorker(pool, redis, registry, context)
        consumer = StreamConsumer(
            redis,
            DELIVERIES_STREAM,
            CONSUMER_GROUP,
            default_consumer_name("delivery"),
            worker.handle_batch,
            # One batch never exceeds the semaphore, and an idle claim needs more than the
            # slowest send; infrastructure outages get 20 redeliveries before the stream DLQ.
            batch_size=MAX_CONCURRENT_SENDS,
            min_idle_seconds=60,
            max_deliveries=20,
        )
        stop = asyncio.Event()
        tasks = [
            asyncio.create_task(consumer.run(stop)),
            asyncio.create_task(run_retry_poller(redis, stop)),
        ]
        app.state.tasks = tasks
        yield
        stop.set()
        with suppress(asyncio.CancelledError, TimeoutError):
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=20)
        await registry.stop()
        await http.aclose()
        await redis.aclose()
        await pool.close()

    app = FastAPI(lifespan=lifespan)

    @app.get("/healthz", response_model=None)
    async def healthz() -> dict[str, str] | JSONResponse:
        """Liveness probe: 503 once a background loop has died."""
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
