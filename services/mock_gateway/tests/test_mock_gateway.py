"""Mock gateway behaviour: messages, outage, retries, health, tickets, request log."""

import pytest
from fastapi.testclient import TestClient

from services.mock_gateway.main import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("MOCK_GATEWAY_RETRY_FAILURES", "2")
    return TestClient(create_app())


def test_sms_and_phone_store_and_return_message_id(client: TestClient) -> None:
    sms = client.post("/sms", json={"to": "+48600000000", "text": "hi", "delivery_id": "d1"})
    phone = client.post("/phone", json={"to": "+48600000000", "text": "hi"})
    assert sms.status_code == 200 and sms.json()["message_id"]
    assert phone.status_code == 200 and phone.json()["message_id"] != sms.json()["message_id"]
    assert len(client.get("/requests", params={"path_prefix": "/sms"}).json()) == 1


def test_invalid_message_is_422(client: TestClient) -> None:
    assert client.post("/sms", json={"to": "x"}).status_code == 422


def test_outage_rejects_and_records(client: TestClient) -> None:
    client.post("/admin/outage", json={"is_down": True, "channels": ["sms"]})
    assert client.post("/sms", json={"to": "a", "text": "b"}).status_code == 503
    assert client.post("/phone", json={"to": "a", "text": "b"}).status_code == 200
    assert client.get("/requests", params={"path_prefix": "/sms"}).json()[0]["rejected"] is True
    assert client.get("/admin/outage").json() == {"is_down": True, "channels": ["sms"]}
    assert "mock_gateway_up 0.0" in client.get("/metrics").text
    client.post("/admin/outage", json={"is_down": False, "channels": None})
    assert client.post("/sms", json={"to": "a", "text": "b"}).status_code == 200
    assert "mock_gateway_up 1.0" in client.get("/metrics").text


def test_outage_all_includes_webhooks(client: TestClient) -> None:
    client.post("/admin/outage", json={"is_down": True, "channels": None})
    assert client.post("/webhooks/slack-rates", json={"text": "x"}).status_code == 503
    assert client.get("/healthz").status_code == 200
    client.post("/admin/outage", json={"is_down": False, "channels": None})


def test_workflow_retry_fails_first_n_then_succeeds(client: TestClient) -> None:
    codes = [client.post("/workflows/w1/retry").status_code for _ in range(4)]
    assert codes == [502, 502, 200, 200]
    assert client.post("/workflows/w2/retry").status_code == 502


def test_service_health_toggle_and_restart(client: TestClient) -> None:
    assert client.get("/services/pricing-adapter/health").status_code == 200
    client.post("/admin/services/pricing-adapter/health", json={"is_healthy": False})
    response = client.get("/services/pricing-adapter/health")
    assert response.status_code == 503 and response.json() == {"status": "unhealthy"}
    assert client.post("/services/pricing-adapter/restart").json() == {"restarted": True}
    assert client.get("/services/pricing-adapter/health").status_code == 200


def test_tickets_webhooks_and_request_listing(client: TestClient) -> None:
    assert client.post("/tickets", json={}).json() == {"ticket_id": "TCK-1"}
    assert client.post("/tickets", json={}).json() == {"ticket_id": "TCK-2"}
    client.post("/webhooks/escalations", json={"a": 1})
    listed = client.get("/requests", params={"path_prefix": "/webhooks", "limit": 5}).json()
    assert listed[0]["body"] == {"a": 1}
    assert client.delete("/requests").json() == {"cleared": True}
    assert client.get("/requests").json() == []
