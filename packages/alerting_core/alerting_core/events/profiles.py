"""Pick the schema profile of a raw event."""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from alerting_contracts.config import SchemaProfile
from alerting_contracts.events import EventEnvelope, NormalizedFields

from alerting_core.logging import get_logger

from .compiled import CompiledProfile, compile_profile
from .normalize import normalize_compiled

GENERIC_PROFILE_ID = "generic"
_log = get_logger(__name__)


def _fallback_profile() -> SchemaProfile:
    """Used only when the configured profiles contain no usable `generic` one."""
    return SchemaProfile.model_validate(
        {
            "id": GENERIC_PROFILE_ID,
            "priority": 0,
            "match": {"field": "severity", "op": "exists", "value": True},
            "fields": {"type": {"const": "unknown"}, "source": {"const": "generic-webhook"}},
            "fingerprint": ["evt", "svc"],
        }
    )


class ProfileMatcher:
    """Profiles compiled and ordered once (priority desc, config order for ties).

    Build one per config reload. A profile whose condition does not compile is logged once and
    skipped; nothing raises on the hot path.
    """

    def __init__(self, profiles: Sequence[SchemaProfile]) -> None:
        compiled: list[CompiledProfile] = []
        for profile in sorted(profiles, key=lambda p: -p.priority):
            try:
                compiled.append(compile_profile(profile))
            except (ValueError, TypeError, re.error) as error:
                _log.error(
                    "schema_profile_skipped",
                    extra={"schema_profile_id": profile.id, "error": str(error)},
                )
        self._ordered = compiled
        self._by_id = {c.profile.id: c for c in compiled}
        self._generic = self._by_id.get(GENERIC_PROFILE_ID) or compile_profile(_fallback_profile())

    def _select(self, payload: Mapping[str, Any]) -> tuple[CompiledProfile, bool]:
        first: CompiledProfile | None = None
        for candidate in self._ordered:
            if not candidate.match(payload):
                continue
            if candidate.profile.id != GENERIC_PROFILE_ID:
                return (first or candidate), False
            # Generic may win on priority; a lower-priority specific match still means "known".
            first = first or candidate
        return (first or self._generic), True

    def select(self, payload: Mapping[str, Any]) -> SchemaProfile:
        """Highest-priority matching profile, else the generic one (never None)."""
        return self._select(payload)[0].profile

    def select_with_flag(self, payload: Mapping[str, Any]) -> tuple[SchemaProfile, bool]:
        """(profile, is_unknown_shape) from one pass over the profiles."""
        compiled, is_unknown = self._select(payload)
        return compiled.profile, is_unknown

    def is_unknown_shape(self, payload: Mapping[str, Any]) -> bool:
        """True when no non-generic profile matches (unknown-schema inbox candidate)."""
        return self._select(payload)[1]

    def normalize(self, envelope: EventEnvelope, profile: SchemaProfile) -> NormalizedFields:
        """normalize_event using the profile's precompiled form (hot path)."""
        compiled = self._by_id.get(profile.id)
        if compiled is None or compiled.profile is not profile:
            compiled = compile_profile(profile)
        return normalize_compiled(envelope, compiled)


def _as_matcher(profiles: Sequence[SchemaProfile] | ProfileMatcher) -> ProfileMatcher:
    return profiles if isinstance(profiles, ProfileMatcher) else ProfileMatcher(profiles)


def select_schema_profile(
    payload: Mapping[str, Any], profiles: Sequence[SchemaProfile] | ProfileMatcher
) -> SchemaProfile:
    """Highest-priority matching profile, else `generic`. Pass a ProfileMatcher on the hot path."""
    return _as_matcher(profiles).select(payload)


def is_unknown_shape(
    payload: Mapping[str, Any], profiles: Sequence[SchemaProfile] | ProfileMatcher
) -> bool:
    """True when no non-generic profile matched (the processor records an unknown-schema sample)."""
    return _as_matcher(profiles).is_unknown_shape(payload)
