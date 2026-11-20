"""Ingest HTTP service (track A, port 8001): accepts events and appends them to stream `events`."""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import orjson
from alerting_contracts.api import ErrorResponse, IngestAccepted
from alerting_contracts.config import SourceConfig
from alerting_contracts.events import EventEnvelope
from alerting_core.connections import create_redis_client
from alerting_core.logging import configure_logging, get_logger
from alerting_core.metrics import LATENCY_BUCKETS, render_metrics
from alerting_core.settings import Settings, get_settings
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram
from redis.asyncio import Redis
from ulid import ULID

from plugins.sources import get_source_plugin

from .sources import load_sources

log = get_logger(__name__)

STREAM = "events"
IDEMPOTENCY_TTL_SECONDS = 86400

EVENTS_TOTAL = Counter("ingest_events_total", "Events seen by ingest", ["source_id", "outcome"])
REQUEST_SECONDS = Histogram(
    "ingest_request_seconds", "Ingest request duration", buckets=LATENCY_BUCKETS
)


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


def lookup_path(payload: dict[str, Any], path: str) -> Any:
    """Value at a dot path in `payload`, or None when any segment is missing."""
    node: Any = payload
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def parse_sent_at(raw: str | None) -> datetime | None:
    """Parse the X-Sent-At header; invalid -> 422."""
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        raise RequestError(422, "validation_failed", "X-Sent-At must be ISO 8601") from None


def get_source(request: Request, source_id: str) -> SourceConfig | None:
    """Single lookup point for source config (A-03 replaces the body with the registry)."""
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
    """Wrap every payload from the source plugin in an EventEnvelope."""
    plugin = get_source_plugin(source.type)
    if plugin is None:
        raise RequestError(404, "not_found", "source is not an HTTP source")
    key_path = source.settings.get("idempotency_key_path")
    now = datetime.now(UTC)
    envelopes = []
    for body in bodies:
        for payload in plugin.extract_payloads(body, source):
            key = header_key
            if key is None and key_path:
                found = lookup_path(payload, key_path)
                key = None if found is None else str(found)
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
    return envelopes


async def append_envelopes(redis: Redis, envelopes: list[EventEnvelope]) -> tuple[list[str], int]:
    """XADD the non-duplicate envelopes; returns (accepted event ids, duplicate count)."""
    keyed = [e for e in envelopes if e.idempotency_key is not None]
    duplicates: set[str] = set()
    if keyed:
        pipe = redis.pipeline(transaction=False)
        for envelope in keyed:
            pipe.set(
                f"ingest-idempotency:{envelope.idempotency_key}",
                1,
                nx=True,
                ex=IDEMPOTENCY_TTL_SECONDS,
            )
        results = await pipe.execute()
        # The same key twice in one batch also works: SET NX makes the second one a duplicate.
        duplicates = {e.event_id for e, created in zip(keyed, results, strict=True) if not created}
    accepted = [e for e in envelopes if e.event_id not in duplicates]
    if accepted:
        pipe = redis.pipeline(transaction=False)
        for envelope in accepted:
            pipe.xadd(STREAM, {"envelope": orjson.dumps(envelope.model_dump(mode="json"))})
        await pipe.execute()
    return [e.event_id for e in accepted], len(duplicates)


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
        header_key = None if is_batch else request.headers.get("idempotency-key")
        envelopes = build_envelopes(source, bodies, header_key, sent_at)
        event_ids, duplicate_count = await append_envelopes(request.app.state.redis, envelopes)
    except RequestError as error:
        EVENTS_TOTAL.labels(source_id, "rejected").inc()
        return error_response(error.status, error.error, error.message)
    finally:
        REQUEST_SECONDS.observe(time.perf_counter() - started)
    EVENTS_TOTAL.labels(source_id, "accepted").inc(len(event_ids))
    if duplicate_count:
        EVENTS_TOTAL.labels(source_id, "duplicate").inc(duplicate_count)
    accepted = IngestAccepted(event_ids=event_ids, duplicate_count=duplicate_count)
    return JSONResponse(accepted.model_dump(mode="json"), status_code=202)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; Settings and the Redis client live in the lifespan (app.state)."""
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging("ingest", resolved.log_level)
        app.state.settings = resolved
        app.state.sources = load_sources(resolved.config_dir)
        app.state.redis = create_redis_client(resolved)
        log.info("ingest_started", extra={"sources": sorted(app.state.sources)})
        yield
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
