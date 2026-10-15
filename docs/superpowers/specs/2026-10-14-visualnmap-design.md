# VisualNmap — Design Spec

**Date:** 2026-10-14
**Status:** Approved in brainstorming, pending written-spec review

## 1. Purpose

VisualNmap is a local, visual web dashboard for running Nmap. It serves two audiences equally:

- **Learners** — a guided mode that explains, in plain language, what each scan does, why you would use it, and how to read the results.
- **Practitioners** — a quick builder mode for people who already know what they want.

**Success looks like:** someone new to Nmap opens the app, follows the guided mode, runs a scan against their own lab or router, and understands both the command that ran and the results it produced.

### Non-goals (v1)

- Multi-user access, authentication, or remote access. The app is single-user and localhost-only.
- Network map / topology graph (v2).
- NSE script browser (v2). No `--script` support in v1.
- Free-form "extra arguments" field. Ever. (See §6 Security.)
- Calling any AI or internet service for explanations.

## 2. Users and assumptions

- Single user, on their own machine (developed on WSL2 / Linux).
- The user scans only targets they own or are authorized to test. The UI displays this reminder on the Home page and the scan review step.
- History is stored in a local SQLite file.

## 3. Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn, PyYAML, `defusedxml` for XML parsing |
| Frontend | React 18 + TypeScript, built with Vite |
| Storage | SQLite (stdlib `sqlite3`) |
| Tests | pytest + httpx/TestClient (backend), Vitest + React Testing Library (frontend) |
| Packaging | `run.sh` (primary), Docker + docker-compose (alternative) |

The frontend is built once (`npm run build`) as the normal user; FastAPI serves the built static files. Node never runs as root.

## 4. Architecture

```
Browser (React UI)  ──HTTP/JSON + WebSocket──►  FastAPI (127.0.0.1:8765)
                                                   │
                                                   ├─ catalog   → explanation data (options, profiles, ports)
                                                   ├─ command   → builds safe nmap argv from a ScanRequest
                                                   ├─ runner    → spawns nmap (no shell), streams output, cancel
                                                   ├─ parser    → nmap XML → hosts/ports JSON
                                                   └─ history   → SQLite: scans, results, raw XML; export; compare
```

### Repository layout

```
VisualNmap/
├── backend/
│   ├── pyproject.toml
│   ├── visualnmap/
│   │   ├── __main__.py        # entrypoint: python -m visualnmap
│   │   ├── api.py             # FastAPI app, REST + WebSocket routes, static serving
│   │   ├── models.py          # Pydantic models (ScanRequest, ScanResult, …)
│   │   ├── environment.py     # is_root, nmap version, in_container detection
│   │   ├── catalog/
│   │   │   ├── __init__.py    # load + validate YAML
│   │   │   ├── options.yaml
│   │   │   ├── profiles.yaml
│   │   │   └── ports.yaml
│   │   ├── command.py
│   │   ├── runner.py
│   │   ├── parser.py
│   │   ├── errors.py          # nmap stderr → plain-language hints
│   │   └── history.py
│   └── tests/
│       ├── fixtures/          # real nmap XML samples, fake_nmap.py
│       └── test_*.py
├── frontend/
│   ├── package.json, vite.config.ts, tsconfig.json
│   └── src/
│       ├── api/               # typed client for REST + WebSocket
│       ├── components/        # CommandBar, OptionInfo, PortTable, OutputPane, …
│       ├── pages/             # Home, Guided, Builder, Scan, History
│       └── test/
├── Dockerfile
├── docker-compose.yml
├── run.sh
├── README.md
└── docs/superpowers/{specs,plans}/
```

### 4.1 `catalog/` — explanation data

All explanatory text lives in YAML so it can be edited without code changes. Loaded and validated once at startup; the app refuses to start if the catalog is invalid.

**`options.yaml`** — one entry per supported Nmap option:

