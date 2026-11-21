"""Ingest HTTP service (track A, port 8001): accepts events and appends them to stream `events`."""

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import orjson
from alerting_contracts.api import ErrorResponse, IngestAccepted
from alerting_contracts.config import SourceConfig
from alerting_contracts.events import EventEnvelope
from alerting_core.config.registry import ConfigRegistry
from alerting_core.config.store import sync_config_files
from alerting_core.connections import create_database_pool, create_redis_client
from alerting_core.logging import configure_logging, get_logger
from alerting_core.metrics import EVENTS_INGESTED, LATENCY_BUCKETS, render_metrics
from alerting_core.rules.field_paths import resolve_field_path
from alerting_core.runbooks.store import register_runbook_kind
from alerting_core.settings import Settings, get_settings
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram
from pydantic import ValidationError
from redis.asyncio.client import Redis
from redis.commands.core import AsyncScript
from redis.exceptions import RedisError
from ulid import ULID

from plugins.sources import get_source_plugin
from plugins.sources.log_tail import LogTailRunner

from .sources import LogTailSet

log = get_logger(__name__)

STREAM = "events"
IDEMPOTENCY_TTL_SECONDS = 86400

EVENTS_TOTAL = Counter("ingest_events_total", "Events seen by ingest", ["source_id", "outcome"])
REQUEST_SECONDS = Histogram(
    "ingest_request_seconds", "Ingest request duration", buckets=LATENCY_BUCKETS
)


# Set the idempotency key and append in one step; nil (false) means the key already existed.
APPEND_SCRIPT = """
if redis.call('SET', KEYS[1], '1', 'NX', 'EX', ARGV[1]) then
  return redis.call('XADD', KEYS[2], '*', 'envelope', ARGV[2])
else
  return false
end
"""


