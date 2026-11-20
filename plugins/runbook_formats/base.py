"""Runbook format plugin contract.

A format plugin turns the original text of a runbook into the one normalized model,
``list[RunbookStep]``. Contract:
- ``normalize`` is pure: no network, no file access.
- It raises ``pydantic.ValidationError`` (with a field path) for structurally invalid input and
  ``ValueError`` when the source yields no steps.
- ``actions`` are the action configs available (id -> config); plugins may only reference those.
- ``approval`` stays None unless the source states it, so the step inherits the action default.
- ``{{placeholders}}`` in text are kept untouched; they are rendered later per alert.
"""

from __future__ import annotations

import abc
from collections.abc import Mapping

from alerting_contracts.config import ActionConfig
from alerting_contracts.runbooks import RunbookFormat, RunbookStep


class RunbookFormatPlugin(abc.ABC):
    format: RunbookFormat

    @abc.abstractmethod
    def normalize(self, source: str, actions: Mapping[str, ActionConfig]) -> list[RunbookStep]:
        """Return the normalized steps for ``source``."""
