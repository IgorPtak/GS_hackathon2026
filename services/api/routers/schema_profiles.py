"""Routes tagged `schema-profiles`: profile CRUD, unknown-schema inbox, propose and test.

Profiles live in `config_documents` (kind = 'schema_profile'). `propose` and `test` are
read-only: `test` only does XRANGE on the events stream and runs the A-07 matcher on the draft.
"""

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
from alerting_contracts.api import (
    ConfigValidationError,
    SchemaProfileProposeRequest,
    SchemaProfileRecord,
    SchemaProfileTestRequest,
    SchemaProfileTestResult,
    SchemaProfileTestSample,
    SchemaProfileWrite,
    UnknownSchemaSample,
)
from alerting_contracts.events import EventEnvelope, SourceType
from alerting_contracts.proposals import SchemaProfileProposal
from alerting_core.config import save_config_document
from alerting_core.durations import parse_duration
from alerting_core.event_log import read_event_log
from alerting_core.events.compiled import compile_profile
from alerting_core.events.normalize import normalize_compiled
from fastapi import APIRouter, Request
from pydantic import BaseModel, ValidationError

from ..dependencies import PoolDep, RedisDep
from ..errors import ApiError
from ..schema_proposal import propose_profile_heuristic
from .rules import validation_errors, validation_failed

router = APIRouter(tags=["schema-profiles"])

_COLUMNS = "id, yaml, version, updated_at, updated_by, document"
_MAX_SAMPLES = 20
_MAX_EVENTS = 50_000


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _record(row: asyncpg.Record) -> SchemaProfileRecord:
    return SchemaProfileRecord.model_validate(
        {
            "kind": "schema_profile",
            "id": row["id"],
            "yaml": row["yaml"],
            "version": row["version"],
            "updated_at": row["updated_at"],
            "updated_by": _json(row["updated_by"]),
            "schema_profile": _json(row["document"]),
        }
    )


async def _body[M: BaseModel](request: Request, model: type[M], what: str) -> M | Any:
    """Validate the JSON body by hand so a 422 carries dot-path `details`."""
    try:
        payload = await request.json()
    except ValueError:
        return validation_failed(
            "body is not valid JSON", [ConfigValidationError(path="", message="invalid JSON")]
        )
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        return validation_failed(f"invalid {what}", validation_errors(exc))


@router.get("/api/v1/schema-profiles")
async def list_schema_profiles(pool: PoolDep) -> list[SchemaProfileRecord]:
    """All schema profiles ordered by id."""
    rows = await pool.fetch(
        f"SELECT {_COLUMNS} FROM config_documents "  # noqa: S608 (constant column list)
        "WHERE kind = 'schema_profile' ORDER BY id"
    )
    return [_record(row) for row in rows]


@router.get("/api/v1/unknown-schemas")
async def list_unknown_schemas(pool: PoolDep) -> list[UnknownSchemaSample]:
    """Unknown-schema inbox, newest `last_seen` first."""
    rows = await pool.fetch(
        "SELECT shape_hash, source_id, key_paths, sample_event, event_count, first_seen, "
        "last_seen FROM unknown_schema_samples ORDER BY last_seen DESC"
    )
    return [
        UnknownSchemaSample.model_validate(
            {
                **dict(row),
                "key_paths": list(row["key_paths"]),
                "sample_event": _json(row["sample_event"]),
            }
        )
        for row in rows
    ]


@router.post("/api/v1/schema-profiles/propose", response_model=SchemaProfileProposal)
async def propose_schema_profile(request: Request) -> Any:
    """Draft a profile for a sample event (heuristic; B-21 adds the LLM variant here)."""
    body = await _body(request, SchemaProfileProposeRequest, "propose request")
    if not isinstance(body, SchemaProfileProposeRequest):
        return body
    try:
        return propose_profile_heuristic(body.sample_event, body.profile_id)
    except (ValidationError, ValueError, TypeError, re.error) as exc:
        return validation_failed(
            "no valid profile could be proposed for this sample",
            [ConfigValidationError(path="sample_event", message=str(exc))],
        )


def _test_envelope(payload: dict[str, Any], now: datetime) -> EventEnvelope:
    return EventEnvelope(
        event_id="sample",
        source_id="schema-profile-test",
        source_type=SourceType.webhook,
        received_at=now,
        payload=payload,
    )


@router.post("/api/v1/schema-profiles/test", response_model=SchemaProfileTestResult)
async def test_schema_profile(request: Request, redis: RedisDep) -> Any:
    """Run the DRAFT profile over the sample event and recent events; no side effects.

    `events_scanned`/`events_matched` count the recent stored events only; the optional sample
    event is tested first and appears in `samples` with `event_id` null.
    """
    body = await _body(request, SchemaProfileTestRequest, "schema profile test request")
    if not isinstance(body, SchemaProfileTestRequest):
        return body
    try:
        compiled = compile_profile(body.schema_profile)
    except (ValueError, TypeError, re.error) as exc:
        return validation_failed(
            "schema profile cannot be compiled",
            [ConfigValidationError(path="schema_profile.match", message=str(exc))],
        )
    now = datetime.now(UTC)
    samples: list[SchemaProfileTestSample] = []
    if body.sample_event is not None and compiled.match(body.sample_event):
        samples.append(
            SchemaProfileTestSample(
                event_id=None,
                normalized=normalize_compiled(_test_envelope(body.sample_event, now), compiled),
            )
        )
    since = now - timedelta(seconds=parse_duration(body.window))
    event_read = await read_event_log(redis, since, _MAX_EVENTS)
    matched = 0
    for envelope in event_read.envelopes:
        if not compiled.match(envelope.payload):
            continue
        matched += 1
        if len(samples) < _MAX_SAMPLES:
            samples.append(
                SchemaProfileTestSample(
                    event_id=envelope.event_id, normalized=normalize_compiled(envelope, compiled)
                )
            )
    return SchemaProfileTestResult(
        events_scanned=len(event_read.envelopes), events_matched=matched, samples=samples
    )


@router.put("/api/v1/schema-profiles/{profile_id}", response_model=SchemaProfileRecord)
async def save_schema_profile(
    profile_id: str, request: Request, pool: PoolDep, redis: RedisDep
) -> Any:
    """Create or replace a schema profile (new version, publishes config.changed)."""
    write = await _body(request, SchemaProfileWrite, "schema profile")
    if not isinstance(write, SchemaProfileWrite):
        return write
    if write.schema_profile.id != profile_id:
        return validation_failed(
            "schema profile id in body does not match the path",
            [
                ConfigValidationError(
                    path="schema_profile.id",
                    message=f"expected {profile_id!r}, got {write.schema_profile.id!r}",
                )
            ],
        )
    await save_config_document(pool, redis, "schema_profile", write.schema_profile, write.actor)
    row = await pool.fetchrow(
        f"SELECT {_COLUMNS} FROM config_documents "  # noqa: S608 (constant column list)
        "WHERE kind = 'schema_profile' AND id = $1",
        profile_id,
    )
    if row is None:
        raise ApiError(404, "not_found", f"schema profile {profile_id!r} not found")
    return _record(row)
