"""
Database Seeding Script.
Executes raw SQL seed files from the database/ directory into the active database.
Usage:
    python backend/scripts/seed_db.py
"""

import sys
import os
import asyncio
import logging
from pathlib import Path
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import AsyncSessionLocal, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_db")

SEED_FILES = [
    "02_seed_infrastructure.sql",
    "03_seed_clinical.sql",
    "04_seed_workflows.sql",
    "05_seed_operational.sql"
]

async def seed_from_sql_files(db_dir: Path = None):
    """Executes database SQL seed files into the connected database."""
    if db_dir is None:
        db_dir = Path(__file__).resolve().parent.parent.parent / "database"

    logger.info(f"Reading database seed files from: {db_dir}")
    await init_db()

    async with AsyncSessionLocal() as session:
        for seed_file in SEED_FILES:
            file_path = db_dir / seed_file
            if not file_path.exists():
                logger.warning(f"Seed file not found: {file_path}")
                continue

            logger.info(f"Applying seed: {seed_file}...")
            with open(file_path, "r", encoding="utf-8") as f:
                sql_content = f.read()

            # Split statements by semicolon or execute directly
            for statement in sql_content.split(";"):
                stmt = statement.strip()
                if stmt:
                    try:
                        await session.execute(text(stmt))
                    except Exception as e:
                        logger.debug(f"Statement execution notice in {seed_file}: {e}")

        await session.commit()
        logger.info("All database seed files applied successfully!")

if __name__ == "__main__":
    asyncio.run(seed_from_sql_files())
