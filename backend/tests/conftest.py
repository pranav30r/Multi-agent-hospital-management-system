import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pathlib import Path
from sqlalchemy import text
from app.database import Base, get_db
from app.main import app
from app.auth.security import create_access_token

# In-memory SQLite async database for isolated fast test runs
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

DATABASE_DIR = Path(__file__).resolve().parent.parent.parent / "database"
SEED_SQL_FILES = [
    "02_seed_infrastructure.sql",
    "03_seed_clinical.sql",
    "04_seed_workflows.sql",
    "05_seed_operational.sql"
]


@pytest_asyncio.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_db():
    """Initializes schema and seeds fresh synthetic data from database seed files for each test run."""
    def seed_sync(sync_conn):
        for seed_file in SEED_SQL_FILES:
            file_path = DATABASE_DIR / seed_file
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().replace("::jsonb", "")
                try:
                    # SQLite DBAPI executescript executes entire multi-statement SQL natively
                    sync_conn.connection.dbapi_connection.executescript(content)
                except Exception as e:
                    # Fallback to standard execution if driver wrapper differs
                    for statement in content.split(";"):
                        stmt = statement.strip()
                        if stmt:
                            sync_conn.exec_driver_sql(stmt)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(seed_sync)

    yield TestingSessionLocal

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(test_db):
    """Provides an async HTTP test client with database dependency override."""
    async def override_get_db():
        async with test_db() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def make_auth_headers():
    """Helper fixture to generate JWT authorization headers for any staff role."""
    def _make(staff_id: str = "DOC-001", role: str = "DOCTOR", name: str = "Dr. Test", department_id: str = "DEP-ER"):
        token = create_access_token({
            "sub": staff_id,
            "role": role,
            "name": name,
            "department_id": department_id
        })
        return {"Authorization": f"Bearer {token}"}
    return _make


@pytest_asyncio.fixture(scope="function")
async def auth_client(client, make_auth_headers):
    """Client pre-authenticated as a DOCTOR (DOC-001)."""
    headers = make_auth_headers(staff_id="DOC-001", role="DOCTOR")
    client.headers.update(headers)
    return client


@pytest_asyncio.fixture(scope="function")
async def admin_client(client, make_auth_headers):
    """Client pre-authenticated as an ADMINISTRATOR (ADM-001)."""
    headers = make_auth_headers(staff_id="ADM-001", role="ADMINISTRATOR")
    client.headers.update(headers)
    return client
