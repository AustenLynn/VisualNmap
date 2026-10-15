"""Pydantic models shared by the command builder, parser, history and API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ScanStatus = Literal["running", "completed", "failed", "cancelled"]


class OptionValue(BaseModel):
    id: str
    value: str | int | None = None


class ScanRequest(BaseModel):
    target: str
    profile_id: str | None = None
    options: list[OptionValue] = Field(default_factory=list)


class ExplainedPart(BaseModel):
    token: str
    text: str
    kind: Literal["option", "plumbing", "target"]


class BuiltCommand(BaseModel):
    argv: list[str]
    parts: list[ExplainedPart]
    warnings: list[str]


class OsMatch(BaseModel):
    name: str
    accuracy: int


class Port(BaseModel):
    port: int
    protocol: str
    state: str
    reason: str | None = None
    service: str | None = None
    product: str | None = None
    version: str | None = None
    extrainfo: str | None = None
    note: str | None = None


class Host(BaseModel):
    address: str
    hostname: str | None = None
    mac: str | None = None
    vendor: str | None = None
    status: str
    reason: str | None = None
    os_matches: list[OsMatch] = Field(default_factory=list)
    ports: list[Port] = Field(default_factory=list)


class ScanStats(BaseModel):
    up: int = 0
    down: int = 0
    total: int = 0
    elapsed_s: float | None = None


class ParsedResult(BaseModel):
    hosts: list[Host] = Field(default_factory=list)
    stats: ScanStats = Field(default_factory=ScanStats)
    partial: bool = False


class Hint(BaseModel):
    code: str
    message: str
    action: Literal["retry_with_pn"] | None = None


class ScanSummary(BaseModel):
    id: str
    created_at: str
    finished_at: str | None = None
    target: str
    profile_id: str | None = None
    status: ScanStatus
    hosts_up: int = 0
    open_ports: int = 0


class ScanRecord(ScanSummary):
    request: ScanRequest
    argv: list[str]
    result: ParsedResult | None = None
    stderr_tail: str = ""
    hints: list[Hint] = Field(default_factory=list)


class ServiceChange(BaseModel):
    port: str  # e.g. "22/tcp"
    before: str
    after: str


class HostDiff(BaseModel):
    ports_opened: list[str] = Field(default_factory=list)
    ports_closed: list[str] = Field(default_factory=list)
    services_changed: list[ServiceChange] = Field(default_factory=list)


class ScanDiff(BaseModel):
    a: str
    b: str
    hosts_added: list[str]
    hosts_removed: list[str]
    per_host: dict[str, HostDiff]


class StatusInfo(BaseModel):
    is_root: bool
    can_raw: bool
    nmap_found: bool
    nmap_version: str | None
    in_container: bool
    active_scan_id: str | None
