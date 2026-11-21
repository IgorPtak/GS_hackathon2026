"""Atomic Lua circuit-breaker tests against real Redis."""

import time

from redis.asyncio import Redis

from services.delivery.circuit import CircuitBreaker, circuit_key
from services.delivery.worker import done_key


async def test_claim_attempt_done_and_in_flight_do_not_touch_circuit(redis: Redis) -> None:
    breaker = CircuitBreaker(redis)
    now_ms = int(time.time() * 1000)
    opened_at = now_ms - 11_000
    await redis.hset(circuit_key("email"), mapping={"state": "open", "opened_at": opened_at})
    await redis.set(done_key(1), "done")
    await redis.set(done_key(2), "pending")

    assert await breaker.claim_attempt("email", done_key(1), now_ms, 60) == ("done", 0)
    assert await breaker.claim_attempt("email", done_key(2), now_ms, 60) == ("in_flight", 0)
    assert await redis.hget(circuit_key("email"), "state") == b"open"
    assert await redis.hget(circuit_key("email"), "opened_at") == str(opened_at).encode()

    assert await breaker.claim_attempt("email", done_key(3), now_ms, 60) == ("claimed", 0)
    assert await redis.get(done_key(3)) == b"pending"
    assert await redis.hget(circuit_key("email"), "state") == b"half_open"

    status, retry_after = await breaker.claim_attempt("email", done_key(4), now_ms + 100, 60)
    assert status == "circuit_open" and retry_after > 0
    assert await redis.exists(done_key(4)) == 0


async def test_complete_attempt_noops_on_healthy_circuit_hash(redis: Redis) -> None:
    breaker = CircuitBreaker(redis)
    assert await breaker.complete_attempt("email", done_key(1), 604800) is False
    assert await redis.get(done_key(1)) == b"done"
    assert await redis.ttl(done_key(1)) > 600_000
    assert await redis.exists(circuit_key("email")) == 0

    await redis.hset(circuit_key("email"), mapping={"state": "closed", "failures": 0})
    async with redis.pipeline(transaction=True) as pipe:
        await pipe.watch(circuit_key("email"))
        pipe.multi()
        pipe.set("watch-probe", "1")
        assert await breaker.complete_attempt("email", done_key(2), 604800) is False
        assert await pipe.execute() == [True]  # no WatchError => zero HSET write on circuit hash


async def test_complete_attempt_resets_half_open_and_failures_but_not_open(redis: Redis) -> None:
    breaker = CircuitBreaker(redis)
    await breaker.record_failure("email", int(time.time() * 1000))  # failures=1, no state field
    assert await breaker.complete_attempt("email", done_key(1), 604800) is True
    assert await redis.hgetall(circuit_key("email")) == {b"state": b"closed", b"failures": b"0"}

    await redis.hset(circuit_key("email"), mapping={"state": "half_open", "failures": 5})
    assert await breaker.complete_attempt("email", done_key(2), 604800) is True
    assert await redis.hgetall(circuit_key("email")) == {b"state": b"closed", b"failures": b"0"}

    await redis.hset(circuit_key("email"), mapping={"state": "open", "opened_at": 1})
    assert await breaker.complete_attempt("email", done_key(3), 604800) is False
    assert await redis.hget(circuit_key("email"), "state") == b"open"
    assert await redis.get(done_key(3)) == b"done"
