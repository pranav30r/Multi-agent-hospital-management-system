import os
import sys
import asyncio
import pytest
import pytest_asyncio
from pathlib import Path
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text, select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.database import Base
from app.models import (
    Department, Bed, BedAssignment, Staff, StaffShift, StaffSkill,
    Equipment, EquipmentBooking, Disease, WorkflowDefinition,
    Patient, Encounter, AgentDecision, ApprovalItem, AuditLog
)

DATABASE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "database"

# Dedicated PostgreSQL test database URL (configurable via env var)
PG_TEST_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgrespassword@localhost:5433/hospital_test"
)

try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False


async def is_postgres_available() -> bool:
    """Checks whether asyncpg is installed and PostgreSQL test instance is reachable."""
    if not HAS_ASYNCPG:
        return False
    test_engine = create_async_engine(PG_TEST_URL, poolclass=NullPool)
    try:
        async with test_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await test_engine.dispose()
        return True
    except Exception:
        try:
            await test_engine.dispose()
        except Exception:
            pass
        return False


@pytest_asyncio.fixture(scope="function")
async def pg_db():
    """
    Initializes PostgreSQL tables and applies dedicated SQL seed files.
    Provides an async_sessionmaker that opens independent PostgreSQL connections (NullPool)
    for true multi-connection pessimistic concurrency and lock testing.
    """
    if not await is_postgres_available():
        pytest.skip(f"PostgreSQL test database is unreachable at {PG_TEST_URL}. Requires Docker / PostgreSQL.")

    engine = create_async_engine(
        PG_TEST_URL,
        poolclass=NullPool,
        isolation_level="READ COMMITTED"
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Seed SQL files directly into PostgreSQL with strict error propagation
    seed_files = [
        "02_seed_infrastructure.sql",
        "03_seed_clinical.sql",
        "04_seed_workflows.sql",
        "05_seed_operational.sql"
    ]
    async with session_factory() as session:
        for s_file in seed_files:
            file_path = DATABASE_DIR / s_file
            if not file_path.exists():
                raise FileNotFoundError(f"Required seed file not found: {file_path}")
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            for stmt in content.split(";"):
                s = stmt.strip()
                if s:
                    await session.execute(text(s))
        await session.commit()

        # Explicitly verify required seed entities exist for concurrency tests
        required_entities = [
            (Bed, "BED-ICU-01"),
            (Bed, "BED-WA-01"),
            (Equipment, "RES-CT-01"),
        ]
        for model_cls, entity_id in required_entities:
            stmt = select(model_cls).where(model_cls.id == entity_id)
            res = await session.execute(stmt)
            if res.scalar_one_or_none() is None:
                raise RuntimeError(
                    f"PostgreSQL seed verification failure: {model_cls.__name__} '{entity_id}' not found after seeding."
                )

    yield session_factory

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    finally:
        await engine.dispose()
