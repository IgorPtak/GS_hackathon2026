"""Voiceover, cut into one segment per recorded file. The same text is in docs/demo.md.

`at` is where the segment starts inside its clip: seconds, or the name of a mark the recorder
logged (the segment then starts at that mark plus `after`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    key: str
    clip: str
    text: str
    at: float | str = 0.6
    after: float = 0.0


SEGMENTS: tuple[Segment, ...] = (
    Segment(
        "s0",
        "s0-problem",
        "Every system throws errors, warnings and business events. They end up in logs, "
        "dashboards and mailboxes. The right person finds out late, or gets so many alerts they "
        "stop reading. Beacon fixes that.",
        at=1.2,
    ),
    Segment(
        "s1",
        "s1-setup",
        "From a fresh clone it is three commands, and the stack is healthy in eighteen seconds. "
        "There is no password: you pick who you are. A short welcome shows the idea: an event, a "
        "rule, one alert, the right person. One click sends a test alert, and here it is, a "
        "second later.",
    ),
    Segment(
        "s2a",
        "s2a-connect",
        "Say a payments team wants alerts. Beacon has never seen their events. One payment event "
        "arrives, and it waits in Connect a system. Beacon suggests how to read it: the type, the "
        "severity, the time, and what makes two events the same. We check it against the sample, "
        "and save. No code, and nothing restarts.",
    ),
    Segment(
        "s2b",
        "s2b-runbook",
        "Next, what to do when it happens. Teams write runbooks the way they talk. We paste a few "
        "sentences, and Beacon turns them into steps: a health check, a retry, an escalation, a "
        "ticket. Anything risky is marked as needing approval. YAML and Markdown work too.",
    ),
    Segment(
        "s2c",
        "s2c-rule",
        "Now the rule, as a form, not code. When: the event type matches 'payment declined', at "
        "warning or above. Who and how: Anna's team, in the app and by email. How the alert reads, "
        "with values from the event in double braces. And which runbook it carries. Before "
        "anything goes live, Preview replays the last hour: how many alerts, how many messages, "
        "and exactly who. Under Advanced it is plain YAML, ready for Git. Save, and every worker "
        "reloads live.",
    ),
    Segment(
        "s2d",
        "s2d-first-alert",
        "The next payment event is a real alert: our title, our text, our runbook, filled in with "
        "this payment. The risky step is already waiting for a human.",
    ),
    Segment(
        "s3-1",
        "s3-phone",
        "When a settlement workflow fails, the team's runbook runs on its own. It checks the "
        "service and retries the workflow twice. The retries fail, and escalating is risky, so "
        "Beacon asks first. It calls Piotr.",
    ),
    Segment(
        "s3-2",
        "s3-phone",
        "He approves on the keypad. He could also reply to the SMS, or click Approve. Every step "
        "is recorded: what ran, who approved, and how.",
        at="keypad_done",
        after=0.3,
    ),
    Segment(
        "s4",
        "s4-people-fix",
        "Each person chooses their own channels and hours. Anna gets an SMS and a call while at "
        "work, and email after that. And if an alert is too noisy, anyone can propose a fix. The "
        "AI can draft it, but it is only a proposal: the owning team sees the diff, accepts it, "
        "and it is live, with no restart.",
    ),
    Segment(
        "s5a",
        "s5a-dedup",
        "Five hundred identical errors are one alert with a counter, not five hundred messages.",
        at=1.0,
    ),
    Segment(
        "s5b",
        "s5b-outage",
        "And when a channel goes down, here the SMS gateway, Beacon pauses it, keeps every "
        "message, and keeps the other channels working. When it comes back, the queue drains. "
        "Nothing is lost.",
    ),
    Segment(
        "s6-1",
        "s6-scale",
        "Under the hood, every worker is stateless and scales out. Alerts and their deliveries are "
        "written in one database transaction, so a crash cannot lose them.",
    ),
    Segment(
        "s6-2",
        "card-bench",
        "We measured, not estimated: eight hundred messages a second sustained, p99 around one "
        "second, and zero lost in every test, including a gateway outage and killing workers "
        "under load.",
        at=0.5,
    ),
    Segment(
        "s7",
        "s7-ai",
        "The AI only reads runbooks and drafts proposals, and never on the alert path. It cannot "
        "remove an approval, secrets are redacted before every call, and all the data here is "
        "synthetic. Beacon: teams change alerts without fear and without code, and the AI only "
        "proposes.",
    ),
)

# Order of the clips in the film, and the chapter label each one carries.
TIMELINE: tuple[tuple[str, str], ...] = (
    ("s0-problem", ""),
    ("card-setup", "Setup"),
    ("s1-setup", "Setup"),
    ("s2a-connect", "New team, no code"),
    ("s2b-runbook", "New team, no code"),
    ("s2c-rule", "New team, no code"),
    ("s2d-first-alert", "New team, no code"),
    ("s3-phone", "Runbook & phone"),
    ("s4-people-fix", "People & fixes"),
    ("s5a-dedup", "No flood, no loss"),
    ("s5b-outage", "No flood, no loss"),
    ("s6-scale", "Scale, measured"),
    ("card-bench", "Scale, measured"),
    ("s7-ai", "AI that only proposes"),
    ("card-end", ""),
)
