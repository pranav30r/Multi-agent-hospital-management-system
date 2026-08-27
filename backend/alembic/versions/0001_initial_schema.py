"""Initial baseline schema migration (35 core hospital management tables)

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-08-27 19:41:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from app.database import Base
import app.models


# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Creates all initial models if not already present.
    Synchronizes Alembic version tracking with Base.metadata.
    """
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    """
    Rolls back initial tables in reverse dependency order.
    """
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
