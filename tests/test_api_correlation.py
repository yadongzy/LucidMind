from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.main import correlate_http_request
from diagnostics import get_collector


def _client():
    app = FastAPI()
    app.middleware("http")(correlate_http_request)

    @app.get("/probe")
    async def probe():
        from diagnostics import record_event
        record_event("probe", "inside_request", "success", 0)
        return {"ok": True}

    return TestClient(app)


def test_http_request_id_is_returned_and_propagated():
    response = _client().get("/probe", headers={"X-Request-ID": "request:test-123"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "request:test-123"
    probe = get_collector().query(category="probe")[-1]
    assert probe["metadata"]["correlation_id"] == "request:test-123"
    request_event = get_collector().query(category="api_request")[-1]
    assert request_event["metadata"]["correlation_id"] == "request:test-123"


def test_http_request_id_is_generated_when_absent():
    response = _client().get("/probe")
    request_id = response.headers["X-Request-ID"]
    assert request_id.startswith("request:")
    assert len(request_id) > len("request:")
