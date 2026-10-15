# VisualNmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build VisualNmap, a localhost web dashboard that builds, explains, runs, and visualizes Nmap scans, with a guided mode for learners and a builder mode for experienced users.

**Architecture:** A FastAPI backend (runs as root through `sudo` or inside Docker) turns a structured `ScanRequest` into an allowlisted nmap argv, runs nmap without a shell, streams progress over a WebSocket, parses the XML into JSON, and stores history in SQLite. All explanation text lives in YAML catalog files. A React + TypeScript + Vite frontend is built once into `frontend/dist`, and FastAPI serves it as static files.

**Tech Stack:** Python ≥3.11, FastAPI, Uvicorn, Pydantic v2, PyYAML, defusedxml, pytest + pytest-asyncio + httpx. React 18, TypeScript, Vite 5, react-router-dom 6, Vitest, React Testing Library, jsdom. Docker multi-stage (node:20-alpine → python:3.12-slim).

**Spec:** `docs/superpowers/specs/2026-10-14-visualnmap-design.md` (read it before starting any task).

**Verified while writing (2026-10-14):** every code block in this plan was extracted into a scratch checkout and run on the dev machine. Results: backend 151 passed + 2 e2e passed against real Nmap 7.99; frontend 47 passed, `tsc` clean, `vite build` OK; `scripts/docker-smoke.sh` printed `SMOKE TEST PASSED`; `./run.sh --no-sudo` served the app. If a step's output differs from what is written here, suspect the environment first.

## Global Constraints

- Python `requires-python = ">=3.11"`; Node ≥ 18 for building the frontend only. Node never runs as root.
- Server binds `127.0.0.1:8765` by default; overridable only via `VISUALNMAP_HOST` / `VISUALNMAP_PORT`. Data dir `VISUALNMAP_DATA` (default `./data`).
- nmap is always started with `asyncio.create_subprocess_exec(*argv)`, never through a shell, never `shell=True`.
- Only options defined in `backend/visualnmap/catalog/options.yaml` can reach nmap. No free-text argument field, no `--script`, no `-iL`, no `-o*` other than the fixed `-oX -`.
- Always-appended plumbing (never user-controlled): `-v` (unless the user picked `verbose`), `--stats-every 2s`, `-oX -`; plus `-6` when targets are IPv6 and `--privileged` when `can_raw and not is_root`.
- Target: 1–16 space-separated tokens; IPv4, IPv4 CIDR `/8`–`/32`, IPv4 last-octet range `a.b.c.d-e`, IPv6 address, or RFC 1123 hostname; no token may start with `-`.
- Root-only options (`requires_root: true`, shown 🔒) are allowed only when `Environment.can_raw` is true.
- One active scan at a time. Event replay buffer max 5,000 events per scan.
- `cancel`: SIGTERM, wait 5 s, then SIGKILL; status `cancelled`.
- POST/DELETE endpoints and the WebSocket reject a request whose `Origin` header is present and is not `http://<Host header>`.
- XML parsed only with `defusedxml`.
- Docker publishes `127.0.0.1:8765:8765` only, `cap_add: [NET_RAW, NET_ADMIN]`, never `privileged: true`.
- No em dashes in Docker/compose resource names or descriptions.
- Every commit message ends with the trailer line: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (shown in each commit step).
- Run backend commands from `backend/` with `.venv/bin/...`; frontend commands from `frontend/`.
- Create the backend venv with `uv venv .venv` + `uv pip install -p .venv ...` (system Python on the dev machine lacks `ensurepip`); `run.sh` must try `python3 -m venv` first and fall back to `uv venv`.

## Review Focus

1. **IPv6 targets.** nmap ignores IPv6 targets unless `-6` is passed, and refuses to mix v4 and v6. Expected: an IPv6 target gets `-6` added automatically, and mixing v4 and v6 is rejected with a clear message. Pinned in Task 3 (`test_ipv6_target_adds_dash_6`, `test_mixed_ip_families_rejected`).
2. **Duplicate flags from profile + user options.** For example, the `everything` profile (`-A` → `-sV -O --traceroute`) plus the user ticking `service_version`. Expected: `-sV` appears once in argv. Pinned in Task 3 (`test_duplicate_tokens_emitted_once`).
3. **Non-UTF-8 bytes in nmap output** (odd hostnames or banners). Expected: the scan still completes and bad bytes are replaced, not crashed on. Pinned in Task 7 (`test_non_utf8_output_is_replaced`).
4. **Opening a finished scan's live stream after an app restart** (the runner has no memory of it). Expected: the WebSocket sends a single `done` event with the stored status and closes. Pinned in Task 8 (`test_ws_for_finished_scan_after_restart_sends_done`).
5. **Cancel races:** cancelling a scan that already finished, or cancelling twice. Expected: 409 for a scan that isn't running, and a second cancel is harmless. Pinned in Task 7 (`test_cancel_twice_is_harmless`) and Task 8 (`test_cancel_finished_scan_409`).

## File Structure

```
backend/
  pyproject.toml                    package + deps + pytest config
  visualnmap/
    __init__.py                     version string
    __main__.py                     `python -m visualnmap`: read settings, run uvicorn
    environment.py                  Environment dataclass + detect_environment()
    models.py                       Pydantic models shared by command/parser/history/api
    catalog/__init__.py             Catalog models + load_catalog()
    catalog/options.yaml            allowlisted nmap options with explanations
    catalog/profiles.yaml           guided-mode presets
    catalog/ports.yaml              common port notes + port-state explanations
    command.py                      build_command(): ScanRequest → BuiltCommand (validation + argv)
    targets.py                      parse_targets(): target string → validated tokens + address count
    parser.py                       parse_nmap_xml(): XML → ParsedResult (tolerates truncation)
    errors.py                       hints_for(): stderr + result → list[Hint]
    history.py                      History: SQLite persistence, export, compare
    runner.py                       ScanRunner: subprocess, streaming events, cancel
    api.py                          create_app(): REST + WebSocket + static frontend
  tests/
    conftest.py                     shared fixtures (catalog, envs)
    fixtures/*.xml                  nmap XML samples
    fixtures/fake_nmap.py           fake nmap executable for runner/api tests
    test_*.py
frontend/
  package.json, tsconfig.json, vite.config.ts, index.html
  src/
    main.tsx, App.tsx, styles.css
    api/types.ts                    TS mirrors of backend models
    api/client.ts                   fetch wrappers + openScanStream()
    hooks/useAppData.tsx            context: status + catalog loaded once
    hooks/usePreview.ts             debounced command preview
    components/                     CommandBar, OptionInfo, StatusBanner, TargetInput, OutputPane,
                                    ProgressBar, HostList, PortTable, HintPanel, StatesHelp, CompareView
    pages/                          Home, Guided, Builder, Scan, History
    test/setup.ts, test/fixtures.ts
run.sh                              primary launcher
Dockerfile, docker-compose.yml, .dockerignore
scripts/docker-smoke.sh
```

---

### Task 1: Backend package skeleton and environment detection

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/visualnmap/__init__.py`
- Create: `backend/visualnmap/environment.py`
- Create: `backend/tests/__init__.py` (empty)
- Test: `backend/tests/test_environment.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `@dataclass(frozen=True) class Environment: is_root: bool; can_raw: bool; nmap_path: str | None; nmap_version: str | None; in_container: bool`
  - `def detect_environment() -> Environment`
  - `def has_cap_net_raw(path: str) -> bool`
  - `def parse_nmap_version(text: str) -> str | None`

- [ ] **Step 1: Create the package config**

`backend/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "visualnmap"
version = "0.1.0"
description = "Visual, beginner-friendly local web dashboard for Nmap"
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "pydantic>=2.7",
  "PyYAML>=6.0",
  "defusedxml>=0.7",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "httpx>=0.27"]

[tool.setuptools.packages.find]
include = ["visualnmap*"]

[tool.setuptools.package-data]
visualnmap = ["catalog/*.yaml"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = ["e2e: runs the real nmap binary (set VISUALNMAP_E2E=1)"]
```

`backend/visualnmap/__init__.py`:

```python
__version__ = "0.1.0"
```

Create an empty `backend/tests/__init__.py`.

Then create the venv:

This machine's system Python has no `ensurepip`, so use `uv` (installed at `~/.local/bin/uv`):

Run: `cd backend && uv venv .venv && uv pip install -p .venv -e '.[dev]'`
Expected: ends with a line containing `+ visualnmap==0.1.0`.
(On machines without uv: `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`.)

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_environment.py`:

```python
import os

import pytest

from visualnmap import environment
from visualnmap.environment import Environment, detect_environment, has_cap_net_raw, parse_nmap_version

# Real xattr captured from Kali's /usr/lib/nmap/nmap (cap_net_bind_service,cap_net_admin,cap_net_raw=eip)
KALI_CAPS = bytes.fromhex("0100000200340000003400000000000000000000")
# Same layout with only cap_net_bind_service (bit 10) set
NO_RAW_CAPS = bytes.fromhex("0100000200040000000400000000000000000000")


def test_parse_nmap_version():
    assert parse_nmap_version("Nmap version 7.99 ( https://nmap.org )\nPlatform: x86_64") == "7.99"
    assert parse_nmap_version("garbage") is None


def test_has_cap_net_raw_true_for_kali_caps(monkeypatch):
    monkeypatch.setattr(os, "getxattr", lambda path, name: KALI_CAPS)
    assert has_cap_net_raw("/whatever") is True


def test_has_cap_net_raw_false_without_raw_bit(monkeypatch):
    monkeypatch.setattr(os, "getxattr", lambda path, name: NO_RAW_CAPS)
    assert has_cap_net_raw("/whatever") is False


def test_has_cap_net_raw_false_when_no_xattr(tmp_path):
    f = tmp_path / "plain"
    f.write_text("x")
    assert has_cap_net_raw(str(f)) is False


