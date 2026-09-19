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
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_uqs = [uq["name"] for uq in insp.get_unique_constraints("departments") if uq.get("name")]
    existing_indexes = [ix["name"] for ix in insp.get_indexes("departments") if ix.get("name")]

    with op.batch_alter_table("departments", schema=None) as batch_op:
        for uq_name in ["departments_code_key", "uq_departments_code"]:
            if uq_name in existing_uqs:
                batch_op.drop_constraint(uq_name, type_="unique")
        if "ix_departments_code" in existing_indexes:
            batch_op.drop_index("ix_departments_code")
        if "uq_departments_tenant_code" not in existing_uqs:
            batch_op.create_unique_constraint("uq_departments_tenant_code", ["tenant_id", "code"])


def downgrade() -> None:
    with op.batch_alter_table("departments", schema=None) as batch_op:
        batch_op.drop_constraint("uq_departments_tenant_code", type_="unique")
        batch_op.create_unique_constraint("departments_code_key", ["code"])
