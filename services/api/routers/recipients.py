"""Routes tagged `config` for recipients: replace a recipient's channel preferences (B-18).

The recipient document is read from Postgres (falling back to the registry snapshot, which can lag
one config.changed behind a save that just happened) and saved through
`save_config_document` (a new version, published as config.changed). The request is idempotent:
when the canonical document equals the current one nothing is written, so the same request twice
leaves the same state and a single version.
"""

import json
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from alerting_contracts.api import ChannelPreferencesWrite, ConfigValidationError
from alerting_contracts.config import ChannelPreference, Recipient
from alerting_core.config import save_config_document
from alerting_core.config.store import canonical_document
from alerting_core.logging import get_logger
from asyncpg import Pool
from fastapi import APIRouter, Request
from pydantic import ValidationError

from ..dependencies import PoolDep, RedisDep, RegistryDep
from ..errors import ApiError, error_response
from .rules import validation_errors, validation_failed

router = APIRouter(tags=["config"])
log = get_logger(__name__)


def _unknown_channels(
    preferences: list[ChannelPreference], known: set[str]
) -> list[ConfigValidationError]:
    """Dot-path errors for every channel id that is not configured."""
    errors: list[ConfigValidationError] = []
    for index, preference in enumerate(preferences):
        for field, ids in (("channels", preference.channels), ("otherwise", preference.otherwise)):
            for position, channel_id in enumerate(ids):
                if channel_id not in known:
                    errors.append(
                        ConfigValidationError(
                            path=f"channel_preferences.{index}.{field}.{position}",
                            message=f"unknown channel {channel_id!r}",
                        )
                    )
    return errors


def _invalid_timezones(preferences: list[ChannelPreference]) -> list[ConfigValidationError]:
    errors: list[ConfigValidationError] = []
    for index, preference in enumerate(preferences):
        try:
            ZoneInfo(preference.timezone)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            errors.append(
                ConfigValidationError(
                    path=f"channel_preferences.{index}.timezone",
                    message=f"unknown timezone {preference.timezone!r}",
                )
            )
    return errors


def check_preferences(
    preferences: list[ChannelPreference], known_channels: set[str]
) -> list[ConfigValidationError]:
    """Semantic checks the contract cannot express (empty list = valid)."""
    return _unknown_channels(preferences, known_channels) + _invalid_timezones(preferences)


async def _stored_recipient(pool: Pool, recipient_id: str) -> Recipient | None:
    """The newest saved version, so an immediate repeat of a PUT compares with what it wrote."""
    raw = await pool.fetchval(
        "SELECT document FROM config_documents WHERE kind = 'recipient' AND id = $1", recipient_id
    )
    if raw is None:
        return None
    return Recipient.model_validate(json.loads(raw) if isinstance(raw, str) else raw)


async def _parse_body(request: Request) -> ChannelPreferencesWrite | Any:
    """The validated body, or a 422 response."""
    try:
        payload = await request.json()
    except ValueError:
        return validation_failed(
            "body is not valid JSON", [ConfigValidationError(path="", message="invalid JSON")]
        )
    try:
        return ChannelPreferencesWrite.model_validate(payload)
    except ValidationError as exc:
        return validation_failed("invalid channel preferences", validation_errors(exc))


@router.put("/api/v1/recipients/{recipient_id}/channel-preferences", response_model=Recipient)
async def update_channel_preferences(
    recipient_id: str,
    request: Request,
    pool: PoolDep,
    redis: RedisDep,
    registry: RegistryDep,
) -> Any:
    """Replace the channel preferences of one recipient; unchanged input saves nothing."""
    body = await _parse_body(request)
    if not isinstance(body, ChannelPreferencesWrite):
        return body
    if registry is None:
        raise ApiError(503, "unavailable", "configuration registry unavailable")
    current = await _stored_recipient(pool, recipient_id) or registry.recipients().get(recipient_id)
    if current is None:
        return error_response(404, "not_found", f"recipient {recipient_id!r} not found")
    errors = check_preferences(body.channel_preferences, set(registry.channels()))
    if errors:
        return validation_failed("invalid channel preferences", errors)
    updated = Recipient.model_validate(
        {
            **current.model_dump(),
            "channel_preferences": [p.model_dump() for p in body.channel_preferences],
        }
    )
    if canonical_document(updated) == canonical_document(current):
        return current
    await save_config_document(pool, redis, "recipient", updated, body.actor)
    log.info(
        "channel_preferences_saved",
        extra={"recipient_id": recipient_id, "actor": body.actor.id},
    )
    return updated
