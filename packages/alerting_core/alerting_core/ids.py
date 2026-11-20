"""Identifier helpers."""

import os
import time
import uuid


def new_uuid7() -> str:
    """Return an RFC 9562 UUID v7 string: 48-bit unix ms, version 7, variant 10, random rest.

    Python 3.12 has no uuid7. Time-ordered ids keep the alerts primary key index append-mostly.
    Ordering inside the same millisecond is not guaranteed.
    """
    unix_ms = time.time_ns() // 1_000_000
    value = (unix_ms & ((1 << 48) - 1)) << 80
    value |= int.from_bytes(os.urandom(10), "big")
    value &= ~(0xF << 76)
    value |= 0x7 << 76  # version
    value &= ~(0x3 << 62)
    value |= 0x2 << 62  # variant 10
    return str(uuid.UUID(int=value))
