import json

import pytest

from visualnmap.history import History
from visualnmap.models import Host, OptionValue, ParsedResult, Port, ScanRequest, ScanStats

REQ = ScanRequest(target="192.168.1.10", profile_id="services", options=[OptionValue(id="timing", value=4)])
ARGV = ["nmap", "-sV", "-F", "-T4", "-v", "--stats-every", "2s", "-oX", "-", "192.168.1.10"]


def port(n, state="open", service="ssh", product=None, version=None):
    return Port(port=n, protocol="tcp", state=state, service=service, product=product, version=version)


def result(*hosts):
    up = sum(1 for h in hosts if h.status == "up")
    return ParsedResult(hosts=list(hosts), stats=ScanStats(up=up, total=len(hosts)))


R1 = result(Host(address="10.0.0.1", status="up", ports=[port(22, product="OpenSSH", version="8.9"), port(80, service="http")]))


@pytest.fixture
def history(tmp_path):
    h = History(tmp_path / "data" / "visualnmap.db")
    yield h
    h.close()


def test_create_and_get_running(history):
    sid = history.create(REQ, ARGV)
    rec = history.get(sid)
    assert rec.status == "running"
    assert rec.request == REQ
    assert rec.argv == ARGV
    assert rec.target == "192.168.1.10" and rec.profile_id == "services"
    assert rec.result is None and rec.finished_at is None


def test_finish_stores_result_and_counts(history):
    sid = history.create(REQ, ARGV)
    history.finish(sid, "completed", "<nmaprun/>", R1, "warning line")
    rec = history.get(sid)
    assert rec.status == "completed"
    assert rec.hosts_up == 1 and rec.open_ports == 2
    assert rec.result == R1
    assert rec.stderr_tail == "warning line"
    assert rec.finished_at is not None
    assert history.get_raw_xml(sid) == "<nmaprun/>"


def test_list_newest_first_with_limit(history):
    ids = [history.create(REQ, ARGV) for _ in range(3)]
    listed = [s.id for s in history.list()]
    assert listed == list(reversed(ids))
    assert len(history.list(limit=2)) == 2


def test_delete(history):
    sid = history.create(REQ, ARGV)
    assert history.delete(sid) is True
    assert history.get(sid) is None
    assert history.delete(sid) is False


def test_export(history):
    sid = history.create(REQ, ARGV)
    history.finish(sid, "completed", "<nmaprun>x</nmaprun>", R1, "")
    content, media = history.export(sid, "xml")
    assert content == b"<nmaprun>x</nmaprun>" and media == "application/xml"
    content, media = history.export(sid, "json")
    assert media == "application/json"
    assert json.loads(content)["result"]["hosts"][0]["address"] == "10.0.0.1"
    assert history.export("missing", "json") is None


def test_recover_interrupted(history):
    sid = history.create(REQ, ARGV)
    assert history.recover_interrupted() == 1
    rec = history.get(sid)
    assert rec.status == "failed"
    assert rec.stderr_tail == "App stopped during scan"


def test_persists_across_instances(tmp_path):
    path = tmp_path / "h.db"
    h1 = History(path)
    sid = h1.create(REQ, ARGV)
    h1.close()
    h2 = History(path)
    assert h2.get(sid) is not None
    h2.close()


def test_compare(history):
    r2 = result(
        Host(
            address="10.0.0.1",
            status="up",
            ports=[port(22, product="OpenSSH", version="9.6"), port(80, service="http", state="closed"), port(8080, service="http-proxy")],
        ),
        Host(address="10.0.0.7", status="up", ports=[port(443, service="https")]),
    )
    a = history.create(REQ, ARGV)
    history.finish(a, "completed", "", R1, "")
    b = history.create(REQ, ARGV)
    history.finish(b, "completed", "", r2, "")
    diff = history.compare(a, b)
    assert diff.hosts_added == ["10.0.0.7"]
    assert diff.hosts_removed == []
    h = diff.per_host["10.0.0.1"]
    assert h.ports_opened == ["8080/tcp"]
    assert h.ports_closed == ["80/tcp"]
    assert [(c.port, c.before, c.after) for c in h.services_changed] == [("22/tcp", "ssh OpenSSH 8.9", "ssh OpenSSH 9.6")]
    assert diff.per_host["10.0.0.7"].ports_opened == ["443/tcp"]


def test_compare_unknown_raises(history):
    a = history.create(REQ, ARGV)
    with pytest.raises(KeyError):
        history.compare(a, "nope")
