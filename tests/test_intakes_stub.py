"""SCRUM-13: take/snooze stubs follow the API contract."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_take_stub_returns_all_contract_results():
    assert client.post("/intakes/1/take").json()["result"] == "ok"
    assert client.post("/intakes/2/take").json()["result"] == "already_taken"
    assert client.post("/intakes/3/take").json()["result"] == "missed"


def test_take_stub_unknown_id_is_404():
    assert client.post("/intakes/999/take").status_code == 404


def test_snooze_stub_returns_remind_at():
    body = client.post("/intakes/1/snooze").json()
    assert body["result"] == "ok"
    assert body["remind_at"] is not None