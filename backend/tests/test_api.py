import pytest
from fastapi.testclient import TestClient

from ew_core.api import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_state_shape(client):
    r = client.get("/api/state")
    assert r.status_code == 200
    body = r.json()
    for key in ("time", "scenario", "receiver", "ownship", "spectrum", "tracks", "alerts"):
        assert key in body


def test_library_and_scenarios(client):
    assert len(client.get("/api/library").json()) >= 5
    names = {s["name"] for s in client.get("/api/scenarios").json()}
    assert {"littoral_patrol", "quiet_range"} <= names


def test_receiver_update_and_validation(client):
    r = client.put("/api/receiver", json={"start_hz": 1e9, "stop_hz": 4e9})
    assert r.status_code == 200
    assert r.json()["start_hz"] == 1e9
    r = client.put("/api/receiver", json={"start_hz": 5e9, "stop_hz": 4e9})
    assert r.status_code == 422


def test_unknown_track_and_scenario(client):
    assert client.get("/api/tracks/E-999").status_code == 404
    assert client.post("/api/scenarios/nope/load").status_code == 404


def test_websocket_stream(client):
    with client.websocket_connect("/ws/stream") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        state = ws.receive_json()
        assert state["type"] == "state"
        assert "spectrum" in state["data"]
