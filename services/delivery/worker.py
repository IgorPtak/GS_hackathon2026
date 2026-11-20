"""One attempt per `deliveries` entry: idempotency, circuit, send, then record the outcome.

Idempotency (`delivery-done:<id>`): set to `pending` with a short TTL before sending and to
`done` for 7 days after a successful send. A job finding `done` is a duplicate and is acked;
one finding `pending` is in flight elsewhere and stays pending in the stream (retried after
the claim idle time), so a worker that dies mid-send never blocks the delivery for good.
Every handled outcome acks the entry: retries travel through `delivery-retries`, not the PEL.
"""

import asyncio
import time
from datetime import UTC, datetime

import asyncpg
from alerting_contracts.alerts import AuditVerb, DeliveryJob, DeliveryStatus
from alerting_contracts.config import ChannelConfig, Recipient
from alerting_contracts.sse import AuditAppendedEvent, DeliveryUpdatedEvent
from alerting_core.config.registry import ConfigRegistry
from alerting_core.durations import parse_duration_ms
from alerting_core.logging import get_logger
from alerting_core.metrics import DEAD_LETTERED, DELIVERIES, DELIVERY_RETRIES
from alerting_core.publishing import publish_team_event
from alerting_core.streams import StreamMessage
from pydantic import ValidationError
from redis.asyncio import Redis

from plugins.channels.base import ChannelContext, ChannelRejectedError
from plugins.channels.registry import get_channel_plugin

from .circuit import CircuitBreaker
from .dead_letters import dead_letter_job
from .metrics import DELIVERY_ATTEMPTS, E2E_LATENCY_SECONDS, SEND_SECONDS
from .records import Outcome, RecordedOutcome, delivery_age_seconds, record_outcome
from .retries import backoff_ms, schedule_retry

log = get_logger(__name__)

DONE_TTL_SECONDS = 7 * 24 * 3600
# Longer than the slowest send (SEND_TIMEOUT) so a live attempt is never duplicated.
PENDING_TTL_SECONDS = 60
SEND_TIMEOUT_SECONDS = 15.0
MAX_CONCURRENT_SENDS = 50
# A channel down longer than this dead-letters its jobs so the fallback channel takes over.
MAX_CIRCUIT_WAIT_SECONDS = 600.0


def done_key(delivery_id: int) -> str:
    return f"delivery-done:{delivery_id}"


class InFlightError(Exception):
    """Another worker is sending this delivery right now; leave the entry pending."""


