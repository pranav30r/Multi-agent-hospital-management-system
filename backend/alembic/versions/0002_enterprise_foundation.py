"""Enterprise Data Foundation & Scalability Migration

Revision ID: 0002_enterprise_foundation
Revises: 0001_initial_schema
Create Date: 2026-09-05 20:30:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_enterprise_foundation"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Table: tenants (hospital deployment boundaries)
    op.create_table(
        'tenants',
        sa.Column('id', sa.String(length=50), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('contact_phone', sa.String(length=25), nullable=True),
        sa.Column('contact_email', sa.String(length=100), nullable=True),
        sa.Column('address', sa.String(length=255), nullable=True),
        sa.Column('timezone', sa.String(length=50), nullable=False, server_default='UTC'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index('ix_tenants_code', 'tenants', ['code'], unique=True)

    # 2. Backfill: Insert default legacy facility
    op.execute(
        sa.text(
            "INSERT INTO tenants (id, name, code, description, is_active, timezone, created_at, updated_at) "
            "VALUES ('HOSP-DEFAULT', 'Default Legacy Facility', 'HOSP-DEF', 'System default facility for migrated records', true, 'UTC', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    )

    # 3. Add direct tenant_id to root entity tables
    for table_name in ['departments', 'staff', 'patients', 'emergency_events', 'audit_log']:
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.add_column(sa.Column('tenant_id', sa.String(length=50), sa.ForeignKey('tenants.id', name=f"fk_{table_name}_tenant_id"), nullable=False, server_default='HOSP-DEFAULT'))

    # 4. Table: clinical_observations (normalized longitudinal vitals & measurements)
    op.create_table(
        'clinical_observations',
        sa.Column('id', sa.String(length=50), primary_key=True),
        sa.Column('patient_id', sa.String(length=50), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('encounter_id', sa.String(length=50), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('tenant_id', sa.String(length=50), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('observation_type', sa.String(length=50), nullable=False),
        sa.Column('value_numeric', sa.Float(), nullable=True),
        sa.Column('value_text', sa.Text(), nullable=True),
        sa.Column('unit', sa.String(length=30), nullable=True),
        sa.Column('observed_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('recorded_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('recorded_by', sa.String(length=50), nullable=False, server_default='SYSTEM'),
        sa.Column('source', sa.String(length=30), nullable=False, server_default='MANUAL'),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='ACTIVE'),
        sa.Column('correction_of', sa.String(length=50), sa.ForeignKey('clinical_observations.id'), nullable=True),
        sa.Column('correction_reason', sa.String(length=255), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )

    # 5. Composite B-Tree Indexes for Enterprise Scale
    op.create_index('ix_patients_tenant_id', 'patients', ['tenant_id'])
    op.create_index('ix_departments_tenant_id', 'departments', ['tenant_id'])
    op.create_index('ix_staff_tenant_id', 'staff', ['tenant_id'])
    op.create_index('ix_emergency_events_tenant_id', 'emergency_events', ['tenant_id'])
    op.create_index('ix_audit_log_tenant_timestamp', 'audit_log', ['tenant_id', sa.text('timestamp DESC')])
    
    op.create_index('ix_obs_patient_observed', 'clinical_observations', ['patient_id', sa.text('observed_at DESC')])
    op.create_index('ix_obs_encounter_observed', 'clinical_observations', ['encounter_id', sa.text('observed_at DESC')])
    op.create_index('ix_obs_tenant_patient', 'clinical_observations', ['tenant_id', 'patient_id'])
    op.create_index('ix_obs_type_patient_observed', 'clinical_observations', ['observation_type', 'patient_id', sa.text('observed_at DESC')])
    
    op.create_index('ix_encounters_patient_status', 'encounters', ['patient_id', 'status'])
    op.create_index('ix_beds_dept_status', 'beds', ['department_id', 'status'])
    op.create_index('ix_staff_dept_role_status', 'staff', ['department_id', 'role', 'status'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_staff_dept_role_status', table_name='staff')
    op.drop_index('ix_beds_dept_status', table_name='beds')
    op.drop_index('ix_encounters_patient_status', table_name='encounters')
    op.drop_index('ix_obs_type_patient_observed', table_name='clinical_observations')
    op.drop_index('ix_obs_tenant_patient', table_name='clinical_observations')
    op.drop_index('ix_obs_encounter_observed', table_name='clinical_observations')
    op.drop_index('ix_obs_patient_observed', table_name='clinical_observations')
    op.drop_index('ix_audit_log_tenant_timestamp', table_name='audit_log')
    op.drop_index('ix_emergency_events_tenant_id', table_name='emergency_events')
    op.drop_index('ix_staff_tenant_id', table_name='staff')
    op.drop_index('ix_departments_tenant_id', table_name='departments')
    op.drop_index('ix_patients_tenant_id', table_name='patients')
    
    # Drop clinical_observations table
    op.drop_table('clinical_observations')

    # Drop tenant_id columns
    for table_name in ['audit_log', 'emergency_events', 'patients', 'staff', 'departments']:
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.drop_column('tenant_id')

    # Drop tenants table
    op.drop_index('ix_tenants_code', table_name='tenants')
    op.drop_table('tenants')
