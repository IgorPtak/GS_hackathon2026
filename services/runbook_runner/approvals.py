"""Delivery of approval requests: one `approval_request` DeliveryJob per on-call recipient."""

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

import asyncpg
from alerting_contracts.alerts import Alert, DeliveryJob, DeliveryPurpose, NotificationContent
from alerting_contracts.config import ChannelConfig, ChannelType, Recipient, Rule, Team
from alerting_contracts.runbooks import ApprovalRequest
from alerting_core.logging import get_logger
from alerting_core.outbox import enqueue_delivery
from alerting_core.routing import resolve_deliveries

log = get_logger(__name__)

# Approvals are answered by text, so these carry the reply: tried when routing yields nothing.
# A code is only useful where a person can answer with it: a call reads it out, a text shows it.
# The call comes first so the on-call person hears the code (demo scene, docs/demo.md).
_FALLBACK_TYPES = (ChannelType.phone, ChannelType.sms)
_CODE_TYPES = frozenset({ChannelType.phone, ChannelType.sms})


class Clock(Protocol):
    def __call__(self) -> datetime: ...


class ApprovalNotifier(Protocol):
    """Enqueues the deliveries asking on-call people to decide an approval request."""

    async def notify(self, alert: Alert, approval: ApprovalRequest) -> int:
        """Returns how many delivery jobs were enqueued."""
        ...


def _fallback_channel(
    recipient: Recipient, channels: Mapping[str, ChannelConfig]
) -> ChannelConfig | None:
    for channel_type in _FALLBACK_TYPES:
        if not getattr(recipient.contacts, channel_type.value):
            continue
        for channel_id in sorted(channels):
            channel = channels[channel_id]
            if channel.type is channel_type and channel.enabled:
                return channel
    return None


def plan_approval_deliveries(
    alert: Alert,
    approval: ApprovalRequest,
    *,
    rule: Rule | None,
    teams: Mapping[str, Team],
    recipients: Mapping[str, Recipient],
    channels: Mapping[str, ChannelConfig],
    now: datetime,
    public_base_url: str,
) -> list[DeliveryJob]:
    """Pure: the delivery jobs for one approval request.

    Channels per recipient are the ones routing picks for the alert (preferences, working
    hours, missing contacts). When none of them can carry a reply code (phone or sms), the
    recipient's phone, else sms, channel is added, so the code always reaches a person.
    The shared `ui` channel is not used: the approval code goes to a person.
    """
    team = teams.get(alert.team)
    if team is None:
        log.warning("approval_unknown_team", extra={"alert_id": alert.id, "team": alert.team})
        return []
    routed: dict[str, list[tuple[str, ChannelType]]] = {}
    if rule is not None:
        for target in resolve_deliveries(
            rule, alert, teams=teams, recipients=recipients, channels=channels, now=now
        ):
            if target.recipient_id is not None:
                routed.setdefault(target.recipient_id, []).append(
                    (target.channel_id, target.channel_type)
                )
    content = NotificationContent(
        title=f"Approval needed: {approval.summary}",
        body=(
            f"{alert.title}\n{approval.summary}\n"
            f"Reply APPROVE {approval.approval_code} or REJECT {approval.approval_code}"
        ),
        severity=alert.severity,
        fields=alert.fields,
        alert_url=f"{public_base_url.rstrip('/')}/alerts/{alert.id}",
        approval_code=approval.approval_code,
    )
    jobs: list[DeliveryJob] = []
    for recipient_id in team.on_call:
        recipient = recipients.get(recipient_id)
        if recipient is None:
            log.warning("approval_unknown_recipient", extra={"recipient_id": recipient_id})
            continue
        targets = list(routed.get(recipient_id, []))
        if not any(channel_type in _CODE_TYPES for _, channel_type in targets):
            fallback = _fallback_channel(recipient, channels)
            if fallback is not None:
                targets.append((fallback.id, fallback.type))
        if not targets:
            log.warning(
                "approval_no_channel",
                extra={"alert_id": alert.id, "recipient_id": recipient_id},
            )
            continue
        for channel_id, channel_type in targets:
            jobs.append(
                DeliveryJob(
                    delivery_id=0,  # stamped with the outbox id by the relay
                    alert_id=alert.id,
                    team=alert.team,
                    recipient_id=recipient_id,
                    channel_id=channel_id,
                    channel_type=channel_type,
                    purpose=DeliveryPurpose.approval_request,
                    content=content,
                    approval_request_id=approval.id,
                )
            )
    return jobs


class OutboxApprovalNotifier:
    """Plans the jobs from the config snapshot and writes them to the outbox in the job's tx."""

    def __init__(
        self,
        connection: asyncpg.Connection,
        *,
        rules: Mapping[str, Rule],
        teams: Mapping[str, Team],
        recipients: Mapping[str, Recipient],
        channels: Mapping[str, ChannelConfig],
        public_base_url: str,
        clock: Clock,
    ) -> None:
        self._connection = connection
        self._rules = rules
        self._teams = teams
        self._recipients = recipients
        self._channels = channels
        self._public_base_url = public_base_url
        self._clock = clock

    async def notify(self, alert: Alert, approval: ApprovalRequest) -> int:
        jobs = plan_approval_deliveries(
            alert,
            approval,
            rule=self._rules.get(alert.rule_id),
            teams=self._teams,
            recipients=self._recipients,
            channels=self._channels,
            now=self._clock(),
            public_base_url=self._public_base_url,
        )
        for job in jobs:
            await enqueue_delivery(self._connection, job)
        return len(jobs)
