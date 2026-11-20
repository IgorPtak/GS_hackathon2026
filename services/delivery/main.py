"""Delivery worker stub (track A).

Exposes /healthz on metrics port 9103; the worker itself arrives in A-13.
"""

from fastapi import FastAPI

app = FastAPI()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe used by compose healthchecks."""
    return {"status": "ok"}
