from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.services.attendance import AttendanceService
from app.services import scanner_simulator
from app.routers.admin import router as admin_router
from app.runtime import (
    DB_PATH,
    RESOURCE_DIR,
    backup_database,
    backup_loop,
    configure_logging,
)

logger = configure_logging()
SERVER_HOST = "127.0.0.1"

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        path = backup_database(DB_PATH)
        logger.info("Backup saat aplikasi mulai dibuat: %s", path)
    except Exception:
        logger.exception("Backup saat aplikasi mulai gagal.")
    app.state.backup_task = asyncio.create_task(backup_loop(DB_PATH))

    yield

    task = app.state.backup_task
    if task:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    logger.info("Aplikasi dihentikan.")


app = FastAPI(title="Absensi TPA", lifespan=lifespan)
templates = Jinja2Templates(directory=str(RESOURCE_DIR / "app" / "templates"))
app.mount("/static", StaticFiles(directory=str(RESOURCE_DIR / "app" / "static")), name="static")
attendance = AttendanceService(DB_PATH)
app.state.templates = templates
app.state.simulator_enabled = scanner_simulator.is_simulation_enabled()
scanner_simulator.log_simulation_status()
app.include_router(admin_router)
app.state.backup_task = None


class TapRequest(BaseModel):
    uid: str
    client_id: str | None = None
    client_tap_id: str | None = None
    age_ms: int = 0


def local_time() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def client_address(request: Request) -> str:
    return request.client.host if request.client else ""


def require_local_admin(request: Request) -> None:
    if client_address(request) not in {"127.0.0.1", "::1"}:
        raise HTTPException(
            status_code=403,
            detail="Halaman ini hanya bisa dibuka dari pc admin.",
        )


@app.get("/scan", response_class=HTMLResponse)
async def scan_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="scan.html",
        context={"title": "Scanner Absensi TPA"},
    )


@app.get("/api/ping")
async def ping() -> dict[str, Any]:
    return {"ok": True, "server_time": local_time()}


@app.post("/api/tap")
async def tap(payload: TapRequest, request: Request) -> JSONResponse:
    result = attendance.tap(
        payload.uid,
        payload.client_id or request.headers.get("X-Client-ID"),
        payload.client_tap_id,
        payload.age_ms,
    )
    logger.info("Tap %s dari %s", result["hasil"], client_address(request))
    return JSONResponse(result)


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc: HTTPException) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="forbidden.html",
        context={"title": "Akses ditolak", "message": str(exc.detail)},
        status_code=403,
    )

if __name__ == "__main__":
    import os
    import uvicorn

    uvicorn.run(
        app,
        host=SERVER_HOST,
        port=int(os.environ.get("ABSENSI_PORT", "8000")),
    )
