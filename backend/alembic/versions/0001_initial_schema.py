"""Initial baseline schema migration (35 explicit tables)

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-08-27 19:50:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Table: patients
    op.create_table(
        'patients',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('first_name', sa.String(length=50), nullable=False),
        sa.Column('last_name', sa.String(length=50), nullable=False),
        sa.Column('age', sa.Integer(), nullable=False),
        sa.Column('gender', sa.String(length=10), nullable=False),
        sa.Column('blood_group', sa.String(length=5), nullable=False),
        sa.Column('contact_phone', sa.String(length=20), nullable=False),
        sa.Column('emergency_contact', sa.String(length=20), nullable=False),
        sa.Column('allergies', sa.JSON(), nullable=True),
        sa.Column('chronic_conditions', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # Table: departments
    op.create_table(
        'departments',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('code', sa.String(length=10), nullable=False),
        sa.Column('description', sa.String(length=200), nullable=True),
        sa.Column('total_beds', sa.Integer(), nullable=False),
        sa.Column('current_occupancy', sa.Integer(), nullable=False),
        sa.Column('min_doctors', sa.Integer(), nullable=False),
        sa.Column('min_nurses', sa.Integer(), nullable=False),
        sa.Column('nurse_patient_ratio', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # Table: diseases
    op.create_table(
        'diseases',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('icd_code', sa.String(length=20), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('is_communicable', sa.Boolean(), nullable=False),
        sa.Column('requires_isolation', sa.Boolean(), nullable=False),
        sa.Column('added_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
    )

    # Table: workflow_definitions
    op.create_table(
        'workflow_definitions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('category', sa.String(length=30), nullable=False),
        sa.Column('steps_json', sa.JSON(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
    )

    # Table: emergency_events
    op.create_table(
        'emergency_events',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('affected_departments', sa.JSON(), nullable=False),
        sa.Column('expected_patient_surge', sa.Integer(), nullable=False),
        sa.Column('declared_by', sa.String(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('declared_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
    )

    # Table: prediction_runs
    op.create_table(
        'prediction_runs',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('model_name', sa.String(length=100), nullable=True),
        sa.Column('model_version', sa.String(length=50), nullable=True),
        sa.Column('prediction_type', sa.String(length=50), nullable=False),
        sa.Column('forecast_horizon_hours', sa.Integer(), nullable=False),
        sa.Column('predicted_value', sa.Float(), nullable=True),
        sa.Column('unit', sa.String(length=30), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=False),
        sa.Column('input_features', sa.JSON(), nullable=True),
        sa.Column('prediction_output', sa.JSON(), nullable=True),
        sa.Column('recommended_action', sa.String(length=200), nullable=True),
        sa.Column('inference_time_ms', sa.Float(), nullable=True),
        sa.Column('target_date', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # Table: agent_messages
    op.create_table(
        'agent_messages',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('sender_agent', sa.String(length=50), nullable=False),
        sa.Column('receiver_agent', sa.String(length=50), nullable=False),
        sa.Column('event_id', sa.String(), nullable=True),
        sa.Column('encounter_id', sa.String(), nullable=True),
        sa.Column('message_type', sa.String(length=20), nullable=False),
        sa.Column('subject', sa.String(length=100), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('response_id', sa.String(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
    )

    # Table: optimization_runs
    op.create_table(
        'optimization_runs',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('trigger_event_id', sa.String(), nullable=True),
        sa.Column('trigger_type', sa.String(length=50), nullable=False),
        sa.Column('encounter_id', sa.String(), nullable=True),
        sa.Column('agents_involved', sa.JSON(), nullable=False),
        sa.Column('candidates_count', sa.Integer(), nullable=False),
        sa.Column('candidates', sa.JSON(), nullable=False),
        sa.Column('selected_plan_index', sa.Integer(), nullable=False),
        sa.Column('selected_plan', sa.JSON(), nullable=False),
        sa.Column('objective_score', sa.Float(), nullable=False),
        sa.Column('waiting_time_score', sa.Float(), nullable=False),
        sa.Column('resource_util_score', sa.Float(), nullable=False),
        sa.Column('staff_balance_score', sa.Float(), nullable=False),
        sa.Column('constraint_violations', sa.Integer(), nullable=False),
        sa.Column('hard_constraint_pass', sa.Boolean(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=False),
        sa.Column('computation_time_ms', sa.Integer(), nullable=False),
    )

    # Table: crew_runs
    op.create_table(
        'crew_runs',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('crew_name', sa.String(length=50), nullable=False),
        sa.Column('trigger_event', sa.String(length=50), nullable=False),
        sa.Column('agents_count', sa.Integer(), nullable=False),
        sa.Column('tasks_count', sa.Integer(), nullable=False),
        sa.Column('output_summary', sa.String(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # Table: langgraph_checkpoints
    op.create_table(
        'langgraph_checkpoints',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('thread_id', sa.String(), nullable=False),
        sa.Column('node_name', sa.String(length=50), nullable=False),
        sa.Column('state_snapshot', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # Table: audit_log
    op.create_table(
        'audit_log',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('entity_type', sa.String(length=30), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('field_changed', sa.String(length=50), nullable=False),
        sa.Column('old_value', sa.String(), nullable=True),
        sa.Column('new_value', sa.String(), nullable=True),
        sa.Column('changed_by', sa.String(), nullable=False),
        sa.Column('change_reason', sa.String(length=200), nullable=False),
        sa.Column('decision_id', sa.String(), nullable=True),
        sa.Column('approval_id', sa.String(), nullable=True),
    )

    # Table: encounters
    op.create_table(
        'encounters',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('encounter_type', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('current_department_id', sa.String(), nullable=False),
        sa.Column('current_bed_id', sa.String(), nullable=True),
        sa.Column('assigned_doctor_id', sa.String(), nullable=True),
        sa.Column('assigned_nurse_id', sa.String(), nullable=True),
        sa.Column('esi_level', sa.Integer(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('patient_status', sa.String(length=30), nullable=False),
        sa.Column('chief_complaint', sa.String(), nullable=False),
        sa.Column('heart_rate', sa.Integer(), nullable=True),
        sa.Column('bp_systolic', sa.Integer(), nullable=True),
        sa.Column('bp_diastolic', sa.Integer(), nullable=True),
        sa.Column('spo2', sa.Integer(), nullable=True),
        sa.Column('temperature_f', sa.Float(), nullable=True),
        sa.Column('pain_level', sa.Integer(), nullable=True),
        sa.Column('respiratory_rate', sa.Integer(), nullable=True),
        sa.Column('gcs_score', sa.Integer(), nullable=True),
        sa.Column('diagnosed_diseases', sa.JSON(), nullable=True),
        sa.Column('diagnosis_notes', sa.String(), nullable=True),
        sa.Column('arrival_time', sa.DateTime(), nullable=False),
        sa.Column('registration_time', sa.DateTime(), nullable=True),
        sa.Column('triage_time', sa.DateTime(), nullable=True),
        sa.Column('doctor_assigned_time', sa.DateTime(), nullable=True),
        sa.Column('bed_requested_time', sa.DateTime(), nullable=True),
        sa.Column('bed_reserved_time', sa.DateTime(), nullable=True),
        sa.Column('bed_occupied_time', sa.DateTime(), nullable=True),
        sa.Column('admission_time', sa.DateTime(), nullable=True),
        sa.Column('discharge_initiated_time', sa.DateTime(), nullable=True),
        sa.Column('discharge_time', sa.DateTime(), nullable=True),
    )

    # Table: beds
    op.create_table(
        'beds',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('department_id', sa.String(), sa.ForeignKey('departments.id'), nullable=False),
        sa.Column('bed_type', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('is_isolation', sa.Boolean(), nullable=False),
        sa.Column('has_ventilator', sa.Boolean(), nullable=False),
        sa.Column('has_telemetry', sa.Boolean(), nullable=False),
        sa.Column('current_patient_id', sa.String(), nullable=True),
        sa.Column('current_encounter_id', sa.String(), nullable=True),
        sa.Column('last_cleaned_at', sa.DateTime(), nullable=True),
    )

    # Table: staff
    op.create_table(
        'staff',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('first_name', sa.String(length=50), nullable=False),
        sa.Column('last_name', sa.String(length=50), nullable=False),
        sa.Column('role', sa.String(length=30), nullable=False),
        sa.Column('department_id', sa.String(), sa.ForeignKey('departments.id'), nullable=False),
        sa.Column('specialization', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('current_workload', sa.Integer(), nullable=False),
        sa.Column('max_workload', sa.Integer(), nullable=False),
        sa.Column('skills', sa.JSON(), nullable=True),
        sa.Column('password_hash', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # Table: equipment
    op.create_table(
        'equipment',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('resource_type', sa.String(length=30), nullable=False),
        sa.Column('department_id', sa.String(), sa.ForeignKey('departments.id'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('slot_duration_mins', sa.Integer(), nullable=False),
        sa.Column('current_patient_id', sa.String(), nullable=True),
        sa.Column('current_encounter_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # Table: clinical_intake_sessions
    op.create_table(
        'clinical_intake_sessions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('encounter_id', sa.String(), sa.ForeignKey('encounters.id'), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=False),
        sa.Column('interaction_mode', sa.String(length=20), nullable=False),
        sa.Column('chief_complaint_raw', sa.String(), nullable=True),
        sa.Column('total_questions', sa.Integer(), nullable=False),
        sa.Column('answered_questions', sa.Integer(), nullable=False),
        sa.Column('completion_percentage', sa.Float(), nullable=False),
        sa.Column('structured_summary', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # Table: clinical_documents
    op.create_table(
        'clinical_documents',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('encounter_id', sa.String(), sa.ForeignKey('encounters.id'), nullable=True),
        sa.Column('document_type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('storage_key', sa.String(length=255), nullable=False),
        sa.Column('storage_provider', sa.String(length=50), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=True),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('checksum', sa.String(length=64), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=False),
        sa.Column('verified_by', sa.String(), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('uploaded_by', sa.String(), nullable=False),
        sa.Column('document_date', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # Table: queues
    op.create_table(
        'queues',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('queue_type', sa.String(length=30), nullable=False),
        sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('encounter_id', sa.String(), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('department_id', sa.String(), sa.ForeignKey('departments.id'), nullable=False),
        sa.Column('esi_level', sa.Integer(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('entered_at', sa.DateTime(), nullable=False),
        sa.Column('estimated_wait_mins', sa.Integer(), nullable=False),
    )

    # Table: tasks
    op.create_table(
        'tasks',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('encounter_id', sa.String(), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('title', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('task_type', sa.String(length=30), nullable=False),
        sa.Column('assigned_to_role', sa.String(length=30), nullable=True),
        sa.Column('assigned_to_staff_id', sa.String(), nullable=True),
        sa.Column('created_by_agent', sa.String(length=30), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )

    # Table: transfers
    op.create_table(
        'transfers',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('encounter_id', sa.String(), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('from_department_id', sa.String(), nullable=False),
        sa.Column('to_department_id', sa.String(), nullable=False),
        sa.Column('from_bed_id', sa.String(), nullable=True),
        sa.Column('to_bed_id', sa.String(), nullable=True),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('transferred_at', sa.DateTime(), nullable=True),
    )

    # Table: discharges
    op.create_table(
        'discharges',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('encounter_id', sa.String(), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('discharging_doctor_id', sa.String(), nullable=False),
        sa.Column('summary_text', sa.String(), nullable=True),
        sa.Column('follow_up_instructions', sa.String(), nullable=True),
        sa.Column('discharged_at', sa.DateTime(), nullable=False),
    )

    # Table: workflow_instances
    op.create_table(
        'workflow_instances',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('definition_id', sa.String(), sa.ForeignKey('workflow_definitions.id'), nullable=False),
        sa.Column('encounter_id', sa.String(), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('current_step_number', sa.Integer(), nullable=False),
        sa.Column('blocked_reason', sa.String(length=200), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )

    # Table: agent_decisions
    op.create_table(
        'agent_decisions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('agent_id', sa.String(length=50), nullable=False),
        sa.Column('event_id', sa.String(), nullable=True),
        sa.Column('encounter_id', sa.String(), sa.ForeignKey('encounters.id'), nullable=True),
        sa.Column('action_type', sa.String(length=50), nullable=False),
        sa.Column('proposed_action', sa.JSON(), nullable=False),
        sa.Column('reasoning', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('alternatives', sa.JSON(), nullable=True),
        sa.Column('risk_level', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
    )

    # Table: bed_assignments
    op.create_table(
        'bed_assignments',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('bed_id', sa.String(), sa.ForeignKey('beds.id'), nullable=False),
        sa.Column('encounter_id', sa.String(), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('assigned_by', sa.String(), nullable=False),
        sa.Column('is_manual_override', sa.Boolean(), nullable=False),
        sa.Column('reserved_at', sa.DateTime(), nullable=False),
        sa.Column('occupied_at', sa.DateTime(), nullable=True),
        sa.Column('released_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
    )

    # Table: staff_shifts
    op.create_table(
        'staff_shifts',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('staff_id', sa.String(), sa.ForeignKey('staff.id'), nullable=False),
        sa.Column('department_id', sa.String(), sa.ForeignKey('departments.id'), nullable=False),
        sa.Column('shift_type', sa.String(length=20), nullable=False),
        sa.Column('start_time', sa.String(length=10), nullable=False),
        sa.Column('end_time', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
    )

    # Table: staff_skills
    op.create_table(
        'staff_skills',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('staff_id', sa.String(), sa.ForeignKey('staff.id'), nullable=False),
        sa.Column('skill_name', sa.String(length=50), nullable=False),
        sa.Column('certification_date', sa.DateTime(), nullable=True),
    )

    # Table: admissions
    op.create_table(
        'admissions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('encounter_id', sa.String(), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('bed_id', sa.String(), sa.ForeignKey('beds.id'), nullable=False),
        sa.Column('department_id', sa.String(), sa.ForeignKey('departments.id'), nullable=False),
        sa.Column('admitting_doctor_id', sa.String(), sa.ForeignKey('staff.id'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('admitted_at', sa.DateTime(), nullable=False),
    )

    # Table: equipment_bookings
    op.create_table(
        'equipment_bookings',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('equipment_id', sa.String(), sa.ForeignKey('equipment.id'), nullable=False),
        sa.Column('encounter_id', sa.String(), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('requested_by', sa.String(), nullable=False),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('notes', sa.String(length=200), nullable=True),
    )

    # Table: intake_questions
    op.create_table(
        'intake_questions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('session_id', sa.String(), sa.ForeignKey('clinical_intake_sessions.id'), nullable=False),
        sa.Column('question_text', sa.String(), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=False),
        sa.Column('is_required', sa.Boolean(), nullable=False),
        sa.Column('response_type', sa.String(length=30), nullable=False),
        sa.Column('allowed_options', sa.JSON(), nullable=True),
        sa.Column('scale_min', sa.Integer(), nullable=True),
        sa.Column('scale_max', sa.Integer(), nullable=True),
        sa.Column('parent_question_id', sa.String(), sa.ForeignKey('intake_questions.id'), nullable=True),
        sa.Column('trigger_condition', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_answered', sa.Boolean(), nullable=False),
        sa.Column('is_skipped', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # Table: clinical_assessments
    op.create_table(
        'clinical_assessments',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('encounter_id', sa.String(), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('intake_session_id', sa.String(), sa.ForeignKey('clinical_intake_sessions.id'), nullable=True),
        sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('requires_priority_attention', sa.Boolean(), nullable=False),
        sa.Column('priority_reason', sa.String(), nullable=True),
        sa.Column('red_flags', sa.JSON(), nullable=True),
        sa.Column('reasons', sa.JSON(), nullable=True),
        sa.Column('supporting_factors', sa.JSON(), nullable=True),
        sa.Column('missing_information', sa.JSON(), nullable=True),
        sa.Column('generated_summary', sa.JSON(), nullable=True),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('generated_by', sa.String(length=50), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=False),
    )

    # Table: clinical_investigations
    op.create_table(
        'clinical_investigations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('encounter_id', sa.String(), sa.ForeignKey('encounters.id'), nullable=True),
        sa.Column('document_id', sa.String(), sa.ForeignKey('clinical_documents.id'), nullable=True),
        sa.Column('investigation_type', sa.String(length=50), nullable=False),
        sa.Column('test_name', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('result_summary', sa.String(), nullable=True),
        sa.Column('result_values', sa.JSON(), nullable=True),
        sa.Column('is_abnormal', sa.Boolean(), nullable=False),
        sa.Column('abnormal_flags', sa.JSON(), nullable=True),
        sa.Column('ordered_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=False),
        sa.Column('verified_by', sa.String(), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('ordered_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # Table: workflow_steps
    op.create_table(
        'workflow_steps',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('workflow_instance_id', sa.String(), sa.ForeignKey('workflow_instances.id'), nullable=False),
        sa.Column('step_number', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('assigned_to', sa.String(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )

    # Table: approval_items
    op.create_table(
        'approval_items',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('decision_id', sa.String(), sa.ForeignKey('agent_decisions.id'), nullable=False),
        sa.Column('agent_id', sa.String(length=50), nullable=False),
        sa.Column('action_type', sa.String(length=50), nullable=False),
        sa.Column('risk_level', sa.String(length=10), nullable=False),
        sa.Column('proposed_action', sa.JSON(), nullable=False),
        sa.Column('reasoning', sa.String(), nullable=False),
        sa.Column('alternatives', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('reviewed_by', sa.String(), nullable=True),
        sa.Column('review_action', sa.String(length=20), nullable=True),
        sa.Column('modification', sa.JSON(), nullable=True),
        sa.Column('rejection_reason', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
    )

    # Table: intake_responses
    op.create_table(
        'intake_responses',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('session_id', sa.String(), sa.ForeignKey('clinical_intake_sessions.id'), nullable=False),
        sa.Column('question_id', sa.String(), sa.ForeignKey('intake_questions.id'), nullable=False),
        sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('raw_response', sa.String(), nullable=False),
        sa.Column('structured_value', sa.JSON(), nullable=True),
        sa.Column('response_type', sa.String(length=30), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
    )

    # Table: clinical_priority_recommendations
    op.create_table(
        'clinical_priority_recommendations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('encounter_id', sa.String(), sa.ForeignKey('encounters.id'), nullable=False),
        sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('assessment_id', sa.String(), sa.ForeignKey('clinical_assessments.id'), nullable=True),
        sa.Column('priority_level', sa.String(length=20), nullable=False),
        sa.Column('route', sa.String(length=50), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('requires_priority_attention', sa.Boolean(), nullable=False),
        sa.Column('reasons', sa.JSON(), nullable=True),
        sa.Column('supporting_factors', sa.JSON(), nullable=True),
        sa.Column('red_flags', sa.JSON(), nullable=True),
        sa.Column('missing_information', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('acknowledged_by', sa.String(), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('acknowledgement_notes', sa.String(), nullable=True),
        sa.Column('overridden_by', sa.String(), nullable=True),
        sa.Column('overridden_at', sa.DateTime(), nullable=True),
        sa.Column('override_priority_level', sa.String(length=20), nullable=True),
        sa.Column('override_route', sa.String(length=50), nullable=True),
        sa.Column('override_reason', sa.String(), nullable=True),
        sa.Column('generated_by', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=False),
    )


def downgrade() -> None:
    # Drop tables in reverse topological dependency order
    op.drop_table('clinical_priority_recommendations')
    op.drop_table('intake_responses')
    op.drop_table('approval_items')
    op.drop_table('workflow_steps')
    op.drop_table('clinical_investigations')
    op.drop_table('clinical_assessments')
    op.drop_table('intake_questions')
    op.drop_table('equipment_bookings')
    op.drop_table('admissions')
    op.drop_table('staff_skills')
    op.drop_table('staff_shifts')
    op.drop_table('bed_assignments')
    op.drop_table('agent_decisions')
    op.drop_table('workflow_instances')
    op.drop_table('discharges')
    op.drop_table('transfers')
    op.drop_table('tasks')
    op.drop_table('queues')
    op.drop_table('clinical_documents')
    op.drop_table('clinical_intake_sessions')
    op.drop_table('equipment')
    op.drop_table('staff')
    op.drop_table('beds')
    op.drop_table('encounters')
    op.drop_table('audit_log')
    op.drop_table('langgraph_checkpoints')
    op.drop_table('crew_runs')
    op.drop_table('optimization_runs')
    op.drop_table('agent_messages')
    op.drop_table('prediction_runs')
    op.drop_table('emergency_events')
    op.drop_table('workflow_definitions')
    op.drop_table('diseases')
    op.drop_table('departments')
    op.drop_table('patients')
