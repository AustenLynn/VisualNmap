import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from visualnmap.api import create_app, hostname_of
from visualnmap.environment import Environment
from visualnmap.history import History
from visualnmap.models import ScanRequest

FAKE = str(Path(__file__).parent / "fixtures" / "fake_nmap.py")
BASE = "http://127.0.0.1:8765"


def local_client(app) -> TestClient:
    """A client that talks to the app the way a browser on this machine does."""
    return TestClient(app, base_url=BASE)


def make_env(nmap=FAKE, root=True) -> Environment:
    return Environment(is_root=root, can_raw=root, nmap_path=nmap, nmap_version="7.99", in_container=False)


@pytest.fixture
def history(tmp_path):
    h = History(tmp_path / "visualnmap.db")
    yield h
    h.close()


@pytest.fixture
def client(catalog, history, monkeypatch):
    monkeypatch.setenv("FAKE_NMAP_MODE", "ok")
    with local_client(create_app(make_env(), catalog, history)) as c:
        yield c


def start_scan(client, body=None) -> str:
    resp = client.post("/api/scans", json=body or {"target": "10.0.0.1", "profile_id": "quick_ports"})
    assert resp.status_code == 201, resp.text
    return resp.json()["scan_id"]


def stream_events(client, scan_id, headers=None) -> list[dict]:
    events = []
    with client.websocket_connect(f"ws://127.0.0.1:8765/api/scans/{scan_id}/stream", headers=headers or {}) as ws:
        while True:
            try:
                events.append(ws.receive_json())
            except WebSocketDisconnect:
                break
            if events[-1]["type"] in ("done", "error"):
                break
    return events


def test_status(client):
    body = client.get("/api/status").json()
    assert body == {
        "is_root": True, "can_raw": True, "nmap_found": True,
        "nmap_version": "7.99", "in_container": False, "active_scan_id": None,
    }


def test_catalog(client):
    body = client.get("/api/catalog").json()
    assert "syn_scan" in body["options"]
    assert body["ports"]["22"]["service"] == "ssh"
    assert "quick_ports" in body["profiles"]


def test_preview_ok(client):
    body = client.post("/api/command/preview", json={"target": "10.0.0.1", "profile_id": "quick_ports"}).json()
    assert body["argv"][0] == FAKE
    assert body["argv"][-1] == "10.0.0.1"
    assert body["parts"][-1]["kind"] == "target"


def test_preview_invalid_target_422(client):
    resp = client.post("/api/command/preview", json={"target": "-iL /etc/shadow"})
    assert resp.status_code == 422
    assert resp.json()["field"] == "target"


def test_preview_root_option_without_root(catalog, history):
    with local_client(create_app(make_env(root=False), catalog, history)) as c:
        resp = c.post("/api/command/preview", json={"target": "10.0.0.1", "options": [{"id": "syn_scan"}]})
    assert resp.status_code == 422
    assert resp.json()["field"] == "options.syn_scan"


def test_full_scan_flow(client):
    sid = start_scan(client)
    events = stream_events(client, sid)
    assert events[-1] == {"type": "done", "status": "completed"}
    assert any(e.get("line") == "Started: Fake Scan" for e in events)
    rec = client.get(f"/api/scans/{sid}").json()
    assert rec["status"] == "completed"
    assert rec["hosts_up"] == 1 and rec["open_ports"] == 1
    assert rec["result"]["hosts"][0]["ports"][0]["note"].startswith("Remote command-line")
    assert rec["hints"] == []
    assert [s["id"] for s in client.get("/api/scans").json()] == [sid]
    assert client.get("/api/status").json()["active_scan_id"] is None


def test_export(client):
    sid = start_scan(client)
    stream_events(client, sid)
    xml = client.get(f"/api/scans/{sid}/export?format=xml")
    assert xml.status_code == 200 and b"<nmaprun" in xml.content
    assert "attachment" in xml.headers["content-disposition"]
    js = client.get(f"/api/scans/{sid}/export?format=json")
    assert json.loads(js.content)["id"] == sid
    assert client.get(f"/api/scans/{sid}/export?format=csv").status_code == 422
    assert client.get("/api/scans/nope/export?format=xml").status_code == 404


def test_busy_cancel_and_cancelled_hint(client, monkeypatch):
    monkeypatch.setenv("FAKE_NMAP_MODE", "slow")
    sid = start_scan(client)
    busy = client.post("/api/scans", json={"target": "10.0.0.2", "profile_id": "quick_ports"})
    assert busy.status_code == 409
    assert busy.json()["active_scan_id"] == sid
    assert client.delete(f"/api/scans/{sid}").status_code == 409
    assert client.post(f"/api/scans/{sid}/cancel").status_code == 202
    events = stream_events(client, sid)
    assert events[-1] == {"type": "done", "status": "cancelled"}
    rec = client.get(f"/api/scans/{sid}").json()
    assert rec["status"] == "cancelled"
    assert "cancelled" in [h["code"] for h in rec["hints"]]


def test_cancel_finished_scan_409(client):
    sid = start_scan(client)
    stream_events(client, sid)
    assert client.post(f"/api/scans/{sid}/cancel").status_code == 409


