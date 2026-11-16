"""Contract-shape tests: run without any store, so they pass in CI on the bare scaffold."""

import httpx
from fastapi.testclient import TestClient

from app.contracts import AnswerStatus, AskResponse
from app.main import app


def test_openapi_lists_the_five_contracts() -> None:
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]
    for path in ("/api/detect", "/api/ask", "/api/figure", "/api/transcribe", "/api/documents"):
        assert path in paths, path


def test_ask_answers_in_the_contract_shape() -> None:
    """The route returns what the pipeline gives; the pipeline itself is tested in test_rag."""

    class Abstains:
        async def ask(self, question: str, component: str | None = None):
            return AskResponse(status=AnswerStatus.abstained, confidence=0.1, stop_reason="x"), None

    with TestClient(app) as client:
        app.state.ask_pipeline = Abstains()
        response = client.post("/api/ask", json={"question": "torque?", "job_id": "j1"})
        del app.state.ask_pipeline
    assert response.status_code == 200
    assert response.json()["status"] == "abstained"


def test_ask_rejects_malformed_request() -> None:
    with TestClient(app) as client:
        response = client.post("/api/ask", json={"job_id": "j1"})
    assert response.status_code == 422


def test_ask_says_what_to_start_when_the_model_is_not_running() -> None:
    class Unreachable:
        async def ask(self, question: str, component: str | None = None):
            raise httpx.ConnectError("connection refused")

    with TestClient(app) as client:
        app.state.ask_pipeline = Unreachable()
        response = client.post("/api/ask", json={"question": "torque?", "job_id": "j1"})
        del app.state.ask_pipeline
    assert response.status_code == 503
    assert "docker compose --profile local up" in response.json()["detail"]
