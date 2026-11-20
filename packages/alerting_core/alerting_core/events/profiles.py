"""Pick the schema profile of a raw event."""

from collections.abc import Mapping, Sequence
from typing import Any

from alerting_contracts.config import SchemaProfile

from ._matcher import _matches

GENERIC_PROFILE_ID = "generic"


def _fallback_profile() -> SchemaProfile:
    """Used only when the configured profiles contain no `generic` one."""
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
    """Profiles ordered once (priority desc, config order for ties); build one per config reload."""

    def __init__(self, profiles: Sequence[SchemaProfile]) -> None:
        self._ordered = sorted(profiles, key=lambda p: -p.priority)
        self._specific = [p for p in self._ordered if p.id != GENERIC_PROFILE_ID]
        generic = next((p for p in self._ordered if p.id == GENERIC_PROFILE_ID), None)
        self._generic = generic or _fallback_profile()

    def select(self, payload: Mapping[str, Any]) -> SchemaProfile:
        """Highest-priority matching profile, else the generic one (never None)."""
        for profile in self._ordered:
            if _matches(profile.match, payload):
                return profile
        return self._generic

    def is_unknown_shape(self, payload: Mapping[str, Any]) -> bool:
        """True when no non-generic profile matches (unknown-schema inbox candidate)."""
        return not any(_matches(p.match, payload) for p in self._specific)


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