def test_delete(client):
    sid = start_scan(client)
    stream_events(client, sid)
    assert client.delete(f"/api/scans/{sid}").status_code == 204
    assert client.get(f"/api/scans/{sid}").status_code == 404
    assert client.delete(f"/api/scans/{sid}").status_code == 404


def test_failed_scan_has_resolve_hint(client, monkeypatch):
    monkeypatch.setenv("FAKE_NMAP_MODE", "fail")
    sid = start_scan(client)
    assert stream_events(client, sid)[-1]["status"] == "failed"
    codes = [h["code"] for h in client.get(f"/api/scans/{sid}").json()["hints"]]
    assert "resolve" in codes


def test_nmap_missing_503(catalog, history):
    with local_client(create_app(make_env(nmap=None), catalog, history)) as c:
        assert c.get("/api/status").json()["nmap_found"] is False
        resp = c.post("/api/scans", json={"target": "10.0.0.1", "profile_id": "quick_ports"})
    assert resp.status_code == 503
    assert "apt install nmap" in resp.json()["message"]


def test_foreign_origin_blocked(client):
    resp = client.post("/api/scans", json={"target": "10.0.0.1"}, headers={"origin": "http://evil.example"})
    assert resp.status_code == 403
    ok = client.post("/api/command/preview", json={"target": "10.0.0.1"}, headers={"origin": BASE})
    assert ok.status_code == 200


def test_ws_foreign_origin_rejected(client):
    sid = start_scan(client)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"ws://127.0.0.1:8765/api/scans/{sid}/stream", headers={"origin": "http://evil.example"}) as ws:
            ws.receive_json()
    stream_events(client, sid)


def test_ws_for_finished_scan_after_restart_sends_done(catalog, history, monkeypatch):
    monkeypatch.setenv("FAKE_NMAP_MODE", "ok")
    with local_client(create_app(make_env(), catalog, history)) as c1:
        sid = start_scan(c1)
        stream_events(c1, sid)
    with local_client(create_app(make_env(), catalog, history)) as c2:  # fresh runner, same history
        assert stream_events(c2, sid) == [{"type": "done", "status": "completed"}]
        assert stream_events(c2, "nope") == [{"type": "error", "message": "Unknown scan."}]


def test_interrupted_scans_recovered_on_startup(catalog, history):
    sid = history.create(ScanRequest(target="10.0.0.1"), ["nmap", "10.0.0.1"])
    with local_client(create_app(make_env(), catalog, history)) as c:
        assert c.get(f"/api/scans/{sid}").json()["status"] == "failed"


def test_compare_endpoint(client):
    a = start_scan(client)
    stream_events(client, a)
    b = start_scan(client)
    stream_events(client, b)
    diff = client.get(f"/api/compare?a={a}&b={b}").json()
    assert diff["hosts_added"] == [] and diff["per_host"] == {}
    assert client.get(f"/api/compare?a={a}&b=nope").status_code == 404


def test_unknown_scan_404(client):
    assert client.get("/api/scans/nope").status_code == 404


def test_static_spa_serving(catalog, history, tmp_path):
    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>INDEX</html>")
    (static / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("SECRET")
    with local_client(create_app(make_env(), catalog, history, static_dir=static)) as c:
        assert "INDEX" in c.get("/").text
        assert "INDEX" in c.get("/history").text
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert "SECRET" not in c.get("/..%2Fsecret.txt").text
        assert c.get("/api/does-not-exist").status_code == 404


def test_frontend_not_built_message(catalog, history, tmp_path):
    with local_client(create_app(make_env(), catalog, history, static_dir=tmp_path / "missing")) as c:
        assert "Frontend not built" in c.get("/").text


EVIL = {"host": "evil.example:8765", "origin": "http://evil.example:8765"}


def test_dns_rebinding_host_rejected_for_http(client):
    # A rebinding attack makes Host and Origin agree with each other, so only a Host allowlist stops it.
    assert client.get("/api/status", headers={"host": "evil.example:8765"}).status_code == 400
    resp = client.post("/api/scans", json={"target": "10.0.0.1", "profile_id": "quick_ports"}, headers=EVIL)
    assert resp.status_code == 400


def test_dns_rebinding_host_rejected_for_websocket(client):
    sid = start_scan(client)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"ws://127.0.0.1:8765/api/scans/{sid}/stream", headers=EVIL) as ws:
            ws.receive_json()
    stream_events(client, sid)


def test_localhost_name_allowed(client):
    assert client.get("/api/status", headers={"host": "localhost:8765"}).status_code == 200


def test_extra_allowed_host(catalog, history):
    app = create_app(make_env(), catalog, history, allowed_hosts=["127.0.0.1", "192.168.1.5"])
    with TestClient(app, base_url="http://192.168.1.5:8765") as c:
        assert c.get("/api/status").status_code == 200


@pytest.mark.parametrize(
    "header,name",
    [("127.0.0.1:8765", "127.0.0.1"), ("LOCALHOST", "localhost"), ("[::1]:8765", "::1"), ("::1", "::1"), ("", "")],
)
def test_hostname_of(header, name):
    assert hostname_of(header) == name
