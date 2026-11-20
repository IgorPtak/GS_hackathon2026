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
