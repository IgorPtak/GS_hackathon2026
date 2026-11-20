"""Markdown runbooks: list items become steps, headings become text steps."""

from __future__ import annotations

import re
from collections.abc import Mapping

from alerting_contracts.config import ActionConfig
from alerting_contracts.runbooks import RunbookFormat, RunbookStep, StepKind

from plugins.runbook_formats.base import RunbookFormatPlugin
from plugins.runbook_formats.registry import register_runbook_format

# Keyword table: the ONE place mapping phrases to actions. First match wins, so order matters.
# (regex, action id, step kind, param that receives the step text or None). A row applies only
# when its action id exists in the given actions. Bare "check" is deliberately not a keyword:
# "check the dashboard" is manual, while the health check needs a URL.
KEYWORD_ACTIONS: tuple[tuple[re.Pattern[str], str, StepKind, str | None], ...] = (
    (
        re.compile(r"\bhealth\b|\bcheck (?:the )?(?:service|endpoint|status)\b", re.I),
        "http-health-check",
        StepKind.check,
        None,
    ),
    (re.compile(r"\bretry\b|\bre-run\b|\brerun\b", re.I), "retry-workflow", StepKind.action, None),
    (re.compile(r"\bescalate\b", re.I), "escalate", StepKind.action, None),
    (re.compile(r"\bticket\b", re.I), "open-ticket", StepKind.action, "summary"),
    (re.compile(r"\brestart\b", re.I), "restart-pricing-adapter", StepKind.action, None),
)

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-*+])\s+(.*\S)\s*$")


def _classify(text: str, actions: Mapping[str, ActionConfig]) -> dict[str, object]:
    for pattern, action_id, kind, text_param in KEYWORD_ACTIONS:
        if action_id in actions and pattern.search(text):
            params = {text_param: text} if text_param else {}
            return {"kind": kind, "action": action_id, "params": params}
    return {"kind": StepKind.text}


def heading_text(source: str) -> str | None:
    """The first markdown heading, if any."""
    for line in source.splitlines():
        match = _HEADING.match(line)
        if match and match.group(1):
            return match.group(1)
    return None


@register_runbook_format
class MarkdownRunbookFormat(RunbookFormatPlugin):
    format = RunbookFormat.markdown

    def normalize(self, source: str, actions: Mapping[str, ActionConfig]) -> list[RunbookStep]:
        # (is_heading, text); nested items are flattened into steps in reading order.
        entries: list[tuple[bool, str]] = []
        in_item = False
        for line in source.splitlines():
            if not line.strip():
                in_item = False
            elif match := _HEADING.match(line):
                in_item = False
                if match.group(1):
                    entries.append((True, match.group(1)))
            elif match := _ITEM.match(line):
                in_item = True
                entries.append((False, match.group(1)))
            elif in_item and line[:1] in " \t":
                # Indented continuation of the previous item.
                is_heading, text = entries[-1]
                entries[-1] = (is_heading, f"{text} {line.strip()}")
            else:
                in_item = False
        if not entries:
            raise ValueError("markdown runbook has no list items or headings to turn into steps")
        steps: list[RunbookStep] = []
        for index, (is_heading, text) in enumerate(entries):
            fields = {"kind": StepKind.text} if is_heading else _classify(text, actions)
            steps.append(RunbookStep(index=index, text=text, **fields))  # type: ignore[arg-type]
        return steps
