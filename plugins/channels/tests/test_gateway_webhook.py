"""sms, phone and webhook channel tests (respx for HTTP, Redis DB 6, private Postgres database)."""

import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import pytest
import respx
from alerting_contracts.alerts import DeliveryJob, DeliveryPurpose, NotificationContent
from alerting_contracts.common import Severity
from alerting_contracts.config import ChannelConfig, ChannelType, Contacts, Recipient
from alerting_contracts.sse import PhoneMessageEvent
from alerting_core.connections import create_database_pool
from alerting_core.settings import Settings
from redis.asyncio import Redis

from plugins.channels import (
    ChannelContext,
    ChannelRejectedError,
    ChannelUnavailableError,
    get_channel_plugin,
)

MIGRATION = Path(__file__).parents[3] / "deploy/postgres/migrations/0001_initial.sql"
TEST_DATABASE = "alerting_channels_test"
SMS_URL = "http://gateway.test/sms"
PHONE_URL = "http://gateway.test/phone"
HOOK_URL = "http://hooks.test/slack"

ALICE = Recipient(
    id="alice",
    display_name="Alice",
    contacts=Contacts(email="alice@example.com", sms="+48100200300", phone="+48100200301"),
)
NO_CONTACTS = Recipient(id="bob", display_name="Bob")


async def ensure_test_database(settings: Settings) -> str:
    """A private database built from the migration, so other suites never see these rows."""
    admin = await asyncpg.connect(settings.database_url)
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", TEST_DATABASE)
        if not exists:
            await admin.execute(f"CREATE DATABASE {TEST_DATABASE}")
    finally:
        await admin.close()
    test_url = settings.database_url.rsplit("/", 1)[0] + f"/{TEST_DATABASE}"
    connection = await asyncpg.connect(test_url)
    try:
        await connection.execute(MIGRATION.read_text())  # idempotent
    finally:
        await connection.close()
    return test_url


@pytest.fixture
async def pool() -> AsyncIterator[asyncpg.Pool]:
    try:
        test_url = await ensure_test_database(Settings())
    except OSError:
        pytest.skip("Postgres on localhost:5432 is not running")
    database_pool = await create_database_pool(Settings(database_url=test_url))
    await database_pool.execute("TRUNCATE phone_messages")
    yield database_pool
    await database_pool.close()


@pytest.fixture
async def context(pool: asyncpg.Pool) -> AsyncIterator[ChannelContext]:
    redis = Redis.from_url("redis://localhost:6379/6")
    async with httpx.AsyncClient() as http:
        yield ChannelContext(redis=redis, http=http, settings=Settings(), database=pool)
    await redis.aclose()


def make_job(
    channel_type: ChannelType,
    purpose: DeliveryPurpose = DeliveryPurpose.alert,
    delivery_id: int = 7,
    **content: Any,
) -> DeliveryJob:
    fields: dict[str, Any] = {
        "title": 'Disk "full"',
        "severity": Severity.critical,
        "alert_url": "http://localhost:5173/alerts/a1",
        "runbook_steps": ["one", "two", "three", "four"],
    } | content
    return DeliveryJob(
        delivery_id=delivery_id,
        alert_id=str(uuid.uuid4()),
        team="ops",
        recipient_id="alice",
        channel_id=channel_type.value,
        channel_type=channel_type,
        purpose=purpose,
        content=NotificationContent(**fields),
    )


def config(channel_type: ChannelType, presentation: str = "link", **settings: Any) -> ChannelConfig:
    return ChannelConfig(
        id=channel_type.value,
        type=channel_type,
        runbook_presentation=presentation,  # type: ignore[arg-type]
        settings=settings,
    )


def plugin(channel_type: ChannelType) -> Any:
    found = get_channel_plugin(channel_type)
    assert found is not None
    return found


