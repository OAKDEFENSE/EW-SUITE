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


def test_terrain_endpoints(client):
    info = client.get("/api/terrain").json()
    assert info["model"] in {"synthetic", "flat", "hgt"}
    r = client.get("/api/terrain/elevation", params={"lat": 55.48, "lon": -2.15})
    assert r.status_code == 200 and r.json()["elevation_m"] >= 0
    r = client.get(
        "/api/terrain/grid", params={"south": 55, "west": -2.5, "north": 56, "east": 0, "n": 20}
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["elevation_m"]) == body["n_lat"]
    r = client.get(
        "/api/terrain/grid", params={"south": 56, "west": -2.5, "north": 55, "east": 0, "n": 20}
    )
    assert r.status_code == 422


def test_coverage_endpoints(client):
    r = client.post(
        "/api/coverage",
        json={
            "lat": 55.35,
            "lon": -1.55,
            "eirp_dbm": 90,
            "freq_hz": 2.9e9,
            "n": 12,
            "radius_km": 20,
        },
    )
    assert r.status_code == 200
    assert len(r.json()["power_dbm"]) == 12
    assert client.get("/api/tracks/E-999/coverage").status_code == 404
    assert client.post("/api/coverage", json={"lat": 55, "lon": -1}).status_code == 422


def test_blue_network_and_links(client):
    net = client.get("/api/blue").json()
    assert {n["id"] for n in net["nodes"]} >= {"OWN", "GCS"}
    links = client.get("/api/links").json()
    assert isinstance(links, list)
    state = client.get("/api/state").json()
    assert "blue" in state and "links" in state
    # Replace the network with a minimal valid one, then reject an invalid one.
    minimal = {
        "nodes": [
            {"id": "OWN", "name": "own", "kind": "ownship"},
            {
                "id": "G",
                "name": "g",
                "kind": "ground",
                "position": {"lat": 55.4, "lon": -1.5, "alt_m": 10},
            },
        ],
        "links": [
            {
                "id": "L1",
                "name": "l1",
                "tx": "OWN",
                "rx": "G",
                "freq_hz": 1e9,
                "bandwidth_hz": 1e6,
                "tx_power_dbm": 40,
            }
        ],
    }
    r = client.put("/api/blue", json=minimal)
    assert r.status_code == 200 and r.json()["links"][0]["id"] == "L1"
    bad = {**minimal, "links": [{**minimal["links"][0], "rx": "NOPE"}]}
    assert client.put("/api/blue", json=bad).status_code == 422
    r = client.get("/api/links/L1/relay-grid", params={"n": 12, "radius_km": 20})
    assert r.status_code == 200
    body = r.json()
    assert len(body["margin_db"]) == 12 and body["link_id"] == "L1"
    assert client.get("/api/links/NOPE/relay-grid").status_code == 404
