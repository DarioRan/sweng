"""Contract-shape tests: run without any store, so they pass in CI on the bare scaffold."""

from fastapi.testclient import TestClient

from app.main import app


def test_openapi_lists_the_five_contracts() -> None:
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]
    for path in ("/api/detect", "/api/ask", "/api/figure", "/api/transcribe", "/api/documents"):
        assert path in paths, path


def test_ask_stub_is_typed_and_not_yet_implemented() -> None:
    with TestClient(app) as client:
        response = client.post("/api/ask", json={"question": "torque?", "job_id": "j1"})
    assert response.status_code == 501


def test_ask_rejects_malformed_request() -> None:
    with TestClient(app) as client:
        response = client.post("/api/ask", json={"job_id": "j1"})
    assert response.status_code == 422
