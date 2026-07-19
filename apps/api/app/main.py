from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.api import router
from app.config import Settings, get_settings
from app.database import Database
from app.processor import Processor
from app.providers.factory import create_partner_provider
from app.sample_data import seed_sample_task
from app.storage import create_storage


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = Database(resolved)
        storage = create_storage(resolved)
        processor = Processor(resolved, database, storage)
        partner_provider, partner_source = create_partner_provider(resolved)
        app.state.settings = resolved
        app.state.database = database
        app.state.storage = storage
        app.state.processor = processor
        app.state.partner_provider = partner_provider
        app.state.partner_source = partner_source
        app.state.partner_turn_cache = {}
        if resolved.auto_create_db:
            await database.create_schema()
        async with database.sessions() as db:
            await seed_sample_task(db)
        worker_task: asyncio.Task[None] | None = None
        if resolved.enable_inline_worker:
            worker_task = asyncio.create_task(processor.run_forever(), name="part2-job-processor")
        try:
            yield
        finally:
            await processor.stop()
            if worker_task:
                with suppress(TimeoutError):
                    await asyncio.wait_for(worker_task, timeout=2)
            await database.dispose()

    app = FastAPI(
        title="B2 Speaking Part 2 Practice API",
        version="0.1.0",
        debug=False,
        lifespan=lifespan,
        docs_url=None if resolved.environment == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if resolved.environment == "production" else "/openapi.json",
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=resolved.trusted_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Upload-Token"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=(self)"
        if request.url.path.startswith("/v1/practice-sessions"):
            response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.exception_handler(Exception)
    async def safe_unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        # Do not echo exception details: provider errors may contain request metadata.
        return JSONResponse(status_code=500, content={"detail": "Internal processing error"})

    app.include_router(router)
    return app
