"""FastAPI application entry point and infrastructure health endpoints."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

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
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Configure logging at startup and emit a clear shutdown event."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("application_starting", extra={"app_env": settings.app_env})
    try:
        yield
    finally:
        logger.info("application_stopping")


app = FastAPI(title="Automotive Bottleneck Analyzer", lifespan=lifespan)


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
    except ValueError as exc:
        return DatabaseHealthResponse(
            status="misconfigured",
            database_connected=False,
            pgvector_available=False,
            vector_operations_available=False,
            detail=str(exc),
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
        detail=result.detail,
    )
