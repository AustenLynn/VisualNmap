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