async def stored_rows(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch("SELECT * FROM phone_messages")


@respx.mock
async def test_sms_posts_text_stores_and_broadcasts(context: ChannelContext) -> None:
    route = respx.post(SMS_URL).respond(200, json={"message_id": "m1"})
    pubsub = context.redis.pubsub()
    await pubsub.subscribe("broadcast")
    await pubsub.get_message(timeout=1)
    job = make_job(ChannelType.sms)
    await plugin(ChannelType.sms).send(
        job, ALICE, config(ChannelType.sms, gateway_url=SMS_URL), context
    )
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "to": "+48100200300",
        "text": '[CRITICAL] Disk "full"\nhttp://localhost:5173/alerts/a1',
        "delivery_id": "7",
    }
    assert context.database is not None
    rows = await stored_rows(context.database)
    assert [(row["to"], row["channel_type"], row["delivery_id"]) for row in rows] == [
        ("+48100200300", "sms", 7)
    ]
    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
    await pubsub.aclose()
    assert message is not None
    event = PhoneMessageEvent.model_validate_json(message["data"])
    assert event.message.text == body["text"]
    assert json.loads(message["data"])["type"] == "phone.message"


@respx.mock
async def test_redelivery_does_not_duplicate_simulator_message(context: ChannelContext) -> None:
    respx.post(SMS_URL).respond(200, json={"message_id": "m1"})
    pubsub = context.redis.pubsub()
    await pubsub.subscribe("broadcast")
    await pubsub.get_message(timeout=1)
    job = make_job(ChannelType.sms)
    for _ in range(2):
        await plugin(ChannelType.sms).send(
            job, ALICE, config(ChannelType.sms, gateway_url=SMS_URL), context
        )
    assert context.database is not None
    assert len(await stored_rows(context.database)) == 1
    assert await pubsub.get_message(ignore_subscribe_messages=True, timeout=1) is not None
    assert await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.3) is None
    await pubsub.aclose()


@respx.mock
async def test_phone_prefix_full_steps_and_approval_hint(context: ChannelContext) -> None:
    route = respx.post(PHONE_URL).respond(200, json={"message_id": "m2"})
    job = make_job(ChannelType.phone, DeliveryPurpose.approval_request, approval_code="4821")
    await plugin(ChannelType.phone).send(
        job, ALICE, config(ChannelType.phone, "full", gateway_url=PHONE_URL), context
    )
    body = json.loads(route.calls.last.request.content)
    assert body["to"] == "+48100200301"
    assert body["text"].splitlines() == [
        'Call: [CRITICAL] Disk "full"',
        "http://localhost:5173/alerts/a1",
        "1. one",
        "2. two",
        "3. three",
        "Reply APPROVE 4821 or REJECT 4821",
    ]
    assert context.database is not None
    assert (await stored_rows(context.database))[0]["approval_code"] == "4821"


@respx.mock
async def test_none_presentation_omits_link(context: ChannelContext) -> None:
    route = respx.post(SMS_URL).respond(200, json={"message_id": "m1"})
    await plugin(ChannelType.sms).send(
        make_job(ChannelType.sms),
        ALICE,
        config(ChannelType.sms, "none", gateway_url=SMS_URL),
        context,
    )
    assert json.loads(route.calls.last.request.content)["text"] == '[CRITICAL] Disk "full"'


async def test_missing_contact_is_rejected(context: ChannelContext) -> None:
    job = make_job(ChannelType.sms)
    with pytest.raises(ChannelRejectedError):
        await plugin(ChannelType.sms).send(job, NO_CONTACTS, config(ChannelType.sms), context)
    with pytest.raises(ChannelRejectedError):
        await plugin(ChannelType.sms).send(job, None, config(ChannelType.sms), context)


@respx.mock
@pytest.mark.parametrize(
    ("status", "error"), [(503, ChannelUnavailableError), (400, ChannelRejectedError)]
)
async def test_gateway_status_mapping_stores_nothing(
    context: ChannelContext, status: int, error: type[Exception]
) -> None:
    respx.post(SMS_URL).respond(status)
    with pytest.raises(error):
        await plugin(ChannelType.sms).send(
            make_job(ChannelType.sms), ALICE, config(ChannelType.sms, gateway_url=SMS_URL), context
        )
    assert context.database is not None
    assert await stored_rows(context.database) == []


