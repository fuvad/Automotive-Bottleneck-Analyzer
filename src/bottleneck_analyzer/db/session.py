"""Create PostgreSQL engines, sessions, and health checks."""

from collections.abc import Generator
from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from bottleneck_analyzer.core.config import get_settings


def create_db_engine(database_url: str | None = None) -> Engine:
    """Build a lazy SQLAlchemy engine for the configured psycopg driver."""
    settings = get_settings()
    url = database_url if database_url is not None else settings.require_database_url()
    if not url.startswith("postgresql+psycopg://"):
        raise ValueError("DATABASE_URL must use postgresql+psycopg://")
    return create_engine(
        url,
        connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
        pool_pre_ping=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Provide transaction-scoped sessions for later repositories."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@dataclass(frozen=True)
class DatabaseHealth:
    """Result of a live PostgreSQL and pgvector capability check."""

    status: str
    database_connected: bool
    pgvector_available: bool
    vector_operations_available: bool
    detail: str


def check_database_health(engine: Engine) -> DatabaseHealth:
    """Check connectivity and report whether the pgvector extension is available."""
    if engine.url.drivername != "postgresql+psycopg":
        return DatabaseHealth(
            "misconfigured", False, False, False, "PostgreSQL psycopg is required"
        )

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            pgvector_available = bool(
                connection.execute(
                    text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
                ).scalar_one()
            )
            vector_operations_available = False
            if pgvector_available:
                distance = connection.execute(
                    text("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector")
                ).scalar_one()
                vector_operations_available = float(distance) == 1.0
    except Exception as exc:  # Database diagnostics must return a useful API response.
        return DatabaseHealth(
            "unavailable", False, False, False, f"Database connection failed: {exc}"
        )

    if not pgvector_available:
        return DatabaseHealth(
            "degraded",
            True,
            False,
            False,
            "PostgreSQL is reachable, but the pgvector extension is not installed",
        )
    if not vector_operations_available:
        return DatabaseHealth(
            "degraded",
            True,
            True,
            False,
            "pgvector is installed, but the vector operation check failed",
        )
    return DatabaseHealth(
        "healthy", True, True, True, "PostgreSQL and pgvector vector operations are available"
    )


def get_db_session() -> Generator[Session, None, None]:
    """Yield a request-scoped session for future read-only application endpoints."""
    engine = create_db_engine()
    factory = create_session_factory(engine)
    try:
        with factory() as session:
            yield session
    finally:
        engine.dispose()