def test_detect_environment_without_nmap(monkeypatch):
    monkeypatch.setattr(environment.shutil, "which", lambda name: None)
    monkeypatch.setattr(environment.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(environment, "KALI_REAL_NMAP", "/nonexistent/nmap")
    monkeypatch.delenv("VISUALNMAP_IN_CONTAINER", raising=False)
    env = detect_environment()
    assert env.nmap_path is None
    assert env.nmap_version is None
    assert env.is_root is False
    assert env.can_raw is False


def test_detect_environment_root_implies_can_raw(monkeypatch):
    monkeypatch.setattr(environment.shutil, "which", lambda name: None)
    monkeypatch.setattr(environment.os, "geteuid", lambda: 0)
    env = detect_environment()
    assert env.is_root is True and env.can_raw is True


def test_detect_environment_container_flag(monkeypatch):
    monkeypatch.setattr(environment.shutil, "which", lambda name: None)
    monkeypatch.setenv("VISUALNMAP_IN_CONTAINER", "1")
    assert detect_environment().in_container is True


def test_environment_is_frozen():
    env = Environment(is_root=False, can_raw=False, nmap_path=None, nmap_version=None, in_container=False)
    with pytest.raises(Exception):
        env.is_root = True  # type: ignore[misc]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_environment.py -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'visualnmap.environment'`.

- [ ] **Step 4: Implement `environment.py`**

`backend/visualnmap/environment.py`:

```python
"""Detects what the scanner is allowed to do on this machine."""
from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
from dataclasses import dataclass

CAP_NET_RAW = 13
# Kali/Debian ship /usr/bin/nmap as a shell wrapper; the real binary (which carries the
# file capabilities) lives here.
KALI_REAL_NMAP = "/usr/lib/nmap/nmap"


@dataclass(frozen=True)
class Environment:
    is_root: bool
    can_raw: bool
    nmap_path: str | None
    nmap_version: str | None
    in_container: bool


def has_cap_net_raw(path: str) -> bool:
    """True if the file's permitted capability set includes CAP_NET_RAW."""
    try:
        data = os.getxattr(path, "security.capability")
    except (OSError, AttributeError):
        return False
    if len(data) < 8:
        return False
    _magic, permitted = struct.unpack("<II", data[:8])
    return bool((permitted >> CAP_NET_RAW) & 1)


def parse_nmap_version(text: str) -> str | None:
    match = re.search(r"Nmap version (\S+)", text)
    return match.group(1) if match else None


def _nmap_version(nmap_path: str) -> str | None:
    try:
        result = subprocess.run([nmap_path, "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_nmap_version(result.stdout)


def detect_environment() -> Environment:
    is_root = os.geteuid() == 0
    nmap_path = shutil.which("nmap")
    nmap_version = _nmap_version(nmap_path) if nmap_path else None
    candidates = [p for p in (nmap_path and os.path.realpath(nmap_path), KALI_REAL_NMAP) if p and os.path.exists(p)]
    can_raw = is_root or any(has_cap_net_raw(p) for p in candidates)
    in_container = os.path.exists("/.dockerenv") or os.environ.get("VISUALNMAP_IN_CONTAINER") == "1"
    return Environment(
        is_root=is_root,
        can_raw=can_raw,
        nmap_path=nmap_path,
        nmap_version=nmap_version,
        in_container=in_container,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_environment.py -v`
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/visualnmap/__init__.py backend/visualnmap/environment.py backend/tests/__init__.py backend/tests/test_environment.py
git commit -m "feat(backend): package skeleton and environment detection

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 2: Explanation catalog (YAML + loader)

**Files:**
- Create: `backend/visualnmap/catalog/__init__.py`
- Create: `backend/visualnmap/catalog/options.yaml`
- Create: `backend/visualnmap/catalog/profiles.yaml`
- Create: `backend/visualnmap/catalog/ports.yaml`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_catalog.py`

**Interfaces:**
- Consumes: nothing.
- Produces (all in `visualnmap.catalog`):
  - `class ValueSpec(BaseModel): type: Literal["int","ports","duration"]; min: int | None; max: int | None; default: str | int; placeholder: str | None`
  - `class OptionSpec(BaseModel): id, flag, group, label, summary, details, when_to_use: str; requires_root: bool; noise: Literal["low","medium","high"]; speed_impact: Literal["none","slower","much_slower"]; example: str; render: Literal["flag","separate","attached"] = "flag"; value: ValueSpec | None = None; expands_to: list[str] | None = None; conflicts_with: list[str] = []`
  - `class GroupSpec(BaseModel): id: str; label: str; description: str`
  - `class ProfileOption(BaseModel): id: str; value: str | int | None = None`
  - `class ProfileSpec(BaseModel): id, title, question, explanation, typical_duration: str; options: list[ProfileOption]; requires_root: bool = False` (`requires_root` is computed by the loader)
  - `class PortNote(BaseModel): service: str; note: str`
  - `class Catalog(BaseModel): groups: list[GroupSpec]; options: dict[str, OptionSpec]; profiles: dict[str, ProfileSpec]; ports: dict[int, PortNote]; states: dict[str, str]`
  - `class CatalogError(Exception)`
  - `def load_catalog(directory: Path | None = None) -> Catalog` (default directory is the package's `catalog/` folder)
  - pytest fixture `catalog` (session scope) in `tests/conftest.py`

- [ ] **Step 1: Write `options.yaml`**

`backend/visualnmap/catalog/options.yaml`:

```yaml
# Every nmap option VisualNmap is allowed to use. Nothing outside this file can reach nmap.
# render: flag = just the flag(s); separate = flag then value as two args; attached = flag+value as one arg.
groups:
  - id: discovery
    label: Host discovery
    description: How nmap decides which addresses are alive before it scans their ports.
  - id: technique
    label: Scan technique
    description: How each port is probed. Pick at most one TCP technique (UDP can be added on top).
  - id: ports
    label: Ports
    description: Which ports get checked. With nothing chosen, nmap checks the 1,000 most common ports.
  - id: detection
    label: Service and OS detection
    description: Identifying the software behind open ports and the operating system of the host.
  - id: timing
    label: Timing
    description: Trade speed against accuracy and stealth.
  - id: output
    label: Output detail
    description: Extra detail shown in the results.

options:
  # ---------------- discovery ----------------
  - id: ping_only
    flag: "-sn"
    group: discovery
    label: Ping scan only (no port scan)
    summary: Finds which devices are online without checking any ports.
    details: >-
      Nmap sends a few quick probes to each address to see if something answers, then stops.
      It is the fastest way to list the devices on a network. As root on a local network it uses
      ARP, which also reveals each device's MAC address and manufacturer.
    when_to_use: To get an inventory of devices on your network before deciding what to scan in depth.
    requires_root: false
    noise: low
    speed_impact: none
    example: "nmap -sn 192.168.1.0/24"
    conflicts_with: [syn_scan, connect_scan, udp_scan, ack_scan, fin_scan, null_scan, xmas_scan, ports, fast, top_ports, all_ports, service_version, version_intensity, os_detect, os_guess, aggressive, open_only]
  - id: skip_ping
    flag: "-Pn"
    group: discovery
    label: Skip host discovery (treat all as online)
    summary: Scans every address even if it doesn't answer pings.
    details: >-
      Normally nmap only port-scans hosts that answered its discovery probes. Many devices,
      especially Windows PCs and firewalled servers, ignore pings, so nmap wrongly thinks they are
      down. -Pn skips that check. On a big range of empty addresses this is much slower.
    when_to_use: When a scan says "0 hosts up" or "Host seems down" but you know the device is there.
    requires_root: false
    noise: low
    speed_impact: slower
    example: "nmap -Pn 192.168.1.20"
  - id: syn_ping
    flag: "-PS"
    group: discovery
    label: TCP SYN ping on ports
    summary: Checks if a host is alive by knocking on the given TCP ports.
    details: >-
      Sends a TCP connection request to each listed port. Any reply (accept or refuse) proves the
      host is up. Useful when ICMP ping is blocked but common ports like 22, 80 or 443 are reachable.
    when_to_use: When ordinary pings are blocked by a firewall.
    requires_root: false
    noise: low
    speed_impact: none
    example: "nmap -PS22,80,443 192.168.1.0/24"
    render: attached
    value: { type: ports, default: "22,80,443", placeholder: "22,80,443" }
  - id: ack_ping
    flag: "-PA"
    group: discovery
    label: TCP ACK ping on ports
    summary: Checks if a host is alive by sending TCP ACK packets to the given ports.
    details: >-
      Sends a packet that looks like part of an existing connection. Hosts reply with a reset,
      which proves they are up. Some simple firewalls that block SYN pings let these through.
    when_to_use: Combined with SYN ping to get past stateless firewalls.
    requires_root: true
    noise: low
    speed_impact: none
    example: "nmap -PA80,443 192.168.1.0/24"
    render: attached
    value: { type: ports, default: "80,443", placeholder: "80,443" }
  - id: icmp_ping
    flag: "-PE"
    group: discovery
    label: ICMP echo ping
    summary: Uses the classic "ping" packet to see if hosts are alive.
    details: >-
      Sends an ICMP echo request, the same thing the ping command sends. Fast and simple, but many
      firewalls drop it, so combine it with a TCP ping for better coverage.
    when_to_use: On internal networks where ping is allowed.
    requires_root: true
    noise: low
    speed_impact: none
    example: "nmap -PE -sn 10.0.0.0/24"
  - id: no_dns
    flag: "-n"
    group: discovery
    label: Don't look up host names
    summary: Skips reverse-DNS lookups, so results show only IP addresses.
    details: >-
      By default nmap asks DNS for the name of every host it finds. On large ranges or slow DNS
      servers that adds a lot of time. -n turns it off.
    when_to_use: For faster scans of big ranges, or when DNS lookups would leak that you are scanning.
    requires_root: false
    noise: low
    speed_impact: none
    example: "nmap -n -sn 10.0.0.0/16"

  # ---------------- technique ----------------
  - id: syn_scan
    flag: "-sS"
    group: technique
    label: SYN scan (half-open)
    summary: Fast, quiet TCP scan that never completes a connection.
    details: >-
      Sends the first packet of a TCP handshake. An open port answers "yes" (SYN/ACK) and nmap hangs
      up before the connection completes, so many applications never log it. This is nmap's default
      when run as root.
    when_to_use: The standard choice for TCP scanning when you have root.
    requires_root: true
    noise: medium
    speed_impact: none
    example: "sudo nmap -sS 192.168.1.10"
    conflicts_with: [connect_scan, ack_scan, fin_scan, null_scan, xmas_scan]
  - id: connect_scan
    flag: "-sT"
    group: technique
    label: TCP connect scan
    summary: Opens a full TCP connection to each port. Works without root.
    details: >-
      Uses the operating system's normal connect() call, exactly like a browser or SSH client would.
      Reliable and needs no special rights, but slower than SYN scan and more likely to show up in
      the target's logs. This is nmap's default without root.
    when_to_use: When you don't have root, or a SYN scan gives confusing results.
    requires_root: false
    noise: high
    speed_impact: slower
    example: "nmap -sT 192.168.1.10"
    conflicts_with: [syn_scan, ack_scan, fin_scan, null_scan, xmas_scan]
  - id: udp_scan
    flag: "-sU"
    group: technique
    label: UDP scan
    summary: Checks UDP services such as DNS (53), DHCP (67), SNMP (161).
    details: >-
      UDP has no handshake, so nmap sends a protocol-specific probe and waits. No reply could mean
      open or filtered, and closed ports are rate-limited by most systems, so UDP scans are slow.
      Keep the port list small. Can be combined with one TCP technique.
    when_to_use: When you need to find UDP services, which TCP scans completely miss.
    requires_root: true
    noise: medium
    speed_impact: much_slower
    example: "sudo nmap -sU --top-ports 20 192.168.1.1"
  - id: ack_scan
    flag: "-sA"
    group: technique
    label: ACK scan (firewall mapping)
    summary: Shows which ports a firewall filters, not which are open.
    details: >-
      Sends TCP ACK packets. Results are "unfiltered" (the packet got through) or "filtered"
      (something blocked it). It never says "open". Used to understand firewall rules.
    when_to_use: To map which ports a firewall lets through.
    requires_root: true
    noise: medium
    speed_impact: none
    example: "sudo nmap -sA 192.168.1.1"
    conflicts_with: [syn_scan, connect_scan, fin_scan, null_scan, xmas_scan]
  - id: fin_scan
    flag: "-sF"
    group: technique
    label: FIN scan
    summary: Sends a lone FIN packet; can slip past some simple firewalls.
    details: >-
      A closed port answers with a reset, an open port stays silent. Windows answers reset to
      everything, so it is unreliable against Windows hosts.
    when_to_use: "Advanced: testing simple stateless firewalls on Unix-like targets."
    requires_root: true
    noise: medium
    speed_impact: none
    example: "sudo nmap -sF 192.168.1.10"
    conflicts_with: [syn_scan, connect_scan, ack_scan, null_scan, xmas_scan]
  - id: null_scan
    flag: "-sN"
    group: technique
    label: Null scan
    summary: Sends a TCP packet with no flags set.
    details: Same idea and limitations as the FIN scan, with an empty flag set.
    when_to_use: "Advanced: firewall testing on Unix-like targets."
    requires_root: true
    noise: medium
    speed_impact: none
    example: "sudo nmap -sN 192.168.1.10"
    conflicts_with: [syn_scan, connect_scan, ack_scan, fin_scan, xmas_scan]
  - id: xmas_scan
    flag: "-sX"
    group: technique
    label: Xmas scan
    summary: Sends a packet with FIN, PSH and URG set ("lit up like a Christmas tree").
    details: Same idea and limitations as the FIN scan, with an unusual flag combination.
    when_to_use: "Advanced: firewall testing on Unix-like targets."
    requires_root: true
    noise: medium
    speed_impact: none
    example: "sudo nmap -sX 192.168.1.10"
    conflicts_with: [syn_scan, connect_scan, ack_scan, fin_scan, null_scan]

  # ---------------- ports ----------------
  - id: ports
    flag: "-p"
    group: ports
    label: Specific ports
    summary: Scan exactly the ports you list.
    details: >-
      Comma-separated ports and ranges, for example 22,80,443 or 1-1024 or 22,8000-8100.
      Each port must be between 1 and 65535.
    when_to_use: When you know which services you care about.
    requires_root: false
    noise: low
    speed_impact: none
    example: "nmap -p 22,80,443 192.168.1.10"
    render: separate
    value: { type: ports, default: "22,80,443", placeholder: "22,80,443 or 1-1024" }
    conflicts_with: [fast, top_ports, all_ports]
  - id: fast
    flag: "-F"
    group: ports
    label: Fast (top 100 ports)
    summary: Checks only the 100 most common ports.
    details: About ten times faster than the default 1,000 ports, and still finds most everyday services.
    when_to_use: For a quick first look.
    requires_root: false
    noise: low
    speed_impact: none
    example: "nmap -F 192.168.1.10"
    conflicts_with: [ports, top_ports, all_ports]
  - id: top_ports
    flag: "--top-ports"
    group: ports
    label: Top N most common ports
    summary: Checks the N ports most often found open on the internet.
    details: Nmap ranks ports by how often they are open in real-world scans. Pick how many to check.
    when_to_use: To balance speed and coverage, e.g. 20 for UDP or 1000 for TCP.
    requires_root: false
    noise: low
    speed_impact: none
    example: "nmap --top-ports 200 192.168.1.10"
    render: separate
    value: { type: int, min: 1, max: 65535, default: 200 }
    conflicts_with: [ports, fast, all_ports]
  - id: all_ports
    flag: "-p-"
    group: ports
    label: All 65,535 ports
    summary: Checks every TCP port. Thorough but slow.
    details: >-
      Services sometimes hide on unusual high ports (for example a web admin page on 8443 or a
      backdoor on 31337). Scanning all ports finds them, at the cost of time.
    when_to_use: When you need to be sure nothing is missed on one or a few hosts.
    requires_root: false
    noise: high
    speed_impact: much_slower
    example: "nmap -p- 192.168.1.10"
    conflicts_with: [ports, fast, top_ports]

  # ---------------- detection ----------------
  - id: service_version
    flag: "-sV"
    group: detection
    label: Detect service versions
    summary: Asks each open port what software is running and which version.
    details: >-
      Nmap sends probes to open ports and matches the replies against a database of thousands of
      services. Slower, but tells you e.g. "OpenSSH 8.9" instead of just "ssh".
    when_to_use: When you need to know what software is behind an open port, e.g. to check for outdated versions.
    requires_root: false
    noise: medium
    speed_impact: slower
    example: "nmap -sV 192.168.1.10"
  - id: version_intensity
    flag: "--version-intensity"
    group: detection
    label: Version detection intensity (0-9)
    summary: How many probes to try when identifying services. Higher is slower but more accurate.
    details: 0 tries only the most likely probes, 9 tries all of them. The default is 7. Only matters together with version detection.
    when_to_use: Lower it to speed up -sV, raise it when services come back unidentified.
    requires_root: false
    noise: medium
    speed_impact: slower
    example: "nmap -sV --version-intensity 9 192.168.1.10"
    render: separate
    value: { type: int, min: 0, max: 9, default: 7 }
  - id: os_detect
    flag: "-O"
    group: detection
    label: Detect operating system
    summary: Guesses the OS from how the host answers unusual network packets.
    details: >-
      Every operating system's network stack has small quirks. Nmap sends a series of special probes
      and compares the answers with thousands of known fingerprints. Works best when the host has
      at least one open and one closed port.
    when_to_use: To find out whether a device is Windows, Linux, a router, a printer, and so on.
    requires_root: true
    noise: medium
    speed_impact: slower
    example: "sudo nmap -O 192.168.1.10"
  - id: os_guess
    flag: "--osscan-guess"
    group: detection
    label: Guess OS aggressively
    summary: Shows the closest OS matches even when nmap is not sure.
    details: Without this, nmap only reports OS matches it is confident about. With it, you get best guesses with a confidence percentage.
    when_to_use: Together with OS detection when it returns no result.
    requires_root: true
    noise: low
    speed_impact: none
    example: "sudo nmap -O --osscan-guess 192.168.1.10"
  - id: aggressive
    flag: "-A"
    group: detection
    label: Everything (version + OS + traceroute)
    summary: Turns on service versions, OS detection and traceroute together.
    details: >-
      In real nmap, -A also runs the default NSE scripts (-sC). VisualNmap v1 does not run scripts,
      so here -A means -sV -O --traceroute. Traceroute shows the network hops between you and the host.
    when_to_use: When you want as much information as possible about a few hosts and time is not a concern.
    requires_root: true
    noise: high
    speed_impact: much_slower
    example: "sudo nmap -sV -O --traceroute 192.168.1.10"
    expands_to: ["-sV", "-O", "--traceroute"]

  # ---------------- timing ----------------
  - id: timing
    flag: "-T"
    group: timing
    label: Timing template (0-5)
    summary: "0 paranoid, 1 sneaky, 2 polite, 3 normal, 4 aggressive, 5 insane."
    details: >-
      Controls how fast nmap sends probes and how long it waits. 0 and 1 are extremely slow and
      meant to avoid intrusion detection. 2 is gentle on fragile devices. 3 is the default.
      4 is a good choice on modern networks you own. 5 may miss results on slow links.
    when_to_use: Use 4 on your own fast network, 2 when scanning old or fragile devices.
    requires_root: false
    noise: low
    speed_impact: none
    example: "nmap -T4 192.168.1.10"
    render: attached
    value: { type: int, min: 0, max: 5, default: 3 }
  - id: max_retries
    flag: "--max-retries"
    group: timing
    label: Max retries per port
    summary: How many times nmap re-sends a probe that got no answer.
    details: Lower values are faster but may report open ports as filtered on lossy networks. Nmap's default is up to 10.
    when_to_use: Lower it (e.g. 1) to speed up scans of heavily filtered hosts.
    requires_root: false
    noise: low
    speed_impact: none
    example: "nmap --max-retries 1 192.168.1.10"
    render: separate
    value: { type: int, min: 0, max: 10, default: 2 }
  - id: host_timeout
    flag: "--host-timeout"
    group: timing
    label: Give up on a host after
    summary: Stops scanning a host that takes longer than this.
    details: A number followed by ms, s, m or h, for example 30s, 10m or 1h. Results for a host that times out are dropped.
    when_to_use: On big ranges, so one slow host doesn't hold up the whole scan.
    requires_root: false
    noise: low
    speed_impact: none
    example: "nmap --host-timeout 10m 10.0.0.0/24"
    render: separate
    value: { type: duration, default: "30m", placeholder: "30s, 10m, 1h" }

  # ---------------- output ----------------
  - id: reason
    flag: "--reason"
    group: output
    label: Show the reason for each state
    summary: Explains why each port got its state (e.g. "syn-ack", "conn-refused", "no-response").
    details: Great for learning. Shows the exact kind of reply nmap received for each port.
    when_to_use: When you want to understand why a port is open, closed or filtered.
    requires_root: false
    noise: low
    speed_impact: none
    example: "nmap --reason 192.168.1.10"
  - id: open_only
    flag: "--open"
    group: output
    label: Only show open ports
    summary: Hides closed and filtered ports from the results.
    details: Makes results shorter. Hosts with no open ports are left out too.
    when_to_use: When scanning many hosts and you only care about what is reachable.
    requires_root: false
    noise: low
    speed_impact: none
    example: "nmap --open 192.168.1.0/24"
  - id: verbose
    flag: "-v"
    group: output
    label: Verbose
    summary: Makes nmap report more about what it is doing.
    details: VisualNmap always adds -v behind the scenes so it can show live progress. Ticking it here just makes that visible in the command.
    when_to_use: Always on in VisualNmap; shown for completeness.
    requires_root: false
    noise: low
    speed_impact: none
    example: "nmap -v 192.168.1.10"
```

- [ ] **Step 2: Write `profiles.yaml`**

`backend/visualnmap/catalog/profiles.yaml`:

```yaml
# Guided-mode presets. Option ids must exist in options.yaml.
profiles:
  - id: find_devices
    title: Find devices
    question: Which devices are on my network?
    explanation: >-
      Asks every address in the range "are you there?" without checking any ports. The result is a
      list of devices that are online. As root on a local network it also shows MAC addresses and
      manufacturers.
    typical_duration: 10-30 seconds for a home network (/24)
    options: [{ id: ping_only }]
  - id: quick_ports
    title: Quick port check
    question: What's open on a machine? (fast)
    explanation: Checks the 100 most common ports at a brisk pace. A good first look at any device.
    typical_duration: a few seconds per host
    options: [{ id: fast }, { id: timing, value: 4 }]
  - id: full_ports
    title: Full port check
    question: What's open on a machine? (thorough)
    explanation: Checks all 65,535 TCP ports so nothing hiding on an unusual port is missed.
    typical_duration: 1-10 minutes per host
    options: [{ id: all_ports }, { id: timing, value: 4 }]
  - id: services
    title: Identify services
    question: What software is running?
    explanation: Finds open ports among the top 100, then asks each one what program and version it runs.
    typical_duration: 10 seconds to 2 minutes per host
    options: [{ id: service_version }, { id: fast }, { id: timing, value: 4 }]
  - id: os_detect
    title: Detect operating system
    question: What operating system is it?
    explanation: Guesses the OS from tiny differences in how the device answers special network packets.
    typical_duration: 10-30 seconds per host
    options: [{ id: os_detect }, { id: os_guess }, { id: fast }]
  - id: stealth
    title: Quiet scan
    question: Scan quietly
    explanation: >-
      A half-open SYN scan sent slowly. Connections are never completed, so applications rarely
      log it, and the slow pace is less likely to trigger alarms.
    typical_duration: 1-3 minutes per host
    options: [{ id: syn_scan }, { id: timing, value: 2 }, { id: fast }]
  - id: udp_common
    title: Common UDP services
    question: What UDP services are running?
    explanation: Checks the 20 most common UDP ports (DNS, DHCP, SNMP, NTP...). UDP is slow by nature.
    typical_duration: 1-5 minutes per host
    options: [{ id: udp_scan }, { id: top_ports, value: 20 }]
  - id: everything
    title: Everything
    question: Tell me everything (slow)
    explanation: Service versions, OS detection and traceroute on the top 100 ports. The most information, the most time.
    typical_duration: 30 seconds to 3 minutes per host
    options: [{ id: aggressive }, { id: timing, value: 4 }, { id: fast }]
```

- [ ] **Step 3: Write `ports.yaml`**

`backend/visualnmap/catalog/ports.yaml`:

```yaml
# Plain-language notes for common ports (keyed by port number) and port states.
ports:
  20: { service: ftp-data, note: "FTP file transfer data channel. FTP sends passwords unencrypted." }
  21: { service: ftp, note: "FTP file transfer. Sends passwords unencrypted; prefer SFTP. Check for anonymous login." }
  22: { service: ssh, note: "Remote command-line access (SSH). Should be locked down with keys; often a target for password guessing." }
  23: { service: telnet, note: "Old unencrypted remote login. Should almost never be open; common on cheap IoT devices." }
  25: { service: smtp, note: "Email sending between mail servers." }
  53: { service: domain, note: "DNS: turns names into IP addresses. Normal on routers and DNS servers." }
  67: { service: dhcps, note: "DHCP server: hands out IP addresses on the network. Normal on routers." }
  68: { service: dhcpc, note: "DHCP client side." }
  69: { service: tftp, note: "Trivial FTP: no passwords at all. Used for network boot and device firmware." }
  80: { service: http, note: "Unencrypted website. Fine for local devices; on the internet, prefer HTTPS (443)." }
  88: { service: kerberos, note: "Kerberos login service. Usually means a Windows domain controller." }
  110: { service: pop3, note: "Old email download protocol, unencrypted." }
  111: { service: rpcbind, note: "Unix RPC directory service (used by NFS). Should not be exposed to the internet." }
  119: { service: nntp, note: "Usenet news." }
  123: { service: ntp, note: "Network time sync. Normal on routers and servers." }
  135: { service: msrpc, note: "Windows RPC. Normal inside Windows networks; never expose to the internet." }
  137: { service: netbios-ns, note: "Old Windows name service." }
  138: { service: netbios-dgm, note: "Old Windows datagram service." }
  139: { service: netbios-ssn, note: "Old Windows file sharing (NetBIOS). Never expose to the internet." }
  143: { service: imap, note: "Email access protocol, unencrypted." }
  161: { service: snmp, note: "Network device management. Default community strings like 'public' can leak a lot of information." }
  162: { service: snmptrap, note: "SNMP alerts sent by devices." }
  389: { service: ldap, note: "Directory service (users, groups). Common on domain controllers." }
  443: { service: https, note: "Encrypted website (HTTPS). The normal port for secure web traffic." }
  445: { service: microsoft-ds, note: "Windows file sharing (SMB). Should never be open to the internet." }
  465: { service: smtps, note: "Encrypted email sending." }
  500: { service: isakmp, note: "VPN (IPsec) key exchange." }
  514: { service: syslog, note: "System log collection." }
  515: { service: printer, note: "Old Unix printing (LPD)." }
  548: { service: afp, note: "Apple file sharing." }
  554: { service: rtsp, note: "Video streaming control; common on IP cameras." }
  587: { service: submission, note: "Email submission from mail clients." }
  631: { service: ipp, note: "Internet Printing Protocol (CUPS). Common on printers and Linux PCs." }
  636: { service: ldaps, note: "Encrypted LDAP." }
  993: { service: imaps, note: "Encrypted IMAP email access." }
  995: { service: pop3s, note: "Encrypted POP3 email download." }
  1194: { service: openvpn, note: "OpenVPN server." }
  1433: { service: ms-sql-s, note: "Microsoft SQL Server database. Should not be exposed to the internet." }
  1521: { service: oracle, note: "Oracle database listener." }
  1723: { service: pptp, note: "Old, weak VPN protocol." }
  1883: { service: mqtt, note: "IoT messaging (MQTT). Often has no authentication." }
  1900: { service: upnp, note: "UPnP device discovery. Routers can be told to open ports through it." }
  2049: { service: nfs, note: "Unix network file sharing." }
  3000: { service: ppp, note: "Often a development web server (Node.js, Grafana)." }
  3306: { service: mysql, note: "MySQL/MariaDB database. Should not be exposed to the internet." }
  3389: { service: ms-wbt-server, note: "Windows Remote Desktop (RDP). A frequent attack target; keep it off the internet." }
  5000: { service: upnp, note: "Often a development web server or a NAS/admin interface." }
  5353: { service: mdns, note: "Multicast DNS (Bonjour/Avahi) for discovering devices on the LAN." }
  5432: { service: postgresql, note: "PostgreSQL database. Should not be exposed to the internet." }
  5900: { service: vnc, note: "VNC remote desktop. Often weakly protected." }
  5985: { service: wsman, note: "Windows Remote Management (WinRM) over HTTP." }
  6379: { service: redis, note: "Redis database. Frequently left without a password." }
  8000: { service: http-alt, note: "Alternative web port, common for development servers and admin pages." }
  8080: { service: http-proxy, note: "Alternative web port: proxies, Tomcat, admin panels." }
  8443: { service: https-alt, note: "Alternative HTTPS port, often an admin interface." }
  8888: { service: sun-answerbook, note: "Often Jupyter notebooks or development web servers." }
  9100: { service: jetdirect, note: "Raw printing to network printers." }
  9200: { service: wap-wsp, note: "Often Elasticsearch, which is frequently left without authentication." }
  11211: { service: memcache, note: "Memcached cache. Should never be exposed to the internet." }
  27017: { service: mongod, note: "MongoDB database. Frequently left without authentication." }
  62078: { service: iphone-sync, note: "Apple iPhone/iPad sync service." }

states:
  open: "A program is accepting connections on this port. Something is listening here; this is usually what you're looking for."
  closed: "The host is reachable but nothing is listening on this port. The door exists but is locked; the host is definitely up."
  filtered: "No answer, or the probe was blocked. Usually a firewall is dropping packets, so nmap can't tell if the port is open."
  unfiltered: "The port is reachable but nmap can't tell if it's open or closed. Only seen with ACK scans (-sA), used to map firewall rules."
  open|filtered: "Nmap can't tell open from filtered. Common with UDP: no reply could mean open or blocked."
  closed|filtered: "Nmap can't tell closed from filtered. Rare; seen with some advanced scan types."
```

- [ ] **Step 4: Write the failing tests**

`backend/tests/conftest.py`:

```python
import pytest

from visualnmap.catalog import load_catalog


@pytest.fixture(scope="session")
def catalog():
    return load_catalog()
```

`backend/tests/test_catalog.py`:

```python
import shutil
from pathlib import Path

import pytest

from visualnmap.catalog import CatalogError, load_catalog

CATALOG_DIR = Path(__file__).resolve().parents[1] / "visualnmap" / "catalog"


def test_every_option_has_full_explanation(catalog):
    assert len(catalog.options) >= 28
    for opt in catalog.options.values():
        for field in ("label", "summary", "details", "when_to_use", "example"):
            assert getattr(opt, field).strip(), f"{opt.id} missing {field}"


def test_option_with_value_renders_with_value(catalog):
    for opt in catalog.options.values():
        if opt.render in ("separate", "attached"):
            assert opt.value is not None, opt.id
        else:
            assert opt.value is None, opt.id


def test_conflicts_reference_known_options(catalog):
    for opt in catalog.options.values():
        for other in opt.conflicts_with:
            assert other in catalog.options, f"{opt.id} conflicts with unknown {other}"


def test_groups_cover_all_options(catalog):
    group_ids = {g.id for g in catalog.groups}
    assert {o.group for o in catalog.options.values()} <= group_ids


def test_profiles_reference_known_options_and_compute_root(catalog):
    assert set(catalog.profiles) == {
        "find_devices", "quick_ports", "full_ports", "services",
        "os_detect", "stealth", "udp_common", "everything",
    }
    for profile in catalog.profiles.values():
        for po in profile.options:
            assert po.id in catalog.options
    assert catalog.profiles["quick_ports"].requires_root is False
    assert catalog.profiles["stealth"].requires_root is True
    assert catalog.profiles["everything"].requires_root is True


def test_ports_and_states(catalog):
    assert len(catalog.ports) >= 55
    assert all(1 <= p <= 65535 for p in catalog.ports)
    assert catalog.ports[22].service == "ssh"
    assert set(catalog.states) == {"open", "closed", "filtered", "unfiltered", "open|filtered", "closed|filtered"}


def _copy_catalog(tmp_path: Path) -> Path:
    dest = tmp_path / "catalog"
    dest.mkdir()
    for name in ("options.yaml", "profiles.yaml", "ports.yaml"):
        shutil.copy(CATALOG_DIR / name, dest / name)
    return dest


def test_unknown_profile_option_is_rejected(tmp_path):
    d = _copy_catalog(tmp_path)
    text = (d / "profiles.yaml").read_text().replace("{ id: ping_only }", "{ id: does_not_exist }")
    (d / "profiles.yaml").write_text(text)
    with pytest.raises(CatalogError, match="does_not_exist"):
        load_catalog(d)


def test_duplicate_option_id_is_rejected(tmp_path):
    d = _copy_catalog(tmp_path)
    text = (d / "options.yaml").read_text().replace("- id: fast\n", "- id: ports\n")
    (d / "options.yaml").write_text(text)
    with pytest.raises(CatalogError, match="duplicate"):
        load_catalog(d)
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_catalog.py -v`
Expected: ERROR with `ImportError: cannot import name 'load_catalog'`.

- [ ] **Step 6: Implement the loader**

`backend/visualnmap/catalog/__init__.py`:

```python
"""Loads and validates the YAML files holding every user-facing explanation."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

CATALOG_DIR = Path(__file__).resolve().parent


class CatalogError(Exception):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ValueSpec(_Strict):
    type: Literal["int", "ports", "duration"]
    min: int | None = None
    max: int | None = None
    default: str | int
    placeholder: str | None = None


class OptionSpec(_Strict):
    id: str
    flag: str
    group: str
    label: str
    summary: str
    details: str
    when_to_use: str
    requires_root: bool
    noise: Literal["low", "medium", "high"]
    speed_impact: Literal["none", "slower", "much_slower"]
    example: str
    render: Literal["flag", "separate", "attached"] = "flag"
    value: ValueSpec | None = None
    expands_to: list[str] | None = None
    conflicts_with: list[str] = []


class GroupSpec(_Strict):
    id: str
    label: str
    description: str


class ProfileOption(_Strict):
    id: str
    value: str | int | None = None


class ProfileSpec(_Strict):
    id: str
    title: str
    question: str
    explanation: str
    typical_duration: str
    options: list[ProfileOption]
    requires_root: bool = False


class PortNote(_Strict):
    service: str
    note: str


class Catalog(_Strict):
    groups: list[GroupSpec]
    options: dict[str, OptionSpec]
    profiles: dict[str, ProfileSpec]
    ports: dict[int, PortNote]
    states: dict[str, str]


def _read(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise CatalogError(f"cannot read {path.name}: {exc}") from exc


def _index(items: list, kind: str) -> dict:
    out: dict = {}
    for item in items:
        if item.id in out:
            raise CatalogError(f"duplicate {kind} id: {item.id}")
        out[item.id] = item
    return out


def load_catalog(directory: Path | None = None) -> Catalog:
    directory = directory or CATALOG_DIR
    opts_doc = _read(directory / "options.yaml")
    prof_doc = _read(directory / "profiles.yaml")
    ports_doc = _read(directory / "ports.yaml")
    try:
        groups = [GroupSpec(**g) for g in opts_doc.get("groups", [])]
        options = _index([OptionSpec(**o) for o in opts_doc.get("options", [])], "option")
        profiles = _index([ProfileSpec(**p) for p in prof_doc.get("profiles", [])], "profile")
        ports = {int(k): PortNote(**v) for k, v in (ports_doc.get("ports") or {}).items()}
        states = {str(k): str(v) for k, v in (ports_doc.get("states") or {}).items()}
    except ValidationError as exc:
        raise CatalogError(str(exc)) from exc

    group_ids = {g.id for g in groups}
    for opt in options.values():
        if opt.group not in group_ids:
            raise CatalogError(f"option {opt.id} has unknown group {opt.group}")
        if (opt.render != "flag") != (opt.value is not None):
            raise CatalogError(f"option {opt.id}: value is required exactly when render is separate/attached")
        for other in opt.conflicts_with:
            if other not in options:
                raise CatalogError(f"option {opt.id} conflicts with unknown option {other}")
    for port in ports:
        if not 1 <= port <= 65535:
            raise CatalogError(f"port {port} out of range")
    for pid, profile in list(profiles.items()):
        for po in profile.options:
            if po.id not in options:
                raise CatalogError(f"profile {pid} uses unknown option {po.id}")
        needs_root = any(options[po.id].requires_root for po in profile.options)
        profiles[pid] = profile.model_copy(update={"requires_root": needs_root})

    return Catalog(groups=groups, options=options, profiles=profiles, ports=ports, states=states)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_catalog.py -v`
Expected: 8 passed.

- [ ] **Step 8: Commit**

```bash
git add backend/visualnmap/catalog backend/tests/conftest.py backend/tests/test_catalog.py
git commit -m "feat(backend): explanation catalog with options, profiles and port notes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 3: Shared models, target validation and the safe command builder

**Files:**
- Create: `backend/visualnmap/models.py`
- Create: `backend/visualnmap/targets.py`
- Create: `backend/visualnmap/command.py`
- Test: `backend/tests/test_targets.py`
- Test: `backend/tests/test_command.py`

**Interfaces:**
- Consumes: `Environment` (Task 1); `Catalog`, `OptionSpec` (Task 2).
- Produces:
  - `visualnmap.models`: `ScanStatus = Literal["running","completed","failed","cancelled"]`, `OptionValue(id: str, value: str | int | None = None)`, `ScanRequest(target: str, profile_id: str | None = None, options: list[OptionValue] = [])`, `ExplainedPart(token: str, text: str, kind: Literal["option","plumbing","target"])`, `BuiltCommand(argv: list[str], parts: list[ExplainedPart], warnings: list[str])`, `OsMatch(name: str, accuracy: int)`, `Port(port: int, protocol: str, state: str, reason: str | None, service: str | None, product: str | None, version: str | None, extrainfo: str | None, note: str | None)`, `Host(address: str, hostname: str | None, mac: str | None, vendor: str | None, status: str, reason: str | None, os_matches: list[OsMatch], ports: list[Port])`, `ScanStats(up: int = 0, down: int = 0, total: int = 0, elapsed_s: float | None = None)`, `ParsedResult(hosts: list[Host] = [], stats: ScanStats, partial: bool = False)`, `Hint(code: str, message: str, action: Literal["retry_with_pn"] | None = None)`, `ScanSummary(id, created_at: str, finished_at: str | None, target: str, profile_id: str | None, status: ScanStatus, hosts_up: int = 0, open_ports: int = 0)`, `ScanRecord(ScanSummary + request: ScanRequest, argv: list[str], result: ParsedResult | None, stderr_tail: str, hints: list[Hint])`, `ServiceChange(port: str, before: str, after: str)`, `HostDiff(ports_opened: list[str], ports_closed: list[str], services_changed: list[ServiceChange])`, `ScanDiff(a: str, b: str, hosts_added: list[str], hosts_removed: list[str], per_host: dict[str, HostDiff])`, `StatusInfo(is_root: bool, can_raw: bool, nmap_found: bool, nmap_version: str | None, in_container: bool, active_scan_id: str | None)`
  - `visualnmap.targets`: `class TargetError(ValueError)`, `@dataclass(frozen=True) ParsedTargets(tokens: list[str], address_count: int, family: int)`, `def parse_targets(text: str) -> ParsedTargets`
  - `visualnmap.command`: `class CommandError(ValueError)` with attributes `.field: str` and `.message: str`; `def count_ports(spec: str) -> int` (raises `ValueError`); `def build_command(req: ScanRequest, env: Environment, catalog: Catalog) -> BuiltCommand`

- [ ] **Step 1: Create the shared models** (no behavior to test on its own; it's exercised by every later test)

`backend/visualnmap/models.py`:

```python
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
```

- [ ] **Step 2: Write the failing target tests**

`backend/tests/test_targets.py`:

```python
import pytest

from visualnmap.targets import TargetError, parse_targets


@pytest.mark.parametrize(
    "text,count,family",
    [
        ("192.168.1.1", 1, 4),
        ("192.168.1.0/24", 256, 4),
        ("10.0.0.0/8", 16777216, 4),
        ("192.168.1.10-50", 41, 4),
        ("scanme.nmap.org", 1, 4),
        ("localhost", 1, 4),
        ("10.0.0.1 10.0.0.2", 2, 4),
        ("::1", 1, 6),
        ("fe80::1 2001:db8::5", 2, 6),
    ],
)
def test_valid_targets(text, count, family):
    parsed = parse_targets(text)
    assert parsed.address_count == count
    assert parsed.family == family
    assert parsed.tokens == text.split()


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "-iL /etc/shadow",
        "--script=vuln",
        "-oN /etc/x",
        "; rm -rf /",
        "$(id)",
        "192.168.1.1;id",
        "`id`",
        "999.1.1.1",
        "192.168.1.0/7",
        "192.168.1.0/33",
        "192.168.1.50-10",
        "192.168.1.1-300",
        "::zz",
        "a_b.example.com",
        " ".join(f"10.0.0.{i}" for i in range(1, 18)),  # 17 tokens
    ],
)
def test_invalid_targets(text):
    with pytest.raises(TargetError):
        parse_targets(text)


def test_mixed_ip_families_rejected():
    with pytest.raises(TargetError, match="IPv4 and IPv6"):
        parse_targets("192.168.1.1 ::1")


def test_error_message_gives_examples():
    with pytest.raises(TargetError, match="192.168.1.0/24"):
        parse_targets("not a target!")
```

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_targets.py -v`
Expected: ERROR `ModuleNotFoundError: No module named 'visualnmap.targets'`.

- [ ] **Step 4: Implement `targets.py`**

`backend/visualnmap/targets.py`:

```python
"""Validates what the user typed in the target box. Nothing that fails here reaches nmap."""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

MAX_TOKENS = 16
EXAMPLES = "e.g. 192.168.1.1, 192.168.1.0/24, 192.168.1.10-50 or scanme.nmap.org"
_RANGE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})-(\d{1,3})$")
_HOSTNAME = re.compile(
    r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)


class TargetError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedTargets:
    tokens: list[str]
    address_count: int
    family: int  # 4 or 6


def parse_targets(text: str) -> ParsedTargets:
    tokens = text.split()
    if not tokens:
        raise TargetError(f"Enter something to scan, {EXAMPLES}.")
    if len(tokens) > MAX_TOKENS:
        raise TargetError(f"Too many targets ({len(tokens)}). The limit is {MAX_TOKENS}; use a range or CIDR instead.")
    total = 0
    families: set[int] = set()
    for token in tokens:
        count, family = _classify(token)
        total += count
        families.add(family)
    if len(families) > 1:
        raise TargetError("Can't mix IPv4 and IPv6 targets in one scan (nmap scans one family at a time). Run two scans.")
    return ParsedTargets(tokens=tokens, address_count=total, family=families.pop())


def _classify(token: str) -> tuple[int, int]:
    if token.startswith("-"):
        raise TargetError(f"'{token}' looks like an nmap option, not a target. Use {EXAMPLES}.")
    if "/" in token:
        try:
            net = ipaddress.IPv4Network(token, strict=False)
        except ValueError:
            raise TargetError(f"'{token}' is not a valid IPv4 network. Use {EXAMPLES}.") from None
        if not 8 <= net.prefixlen <= 32:
            raise TargetError(f"'{token}': the network size must be between /8 and /32.")
        return net.num_addresses, 4
    match = _RANGE.match(token)
    if match:
        a, b, c, start, end = (int(g) for g in match.groups())
        if max(a, b, c, start, end) > 255 or end < start:
            raise TargetError(f"'{token}' is not a valid range. The last number must count up, e.g. 192.168.1.10-50.")
        return end - start + 1, 4
    try:
        ipaddress.IPv4Address(token)
        return 1, 4
    except ValueError:
        pass
    if ":" in token:
        try:
            ipaddress.IPv6Address(token)
            return 1, 6
        except ValueError:
            raise TargetError(f"'{token}' is not a valid IPv6 address.") from None
    last_label = token.rsplit(".", 1)[-1]
    if len(token) <= 253 and _HOSTNAME.match(token) and any(ch.isalpha() for ch in last_label):
        return 1, 4
    raise TargetError(f"'{token}' is not a valid target. Use {EXAMPLES}.")
```

- [ ] **Step 5: Run target tests**

Run: `cd backend && .venv/bin/pytest tests/test_targets.py -v`
Expected: all passed (28 tests).

- [ ] **Step 6: Write the failing command-builder tests**

`backend/tests/test_command.py`:

```python
import pytest

from visualnmap.command import CommandError, build_command, count_ports
from visualnmap.environment import Environment
from visualnmap.models import OptionValue, ScanRequest

NMAP = "/usr/bin/nmap"
PLUMBING = ["-v", "--stats-every", "2s", "-oX", "-"]


def env(root: bool = True, raw: bool | None = None) -> Environment:
    return Environment(
        is_root=root,
        can_raw=root if raw is None else raw,
        nmap_path=NMAP,
        nmap_version="7.99",
        in_container=False,
    )


def req(target="192.168.1.10", profile=None, **opts) -> ScanRequest:
    return ScanRequest(
        target=target,
        profile_id=profile,
        options=[OptionValue(id=k, value=v) for k, v in opts.items()],
    )


def test_quick_ports_profile_argv(catalog):
    built = build_command(req(profile="quick_ports"), env(), catalog)
    assert built.argv == [NMAP, "-F", "-T4", *PLUMBING, "192.168.1.10"]


def test_every_profile_builds_as_root(catalog):
    for pid in catalog.profiles:
        build_command(req(profile=pid), env(), catalog)


def test_user_option_overrides_profile_value(catalog):
    built = build_command(req(profile="quick_ports", timing=2), env(), catalog)
    assert "-T2" in built.argv and "-T4" not in built.argv


def test_separate_and_attached_values(catalog):
    built = build_command(req(ports="22,80", syn_ping="443", max_retries=1), env(), catalog)
    assert built.argv[1:7] == ["-PS443", "-p", "22,80", "--max-retries", "1", "-v"]


def test_missing_value_uses_default(catalog):
    built = build_command(req(top_ports=None), env(), catalog)
    assert built.argv[1:3] == ["--top-ports", "200"]


def test_unknown_option_rejected(catalog):
    with pytest.raises(CommandError) as exc:
        build_command(req(script="vuln"), env(), catalog)
    assert exc.value.field == "options"


def test_unknown_profile_rejected(catalog):
    with pytest.raises(CommandError) as exc:
        build_command(req(profile="nope"), env(), catalog)
    assert exc.value.field == "profile_id"


def test_root_option_rejected_without_raw(catalog):
    with pytest.raises(CommandError) as exc:
        build_command(req(syn_scan=None), env(root=False), catalog)
    assert exc.value.field == "options.syn_scan"
    assert "sudo" in exc.value.message


def test_root_option_allowed_with_caps_adds_privileged(catalog):
    built = build_command(req(syn_scan=None), env(root=False, raw=True), catalog)
    assert "-sS" in built.argv
    assert "--privileged" in built.argv


def test_root_does_not_add_privileged(catalog):
    assert "--privileged" not in build_command(req(syn_scan=None), env(), catalog).argv


def test_conflicting_options_rejected(catalog):
    with pytest.raises(CommandError, match="can't be combined"):
        build_command(req(ping_only=None, ports="80"), env(), catalog)


def test_two_tcp_techniques_rejected(catalog):
    with pytest.raises(CommandError):
        build_command(req(syn_scan=None, connect_scan=None), env(), catalog)


def test_udp_plus_syn_allowed(catalog):
    built = build_command(req(syn_scan=None, udp_scan=None, ports="53"), env(), catalog)
    assert "-sS" in built.argv and "-sU" in built.argv


@pytest.mark.parametrize("spec", ["0", "65536", "1-", "a", "100-10", "22,,80", "-"])
def test_bad_port_specs_rejected(catalog, spec):
    with pytest.raises(CommandError) as exc:
        build_command(req(ports=spec), env(), catalog)
    assert exc.value.field == "options.ports"


def test_count_ports():
    assert count_ports("22,80,8000-8100") == 103
    assert count_ports("1-65535") == 65535


@pytest.mark.parametrize("opts", [{"timing": 6}, {"timing": "x"}, {"top_ports": 0}, {"version_intensity": 10}, {"host_timeout": "10x"}])
def test_out_of_range_values_rejected(catalog, opts):
    with pytest.raises(CommandError):
        build_command(req(**opts), env(), catalog)


def test_duration_accepted(catalog):
    assert "30m" in build_command(req(host_timeout="30m"), env(), catalog).argv


@pytest.mark.parametrize("target", ["-iL /etc/shadow", "; rm -rf /", "$(id)", "--script=vuln", "192.168.1.1;id", "-oN /etc/x"])
def test_injection_targets_rejected(catalog, target):
    with pytest.raises(CommandError) as exc:
        build_command(req(target=target), env(), catalog)
    assert exc.value.field == "target"


def test_targets_are_last(catalog):
    built = build_command(req(target="10.0.0.1 10.0.0.2", fast=None), env(), catalog)
    assert built.argv[-2:] == ["10.0.0.1", "10.0.0.2"]


def test_ipv6_target_adds_dash_6(catalog):
    built = build_command(req(target="::1", fast=None), env(), catalog)
    assert "-6" in built.argv
    assert built.argv.index("-6") < built.argv.index("::1")


def test_ipv4_target_has_no_dash_6(catalog):
    assert "-6" not in build_command(req(fast=None), env(), catalog).argv


def test_mixed_ip_families_rejected(catalog):
    with pytest.raises(CommandError) as exc:
        build_command(req(target="192.168.1.1 ::1"), env(), catalog)
    assert exc.value.field == "target"


def test_duplicate_tokens_emitted_once(catalog):
    built = build_command(req(profile="everything", service_version=None), env(), catalog)
    assert built.argv.count("-sV") == 1
    assert built.argv.count("-O") == 1
    assert "--traceroute" in built.argv


def test_verbose_not_duplicated(catalog):
    built = build_command(req(verbose=None), env(), catalog)
    assert built.argv.count("-v") == 1


def test_parts_cover_argv_exactly(catalog):
    built = build_command(req(profile="services", target="192.168.1.0/24"), env(), catalog)
    assert " ".join(p.token for p in built.parts) == " ".join(built.argv[1:])
    kinds = [p.kind for p in built.parts]
    assert kinds[-1] == "target"
    assert "plumbing" in kinds and "option" in kinds
    assert all(p.text for p in built.parts)


def test_warning_for_huge_target(catalog):
    built = build_command(req(target="10.0.0.0/8", ping_only=None), env(), catalog)
    assert any("16,777,216" in w for w in built.warnings)


def test_warning_for_udp_all_ports(catalog):
    built = build_command(req(udp_scan=None, all_ports=None), env(), catalog)
    assert any("UDP" in w for w in built.warnings)


def test_no_udp_warning_for_top_20(catalog):
    built = build_command(req(profile="udp_common"), env(), catalog)
    assert not any("UDP" in w for w in built.warnings)


@pytest.mark.parametrize("level,word", [(5, "miss"), (0, "slow"), (1, "slow")])
def test_timing_warnings(catalog, level, word):
    built = build_command(req(timing=level), env(), catalog)
    assert any(word in w for w in built.warnings)


def test_version_intensity_without_sv_warns(catalog):
    built = build_command(req(version_intensity=9), env(), catalog)
    assert any("-sV" in w for w in built.warnings)


def test_missing_nmap_path_falls_back_to_name(catalog):
    e = Environment(is_root=True, can_raw=True, nmap_path=None, nmap_version=None, in_container=False)
    assert build_command(req(fast=None), e, catalog).argv[0] == "nmap"
```

- [ ] **Step 7: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_command.py -v`
Expected: ERROR `ModuleNotFoundError: No module named 'visualnmap.command'`.

- [ ] **Step 8: Implement `command.py`**

`backend/visualnmap/command.py`:

```python
"""Turns a ScanRequest into a safe nmap argv. The preview and the real run both use this."""
from __future__ import annotations

import re

from .catalog import Catalog, OptionSpec
from .environment import Environment
from .models import BuiltCommand, ExplainedPart, ScanRequest
from .targets import TargetError, parse_targets

PORTS_RE = re.compile(r"^\d{1,5}(-\d{1,5})?(,\d{1,5}(-\d{1,5})?)*$")
DURATION_RE = re.compile(r"^\d{1,6}(ms|s|m|h)?$")
BIG_TARGET = 65536
DEFAULT_PORT_COUNT = 1000


class CommandError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def count_ports(spec: str) -> int:
    if not PORTS_RE.match(spec):
        raise ValueError("use ports like 22,80,443 or ranges like 1-1024.")
    total = 0
    for part in spec.split(","):
        lo_text, _, hi_text = part.partition("-")
        lo = int(lo_text)
        hi = int(hi_text) if hi_text else lo
        if not (1 <= lo <= 65535 and 1 <= hi <= 65535):
            raise ValueError("each port must be between 1 and 65535.")
        if hi < lo:
            raise ValueError(f"the range {part} goes backwards.")
        total += hi - lo + 1
    return total


def _selected_options(req: ScanRequest, catalog: Catalog) -> dict[str, str | int | None]:
    selected: dict[str, str | int | None] = {}
    if req.profile_id is not None:
        profile = catalog.profiles.get(req.profile_id)
        if profile is None:
            raise CommandError("profile_id", f"Unknown scan profile '{req.profile_id}'.")
        for po in profile.options:
            selected[po.id] = po.value
    for ov in req.options:
        if ov.id not in catalog.options:
            raise CommandError("options", f"Unknown option '{ov.id}'. Only options shown in the builder can be used.")
        selected[ov.id] = ov.value
    return selected


def _checked_value(spec: OptionSpec, raw: str | int | None) -> str:
    vs = spec.value
    assert vs is not None
    field = f"options.{spec.id}"
    text = str(vs.default if raw is None or str(raw).strip() == "" else raw).strip()
    if vs.type == "int":
        try:
            number = int(text)
        except ValueError:
            raise CommandError(field, f"{spec.label}: '{text}' is not a whole number.") from None
        if (vs.min is not None and number < vs.min) or (vs.max is not None and number > vs.max):
            raise CommandError(field, f"{spec.label}: must be between {vs.min} and {vs.max}.")
        return str(number)
    if vs.type == "ports":
        try:
            count_ports(text)
        except ValueError as exc:
            raise CommandError(field, f"{spec.label}: {exc}") from None
        return text
    if not DURATION_RE.match(text):
        raise CommandError(field, f"{spec.label}: use a number followed by ms, s, m or h, e.g. 30s or 10m.")
    return text


def _render(spec: OptionSpec, value: str | None) -> list[str]:
    if spec.render == "separate":
        return [spec.flag, value or ""]
    if spec.render == "attached":
        return [f"{spec.flag}{value}"]
    return list(spec.expands_to or [spec.flag])


def _port_count(values: dict[str, str | None]) -> int:
    if "all_ports" in values:
        return 65535
    if "ports" in values:
        return count_ports(values["ports"] or "")
    if "top_ports" in values:
        return int(values["top_ports"] or 0)
    if "fast" in values:
        return 100
    return DEFAULT_PORT_COUNT


def _warnings(values: dict[str, str | None], address_count: int) -> list[str]:
    warnings: list[str] = []
    if address_count > BIG_TARGET:
        warnings.append(
            f"This target covers {address_count:,} addresses. A scan this large can take hours; consider a smaller range."
        )
    if "udp_scan" in values:
        ports = _port_count(values)
        if ports > 1000:
            warnings.append(f"UDP scanning {ports:,} ports will be very slow (often hours). Try Top N ports with 20 to 100.")
    timing = values.get("timing")
    if timing == "5":
        warnings.append("Timing 5 (insane) may miss open ports on slower networks.")
    if timing in ("0", "1"):
        warnings.append(f"Timing {timing} is extremely slow: it can take hours even for a single host.")
    if "version_intensity" in values and not ({"service_version", "aggressive"} & values.keys()):
        warnings.append("Version intensity only matters together with version detection (-sV).")
    return warnings


def build_command(req: ScanRequest, env: Environment, catalog: Catalog) -> BuiltCommand:
    try:
        targets = parse_targets(req.target)
    except TargetError as exc:
        raise CommandError("target", str(exc)) from None

    values: dict[str, str | None] = {}
    for oid, raw in _selected_options(req, catalog).items():
        spec = catalog.options[oid]
        if spec.requires_root and not env.can_raw:
            raise CommandError(
                f"options.{oid}",
                f"{spec.label} ({spec.flag}) needs root to send raw packets. "
                "Restart VisualNmap with sudo (./run.sh) to use it.",
            )
        values[oid] = _checked_value(spec, raw) if spec.value else None

    ids = list(values)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            sa, sb = catalog.options[a], catalog.options[b]
            if b in sa.conflicts_with or a in sb.conflicts_with:
                raise CommandError(
                    "options",
                    f"{sa.label} ({sa.flag}) can't be combined with {sb.label} ({sb.flag}). Remove one of them.",
                )

    argv = [env.nmap_path or "nmap"]
    parts: list[ExplainedPart] = []
    emitted_flags: set[str] = set()
    for oid in (o for o in catalog.options if o in values):  # catalog order keeps commands stable
        spec = catalog.options[oid]
        tokens = _render(spec, values[oid])
        if spec.render == "flag":
            tokens = [t for t in tokens if t not in emitted_flags]
            if not tokens:
                continue
            emitted_flags.update(tokens)
        argv += tokens
        parts.append(ExplainedPart(token=" ".join(tokens), text=spec.summary, kind="option"))

    def plumbing(tokens: list[str], text: str) -> None:
        argv.extend(tokens)
        parts.append(ExplainedPart(token=" ".join(tokens), text=text, kind="plumbing"))

    if targets.family == 6:
        plumbing(["-6"], "Scan IPv6 addresses (added automatically because the target is IPv6).")
    if env.can_raw and not env.is_root:
        plumbing(["--privileged"], "Lets nmap use raw packets: this nmap has that permission without root.")
    if "verbose" not in values:
        plumbing(["-v"], "App plumbing: makes nmap report its progress so the dashboard can show it.")
    plumbing(["--stats-every", "2s"], "App plumbing: a progress update every 2 seconds.")
    plumbing(["-oX", "-"], "App plumbing: results as XML so the dashboard can read them.")

    argv += targets.tokens
    noun = "address" if targets.address_count == 1 else "addresses"
    parts.append(
        ExplainedPart(
            token=" ".join(targets.tokens),
            text=f"What to scan: {targets.address_count:,} {noun}.",
            kind="target",
        )
    )
    return BuiltCommand(argv=argv, parts=parts, warnings=_warnings(values, targets.address_count))
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_targets.py tests/test_command.py -v`
Expected: all passed.

- [ ] **Step 10: Commit**

```bash
git add backend/visualnmap/models.py backend/visualnmap/targets.py backend/visualnmap/command.py backend/tests/test_targets.py backend/tests/test_command.py
git commit -m "feat(backend): target validation and allowlisted nmap command builder

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 4: Nmap XML parser

**Files:**
- Create: `backend/visualnmap/parser.py`
- Create: `backend/tests/fixtures/services.xml`
- Create: `backend/tests/fixtures/multi.xml`
- Create: `backend/tests/fixtures/zero_hosts.xml`
- Test: `backend/tests/test_parser.py`

**Interfaces:**
- Consumes: `Catalog` (Task 2); `ParsedResult`, `Host`, `Port`, `OsMatch`, `ScanStats` (Task 3).
- Produces:
  - `def parse_nmap_xml(xml: str, catalog: Catalog) -> ParsedResult`: never raises; sets `partial=True` when the XML is truncated, unparsable or has no `<runstats>`.
  - `def repair_truncated(xml: str) -> str`
  - `def open_port_count(result: ParsedResult) -> int`
  - `def hosts_up_count(result: ParsedResult) -> int`

- [ ] **Step 1: Create the XML fixtures** (structure copied from real Nmap 7.99 `-oX -` output, including the `<taskbegin>`/`<taskprogress>`/`<taskend>` lines that `-v --stats-every` produces)

`backend/tests/fixtures/services.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE nmaprun>
<?xml-stylesheet href="file:///usr/share/nmap/nmap.xsl" type="text/xsl"?>
<!-- Nmap 7.99 scan initiated Wed Oct 14 18:48:31 2026 as: nmap -sV -O -v -&#45;stats-every 2s -oX - 192.168.1.10 -->
<nmaprun scanner="nmap" args="nmap -sV -O -v -&#45;stats-every 2s -oX - 192.168.1.10" start="1792025311" startstr="Wed Oct 14 18:48:31 2026" version="7.99" xmloutputversion="1.05">
<scaninfo type="syn" protocol="tcp" numservices="1000" services="1-1000"/>
<verbose level="1"/>
<debugging level="0"/>
<taskbegin task="ARP Ping Scan" time="1792025311"/>
<taskend task="ARP Ping Scan" time="1792025311" extrainfo="1 total hosts"/>
<taskbegin task="SYN Stealth Scan" time="1792025312"/>
<taskprogress task="SYN Stealth Scan" time="1792025314" percent="42.50" remaining="3" etc="1792025317"/>
<taskend task="SYN Stealth Scan" time="1792025317" extrainfo="1000 total ports"/>
<host starttime="1792025311" endtime="1792025323"><status state="up" reason="arp-response" reason_ttl="0"/>
<address addr="192.168.1.10" addrtype="ipv4"/>
<address addr="AA:BB:CC:DD:EE:FF" addrtype="mac" vendor="Raspberry Pi Foundation"/>
<hostnames>
<hostname name="pi.lan" type="PTR"/>
</hostnames>
<ports><extraports state="closed" count="997">
<extrareasons reason="reset" count="997" proto="tcp" ports="1-21,23-79,81-444,446-1000"/>
</extraports>
<port protocol="tcp" portid="22"><state state="open" reason="syn-ack" reason_ttl="64"/><service name="ssh" product="OpenSSH" version="8.9p1 Ubuntu 3ubuntu0.10" extrainfo="Ubuntu Linux; protocol 2.0" ostype="Linux" method="probed" conf="10"/></port>
<port protocol="tcp" portid="80"><state state="open" reason="syn-ack" reason_ttl="64"/><service name="http" product="nginx" version="1.24.0" method="probed" conf="10"/></port>
<port protocol="tcp" portid="445"><state state="filtered" reason="no-response" reason_ttl="0"/><service name="microsoft-ds" method="table" conf="3"/></port>
</ports>
<os><portused state="open" proto="tcp" portid="22"/>
<osmatch name="Linux 5.0 - 5.14" accuracy="96" line="67890"><osclass type="general purpose" vendor="Linux" osfamily="Linux" osgen="5.X" accuracy="96"/></osmatch>
<osmatch name="Linux 4.15 - 5.19" accuracy="93" line="67000"><osclass type="general purpose" vendor="Linux" osfamily="Linux" osgen="4.X" accuracy="93"/></osmatch>
</os>
<times srtt="512" rttvar="300" to="100000"/>
</host>
<runstats><finished time="1792025323" timestr="Wed Oct 14 18:48:43 2026" summary="Nmap done at Wed Oct 14 18:48:43 2026; 1 IP address (1 host up) scanned in 12.50 seconds" elapsed="12.50" exit="success"/><hosts up="1" down="0" total="1"/>
</runstats>
</nmaprun>
```

`backend/tests/fixtures/multi.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE nmaprun>
<nmaprun scanner="nmap" args="nmap -sn -v -oX - 192.168.1.1-2" start="1792025400" version="7.99" xmloutputversion="1.05">
<verbose level="1"/>
<debugging level="0"/>
<taskbegin task="Ping Scan" time="1792025400"/>
<taskend task="Ping Scan" time="1792025401" extrainfo="2 total hosts"/>
<host><status state="up" reason="syn-ack" reason_ttl="0"/>
<address addr="192.168.1.1" addrtype="ipv4"/>
<hostnames>
<hostname name="router.lan" type="PTR"/>
</hostnames>
</host>
<host><status state="down" reason="no-response" reason_ttl="0"/>
<address addr="192.168.1.2" addrtype="ipv4"/>
<hostnames>
</hostnames>
</host>
<runstats><finished time="1792025402" timestr="Wed Oct 14 18:50:02 2026" elapsed="2.04" summary="Nmap done; 2 IP addresses (1 host up) scanned in 2.04 seconds" exit="success"/><hosts up="1" down="1" total="2"/>
</runstats>
</nmaprun>
```

`backend/tests/fixtures/zero_hosts.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE nmaprun>
<nmaprun scanner="nmap" args="nmap -F -v -oX - 10.9.9.0/24" start="1792025500" version="7.99" xmloutputversion="1.05">
<scaninfo type="connect" protocol="tcp" numservices="100" services="7,9,13"/>
<verbose level="1"/>
<debugging level="0"/>
<runstats><finished time="1792025503" timestr="Wed Oct 14 18:51:43 2026" elapsed="3.10" summary="Nmap done; 256 IP addresses (0 hosts up) scanned in 3.10 seconds" exit="success"/><hosts up="0" down="256" total="256"/>
</runstats>
</nmaprun>
```

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_parser.py`:

```python
from pathlib import Path

from visualnmap.parser import hosts_up_count, open_port_count, parse_nmap_xml, repair_truncated

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_services_host_details(catalog):
    result = parse_nmap_xml(load("services.xml"), catalog)
    assert result.partial is False
    assert len(result.hosts) == 1
    host = result.hosts[0]
    assert host.address == "192.168.1.10"
    assert host.hostname == "pi.lan"
    assert host.mac == "AA:BB:CC:DD:EE:FF"
    assert host.vendor == "Raspberry Pi Foundation"
    assert host.status == "up"
    assert host.reason == "arp-response"
    assert [m.accuracy for m in host.os_matches] == [96, 93]
    assert host.os_matches[0].name == "Linux 5.0 - 5.14"


def test_services_ports_and_notes(catalog):
    host = parse_nmap_xml(load("services.xml"), catalog).hosts[0]
    by_port = {p.port: p for p in host.ports}
    assert set(by_port) == {22, 80, 445}
    ssh = by_port[22]
    assert (ssh.protocol, ssh.state, ssh.reason, ssh.service) == ("tcp", "open", "syn-ack", "ssh")
    assert ssh.product == "OpenSSH"
    assert ssh.version == "8.9p1 Ubuntu 3ubuntu0.10"
    assert ssh.extrainfo == "Ubuntu Linux; protocol 2.0"
    assert "SSH" in (ssh.note or "")
    assert by_port[445].state == "filtered"
    assert by_port[445].product is None


def test_stats(catalog):
    result = parse_nmap_xml(load("services.xml"), catalog)
    assert (result.stats.up, result.stats.down, result.stats.total) == (1, 0, 1)
    assert result.stats.elapsed_s == 12.5
    assert open_port_count(result) == 2
    assert hosts_up_count(result) == 1


def test_multiple_hosts_and_down_host(catalog):
    result = parse_nmap_xml(load("multi.xml"), catalog)
    assert [h.status for h in result.hosts] == ["up", "down"]
    assert result.hosts[0].hostname == "router.lan"
    assert result.hosts[1].hostname is None
    assert result.hosts[0].ports == []
    assert (result.stats.up, result.stats.down, result.stats.total) == (1, 1, 2)


def test_zero_hosts(catalog):
    result = parse_nmap_xml(load("zero_hosts.xml"), catalog)
    assert result.hosts == []
    assert result.stats.total == 256 and result.stats.up == 0
    assert result.partial is False


def test_truncated_xml_is_partial_but_keeps_data(catalog):
    xml = load("services.xml")
    cut = xml.index('<port protocol="tcp" portid="80">') + 20  # cut inside the second port's tag
    result = parse_nmap_xml(xml[:cut], catalog)
    assert result.partial is True
    assert len(result.hosts) == 1
    assert [p.port for p in result.hosts[0].ports] == [22]
    assert result.stats.up == 1  # derived from hosts when runstats is missing


def test_garbage_and_empty_input(catalog):
    for text in ("", "   ", "not xml at all", "<nmaprun"):
        result = parse_nmap_xml(text, catalog)
        assert result.partial is True
        assert result.hosts == []


def test_entity_expansion_is_refused(catalog):
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;">]>'
        "<nmaprun>&lol2;</nmaprun>"
    )
    result = parse_nmap_xml(bomb, catalog)
    assert result.partial is True and result.hosts == []


def test_repair_truncated():
    assert repair_truncated("<a><b x='1'><c/><d attr") == "<a><b x='1'><c/></b></a>"
    assert repair_truncated('<?xml version="1.0"?><a><b>text</b>') == '<?xml version="1.0"?><a><b>text</b></a>'
    assert repair_truncated("no tags") == ""
```

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_parser.py -v`
Expected: ERROR `ModuleNotFoundError: No module named 'visualnmap.parser'`.

- [ ] **Step 4: Implement `parser.py`**

`backend/visualnmap/parser.py`:

```python
"""Turns nmap's XML output into ParsedResult. Never raises: bad input gives partial=True."""
from __future__ import annotations

import re
from xml.etree.ElementTree import Element

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from .catalog import Catalog
from .models import Host, OsMatch, ParsedResult, Port, ScanStats

_TAG = re.compile(r"<(/?)([A-Za-z_][\w.:-]*)[^<>]*?(/?)>")


def repair_truncated(xml: str) -> str:
    """Drop the incomplete tail and close every tag still open, so a cancelled scan's XML parses."""
    cut = xml.rfind(">")
    if cut == -1:
        return ""
    body = xml[: cut + 1]
    stack: list[str] = []
    for match in _TAG.finditer(body):
        closing, name, self_closing = match.groups()
        if self_closing:
            continue
        if closing:
            if stack and stack[-1] == name:
                stack.pop()
        else:
            stack.append(name)
    return body + "".join(f"</{name}>" for name in reversed(stack))


def _parse_root(xml: str) -> tuple[Element | None, bool]:
    try:
        return fromstring(xml), False
    except (ParseError, DefusedXmlException):
        pass
    repaired = repair_truncated(xml)
    if not repaired:
        return None, True
    try:
        return fromstring(repaired), True
    except (ParseError, DefusedXmlException):
        return None, True


def _host(el: Element, catalog: Catalog) -> Host:
    address = mac = vendor = None
    for addr in el.findall("address"):
        kind = addr.get("addrtype")
        if kind in ("ipv4", "ipv6") and address is None:
            address = addr.get("addr")
        elif kind == "mac":
            mac, vendor = addr.get("addr"), addr.get("vendor")
    status = el.find("status")
    hostname = el.find("hostnames/hostname")
    ports: list[Port] = []
    for p in el.findall("ports/port"):
        number = int(p.get("portid", "0"))
        state = p.find("state")
        service = p.find("service")
        note = catalog.ports.get(number)
        ports.append(
            Port(
                port=number,
                protocol=p.get("protocol", "tcp"),
                state=state.get("state", "unknown") if state is not None else "unknown",
                reason=state.get("reason") if state is not None else None,
                service=service.get("name") if service is not None else None,
                product=service.get("product") if service is not None else None,
                version=service.get("version") if service is not None else None,
                extrainfo=service.get("extrainfo") if service is not None else None,
                note=note.note if note else None,
            )
        )
    os_matches = [
        OsMatch(name=m.get("name", ""), accuracy=int(m.get("accuracy", "0"))) for m in el.findall("os/osmatch")
    ]
    return Host(
        address=address or mac or "unknown",
        hostname=hostname.get("name") if hostname is not None else None,
        mac=mac,
        vendor=vendor,
        status=status.get("state", "unknown") if status is not None else "unknown",
        reason=status.get("reason") if status is not None else None,
        os_matches=os_matches,
        ports=ports,
    )


def parse_nmap_xml(xml: str, catalog: Catalog) -> ParsedResult:
    if not xml.strip():
        return ParsedResult(partial=True)
    root, partial = _parse_root(xml)
    if root is None or root.tag != "nmaprun":
        return ParsedResult(partial=True)
    hosts = [_host(h, catalog) for h in root.iter("host")]
    runstats_hosts = root.find("runstats/hosts")
    finished = root.find("runstats/finished")
    if runstats_hosts is not None:
        stats = ScanStats(
            up=int(runstats_hosts.get("up", "0")),
            down=int(runstats_hosts.get("down", "0")),
            total=int(runstats_hosts.get("total", "0")),
            elapsed_s=float(finished.get("elapsed")) if finished is not None and finished.get("elapsed") else None,
        )
    else:
        partial = True
        up = sum(1 for h in hosts if h.status == "up")
        stats = ScanStats(up=up, down=len(hosts) - up, total=len(hosts))
    return ParsedResult(hosts=hosts, stats=stats, partial=partial)


def open_port_count(result: ParsedResult) -> int:
    return sum(1 for h in result.hosts for p in h.ports if p.state == "open")


def hosts_up_count(result: ParsedResult) -> int:
    return result.stats.up
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_parser.py -v`
Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/visualnmap/parser.py backend/tests/fixtures/services.xml backend/tests/fixtures/multi.xml backend/tests/fixtures/zero_hosts.xml backend/tests/test_parser.py
git commit -m "feat(backend): nmap XML parser tolerant of truncated output

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 5: Plain-language error hints

**Files:**
- Create: `backend/visualnmap/errors.py`
- Test: `backend/tests/test_errors.py`

**Interfaces:**
- Consumes: `Hint`, `ParsedResult`, `ScanStats` (Task 3).
- Produces: `def hints_for(stderr: str, result: ParsedResult | None, status: str, argv: list[str]) -> list[Hint]`: at most one hint per `code`; codes are `resolve`, `root`, `no_hosts`, `quit`, `cancelled`, `failed`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_errors.py`:

```python
from visualnmap.errors import hints_for
from visualnmap.models import Host, ParsedResult, ScanStats

UP = ParsedResult(hosts=[Host(address="10.0.0.1", status="up")], stats=ScanStats(up=1, total=1))
NONE_UP = ParsedResult(hosts=[], stats=ScanStats(up=0, down=256, total=256))
ARGV = ["nmap", "-F", "-v", "--stats-every", "2s", "-oX", "-", "10.0.0.1"]


def codes(hints):
    return [h.code for h in hints]


def test_failed_to_resolve():
    hints = hints_for('Failed to resolve "nosuchhost.invalid".\n', NONE_UP, "completed", ARGV)
    assert "resolve" in codes(hints)
    assert "spelling" in hints[codes(hints).index("resolve")].message


def test_requires_root():
    stderr = "You requested a scan type which requires root privileges.\nQUITTING!\n"
    hints = hints_for(stderr, None, "failed", ARGV)
    assert codes(hints)[0] == "root"
    assert "quit" not in codes(hints)  # root hint already explains the quit
    assert "failed" not in codes(hints)


def test_no_hosts_up_offers_retry_with_pn():
    hints = hints_for("", NONE_UP, "completed", ARGV)
    assert codes(hints) == ["no_hosts"]
    assert hints[0].action == "retry_with_pn"


def test_host_seems_down_message_also_triggers_no_hosts():
    hints = hints_for("Note: Host seems down. If it is really up, but blocking our ping probes, try -Pn\n", NONE_UP, "completed", ARGV)
    assert codes(hints) == ["no_hosts"]


def test_no_retry_hint_when_pn_already_used():
    argv = ARGV[:1] + ["-Pn"] + ARGV[1:]
    assert hints_for("", NONE_UP, "completed", argv) == []


def test_no_retry_hint_for_ping_scan_with_hosts():
    assert hints_for("", UP, "completed", ARGV) == []


def test_generic_quit():
    hints = hints_for("Something odd happened\nQUITTING!\n", None, "failed", ARGV)
    assert codes(hints) == ["quit"]


def test_generic_failure():
    assert codes(hints_for("", None, "failed", ARGV)) == ["failed"]


def test_cancelled():
    hints = hints_for("", UP, "cancelled", ARGV)
    assert codes(hints) == ["cancelled"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_errors.py -v`
Expected: ERROR `ModuleNotFoundError: No module named 'visualnmap.errors'`.

- [ ] **Step 3: Implement `errors.py`**

`backend/visualnmap/errors.py`:

```python
"""Translates nmap's error output and odd results into plain-language hints."""
from __future__ import annotations

import re

from .models import Hint, ParsedResult

_RESOLVE = re.compile(r"Failed to resolve")
_ROOT = re.compile(r"requires root privileges|You requested a scan type which requires root")
_HOST_DOWN = re.compile(r"Host seems down|0 hosts up")
_QUIT = re.compile(r"QUITTING!")


def hints_for(stderr: str, result: ParsedResult | None, status: str, argv: list[str]) -> list[Hint]:
    hints: list[Hint] = []
    if _RESOLVE.search(stderr):
        hints.append(Hint(code="resolve", message="Couldn't find that host name. Check the spelling or try an IP address."))
    if _ROOT.search(stderr):
        hints.append(Hint(code="root", message="This scan needs root. Restart VisualNmap with sudo (./run.sh); see the README."))
    no_hosts = (result is not None and status == "completed" and result.stats.up == 0) or bool(_HOST_DOWN.search(stderr))
    if no_hosts and "-Pn" not in argv and "-sn" not in argv:
        hints.append(
            Hint(
                code="no_hosts",
                message="No hosts answered. Many devices (especially Windows PCs) block ping. "
                "Try again with 'Skip host discovery (-Pn)'.",
                action="retry_with_pn",
            )
        )
    if status == "cancelled":
        hints.append(Hint(code="cancelled", message="You cancelled this scan. The results show only what nmap found before it stopped."))
    if status == "failed" and not hints:
        if _QUIT.search(stderr):
            hints.append(Hint(code="quit", message="Nmap stopped because of an error. See the output above for its message."))
        else:
            hints.append(Hint(code="failed", message="Nmap exited with an error. See the output above for details."))
    return hints
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_errors.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/visualnmap/errors.py backend/tests/test_errors.py
git commit -m "feat(backend): plain-language hints for nmap errors

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Scan history (SQLite), export and compare

**Files:**
- Create: `backend/visualnmap/history.py`
- Test: `backend/tests/test_history.py`

**Interfaces:**
- Consumes: `ScanRequest`, `ParsedResult`, `ScanRecord`, `ScanSummary`, `ScanDiff`, `HostDiff`, `ServiceChange` (Task 3); `open_port_count`, `hosts_up_count` (Task 4).
- Produces: `class History`:
  - `History(db_path: Path)` creates the parent dir and the table
  - `create(request: ScanRequest, argv: list[str]) -> str` (uuid4 hex, status `running`)
  - `finish(scan_id: str, status: str, raw_xml: str, result: ParsedResult, stderr_tail: str) -> None`
  - `get(scan_id: str) -> ScanRecord | None` (`hints` is always `[]`; the API fills them)
  - `get_raw_xml(scan_id: str) -> str | None`
  - `list(limit: int = 100) -> list[ScanSummary]`, newest first
  - `delete(scan_id: str) -> bool`
  - `export(scan_id: str, fmt: Literal["xml", "json"]) -> tuple[bytes, str] | None` (content, media type)
  - `compare(a: str, b: str) -> ScanDiff` (raises `KeyError` if either id is unknown)
  - `recover_interrupted() -> int`: marks leftover `running` rows `failed`
  - `close() -> None`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_history.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_history.py -v`
Expected: ERROR `ModuleNotFoundError: No module named 'visualnmap.history'`.

- [ ] **Step 3: Implement `history.py`**

`backend/visualnmap/history.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_history.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/visualnmap/history.py backend/tests/test_history.py
git commit -m "feat(backend): SQLite scan history with export and compare

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 7: Scan runner (subprocess, live events, cancel)

**Files:**
- Create: `backend/visualnmap/runner.py`
- Create: `backend/tests/fixtures/fake_nmap.py` (must be executable: `chmod +x`)
- Test: `backend/tests/test_runner.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (deliberately independent: it runs any argv).
- Produces:
  - `FinishCallback = Callable[[str, str, str, str], Awaitable[None]]`, called as `on_finish(scan_id, status, xml, stderr_tail)` **before** the `done` event is emitted
  - `class ScanBusy(Exception)` with `.active_id: str`
  - `def describe_task_line(line: str) -> list[dict]`
  - `class ScanRunner(on_finish: FinishCallback, buffer_limit: int = 5000, kill_grace: float = 5.0)` with:
    - `async start(scan_id: str, argv: list[str]) -> None` (raises `ScanBusy`)
    - `async cancel(scan_id: str) -> bool` (False if unknown or already finished; a second cancel returns True and does nothing)
    - `subscribe(scan_id: str) -> AsyncIterator[dict]` (replays the buffer, then live events, ends after `done`; yields nothing for unknown ids)
    - `async wait(scan_id: str) -> None` (waits until the scan has finished)
    - `active_scan_id() -> str | None`, `knows(scan_id: str) -> bool`, `async shutdown() -> None`
  - Event dicts: `{"type": "output", "line": str}` · `{"type": "progress", "task": str, "percent": float | None, "eta": str | None}` (percent `None` means "phase started, no percentage yet") · `{"type": "done", "status": "completed" | "failed" | "cancelled"}`
  - `tests/fixtures/fake_nmap.py`: behavior chosen by env var `FAKE_NMAP_MODE` = `ok` (default) | `slow` | `stubborn` | `fail` | `binary` | `chatty`; if `FAKE_NMAP_ARGS_FILE` is set, writes its argv (JSON) there

- [ ] **Step 1: Create the fake nmap**

`backend/tests/fixtures/fake_nmap.py`:

```python
#!/usr/bin/env python3
"""Stands in for nmap in tests. Behavior is chosen with FAKE_NMAP_MODE."""
import json
import os
import signal
import sys
import time

mode = os.environ.get("FAKE_NMAP_MODE", "ok")
args_file = os.environ.get("FAKE_NMAP_ARGS_FILE")
if args_file:
    with open(args_file, "w") as fh:
        json.dump(sys.argv[1:], fh)

HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE nmaprun>\n<nmaprun scanner="nmap" args="fake" version="7.99">\n'
HOST = (
    '<host><status state="up" reason="syn-ack"/>\n<address addr="10.0.0.1" addrtype="ipv4"/>\n'
    '<ports><port protocol="tcp" portid="22"><state state="open" reason="syn-ack"/><service name="ssh"/></port>\n'
    "</ports>\n</host>\n"
)
TAIL = '<runstats><finished elapsed="0.20" exit="success"/><hosts up="1" down="0" total="1"/>\n</runstats>\n</nmaprun>\n'


def out(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def err(text: str) -> None:
    sys.stderr.write(text)
    sys.stderr.flush()


if mode == "stubborn":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

out(HEAD)
out('<taskbegin task="Fake Scan" time="1"/>\n')

if mode in ("slow", "stubborn"):
    time.sleep(30)
    sys.exit(0)

if mode == "fail":
    err('Failed to resolve "nosuchhost.invalid".\nQUITTING!\n')
    sys.exit(1)

if mode == "binary":
    sys.stderr.buffer.write(b"Warning: odd banner \xff\xfe here\n")
    sys.stderr.flush()
    sys.stdout.buffer.write(b"<!-- \xff -->\n")
    sys.stdout.flush()

if mode == "chatty":
    for i in range(50):
        err(f"line {i}\n")

time.sleep(0.05)
out('<taskprogress task="Fake Scan" time="2" percent="50.00" remaining="90" etc="3"/>\n')
err("Warning: fake warning\n")
out('<taskend task="Fake Scan" time="3" extrainfo="1000 total ports"/>\n')
out(HOST)
out(TAIL)
sys.exit(0)
```

Run: `chmod +x backend/tests/fixtures/fake_nmap.py`

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_runner.py`:

```python
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
```

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_runner.py -v`
Expected: ERROR `ModuleNotFoundError: No module named 'visualnmap.runner'`.

- [ ] **Step 4: Implement `runner.py`**

`backend/visualnmap/runner.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_runner.py -v`
Expected: 12 passed (well under 10 s total).

- [ ] **Step 6: Commit**

```bash
git add backend/visualnmap/runner.py backend/tests/fixtures/fake_nmap.py backend/tests/test_runner.py
git commit -m "feat(backend): scan runner with live events, replay buffer and cancel

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 8: HTTP/WebSocket API, static frontend serving and entrypoint

**Files:**
- Create: `backend/visualnmap/api.py`
- Create: `backend/visualnmap/__main__.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `Environment`, `detect_environment` (Task 1); `Catalog`, `load_catalog` (Task 2); all models, `build_command`, `CommandError` (Task 3); `parse_nmap_xml` (Task 4); `hints_for` (Task 5); `History` (Task 6); `ScanRunner`, `ScanBusy` (Task 7); `tests/fixtures/fake_nmap.py` (Task 7).
- Produces:
  - `def create_app(env: Environment, catalog: Catalog, history: History, static_dir: Path | None = None) -> FastAPI` (calls `history.recover_interrupted()`; `app.state.runner` is the `ScanRunner`)
  - `@dataclass Settings(host: str, port: int, data_dir: Path, static_dir: Path)` with `Settings.from_env()` reading `VISUALNMAP_HOST` (default `127.0.0.1`), `VISUALNMAP_PORT` (`8765`), `VISUALNMAP_DATA` (`data`), `VISUALNMAP_STATIC` (default `<repo>/frontend/dist`)
  - `python -m visualnmap` starts uvicorn
  - HTTP contract for the frontend (Task 10 mirrors it in TypeScript):

| Method | Path | Success | Errors |
|---|---|---|---|
| GET | `/api/status` | 200 `StatusInfo` | |
| GET | `/api/catalog` | 200 `Catalog` as JSON (port keys become strings) | |
| POST | `/api/command/preview` | 200 `BuiltCommand` | 422 `{field, message}` |
| POST | `/api/scans` | 201 `{scan_id}` | 422 `{field, message}` · 409 `{message, active_scan_id}` · 503 `{message}` |
| GET | `/api/scans` | 200 `ScanSummary[]` | |
| GET | `/api/scans/{id}` | 200 `ScanRecord` (with `hints`) | 404 `{message}` |
| POST | `/api/scans/{id}/cancel` | 202 `{status: "cancelling"}` | 409 `{message}` |
| DELETE | `/api/scans/{id}` | 204 | 404 · 409 `{message}` |
| GET | `/api/scans/{id}/export?format=xml\|json` | 200 file download | 404 |
| GET | `/api/compare?a=&b=` | 200 `ScanDiff` | 404 `{message}` |
| WS | `/api/scans/{id}/stream` | runner events, then close; for a scan the runner doesn't know: one `{"type":"done","status":<stored>}`; unknown id: `{"type":"error","message":"Unknown scan."}` | handshake rejected for a foreign Origin |

POST/DELETE routes and the WebSocket return 403 `{detail: "Cross-site request blocked."}` (or reject the handshake) when `Origin` is present and is not `http://<Host>` or `https://<Host>`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_api.py`:

```python
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from visualnmap.api import create_app
from visualnmap.environment import Environment
from visualnmap.history import History
from visualnmap.models import ScanRequest

FAKE = str(Path(__file__).parent / "fixtures" / "fake_nmap.py")


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
    with TestClient(create_app(make_env(), catalog, history)) as c:
        yield c


def start_scan(client, body=None) -> str:
    resp = client.post("/api/scans", json=body or {"target": "10.0.0.1", "profile_id": "quick_ports"})
    assert resp.status_code == 201, resp.text
    return resp.json()["scan_id"]


def stream_events(client, scan_id, headers=None) -> list[dict]:
    events = []
    with client.websocket_connect(f"/api/scans/{scan_id}/stream", headers=headers or {}) as ws:
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
    with TestClient(create_app(make_env(root=False), catalog, history)) as c:
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
    with TestClient(create_app(make_env(nmap=None), catalog, history)) as c:
        assert c.get("/api/status").json()["nmap_found"] is False
        resp = c.post("/api/scans", json={"target": "10.0.0.1", "profile_id": "quick_ports"})
    assert resp.status_code == 503
    assert "apt install nmap" in resp.json()["message"]


def test_foreign_origin_blocked(client):
    resp = client.post("/api/scans", json={"target": "10.0.0.1"}, headers={"origin": "http://evil.example"})
    assert resp.status_code == 403
    ok = client.post("/api/command/preview", json={"target": "10.0.0.1"}, headers={"origin": "http://testserver"})
    assert ok.status_code == 200


def test_ws_foreign_origin_rejected(client):
    sid = start_scan(client)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/scans/{sid}/stream", headers={"origin": "http://evil.example"}) as ws:
            ws.receive_json()
    stream_events(client, sid)


def test_ws_for_finished_scan_after_restart_sends_done(catalog, history, monkeypatch):
    monkeypatch.setenv("FAKE_NMAP_MODE", "ok")
    with TestClient(create_app(make_env(), catalog, history)) as c1:
        sid = start_scan(c1)
        stream_events(c1, sid)
    with TestClient(create_app(make_env(), catalog, history)) as c2:  # fresh runner, same history
        assert stream_events(c2, sid) == [{"type": "done", "status": "completed"}]
        assert stream_events(c2, "nope") == [{"type": "error", "message": "Unknown scan."}]


def test_interrupted_scans_recovered_on_startup(catalog, history):
    sid = history.create(ScanRequest(target="10.0.0.1"), ["nmap", "10.0.0.1"])
    with TestClient(create_app(make_env(), catalog, history)) as c:
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
    with TestClient(create_app(make_env(), catalog, history, static_dir=static)) as c:
        assert "INDEX" in c.get("/").text
        assert "INDEX" in c.get("/history").text
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert "SECRET" not in c.get("/..%2Fsecret.txt").text
        assert c.get("/api/does-not-exist").status_code == 404


def test_frontend_not_built_message(catalog, history, tmp_path):
    with TestClient(create_app(make_env(), catalog, history, static_dir=tmp_path / "missing")) as c:
        assert "Frontend not built" in c.get("/").text
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_api.py -v`
Expected: ERROR `ModuleNotFoundError: No module named 'visualnmap.api'`.

- [ ] **Step 3: Implement `api.py`**

`backend/visualnmap/api.py`:

```python
"""FastAPI app: REST + WebSocket API and the built frontend."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from .catalog import Catalog
from .command import CommandError, build_command
from .environment import Environment
from .errors import hints_for
from .history import History
from .models import BuiltCommand, ScanDiff, ScanRecord, ScanRequest, ScanSummary, StatusInfo
from .parser import parse_nmap_xml
from .runner import ScanBusy, ScanRunner

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    host: str
    port: int
    data_dir: Path
    static_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=os.environ.get("VISUALNMAP_HOST", "127.0.0.1"),
            port=int(os.environ.get("VISUALNMAP_PORT", "8765")),
            data_dir=Path(os.environ.get("VISUALNMAP_DATA", "data")),
            static_dir=Path(os.environ.get("VISUALNMAP_STATIC", str(REPO_ROOT / "frontend" / "dist"))),
        )


def _origin_ok(headers) -> bool:
    origin = headers.get("origin")
    if origin is None:
        return True
    host = headers.get("host", "")
    return origin in (f"http://{host}", f"https://{host}")


def check_origin(request: Request) -> None:
    if not _origin_ok(request.headers):
        raise HTTPException(status_code=403, detail="Cross-site request blocked.")


def _error(status: int, **body) -> JSONResponse:
    return JSONResponse(status_code=status, content=body)


def create_app(env: Environment, catalog: Catalog, history: History, static_dir: Path | None = None) -> FastAPI:
    history.recover_interrupted()

    async def on_finish(scan_id: str, status: str, xml: str, stderr_tail: str) -> None:
        history.finish(scan_id, status, xml, parse_nmap_xml(xml, catalog), stderr_tail)

    runner = ScanRunner(on_finish)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        await runner.shutdown()

    app = FastAPI(title="VisualNmap", lifespan=lifespan)
    app.state.runner = runner
    api = APIRouter(prefix="/api")
    guarded = [Depends(check_origin)]

    @api.get("/status", response_model=StatusInfo)
    async def status() -> StatusInfo:
        return StatusInfo(
            is_root=env.is_root,
            can_raw=env.can_raw,
            nmap_found=env.nmap_path is not None,
            nmap_version=env.nmap_version,
            in_container=env.in_container,
            active_scan_id=runner.active_scan_id(),
        )

    @api.get("/catalog")
    async def get_catalog() -> dict:
        return catalog.model_dump(mode="json")

    @api.post("/command/preview", response_model=BuiltCommand, dependencies=guarded)
    async def preview(req: ScanRequest):
        try:
            return build_command(req, env, catalog)
        except CommandError as exc:
            return _error(422, field=exc.field, message=exc.message)

    @api.post("/scans", status_code=201, dependencies=guarded)
    async def create_scan(req: ScanRequest):
        if env.nmap_path is None:
            return _error(503, message="Nmap is not installed. Install it with: sudo apt install nmap")
        try:
            built = build_command(req, env, catalog)
        except CommandError as exc:
            return _error(422, field=exc.field, message=exc.message)
        active = runner.active_scan_id()
        if active is not None:
            return _error(409, message="Another scan is already running.", active_scan_id=active)
        scan_id = history.create(req, built.argv)
        try:
            await runner.start(scan_id, built.argv)
        except ScanBusy as exc:
            history.delete(scan_id)
            return _error(409, message="Another scan is already running.", active_scan_id=exc.active_id)
        return {"scan_id": scan_id}

    @api.get("/scans", response_model=list[ScanSummary])
    async def list_scans() -> list[ScanSummary]:
        return history.list()

    @api.get("/scans/{scan_id}", response_model=ScanRecord)
    async def get_scan(scan_id: str):
        record = history.get(scan_id)
        if record is None:
            return _error(404, message="Scan not found.")
        if record.status != "running":
            record.hints = hints_for(record.stderr_tail, record.result, record.status, record.argv)
        return record

    @api.post("/scans/{scan_id}/cancel", status_code=202, dependencies=guarded)
    async def cancel_scan(scan_id: str):
        if runner.active_scan_id() != scan_id:
            return _error(409, message="This scan is not running.")
        await runner.cancel(scan_id)
        return {"status": "cancelling"}

    @api.delete("/scans/{scan_id}", status_code=204, dependencies=guarded)
    async def delete_scan(scan_id: str):
        if runner.active_scan_id() == scan_id:
            return _error(409, message="Cancel the scan before deleting it.")
        if not history.delete(scan_id):
            return _error(404, message="Scan not found.")
        return Response(status_code=204)

    @api.get("/scans/{scan_id}/export")
    async def export_scan(scan_id: str, format: Literal["xml", "json"]):
        exported = history.export(scan_id, format)
        if exported is None:
            return _error(404, message="Scan not found.")
        content, media_type = exported
        filename = f"visualnmap-{scan_id[:8]}.{format}"
        return Response(content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @api.get("/compare", response_model=ScanDiff)
    async def compare(a: str, b: str):
        try:
            return history.compare(a, b)
        except KeyError:
            return _error(404, message="One of the scans to compare was not found.")

    app.include_router(api)

    @app.websocket("/api/scans/{scan_id}/stream")
    async def stream(websocket: WebSocket, scan_id: str):
        if not _origin_ok(websocket.headers):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        try:
            if runner.knows(scan_id):
                async for event in runner.subscribe(scan_id):
                    await websocket.send_json(event)
            else:
                record = history.get(scan_id)
                if record is None:
                    await websocket.send_json({"type": "error", "message": "Unknown scan."})
                else:
                    await websocket.send_json({"type": "done", "status": record.status})
            await websocket.close()
        except WebSocketDisconnect:
            pass

    if static_dir is not None and (static_dir / "index.html").is_file():
        root = static_dir.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(status_code=404)
            candidate = (root / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate)
            return FileResponse(root / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        async def not_built():
            return HTMLResponse(
                "<h1>VisualNmap</h1><p>Frontend not built. Run <code>./run.sh</code>, "
                "or <code>cd frontend &amp;&amp; npm ci &amp;&amp; npm run build</code>.</p>"
            )

    return app
```

- [ ] **Step 4: Implement the entrypoint**

`backend/visualnmap/__main__.py`:

```python
"""`python -m visualnmap`: start the dashboard."""
from __future__ import annotations

import uvicorn

from .api import Settings, create_app
from .catalog import load_catalog
from .environment import detect_environment
from .history import History


def main() -> None:
    settings = Settings.from_env()
    env = detect_environment()
    catalog = load_catalog()
    history = History(settings.data_dir / "visualnmap.db")
    app = create_app(env, catalog, history, settings.static_dir)

    print(f"Nmap: {env.nmap_version or 'NOT FOUND (sudo apt install nmap)'}")
    print(f"Raw packets (root-only scans): {'available' if env.can_raw else 'not available (run with sudo)'}")
    if env.in_container:
        print("Running in a container: LAN discovery is limited; 'localhost' means the container.")
    if settings.host not in ("127.0.0.1", "localhost", "::1") and not env.in_container:
        print(f"WARNING: listening on {settings.host}. Anyone who can reach this machine can run scans.")
    shown_host = "127.0.0.1" if env.in_container else settings.host
    print(f"VisualNmap running at http://{shown_host}:{settings.port}", flush=True)
    try:
        uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")
    finally:
        history.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the API tests, then the whole backend suite**

Run: `cd backend && .venv/bin/pytest tests/test_api.py -v`
Expected: 20 passed.

Run: `cd backend && .venv/bin/pytest -q`
Expected: all tests pass, 0 failures.

- [ ] **Step 6: Manual check that the server starts**

Run: `cd /home/maikolkali/VisualNmap && timeout 5 backend/.venv/bin/python -m visualnmap; curl -s http://127.0.0.1:8765/api/status` (run the server in the background with `&` before the curl if needed)
Expected: prints `VisualNmap running at http://127.0.0.1:8765`; the curl returns JSON containing `"nmap_found":true`. `/` shows "Frontend not built" (the frontend doesn't exist yet).

- [ ] **Step 7: Commit**

```bash
git add backend/visualnmap/api.py backend/visualnmap/__main__.py backend/tests/test_api.py
git commit -m "feat(backend): REST and WebSocket API with origin checks and SPA serving

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 9: `run.sh` launcher and real-nmap end-to-end tests

**Files:**
- Create: `run.sh` (executable)
- Create: `backend/tests/test_e2e.py`

**Interfaces:**
- Consumes: `create_app` (Task 8), `detect_environment` (Task 1), `History` (Task 6), `python -m visualnmap` (Task 8).
- Produces: `./run.sh [--no-sudo] [--help]`, the primary way to run the app. It refuses to run as root, creates `backend/.venv` (`python3 -m venv`, falling back to `uv venv`), reinstalls the backend when `backend/pyproject.toml` is newer than `backend/.venv/.installed`, builds `frontend/dist` when it is missing or older than the frontend sources (skipped silently if `frontend/` does not exist yet), pre-creates `data/visualnmap.db` as the normal user, then `exec sudo --preserve-env=... backend/.venv/bin/python -m visualnmap`.

- [ ] **Step 1: Write the failing e2e tests**

`backend/tests/test_e2e.py`:

```python
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
```

- [ ] **Step 2: Run them against real nmap**

Run: `cd backend && VISUALNMAP_E2E=1 .venv/bin/pytest -m e2e -v`
Expected: 2 passed. (The code they exercise already exists, so they pass right away. They pin real-nmap behavior, especially that `-v --stats-every 2s -oX -` output parses.) Also run `cd backend && .venv/bin/pytest -q` and confirm the two e2e tests show as **skipped** without the env var.

- [ ] **Step 3: Write `run.sh`**

`run.sh`:

```bash
#!/usr/bin/env bash
# VisualNmap launcher: sets up on first run, builds the web interface, then starts the server with sudo.
set -euo pipefail
cd "$(dirname "$0")"

USE_SUDO=1
for arg in "$@"; do
  case "$arg" in
    --no-sudo) USE_SUDO=0 ;;
    -h|--help)
      echo "Usage: ./run.sh [--no-sudo]"
      echo "  --no-sudo   run without root (options marked with a lock are disabled)"
      exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

if [ "$(id -u)" -eq 0 ]; then
  echo "Run ./run.sh as your normal user. It asks for sudo itself, so nothing is built as root." >&2
  exit 1
fi

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1. Install it with: $2" >&2; exit 1; }
}
need nmap "sudo apt install nmap"
need python3 "sudo apt install python3 python3-venv"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || { echo "Python 3.11 or newer is required (found $(python3 --version))." >&2; exit 1; }

# ---- backend environment ----
VENV=backend/.venv
if [ ! -x "$VENV/bin/python" ]; then
  echo "==> Creating the Python environment (first run only)"
  if ! python3 -m venv "$VENV" >/dev/null 2>&1; then
    rm -rf "$VENV"
    command -v uv >/dev/null 2>&1 \
      || { echo "python3-venv is missing. Install it with: sudo apt install python3-venv" >&2; exit 1; }
    uv venv -q "$VENV"
  fi
fi
if [ ! -f "$VENV/.installed" ] || [ backend/pyproject.toml -nt "$VENV/.installed" ]; then
  echo "==> Installing the backend"
  if [ -x "$VENV/bin/pip" ]; then
    "$VENV/bin/pip" install -q -e backend
  else
    uv pip install -q -p "$VENV" -e backend
  fi
  touch "$VENV/.installed"
fi

# ---- frontend build (as the normal user, never as root) ----
if [ -d frontend ]; then
  if [ ! -f frontend/dist/index.html ] \
     || [ -n "$(find frontend/src frontend/index.html frontend/package.json -newer frontend/dist/index.html -print -quit)" ]; then
    need node "sudo apt install nodejs npm (Node 18 or newer)"
    node -e 'process.exit(parseInt(process.versions.node, 10) >= 18 ? 0 : 1)' \
      || { echo "Node 18 or newer is required (found $(node --version))." >&2; exit 1; }
    echo "==> Building the web interface"
    if [ ! -d frontend/node_modules ] || [ frontend/package-lock.json -nt frontend/node_modules/.package-lock.json ]; then
      (cd frontend && npm ci --no-audit --no-fund)
    fi
    (cd frontend && npm run build)
  fi
fi

# ---- data dir owned by the normal user, so --no-sudo runs can still write to it ----
mkdir -p data
[ -f data/visualnmap.db ] || : > data/visualnmap.db
export VISUALNMAP_DATA="$PWD/data"

if [ "$USE_SUDO" -eq 1 ]; then
  echo "==> Starting VisualNmap with sudo (needed for SYN, OS and UDP scans)"
  exec sudo --preserve-env=VISUALNMAP_HOST,VISUALNMAP_PORT,VISUALNMAP_DATA,VISUALNMAP_STATIC \
    "$VENV/bin/python" -m visualnmap
else
  echo "==> Starting VisualNmap without root"
  exec "$VENV/bin/python" -m visualnmap
fi
```

Run: `chmod +x run.sh && bash -n run.sh && echo syntax-ok`
Expected: `syntax-ok`.

- [ ] **Step 4: Smoke-test `run.sh` without sudo**

Run: `./run.sh --no-sudo & sleep 4; curl -s http://127.0.0.1:8765/api/status; kill %1`
Expected: the JSON shows `"nmap_found":true` and `"is_root":false`; on this Kali machine `"can_raw":true` (the nmap binary has `cap_net_raw`). `./run.sh --help` prints usage; `sudo ./run.sh` prints the "Run ./run.sh as your normal user" error.

(Ask your human partner to run `./run.sh` with sudo once by hand, since it needs their password, and confirm `"is_root":true`.)

- [ ] **Step 5: Commit**

```bash
git add run.sh backend/tests/test_e2e.py
git commit -m "feat: run.sh launcher and real-nmap end-to-end tests

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 10: Frontend scaffold, typed API client, app shell and Home page

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/index.html`
- Create: `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/styles.css`
- Create: `frontend/src/api/types.ts`, `frontend/src/api/client.ts`
- Create: `frontend/src/hooks/useAppData.tsx`
- Create: `frontend/src/components/StatusBanner.tsx`
- Create: `frontend/src/pages/Home.tsx`
- Create: `frontend/src/pages/Placeholder.tsx` (temporary stand-in for pages built in Tasks 11–14; deleted in Task 14)
- Create: `frontend/src/test/setup.ts`, `frontend/src/test/fixtures.ts`, `frontend/src/test/render.tsx`
- Test: `frontend/src/api/client.test.ts`, `frontend/src/components/StatusBanner.test.tsx`, `frontend/src/pages/Home.test.tsx`

**Interfaces:**
- Consumes: the HTTP contract table in Task 8.
- Produces:
  - `src/api/types.ts`: TypeScript mirrors of every backend model: `ValueSpec, OptionSpec, GroupSpec, ProfileOption, ProfileSpec, PortNote, Catalog, StatusInfo, OptionValue, ScanRequest, ExplainedPart, BuiltCommand, OsMatch, Port, Host, ScanStats, ParsedResult, Hint, ScanStatus, ScanSummary, ScanRecord, ServiceChange, HostDiff, ScanDiff, StreamEvent, ApiErrorBody`
  - `src/api/client.ts`: `class ApiError extends Error { status: number; body: ApiErrorBody; field?: string }`; `api.status()`, `api.catalog()`, `api.preview(req)`, `api.startScan(req) -> {scan_id}`, `api.listScans()`, `api.getScan(id)`, `api.cancelScan(id)`, `api.deleteScan(id)`, `api.compare(a, b)`, `api.exportUrl(id, "xml" | "json") -> string`; `openScanStream(id: string, onEvent: (e: StreamEvent) => void): () => void`
  - `src/hooks/useAppData.tsx`: `AppDataContext`, `AppDataProvider`, `useAppData(): { status: StatusInfo; catalog: Catalog; refreshStatus(): Promise<void> }`
  - `src/components/StatusBanner.tsx`: `StatusBanner({ status }: { status: StatusInfo })`
  - `src/test/fixtures.ts`: `catalogFixture`, `statusRoot`, `statusUser`, `statusNoNmap`, `statusDocker`, `recordFixture`, `diffFixture`
  - `src/test/render.tsx`: `renderWithData(ui, { status?, catalog?, route?, path? })`, which wraps in `MemoryRouter` + `AppDataContext.Provider`
  - Routes: `/` Home, `/guided`, `/builder`, `/scans/:id`, `/history`

- [ ] **Step 1: Create the project files**

`frontend/package.json`:

```json
{
  "name": "visualnmap-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "react-router-dom": "6.28.0"
  },
  "devDependencies": {
    "@testing-library/dom": "10.4.0",
    "@testing-library/jest-dom": "6.6.3",
    "@testing-library/react": "16.1.0",
    "@testing-library/user-event": "14.5.2",
    "@types/react": "18.3.12",
    "@types/react-dom": "18.3.1",
    "@vitejs/plugin-react": "4.3.4",
    "jsdom": "25.0.1",
    "typescript": "5.6.3",
    "vite": "5.4.11",
    "vitest": "2.1.8"
  }
}
```

`frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "vite.config.ts"]
}
```

`frontend/vite.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // changeOrigin stays false so the backend's Origin check sees matching Host and Origin headers.
    proxy: { "/api": { target: "http://127.0.0.1:8765", ws: true, changeOrigin: false } },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
```

`frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>VisualNmap</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Run: `cd frontend && npm install`
Expected: creates `node_modules/` and `package-lock.json`, with no errors.

- [ ] **Step 2: Types and API client**

`frontend/src/api/types.ts`:

```ts
// Mirrors backend/visualnmap/models.py and catalog/__init__.py. Keep in sync.
export interface ValueSpec {
  type: "int" | "ports" | "duration";
  min: number | null;
  max: number | null;
  default: string | number;
  placeholder: string | null;
}
export interface OptionSpec {
  id: string;
  flag: string;
  group: string;
  label: string;
  summary: string;
  details: string;
  when_to_use: string;
  requires_root: boolean;
  noise: "low" | "medium" | "high";
  speed_impact: "none" | "slower" | "much_slower";
  example: string;
  render: "flag" | "separate" | "attached";
  value: ValueSpec | null;
  expands_to: string[] | null;
  conflicts_with: string[];
}
export interface GroupSpec { id: string; label: string; description: string }
export interface ProfileOption { id: string; value: string | number | null }
export interface ProfileSpec {
  id: string;
  title: string;
  question: string;
  explanation: string;
  typical_duration: string;
  options: ProfileOption[];
  requires_root: boolean;
}
export interface PortNote { service: string; note: string }
export interface Catalog {
  groups: GroupSpec[];
  options: Record<string, OptionSpec>;
  profiles: Record<string, ProfileSpec>;
  ports: Record<string, PortNote>;
  states: Record<string, string>;
}
export interface StatusInfo {
  is_root: boolean;
  can_raw: boolean;
  nmap_found: boolean;
  nmap_version: string | null;
  in_container: boolean;
  active_scan_id: string | null;
}
export interface OptionValue { id: string; value?: string | number | null }
export interface ScanRequest { target: string; profile_id?: string | null; options: OptionValue[] }
export interface ExplainedPart { token: string; text: string; kind: "option" | "plumbing" | "target" }
export interface BuiltCommand { argv: string[]; parts: ExplainedPart[]; warnings: string[] }
export interface OsMatch { name: string; accuracy: number }
export interface Port {
  port: number;
  protocol: string;
  state: string;
  reason: string | null;
  service: string | null;
  product: string | null;
  version: string | null;
  extrainfo: string | null;
  note: string | null;
}
export interface Host {
  address: string;
  hostname: string | null;
  mac: string | null;
  vendor: string | null;
  status: string;
  reason: string | null;
  os_matches: OsMatch[];
  ports: Port[];
}
export interface ScanStats { up: number; down: number; total: number; elapsed_s: number | null }
export interface ParsedResult { hosts: Host[]; stats: ScanStats; partial: boolean }
export interface Hint { code: string; message: string; action: "retry_with_pn" | null }
export type ScanStatus = "running" | "completed" | "failed" | "cancelled";
export interface ScanSummary {
  id: string;
  created_at: string;
  finished_at: string | null;
  target: string;
  profile_id: string | null;
  status: ScanStatus;
  hosts_up: number;
  open_ports: number;
}
export interface ScanRecord extends ScanSummary {
  request: ScanRequest;
  argv: string[];
  result: ParsedResult | null;
  stderr_tail: string;
  hints: Hint[];
}
export interface ServiceChange { port: string; before: string; after: string }
export interface HostDiff { ports_opened: string[]; ports_closed: string[]; services_changed: ServiceChange[] }
export interface ScanDiff {
  a: string;
  b: string;
  hosts_added: string[];
  hosts_removed: string[];
  per_host: Record<string, HostDiff>;
}
export type StreamEvent =
  | { type: "output"; line: string }
  | { type: "progress"; task: string; percent: number | null; eta: string | null }
  | { type: "done"; status: ScanStatus }
  | { type: "error"; message: string };
export interface ApiErrorBody { field?: string; message?: string; active_scan_id?: string; detail?: unknown }
```

`frontend/src/api/client.ts`:

```ts
import type {
  ApiErrorBody, BuiltCommand, Catalog, ScanDiff, ScanRecord, ScanRequest, ScanSummary, StatusInfo, StreamEvent,
} from "./types";

export class ApiError extends Error {
  status: number;
  body: ApiErrorBody;
  field?: string;
  constructor(status: number, body: ApiErrorBody) {
    super(body.message ?? `Request failed (${status})`);
    this.status = status;
    this.body = body;
    this.field = body.field;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!resp.ok) {
    let body: ApiErrorBody = {};
    try {
      body = await resp.json();
    } catch {
      /* non-JSON error body */
    }
    if (!body.message && typeof body.detail === "string") body.message = body.detail;
    throw new ApiError(resp.status, body);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

const post = (body?: unknown): RequestInit => ({ method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  status: () => request<StatusInfo>("/api/status"),
  catalog: () => request<Catalog>("/api/catalog"),
  preview: (req: ScanRequest) => request<BuiltCommand>("/api/command/preview", post(req)),
  startScan: (req: ScanRequest) => request<{ scan_id: string }>("/api/scans", post(req)),
  listScans: () => request<ScanSummary[]>("/api/scans"),
  getScan: (id: string) => request<ScanRecord>(`/api/scans/${encodeURIComponent(id)}`),
  cancelScan: (id: string) => request<{ status: string }>(`/api/scans/${encodeURIComponent(id)}/cancel`, post()),
  deleteScan: (id: string) => request<void>(`/api/scans/${encodeURIComponent(id)}`, { method: "DELETE" }),
  compare: (a: string, b: string) =>
    request<ScanDiff>(`/api/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`),
  exportUrl: (id: string, format: "xml" | "json") => `/api/scans/${encodeURIComponent(id)}/export?format=${format}`,
};

export function openScanStream(id: string, onEvent: (event: StreamEvent) => void): () => void {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${window.location.host}/api/scans/${encodeURIComponent(id)}/stream`);
  ws.onmessage = (msg) => onEvent(JSON.parse(msg.data) as StreamEvent);
  return () => ws.close();
}
```

- [ ] **Step 3: App data context, test helpers and fixtures**

`frontend/src/hooks/useAppData.tsx`:

```tsx
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { Catalog, StatusInfo } from "../api/types";

export interface AppData {
  status: StatusInfo;
  catalog: Catalog;
  refreshStatus: () => Promise<void>;
}

export const AppDataContext = createContext<AppData | null>(null);

export function AppDataProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<StatusInfo | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshStatus = useCallback(async () => {
    setStatus(await api.status());
  }, []);

  useEffect(() => {
    Promise.all([api.status(), api.catalog()])
      .then(([s, c]) => {
        setStatus(s);
        setCatalog(c);
      })
      .catch(() => setError("Can't reach the VisualNmap server. Is ./run.sh still running?"));
  }, []);

  if (error) return <div className="banner banner-error" role="alert">{error}</div>;
  if (!status || !catalog) return <p className="loading">Loading VisualNmap…</p>;
  return <AppDataContext.Provider value={{ status, catalog, refreshStatus }}>{children}</AppDataContext.Provider>;
}

export function useAppData(): AppData {
  const value = useContext(AppDataContext);
  if (!value) throw new Error("useAppData must be used inside AppDataProvider");
  return value;
}
```

`frontend/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

`frontend/src/test/fixtures.ts`:

```ts
import type { Catalog, OptionSpec, ScanDiff, ScanRecord, StatusInfo } from "../api/types";

function opt(partial: Partial<OptionSpec> & Pick<OptionSpec, "id" | "flag" | "group" | "label">): OptionSpec {
  return {
    summary: `${partial.label} summary`,
    details: `${partial.label} details`,
    when_to_use: `${partial.label} when`,
    requires_root: false,
    noise: "low",
    speed_impact: "none",
    example: `nmap ${partial.flag} 10.0.0.1`,
    render: "flag",
    value: null,
    expands_to: null,
    conflicts_with: [],
    ...partial,
  };
}

export const catalogFixture: Catalog = {
  groups: [
    { id: "discovery", label: "Host discovery", description: "Which hosts are alive." },
    { id: "technique", label: "Scan technique", description: "How ports are probed." },
    { id: "ports", label: "Ports", description: "Which ports." },
    { id: "detection", label: "Service and OS detection", description: "What runs there." },
    { id: "timing", label: "Timing", description: "How fast." },
  ],
  options: {
    ping_only: opt({ id: "ping_only", flag: "-sn", group: "discovery", label: "Ping scan only" }),
    skip_ping: opt({ id: "skip_ping", flag: "-Pn", group: "discovery", label: "Skip host discovery" }),
    syn_scan: opt({ id: "syn_scan", flag: "-sS", group: "technique", label: "SYN scan", requires_root: true }),
    connect_scan: opt({ id: "connect_scan", flag: "-sT", group: "technique", label: "TCP connect scan" }),
    fast: opt({ id: "fast", flag: "-F", group: "ports", label: "Fast (top 100 ports)" }),
    ports: opt({
      id: "ports", flag: "-p", group: "ports", label: "Specific ports", render: "separate",
      value: { type: "ports", min: null, max: null, default: "22,80,443", placeholder: "22,80,443" },
    }),
    service_version: opt({ id: "service_version", flag: "-sV", group: "detection", label: "Detect service versions" }),
    timing: opt({
      id: "timing", flag: "-T", group: "timing", label: "Timing template (0-5)", render: "attached",
      value: { type: "int", min: 0, max: 5, default: 3, placeholder: null },
    }),
  },
  profiles: {
    find_devices: {
      id: "find_devices", title: "Find devices", question: "Which devices are on my network?",
      explanation: "Ping sweep.", typical_duration: "10-30 seconds", options: [{ id: "ping_only", value: null }],
      requires_root: false,
    },
    quick_ports: {
      id: "quick_ports", title: "Quick port check", question: "What's open on a machine? (fast)",
      explanation: "Top 100 ports.", typical_duration: "a few seconds",
      options: [{ id: "fast", value: null }, { id: "timing", value: 4 }], requires_root: false,
    },
    stealth: {
      id: "stealth", title: "Quiet scan", question: "Scan quietly", explanation: "Slow SYN scan.",
      typical_duration: "1-3 minutes", options: [{ id: "syn_scan", value: null }], requires_root: true,
    },
  },
  ports: { "22": { service: "ssh", note: "Remote command-line access (SSH)." } },
  states: {
    open: "Something is listening.",
    closed: "Reachable, nothing listening.",
    filtered: "Blocked by a firewall.",
  },
};

const baseStatus: StatusInfo = {
  is_root: true, can_raw: true, nmap_found: true, nmap_version: "7.99", in_container: false, active_scan_id: null,
};
export const statusRoot: StatusInfo = baseStatus;
export const statusUser: StatusInfo = { ...baseStatus, is_root: false, can_raw: false };
export const statusNoNmap: StatusInfo = { ...baseStatus, nmap_found: false, nmap_version: null };
export const statusDocker: StatusInfo = { ...baseStatus, in_container: true };

export const recordFixture: ScanRecord = {
  id: "abc123",
  created_at: "2026-10-14T18:48:31+00:00",
  finished_at: "2026-10-14T18:48:43+00:00",
  target: "192.168.1.10",
  profile_id: "quick_ports",
  status: "completed",
  hosts_up: 1,
  open_ports: 2,
  request: { target: "192.168.1.10", profile_id: "quick_ports", options: [] },
  argv: ["nmap", "-F", "-T4", "-v", "--stats-every", "2s", "-oX", "-", "192.168.1.10"],
  stderr_tail: "",
  hints: [],
  result: {
    partial: false,
    stats: { up: 1, down: 0, total: 1, elapsed_s: 12.5 },
    hosts: [
      {
        address: "192.168.1.10", hostname: "pi.lan", mac: "AA:BB:CC:DD:EE:FF", vendor: "Raspberry Pi Foundation",
        status: "up", reason: "arp-response",
        os_matches: [{ name: "Linux 5.0 - 5.14", accuracy: 96 }],
        ports: [
          { port: 22, protocol: "tcp", state: "open", reason: "syn-ack", service: "ssh", product: "OpenSSH",
            version: "8.9p1", extrainfo: null, note: "Remote command-line access (SSH)." },
          { port: 80, protocol: "tcp", state: "open", reason: "syn-ack", service: "http", product: "nginx",
            version: "1.24.0", extrainfo: null, note: null },
          { port: 445, protocol: "tcp", state: "filtered", reason: "no-response", service: "microsoft-ds",
            product: null, version: null, extrainfo: null, note: null },
        ],
      },
    ],
  },
};

export const diffFixture: ScanDiff = {
  a: "aaa",
  b: "bbb",
  hosts_added: ["10.0.0.7"],
  hosts_removed: ["10.0.0.9"],
  per_host: {
    "10.0.0.1": {
      ports_opened: ["8080/tcp"],
      ports_closed: ["80/tcp"],
      services_changed: [{ port: "22/tcp", before: "ssh OpenSSH 8.9", after: "ssh OpenSSH 9.6" }],
    },
  },
};
```

`frontend/src/test/render.tsx`:

```tsx
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { Catalog, StatusInfo } from "../api/types";
import { AppDataContext } from "../hooks/useAppData";
import { catalogFixture, statusRoot } from "./fixtures";

interface Options {
  status?: StatusInfo;
  catalog?: Catalog;
  route?: string; // URL to start at, e.g. "/scans/abc123"
  path?: string; // route pattern the ui is mounted on, e.g. "/scans/:id"
}

export function renderWithData(ui: ReactElement, { status = statusRoot, catalog = catalogFixture, route = "/", path = "*" }: Options = {}) {
  const refreshStatus = vi.fn(async () => {});
  const result = render(
    <AppDataContext.Provider value={{ status, catalog, refreshStatus }}>
      <MemoryRouter initialEntries={[route]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path={path} element={ui} />
          <Route path="/scans/:id" element={<div>SCAN PAGE</div>} />
        </Routes>
      </MemoryRouter>
    </AppDataContext.Provider>,
  );
  return { ...result, refreshStatus };
}
```

- [ ] **Step 4: Write the failing tests**

`frontend/src/api/client.test.ts`:

```ts
import { ApiError, api } from "./client";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

test("preview posts the request as JSON", async () => {
  const fetchFn = mockFetch(200, { argv: ["nmap"], parts: [], warnings: [] });
  await api.preview({ target: "10.0.0.1", options: [] });
  const [url, init] = fetchFn.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe("/api/command/preview");
  expect(init.method).toBe("POST");
  expect(JSON.parse(init.body as string)).toEqual({ target: "10.0.0.1", options: [] });
});

test("errors carry the backend field and message", async () => {
  mockFetch(422, { field: "target", message: "bad target" });
  await expect(api.preview({ target: "-x", options: [] })).rejects.toMatchObject({
    status: 422, field: "target", message: "bad target",
  });
});

test("string detail becomes the message", async () => {
  mockFetch(403, { detail: "Cross-site request blocked." });
  const err = await api.startScan({ target: "x", options: [] }).catch((e) => e);
  expect(err).toBeInstanceOf(ApiError);
  expect(err.message).toBe("Cross-site request blocked.");
});

test("204 resolves to undefined", async () => {
  mockFetch(204, undefined);
  await expect(api.deleteScan("abc")).resolves.toBeUndefined();
});

test("exportUrl", () => {
  expect(api.exportUrl("abc", "xml")).toBe("/api/scans/abc/export?format=xml");
});
```

`frontend/src/components/StatusBanner.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { statusDocker, statusNoNmap, statusRoot, statusUser } from "../test/fixtures";
import { StatusBanner } from "./StatusBanner";

test("nothing to say when all is well", () => {
  const { container } = render(<StatusBanner status={statusRoot} />);
  expect(container).toBeEmptyDOMElement();
});

test("nmap missing shows install command", () => {
  render(<StatusBanner status={statusNoNmap} />);
  expect(screen.getByRole("alert")).toHaveTextContent("sudo apt install nmap");
});

test("no raw sockets explains how to unlock", () => {
  render(<StatusBanner status={statusUser} />);
  expect(screen.getByText(/Started without sudo/)).toBeInTheDocument();
  expect(screen.getByText(/\.\/run\.sh/)).toBeInTheDocument();
});

test("docker notice", () => {
  render(<StatusBanner status={statusDocker} />);
  expect(screen.getByText(/Running in Docker/)).toBeInTheDocument();
});
```

`frontend/src/pages/Home.test.tsx`:

```tsx
import { screen } from "@testing-library/react";
import { renderWithData } from "../test/render";
import { Home } from "./Home";

test("offers both modes and the permission reminder", () => {
  renderWithData(<Home />);
  expect(screen.getByRole("link", { name: /Guide me/ })).toHaveAttribute("href", "/guided");
  expect(screen.getByRole("link", { name: /I know what I want/ })).toHaveAttribute("href", "/builder");
  expect(screen.getByText(/What is Nmap\?/)).toBeInTheDocument();
  expect(screen.getByText(/permission/i)).toBeInTheDocument();
});
```

- [ ] **Step 5: Run to verify failure**

Run: `cd frontend && npx vitest run`
Expected: FAIL. `client.test.ts` passes (the client exists), and the StatusBanner and Home tests fail with "Failed to resolve import" for `./StatusBanner` and `./Home`.

- [ ] **Step 6: Implement the banner, Home page, app shell and styles**

`frontend/src/components/StatusBanner.tsx`:

```tsx
import type { StatusInfo } from "../api/types";

export function StatusBanner({ status }: { status: StatusInfo }) {
  const banners = [];
  if (!status.nmap_found) {
    banners.push(
      <div key="nmap" className="banner banner-error" role="alert">
        <strong>Nmap is not installed.</strong> Install it with <code>sudo apt install nmap</code>, then restart VisualNmap.
      </div>,
    );
  }
  if (!status.can_raw) {
    banners.push(
      <div key="root" className="banner banner-warn">
        <strong>Started without sudo:</strong> options marked 🔒 are disabled because they need raw network access.
        Restart with <code>./run.sh</code> (it uses sudo) to unlock them.
      </div>,
    );
  }
  if (status.in_container) {
    banners.push(
      <div key="docker" className="banner banner-info">
        <strong>Running in Docker:</strong> LAN device discovery is limited, and <code>localhost</code> means the
        container. Scan your PC by its LAN IP instead.
      </div>,
    );
  }
  if (banners.length === 0) return null;
  return <div className="banners">{banners}</div>;
}
```

`frontend/src/pages/Home.tsx`:

```tsx
import { Link } from "react-router-dom";

export function Home() {
  return (
    <div className="home">
      <div className="mode-cards">
        <Link to="/guided" className="mode-card">
          <span className="mode-icon" aria-hidden>🧭</span>
          <span className="mode-title">Guide me</span>
          <span className="mode-text">Answer four simple questions and VisualNmap builds the right scan, explaining every step.</span>
        </Link>
        <Link to="/builder" className="mode-card">
          <span className="mode-icon" aria-hidden>⚡</span>
          <span className="mode-title">I know what I want</span>
          <span className="mode-text">Every supported option on one screen, grouped by purpose, with the exact command always visible.</span>
        </Link>
      </div>
      <section className="card">
        <h2>What is Nmap?</h2>
        <p>
          Nmap ("Network Mapper") is a free tool that sends carefully crafted packets to computers and reads the replies.
          From those replies it works out which devices are online, which ports (doors into a computer) are open, what
          software is listening behind them, and often which operating system a device runs.
        </p>
        <p>
          Network admins use it to keep an inventory and spot things that shouldn't be exposed; security testers use it as
          the first step of an assessment. VisualNmap shows you the exact nmap command it runs, so you learn the real tool
          as you go.
        </p>
      </section>
      <p className="legal">
        ⚠️ Only scan computers and networks you own or have written permission to test. Good practice targets: your own
        router, your own PCs, lab VMs, and <code>scanme.nmap.org</code>.
      </p>
    </div>
  );
}
```

`frontend/src/pages/Placeholder.tsx`:

```tsx
export function Placeholder({ name }: { name: string }) {
  return <p className="muted">{name} page coming soon.</p>;
}
```

`frontend/src/App.tsx`:

```tsx
import { NavLink, Route, Routes } from "react-router-dom";
import { StatusBanner } from "./components/StatusBanner";
import { useAppData } from "./hooks/useAppData";
import { Home } from "./pages/Home";
import { Placeholder } from "./pages/Placeholder";

export function App() {
  const { status } = useAppData();
  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand">VisualNmap</NavLink>
        <nav>
          <NavLink to="/" end>Home</NavLink>
          <NavLink to="/guided">Guided</NavLink>
          <NavLink to="/builder">Builder</NavLink>
          <NavLink to="/history">History</NavLink>
        </nav>
        <span className={`badge ${status.can_raw ? "badge-ok" : "badge-warn"}`} title="Whether 🔒 options are available">
          {status.can_raw ? "🔒 unlocked" : "no root"}
        </span>
      </header>
      <StatusBanner status={status} />
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/guided" element={<Placeholder name="Guided" />} />
          <Route path="/builder" element={<Placeholder name="Builder" />} />
          <Route path="/scans/:id" element={<Placeholder name="Scan" />} />
          <Route path="/history" element={<Placeholder name="History" />} />
        </Routes>
      </main>
    </div>
  );
}
```

`frontend/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { AppDataProvider } from "./hooks/useAppData";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppDataProvider>
        <App />
      </AppDataProvider>
    </BrowserRouter>
  </StrictMode>,
);
```

`frontend/src/styles.css`:

```css
:root {
  --bg: #f6f7f9; --surface: #ffffff; --text: #1d232b; --muted: #5d6875; --border: #d9dee4;
  --accent: #1f6feb; --ok: #1a7f37; --warn: #9a6700; --error: #cf222e; --info: #0969da;
  --ok-bg: #dafbe1; --warn-bg: #fff8c5; --error-bg: #ffebe9; --info-bg: #ddf4ff;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --term-bg: #0d1117; --term-text: #c9d1d9;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117; --surface: #161b22; --text: #e6edf3; --muted: #8d96a0; --border: #30363d;
    --accent: #4493f8; --ok: #3fb950; --warn: #d29922; --error: #f85149; --info: #58a6ff;
    --ok-bg: #12261e; --warn-bg: #272115; --error-bg: #2d1517; --info-bg: #121d2f;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 system-ui, sans-serif; }
code, pre, .mono { font-family: var(--mono); }
a { color: var(--accent); }
.app { max-width: 1100px; margin: 0 auto; padding: 0 16px 120px; }
.topbar { display: flex; align-items: center; gap: 24px; padding: 14px 0; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.topbar nav { display: flex; gap: 16px; flex: 1; }
.topbar a { text-decoration: none; color: var(--muted); }
.topbar a.active { color: var(--text); font-weight: 600; }
.brand { font-weight: 700; font-size: 18px; color: var(--text) !important; }
.badge { font-size: 12px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border); }
.badge-ok { color: var(--ok); background: var(--ok-bg); }
.badge-warn { color: var(--warn); background: var(--warn-bg); }
.banners { display: grid; gap: 8px; margin-top: 12px; }
.banner { padding: 10px 14px; border-radius: 8px; border: 1px solid var(--border); }
.banner-error { background: var(--error-bg); color: var(--error); }
.banner-warn { background: var(--warn-bg); color: var(--warn); }
.banner-info { background: var(--info-bg); color: var(--info); }
main { padding-top: 20px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px 20px; margin-bottom: 16px; }
.muted, .loading { color: var(--muted); }
.legal { color: var(--warn); }
.mode-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin-bottom: 20px; }
.mode-card { display: grid; gap: 6px; padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; text-decoration: none; color: var(--text); }
.mode-card:hover { border-color: var(--accent); }
.mode-icon { font-size: 28px; }
.mode-title { font-size: 18px; font-weight: 600; }
.mode-text { color: var(--muted); }
button { font: inherit; padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border); background: var(--surface); color: var(--text); cursor: pointer; }
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
input[type="text"], input[type="number"], select { font: inherit; padding: 6px 10px; border-radius: 6px; border: 1px solid var(--border); background: var(--surface); color: var(--text); }
.field-error { color: var(--error); font-size: 13px; margin-top: 4px; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: 13px; }
```

- [ ] **Step 7: Run tests and the type check**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: 10 tests passed; tsc prints nothing.

- [ ] **Step 8: Build and view it through the backend**

Run: `cd frontend && npm run build` (expected: `dist/index.html` created), then `./run.sh --no-sudo` from the repo root and open http://127.0.0.1:8765.
Expected: the Home page shows both mode cards, the nav, and the `🔒 unlocked` badge (Kali caps) with no banners.

- [ ] **Step 9: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html frontend/src
git commit -m "feat(frontend): scaffold, typed API client, app shell and Home page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 11: Command bar, option explanations, target input and the Builder page

**Files:**
- Create: `frontend/src/components/CommandBar.tsx`, `frontend/src/components/OptionInfo.tsx`, `frontend/src/components/TargetInput.tsx`, `frontend/src/components/RunError.tsx`
- Create: `frontend/src/hooks/usePreview.ts`, `frontend/src/hooks/useRunScan.ts`
- Create: `frontend/src/lib/request.ts`
- Create: `frontend/src/pages/Builder.tsx`
- Modify: `frontend/src/App.tsx` (route `/builder` → `<Builder />`)
- Modify: `frontend/src/styles.css` (append command bar / builder styles)
- Modify: `frontend/src/test/fixtures.ts` (append `commandFixture`)
- Test: `frontend/src/components/CommandBar.test.tsx`, `frontend/src/components/OptionInfo.test.tsx`, `frontend/src/pages/Builder.test.tsx`

**Interfaces:**
- Consumes: `api`, `ApiError` (Task 10); types (Task 10); `useAppData` (Task 10); `renderWithData`, fixtures (Task 10).
- Produces:
  - `CommandBar(props: { command: BuiltCommand | null; error?: ApiError | null; onRun?: () => void; runDisabled?: boolean; runLabel?: string; sticky?: boolean; showAll?: boolean })`
  - `OptionInfo({ option }: { option: OptionSpec })`
  - `TargetInput({ value, onChange, error, autoFocus }: { value: string; onChange(v: string): void; error?: string; autoFocus?: boolean })`
  - `RunError({ error }: { error: ApiError | null })`
  - `usePreview(request: ScanRequest | null, delay = 250): { command: BuiltCommand | null; error: ApiError | null }`
  - `useRunScan(): { run(req: ScanRequest): Promise<void>; busy: boolean; error: ApiError | null }`, which navigates to `/scans/:id` on success
  - `lib/request.ts`: `type Selected = Record<string, string | number | null>`; `requestToSelected(req: ScanRequest, catalog: Catalog): Selected`; `selectedToRequest(target: string, selected: Selected): ScanRequest`
  - `Builder` page reads optional router state `{ request?: ScanRequest }` to pre-fill
  - `commandFixture: BuiltCommand` in `test/fixtures.ts`

- [ ] **Step 1: Add the command fixture**

In `frontend/src/test/fixtures.ts`, change the first line to
`import type { BuiltCommand, Catalog, OptionSpec, ScanDiff, ScanRecord, StatusInfo } from "../api/types";`
and append:

```ts
export const commandFixture: BuiltCommand = {
  argv: ["/usr/bin/nmap", "-F", "-v", "--stats-every", "2s", "-oX", "-", "10.0.0.1"],
  parts: [
    { token: "-F", text: "Checks only the 100 most common ports.", kind: "option" },
    { token: "-v", text: "App plumbing: makes nmap report its progress.", kind: "plumbing" },
    { token: "--stats-every 2s", text: "App plumbing: a progress update every 2 seconds.", kind: "plumbing" },
    { token: "-oX -", text: "App plumbing: results as XML.", kind: "plumbing" },
    { token: "10.0.0.1", text: "What to scan: 1 address.", kind: "target" },
  ],
  warnings: [],
};
```

- [ ] **Step 2: Write the failing tests**

`frontend/src/components/CommandBar.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../api/client";
import { commandFixture } from "../test/fixtures";
import { CommandBar } from "./CommandBar";

test("shows each part and explains it on hover", async () => {
  const user = userEvent.setup();
  render(<CommandBar command={commandFixture} />);
  expect(screen.getByText("$ nmap")).toBeInTheDocument();
  await user.hover(screen.getByRole("button", { name: "-F" }));
  expect(screen.getByText(/Checks only the 100 most common ports/)).toBeInTheDocument();
});

test("plumbing tokens are marked", () => {
  render(<CommandBar command={commandFixture} />);
  expect(screen.getByRole("button", { name: "-oX -" })).toHaveClass("token-plumbing");
  expect(screen.getByRole("button", { name: "10.0.0.1" })).toHaveClass("token-target");
});

test("copy puts a runnable command on the clipboard", async () => {
  const user = userEvent.setup();
  render(<CommandBar command={commandFixture} />);
  await user.click(screen.getByRole("button", { name: "Copy" }));
  expect(await navigator.clipboard.readText()).toBe("nmap -F -v --stats-every 2s -oX - 10.0.0.1");
});

test("run button and warnings", async () => {
  const user = userEvent.setup();
  const onRun = vi.fn();
  render(<CommandBar command={{ ...commandFixture, warnings: ["Big scan ahead"] }} onRun={onRun} />);
  expect(screen.getByText(/Big scan ahead/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Run scan" }));
  expect(onRun).toHaveBeenCalledOnce();
});

test("run disabled without a command", () => {
  render(<CommandBar command={null} onRun={() => {}} />);
  expect(screen.getByRole("button", { name: "Run scan" })).toBeDisabled();
});

test("general errors are shown, inline-field errors are not", () => {
  const { rerender } = render(<CommandBar command={null} error={new ApiError(422, { field: "options", message: "Can't combine" })} />);
  expect(screen.getByText("Can't combine")).toBeInTheDocument();
  rerender(<CommandBar command={null} error={new ApiError(422, { field: "target", message: "Bad target" })} />);
  expect(screen.queryByText("Bad target")).not.toBeInTheDocument();
});

test("showAll lists every part with its explanation", () => {
  render(<CommandBar command={commandFixture} showAll />);
  expect(screen.getByText("What to scan: 1 address.")).toBeInTheDocument();
  expect(screen.getByText("App plumbing: results as XML.")).toBeInTheDocument();
});
```

`frontend/src/components/OptionInfo.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { catalogFixture } from "../test/fixtures";
import { OptionInfo } from "./OptionInfo";

test("toggles the full explanation", async () => {
  const user = userEvent.setup();
  render(<OptionInfo option={catalogFixture.options.syn_scan} />);
  expect(screen.queryByText("SYN scan details")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "About SYN scan" }));
  expect(screen.getByText("SYN scan details")).toBeInTheDocument();
  expect(screen.getByText(/needs root/)).toBeInTheDocument();
  expect(screen.getByText("nmap -sS 10.0.0.1")).toBeInTheDocument();
});
```

`frontend/src/pages/Builder.test.tsx`:

```tsx
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError, api } from "../api/client";
import type { StatusInfo } from "../api/types";
import { commandFixture, statusUser } from "../test/fixtures";
import { renderWithData } from "../test/render";
import { Builder } from "./Builder";

vi.mock("../api/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../api/client")>();
  return { ...mod, api: { ...mod.api, preview: vi.fn(), startScan: vi.fn() } };
});

const preview = vi.mocked(api.preview);
const startScan = vi.mocked(api.startScan);

beforeEach(() => {
  preview.mockReset().mockResolvedValue(commandFixture);
  startScan.mockReset();
});

const renderBuilder = (status?: StatusInfo) =>
  renderWithData(<Builder />, { route: "/builder", path: "/builder", status });

async function clickRunWhenReady(user: ReturnType<typeof userEvent.setup>) {
  const button = await screen.findByRole("button", { name: "Run scan" });
  await waitFor(() => expect(button).toBeEnabled());
  await user.click(button);
}

test("shows option groups with explanations", () => {
  renderBuilder();
  expect(screen.getByRole("group", { name: "Ports" })).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: /Fast \(top 100 ports\)/ })).toBeInTheDocument();
});

test("root-only options are disabled without raw access", () => {
  renderBuilder(statusUser);
  expect(screen.getByRole("checkbox", { name: /SYN scan/ })).toBeDisabled();
  expect(screen.getByRole("option", { name: /Quiet scan/ })).toBeDisabled();
});

test("root-only options are enabled as root", () => {
  renderBuilder();
  expect(screen.getByRole("checkbox", { name: /SYN scan/ })).toBeEnabled();
});

test("previews the request as options are chosen", async () => {
  const user = userEvent.setup();
  renderBuilder();
  await user.type(screen.getByLabelText(/Target/), "10.0.0.1");
  await user.click(screen.getByRole("checkbox", { name: /Fast/ }));
  await waitFor(() =>
    expect(preview).toHaveBeenLastCalledWith({ target: "10.0.0.1", options: [{ id: "fast", value: null }] }),
  );
  expect(await screen.findByRole("button", { name: "-F" })).toBeInTheDocument();
});

test("start from profile fills the options", async () => {
  const user = userEvent.setup();
  renderBuilder();
  await user.selectOptions(screen.getByLabelText("Start from profile"), "quick_ports");
  expect(screen.getByRole("checkbox", { name: /Fast/ })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: /Timing template/ })).toBeChecked();
  expect(screen.getByLabelText("Timing template (0-5) value")).toHaveValue(4);
});

test("field errors appear next to the option", async () => {
  preview.mockRejectedValue(new ApiError(422, { field: "options.ports", message: "Specific ports: each port must be between 1 and 65535." }));
  const user = userEvent.setup();
  renderBuilder();
  await user.type(screen.getByLabelText(/Target/), "10.0.0.1");
  await user.click(screen.getByRole("checkbox", { name: /Specific ports/ }));
  expect(await screen.findByText(/each port must be between 1 and 65535/)).toBeInTheDocument();
});

test("run starts the scan and opens it", async () => {
  startScan.mockResolvedValue({ scan_id: "xyz" });
  const user = userEvent.setup();
  renderBuilder();
  await user.type(screen.getByLabelText(/Target/), "10.0.0.1");
  await clickRunWhenReady(user);
  expect(startScan).toHaveBeenCalledWith({ target: "10.0.0.1", options: [] });
  expect(await screen.findByText("SCAN PAGE")).toBeInTheDocument();
});

test("busy scanner shows a link to the running scan", async () => {
  startScan.mockRejectedValue(new ApiError(409, { message: "Another scan is already running.", active_scan_id: "zzz" }));
  const user = userEvent.setup();
  renderBuilder();
  await user.type(screen.getByLabelText(/Target/), "10.0.0.1");
  await clickRunWhenReady(user);
  expect(await screen.findByRole("alert")).toHaveTextContent("Another scan is already running.");
  expect(screen.getByRole("link", { name: "Open the running scan" })).toHaveAttribute("href", "/scans/zzz");
});
```

- [ ] **Step 3: Run to verify failure**

Run: `cd frontend && npx vitest run src/components src/pages/Builder.test.tsx`
Expected: FAIL with "Failed to resolve import" for `./CommandBar`, `./OptionInfo` and `./Builder`.

- [ ] **Step 4: Implement hooks and helpers**

`frontend/src/lib/request.ts`:

```ts
import type { Catalog, ScanRequest } from "../api/types";

export type Selected = Record<string, string | number | null>;

export function requestToSelected(req: ScanRequest, catalog: Catalog): Selected {
  const selected: Selected = {};
  const profile = req.profile_id ? catalog.profiles[req.profile_id] : undefined;
  for (const po of profile?.options ?? []) selected[po.id] = po.value;
  for (const ov of req.options) selected[ov.id] = ov.value ?? null;
  return selected;
}

export function selectedToRequest(target: string, selected: Selected): ScanRequest {
  return { target, options: Object.entries(selected).map(([id, value]) => ({ id, value })) };
}
```

`frontend/src/hooks/usePreview.ts`:

```ts
import { useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import type { BuiltCommand, ScanRequest } from "../api/types";

export function usePreview(request: ScanRequest | null, delay = 250) {
  const [command, setCommand] = useState<BuiltCommand | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const key = request && request.target.trim() ? JSON.stringify(request) : null;

  useEffect(() => {
    if (!key) {
      setCommand(null);
      setError(null);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      api
        .preview(JSON.parse(key) as ScanRequest)
        .then((built) => {
          if (cancelled) return;
          setCommand(built);
          setError(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setCommand(null);
          setError(err instanceof ApiError ? err : new ApiError(0, { message: String(err) }));
        });
    }, delay);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [key, delay]);

  return { command, error };
}
```

`frontend/src/hooks/useRunScan.ts`:

```ts
import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { ScanRequest } from "../api/types";
import { useAppData } from "./useAppData";

export function useRunScan() {
  const navigate = useNavigate();
  const { refreshStatus } = useAppData();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const run = useCallback(
    async (req: ScanRequest) => {
      setBusy(true);
      setError(null);
      try {
        const { scan_id } = await api.startScan(req);
        void refreshStatus().catch(() => {});
        navigate(`/scans/${scan_id}`);
      } catch (err) {
        setError(err instanceof ApiError ? err : new ApiError(0, { message: String(err) }));
      } finally {
        setBusy(false);
      }
    },
    [navigate, refreshStatus],
  );

  return { run, busy, error };
}
```

- [ ] **Step 5: Implement the components**

`frontend/src/components/CommandBar.tsx`:

```tsx
import { useState } from "react";
import type { ApiError } from "../api/client";
import type { BuiltCommand } from "../api/types";

interface Props {
  command: BuiltCommand | null;
  error?: ApiError | null;
  onRun?: () => void;
  runDisabled?: boolean;
  runLabel?: string;
  sticky?: boolean;
  showAll?: boolean;
}

// Errors on these fields are shown next to the field itself, so the bar doesn't repeat them.
const isInlineField = (field?: string) => field === "target" || (field ?? "").startsWith("options.");

export function CommandBar({ command, error, onRun, runDisabled, runLabel = "Run scan", sticky = true, showAll = false }: Props) {
  const [active, setActive] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const text = command ? ["nmap", ...command.argv.slice(1)].join(" ") : "";
  const activePart = command && active !== null ? command.parts[active] : null;

  const copy = async () => {
    await navigator.clipboard?.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <section className={`command-bar${sticky ? " sticky" : ""}`} aria-label="Command preview">
      <div className="command-line">
        <code className="command-tokens">
          <span className="prompt">$ nmap</span>
          {command?.parts.map((part, i) => (
            <button
              key={`${i}-${part.token}`}
              type="button"
              className={`token token-${part.kind}`}
              onMouseEnter={() => setActive(i)}
              onFocus={() => setActive(i)}
              onClick={() => setActive(i)}
            >
              {part.token}
            </button>
          ))}
          {!command && <span className="muted"> … enter a target to see the command</span>}
        </code>
        <div className="command-actions">
          <button type="button" onClick={copy} disabled={!command}>{copied ? "Copied!" : "Copy"}</button>
          {onRun && (
            <button type="button" className="primary" onClick={onRun} disabled={!command || runDisabled}>
              {runLabel}
            </button>
          )}
        </div>
      </div>
      <p className="command-explain" aria-live="polite">
        {activePart ? (
          <>
            <code>{activePart.token}</code>: {activePart.text}
          </>
        ) : command ? (
          "Hover over or tap any part of the command to see what it does."
        ) : null}
      </p>
      {error && !isInlineField(error.field) && <p className="field-error">{error.message}</p>}
      {command?.warnings.map((w) => <p key={w} className="warning">⚠️ {w}</p>)}
      {showAll && command && (
        <dl className="parts-list">
          {command.parts.map((part, i) => (
            <div key={`${i}-${part.token}`} className={`part part-${part.kind}`}>
              <dt><code>{part.token}</code></dt>
              <dd>{part.text}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
```

`frontend/src/components/OptionInfo.tsx`:

```tsx
import { useState } from "react";
import type { OptionSpec } from "../api/types";

const NOISE = { low: "low (rarely noticed)", medium: "medium", high: "high (likely to be logged)" };
const SPEED = { none: "no slowdown", slower: "slower", much_slower: "much slower" };

export function OptionInfo({ option }: { option: OptionSpec }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="option-info">
      <button type="button" className="info-btn" aria-label={`About ${option.label}`} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        ⓘ
      </button>
      {open && (
        <div className="info-pop" role="note">
          <p><strong>{option.summary}</strong></p>
          <p>{option.details}</p>
          <p><em>When to use:</em> {option.when_to_use}</p>
          <p className="meta">
            Noise: {NOISE[option.noise]} · Speed: {SPEED[option.speed_impact]}
            {option.requires_root ? " · 🔒 needs root" : ""}
          </p>
          <p>Example: <code>{option.example}</code></p>
        </div>
      )}
    </span>
  );
}
```

`frontend/src/components/TargetInput.tsx`:

```tsx
const EXAMPLES: [string, string][] = [
  ["192.168.1.1", "one device (often your router)"],
  ["192.168.1.0/24", "a whole home network (256 addresses)"],
  ["192.168.1.10-50", "a range of addresses"],
  ["scanme.nmap.org", "Nmap's official practice host"],
];

interface Props {
  value: string;
  onChange: (value: string) => void;
  error?: string;
  autoFocus?: boolean;
}

export function TargetInput({ value, onChange, error, autoFocus }: Props) {
  return (
    <div className="target-input">
      <label htmlFor="target"><strong>Target</strong>: what to scan</label>
      <input
        id="target"
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="192.168.1.1, 192.168.1.0/24 or scanme.nmap.org"
        aria-invalid={Boolean(error)}
        autoFocus={autoFocus}
        spellCheck={false}
      />
      {error && <p className="field-error">{error}</p>}
      <ul className="examples">
        {EXAMPLES.map(([example, meaning]) => (
          <li key={example}>
            <button type="button" className="chip" onClick={() => onChange(example)}>{example}</button> {meaning}
          </li>
        ))}
      </ul>
      <details>
        <summary>What's /24 (CIDR)?</summary>
        <p>
          CIDR notation says how much of the address is fixed. <code>/24</code> fixes the first three numbers and scans every
          value of the last one (256 addresses). <code>/16</code> would be 65,536 addresses, which takes much longer.
        </p>
        <p>
          Not sure what your network is? Run <code>ip route</code> (Linux/WSL) or <code>ipconfig</code> (Windows) and look for
          an address like <code>192.168.x.x</code> or <code>10.x.x.x</code>.
        </p>
      </details>
      <p className="legal small">Only scan devices you own or have permission to test.</p>
    </div>
  );
}
```

`frontend/src/components/RunError.tsx`:

```tsx
import { Link } from "react-router-dom";
import type { ApiError } from "../api/client";

export function RunError({ error }: { error: ApiError | null }) {
  if (!error) return null;
  return (
    <div className="banner banner-error" role="alert">
      {error.message}
      {error.body.active_scan_id && (
        <>
          {" "}
          <Link to={`/scans/${error.body.active_scan_id}`}>Open the running scan</Link>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Implement the Builder page**

`frontend/src/pages/Builder.tsx`:

```tsx
import { useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import type { OptionSpec, ScanRequest } from "../api/types";
import { CommandBar } from "../components/CommandBar";
import { OptionInfo } from "../components/OptionInfo";
import { RunError } from "../components/RunError";
import { TargetInput } from "../components/TargetInput";
import { useAppData } from "../hooks/useAppData";
import { usePreview } from "../hooks/usePreview";
import { useRunScan } from "../hooks/useRunScan";
import { requestToSelected, selectedToRequest, type Selected } from "../lib/request";

export function Builder() {
  const { catalog, status } = useAppData();
  const initial = (useLocation().state as { request?: ScanRequest } | null)?.request;
  const [target, setTarget] = useState(initial?.target ?? "");
  const [selected, setSelected] = useState<Selected>(() => (initial ? requestToSelected(initial, catalog) : {}));
  const request = useMemo(() => selectedToRequest(target, selected), [target, selected]);
  const { command, error } = usePreview(request);
  const { run, busy, error: runError } = useRunScan();

  const toggle = (option: OptionSpec) =>
    setSelected((current) => {
      const next = { ...current };
      if (option.id in next) delete next[option.id];
      else next[option.id] = option.value ? option.value.default : null;
      return next;
    });

  const applyProfile = (profileId: string) => {
    const profile = catalog.profiles[profileId];
    if (!profile) return;
    setSelected(
      Object.fromEntries(profile.options.map((po) => [po.id, po.value ?? catalog.options[po.id]?.value?.default ?? null])),
    );
  };

  const fieldError = (field: string) => (error?.field === field ? error.message : undefined);

  return (
    <div className="builder">
      <h1>Builder</h1>
      <p className="muted">
        Tick the options you want and click ⓘ for a full explanation. The command at the bottom updates as you go; hover over
        any part of it to see what it does.
      </p>
      <TargetInput value={target} onChange={setTarget} error={fieldError("target")} />
      <label className="profile-select">
        Start from profile{" "}
        <select aria-label="Start from profile" value="" onChange={(e) => applyProfile(e.target.value)}>
          <option value="">Choose…</option>
          {Object.values(catalog.profiles).map((p) => (
            <option key={p.id} value={p.id} disabled={p.requires_root && !status.can_raw}>
              {p.title}{p.requires_root ? " 🔒" : ""}
            </option>
          ))}
        </select>
      </label>
      {catalog.groups.map((group) => {
        const options = Object.values(catalog.options).filter((o) => o.group === group.id);
        if (options.length === 0) return null;
        return (
          <fieldset key={group.id} className="option-group">
            <legend>{group.label}</legend>
            <p className="muted small">{group.description}</p>
            {options.map((option) => {
              const locked = option.requires_root && !status.can_raw;
              const checked = option.id in selected;
              const optionError = fieldError(`options.${option.id}`);
              return (
                <div key={option.id} className={`option-row${locked ? " locked" : ""}`}>
                  <label title={locked ? "Needs root: restart VisualNmap with ./run.sh" : option.summary}>
                    <input type="checkbox" checked={checked} disabled={locked} onChange={() => toggle(option)} /> {option.label}{" "}
                    <code>{option.flag}</code>
                    {option.requires_root && <span className="lock"> 🔒</span>}
                  </label>
                  <OptionInfo option={option} />
                  {checked && option.value && (
                    <input
                      aria-label={`${option.label} value`}
                      type={option.value.type === "int" ? "number" : "text"}
                      min={option.value.min ?? undefined}
                      max={option.value.max ?? undefined}
                      placeholder={option.value.placeholder ?? undefined}
                      value={String(selected[option.id] ?? "")}
                      onChange={(e) => setSelected((s) => ({ ...s, [option.id]: e.target.value }))}
                    />
                  )}
                  {locked && <span className="muted small"> needs root</span>}
                  {optionError && <p className="field-error">{optionError}</p>}
                </div>
              );
            })}
          </fieldset>
        );
      })}
      <RunError error={runError} />
      <CommandBar command={command} error={error} onRun={() => run(request)} runDisabled={busy || !status.nmap_found} />
    </div>
  );
}
```

In `frontend/src/App.tsx`, add `import { Builder } from "./pages/Builder";` and change the builder route to `<Route path="/builder" element={<Builder />} />`.

Append to `frontend/src/styles.css`:

```css
.small { font-size: 13px; }
.command-bar { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; margin-top: 16px; }
.command-bar.sticky { position: sticky; bottom: 12px; box-shadow: 0 4px 24px rgb(0 0 0 / 0.15); }
.command-line { display: flex; gap: 12px; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; }
.command-tokens { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.prompt { color: var(--muted); margin-right: 4px; }
.token { font-family: var(--mono); padding: 1px 6px; border-radius: 4px; border: 1px solid transparent; }
.token:hover, .token:focus { border-color: var(--accent); }
.token-option { color: var(--accent); }
.token-target { color: var(--ok); font-weight: 600; }
.token-plumbing { color: var(--muted); opacity: 0.7; }
.command-actions { display: flex; gap: 8px; }
.command-explain { margin: 8px 0 0; color: var(--muted); min-height: 1.5em; }
.warning { color: var(--warn); margin: 6px 0 0; }
.parts-list { display: grid; gap: 6px; margin: 12px 0 0; }
.part { display: grid; grid-template-columns: minmax(120px, max-content) 1fr; gap: 12px; }
.part dd { margin: 0; }
.part-plumbing { opacity: 0.7; }
.target-input { display: grid; gap: 6px; margin-bottom: 16px; }
.target-input input { width: 100%; max-width: 520px; font-family: var(--mono); }
.examples { list-style: none; padding: 0; margin: 0; display: grid; gap: 2px; color: var(--muted); font-size: 13px; }
.chip { font-family: var(--mono); font-size: 12px; padding: 1px 8px; border-radius: 999px; }
.profile-select { display: block; margin: 12px 0 16px; }
.option-group { border: 1px solid var(--border); border-radius: 10px; padding: 8px 16px 12px; margin: 0 0 12px; background: var(--surface); }
.option-group legend { font-weight: 600; padding: 0 6px; }
.option-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 4px 0; position: relative; }
.option-row.locked label { opacity: 0.55; }
.option-row input[type="number"] { width: 90px; }
.info-btn { padding: 0 6px; border: none; background: none; color: var(--accent); }
.info-pop { position: absolute; z-index: 5; top: 100%; left: 0; max-width: 520px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 8px 14px; box-shadow: 0 6px 24px rgb(0 0 0 / 0.2); }
.info-pop .meta { color: var(--muted); font-size: 13px; }
```

- [ ] **Step 7: Run tests and type check**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: all tests pass (10 from Task 10 + 7 CommandBar + 1 OptionInfo + 8 Builder = 26); tsc silent.

- [ ] **Step 8: Try it for real**

Run: `cd frontend && npm run build`, then `./run.sh --no-sudo`, open http://127.0.0.1:8765/builder, type `127.0.0.1`, tick *Fast*.
Expected: the command bar shows `$ nmap -F --privileged -v --stats-every 2s -oX - 127.0.0.1`; hovering `-F` explains it; `--privileged` shows as plumbing.

- [ ] **Step 9: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): command bar with explained tokens and Builder page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 12: Guided mode wizard

**Files:**
- Create: `frontend/src/pages/Guided.tsx`
- Modify: `frontend/src/App.tsx` (route `/guided` → `<Guided />`)
- Modify: `frontend/src/styles.css` (append wizard styles)
- Test: `frontend/src/pages/Guided.test.tsx`

**Interfaces:**
- Consumes: `CommandBar`, `TargetInput`, `RunError`, `usePreview`, `useRunScan` (Task 11); `useAppData` (Task 10).
- Produces: `Guided` page. It sends `ScanRequest { target, profile_id, options: [{ id: "timing", value: 2 | 3 | 4 }] }`. The speed defaults to the profile's own timing value (3 if it has none). "Edit in builder" links to `/builder` with router state `{ request }`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/pages/Guided.test.tsx`:

```tsx
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError, api } from "../api/client";
import { commandFixture, statusUser } from "../test/fixtures";
import { renderWithData } from "../test/render";
import { Guided } from "./Guided";

vi.mock("../api/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../api/client")>();
  return { ...mod, api: { ...mod.api, preview: vi.fn(), startScan: vi.fn() } };
});

const preview = vi.mocked(api.preview);
const startScan = vi.mocked(api.startScan);

beforeEach(() => {
  preview.mockReset().mockResolvedValue(commandFixture);
  startScan.mockReset().mockResolvedValue({ scan_id: "xyz" });
});

type User = ReturnType<typeof userEvent.setup>;

async function next(user: User) {
  const button = screen.getByRole("button", { name: "Next" });
  await waitFor(() => expect(button).toBeEnabled());
  await user.click(button);
}

async function goToSpeedStep(user: User) {
  await user.click(screen.getByRole("radio", { name: /What's open on a machine\? \(fast\)/ }));
  await next(user);
  await user.type(screen.getByLabelText(/Target/), "10.0.0.1");
  await next(user);
}

test("step 1 lists the questions and locks root-only ones", () => {
  renderWithData(<Guided />, { status: statusUser });
  expect(screen.getByRole("heading", { name: "What do you want to find out?" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: /Which devices are on my network\?/ })).toBeEnabled();
  expect(screen.getByRole("radio", { name: /Scan quietly/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
});

test("speed defaults to the profile's timing", async () => {
  const user = userEvent.setup();
  renderWithData(<Guided />);
  await goToSpeedStep(user);
  expect(screen.getByRole("radio", { name: /Aggressive/ })).toBeChecked();
});

test("full walk-through runs the expected request", async () => {
  const user = userEvent.setup();
  renderWithData(<Guided />);
  await goToSpeedStep(user);
  await user.click(screen.getByRole("radio", { name: /Polite/ }));
  await next(user);
  expect(screen.getByRole("heading", { name: "Review and run" })).toBeInTheDocument();
  expect(await screen.findByText("What to scan: 1 address.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Edit in builder" })).toHaveAttribute("href", "/builder");
  const run = screen.getByRole("button", { name: "Run scan" });
  await waitFor(() => expect(run).toBeEnabled());
  await user.click(run);
  expect(startScan).toHaveBeenCalledWith({
    target: "10.0.0.1", profile_id: "quick_ports", options: [{ id: "timing", value: 2 }],
  });
  expect(await screen.findByText("SCAN PAGE")).toBeInTheDocument();
});

test("invalid target blocks the next step", async () => {
  preview.mockRejectedValue(new ApiError(422, { field: "target", message: "'x' is not a valid target." }));
  const user = userEvent.setup();
  renderWithData(<Guided />);
  await user.click(screen.getByRole("radio", { name: /What's open on a machine\? \(fast\)/ }));
  await next(user);
  await user.type(screen.getByLabelText(/Target/), "x");
  expect(await screen.findByText("'x' is not a valid target.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
});

test("back returns to the previous step", async () => {
  const user = userEvent.setup();
  renderWithData(<Guided />);
  await user.click(screen.getByRole("radio", { name: /Which devices/ }));
  await next(user);
  await user.click(screen.getByRole("button", { name: "Back" }));
  expect(screen.getByRole("radio", { name: /Which devices/ })).toHaveAttribute("aria-checked", "true");
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/pages/Guided.test.tsx`
Expected: FAIL with "Failed to resolve import ./Guided".

- [ ] **Step 3: Implement the wizard**

`frontend/src/pages/Guided.tsx`:

```tsx
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { ScanRequest } from "../api/types";
import { CommandBar } from "../components/CommandBar";
import { RunError } from "../components/RunError";
import { TargetInput } from "../components/TargetInput";
import { useAppData } from "../hooks/useAppData";
import { usePreview } from "../hooks/usePreview";
import { useRunScan } from "../hooks/useRunScan";

const STEPS = ["What do you want to find out?", "What do you want to scan?", "How fast and how quiet?", "Review and run"];

const SPEEDS = [
  { value: 2, icon: "🐢", label: "Polite", flag: "-T2", text: "Slow and gentle. Less likely to overload old devices or trigger alarms." },
  { value: 3, icon: "🚶", label: "Normal", flag: "-T3", text: "Nmap's default balance of speed and reliability." },
  { value: 4, icon: "🏃", label: "Aggressive", flag: "-T4", text: "Faster. Fine on modern networks you own; may miss results on slow or flaky links." },
];

export function Guided() {
  const { catalog, status } = useAppData();
  const [step, setStep] = useState(0);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [target, setTarget] = useState("");
  const [speed, setSpeed] = useState<number | null>(null);

  const profile = profileId ? catalog.profiles[profileId] : null;
  const profileTiming = profile?.options.find((o) => o.id === "timing")?.value;
  const effectiveSpeed = speed ?? (profileTiming != null ? Number(profileTiming) : 3);

  const request = useMemo<ScanRequest | null>(
    () => (profileId ? { target, profile_id: profileId, options: [{ id: "timing", value: effectiveSpeed }] } : null),
    [profileId, target, effectiveSpeed],
  );
  const { command, error } = usePreview(step >= 1 ? request : null);
  const { run, busy, error: runError } = useRunScan();
  const targetError = error?.field === "target" ? error.message : undefined;

  const canNext =
    step === 0 ? profileId !== null : step === 1 ? target.trim() !== "" && !targetError && command !== null : true;

  return (
    <div className="guided">
      <ol className="stepper">
        {STEPS.map((label, i) => (
          <li key={label} className={i === step ? "current" : i < step ? "done" : ""} aria-current={i === step ? "step" : undefined}>
            {i + 1}. {label}
          </li>
        ))}
      </ol>
      <h1>{STEPS[step]}</h1>

      {step === 0 && (
        <div className="profile-cards" role="radiogroup" aria-label="Scan goal">
          {Object.values(catalog.profiles).map((p) => {
            const locked = p.requires_root && !status.can_raw;
            return (
              <button
                key={p.id}
                type="button"
                role="radio"
                aria-checked={profileId === p.id}
                disabled={locked}
                className={`profile-card${profileId === p.id ? " selected" : ""}`}
                onClick={() => {
                  setProfileId(p.id);
                  setSpeed(null);
                }}
              >
                <span className="profile-question">{p.question}{p.requires_root ? " 🔒" : ""}</span>
                <span className="profile-explain">{p.explanation}</span>
                <span className="muted small">
                  ⏱ {p.typical_duration}
                  {locked ? " · needs root: restart with ./run.sh" : ""}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {step === 1 && <TargetInput value={target} onChange={setTarget} error={targetError} autoFocus />}

      {step === 2 && (
        <div className="speed-options" role="radiogroup" aria-label="Speed">
          {SPEEDS.map((s) => (
            <label key={s.value} className={`speed-card${effectiveSpeed === s.value ? " selected" : ""}`}>
              <input type="radio" name="speed" checked={effectiveSpeed === s.value} onChange={() => setSpeed(s.value)} />
              <span>
                {s.icon} <strong>{s.label}</strong> <code>{s.flag}</code>
              </span>
              <span className="muted">{s.text}</span>
            </label>
          ))}
        </div>
      )}

      {step === 3 && profile && (
        <div className="review">
          <p>
            You're about to run <strong>{profile.title}</strong> against <code>{target}</code>. Typical duration:{" "}
            {profile.typical_duration}.
          </p>
          <p>This is the exact command, piece by piece:</p>
          <CommandBar
            command={command}
            error={error}
            sticky={false}
            showAll
            onRun={() => request && run(request)}
            runDisabled={busy || !status.nmap_found}
          />
          <p className="legal">⚠️ Only run this against devices you own or have permission to test.</p>
          <p>
            Want to tweak it? <Link to="/builder" state={{ request }}>Edit in builder</Link>
          </p>
          <RunError error={runError} />
        </div>
      )}

      <div className="wizard-nav">
        {step > 0 && <button type="button" onClick={() => setStep(step - 1)}>Back</button>}
        {step < STEPS.length - 1 && (
          <button type="button" className="primary" disabled={!canNext} onClick={() => setStep(step + 1)}>
            Next
          </button>
        )}
      </div>
    </div>
  );
}
```

In `frontend/src/App.tsx`, add `import { Guided } from "./pages/Guided";` and set `<Route path="/guided" element={<Guided />} />`.

Append to `frontend/src/styles.css`:

```css
.stepper { display: flex; gap: 16px; list-style: none; padding: 0; margin: 0 0 8px; color: var(--muted); flex-wrap: wrap; font-size: 13px; }
.stepper .current { color: var(--accent); font-weight: 600; }
.stepper .done { color: var(--ok); }
.profile-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.profile-card { display: grid; gap: 6px; text-align: left; padding: 14px; border-radius: 10px; }
.profile-card.selected, .speed-card.selected { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent); }
.profile-question { font-weight: 600; }
.speed-options { display: grid; gap: 10px; max-width: 640px; }
.speed-card { display: grid; grid-template-columns: auto 1fr; gap: 4px 10px; padding: 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); cursor: pointer; }
.speed-card .muted { grid-column: 2; }
.wizard-nav { display: flex; gap: 8px; margin-top: 20px; }
```

- [ ] **Step 4: Run tests and type check**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: all pass (26 earlier + 5 Guided = 31); tsc silent.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): guided four-step scan wizard

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 13: Live scan page and results view

**Files:**
- Create: `frontend/src/hooks/useScan.ts`
- Create: `frontend/src/components/OutputPane.tsx`, `ProgressBar.tsx`, `HostList.tsx`, `PortTable.tsx`, `HintPanel.tsx`, `StatesHelp.tsx`, `ResultsView.tsx` (all in `frontend/src/components/`)
- Create: `frontend/src/lib/format.ts`
- Create: `frontend/src/pages/Scan.tsx`
- Modify: `frontend/src/App.tsx` (route `/scans/:id` → `<Scan />`)
- Modify: `frontend/src/test/render.tsx` (skip the stand-in "SCAN PAGE" route when `path === "/scans/:id"`)
- Modify: `frontend/src/styles.css` (append scan/results styles)
- Test: `frontend/src/pages/Scan.test.tsx`, `frontend/src/components/PortTable.test.tsx`

**Interfaces:**
- Consumes: `api`, `ApiError`, `openScanStream` (Task 10); `useRunScan`, `RunError` (Task 11); `useAppData` (Task 10).
- Produces:
  - `useScan(id: string): { record: ScanRecord | null; notFound: boolean; lines: string[]; progress: Progress | null }` with `interface Progress { task: string; percent: number | null; eta: string | null }`. It opens the stream only while the record is `running`, and reloads the record and status on `done`.
  - `OutputPane({ lines })`, `ProgressBar({ progress })`, `HostList({ hosts, selected, onSelect })`, `PortTable({ host, states, pingOnly })`, `HintPanel({ hints, onRetryWithPn, busy })`, `StatesHelp({ states })`, `ResultsView({ record, onRetryWithPn, onRunAgain, busy })`
  - `lib/format.ts`: `formatDate(iso: string): string`, `formatDuration(seconds: number | null): string`, `serviceText(p: Port): string`, `withSkipPing(req: ScanRequest): ScanRequest`

- [ ] **Step 1: Adjust the test render helper**

In `frontend/src/test/render.tsx`, replace the stand-in route line with:

```tsx
          {path !== "/scans/:id" && <Route path="/scans/:id" element={<div>SCAN PAGE</div>} />}
```

- [ ] **Step 2: Write the failing tests**

`frontend/src/components/PortTable.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { catalogFixture, recordFixture } from "../test/fixtures";
import { PortTable } from "./PortTable";

const host = recordFixture.result!.hosts[0];

test("lists ports with versions and plain-language notes", () => {
  render(<PortTable host={host} states={catalogFixture.states} pingOnly={false} />);
  const rows = screen.getAllByRole("row");
  expect(rows).toHaveLength(4); // header + 3 ports
  expect(screen.getByText("OpenSSH 8.9p1")).toBeInTheDocument();
  expect(screen.getByText("Remote command-line access (SSH).")).toBeInTheDocument();
  expect(screen.getByText("filtered")).toHaveAttribute("title", "Blocked by a firewall.");
});

test("ping-only scans explain why there are no ports", () => {
  render(<PortTable host={{ ...host, ports: [] }} states={catalogFixture.states} pingOnly />);
  expect(screen.getByText(/ping scan/i)).toBeInTheDocument();
});

test("no ports found message", () => {
  render(<PortTable host={{ ...host, ports: [] }} states={catalogFixture.states} pingOnly={false} />);
  expect(screen.getByText(/No ports to show/)).toBeInTheDocument();
});
```

`frontend/src/pages/Scan.test.tsx`:

```tsx
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError, api, openScanStream } from "../api/client";
import type { ScanRecord, StreamEvent } from "../api/types";
import { recordFixture } from "../test/fixtures";
import { renderWithData } from "../test/render";
import { Scan } from "./Scan";

vi.mock("../api/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../api/client")>();
  return {
    ...mod,
    api: { ...mod.api, getScan: vi.fn(), cancelScan: vi.fn(), startScan: vi.fn() },
    openScanStream: vi.fn(),
  };
});

const getScan = vi.mocked(api.getScan);
const cancelScan = vi.mocked(api.cancelScan);
const startScan = vi.mocked(api.startScan);
const stream = vi.mocked(openScanStream);

const running: ScanRecord = { ...recordFixture, status: "running", result: null, finished_at: null, hosts_up: 0, open_ports: 0 };
const renderScan = () => renderWithData(<Scan />, { route: "/scans/abc123", path: "/scans/:id" });

beforeEach(() => {
  getScan.mockReset();
  cancelScan.mockReset().mockResolvedValue({ status: "cancelling" });
  startScan.mockReset().mockResolvedValue({ scan_id: "new1" });
  stream.mockReset().mockReturnValue(() => {});
});

test("completed scan shows results, help and exports", async () => {
  getScan.mockResolvedValue(recordFixture);
  renderScan();
  expect(await screen.findByRole("heading", { level: 2, name: /pi\.lan/ })).toBeInTheDocument();
  expect(screen.getByText("OpenSSH 8.9p1")).toBeInTheDocument();
  expect(screen.getByText(/1 of 1 hosts up/)).toBeInTheDocument();
  expect(screen.getByText(/2 open ports/)).toBeInTheDocument();
  expect(screen.getByText("Linux 5.0 - 5.14 (96%)")).toBeInTheDocument();
  expect(screen.getByText("Something is listening.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Export XML" })).toHaveAttribute("href", "/api/scans/abc123/export?format=xml");
  expect(stream).not.toHaveBeenCalled();
});

test("running scan streams output and progress, then shows results", async () => {
  getScan.mockResolvedValueOnce(running).mockResolvedValueOnce(recordFixture);
  let emit: (e: StreamEvent) => void = () => {};
  stream.mockImplementation((_id, onEvent) => {
    emit = onEvent;
    return () => {};
  });
  renderScan();
  await waitFor(() => expect(stream).toHaveBeenCalledWith("abc123", expect.any(Function)));
  act(() => emit({ type: "output", line: "Started: Connect Scan" }));
  act(() => emit({ type: "progress", task: "Connect Scan", percent: 42.5, eta: "about 2 min left" }));
  expect(screen.getByRole("log")).toHaveTextContent("Started: Connect Scan");
  expect(screen.getByRole("progressbar")).toHaveAttribute("value", "42.5");
  expect(screen.getByText(/about 2 min left/)).toBeInTheDocument();
  act(() => emit({ type: "done", status: "completed" }));
  expect(await screen.findByRole("heading", { level: 2, name: /pi\.lan/ })).toBeInTheDocument();
});

test("cancel button cancels the running scan", async () => {
  getScan.mockResolvedValue(running);
  const user = userEvent.setup();
  renderScan();
  await user.click(await screen.findByRole("button", { name: "Cancel scan" }));
  expect(cancelScan).toHaveBeenCalledWith("abc123");
});

test("no-hosts hint offers retry with -Pn", async () => {
  getScan.mockResolvedValue({
    ...recordFixture,
    hosts_up: 0,
    open_ports: 0,
    result: { hosts: [], stats: { up: 0, down: 1, total: 1, elapsed_s: 3 }, partial: false },
    hints: [{ code: "no_hosts", message: "No hosts answered.", action: "retry_with_pn" }],
  });
  const user = userEvent.setup();
  renderScan();
  await user.click(await screen.findByRole("button", { name: "Retry with -Pn" }));
  expect(startScan).toHaveBeenCalledWith({
    target: "192.168.1.10",
    profile_id: "quick_ports",
    options: [{ id: "skip_ping", value: null }],
  });
});

test("run again repeats the same request", async () => {
  getScan.mockResolvedValue(recordFixture);
  const user = userEvent.setup();
  renderScan();
  await user.click(await screen.findByRole("button", { name: "Run again" }));
  expect(startScan).toHaveBeenCalledWith(recordFixture.request);
});

test("unknown scan", async () => {
  getScan.mockRejectedValue(new ApiError(404, { message: "Scan not found." }));
  renderScan();
  expect(await screen.findByText(/Scan not found/)).toBeInTheDocument();
});
```

- [ ] **Step 3: Run to verify failure**

Run: `cd frontend && npx vitest run src/pages/Scan.test.tsx src/components/PortTable.test.tsx`
Expected: FAIL with "Failed to resolve import" for `./Scan` and `./PortTable`.

- [ ] **Step 4: Implement helpers and the hook**

`frontend/src/lib/format.ts`:

```ts
import type { Port, ScanRequest } from "../api/types";

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function formatDuration(seconds: number | null): string {
  if (seconds == null) return "unknown time";
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const m = Math.floor(seconds / 60);
  return `${m} min ${Math.round(seconds - m * 60)} s`;
}

export function serviceText(p: Port): string {
  return [p.product, p.version, p.extrainfo ? `(${p.extrainfo})` : null].filter(Boolean).join(" ");
}

export function withSkipPing(req: ScanRequest): ScanRequest {
  return { ...req, options: [...req.options.filter((o) => o.id !== "skip_ping"), { id: "skip_ping", value: null }] };
}
```

`frontend/src/hooks/useScan.ts`:

```ts
import { useEffect, useState } from "react";
import { ApiError, api, openScanStream } from "../api/client";
import type { ScanRecord } from "../api/types";
import { useAppData } from "./useAppData";

export interface Progress {
  task: string;
  percent: number | null;
  eta: string | null;
}

const MAX_LINES = 2000;

export function useScan(id: string) {
  const { refreshStatus } = useAppData();
  const [record, setRecord] = useState<ScanRecord | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [lines, setLines] = useState<string[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);

  useEffect(() => {
    let closed = false;
    let closeStream: (() => void) | null = null;
    setRecord(null);
    setNotFound(false);
    setLines([]);
    setProgress(null);

    const load = () =>
      api.getScan(id).then((r) => {
        if (!closed) setRecord(r);
        return r;
      });

    load()
      .then((r) => {
        if (closed || r.status !== "running") return;
        closeStream = openScanStream(id, (event) => {
          if (event.type === "output") setLines((l) => [...l.slice(-(MAX_LINES - 1)), event.line]);
          else if (event.type === "progress") setProgress({ task: event.task, percent: event.percent, eta: event.eta });
          else if (event.type === "done") {
            void load().catch(() => {});
            void refreshStatus().catch(() => {});
          }
        });
      })
      .catch((err: unknown) => {
        if (!closed && err instanceof ApiError && err.status === 404) setNotFound(true);
      });

    return () => {
      closed = true;
      closeStream?.();
    };
  }, [id, refreshStatus]);

  return { record, notFound, lines, progress };
}
```

- [ ] **Step 5: Implement the components**

`frontend/src/components/OutputPane.tsx`:

```tsx
import { useEffect, useRef } from "react";

export function OutputPane({ lines }: { lines: string[] }) {
  const ref = useRef<HTMLPreElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [lines]);
  return (
    <pre ref={ref} className="terminal" role="log" aria-label="Nmap output">
      {lines.length ? lines.join("\n") : "Waiting for nmap…"}
    </pre>
  );
}
```

`frontend/src/components/ProgressBar.tsx`:

```tsx
import type { Progress } from "../hooks/useScan";

export function ProgressBar({ progress }: { progress: Progress | null }) {
  if (progress?.percent != null) {
    return (
      <div className="progress">
        <progress max={100} value={progress.percent} aria-label="Scan progress" />
        <span>
          {progress.task}: {Math.floor(progress.percent)}%{progress.eta ? `, ${progress.eta}` : ""}
        </span>
      </div>
    );
  }
  return (
    <div className="progress">
      <progress aria-label="Scan progress" />
      <span>Working: {progress?.task ?? "starting nmap"}…</span>
    </div>
  );
}
```

`frontend/src/components/HostList.tsx`:

```tsx
import type { Host } from "../api/types";

interface Props {
  hosts: Host[];
  selected: number;
  onSelect: (index: number) => void;
}

export function HostList({ hosts, selected, onSelect }: Props) {
  return (
    <ul className="host-list" aria-label="Hosts">
      {hosts.map((h, i) => {
        const open = h.ports.filter((p) => p.state === "open").length;
        return (
          <li key={h.address}>
            <button type="button" className={i === selected ? "selected" : ""} aria-pressed={i === selected} onClick={() => onSelect(i)}>
              <span className={`dot dot-${h.status}`} aria-hidden /> <code>{h.address}</code>
              {h.hostname && <span className="muted"> {h.hostname}</span>}
              <span className="muted small"> · {h.status === "up" ? `${open} open` : "down"}</span>
              {h.vendor && <span className="muted small"> · {h.vendor}</span>}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
```

`frontend/src/components/PortTable.tsx`:

```tsx
import type { Host } from "../api/types";
import { serviceText } from "../lib/format";

interface Props {
  host: Host;
  states: Record<string, string>;
  pingOnly: boolean;
}

export function PortTable({ host, states, pingOnly }: Props) {
  if (host.ports.length === 0) {
    return (
      <p className="muted">
        {pingOnly
          ? "This was a ping scan (-sn): nmap only checked whether the host is online, not its ports."
          : "No ports to show. Either every scanned port was closed (and hidden in a summary), or the host didn't answer."}
      </p>
    );
  }
  return (
    <table className="port-table">
      <thead>
        <tr>
          <th>Port</th>
          <th>Proto</th>
          <th>State</th>
          <th>Service</th>
          <th>Version</th>
          <th>What is this?</th>
        </tr>
      </thead>
      <tbody>
        {host.ports.map((p) => (
          <tr key={`${p.port}/${p.protocol}`}>
            <td><code>{p.port}</code></td>
            <td>{p.protocol}</td>
            <td>
              <span className={`state state-${p.state.replace("|", "-")}`} title={states[p.state] ?? ""}>{p.state}</span>
              {p.reason && <div className="muted small">{p.reason}</div>}
            </td>
            <td>{p.service ?? "unknown"}</td>
            <td>{serviceText(p)}</td>
            <td className="muted">{p.note ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

`frontend/src/components/HintPanel.tsx`:

```tsx
import type { Hint } from "../api/types";

interface Props {
  hints: Hint[];
  onRetryWithPn: () => void;
  busy: boolean;
}

export function HintPanel({ hints, onRetryWithPn, busy }: Props) {
  if (hints.length === 0) return null;
  return (
    <div className="hints">
      {hints.map((h) => (
        <div key={h.code} className="banner banner-info">
          💡 {h.message}
          {h.action === "retry_with_pn" && (
            <>
              {" "}
              <button type="button" onClick={onRetryWithPn} disabled={busy}>Retry with -Pn</button>
            </>
          )}
        </div>
      ))}
    </div>
  );
}
```

`frontend/src/components/StatesHelp.tsx`:

```tsx
export function StatesHelp({ states }: { states: Record<string, string> }) {
  return (
    <details className="card states-help">
      <summary>How to read port states</summary>
      <dl>
        {Object.entries(states).map(([state, text]) => (
          <div key={state}>
            <dt><code>{state}</code></dt>
            <dd>{text}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
```

`frontend/src/components/ResultsView.tsx`:

```tsx
import { useState } from "react";
import { api } from "../api/client";
import type { ScanRecord } from "../api/types";
import { useAppData } from "../hooks/useAppData";
import { formatDuration } from "../lib/format";
import { HintPanel } from "./HintPanel";
import { HostList } from "./HostList";
import { PortTable } from "./PortTable";
import { StatesHelp } from "./StatesHelp";

interface Props {
  record: ScanRecord;
  onRetryWithPn: () => void;
  onRunAgain: () => void;
  busy: boolean;
}

export function ResultsView({ record, onRetryWithPn, onRunAgain, busy }: Props) {
  const { catalog } = useAppData();
  const result = record.result;
  const hosts = result?.hosts ?? [];
  const firstUp = Math.max(0, hosts.findIndex((h) => h.status === "up"));
  const [selected, setSelected] = useState(firstUp);
  const host = hosts[selected];
  const pingOnly = record.argv.includes("-sn");

  return (
    <section className="results">
      <div className="summary-strip">
        <span><strong>{result?.stats.up ?? 0} of {result?.stats.total ?? 0} hosts up</strong></span>
        <span>{record.open_ports} open ports</span>
        <span>took {formatDuration(result?.stats.elapsed_s ?? null)}</span>
        <span className={`status status-${record.status}`}>{record.status}</span>
        {result?.partial && <span className="muted">partial results</span>}
      </div>
      <HintPanel hints={record.hints} onRetryWithPn={onRetryWithPn} busy={busy} />
      {hosts.length > 0 && (
        <div className="results-grid">
          <HostList hosts={hosts} selected={selected} onSelect={setSelected} />
          {host && (
            <div className="host-detail">
              <h2>
                <code>{host.address}</code> {host.hostname && <span className="muted">{host.hostname}</span>}
              </h2>
              {host.mac && (
                <p className="muted small">MAC {host.mac}{host.vendor ? ` (${host.vendor})` : ""}</p>
              )}
              {host.os_matches.length > 0 && (
                <div className="os-matches">
                  <strong>Operating system guesses:</strong>
                  <ul>
                    {host.os_matches.slice(0, 3).map((m) => <li key={m.name}>{`${m.name} (${m.accuracy}%)`}</li>)}
                  </ul>
                </div>
              )}
              <PortTable host={host} states={catalog.states} pingOnly={pingOnly} />
            </div>
          )}
        </div>
      )}
      <StatesHelp states={catalog.states} />
      {record.stderr_tail.trim() && (
        <details className="card">
          <summary>Nmap's messages</summary>
          <pre className="terminal">{record.stderr_tail}</pre>
        </details>
      )}
      <div className="result-actions">
        <a href={api.exportUrl(record.id, "xml")} download>Export XML</a>
        <a href={api.exportUrl(record.id, "json")} download>Export JSON</a>
        <button type="button" onClick={onRunAgain} disabled={busy}>Run again</button>
      </div>
    </section>
  );
}
```

`frontend/src/pages/Scan.tsx`:

```tsx
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { OutputPane } from "../components/OutputPane";
import { ProgressBar } from "../components/ProgressBar";
import { ResultsView } from "../components/ResultsView";
import { RunError } from "../components/RunError";
import { useRunScan } from "../hooks/useRunScan";
import { useScan } from "../hooks/useScan";
import { formatDate, withSkipPing } from "../lib/format";

export function Scan() {
  const { id = "" } = useParams();
  const { record, notFound, lines, progress } = useScan(id);
  const { run, busy, error: runError } = useRunScan();
  const [cancelling, setCancelling] = useState(false);

  if (notFound) return <p>Scan not found. <Link to="/history">Back to history</Link></p>;
  if (!record) return <p className="loading">Loading scan…</p>;
  const running = record.status === "running";

  const cancel = async () => {
    setCancelling(true);
    try {
      await api.cancelScan(id);
    } catch {
      /* the scan may have just finished; the stream's done event refreshes the page */
    }
  };

  return (
    <div className="scan-page">
      <h1>Scan of <code>{record.target}</code></h1>
      <p className="muted">Started {formatDate(record.created_at)}</p>
      <pre className="argv"><code>{["nmap", ...record.argv.slice(1)].join(" ")}</code></pre>
      {running && (
        <div className="running">
          <ProgressBar progress={progress} />
          <button type="button" onClick={cancel} disabled={cancelling}>{cancelling ? "Cancelling…" : "Cancel scan"}</button>
          <p className="muted small">You can close this tab; the scan keeps running. Reopen it from History.</p>
        </div>
      )}
      {(running || lines.length > 0) && <OutputPane lines={lines} />}
      {!running && (
        <ResultsView record={record} onRetryWithPn={() => run(withSkipPing(record.request))} onRunAgain={() => run(record.request)} busy={busy} />
      )}
      <RunError error={runError} />
    </div>
  );
}
```

In `frontend/src/App.tsx`, add `import { Scan } from "./pages/Scan";` and set `<Route path="/scans/:id" element={<Scan />} />`.

Append to `frontend/src/styles.css`:

```css
.argv { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; overflow-x: auto; }
.terminal { background: var(--term-bg); color: var(--term-text); border-radius: 8px; padding: 12px; max-height: 320px; overflow: auto; font-size: 13px; white-space: pre-wrap; }
.running { display: grid; gap: 8px; margin: 12px 0; }
.progress { display: flex; gap: 12px; align-items: center; }
.progress progress { width: 320px; max-width: 60vw; }
.summary-strip { display: flex; gap: 20px; flex-wrap: wrap; padding: 12px 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; margin: 12px 0; }
.status-completed { color: var(--ok); } .status-failed { color: var(--error); } .status-cancelled { color: var(--warn); } .status-running { color: var(--info); }
.hints { display: grid; gap: 8px; margin-bottom: 12px; }
.results-grid { display: grid; grid-template-columns: minmax(220px, 280px) 1fr; gap: 16px; align-items: start; }
@media (max-width: 720px) { .results-grid { grid-template-columns: 1fr; } }
.host-list { list-style: none; padding: 0; margin: 0; display: grid; gap: 6px; }
.host-list button { width: 100%; text-align: left; }
.host-list button.selected { border-color: var(--accent); }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
.dot-up { background: var(--ok); }
.host-detail h2 { margin-top: 0; font-size: 18px; }
.state-open { color: var(--ok); font-weight: 600; } .state-filtered, .state-open-filtered { color: var(--warn); } .state-closed { color: var(--muted); }
.states-help { margin-top: 16px; } .states-help dl > div { display: grid; grid-template-columns: 140px 1fr; gap: 8px; } .states-help dd { margin: 0; }
.result-actions { display: flex; gap: 16px; align-items: center; margin-top: 16px; }
```

- [ ] **Step 6: Run tests and type check**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: all pass (31 earlier + 3 PortTable + 6 Scan = 40); tsc silent.

- [ ] **Step 7: Real scan in the browser**

Run: `cd frontend && npm run build`, then `./run.sh --no-sudo`, open http://127.0.0.1:8765/guided, pick "What's open on a machine? (fast)", target `127.0.0.1`, Normal, Run.
Expected: the scan page shows phase lines in the output pane, then the results: `127.0.0.1` up, a port table (or the "No ports to show" message if nothing listens), and the port-state help.

- [ ] **Step 8: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): live scan page with progress, results and hints

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 14: History page and scan comparison

**Files:**
- Create: `frontend/src/pages/History.tsx`
- Create: `frontend/src/components/CompareView.tsx`
- Modify: `frontend/src/App.tsx` (final version below; removes the placeholder)
- Delete: `frontend/src/pages/Placeholder.tsx`
- Modify: `frontend/src/styles.css` (append history/compare styles)
- Test: `frontend/src/pages/History.test.tsx`, `frontend/src/components/CompareView.test.tsx`

**Interfaces:**
- Consumes: `api` (Task 10), `useRunScan`, `RunError` (Task 11), `formatDate` (Task 13), `useAppData` (Task 10), `diffFixture` (Task 10).
- Produces: `History` page; `CompareView({ diff, older, newer }: { diff: ScanDiff; older: ScanSummary; newer: ScanSummary })`. Compare always passes the older scan as `a` and the newer as `b`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/CompareView.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import type { ScanSummary } from "../api/types";
import { diffFixture } from "../test/fixtures";
import { CompareView } from "./CompareView";

const older: ScanSummary = { id: "aaa", created_at: "2026-10-13T10:00:00+00:00", finished_at: null, target: "10.0.0.0/24", profile_id: null, status: "completed", hosts_up: 2, open_ports: 3 };
const newer: ScanSummary = { ...older, id: "bbb", created_at: "2026-10-14T10:00:00+00:00" };

test("shows hosts and ports that changed", () => {
  render(<CompareView diff={diffFixture} older={older} newer={newer} />);
  expect(screen.getByText("10.0.0.7")).toBeInTheDocument();
  expect(screen.getByText("10.0.0.9")).toBeInTheDocument();
  expect(screen.getByText("8080/tcp")).toBeInTheDocument();
  expect(screen.getByText("80/tcp")).toBeInTheDocument();
  expect(screen.getByText(/ssh OpenSSH 8\.9 → ssh OpenSSH 9\.6/)).toBeInTheDocument();
});

test("says so when nothing changed", () => {
  render(<CompareView diff={{ a: "aaa", b: "bbb", hosts_added: [], hosts_removed: [], per_host: {} }} older={older} newer={newer} />);
  expect(screen.getByText(/No differences/)).toBeInTheDocument();
});
```

`frontend/src/pages/History.test.tsx`:

```tsx
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "../api/client";
import type { ScanSummary } from "../api/types";
import { diffFixture, recordFixture } from "../test/fixtures";
import { renderWithData } from "../test/render";
import { History } from "./History";

vi.mock("../api/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../api/client")>();
  return {
    ...mod,
    api: { ...mod.api, listScans: vi.fn(), deleteScan: vi.fn(), getScan: vi.fn(), startScan: vi.fn(), compare: vi.fn() },
  };
});

const listScans = vi.mocked(api.listScans);
const deleteScan = vi.mocked(api.deleteScan);
const getScan = vi.mocked(api.getScan);
const startScan = vi.mocked(api.startScan);
const compare = vi.mocked(api.compare);

const older: ScanSummary = { id: "aaa", created_at: "2026-10-13T10:00:00+00:00", finished_at: "2026-10-13T10:00:05+00:00", target: "192.168.1.10", profile_id: "quick_ports", status: "completed", hosts_up: 1, open_ports: 2 };
const newer: ScanSummary = { ...older, id: "bbb", created_at: "2026-10-14T10:00:00+00:00", profile_id: null };

beforeEach(() => {
  listScans.mockReset().mockResolvedValue([newer, older]);
  deleteScan.mockReset().mockResolvedValue(undefined);
  getScan.mockReset().mockResolvedValue(recordFixture);
  startScan.mockReset().mockResolvedValue({ scan_id: "new1" });
  compare.mockReset().mockResolvedValue(diffFixture);
});

const renderHistory = () => renderWithData(<History />, { route: "/history", path: "/history" });
const rowFor = async (id: string) => (await screen.findByTestId(`scan-${id}`)) as HTMLElement;

test("lists scans newest first with profile names", async () => {
  renderHistory();
  const rows = await screen.findAllByTestId(/^scan-/);
  expect(rows.map((r) => r.dataset.testid)).toEqual(["scan-bbb", "scan-aaa"]);
  expect(within(rows[1]).getByText("Quick port check")).toBeInTheDocument();
  expect(within(rows[0]).getByText("Custom")).toBeInTheDocument();
});

test("empty history points to the guided mode", async () => {
  listScans.mockResolvedValue([]);
  renderHistory();
  expect(await screen.findByText(/No scans yet/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /guided mode/i })).toHaveAttribute("href", "/guided");
});

test("delete asks first, then reloads", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const user = userEvent.setup();
  renderHistory();
  await user.click(within(await rowFor("aaa")).getByRole("button", { name: "Delete" }));
  expect(deleteScan).toHaveBeenCalledWith("aaa");
  await waitFor(() => expect(listScans).toHaveBeenCalledTimes(2));
});

test("re-run starts the stored request", async () => {
  const user = userEvent.setup();
  renderHistory();
  await user.click(within(await rowFor("aaa")).getByRole("button", { name: "Re-run" }));
  expect(getScan).toHaveBeenCalledWith("aaa");
  expect(startScan).toHaveBeenCalledWith(recordFixture.request);
  expect(await screen.findByText("SCAN PAGE")).toBeInTheDocument();
});

test("compare two scans, older first", async () => {
  const user = userEvent.setup();
  renderHistory();
  const compareButton = await screen.findByRole("button", { name: "Compare selected" });
  expect(compareButton).toBeDisabled();
  await user.click(within(await rowFor("bbb")).getByRole("checkbox"));
  expect(compareButton).toBeDisabled();
  await user.click(within(await rowFor("aaa")).getByRole("checkbox"));
  await user.click(compareButton);
  expect(compare).toHaveBeenCalledWith("aaa", "bbb");
  expect(await screen.findByText("8080/tcp")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/pages/History.test.tsx src/components/CompareView.test.tsx`
Expected: FAIL with "Failed to resolve import" for `./History` and `./CompareView`.

- [ ] **Step 3: Implement `CompareView`**

`frontend/src/components/CompareView.tsx`:

```tsx
import type { ScanDiff, ScanSummary } from "../api/types";
import { formatDate } from "../lib/format";

interface Props {
  diff: ScanDiff;
  older: ScanSummary;
  newer: ScanSummary;
}

export function CompareView({ diff, older, newer }: Props) {
  const hostEntries = Object.entries(diff.per_host);
  const nothing = diff.hosts_added.length === 0 && diff.hosts_removed.length === 0 && hostEntries.length === 0;
  return (
    <section className="card compare">
      <h2>What changed</h2>
      <p className="muted">
        From {formatDate(older.created_at)} (<code>{older.target}</code>) to {formatDate(newer.created_at)} (
        <code>{newer.target}</code>). Only open ports are compared.
      </p>
      {older.target !== newer.target && (
        <p className="warning">⚠️ These scans have different targets, so some differences are just the targets being different.</p>
      )}
      {nothing && <p>No differences in hosts, open ports or services. 🎉</p>}
      {diff.hosts_added.length > 0 && (
        <div>
          <h3>New hosts</h3>
          <ul>{diff.hosts_added.map((h) => <li key={h}><code>{h}</code></li>)}</ul>
        </div>
      )}
      {diff.hosts_removed.length > 0 && (
        <div>
          <h3>Hosts that disappeared</h3>
          <ul>{diff.hosts_removed.map((h) => <li key={h}><code>{h}</code></li>)}</ul>
        </div>
      )}
      {hostEntries.map(([address, hd]) => (
        <div key={address} className="host-diff">
          <h3><code>{address}</code></h3>
          {hd.ports_opened.length > 0 && (
            <p>Newly open: {hd.ports_opened.map((p) => <code key={p} className="diff-add">{p}</code>)}</p>
          )}
          {hd.ports_closed.length > 0 && (
            <p>No longer open: {hd.ports_closed.map((p) => <code key={p} className="diff-remove">{p}</code>)}</p>
          )}
          {hd.services_changed.length > 0 && (
            <ul>
              {hd.services_changed.map((c) => (
                <li key={c.port}><code>{c.port}</code>: {`${c.before} → ${c.after}`}</li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </section>
  );
}
```

- [ ] **Step 4: Implement the History page**

`frontend/src/pages/History.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { ScanDiff, ScanSummary } from "../api/types";
import { CompareView } from "../components/CompareView";
import { RunError } from "../components/RunError";
import { useAppData } from "../hooks/useAppData";
import { useRunScan } from "../hooks/useRunScan";
import { formatDate } from "../lib/format";

export function History() {
  const { catalog } = useAppData();
  const [scans, setScans] = useState<ScanSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [comparison, setComparison] = useState<{ diff: ScanDiff; older: ScanSummary; newer: ScanSummary } | null>(null);
  const { run, busy, error: runError } = useRunScan();

  const load = useCallback(async () => {
    try {
      setScans(await api.listScans());
    } catch {
      setError("Couldn't load the scan history.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const togglePick = (id: string) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id].slice(-2)));

  const remove = async (id: string) => {
    if (!window.confirm("Delete this scan from history?")) return;
    try {
      await api.deleteScan(id);
      setPicked((p) => p.filter((x) => x !== id));
      setComparison(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  };

  const rerun = async (id: string) => {
    try {
      const record = await api.getScan(id);
      await run(record.request);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  };

  const compare = async () => {
    if (!scans || picked.length !== 2) return;
    const [older, newer] = scans
      .filter((s) => picked.includes(s.id))
      .sort((x, y) => x.created_at.localeCompare(y.created_at));
    try {
      setComparison({ diff: await api.compare(older.id, newer.id), older, newer });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  };

  if (scans === null && !error) return <p className="loading">Loading history…</p>;

  return (
    <div className="history">
      <h1>History</h1>
      {error && <div className="banner banner-error" role="alert">{error}</div>}
      <RunError error={runError} />
      {scans && scans.length === 0 && (
        <p>
          No scans yet. Start with the <Link to="/guided">guided mode</Link> or the <Link to="/builder">builder</Link>.
        </p>
      )}
      {scans && scans.length > 0 && (
        <>
          <p className="muted">
            Tick two finished scans (ideally of the same target, taken at different times) and press Compare to see what
            changed.
          </p>
          <table className="history-table">
            <thead>
              <tr>
                <th>Compare</th>
                <th>When</th>
                <th>Target</th>
                <th>Scan</th>
                <th>Status</th>
                <th>Hosts up</th>
                <th>Open ports</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {scans.map((s) => (
                <tr key={s.id} data-testid={`scan-${s.id}`}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Select scan of ${s.target} from ${formatDate(s.created_at)}`}
                      checked={picked.includes(s.id)}
                      disabled={s.status !== "completed"}
                      onChange={() => togglePick(s.id)}
                    />
                  </td>
                  <td><Link to={`/scans/${s.id}`}>{formatDate(s.created_at)}</Link></td>
                  <td><code>{s.target}</code></td>
                  <td>{(s.profile_id && catalog.profiles[s.profile_id]?.title) || "Custom"}</td>
                  <td className={`status status-${s.status}`}>{s.status}</td>
                  <td>{s.hosts_up}</td>
                  <td>{s.open_ports}</td>
                  <td className="row-actions">
                    <button type="button" onClick={() => rerun(s.id)} disabled={busy}>Re-run</button>
                    <a href={api.exportUrl(s.id, "xml")} download>XML</a>
                    <a href={api.exportUrl(s.id, "json")} download>JSON</a>
                    <button type="button" onClick={() => remove(s.id)} disabled={s.status === "running"}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button type="button" className="primary compare-btn" disabled={picked.length !== 2} onClick={compare}>
            Compare selected
          </button>
        </>
      )}
      {comparison && <CompareView diff={comparison.diff} older={comparison.older} newer={comparison.newer} />}
    </div>
  );
}
```

- [ ] **Step 5: Final `App.tsx`, remove the placeholder, styles**

Replace `frontend/src/App.tsx` with:

```tsx
import { NavLink, Route, Routes } from "react-router-dom";
import { StatusBanner } from "./components/StatusBanner";
import { useAppData } from "./hooks/useAppData";
import { Builder } from "./pages/Builder";
import { Guided } from "./pages/Guided";
import { History } from "./pages/History";
import { Home } from "./pages/Home";
import { Scan } from "./pages/Scan";

export function App() {
  const { status } = useAppData();
  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand">VisualNmap</NavLink>
        <nav>
          <NavLink to="/" end>Home</NavLink>
          <NavLink to="/guided">Guided</NavLink>
          <NavLink to="/builder">Builder</NavLink>
          <NavLink to="/history">History</NavLink>
        </nav>
        <span className={`badge ${status.can_raw ? "badge-ok" : "badge-warn"}`} title="Whether 🔒 options are available">
          {status.can_raw ? "🔒 unlocked" : "no root"}
        </span>
      </header>
      <StatusBanner status={status} />
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/guided" element={<Guided />} />
          <Route path="/builder" element={<Builder />} />
          <Route path="/scans/:id" element={<Scan />} />
          <Route path="/history" element={<History />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}
```

Run: `git rm frontend/src/pages/Placeholder.tsx`

Append to `frontend/src/styles.css`:

```css
.history-table td { white-space: nowrap; }
.row-actions { display: flex; gap: 8px; align-items: center; }
.compare-btn { margin-top: 12px; }
.compare { margin-top: 16px; }
.diff-add { color: var(--ok); margin-right: 6px; }
.diff-remove { color: var(--error); margin-right: 6px; text-decoration: line-through; }
```

- [ ] **Step 6: Run the full frontend suite, type check and build**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npm run build`
Expected: all tests pass (40 earlier + 2 CompareView + 5 History = 47); tsc silent; `dist/` built.

- [ ] **Step 7: Commit**

```bash
git add -A frontend/src
git commit -m "feat(frontend): scan history with re-run, export and compare

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 15: Docker packaging, smoke test and README finish

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `docker-compose.yml`
- Create: `scripts/docker-smoke.sh` (executable)
- Modify: `README.md` (Docker volume, dev setup, remove the "in development" note)

**Interfaces:**
- Consumes: `python -m visualnmap` and env vars `VISUALNMAP_HOST/PORT/DATA/STATIC/IN_CONTAINER` (Task 8); `frontend` build (Task 14); `/api/status`, `/api/scans` (Task 8).
- Produces: `docker compose up --build -d` serves on `127.0.0.1:8765`; `scripts/docker-smoke.sh` exits 0 and prints `SMOKE TEST PASSED`.

Scan history in Docker lives in the **named volume** `visualnmap-data` instead of `./data`. A bind-mounted `./data` would be created root-owned by Docker, and that would break `./run.sh --no-sudo`, which writes to the same folder as the normal user.

- [ ] **Step 1: Write the Docker files**

`.dockerignore`:

```
.git
**/node_modules
**/__pycache__
**/.pytest_cache
backend/.venv
frontend/dist
data
docs
```

`Dockerfile`:

```dockerfile
# Stage 1: build the React frontend (Node never ships in the final image)
FROM node:20-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + nmap
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends nmap \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/ ./backend/
RUN pip install --no-cache-dir ./backend
COPY --from=frontend /src/frontend/dist ./static
ENV VISUALNMAP_HOST=0.0.0.0 \
    VISUALNMAP_PORT=8765 \
    VISUALNMAP_IN_CONTAINER=1 \
    VISUALNMAP_DATA=/data \
    VISUALNMAP_STATIC=/app/static \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/status', timeout=4)" || exit 1
CMD ["python", "-m", "visualnmap"]
```

`docker-compose.yml`:

```yaml
services:
  visualnmap:
    build: .
    image: visualnmap:local
    container_name: visualnmap
    ports:
      - "127.0.0.1:8765:8765" # dashboard reachable only from this computer
    cap_add:
      - NET_RAW # raw packets for SYN, OS and UDP scans
      - NET_ADMIN
    volumes:
      - visualnmap-data:/data # scan history survives rebuilds
    restart: unless-stopped
    # Native Linux only: give nmap the host's own network view (better LAN discovery).
    # If you enable this, remove the "ports:" section above AND uncomment the environment
    # lines, otherwise the dashboard would listen on every network interface.
    # network_mode: host
    # environment:
    #   VISUALNMAP_HOST: 127.0.0.1

volumes:
  visualnmap-data:
```

- [ ] **Step 2: Write the smoke test**

`scripts/docker-smoke.sh`:

```bash
#!/usr/bin/env bash
# Builds the image, starts a container, checks /api/status, then runs one real ping scan through the API.
set -euo pipefail
cd "$(dirname "$0")/.."

NAME=visualnmap-smoke
PORT=18765
URL="http://127.0.0.1:$PORT"
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "==> Building image"
docker build -q -t visualnmap:smoke . >/dev/null
cleanup
echo "==> Starting container"
docker run -d --name "$NAME" --cap-add NET_RAW --cap-add NET_ADMIN -p "127.0.0.1:$PORT:8765" visualnmap:smoke >/dev/null

for _ in $(seq 1 30); do
  curl -fsS "$URL/api/status" >/dev/null 2>&1 && break
  sleep 1
done

STATUS=$(curl -fsS "$URL/api/status")
echo "status: $STATUS"
python3 -c 'import json,sys; s=json.loads(sys.argv[1]); assert s["is_root"] and s["can_raw"] and s["nmap_found"] and s["in_container"], s' "$STATUS"

curl -fsS "$URL/" | grep -q '<div id="root">' || { echo "frontend not served" >&2; exit 1; }

GATEWAY=$(docker exec "$NAME" python -c '
import socket, struct
for line in open("/proc/net/route").readlines()[1:]:
    f = line.split()
    if f[1] == "00000000":
        print(socket.inet_ntoa(struct.pack("<L", int(f[2], 16))))
        break
')
echo "==> Ping-scanning the container gateway $GATEWAY"
SCAN_ID=$(curl -fsS -X POST -H 'Content-Type: application/json' \
  -d "{\"target\": \"$GATEWAY\", \"profile_id\": \"find_devices\"}" "$URL/api/scans" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["scan_id"])')

for _ in $(seq 1 60); do
  SCAN_STATUS=$(curl -fsS "$URL/api/scans/$SCAN_ID" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  [ "$SCAN_STATUS" != "running" ] && break
  sleep 1
done
echo "scan status: $SCAN_STATUS"
[ "$SCAN_STATUS" = "completed" ] || { docker logs "$NAME" >&2; exit 1; }
echo "SMOKE TEST PASSED"
```

Run: `chmod +x scripts/docker-smoke.sh && bash -n scripts/docker-smoke.sh && echo syntax-ok`
Expected: `syntax-ok`.

- [ ] **Step 3: Run the smoke test**

Run: `scripts/docker-smoke.sh`
Expected: the last line is `SMOKE TEST PASSED`. (Docker Desktop's WSL integration is enabled on the dev machine. If `docker` is missing, stop and ask your human partner rather than skipping the step.)

- [ ] **Step 4: Try compose the way users will**

Run: `docker compose up --build -d && sleep 5 && curl -s http://127.0.0.1:8765/api/status && docker compose down`
Expected: JSON with `"in_container":true`. Opening the page in the browser shows the blue "Running in Docker" banner.

- [ ] **Step 5: Update the README**

In `README.md`, make these exact replacements.

Delete the whole line starting with `> 🚧 **Status:** in development.` and the blank line after it.

Replace:

```
Scan history is kept in `./data` on your host, so it survives rebuilds.
```

with:

```
Scan history is kept in the Docker volume `visualnmap-data`, so it survives rebuilds. To wipe it: `docker compose down -v`.
```

Replace:

```
volumes:
  - ./data:/data             # scan history persists here
```

with:

```
volumes:
  - visualnmap-data:/data    # scan history persists in a named volume
```

In the *Native Linux only* paragraph of §3.4, append this sentence: `Also uncomment the two environment lines so the dashboard keeps listening on 127.0.0.1 only.`

Replace:

```
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
```

with:

```
python3 -m venv .venv || uv venv .venv     # uv works where python3-venv is missing
. .venv/bin/activate
pip install -e '.[dev]' || uv pip install -e '.[dev]'
```

In the §12 Troubleshooting table, change the *Want a clean slate* row's text to: `Stop the app and delete data/visualnmap.db (Docker: docker compose down -v).`

- [ ] **Step 6: Full verification**

Run each command and confirm the expected output:

- `cd backend && .venv/bin/pytest -q` → all pass, 2 skipped (e2e).
- `cd backend && VISUALNMAP_E2E=1 .venv/bin/pytest -m e2e -q` → 2 passed.
- `cd frontend && npx vitest run && npx tsc --noEmit && npm run build` → 47 passed; build succeeds.
- `scripts/docker-smoke.sh` → `SMOKE TEST PASSED`.
- `./run.sh --no-sudo`, then in the browser: run the guided "Quick port check" against `127.0.0.1`, open History, re-run it, tick both scans and press Compare. Expected: "No differences" (or the real differences).
- Ask your human partner to run `./run.sh` once (it needs their sudo password) and check that the badge says `🔒 unlocked` and that the "Quiet scan" profile runs.

- [ ] **Step 7: Commit and push**

```bash
git add Dockerfile .dockerignore docker-compose.yml scripts/docker-smoke.sh README.md
git commit -m "feat: Docker packaging, smoke test and README updates

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```
