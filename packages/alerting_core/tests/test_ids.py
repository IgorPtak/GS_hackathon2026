import time
import uuid

from alerting_core.ids import new_uuid7


def test_uuid7_version_and_variant_bits() -> None:
    value = uuid.UUID(new_uuid7())
    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_uuid7_embeds_current_unix_milliseconds() -> None:
    before = int(time.time() * 1000)
    value = uuid.UUID(new_uuid7())
    after = int(time.time() * 1000)
    assert before <= value.int >> 80 <= after


def test_uuid7_sorts_by_time_across_milliseconds() -> None:
    first = new_uuid7()
    time.sleep(0.005)
    second = new_uuid7()
    assert first < second


def test_uuid7_is_unique() -> None:
    assert len({new_uuid7() for _ in range(1000)}) == 1000
