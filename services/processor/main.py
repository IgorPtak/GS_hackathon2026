"""Processor worker stub (track A).

Exposes /healthz on metrics port 9101; the consumer itself arrives in A-09.
"""

from fastapi import FastAPI

app = FastAPI()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe used by compose healthchecks."""
    return {"status": "ok"}
