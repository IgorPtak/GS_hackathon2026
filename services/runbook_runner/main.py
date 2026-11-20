"""Runbook runner worker stub (track B).

Exposes /healthz on metrics port 9104; the runner itself arrives in B-06.
"""

from fastapi import FastAPI

app = FastAPI()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe used by compose healthchecks."""
    return {"status": "ok"}
