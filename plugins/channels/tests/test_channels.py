"""Channel registry, ui and email tests (real Redis DB 9 and Mailpit on localhost)."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from alerting_contracts.alerts import DeliveryJob, DeliveryPurpose, NotificationContent
from alerting_contracts.common import Severity
from alerting_contracts.config import ChannelConfig, ChannelType, Contacts, Recipient
from alerting_contracts.sse import NotificationEvent
from alerting_core.settings import Settings
from redis.asyncio import Redis

from plugins.channels import (
    ChannelContext,
    ChannelPlugin,
    ChannelRejectedError,
    ChannelUnavailableError,
    get_channel_plugin,
)

MAILPIT_API = "http://localhost:8025/api/v1"


def plugin(channel_type: ChannelType) -> ChannelPlugin:
    found = get_channel_plugin(channel_type)
    assert found is not None
    return found


def make_job(channel_type: ChannelType, token: str = "tok", **content: Any) -> DeliveryJob:
    fields: dict[str, Any] = {
        "title": f"Disk full {token}",
        "body": "Disk is at 99%",
        "severity": Severity.critical,
        "alert_url": "http://localhost:5173/alerts/a1",
        "runbook_steps": ["Check df", "Delete logs"],
    } | content
    return DeliveryJob(
        delivery_id=42,
        alert_id="a1",
        team="ops",
        recipient_id="alice",
        channel_id=channel_type.value,
        channel_type=channel_type,
        purpose=DeliveryPurpose.alert,
        content=NotificationContent(**fields),
    )


@pytest.fixture
async def context() -> AsyncIterator[ChannelContext]:
    redis = Redis.from_url("redis://localhost:6379/9")
    async with httpx.AsyncClient() as http:
        yield ChannelContext(redis=redis, http=http, settings=Settings())
    await redis.aclose()


def email_config(presentation: str = "full", port: int = 1025) -> ChannelConfig:
    return ChannelConfig.model_validate(
        {
            "id": "email",
            "type": "email",
            "runbook_presentation": presentation,
            "settings": {
                "smtp_host": "localhost",
                "smtp_port": port,
                "from_address": "alerts@example.com",
            },
        }
    )


ALICE = Recipient(id="alice", display_name="Alice", contacts=Contacts(email="alice@example.com"))


async def find_mail(token: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        for _ in range(20):
            found = (await client.get(f"{MAILPIT_API}/search", params={"query": token})).json()
            if found["messages_count"]:
                message_id = found["messages"][0]["ID"]
                return (await client.get(f"{MAILPIT_API}/message/{message_id}")).json()
            await asyncio.sleep(0.1)
    raise AssertionError("mail not found")


def test_registry_lookup_by_type() -> None:
    assert plugin(ChannelType.ui).channel_type == ChannelType.ui
    assert plugin(ChannelType.email).channel_type == ChannelType.email
    assert get_channel_plugin(ChannelType.webhook) is not None


async def test_ui_publishes_notification_to_team_channel(context: ChannelContext) -> None:
    pubsub = context.redis.pubsub()
    await pubsub.subscribe("alerts.team.ops")
    await pubsub.get_message(timeout=1)  # subscribe confirmation
    job = make_job(ChannelType.ui)
    config = ChannelConfig(id="ui", type=ChannelType.ui)
    await plugin(ChannelType.ui).send(job, None, config, context)
    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
    await pubsub.aclose()
    assert message is not None
    event = NotificationEvent.model_validate_json(message["data"])
    assert (event.alert_id, event.team, event.title, event.delivery_id) == (
        "a1",
        "ops",
        job.content.title,
        42,
    )
    assert event.severity == Severity.critical
    assert json.loads(message["data"])["type"] == "notification"


async def test_email_full_includes_runbook_steps(context: ChannelContext) -> None:
    token = uuid.uuid4().hex
    job = make_job(ChannelType.email, token, fields=[{"path": "host", "value": "web-1"}])
    await plugin(ChannelType.email).send(job, ALICE, email_config("full"), context)
    mail = await find_mail(token)
    assert mail["Subject"] == f"[CRITICAL] Disk full {token}"
    assert "1. Check df" in mail["Text"] and "2. Delete logs" in mail["Text"]
    assert "host: web-1" in mail["Text"] and "http://localhost:5173/alerts/a1" in mail["Text"]
    assert "Reply APPROVE" not in mail["Text"]


async def test_email_link_omits_runbook_steps_and_adds_approval_reply(
    context: ChannelContext,
) -> None:
    token = uuid.uuid4().hex
    job = make_job(ChannelType.email, token, approval_code="XY12").model_copy(
        update={"purpose": DeliveryPurpose.approval_request}
    )
    await plugin(ChannelType.email).send(job, ALICE, email_config("link"), context)
    mail = await find_mail(token)
    assert "Check df" not in mail["Text"]
    assert "http://localhost:5173/alerts/a1" in mail["Text"]
    assert "Reply APPROVE XY12 or REJECT XY12" in mail["Text"]


async def test_email_unreachable_smtp_is_unavailable(context: ChannelContext) -> None:
    with pytest.raises(ChannelUnavailableError):
        await plugin(ChannelType.email).send(
            make_job(ChannelType.email), ALICE, email_config(port=1), context
        )


async def test_email_missing_address_is_rejected(context: ChannelContext) -> None:
    nobody = Recipient(id="bob", display_name="Bob")
    with pytest.raises(ChannelRejectedError):
        await plugin(ChannelType.email).send(
            make_job(ChannelType.email), nobody, email_config(), context
        )
