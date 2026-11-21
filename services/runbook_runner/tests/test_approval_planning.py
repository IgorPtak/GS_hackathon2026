"""plan_approval_deliveries: the reply code always reaches a channel a person can answer from."""

from alerting_contracts.alerts import DeliveryPurpose
from alerting_contracts.config import ChannelConfig, ChannelType, Recipient, Rule, Team
from alerting_contracts.runbooks import ApprovalRequest
from alerting_core.ids import new_uuid7

from services.runbook_runner.approvals import plan_approval_deliveries
from services.runbook_runner.tests.fakes import NOW, make_alert

CHANNELS = {
    channel.id: channel
    for channel in (
        ChannelConfig(id="ui", type=ChannelType.ui),
        ChannelConfig(id="email", type=ChannelType.email),
        ChannelConfig(id="sms", type=ChannelType.sms),
        ChannelConfig(id="phone", type=ChannelType.phone),
    )
}
TEAMS = {"settlements": Team(id="settlements", display_name="Settlements", on_call=["piotr"])}


def recipient(**contacts: str) -> dict[str, Recipient]:
    return {
        "piotr": Recipient.model_validate(
            {"id": "piotr", "display_name": "Piotr", "teams": ["settlements"], "contacts": contacts}
        )
    }


def rule(channels: list[str]) -> Rule:
    return Rule.model_validate(
        {
            "id": "rule",
            "team": "settlements",
            "when": {"field": "a", "op": "exists", "value": True},
            "route": {"channels": channels, "recipients": ["piotr"]},
            "present": {"title": "t"},
        }
    )


def approval() -> ApprovalRequest:
    return ApprovalRequest(
        id=new_uuid7(),
        action_run_id=new_uuid7(),
        alert_id=make_alert().id,
        team="settlements",
        runbook_id="rb",
        step_index=0,
        action_id="escalate",
        params={},
        summary="Escalate to the lead",
        approval_code="4602",
        requested_at=NOW,
    )


def plan(rule_channels: list[str], **contacts: str) -> list[tuple[str, str]]:
    jobs = plan_approval_deliveries(
        make_alert(),
        approval(),
        rule=rule(rule_channels),
        teams=TEAMS,
        recipients=recipient(**contacts),
        channels=CHANNELS,
        now=NOW,
        public_base_url="http://localhost:5173",
    )
    assert all(job.purpose is DeliveryPurpose.approval_request for job in jobs)
    assert all(job.content.approval_code == "4602" for job in jobs)
    return sorted((job.channel_id, job.recipient_id or "") for job in jobs)


def test_email_only_rule_still_calls_the_approver_with_the_code() -> None:
    targets = plan(["ui", "email"], email="p@example.com", sms="+48600", phone="+48600")
    assert targets == [("email", "piotr"), ("phone", "piotr")]


def test_without_a_phone_number_the_code_goes_by_sms() -> None:
    assert plan(["email"], email="p@example.com", sms="+48600") == [
        ("email", "piotr"),
        ("sms", "piotr"),
    ]


def test_a_routed_code_channel_is_not_doubled() -> None:
    targets = plan(["sms"], sms="+48600", phone="+48600")
    assert targets == [("sms", "piotr")]


def test_no_contacts_at_all_means_no_jobs() -> None:
    assert plan(["ui"]) == []
