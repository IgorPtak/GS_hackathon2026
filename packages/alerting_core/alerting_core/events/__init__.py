"""Schema profiles: select a profile for a raw event, then normalize, fingerprint, shape hash."""

from .fingerprint import compute_fingerprint
from .normalize import normalize_event
from .profiles import ProfileMatcher, is_unknown_shape, select_schema_profile
from .shape import key_paths, shape_hash

__all__ = [
    "ProfileMatcher",
    "compute_fingerprint",
    "is_unknown_shape",
    "key_paths",
    "normalize_event",
    "select_schema_profile",
    "shape_hash",
]