class RequestError(Exception):
    """A request rejected with an ErrorResponse."""

    def __init__(self, status: int, error: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.error = error
        self.message = message


def error_response(status: int, error: str, message: str) -> JSONResponse:
    """Build the contract `ErrorResponse` body."""
    body = ErrorResponse(error=error, message=message)
    return JSONResponse(body.model_dump(mode="json"), status_code=status)


def parse_sent_at(raw: str | None) -> datetime | None:
    """Parse the X-Sent-At header; invalid -> 422."""
    if raw is None:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        raise RequestError(422, "validation_failed", "X-Sent-At must be ISO 8601") from None
    if parsed.tzinfo is None:
        raise RequestError(422, "validation_failed", "sent_at must include a timezone")
    return parsed


def get_source(request: Request, source_id: str) -> SourceConfig | None:
    """Single lookup point: an in-memory dict that the registry callback swaps on reload."""
    return request.app.state.sources.get(source_id)


async def parse_body(request: Request) -> Any:
    """Decode the JSON body; non-JSON -> 422."""
    try:
        return orjson.loads(await request.body())
    except orjson.JSONDecodeError:
        raise RequestError(422, "validation_failed", "body is not valid JSON") from None


def build_envelopes(
    source: SourceConfig,
    bodies: list[Any],
    header_key: str | None,
    sent_at: datetime | None,
) -> list[EventEnvelope]:
    """Wrap every payload from the source plugin in an EventEnvelope.

    The caller has already checked that the source type has an HTTP plugin.
    """
    plugin = get_source_plugin(source.type)
    if plugin is None:
        raise RequestError(404, "not_found", "source is not an HTTP source")
    key_path = source.settings.get("idempotency_key_path")
    now = datetime.now(UTC)
    payloads = [p for body in bodies for p in plugin.extract_payloads(body, source)]
    envelopes = []
    for index, payload in enumerate(payloads):
        key = None
        if header_key:
            # One client key for several payloads would drop all but the first event.
            key = header_key if len(payloads) == 1 else f"{header_key}:{index}"
        elif key_path:
            is_found, found = resolve_field_path(payload, key_path)
            key = str(found) if is_found and found is not None else None
        else:
            key = plugin.idempotency_key(payload, source)
        try:
            envelopes.append(
                EventEnvelope(
                    event_id=str(ULID()),
                    idempotency_key=key,
                    source_id=source.id,
                    source_type=source.type,
                    received_at=now,
                    sent_at=sent_at,
                    payload=payload,
                )
            )
        except ValidationError as error:
            raise RequestError(422, "validation_failed", f"invalid event: {error}") from None
    return envelopes


async def append_envelopes(
    redis: Redis, script: AsyncScript, envelopes: list[EventEnvelope]
) -> tuple[list[str], int]:
    """Append envelopes in one pipeline; returns (accepted event ids, duplicate count).

    Keyed envelopes go through a Lua script so the idempotency key is only set when the XADD
    happens in the same step; a failed append never blocks the client's retry.
    """
    pipe = redis.pipeline(transaction=False)
    for envelope in envelopes:
        # One pass in pydantic-core instead of model_dump + orjson.dumps.
        raw = envelope.model_dump_json()
        if envelope.idempotency_key is None:
            pipe.xadd(STREAM, {"envelope": raw})
        else:
            pipe.scripts.add(script)
            pipe.evalsha(
                script.sha,
                2,
                f"ingest-idempotency:{envelope.idempotency_key}",
                STREAM,
                IDEMPOTENCY_TTL_SECONDS,
                raw,
            )
    results = await pipe.execute()
    # A nil result means SET NX found the key: a duplicate.
    accepted = [e.event_id for e, result in zip(envelopes, results, strict=True) if result]
    return accepted, len(envelopes) - len(accepted)


def parse_bodies(body: Any, *, is_batch: bool) -> list[Any]:
    """Validate the body shape: object for single, array of objects for batch."""
    if is_batch:
        if not isinstance(body, list) or not all(isinstance(item, dict) for item in body):
            raise RequestError(422, "validation_failed", "body must be an array of objects")
        return body
    if not isinstance(body, dict):
        raise RequestError(422, "validation_failed", "body must be a JSON object")
    return [body]


async def handle_ingest(request: Request, source_id: str, *, is_batch: bool) -> Response:
    """Shared body of the single and batch endpoints."""
    started = time.perf_counter()
    try:
        source = get_source(request, source_id)
        if source is None or not source.enabled or get_source_plugin(source.type) is None:
            raise RequestError(404, "not_found", f"unknown source '{source_id}'")
        bodies = parse_bodies(await parse_body(request), is_batch=is_batch)
        sent_at = parse_sent_at(request.headers.get("x-sent-at"))
        header_key = None if is_batch else (request.headers.get("idempotency-key") or "").strip()
        envelopes = build_envelopes(source, bodies, header_key, sent_at)
        try:
            event_ids, duplicate_count = await append_envelopes(
                request.app.state.redis, request.app.state.append_script, envelopes
            )
        except RedisError as error:
            log.error("ingest_append_failed", extra={"source_id": source_id, "error": str(error)})
            raise RequestError(503, "unavailable", "event store unavailable, retry") from None
    except RequestError as error:
        EVENTS_TOTAL.labels(source_id, "rejected").inc()
        return error_response(error.status, error.error, error.message)
    finally:
        REQUEST_SECONDS.observe(time.perf_counter() - started)
    EVENTS_TOTAL.labels(source_id, "accepted").inc(len(event_ids))
    EVENTS_INGESTED.inc(len(event_ids))
    if duplicate_count:
        EVENTS_TOTAL.labels(source_id, "duplicate").inc(duplicate_count)
    accepted = IngestAccepted(event_ids=event_ids, duplicate_count=duplicate_count)
    return JSONResponse(accepted.model_dump(mode="json"), status_code=202)


def make_tail_starter(app: FastAPI) -> Callable[[SourceConfig], Awaitable[None]]:
    """Return the coroutine factory `LogTailSet` uses to run one source's tail (lock inside)."""

    async def start_tail(source: SourceConfig) -> None:
        async def append(envelopes: list[EventEnvelope]) -> None:
            event_ids, duplicates = await append_envelopes(
                app.state.redis, app.state.append_script, envelopes
            )
            EVENTS_TOTAL.labels(source.id, "accepted").inc(len(event_ids))
            EVENTS_INGESTED.inc(len(event_ids))
            if duplicates:
                EVENTS_TOTAL.labels(source.id, "duplicate").inc(duplicates)

        await LogTailRunner(source, app.state.redis, append).run()

    return start_tail


def create_app(settings: Settings | None = None, registry: ConfigRegistry | None = None) -> FastAPI:
    """Build the app; Settings, Redis and the config registry live in the lifespan (app.state).

    A caller-supplied `registry` is already started and owned by the caller (tests).
    """
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging("ingest", resolved.log_level)
        app.state.settings = resolved
        app.state.redis = create_redis_client(resolved)
        app.state.append_script = app.state.redis.register_script(APPEND_SCRIPT)
        pool = None
        config = registry
        if config is None:
            pool = await create_database_pool(resolved)
            register_runbook_kind()
            # Atomic per document, so every replica may run it; covers a cold database.
            await sync_config_files(pool, app.state.redis, resolved.config_dir)
            config = ConfigRegistry()
            await config.start(pool, app.state.redis)
        tails = LogTailSet(make_tail_starter(app))

        def apply_sources(_snapshot: object = None) -> None:
            # Swapping the dict reference keeps the per-request lookup a plain dict get.
            app.state.sources = dict(config.sources())
            tails.reconcile(app.state.sources)
            log.info("ingest_sources_applied", extra={"sources": sorted(app.state.sources)})

        apply_sources()
        config.on_reload.append(apply_sources)
        log.info("ingest_started", extra={"sources": sorted(app.state.sources)})
        yield
        config.on_reload.remove(apply_sources)
        await tails.stop()
        if pool is not None:
            await config.stop()
            await pool.close()
        await app.state.redis.aclose()

    app = FastAPI(lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Liveness probe used by compose healthchecks."""
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics() -> Response:
        """Prometheus exposition."""
        body, content_type = render_metrics()
        return Response(body, media_type=content_type)

    @app.post("/api/v1/ingest/{source_id}/batch")
    async def ingest_event_batch(request: Request, source_id: str) -> Response:
        """Accept a JSON array of events."""
        return await handle_ingest(request, source_id, is_batch=True)

    @app.post("/api/v1/ingest/{source_id}")
    async def ingest_event(request: Request, source_id: str) -> Response:
        """Accept one event from an HTTP source."""
        return await handle_ingest(request, source_id, is_batch=False)

    return app


app = create_app()
