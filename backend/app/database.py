import logging
from typing import AsyncGenerator
# pyrefly: ignore [missing-import]
from sqlalchemy import text
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

logger = logging.getLogger(__name__)

# Determine engine kwargs
engine_kwargs = {
    "echo": False,
    "future": True,
}

db_url = settings.DATABASE_URL
if db_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # Production-grade PostgreSQL connection pooling
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 1800

# Create Async Engine
engine = create_async_engine(db_url, **engine_kwargs)

# Create Async Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Declarative Base Model
class Base(DeclarativeBase):
    pass

# Dependency helper for FastAPI routes
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def verify_db_connection() -> bool:
    """Verifies that the database engine can successfully connect and execute queries."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connectivity probe succeeded (SELECT 1 passed).")
        return True
    except Exception as e:
        logger.error(f"Database connectivity probe failed: {e}")
        return False

async def init_db():
    """Verify connectivity or initialize schema for local development."""
    is_connected = await verify_db_connection()
    if not is_connected and settings.DATABASE_URL.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Local SQLite tables created via Base.metadata.create_all.")
    elif is_connected:
        logger.info("Database connection active. Schema managed authoritatively via Alembic migrations.")
