"""Live PostgreSQL and pgvector checks for a configured local environment."""

import pytest
from sqlalchemy import text

from bottleneck_analyzer.core.config import get_settings
from bottleneck_analyzer.db.session import create_db_engine


def test_postgresql_connectivity_and_vector_operation() -> None:
    """Verify the configured database and a real pgvector distance operation."""
    settings = get_settings()
    if not settings.database_url:
        pytest.skip("DATABASE_URL is not configured")

    engine = create_db_engine()
    try:
        with engine.connect() as connection:
            connected = connection.execute(text("SELECT 1")).scalar_one()
            extension = connection.execute(
                text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
            ).scalar_one()
            distance = connection.execute(
                text("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector")
            ).scalar_one()
    except Exception as exc:
        pytest.fail(f"Configured PostgreSQL/pgvector validation failed: {exc}")
    finally:
        engine.dispose()

    assert connected == 1
    assert extension is True
    assert float(distance) == 1.0
