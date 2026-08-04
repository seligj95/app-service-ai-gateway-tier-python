from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.api import create_app
from app.errors import GatewayFailure


class FakeAgent:
    def __init__(self, chunks: list[str] | None = None, failure: GatewayFailure | None = None) -> None:
        self.chunks = chunks or []
        self.failure = failure
        self.calls: list[tuple[str, str]] = []

    async def stream(self, message: str, correlation_id: str) -> AsyncIterator[str]:
        self.calls.append((message, correlation_id))
        for chunk in self.chunks:
            yield chunk
        if self.failure:
            raise self.failure


def test_sse_streams_deltas_and_correlation(settings) -> None:
    agent = FakeAgent(["hello", " world"])
    client = TestClient(create_app(settings, agent))
    response = client.post(
        "/api/chat/stream",
        json={"message": "hello"},
        headers={"x-correlation-id": "test-correlation"},
    )
    assert response.status_code == 200
    assert response.headers["x-correlation-id"] == "test-correlation"
    assert "event: meta" in response.text
    assert '"text":"hello"' in response.text
    assert '"text":" world"' in response.text
    assert "event: done" in response.text
    assert agent.calls == [("hello", "test-correlation")]


def test_sse_returns_sanitized_gateway_error(settings) -> None:
    client = TestClient(
        create_app(settings, FakeAgent(failure=GatewayFailure(401, "gateway_unauthorized")))
    )
    response = client.post("/api/chat/stream", json={"message": "hello"})
    assert response.status_code == 200
    assert "gateway_unauthorized" in response.text
    assert "opaque-runtime-value" not in response.text


def test_health_status_and_clean_ui_work_without_gateway_settings() -> None:
    client = TestClient(create_app())
    assert client.get("/health").json()["status"] == "healthy"
    assert client.get("/status").json()["status"] == "configuration_required"
    assert "App Service AI Gateway tier chat" in client.get("/").text


def test_correlation_identifier_is_generated_when_missing(settings) -> None:
    client = TestClient(create_app(settings, FakeAgent(["ok"])))
    response = client.get("/status")
    assert response.headers["x-correlation-id"]
    assert response.json()["correlationId"] == response.headers["x-correlation-id"]


def test_invalid_request_does_not_echo_message_content(settings) -> None:
    client = TestClient(create_app(settings, FakeAgent(["ok"])))
    response = client.post("/api/chat/stream", json={"message": ""})
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "invalid_request"}}
