"""Runs nmap as a subprocess (never through a shell) and streams its progress as events."""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

FinishCallback = Callable[[str, str, str, str], Awaitable[None]]
_TASK = re.compile(r"<(taskbegin|taskprogress|taskend)\s([^>]*?)/?>")
_ATTR = re.compile(r'(\w+)="([^"]*)"')
STDERR_TAIL_LINES = 50
READ_LIMIT = 1024 * 1024


class ScanBusy(Exception):
    def __init__(self, active_id: str):
        super().__init__(f"scan {active_id} is already running")
        self.active_id = active_id


def _output(line: str) -> dict:
    return {"type": "output", "line": line}


def _eta_text(remaining: str | None) -> str | None:
    if not remaining:
        return None
    try:
        seconds = int(float(remaining))
    except ValueError:
        return None
    if seconds < 60:
        return f"about {seconds} s left"
    if seconds < 3600:
        return f"about {round(seconds / 60)} min left"
    return f"about {seconds / 3600:.1f} h left"


def describe_task_line(line: str) -> list[dict]:
    match = _TASK.search(line)
    if not match:
        return []
    kind = match.group(1)
    attrs = dict(_ATTR.findall(match.group(2)))
    task = attrs.get("task", "Scan")
    if kind == "taskbegin":
        return [_output(f"Started: {task}"), {"type": "progress", "task": task, "percent": None, "eta": None}]
    if kind == "taskend":
        extra = attrs.get("extrainfo")
        return [_output(f"Finished: {task}" + (f" ({extra})" if extra else ""))]
    try:
        percent = float(attrs.get("percent", "0"))
    except ValueError:
        percent = 0.0
    eta = _eta_text(attrs.get("remaining"))
    text = f"{task} {int(percent)}% done" + (f", {eta}" if eta else "")
    return [_output(text), {"type": "progress", "task": task, "percent": percent, "eta": eta}]


@dataclass
class _Scan:
    cond: asyncio.Condition = field(default_factory=asyncio.Condition)
    events: list[dict] = field(default_factory=list)
    dropped: int = 0
    done: bool = False
    cancelled: bool = False
    proc: asyncio.subprocess.Process | None = None
    task: asyncio.Task | None = None
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)


class ScanRunner:
    def __init__(self, on_finish: FinishCallback, buffer_limit: int = 5000, kill_grace: float = 5.0):
        self._on_finish = on_finish
        self._limit = buffer_limit
        self._grace = kill_grace
        self._scans: dict[str, _Scan] = {}
        self._active: str | None = None

    def active_scan_id(self) -> str | None:
        return self._active

    def knows(self, scan_id: str) -> bool:
        return scan_id in self._scans

    async def _emit(self, state: _Scan, event: dict, final: bool = False) -> None:
        async with state.cond:
            state.events.append(event)
            overflow = len(state.events) - self._limit
            if overflow > 0:
                del state.events[:overflow]
                state.dropped += overflow
            if final:
                state.done = True
            state.cond.notify_all()

    async def start(self, scan_id: str, argv: list[str]) -> None:
        if self._active is not None:
            raise ScanBusy(self._active)
        state = _Scan()
        self._scans[scan_id] = state
        self._active = scan_id
        try:
            state.proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=READ_LIMIT,
            )
        except OSError as exc:
            await self._emit(state, _output(f"Could not start nmap: {exc}"))
            state.stderr.append(f"Could not start nmap: {exc}\n")
            state.task = asyncio.create_task(self._finish(scan_id, state, "failed"))
            return
        state.task = asyncio.create_task(self._run(scan_id, state))

    async def _read_stdout(self, state: _Scan) -> None:
        assert state.proc and state.proc.stdout
        async for raw in state.proc.stdout:
            line = raw.decode("utf-8", errors="replace")
            state.stdout.append(line)
            for event in describe_task_line(line):
                await self._emit(state, event)

    async def _read_stderr(self, state: _Scan) -> None:
        assert state.proc and state.proc.stderr
        async for raw in state.proc.stderr:
            line = raw.decode("utf-8", errors="replace")
            state.stderr.append(line)
            if len(state.stderr) > STDERR_TAIL_LINES:
                del state.stderr[0]
            await self._emit(state, _output(line.rstrip("\r\n")))

    async def _run(self, scan_id: str, state: _Scan) -> None:
        assert state.proc
        try:
            await asyncio.gather(self._read_stdout(state), self._read_stderr(state))
            code = await state.proc.wait()
        except Exception:  # never leave a scan stuck in "running"
            log.exception("error while reading nmap output")
            code = -1
        status = "cancelled" if state.cancelled else ("completed" if code == 0 else "failed")
        await self._finish(scan_id, state, status)

    async def _finish(self, scan_id: str, state: _Scan, status: str) -> None:
        try:
            await self._on_finish(scan_id, status, "".join(state.stdout), "".join(state.stderr))
        except Exception:
            log.exception("on_finish failed for scan %s", scan_id)
        finally:
            if self._active == scan_id:
                self._active = None
            await self._emit(state, {"type": "done", "status": status}, final=True)
            state.finished.set()

    async def cancel(self, scan_id: str) -> bool:
        state = self._scans.get(scan_id)
        if state is None or state.done or state.proc is None:
            return False
        if state.cancelled:
            return True
        state.cancelled = True
        await self._emit(state, _output("Cancelling scan..."))
        try:
            state.proc.terminate()
        except ProcessLookupError:
            return True
        try:
            await asyncio.wait_for(state.proc.wait(), self._grace)
        except asyncio.TimeoutError:
            try:
                state.proc.kill()
            except ProcessLookupError:
                pass
        return True

    async def subscribe(self, scan_id: str) -> AsyncIterator[dict]:
        state = self._scans.get(scan_id)
        if state is None:
            return
        index = 0
        while True:
            async with state.cond:
                await state.cond.wait_for(lambda: index < state.dropped + len(state.events) or state.done)
                index = max(index, state.dropped)
                batch = state.events[index - state.dropped:]
                index += len(batch)
                finished = state.done and index >= state.dropped + len(state.events)
            for event in batch:
                yield event
            if finished:
                return

    async def wait(self, scan_id: str) -> None:
        state = self._scans.get(scan_id)
        if state is not None:
            await state.finished.wait()

    async def shutdown(self) -> None:
        if self._active is not None:
            active = self._active
            await self.cancel(active)
            await self.wait(active)
