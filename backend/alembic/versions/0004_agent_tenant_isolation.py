"""Add tenant isolation to agent decisions, crew runs, and approval items

Revision ID: 0004_agent_tenant_isolation
Revises: 0003_department_tenant_code_unique
Create Date: 2026-10-11 22:30:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_agent_tenant_isolation"
down_revision: Union[str, None] = "0003_department_tenant_code_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. Table: agent_decisions
    dec_cols = [c["name"] for c in insp.get_columns("agent_decisions")]
    dec_indexes = [ix["name"] for ix in insp.get_indexes("agent_decisions") if ix.get("name")]
    if "tenant_id" not in dec_cols:
        with op.batch_alter_table("agent_decisions", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "tenant_id",
                    sa.String(length=50),
                    sa.ForeignKey("tenants.id", name="fk_agent_decisions_tenant_id"),
                    nullable=False,
                    server_default="HOSP-DEFAULT",
                )
            )
        # Safe tenant backfill: link via encounters -> patients if available
        op.execute(
            sa.text(
                """
                UPDATE agent_decisions
                SET tenant_id = (
                    SELECT p.tenant_id
                    FROM encounters e
                    JOIN patients p ON e.patient_id = p.id
                    WHERE e.id = agent_decisions.encounter_id
                )
                WHERE encounter_id IS NOT NULL
                  AND EXISTS (
                    SELECT 1
                    FROM encounters e
                    JOIN patients p ON e.patient_id = p.id
                    WHERE e.id = agent_decisions.encounter_id
                      AND p.tenant_id IS NOT NULL
                  )
                """
            )
        )
    if "ix_agent_decisions_tenant_id" not in dec_indexes:
        op.create_index("ix_agent_decisions_tenant_id", "agent_decisions", ["tenant_id"])

    # 2. Table: crew_runs
    crew_cols = [c["name"] for c in insp.get_columns("crew_runs")]
    crew_indexes = [ix["name"] for ix in insp.get_indexes("crew_runs") if ix.get("name")]
    if "tenant_id" not in crew_cols:
        with op.batch_alter_table("crew_runs", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "tenant_id",
                    sa.String(length=50),
                    sa.ForeignKey("tenants.id", name="fk_crew_runs_tenant_id"),
                    nullable=False,
                    server_default="HOSP-DEFAULT",
                )
            )
    if "ix_crew_runs_tenant_id" not in crew_indexes:
        op.create_index("ix_crew_runs_tenant_id", "crew_runs", ["tenant_id"])

    # 3. Table: approval_items
    app_cols = [c["name"] for c in insp.get_columns("approval_items")]
    app_indexes = [ix["name"] for ix in insp.get_indexes("approval_items") if ix.get("name")]
    if "tenant_id" not in app_cols:
        with op.batch_alter_table("approval_items", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "tenant_id",
                    sa.String(length=50),
                    sa.ForeignKey("tenants.id", name="fk_approval_items_tenant_id"),
                    nullable=False,
                    server_default="HOSP-DEFAULT",
                )
            )
        # Safe tenant backfill: link via agent_decisions if available
        op.execute(
            sa.text(
                """
                UPDATE approval_items
                SET tenant_id = (
                    SELECT d.tenant_id
                    FROM agent_decisions d
                    WHERE d.id = approval_items.decision_id
                )
                WHERE decision_id IS NOT NULL
                  AND EXISTS (
                    SELECT 1
                    FROM agent_decisions d
                    WHERE d.id = approval_items.decision_id
                      AND d.tenant_id IS NOT NULL
                  )
                """
            )
        )
    if "ix_approval_items_tenant_id" not in app_indexes:
        op.create_index("ix_approval_items_tenant_id", "approval_items", ["tenant_id"])


def downgrade() -> None:
    # Drop indexes and columns in reverse order
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. approval_items
    app_indexes = [ix["name"] for ix in insp.get_indexes("approval_items") if ix.get("name")]
    if "ix_approval_items_tenant_id" in app_indexes:
        op.drop_index("ix_approval_items_tenant_id", table_name="approval_items")
    with op.batch_alter_table("approval_items", schema=None) as batch_op:
        batch_op.drop_column("tenant_id")

    # 2. crew_runs
    crew_indexes = [ix["name"] for ix in insp.get_indexes("crew_runs") if ix.get("name")]
    if "ix_crew_runs_tenant_id" in crew_indexes:
        op.drop_index("ix_crew_runs_tenant_id", table_name="crew_runs")
    with op.batch_alter_table("crew_runs", schema=None) as batch_op:
        batch_op.drop_column("tenant_id")

    # 3. agent_decisions
    dec_indexes = [ix["name"] for ix in insp.get_indexes("agent_decisions") if ix.get("name")]
    if "ix_agent_decisions_tenant_id" in dec_indexes:
        op.drop_index("ix_agent_decisions_tenant_id", table_name="agent_decisions")
    with op.batch_alter_table("agent_decisions", schema=None) as batch_op:
        batch_op.drop_column("tenant_id")
