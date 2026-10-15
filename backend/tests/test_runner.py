import asyncio
import sys
from pathlib import Path

import pytest

from visualnmap.runner import ScanBusy, ScanRunner, describe_task_line

FAKE = str(Path(__file__).parent / "fixtures" / "fake_nmap.py")
ARGV = [sys.executable, FAKE]


class Recorder:
    def __init__(self):
        self.calls = []

    async def __call__(self, scan_id, status, xml, stderr_tail):
        self.calls.append((scan_id, status, xml, stderr_tail))


async def collect(runner, sid):
    return [ev async for ev in runner.subscribe(sid)]


async def wait_first_event(runner, sid):
    async for ev in runner.subscribe(sid):
        return ev


def test_describe_task_lines():
    assert describe_task_line('<taskbegin task="Connect Scan" time="1"/>') == [
        {"type": "output", "line": "Started: Connect Scan"},
        {"type": "progress", "task": "Connect Scan", "percent": None, "eta": None},
    ]
    assert describe_task_line('<taskprogress task="Connect Scan" time="2" percent="42.50" remaining="90" etc="3"/>') == [
        {"type": "output", "line": "Connect Scan 42% done, about 2 min left"},
        {"type": "progress", "task": "Connect Scan", "percent": 42.5, "eta": "about 2 min left"},
    ]
    assert describe_task_line('<taskend task="Connect Scan" time="3" extrainfo="500 total ports"/>') == [
        {"type": "output", "line": "Finished: Connect Scan (500 total ports)"},
    ]
    assert describe_task_line('<port protocol="tcp" portid="22">') == []


async def test_successful_scan_streams_events_and_finishes(monkeypatch):
    monkeypatch.setenv("FAKE_NMAP_MODE", "ok")
    rec = Recorder()
    runner = ScanRunner(rec)
    await runner.start("s1", ARGV)
    events = await collect(runner, "s1")
    lines = [e["line"] for e in events if e["type"] == "output"]
    assert "Started: Fake Scan" in lines
    assert "Warning: fake warning" in lines
    assert "Finished: Fake Scan (1000 total ports)" in lines
    assert {"type": "progress", "task": "Fake Scan", "percent": 50.0, "eta": "about 2 min left"} in events
    assert events[-1] == {"type": "done", "status": "completed"}
    (sid, status, xml, stderr_tail), = rec.calls
    assert (sid, status) == ("s1", "completed")
    assert "<nmaprun" in xml and "</nmaprun>" in xml
    assert "fake warning" in stderr_tail
    assert runner.active_scan_id() is None


async def test_replay_after_finish(monkeypatch):
    monkeypatch.setenv("FAKE_NMAP_MODE", "ok")
    runner = ScanRunner(Recorder())
    await runner.start("s1", ARGV)
    await runner.wait("s1")
    events = await collect(runner, "s1")
    assert events[0]["line"] == "Started: Fake Scan"
    assert events[-1]["type"] == "done"


async def test_busy_while_running(monkeypatch):
    monkeypatch.setenv("FAKE_NMAP_MODE", "slow")
    runner = ScanRunner(Recorder())
    await runner.start("s1", ARGV)
    with pytest.raises(ScanBusy) as exc:
        await runner.start("s2", ARGV)
    assert exc.value.active_id == "s1"
    assert runner.active_scan_id() == "s1"
    await runner.cancel("s1")
    await runner.wait("s1")


async def test_cancel_terminates(monkeypatch):
    monkeypatch.setenv("FAKE_NMAP_MODE", "slow")
    rec = Recorder()
    runner = ScanRunner(rec)
    await runner.start("s1", ARGV)
    await wait_first_event(runner, "s1")
    assert await runner.cancel("s1") is True
    await asyncio.wait_for(runner.wait("s1"), 5)
    assert rec.calls[0][1] == "cancelled"
    assert "<nmaprun" in rec.calls[0][2]  # partial XML is handed over
    events = await collect(runner, "s1")
    assert events[-1] == {"type": "done", "status": "cancelled"}


async def test_cancel_kills_process_that_ignores_sigterm(monkeypatch):
    monkeypatch.setenv("FAKE_NMAP_MODE", "stubborn")
    rec = Recorder()
    runner = ScanRunner(rec, kill_grace=0.3)
    await runner.start("s1", ARGV)
    await wait_first_event(runner, "s1")
    await runner.cancel("s1")
    await asyncio.wait_for(runner.wait("s1"), 5)
    assert rec.calls[0][1] == "cancelled"


async def test_cancel_twice_is_harmless(monkeypatch):
    monkeypatch.setenv("FAKE_NMAP_MODE", "slow")
    runner = ScanRunner(Recorder())
    await runner.start("s1", ARGV)
    await wait_first_event(runner, "s1")
    first, second = await asyncio.gather(runner.cancel("s1"), runner.cancel("s1"))
    assert first is True and second is True
    await asyncio.wait_for(runner.wait("s1"), 5)
    assert await runner.cancel("s1") is False  # already finished
    assert await runner.cancel("unknown") is False


async def test_failure_exit_code(monkeypatch):
    monkeypatch.setenv("FAKE_NMAP_MODE", "fail")
    rec = Recorder()
    runner = ScanRunner(rec)
    await runner.start("s1", ARGV)
    events = await collect(runner, "s1")
    assert events[-1] == {"type": "done", "status": "failed"}
    assert "Failed to resolve" in rec.calls[0][3]


async def test_non_utf8_output_is_replaced(monkeypatch):
    monkeypatch.setenv("FAKE_NMAP_MODE", "binary")
    rec = Recorder()
    runner = ScanRunner(rec)
    await runner.start("s1", ARGV)
    events = await collect(runner, "s1")
    assert events[-1] == {"type": "done", "status": "completed"}
    assert any("�" in e.get("line", "") for e in events)
    assert "�" in rec.calls[0][2]


async def test_missing_binary_fails_cleanly():
    rec = Recorder()
    runner = ScanRunner(rec)
    await runner.start("s1", ["/nonexistent/nmap", "-F", "10.0.0.1"])
    events = await collect(runner, "s1")
    assert events[-1] == {"type": "done", "status": "failed"}
    assert any("Could not start nmap" in e.get("line", "") for e in events)
    assert rec.calls[0][1] == "failed"
    assert runner.active_scan_id() is None


async def test_buffer_limit_drops_oldest(monkeypatch):
    monkeypatch.setenv("FAKE_NMAP_MODE", "chatty")
    runner = ScanRunner(Recorder(), buffer_limit=5)
    await runner.start("s1", ARGV)
    await runner.wait("s1")
    events = await collect(runner, "s1")
    assert len(events) == 5
    assert events[-1]["type"] == "done"


async def test_unknown_scan_subscribe_yields_nothing():
    runner = ScanRunner(Recorder())
    assert await collect(runner, "nope") == []
    assert runner.knows("nope") is False