@respx.mock
async def test_gateway_timeout_is_unavailable(context: ChannelContext) -> None:
    respx.post(SMS_URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    with pytest.raises(ChannelUnavailableError):
        await plugin(ChannelType.sms).send(
            make_job(ChannelType.sms), ALICE, config(ChannelType.sms, gateway_url=SMS_URL), context
        )


@respx.mock
async def test_sms_without_database_still_publishes(context: ChannelContext) -> None:
    respx.post(SMS_URL).respond(200, json={"message_id": "m1"})
    no_database = ChannelContext(
        redis=context.redis, http=context.http, settings=context.settings, database=None
    )
    pubsub = context.redis.pubsub()
    await pubsub.subscribe("broadcast")
    await pubsub.get_message(timeout=1)
    await plugin(ChannelType.sms).send(
        make_job(ChannelType.sms), ALICE, config(ChannelType.sms, gateway_url=SMS_URL), no_database
    )
    assert await pubsub.get_message(ignore_subscribe_messages=True, timeout=2) is not None
    await pubsub.aclose()


async def test_sms_against_real_mock_gateway(context: ChannelContext) -> None:
    try:
        await context.http.get("http://localhost:8090/healthz", timeout=1)
    except httpx.HTTPError:
        pytest.skip("mock gateway on localhost:8090 is not running")
    job = make_job(ChannelType.sms)
    await plugin(ChannelType.sms).send(
        job, ALICE, config(ChannelType.sms, gateway_url="http://localhost:8090/sms"), context
    )
    assert context.database is not None
    assert len(await stored_rows(context.database)) == 1


DETAIL_TEMPLATE = (
    '{"d": "{{job.delivery_id}}", "r": "{{recipient.display_name}}", "t": "{{alert.team}}"}'
)
SLACK_TEMPLATE = '{"text": "[{{alert.severity}}] {{alert.title}} {{alert.alert_url}}"}'


@respx.mock
async def test_webhook_renders_template_as_json(context: ChannelContext) -> None:
    route = respx.post(HOOK_URL).respond(200, json={"received": True})
    hook = config(
        ChannelType.webhook,
        url=HOOK_URL,
        headers={"X-Token": "t"},
        body_template=SLACK_TEMPLATE,
    )
    await plugin(ChannelType.webhook).send(make_job(ChannelType.webhook), None, hook, context)
    request = route.calls.last.request
    assert json.loads(request.content) == {
        "text": '[critical] Disk "full" http://localhost:5173/alerts/a1'
    }
    assert request.headers["X-Token"] == "t"
    assert request.headers["Content-Type"] == "application/json"


@respx.mock
async def test_webhook_context_has_job_and_recipient(context: ChannelContext) -> None:
    route = respx.put(HOOK_URL).respond(200)
    hook = config(
        ChannelType.webhook,
        url=HOOK_URL,
        method="PUT",
        body_template=DETAIL_TEMPLATE,
    )
    await plugin(ChannelType.webhook).send(make_job(ChannelType.webhook), ALICE, hook, context)
    assert json.loads(route.calls.last.request.content) == {"d": "7", "r": "Alice", "t": "ops"}


@respx.mock
async def test_webhook_invalid_json_is_rejected_and_not_sent(context: ChannelContext) -> None:
    route = respx.post(HOOK_URL).respond(200)
    hook = config(ChannelType.webhook, url=HOOK_URL, body_template='{"text": {{alert.title}}')
    with pytest.raises(ChannelRejectedError):
        await plugin(ChannelType.webhook).send(make_job(ChannelType.webhook), None, hook, context)
    assert not route.called


@respx.mock
@pytest.mark.parametrize(
    ("status", "error"), [(500, ChannelUnavailableError), (404, ChannelRejectedError)]
)
async def test_webhook_status_mapping(
    context: ChannelContext, status: int, error: type[Exception]
) -> None:
    respx.post(HOOK_URL).respond(status)
    hook = config(ChannelType.webhook, url=HOOK_URL, body_template=SLACK_TEMPLATE)
    with pytest.raises(error):
        await plugin(ChannelType.webhook).send(make_job(ChannelType.webhook), None, hook, context)


@respx.mock
async def test_webhook_timeout_is_unavailable(context: ChannelContext) -> None:
    respx.post(HOOK_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    hook = config(ChannelType.webhook, url=HOOK_URL, body_template=SLACK_TEMPLATE)
    with pytest.raises(ChannelUnavailableError):
        await plugin(ChannelType.webhook).send(make_job(ChannelType.webhook), None, hook, context)
