"""FastAPI entrypoint and route registration (owner: Olamide).

Run from backend/:  uvicorn app.main:app --port 8000
The frontend's dev server proxies /api to it (frontend/vite.config.js); open the app with ?mock=0 to use it.
After `npm run build`, this app also serves frontend/dist.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

from app import scheduler, seed  # noqa: E402  (after .env is loaded)
from app.db import Store, set_store, store  # noqa: E402
from app.routes import assistant, auth, care, voice  # noqa: E402
from app.util import ApiError  # noqa: E402

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    set_store(Store())
    if store().is_empty() and os.getenv("CARELOOP_SEED", "1") == "1":
        seed.load_into(store())
        store().flush()
    if os.getenv("CARELOOP_SCHEDULER", "1") == "1":
        scheduler.start()
    yield
    scheduler.stop()
    store().flush()


app = FastAPI(title="CareLoop API", lifespan=lifespan)


@app.exception_handler(ApiError)
async def api_error(_: Request, error: ApiError):
    return JSONResponse({"detail": error.detail, **error.extra}, status_code=error.status)


@app.exception_handler(RequestValidationError)
async def bad_request(_: Request, error: RequestValidationError):
    return JSONResponse({"detail": "Some details are missing or not in the right format."}, status_code=400)


@app.middleware("http")
async def save_changes(request: Request, call_next):
    """Write whatever the request changed. Errors still save (failed code tries and lockouts must stick)."""
    try:
        return await call_next(request)
    finally:
        if request.url.path.startswith("/api"):
            store().flush()


@app.get("/api/health")
def health():
    return {"ok": True}


for router in (auth.router, care.router, voice.router, voice.worker, assistant.router):
    app.include_router(router, prefix="/api")

DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
