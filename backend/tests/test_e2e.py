"""Runs the real nmap binary against this machine. Opt in with VISUALNMAP_E2E=1."""
import os
import shutil

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from visualnmap.api import create_app
from visualnmap.environment import detect_environment
from visualnmap.history import History

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("VISUALNMAP_E2E") != "1" or shutil.which("nmap") is None,
        reason="set VISUALNMAP_E2E=1 and install nmap to run",
    ),
]


def run_scan(client: TestClient, body: dict) -> dict:
    resp = client.post("/api/scans", json=body)
    assert resp.status_code == 201, resp.text
    sid = resp.json()["scan_id"]
    with client.websocket_connect(f"/api/scans/{sid}/stream") as ws:
        while True:
            try:
                event = ws.receive_json()
            except WebSocketDisconnect:
                break
            if event["type"] == "done":
                break
    return client.get(f"/api/scans/{sid}").json()


@pytest.fixture
def client(catalog, tmp_path):
    history = History(tmp_path / "e2e.db")
    with TestClient(create_app(detect_environment(), catalog, history)) as c:
        yield c
    history.close()


def test_real_ping_scan_of_localhost(client):
    rec = run_scan(client, {"target": "127.0.0.1", "profile_id": "find_devices"})
    assert rec["status"] == "completed", rec["stderr_tail"]
    assert rec["hosts_up"] == 1
    assert rec["result"]["hosts"][0]["address"] == "127.0.0.1"


def test_real_quick_port_scan_of_localhost(client):
    rec = run_scan(client, {"target": "127.0.0.1", "options": [{"id": "fast"}, {"id": "connect_scan"}]})
    assert rec["status"] == "completed", rec["stderr_tail"]
    assert rec["result"]["partial"] is False
    assert rec["result"]["stats"]["up"] == 1
