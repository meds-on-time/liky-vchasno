from fastapi.testclient import TestClient

from app.main import app


def test_root_returns_200():
    # Not using context manager: background polling/DB are irrelevant to this test.
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "starter"


def test_openapi_is_available():
    response = TestClient(app).get("/openapi.json")
    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