```yaml
- id: service_version
  flag: "-sV"
  group: detection            # discovery | technique | ports | detection | timing | output
  label: "Detect service versions"
  summary: "Asks each open port what software is running and which version."
  details: "Nmap sends probes to open ports and matches the replies against a database of thousands of services. Slower, but tells you e.g. 'OpenSSH 8.9' instead of just 'ssh'."
  when_to_use: "When you need to know what software is behind an open port, e.g. to check for outdated versions."
  requires_root: false
  noise: medium               # low | medium | high — how visible the scan is to the target
  speed_impact: slower        # none | slower | much_slower
  example: "nmap -sV 192.168.1.10"
  takes_value: false          # or: { type: enum|int|ports, choices/min/max }
  conflicts_with: []          # option ids
```

**v1 option set** (allowlist — nothing else can reach nmap):

| Group | Options |
|---|---|
| discovery | `-sn` (ping scan only), `-Pn` (skip host discovery), `-PS` (TCP SYN ping, ports), `-PA` (TCP ACK ping, ports), `-PE` (ICMP echo ping)🔒, `-n` (no DNS resolution) |
| technique | `-sS` (SYN)🔒, `-sT` (TCP connect), `-sU` (UDP)🔒, `-sA` (ACK)🔒, `-sF`/`-sN`/`-sX` (FIN/Null/Xmas)🔒 |
| ports | `-p` (ports spec), `-F` (top 100), `--top-ports N` (1–65535), `-p-` (all ports) |
| detection | `-sV`, `--version-intensity 0–9`, `-O`🔒, `--osscan-guess`🔒, `-A`🔒 (shown as "everything: -sV -O -sC --traceroute" but **v1 maps `-A` to `-sV -O --traceroute`** because `-sC` runs scripts; the explanation says so) |
| timing | `-T0`…`-T5`, `--max-retries N` (0–10), `--host-timeout` (e.g. `30m`) |
| output | `--reason`, `--open` (only show open ports), `-v` |

🔒 = `requires_root: true` (really "needs raw sockets"; enabled when `can_raw` is true).

Always appended by `command.py`, never user-controlled: `-v` (unless the user already picked it), `--stats-every 2s`, and `-oX -` (XML to stdout).

Verified against Nmap 7.99 on this machine: with `-oX -`, progress is **not** written to stderr. It appears inside the XML stream as `<taskbegin task="…"/>`, `<taskprogress task="…" percent="…" etc="…"/>` and `<taskend …/>` elements (`-v` is required for these). `<taskprogress>` only appears for longer phases, so progress is best-effort. stderr carries warnings and errors only.

**`profiles.yaml`** — named presets for guided mode and the builder's "Start from profile":

| id | Guided question | Options | Root needed |
|---|---|---|---|
| `find_devices` | "Which devices are on my network?" | `-sn` | no (better with root: ARP) |
| `quick_ports` | "What's open on a machine? (fast)" | `-F -T4` | no |
| `full_ports` | "What's open on a machine? (thorough)" | `-p- -T4` | no |
| `services` | "What software is running?" | `-sV -F -T4` | no |
| `os_detect` | "What operating system is it?" | `-O --osscan-guess -F` | yes |
| `stealth` | "Scan quietly" | `-sS -T2 -F` | yes |
| `udp_common` | "What UDP services are running?" | `-sU --top-ports 20` | yes |
| `everything` | "Tell me everything (slow)" | `-A -T4 -F` | yes |

Each profile has `title`, `question`, `explanation`, `typical_duration` (text, e.g. "under a minute for one host"), and `options` (list of option ids with values).

**`ports.yaml`** — plain-language notes for ~60 common ports, e.g.:

```yaml
22:  { service: ssh,   note: "Remote command-line access (SSH). Should be locked down with keys; often a target for password guessing." }
80:  { service: http,  note: "Unencrypted website. Fine for local devices; on the internet, prefer HTTPS (443)." }
445: { service: microsoft-ds, note: "Windows file sharing (SMB). Should never be open to the internet." }
```

Also contains `states:` explaining `open`, `closed`, `filtered`, `unfiltered`, `open|filtered`, `closed|filtered`.

### 4.2 `command.py` — safe argv builder

```python
def build_command(req: ScanRequest, env: Environment, catalog: Catalog) -> BuiltCommand
```

