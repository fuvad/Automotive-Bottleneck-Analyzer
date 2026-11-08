"""FastAPI application entry point and infrastructure health endpoints."""

import asyncio
import logging
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from bottleneck_analyzer.api.routes import router
from bottleneck_analyzer.api.runtime import InvestigationRuntime
from bottleneck_analyzer.api.security import LocalBoundary
from bottleneck_analyzer.api.settings import APISettings
from bottleneck_analyzer.core.config import get_settings
from bottleneck_analyzer.core.logging import configure_logging
from bottleneck_analyzer.db.session import check_database_health, create_db_engine

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    """Application liveness response."""

    status: str
    service: str
    tracing_enabled: bool


class DatabaseHealthResponse(BaseModel):
    """Database and pgvector readiness response."""

    status: str
    database_connected: bool
    pgvector_available: bool
    vector_operations_available: bool
    detail: str


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Configure logging at startup and emit a clear shutdown event."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("application_starting", extra={"app_env": settings.app_env})
    application.state.investigations = InvestigationRuntime()
    try:
        yield
    finally:
        await asyncio.to_thread(application.state.investigations.close)
        logger.info("application_stopping")


app = FastAPI(title="Automotive Bottleneck Analyzer", lifespan=lifespan)
app.add_middleware(LocalBoundary, port=get_settings().app_port, settings=APISettings())
app.include_router(router)
static_path = Path(__file__).parent / "api" / "static"
# Windows MIME mappings can report application/x-css, which browsers reject.
mimetypes.add_type("text/css", ".css")
app.mount("/static", StaticFiles(directory=static_path, check_dir=False), name="static")


@app.get("/", include_in_schema=False)
def interface():
    return FileResponse(static_path / "index.html")


@app.exception_handler(RequestValidationError)
async def invalid_request(_, exc):
    return JSONResponse(
        {
            "error": {
                "code": "invalid_request",
                "message": "Invalid request",
                "fields": [".".join(map(str, e["loc"])) for e in exc.errors()[:20]],
            }
        },
        status_code=422,
    )


@app.exception_handler(HTTPException)
async def http_error(_, exc):
    detail = (
        exc.detail
        if isinstance(exc.detail, dict)
        else {"code": "http_error", "message": "Request could not be served"}
    )
    return JSONResponse({"error": detail}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(SQLAlchemyError)
@app.exception_handler(ValueError)
async def infrastructure_error(_, exc):
    logger.warning("api_infrastructure_unavailable", extra={"category": type(exc).__name__})
    return JSONResponse(
        {
            "error": {
                "code": "infrastructure_unavailable",
                "message": "Database or configuration unavailable",
            }
        },
        status_code=503,
    )


@app.exception_handler(Exception)
async def unexpected_error(_, exc):
    logger.error("api_unexpected_error", extra={"category": type(exc).__name__})
    return JSONResponse(
        {
            "error": {
                "code": "internal_error",
                "message": "Request failed; inspect local diagnostics",
            }
        },
        status_code=500,
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report that the application process is alive without contacting a database."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="automotive-bottleneck-analyzer",
        tracing_enabled=settings.langsmith_tracing,
    )


@app.get("/health/database", response_model=DatabaseHealthResponse)
def database_health() -> DatabaseHealthResponse:
    """Check configured PostgreSQL connectivity and the pgvector extension."""
    try:
        engine = create_db_engine()
    except ValueError:
        return DatabaseHealthResponse(
            status="misconfigured",
            database_connected=False,
            pgvector_available=False,
            vector_operations_available=False,
            detail="Database configuration is missing or invalid",
        )

    try:
        result = check_database_health(engine)
    finally:
        engine.dispose()
    return DatabaseHealthResponse(
        status=result.status,
        database_connected=result.database_connected,
        pgvector_available=result.pgvector_available,
        vector_operations_available=result.vector_operations_available,
        detail=result.detail if result.database_connected else "Database connection unavailable",
    )
