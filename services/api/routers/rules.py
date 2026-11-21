"""Routes tagged `rules`: list, read, save and delete rules stored in `config_documents`.

Source of truth is the `config_documents` table (kind = 'rule'): it holds the canonical YAML,
version, updated_at and updated_by that `RuleRecord` needs, and it is what `save_config_document`
writes. `POST /rules/preview` (B-16) is read-only: Redis reads and pure simulation.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
from alerting_contracts.api import (
    ConfigValidationError,
    ErrorResponse,
    RulePreview,
    RulePreviewRequest,
    RuleRecord,
    RuleWrite,
)
from alerting_core.config import publish_config_changed, save_config_document
from alerting_core.durations import parse_duration
from alerting_core.event_log import read_event_log
from alerting_core.logging import get_logger
from alerting_core.rules.conditions import compile_condition
from alerting_core.rules.preview import preview_rule
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..dependencies import PoolDep, RedisDep, RegistryDep
from ..errors import ApiError

router = APIRouter(tags=["rules"])
log = get_logger(__name__)

_COLUMNS = "id, yaml, version, updated_at, updated_by, document"


def dot_path(loc: tuple[Any, ...]) -> str:
    """Join a pydantic error `loc` into a dot path (`when.all.0.op`).

    Union member names pydantic inserts (`ConditionAll`, capitalised) are dropped; config keys
    are lowercase.
    """
    return ".".join(str(p) for p in loc if not (isinstance(p, str) and p[:1].isupper()))


def validation_errors(exc: ValidationError) -> list[ConfigValidationError]:
    """Convert pydantic errors to contract errors with dot paths."""
    return [ConfigValidationError(path=dot_path(e["loc"]), message=e["msg"]) for e in exc.errors()]


def validation_failed(message: str, details: list[ConfigValidationError]) -> JSONResponse:
    """422 `ErrorResponse` carrying `details`."""
    body = ErrorResponse(error="validation_failed", message=message, details=details)
    return JSONResponse(body.model_dump(mode="json"), status_code=422)


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _record(row: asyncpg.Record) -> RuleRecord:
    """Build a RuleRecord from a config_documents row."""
    updated_by = _json(row["updated_by"])
    return RuleRecord.model_validate(
        {
            "kind": "rule",
            "id": row["id"],
            "yaml": row["yaml"],
            "version": row["version"],
            "updated_at": row["updated_at"],
            "updated_by": updated_by,
            "rule": _json(row["document"]),
        }
    )


@router.get("/api/v1/rules")
async def list_rules(pool: PoolDep, team: str | None = None) -> list[RuleRecord]:
    """All rules, optionally of one team, ordered by id."""
    rows = await pool.fetch(
        f"SELECT {_COLUMNS} FROM config_documents "  # noqa: S608 (constant column list)
        "WHERE kind = 'rule' AND ($1::text IS NULL OR team = $1) ORDER BY id",
        team,
    )
    return [_record(row) for row in rows]


async def _fetch(pool: asyncpg.Pool, rule_id: str) -> RuleRecord:
    row = await pool.fetchrow(
        f"SELECT {_COLUMNS} FROM config_documents WHERE kind = 'rule' AND id = $1",  # noqa: S608
        rule_id,
    )
    if row is None:
        raise ApiError(404, "not_found", f"rule {rule_id!r} not found")
    return _record(row)


@router.post("/api/v1/rules/preview", response_model=RulePreview)
async def preview_rule_route(request: Request, redis: RedisDep, registry: RegistryDep) -> Any:
    """Simulate a draft rule over the last `window` of the events stream; no side effects."""
    try:
        payload = await request.json()
    except ValueError:
        return validation_failed(
            "body is not valid JSON", [ConfigValidationError(path="", message="invalid JSON")]
        )
    try:
        body = RulePreviewRequest.model_validate(payload)
    except ValidationError as exc:
        return validation_failed("invalid rule preview request", validation_errors(exc))
    if registry is None:
        raise ApiError(503, "unavailable", "configuration registry unavailable")
    window_end = datetime.now(UTC)
    window_start = window_end - timedelta(seconds=parse_duration(body.window))
    event_read = await read_event_log(redis, window_start, body.max_events)
    try:
        # CPU-bound pure simulation: keep it off the event loop.
        return await asyncio.to_thread(
            preview_rule,
            body.rule,
            event_read.envelopes,
            registry.snapshot,
            window_start=window_start,
            window_end=window_end,
            now=window_end,
            skipped_events=event_read.skipped_invalid,
            max_events=body.max_events,
        )
    except ValueError as exc:
        return validation_failed(
            "rule condition cannot be compiled",
            [ConfigValidationError(path="rule.when", message=str(exc))],
        )


@router.get("/api/v1/rules/{rule_id}")
async def get_rule(rule_id: str, pool: PoolDep) -> RuleRecord:
    """One rule or 404."""
    return await _fetch(pool, rule_id)


@router.put("/api/v1/rules/{rule_id}", response_model=RuleRecord)
async def save_rule(rule_id: str, request: Request, pool: PoolDep, redis: RedisDep) -> Any:
    """Create or replace a rule; bumps the version and publishes config.changed.

    The body is validated here (not by FastAPI) so a 422 carries dot-path `details`.
    """
    try:
        payload = await request.json()
    except ValueError:
        return validation_failed(
            "body is not valid JSON", [ConfigValidationError(path="", message="invalid JSON")]
        )
    try:
        write = RuleWrite.model_validate(payload)
    except ValidationError as exc:
        return validation_failed("invalid rule", validation_errors(exc))
    if write.rule.id != rule_id:
        return validation_failed(
            "rule id in body does not match the path",
            [
                ConfigValidationError(
                    path="rule.id", message=f"expected {rule_id!r}, got {write.rule.id!r}"
                )
            ],
        )
    try:
        compile_condition(write.rule.when)
    except (ValueError, TypeError) as exc:
        return validation_failed(
            "rule condition cannot be compiled",
            [ConfigValidationError(path="rule.when", message=str(exc))],
        )
    await save_config_document(pool, redis, "rule", write.rule, write.actor)
    return await _fetch(pool, rule_id)


@router.delete("/api/v1/rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: str, pool: PoolDep, redis: RedisDep) -> Response:
    """Delete a rule and publish config.changed (404 when missing)."""
    row = await pool.fetchrow(
        "DELETE FROM config_documents WHERE kind = 'rule' AND id = $1 RETURNING version", rule_id
    )
    if row is None:
        raise ApiError(404, "not_found", f"rule {rule_id!r} not found")
    try:
        await publish_config_changed(redis, "rule", rule_id, int(row["version"]))
    except Exception:  # noqa: BLE001  # the registry's reconcile loop repairs a lost notification
        log.exception("config_publish_failed", extra={"kind": "rule", "config_id": rule_id})
    log.info("config_document_deleted", extra={"kind": "rule", "config_id": rule_id})
    return Response(status_code=204)
