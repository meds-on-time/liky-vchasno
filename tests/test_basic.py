from fastapi.testclient import TestClient

from app.main import app


def test_root_returns_200():
    """Кореневий ендпоінт GET / повертає статус 200 та status='starter'"""
    # Not using context manager: background polling/DB are irrelevant to this test.
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "starter"


def test_openapi_is_available():
    """Схема OpenAPI доступна за /openapi.json і містить шлях /health"""
    response = TestClient(app).get("/openapi.json")
    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
