# VisualNmap

**A visual, beginner-friendly dashboard for [Nmap](https://nmap.org), running on your own machine.**

VisualNmap lets you build and run Nmap scans by clicking instead of memorizing flags, and explains every step in plain language:

- **What each option does, when you'd use it, how slow or noisy it is, and whether it needs root.**
- **The exact `nmap` command** being built, with every part explained when you hover over it.
- **Live progress** while the scan runs, with the option to cancel.
- **Readable results**: hosts, open ports, services and versions, plus a "what is this?" note for common ports.
- **History**: re-open past scans, run them again, compare two scans, and export to XML or JSON.

There are two ways to use it:

| Mode | For | How it works |
|---|---|---|
| 🧭 **Guided mode** | People learning Nmap | A 4-step wizard: *what do you want to find out → what to scan → how fast → review & run*. |
| ⚡ **Builder (quick mode)** | People who know Nmap | Every supported option on one screen, grouped by purpose, with the command preview always visible. |

> 🚧 **Status:** in development. This README describes the app as designed (see [`docs/superpowers/specs/2026-10-14-visualnmap-design.md`](docs/superpowers/specs/2026-10-14-visualnmap-design.md)). Some features may not be available yet.

---

## ⚠️ Only scan what you're allowed to scan

Port scanning networks or computers you don't own, or don't have **written permission** to test, can be illegal and can get you banned by your ISP or employer. Good targets to practice on:

- Your own computer, router, or home lab VMs.
- `scanme.nmap.org`, a host the Nmap project provides **specifically** so people can test against it (please don't hammer it).
- Deliberately vulnerable practice machines (e.g. Metasploitable, CTF labs) on an isolated network.

---

## Contents

1. [Requirements](#1-requirements)
2. [Install and run (recommended: `run.sh`)](#2-install-and-run-recommended-runsh)
3. [Alternative: run with Docker](#3-alternative-run-with-docker)
4. [A tour of the app](#4-a-tour-of-the-app)
5. [Guided mode, step by step](#5-guided-mode-step-by-step)
6. [Builder (quick mode)](#6-builder-quick-mode)
7. [Watching a scan run](#7-watching-a-scan-run)
8. [Reading the results](#8-reading-the-results)
9. [History, compare and export](#9-history-compare-and-export)
10. [Scan profiles cheat sheet](#10-scan-profiles-cheat-sheet)
11. [Why some options have a 🔒](#11-why-some-options-have-a-)
12. [Troubleshooting](#12-troubleshooting)
13. [Security model](#13-security-model)
14. [Development](#14-development)

---

## 1. Requirements

| Tool | Version | Why | Install (Debian/Ubuntu/Kali/WSL) |
|---|---|---|---|
| **Nmap** | 7.80+ | The scanner itself | `sudo apt install nmap` |
| **Python** | 3.11+ | Runs the backend | `sudo apt install python3 python3-venv` |
| **Node.js** | 18+ | Builds the web interface (only once, not while scanning) | `sudo apt install nodejs npm` or [nodejs.org](https://nodejs.org) |
| **A web browser** | any modern one | Shows the dashboard | On WSL2, your normal Windows browser works |

Check what you have:

```bash
nmap --version
python3 --version
node --version
```

---

## 2. Install and run (recommended: `run.sh`)

```bash
git clone https://github.com/AustenLynn/VisualNmap.git
cd VisualNmap
./run.sh
```

What `./run.sh` does:

1. Checks that Nmap, Python and Node are installed, and tells you how to install anything that's missing.
2. **First run only:** creates a Python virtual environment in `backend/.venv` and installs the backend.
3. Builds the web interface into `frontend/dist`. This runs as **your normal user**, and only happens again if the frontend source has changed.
4. Starts the server **with `sudo`**. It will ask for your password. Root lets Nmap use raw packets, which the most useful scans need (see [§11](#11-why-some-options-have-a-)).
5. Prints:

   ```
   VisualNmap running at http://127.0.0.1:8765
   ```

Open **http://127.0.0.1:8765** in your browser. Press `Ctrl+C` in the terminal to stop the app.

**Run without root:**

```bash
./run.sh --no-sudo
```

Everything still works, but options marked 🔒 are disabled (unless your Nmap install already has raw-socket permissions, as Kali's does).

**Settings** (environment variables):

| Variable | Default | Meaning |
|---|---|---|
| `VISUALNMAP_PORT` | `8765` | Port the dashboard listens on |
| `VISUALNMAP_HOST` | `127.0.0.1` | Address it listens on. **Leave this alone** unless you understand the risk (§13) |
| `VISUALNMAP_DATA` | `./data` | Where scan history (`visualnmap.db`) is stored |

---

## 3. Alternative: run with Docker

Docker runs VisualNmap and its own copy of Nmap in an isolated container, so nothing runs as root on your host system.

### 3.1 Prerequisites

- Docker Engine with Docker Compose v2 (`docker compose version`).
- **WSL2 users:** install Docker Desktop on Windows, then enable it for your distro under **Docker Desktop → Settings → Resources → WSL Integration**. Otherwise you'll see `The command 'docker' could not be found in this WSL 2 distro`.

### 3.2 Start it

```bash
docker compose up --build -d
```

Open **http://127.0.0.1:8765**.

```bash
docker compose logs -f      # watch the logs
docker compose down         # stop it
```

Scan history is kept in `./data` on your host, so it survives rebuilds.

### 3.3 What the compose file does

```yaml
ports:
  - "127.0.0.1:8765:8765"   # dashboard only reachable from YOUR computer
cap_add: [NET_RAW, NET_ADMIN] # lets nmap send raw packets (SYN/OS/UDP scans) without --privileged
volumes:
  - ./data:/data             # scan history persists here
```

### 3.4 Docker networking limits (read this!)

Inside Docker, Nmap sees the network **through Docker's virtual network (NAT)**, not directly through your Wi-Fi or Ethernet card. In practice:

| You want to… | Works in Docker? | Notes |
|---|---|---|
| Scan an internet host or `scanme.nmap.org` | ✅ Yes | |
| Scan a LAN device by IP (`192.168.1.10`) | ✅ Mostly | Port results are accurate |
| Discover **all** devices on your LAN (`192.168.1.0/24` ping sweep) | ⚠️ Limited | ARP discovery doesn't work through NAT, so some devices are missed and MAC address/vendor info is missing |
| Scan **your own PC** | ⚠️ Different | `127.0.0.1`/`localhost` means **the container**. Use your PC's LAN IP instead (`ip addr` on Linux, `ipconfig` on Windows) |

The app detects when it's running in Docker and shows a blue banner reminding you of this.

**Native Linux only:** for full LAN visibility, edit `docker-compose.yml`, remove the `ports:` section and uncomment `network_mode: host`. On Docker Desktop (Windows/macOS) host networking attaches to Docker's VM, not your real network card, so it doesn't help there. Use `./run.sh` instead.

---

## 4. A tour of the app

```
┌──────────────────────────────────────────────────────────────────┐
│  VisualNmap        Home   Guided   Builder   History    ● root ✓ │
├──────────────────────────────────────────────────────────────────┤
│  [banners: not-root / running in Docker / nmap missing]          │
│                                                                  │
│   ┌────────────────────────┐   ┌────────────────────────┐        │
│   │  🧭 Guide me           │   │  ⚡ I know what I want  │        │
│   │  Answer 4 questions,   │   │  All options, grouped,  │        │
│   │  we build the scan.    │   │  with explanations.     │        │
│   └────────────────────────┘   └────────────────────────┘        │
│                                                                  │
│   What is Nmap?  …   ⚠️ Only scan networks you're allowed to.     │
├──────────────────────────────────────────────────────────────────┤
│ $ nmap -sV -F -T4 192.168.1.10                       [copy] [Run]│  ← command bar
└──────────────────────────────────────────────────────────────────┘
```

- **Top bar:** navigation, plus a badge showing whether 🔒 options are available (`root ✓` or `no root`).
- **Banners:** appear only when something needs your attention (Nmap not installed, no root, running in Docker).
- **Command bar:** always shows the exact command that will run. **Hover over any part** (`-sV`, `-T4`, the target…) to see what it means. **Copy** puts the command on your clipboard so you can run it in a terminal yourself, which is a good way to learn.

> The command bar shows `-v --stats-every 2s -oX -` as greyed-out "app plumbing". These make Nmap report progress and results in a format the dashboard can read. You can't change them, and they don't affect what's scanned.

---

## 5. Guided mode, step by step

Click **🧭 Guide me** on the Home page.

### Step 1: What do you want to find out?

Pick the card that matches your question. Each card shows what it does, roughly how long it takes, and 🔒 if it needs root.

| Card | Picks this scan | In plain words |
|---|---|---|
| Which devices are on my network? | `-sn` | Asks every address "are you there?" without checking ports. Fast. |
| What's open on a machine? (fast) | `-F -T4` | Checks the 100 most common ports. |
| What's open on a machine? (thorough) | `-p- -T4` | Checks all 65,535 TCP ports. Slow, but misses nothing. |
| What software is running? | `-sV -F -T4` | Finds open ports, then asks each one what program and version it runs. |
| What operating system is it? 🔒 | `-O --osscan-guess -F` | Guesses the OS from tiny differences in how it answers network packets. |
| Scan quietly 🔒 | `-sS -T2 -F` | "Half-open" scan, sent slowly, so it's less likely to be noticed or logged. |
| What UDP services are running? 🔒 | `-sU --top-ports 20` | Checks common UDP services (DNS, DHCP, SNMP…). UDP scans are slow by nature. |
| Tell me everything 🔒 | `-A -T4 -F` | Version + OS detection + traceroute. The most information, the most time. |

### Step 2: What do you want to scan?

Type a **target**. The box checks it as you type and shows examples:

| You type | It means |
|---|---|
| `192.168.1.1` | One device (often your home router) |
| `192.168.1.0/24` | All 256 addresses from `192.168.1.0` to `192.168.1.255`, i.e. a typical home network |
| `192.168.1.10-50` | Addresses `.10` through `.50` |
| `scanme.nmap.org` | A host name; it gets looked up to an IP first |
| `10.0.0.5 10.0.0.9` | Several targets, separated by spaces (up to 16) |

> **What's `/24`?** It's "CIDR notation": how many bits of the address are fixed. `/24` fixes the first three numbers and scans every value of the last one (256 addresses). `/16` would be 65,536 addresses, which is a lot. The app warns you about big ranges.

**Not sure what your network is?** On Linux/WSL run `ip route`; on Windows run `ipconfig`. Look for an address like `192.168.x.x` or `10.x.x.x`.

### Step 3: How fast and how quiet?

| Choice | Flag | Trade-off |
|---|---|---|
| 🐢 Polite | `-T2` | Slow and gentle. Less likely to overload old devices or trigger alarms. |
| 🚶 Normal | `-T3` | Nmap's default balance. |
| 🏃 Aggressive | `-T4` | Faster. Fine on modern networks you own; may miss results on slow or flaky links. |

### Step 4: Review and run

You'll see:

- The full command, with **each part explained in a list** below it.
- An estimate of how long it will take.
- Any **warnings** (e.g. "this is 65,536 addresses, which may take hours").
- The permission reminder.

Click **Run scan**. You'll go to the live scan page ([§7](#7-watching-a-scan-run)).

---

## 6. Builder (quick mode)

Click **⚡ I know what I want**, or **Builder** in the top bar.

1. **Target:** same rules as guided Step 2.
2. **Start from profile** (optional): pre-fills options from any guided scan, which you can then change.
3. **Option groups** (click a heading to expand it):

| Group | Options | What the group is about |
|---|---|---|
| **Host discovery** | `-sn`, `-Pn`, `-PS`, `-PA`, `-PE`🔒, `-n` | How Nmap decides which addresses are "alive" before scanning ports |
| **Scan technique** | `-sS`🔒, `-sT`, `-sU`🔒, `-sA`🔒, `-sF`🔒, `-sN`🔒, `-sX`🔒 | *How* each port is probed |
| **Ports** | `-p`, `-F`, `--top-ports N`, `-p-` | *Which* ports are checked |
| **Detection** | `-sV`, `--version-intensity`, `-O`🔒, `--osscan-guess`🔒, `-A`🔒 | Identifying software and operating systems |
| **Timing** | `-T0`…`-T5`, `--max-retries`, `--host-timeout` | Speed vs. accuracy vs. stealth |
| **Output** | `--reason`, `--open`, `-v` | What extra detail appears in results |

Every option has:

- A short label you can tick, plus a value box if it needs one (e.g. the port list for `-p`).
- An **ⓘ button** that opens the full explanation: *what it does · when to use it · noise level · speed impact · example command*.
- A **🔒 badge** if it needs root. When 🔒 options aren't available, they're greyed out with a note on how to enable them.

The builder **stops impossible combinations** and tells you why. For example, `-sn` (no port scan) together with `-p 80` gives *"Ping scan (-sn) skips port scanning, so a port list has no effect. Remove one of them."*

**Port list format** for `-p`: `22`, `22,80,443`, `1-1024`, `22,80,8000-8100`. Each port must be 1–65535.

> **Note on `-A`:** real Nmap's `-A` also runs default NSE scripts (`-sC`). VisualNmap v1 doesn't run scripts, so here `-A` means `-sV -O --traceroute`. The ⓘ explanation says the same.

---

## 7. Watching a scan run

After you click Run you'll see:

- **Progress bar:** the percentage and time left, when Nmap reports them. For short phases Nmap doesn't report a percentage, so the bar shows the current phase (e.g. *"Connect Scan…"*) instead.
- **Output pane:** a terminal-style log of what Nmap is doing:

  ```
  Started: Ping Scan
  Finished: Ping Scan (1 host up)
  Started: Connect Scan
  Connect Scan 42% done, about 1 min left
  Finished: Connect Scan (1000 total ports)
  ```

- **Cancel:** stops Nmap. Anything already found is kept and the scan is marked *cancelled*.

You can close the tab. The scan keeps running, and re-opening it from **History** shows the output from the beginning. Only **one scan runs at a time**; while one is running, the Run button links to it.

---

## 8. Reading the results

When the scan finishes, the page switches to results.

**Summary strip:** hosts up / total scanned · open ports found · how long it took · status (completed / cancelled / failed).

**Hints panel:** appears when something went wrong or looks odd, with a suggested fix. The most common is:

> *"No hosts answered. Many devices (especially Windows PCs) block ping. Try again with 'Skip host discovery (-Pn)'."* → **[Retry with -Pn]**

**Host list:** each device that answered, with its IP, hostname (if known), MAC address and vendor (on local networks, as root), and OS guesses with confidence percentages.

**Port table** for the selected host:

| Port | Proto | State | Service | Version | What is this? |
|---|---|---|---|---|---|
| 22 | tcp | open | ssh | OpenSSH 8.9p1 | Remote command-line access. Should use keys, not passwords. |
| 80 | tcp | open | http | nginx 1.24 | Unencrypted website. Fine for local devices; prefer HTTPS on the internet. |
| 445 | tcp | filtered | microsoft-ds | | Windows file sharing (SMB). Should never be exposed to the internet. |

**What the states mean** (also shown in the "How to read this" panel):

| State | Meaning | In plain words |
|---|---|---|
| `open` | A program is accepting connections on this port | Something is listening here. This is what you're usually looking for. |
| `closed` | Reachable, but nothing is listening | The door exists but is locked. The host is definitely up. |
| `filtered` | No answer, or blocked by a firewall | Nmap can't tell: something (usually a firewall) is dropping the probes. |
| `unfiltered` | Reachable, but open/closed is unknown | Only seen with ACK scans (`-sA`). Used to map firewall rules. |
| `open\|filtered` | Can't tell open from filtered | Common with UDP: no reply could mean open or blocked. |
| `closed\|filtered` | Can't tell closed from filtered | Rare; seen with some IP ID idle scans. |

Buttons: **Export XML** (standard Nmap XML, which other tools can import), **Export JSON** (VisualNmap's cleaned-up format) and **Run again**.

---

## 9. History, compare and export

Open **History** in the top bar to see every scan with its date, target, profile, status, hosts up and open ports.

- **Open:** view its results again.
- **Re-run:** start the same scan again with the same options.
- **Delete:** remove it (not possible while it's running).
- **Export:** XML or JSON.
- **Compare:** tick **two** scans and click **Compare**. You'll see:
  - hosts that appeared or disappeared,
  - ports that **opened** or **closed** on each host,
  - services whose **version changed** (e.g. `OpenSSH 8.9 → 9.6`).

  Comparing two scans of the same target taken at different times is a simple way to spot changes on your network.

History is stored in `data/visualnmap.db` (SQLite). Delete that file to wipe all history.

---

## 10. Scan profiles cheat sheet

| Profile | Command (target omitted) | Typical time, 1 host | Needs 🔒 |
|---|---|---|---|
| Find devices | `nmap -sn` | seconds (a /24 takes ~10–30 s) | no (better with root: uses ARP on LANs) |
| Quick ports | `nmap -F -T4` | a few seconds | no |
| Full ports | `nmap -p- -T4` | 1–10 min | no |
| Services | `nmap -sV -F -T4` | 10 s–2 min | no |
| OS detection | `nmap -O --osscan-guess -F` | 10–30 s | yes |
| Stealth | `nmap -sS -T2 -F` | 1–3 min | yes |
| UDP common | `nmap -sU --top-ports 20` | 1–5 min | yes |
| Everything | `nmap -A -T4 -F` → `-sV -O --traceroute -T4 -F` | 30 s–3 min | yes |

---

## 11. Why some options have a 🔒

Normal programs talk to the network through the operating system's standard "connect" mechanism. Many of Nmap's best techniques need to **craft packets by hand** ("raw sockets"): sending only half of a TCP handshake (SYN scan), sending odd packets to fingerprint the OS, or probing UDP. Linux only allows that for **root** or for programs given the `CAP_NET_RAW` capability.

| Without raw sockets | With raw sockets (🔒 unlocked) |
|---|---|
| TCP connect scan (`-sT`): completes full connections, which is slower and more likely to be logged | SYN scan (`-sS`): faster and quieter |
| No OS detection | `-O` OS detection |
| No UDP scan | `-sU` UDP scan |
| Ping uses TCP connects | ICMP/ARP ping: more accurate device discovery |

VisualNmap detects which situation you're in:

- `./run.sh` (uses sudo) → 🔒 options available.
- `./run.sh --no-sudo` → 🔒 options disabled, **unless** your Nmap already has raw-socket capability (Kali Linux sets this up; VisualNmap detects it).
- Docker → available (the container is given `NET_RAW`).

---

## 12. Troubleshooting

| Problem | What to do |
|---|---|
| **"Nmap not found"** red banner | `sudo apt install nmap`, then restart the app. |
| **"Started without sudo"** yellow banner | Restart with `./run.sh` (not `--no-sudo`). |
| **Page doesn't load** | Is the terminal still showing "running at…"? Is something else using port 8765? Try `VISUALNMAP_PORT=8899 ./run.sh`. |
| **WSL2: Windows browser can't reach it** | WSL2 forwards `localhost` automatically on current Windows versions. If it doesn't, open `http://<WSL IP>:8765` (find it with `hostname -I`) **and** run with `VISUALNMAP_HOST=0.0.0.0`, but only on a trusted network (§13). |
| **"0 hosts up"** | The device may block ping. Use the **Retry with -Pn** button, or tick `-Pn` in the builder. |
| **"Couldn't find that host name"** | Typo, or DNS can't resolve it. Try the IP address instead. |
| **Everything shows `filtered`** | A firewall is dropping probes. Try fewer ports, `-Pn`, or (if you're allowed to) a different technique like `-sS`. |
| **Scan is taking forever** | Large ranges, `-p-`, UDP and `-T0`/`-T1` are slow. Cancel and narrow the target or ports. |
| **Docker: scanning `localhost` finds nothing useful** | In Docker, `localhost` is the container. Use your PC's LAN IP. See [§3.4](#34-docker-networking-limits-read-this). |
| **Docker: `docker` command not found in WSL** | Enable WSL Integration in Docker Desktop settings. |
| **Want a clean slate** | Stop the app and delete `data/visualnmap.db`. |

---

## 13. Security model

VisualNmap runs a powerful tool with root privileges, so it's deliberately locked down:

- **Localhost only.** It listens on `127.0.0.1`, so other computers on your network can't open the dashboard. Docker publishes the port on `127.0.0.1` only.
- **No shell.** Nmap is started directly with a list of arguments. Nothing is passed through `bash`, so typing `; rm -rf /` in a box does nothing.
- **Allowlist only.** Only the options listed in this README can reach Nmap. There is deliberately **no "extra arguments" box**: options like `--script`, `-iL` (read targets from a file) or `-oN` (write to a file) could read or write files as root.
- **Targets are validated** (IP, CIDR range, IP range or host name; nothing starting with `-`).
- **Cross-site protection.** The server rejects requests coming from other websites open in your browser.
- **Safe XML parsing** with `defusedxml`.

If you change `VISUALNMAP_HOST` to `0.0.0.0`, **anyone who can reach your machine can run scans as root through it**. Don't do that on untrusted networks.

---

## 14. Development

```
backend/    FastAPI app (python -m visualnmap)
  visualnmap/catalog/*.yaml   ← all explanation text lives here; edit freely
frontend/   React + TypeScript + Vite
docs/       design spec and implementation plan
```

**Backend:**

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest                       # unit + API tests (uses a fake nmap, no network)
VISUALNMAP_E2E=1 pytest -m e2e   # also runs real nmap against 127.0.0.1
```

**Frontend:**

```bash
cd frontend
npm ci
npm run dev        # dev server with hot reload, proxies /api to 127.0.0.1:8765
npm test           # Vitest
npm run build      # production build into frontend/dist
```

**Docker smoke test:**

```bash
scripts/docker-smoke.sh
```

**Improving explanations:** all user-facing explanations live in `backend/visualnmap/catalog/options.yaml`, `profiles.yaml` and `ports.yaml`. The test suite checks that every option has a label, summary, details, "when to use" and an example.

---

## License

MIT (see `LICENSE`).