- `ScanRequest`: `{ target: str, profile_id: str | None, options: list[OptionValue] }` where `OptionValue = { id: str, value: str | int | None }`. If `profile_id` is set, its options are the base; `options` adds to / overrides them.
- `BuiltCommand`: `{ argv: list[str], parts: list[ExplainedPart], warnings: list[str] }` where `ExplainedPart = { token: str, text: str }` (one per user-visible flag + target; the hidden `-oX -` and `--stats-every` are explained as "app plumbing").
- Validation (raises `CommandError(field, message)`):
  - Unknown option id → reject.
  - Option value checked against its `takes_value` schema (enum / int range / ports spec regex `^(\d{1,5}(-\d{1,5})?)(,\d{1,5}(-\d{1,5})?)*$` with each port 1–65535, or `-` for all).
  - `requires_root` option while `env.can_raw` is false → reject with message telling the user to restart with sudo.
  - `conflicts_with` pairs (e.g. `-sn` with any port option; two scan techniques except `-sU` + one TCP technique) → reject.
  - **Target**: one or more space-separated tokens, each must be an IPv4 address, IPv4 CIDR (`/8`–`/32`), IPv4 octet range (`192.168.1.1-50`), IPv6 address, or hostname (RFC 1123, `^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$`). Max 16 tokens. Any token starting with `-` is rejected. Shell metacharacters are irrelevant (no shell) but rejected anyway by the regexes.
  - Warnings (non-blocking): target larger than /16 in total addresses; `-sU` with more than 1000 ports or `-p-`; `-T5` ("may miss results"); `-T0`/`-T1` ("extremely slow").
- Target tokens are always placed last in argv. Nmap has no `--` end-of-options marker, so safety comes from the option allowlist plus the target regexes (no target token can start with `-`).
- The same function powers `POST /api/command/preview` and `POST /api/scans`, so the preview is exactly what runs.

### 4.3 `runner.py` — process execution

```python
class ScanRunner:
    async def start(self, scan_id: str, argv: list[str]) -> None
    async def cancel(self, scan_id: str) -> None
    def subscribe(self, scan_id: str) -> AsyncIterator[StreamEvent]   # replays buffer, then live
    def active_scan_id(self) -> str | None
```

- `asyncio.create_subprocess_exec(*argv, stdout=PIPE, stderr=PIPE)` — never a shell.
- Reads stdout line by line and accumulates it as the XML document. Lines containing `<taskbegin>`, `<taskprogress>` or `<taskend>` are also turned into events: `output` with a readable line (e.g. "Started: Connect Scan", "Connect Scan 42% done, about 1 min left", "Finished: Connect Scan (500 total ports)") and, for `<taskprogress>`, a `progress` event. Each stderr line (warnings, errors) is streamed as an `output` event as-is.
- The live output pane therefore shows phase/progress lines derived from the XML plus nmap's stderr. When the scan finishes, the Results view is rendered from the parsed XML, which is the single source of truth. If no `<taskprogress>` arrives, the UI shows an indeterminate progress bar with the current phase name.
- One active scan at a time (v1). A second `start` raises `ScanBusy`.
- Per-scan event buffer (max 5,000 lines) so a reconnecting browser gets a replay.
- `cancel`: SIGTERM, wait 5 s, then SIGKILL. Status becomes `cancelled`; partial XML is parsed best-effort.
- On exit: status `completed` (exit 0) or `failed` (non-zero), parse XML, save to history, emit `done`.
- `StreamEvent` = `{type: "output", line}` | `{type: "progress", percent: float, eta: str | None}` | `{type: "done", status: "completed"|"failed"|"cancelled"}`.

### 4.4 `parser.py`

```python
def parse_nmap_xml(xml: str, catalog: Catalog) -> ParsedResult
```

- Uses `defusedxml.ElementTree`. Tolerates truncated XML (cancelled scans): if parsing fails, retries after closing open tags; if still failing, returns `ParsedResult(hosts=[], partial=True)`.
- `ParsedResult = { hosts: list[Host], stats: {up, down, total, elapsed_s}, partial: bool }`
- `Host = { address, hostname | None, mac | None, vendor | None, status: "up"|"down", reason, os_matches: [{name, accuracy}], ports: list[Port] }`
- `Port = { port: int, protocol, state, reason, service | None, product | None, version | None, extrainfo | None, note | None }` — `note` filled from `ports.yaml`.

### 4.5 `errors.py`

