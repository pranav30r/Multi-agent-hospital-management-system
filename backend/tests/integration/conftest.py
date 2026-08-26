import os
import sys
import asyncio
import pytest
import pytest_asyncio
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text, select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.database import Base
from app.models import Department, Bed, Staff, Equipment, Disease, WorkflowDefinition

DATABASE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "database"

# Dedicated PostgreSQL test database URL (configurable via env var)
PG_TEST_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgrespassword@localhost:5433/hospital_test"
)

try:
    import asyncpg
    HAS_ASYNCPG = True
    pg_test_engine = create_async_engine(
        PG_TEST_URL,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
        isolation_level="READ COMMITTED"
    )
    PgTestingSessionLocal = async_sessionmaker(
        bind=pg_test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
except ImportError:
    HAS_ASYNCPG = False
    pg_test_engine = None
    PgTestingSessionLocal = None

async def is_postgres_available() -> bool:
    """Checks whether asyncpg is installed and PostgreSQL test instance is reachable."""
    if not HAS_ASYNCPG or pg_test_engine is None:
        return False
    try:
        async with pg_test_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

@pytest_asyncio.fixture(scope="session")
def event_loop():
    """Create an event loop for the integration test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="function")
async def pg_db():
    """
    Initializes PostgreSQL tables and applies dedicated SQL seed files.
    Skips test if PostgreSQL daemon is unreachable on the current host.
    """
    if not await is_postgres_available():
        pytest.skip(f"PostgreSQL test database is unreachable at {PG_TEST_URL}. Requires Docker / PostgreSQL.")

    async with pg_test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Seed SQL files directly into PostgreSQL
    seed_files = [
        "02_seed_infrastructure.sql",
        "03_seed_clinical.sql",
        "04_seed_workflows.sql",
        "05_seed_operational.sql"
    ]
    async with PgTestingSessionLocal() as session:
        for s_file in seed_files:
            file_path = DATABASE_DIR / s_file
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                for stmt in content.split(";"):
                    s = stmt.strip()
                    if s:
                        try:
                            await session.execute(text(s))
                        except Exception:
                            pass
        await session.commit()

    yield PgTestingSessionLocal

    async with pg_test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
