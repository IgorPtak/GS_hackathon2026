"""Outbox relay worker stub (track A).

Exposes /healthz on metrics port 9102; the relay itself arrives in A-11.
"""

from fastapi import FastAPI

app = FastAPI()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe used by compose healthchecks."""
    return {"status": "ok"}