class DeliveryWorker:
    """Batch handler for `StreamConsumer` on `deliveries`."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        redis: Redis,
        registry: ConfigRegistry,
        context: ChannelContext,
    ) -> None:
        self._pool = pool
        self._redis = redis
        self._registry = registry
        self._context = context
        self._circuit = CircuitBreaker(redis)
        self._limit = asyncio.Semaphore(MAX_CONCURRENT_SENDS)

    async def handle_batch(self, messages: list[StreamMessage]) -> dict[str, str]:
        """Attempt every job concurrently; returns entries to leave pending."""
        results = await asyncio.gather(*(self._handle_one(m) for m in messages))
        return {m.id: error for m, error in zip(messages, results, strict=True) if error}

    async def _handle_one(self, message: StreamMessage) -> str | None:
        try:
            job = DeliveryJob.model_validate_json(message.fields[b"job"])
        except (KeyError, ValidationError, ValueError) as error:
            await dead_letter_job(self._redis, message.fields.get(b"job", b""), str(error), 0)
            return None
        async with self._limit:
            try:
                await self.attempt(job)
            except InFlightError:
                return "in_flight"
            except Exception as error:
                # Postgres or Redis down while recording: keep the entry for XAUTOCLAIM.
                log.exception(
                    "delivery_attempt_failed",
                    extra={"alert_id": job.alert_id, "delivery_id": job.delivery_id},
                )
                return f"{type(error).__name__}: {error}"
        return None

    async def attempt(self, job: DeliveryJob) -> None:
        """Run one attempt of `job` and record what happened."""
        channel = self._registry.snapshot.of_kind("channel").get(job.channel_id)
        if channel is None or not channel.enabled:
            await self._give_up(job, channel, f"channel {job.channel_id} unavailable", job.attempt)
            return
        key = done_key(job.delivery_id)
        if await self._redis.get(key) == b"done":
            # Sent before; record it in case that worker died before writing the row (no-op
            # when the row already says delivered, so true duplicates stay quiet).
            DELIVERY_ATTEMPTS.labels(job.channel_type.value, "duplicate").inc()
            await self._delivered(job, observe_latency=False)
            return
        now_ms = int(time.time() * 1000)
        decision = await self._circuit.acquire(channel.id, now_ms)
        if not decision.is_allowed:
            await self._wait_for_circuit(job, channel, now_ms + max(decision.retry_after_ms, 500))
            return
        if not await self._redis.set(key, "pending", nx=True, ex=PENDING_TTL_SECONDS):
            raise InFlightError(job.delivery_id)
        recipient = self._recipient(job)
        try:
            await self._send(job, recipient, channel)
        except ChannelRejectedError as error:
            await self._redis.delete(key)
            await self._circuit.record_success(channel.id)  # the channel answered
            await self._give_up(job, channel, f"rejected: {error}", job.attempt + 1)
            return
        except Exception as error:  # unavailable, timeout or a plugin bug: retry with backoff
            await self._redis.delete(key)
            await self._circuit.record_failure(channel.id, int(time.time() * 1000))
            await self._retry_or_give_up(job, channel, f"{type(error).__name__}: {error}")
            return
        await self._redis.set(key, "done", ex=DONE_TTL_SECONDS)
        await self._circuit.record_success(channel.id)
        await self._delivered(job)

    async def _wait_for_circuit(
        self, job: DeliveryJob, channel: ChannelConfig, due_ms: int
    ) -> None:
        """Park the job until half-open without spending an attempt, but not forever: after
        MAX_CIRCUIT_WAIT_SECONDS the job gives up so its fallback channel still gets the alert."""
        if await delivery_age_seconds(self._pool, job.delivery_id) > MAX_CIRCUIT_WAIT_SECONDS:
            await self._give_up(job, channel, "circuit open too long", job.attempt)
            return
        await schedule_retry(self._redis, job, due_ms)
        DELIVERY_ATTEMPTS.labels(job.channel_type.value, "circuit_open").inc()

    def _recipient(self, job: DeliveryJob) -> Recipient | None:
        if job.recipient_id is None:
            return None
        recipient: Recipient | None = self._registry.snapshot.of_kind("recipient").get(
            job.recipient_id
        )
        return recipient

    async def _send(
        self, job: DeliveryJob, recipient: Recipient | None, channel: ChannelConfig
    ) -> None:
        plugin = get_channel_plugin(channel.type)
        if plugin is None:
            raise ChannelRejectedError(f"no plugin for channel type {channel.type}")
        started = time.perf_counter()
        try:
            await asyncio.wait_for(
                plugin.send(job, recipient, channel, self._context), SEND_TIMEOUT_SECONDS
            )
        finally:
            SEND_SECONDS.labels(channel.type.value).observe(time.perf_counter() - started)

    async def _delivered(self, job: DeliveryJob, *, observe_latency: bool = True) -> None:
        now = datetime.now(UTC)
        outcome = Outcome(
            DeliveryStatus.delivered, AuditVerb.delivery_delivered, job.attempt + 1, None, now
        )
        recorded = await record_outcome(self._pool, job, outcome)
        if recorded.delivery is None:
            return  # already recorded as delivered
        DELIVERY_ATTEMPTS.labels(job.channel_type.value, "delivered").inc()
        DELIVERIES.labels(job.channel_type.value, "delivered").inc()
        if observe_latency and job.event_sent_at is not None and not job.is_fallback:
            latency = (now - job.event_sent_at).total_seconds()
            E2E_LATENCY_SECONDS.labels(job.channel_type.value).observe(max(latency, 0.0))
        await self._publish(job, recorded)

    async def _retry_or_give_up(self, job: DeliveryJob, channel: ChannelConfig, error: str) -> None:
        attempt = job.attempt + 1
        if attempt >= channel.retry.max_attempts:
            await self._give_up(job, channel, error, attempt)
            return
        delay = backoff_ms(
            attempt,
            parse_duration_ms(channel.retry.initial_backoff),
            parse_duration_ms(channel.retry.max_backoff),
        )
        due_ms = int(time.time() * 1000) + delay
        not_before = datetime.fromtimestamp(due_ms / 1000, UTC)
        # Record first: if the zadd then fails the entry stays pending and is retried as is.
        outcome = Outcome(DeliveryStatus.failed, AuditVerb.delivery_failed, attempt, error)
        recorded = await record_outcome(self._pool, job, outcome)
        await schedule_retry(
            self._redis,
            job.model_copy(update={"attempt": attempt, "not_before": not_before}),
            due_ms,
        )
        DELIVERY_ATTEMPTS.labels(job.channel_type.value, "retry").inc()
        DELIVERIES.labels(job.channel_type.value, "failed").inc()
        DELIVERY_RETRIES.inc()
        log.warning(
            "delivery_retry_scheduled",
            extra={"alert_id": job.alert_id, "delivery_id": job.delivery_id, "attempt": attempt},
        )
        await self._publish(job, recorded)

    async def _give_up(
        self, job: DeliveryJob, channel: ChannelConfig | None, error: str, attempt: int
    ) -> None:
        """Dead-letter the job and, once per chain, queue it on the fallback channel."""
        fallback = self._fallback_for(job, channel)
        outcome = Outcome(
            DeliveryStatus.dead_lettered, AuditVerb.delivery_dead_lettered, attempt, error
        )
        recorded = await record_outcome(self._pool, job, outcome, fallback)
        await dead_letter_job(self._redis, job.model_dump_json().encode(), error, attempt)
        DELIVERY_ATTEMPTS.labels(job.channel_type.value, "dead_lettered").inc()
        DELIVERIES.labels(job.channel_type.value, "dead_lettered").inc()
        DEAD_LETTERED.inc()
        log.error(
            "delivery_dead_lettered",
            extra={"alert_id": job.alert_id, "delivery_id": job.delivery_id, "error": error},
        )
        await self._publish(job, recorded)

    def _fallback_for(
        self, job: DeliveryJob, channel: ChannelConfig | None
    ) -> ChannelConfig | None:
        # A fallback never falls back again, so a broken chain cannot loop.
        if job.is_fallback or channel is None or channel.fallback_channel_id is None:
            return None
        fallback: ChannelConfig | None = self._registry.snapshot.of_kind("channel").get(
            channel.fallback_channel_id
        )
        return fallback if fallback is not None and fallback.enabled else None

    async def _publish(self, job: DeliveryJob, recorded: RecordedOutcome) -> None:
        now = datetime.now(UTC)
        if recorded.delivery is not None:
            event = DeliveryUpdatedEvent(at=now, delivery=recorded.delivery)
            await publish_team_event(self._redis, job.team, event)
        for entry in recorded.audit:
            await publish_team_event(self._redis, job.team, AuditAppendedEvent(at=now, entry=entry))
