"""FastAPI entry point — the single service-layer process from §5."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import api
from app.stores import Stores


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.stores = Stores.from_settings(settings)
    try:
        yield
    finally:
        await app.state.stores.close()


app = FastAPI(
    title="Repair Assistant",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router)


@app.get("/health", tags=["ops"])
async def health(request: Request) -> JSONResponse:
    """Liveness plus a probe of each store. 200 only when all three answer."""
    settings = get_settings()
    stores: Stores = request.app.state.stores
    report = await stores.probe_all()
    all_ok = all(entry["status"] == "ok" for entry in report.values())
    body = {
        "status": "ok" if all_ok else "degraded",
        "env": settings.app_env,
        "llm_backend": settings.llm_backend,
        "stores": report,
    }
    return JSONResponse(body, status_code=200 if all_ok else 503)
