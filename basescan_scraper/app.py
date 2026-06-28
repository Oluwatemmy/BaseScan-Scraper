# basescan_scraper/app.py
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from basescan_scraper.api import deps
from basescan_scraper.api.errors import register_error_handlers
from basescan_scraper.api.routers import addresses, health
from basescan_scraper.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # On shutdown, close the cached httpx client — but only if it was created,
    # to avoid instantiating a client just to close it.
    if deps._fetcher.cache_info().currsize > 0:
        await deps._fetcher().aclose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="BaseScan Scraper API",
        version="0.1.0",
        description="Read-only REST API exposing Base chain data scraped from basescan.org.",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "Health", "description": "Service liveness."},
            {"name": "Addresses", "description": "Wallet/address data."},
        ],
    )

    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_methods=["GET"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(addresses.router)
    return app


app = create_app()
