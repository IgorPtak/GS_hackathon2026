import base64

import orjson
import pytest
from alerting_core.storage.alerts_read import InvalidCursorError, decode_cursor


def test_decode_cursor_rejects_naive_datetime() -> None:
    cursor = base64.urlsafe_b64encode(orjson.dumps(["2026-01-01T00:00:00", "x"])).decode()
    with pytest.raises(InvalidCursorError):
        decode_cursor(cursor)
