"""Structured JSON logs: one object per line with `event`, `service`, `alert_id`, `rule_id`.

Usage: `log = get_logger(__name__)`, then
`log.info("alert_created", extra={"alert_id": alert.id, "rule_id": rule.id})`.
The message is the event name; everything else goes in `extra`.
"""

import logging
import sys
from datetime import UTC, datetime
from typing import Any

import orjson

# Attributes every LogRecord has; anything else on the record came from `extra`.
_RESERVED_ATTRIBUTES = frozenset(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """One JSON line per record; `alert_id` and `rule_id` are always present (maybe null)."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "at": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "service": self._service_name,
            "logger": record.name,
            "event": record.getMessage(),
            "alert_id": None,
            "rule_id": None,
        }
        for key, value in vars(record).items():
            if key not in _RESERVED_ATTRIBUTES:
                entry[key] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return orjson.dumps(entry, default=str).decode()


def configure_logging(service_name: str, level: str = "INFO") -> None:
    """Replace root handlers with one JSON handler on stdout; call once at service start."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service_name))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # uvicorn installs its own handlers; route its logs through ours instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        # `--no-access-log` leaves uvicorn.access with no handlers and propagate off; keep it so.
        is_switched_off = not uvicorn_logger.handlers and not uvicorn_logger.propagate
        uvicorn_logger.handlers[:] = []
        uvicorn_logger.propagate = not (name == "uvicorn.access" and is_switched_off)


def get_logger(name: str) -> logging.Logger:
    """Module logger; formatting is decided once by configure_logging."""
    return logging.getLogger(name)
