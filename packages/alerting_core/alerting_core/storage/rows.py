"""Row <-> contract model conversion shared by every writer and reader of the alerts table."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from alerting_contracts.alerts import Alert

# Column order of INSERT statements; `alert_values` returns parameters in the same order.
ALERT_COLUMNS: tuple[str, ...] = (
    "id",
    "rule_id",
    "team",
    "schema_profile_id",
    "source_id",
    "fingerprint",
    "group_key",
    "is_group_summary",
    "group_members",
    "severity",
    "title",
    "body",
    "fields",
    "color",
    "count",
    "first_seen",
    "last_seen",
    "status",
    "runbook_id",
    "last_event",
    "acknowledged_by",
    "acknowledged_at",
    "resolved_by",
    "resolved_at",
    "resolution_reason",
    "updated_at",
)
ALERT_SELECT = ", ".join(ALERT_COLUMNS)

_DATETIME_COLUMNS = ("first_seen", "last_seen", "acknowledged_at", "resolved_at", "updated_at")


def row_to_dict(record: Mapping[str, Any]) -> dict[str, Any]:
    """Turn a record into a plain dict, converting uuid columns to str (jsonb is decoded)."""
    return {key: str(value) if isinstance(value, UUID) else value for key, value in record.items()}


def alert_from_row(record: Mapping[str, Any]) -> Alert:
    """Build an Alert from an alerts row (needs the jsonb codec from `create_database_pool`)."""
    return Alert.model_validate(row_to_dict(record))


def alert_values(alert: Alert) -> list[Any]:
    """Parameters for `ALERT_COLUMNS` in order (cast the id as `$1::uuid`).

    jsonb values are plain data for the codec; timestamps stay datetime objects for asyncpg.
    """
    data = alert.model_dump(mode="json")
    for column in _DATETIME_COLUMNS:
        data[column] = getattr(alert, column)
    return [data[column] for column in ALERT_COLUMNS]