Maps known nmap stderr patterns to `{hint, action}`:

| Pattern | Hint |
|---|---|
| `Failed to resolve "X"` | "Couldn't find that host name. Check spelling or try an IP address." |
| `requires root privileges` / `You requested a scan type which requires root` | "This scan needs root. Restart VisualNmap with sudo (see README)." |
| `0 hosts up` / `Note: Host seems down` | "No hosts answered. Many devices block ping — try again with 'Skip host discovery (-Pn)'." + action `retry_with_pn` |
| `QUITTING!` | "Nmap stopped because of an error — see the output above." |

### 4.6 `history.py`

SQLite at `$VISUALNMAP_DATA/visualnmap.db` (default `./data/`).

Table `scans`: `id TEXT PK (uuid4)`, `created_at TEXT (ISO 8601 UTC)`, `finished_at TEXT NULL`, `target TEXT`, `profile_id TEXT NULL`, `request_json TEXT`, `argv_json TEXT`, `status TEXT` (`running|completed|failed|cancelled`), `hosts_up INT`, `open_ports INT`, `raw_xml TEXT`, `result_json TEXT`, `stderr_tail TEXT`.

```python
class History:
    def create(self, scan: NewScan) -> str
    def finish(self, scan_id: str, status: str, raw_xml: str, result: ParsedResult, stderr_tail: str) -> None
    def get(self, scan_id: str) -> ScanRecord | None
    def list(self, limit: int = 100) -> list[ScanSummary]
    def delete(self, scan_id: str) -> bool
    def export(self, scan_id: str, fmt: Literal["xml", "json"]) -> tuple[bytes, str]   # (content, media type)
    def compare(self, a: str, b: str) -> ScanDiff
```

`ScanDiff = { hosts_added, hosts_removed, per_host: {address: {ports_opened: [..], ports_closed: [..], services_changed: [{port, before, after}]}} }`. Compare is allowed for any two completed scans; the UI suggests same-target pairs.

On startup, any scan left in `running` (app crashed) is marked `failed` with stderr_tail "App stopped during scan".

### 4.7 `environment.py`

```python
@dataclass
class Environment:
    is_root: bool            # os.geteuid() == 0
    can_raw: bool            # is_root, OR the real nmap binary has cap_net_raw (Kali ships /usr/bin/nmap as a
                             # wrapper that adds --privileged for non-root users). Detected by reading the
                             # 'security.capability' xattr of the resolved binary (/usr/lib/nmap/nmap if present).
    nmap_path: str | None    # shutil.which("nmap")
    nmap_version: str | None # parsed from `nmap --version`
    in_container: bool       # /.dockerenv exists or VISUALNMAP_IN_CONTAINER=1
```

### 4.8 `api.py` — HTTP API

| Method | Path | Body / Response |
|---|---|---|
| GET | `/api/status` | `{is_root, can_raw, nmap_version, nmap_found, in_container, active_scan_id}` |
| GET | `/api/catalog` | `{options, profiles, ports, states}` |
| POST | `/api/command/preview` | `ScanRequest` → `BuiltCommand` or 422 `{field, message}` |
| POST | `/api/scans` | `ScanRequest` → 201 `{scan_id}`; 409 `{active_scan_id}` if busy; 422 on validation; 503 if nmap missing |
| GET | `/api/scans` | `[ScanSummary]` |
| GET | `/api/scans/{id}` | `ScanRecord` (incl. parsed result, hints) or 404 |
| POST | `/api/scans/{id}/cancel` | 202, or 409 if not running |
| DELETE | `/api/scans/{id}` | 204, or 409 if running |
| GET | `/api/scans/{id}/export?format=xml\|json` | file download |
| GET | `/api/compare?a={id}&b={id}` | `ScanDiff` |
| WS | `/api/scans/{id}/stream` | `StreamEvent` messages; closes after `done` |
| GET | `/*` | built frontend (SPA fallback to `index.html`) |

