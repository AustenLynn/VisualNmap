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
