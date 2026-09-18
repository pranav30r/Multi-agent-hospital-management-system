"""Scope department code uniqueness to tenant_id (composite unique constraint)

Revision ID: 0003_department_tenant_code_unique
Revises: 0002_enterprise_foundation
Create Date: 2026-09-17 20:05:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_department_tenant_code_unique"
down_revision: Union[str, None] = "0002_enterprise_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Safely remove existing global uniqueness on code and establish composite (tenant_id, code) uniqueness
    with op.batch_alter_table("departments", schema=None) as batch_op:
        try:
            batch_op.drop_constraint("departments_code_key", type_="unique")
        except Exception:
            pass
        try:
            batch_op.drop_constraint("uq_departments_code", type_="unique")
        except Exception:
            pass
        try:
            batch_op.drop_index("ix_departments_code")
        except Exception:
            pass
        batch_op.create_unique_constraint("uq_departments_tenant_code", ["tenant_id", "code"])


def downgrade() -> None:
    with op.batch_alter_table("departments", schema=None) as batch_op:
        batch_op.drop_constraint("uq_departments_tenant_code", type_="unique")
        batch_op.create_unique_constraint("departments_code_key", ["code"])