Server binds to `127.0.0.1:8765` by default. `VISUALNMAP_HOST` / `VISUALNMAP_PORT` env vars override (Docker sets host `0.0.0.0` *inside* the container, published only on host `127.0.0.1`). WebSocket and POST endpoints check the `Origin` header equals the served origin (blocks a malicious web page from driving the scanner via the user's browser).

## 5. Frontend

### Pages

- **Home** — two cards: *Guide me* (guided mode) and *I know what I want* (builder). "What is Nmap?" explainer (3–4 sentences). Authorization reminder. Status banners (see §7).
- **Guided** — 4-step wizard:
  1. *What do you want to find out?* — profile cards (title, question, explanation, typical duration, 🔒 badge).
  2. *What do you want to scan?* — target input with examples (`192.168.1.1`, `192.168.1.0/24`, `scanme.nmap.org`), a "What's CIDR?" explainer, and live validation via preview endpoint.
  3. *How fast / how quiet?* — Polite (`-T2`) / Normal (`-T3`) / Aggressive (`-T4`), each with trade-off text.
  4. *Review* — CommandBar with each part explained, typical duration, warnings, authorization reminder, **Run**.
- **Builder** — target input; "Start from profile" dropdown; option groups (collapsible sections) with label, ⓘ popover (summary, details, when to use, noise, speed, example), 🔒 badge + disabled state when not root; sticky CommandBar.
- **Scan** (`/scans/:id`) — while running: OutputPane (terminal style, auto-scroll), progress bar + ETA, Cancel. After done: Results view —
  - Summary strip: hosts up / total, open ports, duration, status.
  - Hints panel (from `errors.py`), incl. "Retry with -Pn" button.
  - Host list; selecting a host shows OS guesses and PortTable (port, protocol, state, service, version, "What is this?" note).
  - "How to read this" panel explaining port states.
  - Export buttons (XML / JSON), "Run again".
- **History** — table (date, target, profile, status, hosts up, open ports); actions: open, re-run, delete, export; select two → Compare view (hosts added/removed, ports opened/closed, service changes).

### Key components

- `CommandBar` — renders `BuiltCommand.parts` as tokens; hovering/tapping a token shows its explanation; copy-to-clipboard button; warnings below.
- `OptionInfo` — ⓘ popover for an option.
- `OutputPane`, `ProgressBar`, `PortTable`, `HostList`, `HintPanel`, `StatusBanner`, `CompareView`.

### Frontend data flow

1. On load: `GET /api/status`, `GET /api/catalog`.
2. On every change in Guided/Builder: debounced (250 ms) `POST /api/command/preview`; 422 errors are shown inline on the related field.
3. Run → `POST /api/scans` → navigate to `/scans/{id}` → open WebSocket.
4. On `done` → `GET /api/scans/{id}` → render results.

## 6. Security

The backend runs as root (via `sudo` or in a container) and executes a powerful network tool, so:

1. **Localhost only.** Default bind `127.0.0.1`. Docker publishes `127.0.0.1:8765:8765` only.
2. **No shell, ever.** `create_subprocess_exec` with an argv list.
3. **Allowlist only.** Every flag comes from `options.yaml`; values are schema-validated; no free-text args, no `--script`, no `-iL`, no `-o*` other than the fixed `-oX -`, no `--datadir`, no `--resume`.
4. **Target validation** per §4.2.
5. **Origin check** on POST and WebSocket to block cross-site requests from other browser tabs.
6. **XML parsing** with `defusedxml`.
7. **Authorization reminder** in the UI.

## 7. Error handling (user-facing)

| Condition | Behavior |
|---|---|
| nmap not installed | `/api/status.nmap_found=false`; Home shows red banner with `sudo apt install nmap`; Run disabled; `POST /api/scans` → 503 |
| Not root and no raw-socket capability (`can_raw=false`) | Yellow banner: "Started without sudo: 🔒 options are disabled. Restart with `./run.sh` (it uses sudo) to unlock them." 🔒 options disabled; backend rejects them |
| In container | Blue info banner: "Running in Docker: LAN device discovery is limited and `localhost` means the container — use your PC's IP." |
| Invalid target / option | Inline field error from 422, with valid examples |
| Scan already running | Run disabled with link to running scan; backend 409 |
| nmap non-zero exit | Status `failed`; stderr shown; hints from `errors.py` |
| Zero hosts up | Hint + "Retry with -Pn" one-click |
| Browser disconnect | Scan continues; reconnect replays buffer |
| Big scan | Non-blocking warnings (§4.2) |
| App crash mid-scan | On restart, scan marked `failed` |

## 8. Running the app

### Primary: `run.sh`

```bash
./run.sh            # first run: creates backend/.venv, pip installs, builds frontend (npm ci && npm run build) as the current user
                    # then: sudo backend/.venv/bin/python -m visualnmap
```

- Checks prerequisites (python3 ≥ 3.11, node ≥ 18 for the build, nmap) and prints install hints if missing.
- Prints `VisualNmap running at http://127.0.0.1:8765`.
- `./run.sh --no-sudo` runs unprivileged (🔒 options disabled).
- Rebuilds frontend only if `frontend/dist` is missing or older than `frontend/src`.

### Alternative: Docker

**Dockerfile** (multi-stage):
1. `node:20-alpine` — `npm ci && npm run build` in `frontend/`.
2. `python:3.12-slim` — `apt-get install -y --no-install-recommends nmap`, `pip install ./backend`, copy `frontend/dist`, `ENV VISUALNMAP_HOST=0.0.0.0 VISUALNMAP_IN_CONTAINER=1 VISUALNMAP_DATA=/data`, `CMD ["python","-m","visualnmap"]`.

**docker-compose.yml**:

```yaml
services:
  visualnmap:
    build: .
    ports:
      - "127.0.0.1:8765:8765"
    cap_add: [NET_RAW, NET_ADMIN]
    volumes:
      - ./data:/data
    # Native Linux only — gives nmap the host's network view (better LAN discovery).
    # Remove the "ports:" section above if you enable this.
    # network_mode: host
```

Container runs as root inside the container (needed for raw sockets) with only the two extra capabilities, not `--privileged`.

## 9. Testing

**Backend (pytest)**
- `test_catalog.py` — every option has label/summary/details/when_to_use/requires_root/example; every profile references known option ids; ports.yaml keys are ints 1–65535.
- `test_command.py` — each profile → expected argv; unknown option rejected; injection attempts rejected (`-iL /etc/shadow` as target, `; rm -rf /`, `$(id)`, `--script=vuln` as target, `-oN /etc/x`); root gating; conflict rules; port spec validation (0, 65536, `1-`, `a`); target forms (IPv4, CIDR, range, IPv6, hostname, 17 tokens rejected); warnings for /8 and UDP `-p-`; preview argv == run argv.
- `test_parser.py` — fixtures: host up with services, host down, OS detection, multiple hosts, truncated XML (cancelled), empty run.
- `test_errors.py` — each stderr pattern → hint.
- `test_history.py` — create/finish/get/list/delete/export/compare on a tmp DB; crash recovery marks `running` → `failed`.
- `test_runner.py` — uses `tests/fixtures/fake_nmap.py` (prints XML incl. `<taskbegin>/<taskprogress>/<taskend>` to stdout, a warning to stderr, sleeps) to test streaming, progress parsing, buffer replay, cancel (SIGTERM path), busy rejection, failure exit code.
- `test_api.py` — TestClient over all endpoints with fake runner; origin check rejects foreign Origin.
- `test_e2e.py` (marked `@pytest.mark.e2e`, skipped unless `VISUALNMAP_E2E=1`) — real nmap: `-sn 127.0.0.1` and `-F 127.0.0.1`.

**Frontend (Vitest + RTL)**
- Wizard produces correct `ScanRequest` for a profile + target + speed.
- CommandBar renders parts and shows explanation on hover.
- Builder disables 🔒 options when `can_raw=false`.
- Results render from a fixture `ScanRecord`; port notes displayed.
- Compare view renders a fixture `ScanDiff`.

**Docker smoke test** (documented script `scripts/docker-smoke.sh`): build image, start container, `curl /api/status` shows `is_root: true, can_raw: true, nmap_found: true, in_container: true`, run a `-sn` scan of the container gateway, assert `completed`.

## 10. Deliverables

- Working app per above.
- `README.md` — what it is, legal/authorization note, requirements, install & run (run.sh and Docker), guided-mode walkthrough, builder walkthrough, reading results, Docker networking limits, troubleshooting, development & tests.
- Public GitHub repo `AustenLynn/VisualNmap`, MIT license.
