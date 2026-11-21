"""Markdown runbooks: list items become steps, headings become text steps."""

from __future__ import annotations

import re
from collections.abc import Mapping

from alerting_contracts.config import ActionConfig, ApprovalPolicy
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


_INLINE_ACTION = re.compile(r"\s*(?:[-–—:]\s*)?`([^`]+)`\s*[.;]?\s*$")
_PAIR = re.compile(r'([A-Za-z_][\w.-]*)=("[^"]*"|\S+)')
_NEEDS_APPROVAL = re.compile(r"\bneeds?\s+(?:human\s+)?approval\b", re.I)
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _parse_inline_action(
    text: str, actions: Mapping[str, ActionConfig]
) -> tuple[str, str, dict[str, str], ApprovalPolicy | None] | None:
    """Split a trailing `action key=value` code span off ``text``.

    Returns (text without the span, action id, params, explicit approval) or None when the item
    has no such span or the span does not start with a known action id.
    """
    match = _INLINE_ACTION.search(text)
    if not match:
        return None
    head, _, rest = match.group(1).strip().partition(" ")
    action_id = head.replace("_", "-")
    if action_id not in actions:
        return None
    declared = actions[action_id].params
    params: dict[str, str] = {}
    approval: ApprovalPolicy | None = None
    for key, raw in _PAIR.findall(rest):
        value = raw[1:-1] if raw.startswith('"') else raw
        if key == "approval":
            approval = ApprovalPolicy(value) if value in list(ApprovalPolicy) else None
            continue
        snake = _CAMEL_BOUNDARY.sub("_", key).lower().replace("-", "_")
        params[snake if snake in declared else key] = value
    return text[: match.start()].strip() or text, action_id, params, approval


def _classify(text: str, actions: Mapping[str, ActionConfig]) -> dict[str, object]:
    fields: dict[str, object] = {}
    action_id: str | None = None
    params: dict[str, str] = {}
    approval: ApprovalPolicy | None = None
    kind = StepKind.action
    if inline := _parse_inline_action(text, actions):
        fields["text"], action_id, params, approval = inline
        kind = next((k for _, a, k, _ in KEYWORD_ACTIONS if a == action_id), StepKind.action)
    else:
        for pattern, keyword_action, keyword_kind, text_param in KEYWORD_ACTIONS:
            if keyword_action in actions and pattern.search(text):
                action_id, kind = keyword_action, keyword_kind
                params = {text_param: text} if text_param else {}
                break
    if _NEEDS_APPROVAL.search(text):
        approval = ApprovalPolicy.required
    if approval is not None:
        fields["approval"] = approval
    if action_id is None:
        return {**fields, "kind": StepKind.text}
    specs = actions[action_id].params
    if any(spec.is_required and name not in params for name, spec in specs.items()):
        # A step that would fail at run time for lack of params is a manual instruction instead.
        return {**fields, "kind": StepKind.text}
    return {**fields, "kind": kind, "action": action_id, "params": params}


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
            steps.append(RunbookStep(index=index, **{"text": text, **fields}))  # type: ignore[arg-type]
        return steps
