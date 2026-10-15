"""SQLite-backed scan history, export and compare."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .models import HostDiff, ParsedResult, Port, ScanDiff, ScanRecord, ScanRequest, ScanSummary, ServiceChange
from .parser import hosts_up_count, open_port_count

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    target TEXT NOT NULL,
    profile_id TEXT,
    request_json TEXT NOT NULL,
    argv_json TEXT NOT NULL,
    status TEXT NOT NULL,
    hosts_up INTEGER NOT NULL DEFAULT 0,
    open_ports INTEGER NOT NULL DEFAULT 0,
    raw_xml TEXT NOT NULL DEFAULT '',
    result_json TEXT,
    stderr_tail TEXT NOT NULL DEFAULT ''
);
"""
SUMMARY_COLUMNS = "id, created_at, finished_at, target, profile_id, status, hosts_up, open_ports"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _port_key(key: str) -> tuple[int, str]:
    number, _, proto = key.partition("/")
    return int(number), proto


def _service(p: Port) -> str:
    return " ".join(x for x in (p.service, p.product, p.version) if x) or "unknown"


def _open_ports(result: ParsedResult | None) -> dict[str, dict[str, Port]]:
    hosts: dict[str, dict[str, Port]] = {}
    for host in (result.hosts if result else []):
        if host.status != "up":
            continue
        hosts[host.address] = {f"{p.port}/{p.protocol}": p for p in host.ports if p.state == "open"}
    return hosts


class History:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._db.execute(sql, params)
            self._db.commit()
            return cur

    def create(self, request: ScanRequest, argv: list[str]) -> str:
        scan_id = uuid.uuid4().hex
        self._execute(
            "INSERT INTO scans (id, created_at, target, profile_id, request_json, argv_json, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'running')",
            (scan_id, _now(), request.target, request.profile_id, request.model_dump_json(), json.dumps(argv)),
        )
        return scan_id

    def finish(self, scan_id: str, status: str, raw_xml: str, result: ParsedResult, stderr_tail: str) -> None:
        self._execute(
            "UPDATE scans SET status=?, finished_at=?, raw_xml=?, result_json=?, stderr_tail=?, hosts_up=?, open_ports=? "
            "WHERE id=?",
            (status, _now(), raw_xml, result.model_dump_json(), stderr_tail,
             hosts_up_count(result), open_port_count(result), scan_id),
        )

    def recover_interrupted(self) -> int:
        cur = self._execute(
            "UPDATE scans SET status='failed', finished_at=?, stderr_tail='App stopped during scan' WHERE status='running'",
            (_now(),),
        )
        return cur.rowcount

    def get(self, scan_id: str) -> ScanRecord | None:
        row = self._execute("SELECT * FROM scans WHERE id=?", (scan_id,)).fetchone()
        if row is None:
            return None
        return ScanRecord(
            id=row["id"],
            created_at=row["created_at"],
            finished_at=row["finished_at"],
            target=row["target"],
            profile_id=row["profile_id"],
            status=row["status"],
            hosts_up=row["hosts_up"],
            open_ports=row["open_ports"],
            request=ScanRequest.model_validate_json(row["request_json"]),
            argv=json.loads(row["argv_json"]),
            result=ParsedResult.model_validate_json(row["result_json"]) if row["result_json"] else None,
            stderr_tail=row["stderr_tail"],
        )

    def get_raw_xml(self, scan_id: str) -> str | None:
        row = self._execute("SELECT raw_xml FROM scans WHERE id=?", (scan_id,)).fetchone()
        return row["raw_xml"] if row else None

    def list(self, limit: int = 100) -> list[ScanSummary]:
        rows = self._execute(
            f"SELECT {SUMMARY_COLUMNS} FROM scans ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
        ).fetchall()
        return [ScanSummary(**dict(r)) for r in rows]

    def delete(self, scan_id: str) -> bool:
        return self._execute("DELETE FROM scans WHERE id=?", (scan_id,)).rowcount > 0

    def export(self, scan_id: str, fmt: Literal["xml", "json"]) -> tuple[bytes, str] | None:
        record = self.get(scan_id)
        if record is None:
            return None
        if fmt == "xml":
            return (self.get_raw_xml(scan_id) or "").encode("utf-8"), "application/xml"
        return record.model_dump_json(indent=2).encode("utf-8"), "application/json"

    def compare(self, a: str, b: str) -> ScanDiff:
        rec_a, rec_b = self.get(a), self.get(b)
        if rec_a is None:
            raise KeyError(a)
        if rec_b is None:
            raise KeyError(b)
        before, after = _open_ports(rec_a.result), _open_ports(rec_b.result)
        added = sorted(after.keys() - before.keys())
        removed = sorted(before.keys() - after.keys())
        per_host: dict[str, HostDiff] = {}
        for addr in sorted(before.keys() | after.keys()):
            pa, pb = before.get(addr, {}), after.get(addr, {})
            changed = [
                ServiceChange(port=k, before=_service(pa[k]), after=_service(pb[k]))
                for k in sorted(pa.keys() & pb.keys(), key=_port_key)
                if _service(pa[k]) != _service(pb[k])
            ]
            diff = HostDiff(
                ports_opened=sorted(pb.keys() - pa.keys(), key=_port_key),
                ports_closed=sorted(pa.keys() - pb.keys(), key=_port_key),
                services_changed=changed,
            )
            if diff.ports_opened or diff.ports_closed or diff.services_changed:
                per_host[addr] = diff
        return ScanDiff(a=a, b=b, hosts_added=added, hosts_removed=removed, per_host=per_host)
