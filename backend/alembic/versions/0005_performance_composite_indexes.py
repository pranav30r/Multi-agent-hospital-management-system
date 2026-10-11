"""Add composite performance indexes for observations, encounters, and patients

Revision ID: 0005_performance_composite_indexes
Revises: 0004_agent_tenant_isolation
Create Date: 2026-10-12 01:36:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005_performance_composite_indexes"
down_revision: Union[str, None] = "0004_agent_tenant_isolation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. clinical_observations composite indexes
    if "clinical_observations" in insp.get_table_names():
        obs_indexes = {ix["name"] for ix in insp.get_indexes("clinical_observations") if ix.get("name")}
        if "idx_obs_tenant_patient_observed" not in obs_indexes:
            op.create_index(
                "idx_obs_tenant_patient_observed",
                "clinical_observations",
                ["tenant_id", "patient_id", "observed_at"],
                unique=False,
            )
        if "idx_obs_tenant_patient_type_observed" not in obs_indexes:
            op.create_index(
                "idx_obs_tenant_patient_type_observed",
                "clinical_observations",
                ["tenant_id", "patient_id", "observation_type", "observed_at"],
                unique=False,
            )

    # 2. encounters composite index
    if "encounters" in insp.get_table_names():
        enc_indexes = {ix["name"] for ix in insp.get_indexes("encounters") if ix.get("name")}
        if "ix_encounters_patient_arrival" not in enc_indexes:
            op.create_index(
                "ix_encounters_patient_arrival",
                "encounters",
                ["patient_id", "arrival_time"],
                unique=False,
            )

    # 3. patients composite index
    if "patients" in insp.get_table_names():
        pat_indexes = {ix["name"] for ix in insp.get_indexes("patients") if ix.get("name")}
        if "ix_patients_tenant_phone" not in pat_indexes:
            op.create_index(
                "ix_patients_tenant_phone",
                "patients",
                ["tenant_id", "contact_phone"],
                unique=False,
            )
        if "ix_patients_tenant_created" not in pat_indexes:
            op.create_index(
                "ix_patients_tenant_created",
                "patients",
                ["tenant_id", "created_at"],
                unique=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "patients" in insp.get_table_names():
        pat_indexes = {ix["name"] for ix in insp.get_indexes("patients") if ix.get("name")}
        if "ix_patients_tenant_created" in pat_indexes:
            op.drop_index("ix_patients_tenant_created", table_name="patients")
        if "ix_patients_tenant_phone" in pat_indexes:
            op.drop_index("ix_patients_tenant_phone", table_name="patients")

    if "encounters" in insp.get_table_names():
        enc_indexes = {ix["name"] for ix in insp.get_indexes("encounters") if ix.get("name")}
        if "ix_encounters_patient_arrival" in enc_indexes:
            op.drop_index("ix_encounters_patient_arrival", table_name="encounters")

    if "clinical_observations" in insp.get_table_names():
        obs_indexes = {ix["name"] for ix in insp.get_indexes("clinical_observations") if ix.get("name")}
        if "idx_obs_tenant_patient_type_observed" in obs_indexes:
            op.drop_index("idx_obs_tenant_patient_type_observed", table_name="clinical_observations")
        if "idx_obs_tenant_patient_observed" in obs_indexes:
            op.drop_index("idx_obs_tenant_patient_observed", table_name="clinical_observations")
