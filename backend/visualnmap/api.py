"""FastAPI app: REST + WebSocket API and the built frontend."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable
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
# Host names the dashboard answers to. Anything else is refused, which blocks DNS-rebinding
# attacks (a web page whose own domain is made to resolve to 127.0.0.1).
DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "localhost", "::1")
WILDCARD_BINDS = ("0.0.0.0", "::", "")


@dataclass
class Settings:
    host: str
    port: int
    data_dir: Path
    static_dir: Path
    allowed_hosts: list[str]

    @classmethod
    def from_env(cls) -> "Settings":
        host = os.environ.get("VISUALNMAP_HOST", "127.0.0.1")
        extra = [h.strip() for h in os.environ.get("VISUALNMAP_ALLOWED_HOSTS", "").split(",") if h.strip()]
        allowed = [*DEFAULT_ALLOWED_HOSTS, *extra]
        if host not in WILDCARD_BINDS:
            allowed.append(host)
        return cls(
            host=host,
            port=int(os.environ.get("VISUALNMAP_PORT", "8765")),
            data_dir=Path(os.environ.get("VISUALNMAP_DATA", "data")),
            static_dir=Path(os.environ.get("VISUALNMAP_STATIC", str(REPO_ROOT / "frontend" / "dist"))),
            allowed_hosts=allowed,
        )


def hostname_of(host_header: str) -> str:
    """The hostname part of a Host header, lower-cased, without port or IPv6 brackets."""
    host = host_header.strip().lower()
    if host.startswith("["):
        return host[1 : host.index("]")] if "]" in host else host[1:]
    if host.count(":") == 1:
        return host.split(":", 1)[0]
    return host


def _origin_ok(headers) -> bool:
    origin = headers.get("origin")
    if origin is None:
        return True
    host = headers.get("host", "")
    return origin in (f"http://{host}", f"https://{host}")


class HostGuard:
    """ASGI middleware: refuse HTTP requests and WebSockets whose Host header isn't allowed."""

    def __init__(self, app, allowed: Iterable[str]):
        self.app = app
        self.allowed = {h.lower() for h in allowed}

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            host = dict(scope["headers"]).get(b"host", b"").decode("latin-1")
            if hostname_of(host) not in self.allowed:
                if scope["type"] == "http":
                    response = JSONResponse(
                        {"detail": "Unknown host name. Open VisualNmap at http://127.0.0.1:8765 "
                                   "(or add the name to VISUALNMAP_ALLOWED_HOSTS)."},
                        status_code=400,
                    )
                    await response(scope, receive, send)
                else:
                    await receive()  # websocket.connect
                    await send({"type": "websocket.close", "code": 1008})
                return
        await self.app(scope, receive, send)


def check_origin(request: Request) -> None:
    if not _origin_ok(request.headers):
        raise HTTPException(status_code=403, detail="Cross-site request blocked.")


def _error(status: int, **body) -> JSONResponse:
    return JSONResponse(status_code=status, content=body)


def create_app(
    env: Environment,
    catalog: Catalog,
    history: History,
    static_dir: Path | None = None,
    allowed_hosts: Iterable[str] = DEFAULT_ALLOWED_HOSTS,
) -> FastAPI:
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
    app.add_middleware(HostGuard, allowed=list(allowed_hosts))
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
