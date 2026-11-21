"""Circuit breaker per channel, shared by all delivery replicas (`circuit:<channel_id>` hash).

closed --5 consecutive failures--> open --10 s--> half_open (one probe) --success--> closed
                                                                       --failure--> open
While open, jobs are rescheduled for the half-open time without spending an attempt, so an
outage does not push deliveries into the DLQ.
"""

from dataclasses import dataclass

from redis.asyncio import Redis

FAILURE_THRESHOLD = 5
OPEN_SECONDS = 10.0

# Returns {allowed (0/1), retry_after_ms}. A half-open circuit lets exactly one probe through
# per OPEN_SECONDS; a probe whose worker died is replaced after that time.
_ACQUIRE = """
local state = redis.call('HGET', KEYS[1], 'state')
if not state or state == 'closed' then return {1, 0} end
local now = tonumber(ARGV[1])
local open_ms = tonumber(ARGV[2])
local opened_at = tonumber(redis.call('HGET', KEYS[1], 'opened_at') or '0')
if now - opened_at < open_ms then return {0, open_ms - (now - opened_at)} end
redis.call('HSET', KEYS[1], 'state', 'half_open', 'opened_at', now)
return {1, 0}
"""
_RECORD_FAILURE = """
local failures = redis.call('HINCRBY', KEYS[1], 'failures', 1)
local state = redis.call('HGET', KEYS[1], 'state')
if state == 'half_open' or (state ~= 'open' and failures >= tonumber(ARGV[2])) then
  redis.call('HSET', KEYS[1], 'state', 'open', 'opened_at', ARGV[1])
  return 1
end
return 0
"""

# A success closes a closed or half-open circuit; an open one stays open until its probe, so a
# slow success racing the failures that opened it cannot mask the outage.
_RECORD_SUCCESS = """
if redis.call('HGET', KEYS[1], 'state') == 'open' then return 0 end
redis.call('HSET', KEYS[1], 'state', 'closed', 'failures', 0)
return 1
"""

# Atomically checks delivery-done:<id> first (so in-flight or done duplicates never touch circuit
# state or consume a half-open probe), checks/half-opens circuit:<channel_id>, then sets pending.
_CLAIM_ATTEMPT = """
local status = redis.call('GET', KEYS[1])
if status == 'done' then return {'done', 0} end
if status then return {'in_flight', 0} end
local state = redis.call('HGET', KEYS[2], 'state')
if state and state ~= 'closed' then
  local now = tonumber(ARGV[1])
  local open_ms = tonumber(ARGV[2])
  local opened_at = tonumber(redis.call('HGET', KEYS[2], 'opened_at') or '0')
  if now - opened_at < open_ms then return {'circuit_open', open_ms - (now - opened_at)} end
  redis.call('HSET', KEYS[2], 'state', 'half_open', 'opened_at', now)
end
redis.call('SET', KEYS[1], 'pending', 'EX', ARGV[3])
return {'claimed', 0}
"""

# Marks delivery-done:<id> as done and only writes to circuit:<channel_id> when resetting from
# half_open or clearing non-zero failures, avoiding redundant HSET AOF writes on healthy sends.
_COMPLETE_ATTEMPT = """
redis.call('SET', KEYS[1], 'done', 'EX', ARGV[1])
local vals = redis.call('HMGET', KEYS[2], 'state', 'failures')
local state = vals[1]
if state == 'open' then return 0 end
local failures = tonumber(vals[2]) or 0
if state == 'half_open' or ((not state or state == 'closed') and failures > 0) then
  redis.call('HSET', KEYS[2], 'state', 'closed', 'failures', 0)
  return 1
end
return 0
"""


def circuit_key(channel_id: str) -> str:
    return f"circuit:{channel_id}"


@dataclass(frozen=True, slots=True)
class CircuitDecision:
    is_allowed: bool
    retry_after_ms: int


class CircuitBreaker:
    """Thin wrapper over the Lua scripts; all state lives in Redis."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._acquire = redis.register_script(_ACQUIRE)
        self._record_failure = redis.register_script(_RECORD_FAILURE)
        self._record_success = redis.register_script(_RECORD_SUCCESS)
        self._claim_attempt = redis.register_script(_CLAIM_ATTEMPT)
        self._complete_attempt = redis.register_script(_COMPLETE_ATTEMPT)

    async def acquire(self, channel_id: str, now_ms: int) -> CircuitDecision:
        allowed, retry_after = await self._acquire(
            keys=[circuit_key(channel_id)], args=[now_ms, int(OPEN_SECONDS * 1000)]
        )
        return CircuitDecision(bool(allowed), int(retry_after))

    async def record_success(self, channel_id: str) -> None:
        await self._record_success(keys=[circuit_key(channel_id)], args=[])

    async def record_failure(self, channel_id: str, now_ms: int) -> bool:
        """Count a failure; returns True when this failure opened the circuit."""
        opened = await self._record_failure(
            keys=[circuit_key(channel_id)], args=[now_ms, FAILURE_THRESHOLD]
        )
        return bool(opened)

    async def claim_attempt(
        self, channel_id: str, done_key: str, now_ms: int, pending_ttl_seconds: int = 60
    ) -> tuple[str, int]:
        """Atomically check idempotency, acquire circuit if allowed, and set pending."""
        status, retry_after = await self._claim_attempt(
            keys=[done_key, circuit_key(channel_id)],
            args=[now_ms, int(OPEN_SECONDS * 1000), pending_ttl_seconds],
        )
        text = status.decode() if isinstance(status, bytes) else str(status)
        return text, int(retry_after)

    async def complete_attempt(
        self, channel_id: str, done_key: str, done_ttl_seconds: int = 24 * 3600
    ) -> bool:
        """Mark `done_key` as done and reset the circuit only if recovery/failures need clearing."""
        reset = await self._complete_attempt(
            keys=[done_key, circuit_key(channel_id)], args=[done_ttl_seconds]
        )
        return bool(reset)
