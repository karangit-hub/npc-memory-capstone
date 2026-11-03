"""Opt-in, loopback-only UI and read-only inspection for a separate demo DB."""

import ipaddress
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from memory_store import DEFAULT_DB_PATH, inspect_chat_context
from summary_store import SummaryError

STATIC_DIR = Path(__file__).resolve().with_name("web")


class ContextPreview(BaseModel):
    player_id: str = Field(min_length=1, max_length=200)
    npc_id: str = Field(min_length=1, max_length=200)
    message: str = Field(default="", max_length=12000)


def install_demo(app, settings):
    def local_demo(request: Request):
        config = settings()
        if not config["enabled"]:
            raise HTTPException(404, "Local demo is disabled")
        try:
            local = request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
        except ValueError:
            local = False
        host = urlsplit("http://" + request.headers.get("host", "")).hostname
        origin = request.headers.get("origin")
        if (not local or host not in {"127.0.0.1", "localhost", "::1"}
                or (origin and origin != str(request.base_url).rstrip("/"))):
            raise HTTPException(403, "The demo is restricted to this localhost origin")
        if Path(config["db_path"]).resolve() == DEFAULT_DB_PATH.resolve():
            raise HTTPException(403, "The demo requires a separate database")
        return config

    router = APIRouter(prefix="/demo", dependencies=[Depends(local_demo)])

    @router.get("")
    def index():
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    @router.get("/assets/{name}")
    def asset(name: str):
        if name not in {"app.js", "styles.css"}:
            raise HTTPException(404, "Asset not found")
        return FileResponse(STATIC_DIR / name)

    @router.get("/api/status")
    async def status(config=Depends(local_demo)):
        result = {
            "backend": "online", "database_path": str(config["db_path"]),
            "database_is_isolated": True, "summary_context_enabled": config["summary_enabled"],
            "model": config["model"], "ollama_available": False, "model_installed": None,
        }
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get("http://127.0.0.1:11434/api/tags")
                response.raise_for_status()
            result["model_installed"] = any(m.get("name") == config["model"] for m in response.json()["models"])
            result["ollama_available"] = True
        except (httpx.HTTPError, ValueError, KeyError) as error:
            result["ollama_error"] = str(error)
        return result

    @router.post("/api/context")
    def preview(body: ContextPreview, config=Depends(local_demo)):
        try:
            return inspect_chat_context(
                body.player_id, body.npc_id, body.message, config["db_path"],
                include_summary=config["summary_enabled"],
            )
        except SummaryError as error:
            raise HTTPException(503, str(error)) from error

    app.include_router(router)

    @app.middleware("http")
    async def demo_headers(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/demo"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; object-src 'none'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'self'"
            )
        return response
