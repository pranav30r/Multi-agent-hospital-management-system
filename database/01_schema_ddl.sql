-- ============================================================================
-- MULTI-AGENT HOSPITAL MANAGEMENT SYSTEM - DATABASE SCHEMA DDL
-- Target Engine: PostgreSQL 15+ / ACID-Compliant Relational SQL
-- Architecture: Multi-Agent Clinical Workflow & Resource Optimization
-- ============================================================================

-- Enable UUID extension if using native UUIDs (optional fallback)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 1. DEPARTMENTS & INFRASTRUCTURE
-- ============================================================================

CREATE TABLE IF NOT EXISTS departments (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    code VARCHAR(16) NOT NULL UNIQUE,
    floor_number INTEGER DEFAULT 1,
    min_doctors INTEGER DEFAULT 1,
    min_nurses INTEGER DEFAULT 2,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS beds (
    id VARCHAR(32) PRIMARY KEY,
    department_id VARCHAR(32) NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    bed_number VARCHAR(16) NOT NULL,
    bed_type VARCHAR(32) NOT NULL, -- ICU, GENERAL, ER, ISOLATION, CARDIAC, STEPDOWN
    status VARCHAR(32) NOT NULL DEFAULT 'AVAILABLE', -- AVAILABLE, RESERVED, OCCUPIED, CLEANING, MAINTENANCE, BLOCKED
    is_isolation_capable BOOLEAN DEFAULT FALSE,
    current_patient_id VARCHAR(32),
    current_encounter_id VARCHAR(32),
    reserved_at TIMESTAMP WITH TIME ZONE,
    occupied_at TIMESTAMP WITH TIME ZONE,
    last_cleaned_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 2. PATIENTS & ENCOUNTERS
-- ============================================================================

CREATE TABLE IF NOT EXISTS patients (
    id VARCHAR(32) PRIMARY KEY,
    first_name VARCHAR(64) NOT NULL,
    last_name VARCHAR(64) NOT NULL,
    date_of_birth DATE NOT NULL,
    gender VARCHAR(16) NOT NULL,
    contact_number VARCHAR(32),
    emergency_contact VARCHAR(128),
    blood_group VARCHAR(8),
    allergies JSONB DEFAULT '[]'::jsonb,
    chronic_conditions JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS encounters (
    id VARCHAR(32) PRIMARY KEY,
    patient_id VARCHAR(32) NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    admission_type VARCHAR(32) NOT NULL, -- EMERGENCY, ELECTIVE, OUTPATIENT, TRANSFER
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, DISCHARGED, TRANSFERRED, DECEASED
    current_department_id VARCHAR(32) NOT NULL REFERENCES departments(id),
    current_bed_id VARCHAR(32) REFERENCES beds(id),
    patient_status VARCHAR(32) NOT NULL DEFAULT 'ARRIVED', -- ARRIVED, REGISTERED, TRIAGED, WAITING_FOR_DOCTOR, IN_TREATMENT, ADMITTED, READY_FOR_DISCHARGE, DISCHARGED
    chief_complaint TEXT NOT NULL,
    initial_vitals JSONB DEFAULT '{}'::jsonb,
    latest_vitals JSONB DEFAULT '{}'::jsonb,
    presenting_symptoms JSONB DEFAULT '[]'::jsonb,
    esi_score INTEGER, -- Emergency Severity Index: 1 (Resuscitation) to 5 (Non-urgent)
    triage_notes TEXT,
    assigned_doctor_id VARCHAR(32),
    assigned_nurse_id VARCHAR(32),
    admitted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    discharged_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS bed_assignments (
    id VARCHAR(32) PRIMARY KEY,
    bed_id VARCHAR(32) NOT NULL REFERENCES beds(id),
    encounter_id VARCHAR(32) NOT NULL REFERENCES encounters(id),
    patient_id VARCHAR(32) NOT NULL REFERENCES patients(id),
    status VARCHAR(32) NOT NULL DEFAULT 'RESERVED', -- RESERVED, OCCUPIED, COMPLETED, CANCELLED
    assigned_by VARCHAR(64) NOT NULL, -- AI Agent ID or Staff ID
    reserved_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    occupied_at TIMESTAMP WITH TIME ZONE,
    released_at TIMESTAMP WITH TIME ZONE,
    release_reason VARCHAR(128)
);

-- ============================================================================
-- 3. WORKFORCE & STAFF MANAGEMENT
-- ============================================================================

CREATE TABLE IF NOT EXISTS staff (
    id VARCHAR(32) PRIMARY KEY,
    first_name VARCHAR(64) NOT NULL,
    last_name VARCHAR(64) NOT NULL,
    role VARCHAR(32) NOT NULL, -- DOCTOR, NURSE, CHARGE_NURSE, TECHNICIAN, RECEPTIONIST, ADMINISTRATOR
    department_id VARCHAR(32) NOT NULL REFERENCES departments(id),
    specialization VARCHAR(64),
    status VARCHAR(32) NOT NULL DEFAULT 'AVAILABLE', -- AVAILABLE, BUSY, ON_BREAK, OFF_SHIFT
    current_workload INTEGER DEFAULT 0,
    max_workload INTEGER DEFAULT 5,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staff_shifts (
    id VARCHAR(32) PRIMARY KEY,
    staff_id VARCHAR(32) NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
    department_id VARCHAR(32) NOT NULL REFERENCES departments(id),
    shift_type VARCHAR(16) NOT NULL, -- MORNING, EVENING, NIGHT
    start_time VARCHAR(8) NOT NULL,
    end_time VARCHAR(8) NOT NULL,
    status VARCHAR(16) DEFAULT 'SCHEDULED',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staff_skills (
    id VARCHAR(32) PRIMARY KEY,
    staff_id VARCHAR(32) NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
    skill_name VARCHAR(64) NOT NULL,
    certification_date TIMESTAMP WITH TIME ZONE
);

-- ============================================================================
-- 4. EQUIPMENT & DIAGNOSTIC RESOURCES
-- ============================================================================

CREATE TABLE IF NOT EXISTS equipment (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    resource_type VARCHAR(64) NOT NULL, -- CT_SCANNER, MRI, XRAY, ULTRASOUND, VENTILATOR, ECG_MACHINE, LAB_ANALYZER, OPERATING_THEATRE
    department_id VARCHAR(32) NOT NULL REFERENCES departments(id),
    status VARCHAR(32) NOT NULL DEFAULT 'AVAILABLE', -- AVAILABLE, IN_USE, RESERVED, MAINTENANCE, OUT_OF_SERVICE
    slot_duration_mins INTEGER DEFAULT 30,
    current_patient_id VARCHAR(32),
    current_encounter_id VARCHAR(32),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS equipment_bookings (
    id VARCHAR(32) PRIMARY KEY,
    equipment_id VARCHAR(32) NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,
    encounter_id VARCHAR(32) NOT NULL REFERENCES encounters(id),
    patient_id VARCHAR(32) NOT NULL REFERENCES patients(id),
    requested_by VARCHAR(64) NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP WITH TIME ZONE,
    status VARCHAR(32) NOT NULL DEFAULT 'IN_PROGRESS', -- SCHEDULED, IN_PROGRESS, COMPLETED, CANCELLED
    notes TEXT
);

-- ============================================================================
-- 5. DISEASE CATALOG & CLINICAL CONTEXT
-- ============================================================================

CREATE TABLE IF NOT EXISTS diseases (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    icd_code VARCHAR(16) NOT NULL UNIQUE,
    category VARCHAR(64) NOT NULL,
    is_communicable BOOLEAN DEFAULT FALSE,
    requires_isolation BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 6. CLINICAL WORKFLOWS & QUEUES
-- ============================================================================

CREATE TABLE IF NOT EXISTS workflow_definitions (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    category VARCHAR(32) NOT NULL, -- EMERGENCY, OPD, TRANSFER
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workflow_instances (
    id VARCHAR(32) PRIMARY KEY,
    workflow_definition_id VARCHAR(32) NOT NULL REFERENCES workflow_definitions(id),
    encounter_id VARCHAR(32) NOT NULL REFERENCES encounters(id),
    patient_id VARCHAR(32) NOT NULL REFERENCES patients(id),
    current_step_number INTEGER DEFAULT 1,
    current_step_name VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'IN_PROGRESS', -- IN_PROGRESS, COMPLETED, CANCELLED
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    sla_breached BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS workflow_steps (
    id VARCHAR(32) PRIMARY KEY,
    instance_id VARCHAR(32) NOT NULL REFERENCES workflow_instances(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    step_name VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'IN_PROGRESS', -- PENDING, IN_PROGRESS, COMPLETED, SKIPPED
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    performed_by_id VARCHAR(64)
);

CREATE TABLE IF NOT EXISTS queues (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    department_id VARCHAR(32) NOT NULL REFERENCES departments(id),
    current_depth INTEGER DEFAULT 0,
    average_wait_time_minutes FLOAT DEFAULT 0.0,
    max_capacity INTEGER DEFAULT 50,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(32) PRIMARY KEY,
    encounter_id VARCHAR(32) NOT NULL REFERENCES encounters(id),
    task_type VARCHAR(64) NOT NULL,
    description TEXT NOT NULL,
    assigned_to_id VARCHAR(32),
    priority INTEGER DEFAULT 3,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    due_time TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admissions (
    id VARCHAR(32) PRIMARY KEY,
    encounter_id VARCHAR(32) NOT NULL REFERENCES encounters(id),
    patient_id VARCHAR(32) NOT NULL REFERENCES patients(id),
    department_id VARCHAR(32) NOT NULL REFERENCES departments(id),
    bed_id VARCHAR(32) NOT NULL REFERENCES beds(id),
    admitted_by VARCHAR(64) NOT NULL,
    admission_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transfers (
    id VARCHAR(32) PRIMARY KEY,
    encounter_id VARCHAR(32) NOT NULL REFERENCES encounters(id),
    from_department_id VARCHAR(32) NOT NULL,
    to_department_id VARCHAR(32) NOT NULL,
    from_bed_id VARCHAR(32),
    to_bed_id VARCHAR(32),
    status VARCHAR(32) NOT NULL DEFAULT 'REQUESTED',
    requested_by VARCHAR(64) NOT NULL,
    reason TEXT NOT NULL,
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS discharges (
    id VARCHAR(32) PRIMARY KEY,
    encounter_id VARCHAR(32) NOT NULL REFERENCES encounters(id),
    patient_id VARCHAR(32) NOT NULL REFERENCES patients(id),
    discharged_by VARCHAR(64) NOT NULL,
    discharge_summary TEXT,
    discharge_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 7. EMERGENCY SURGE & PREDICTIVE ANALYTICS
-- ============================================================================

CREATE TABLE IF NOT EXISTS emergency_events (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    emergency_type VARCHAR(32) NOT NULL, -- MASS_CASUALTY, EPIDEMIC, CODE_BLUE, NATURAL_DISASTER
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, CONTAINED, RESOLVED
    severity_level INTEGER DEFAULT 5,
    declared_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE,
    declared_by VARCHAR(64) NOT NULL,
    affected_departments JSONB DEFAULT '[]'::jsonb,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS prediction_runs (
    id VARCHAR(32) PRIMARY KEY,
    model_name VARCHAR(64) NOT NULL,
    model_version VARCHAR(16) NOT NULL,
    prediction_type VARCHAR(32) NOT NULL, -- SURGE_FORECAST, ICU_BED_DEMAND, LENGTH_OF_STAY
    input_features JSONB DEFAULT '{}'::jsonb,
    prediction_output JSONB DEFAULT '{}'::jsonb,
    confidence_score FLOAT NOT NULL,
    inference_time_ms FLOAT NOT NULL,
    target_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 8. MULTI-AGENT GOVERNANCE, APPROVAL QUEUE & AUDIT TRAIL
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_decisions (
    id VARCHAR(32) PRIMARY KEY,
    agent_id VARCHAR(64) NOT NULL, -- TriageAgent, BedAgent, StaffAgent, WorkflowAgent, SurgeAgent, Coordinator
    decision_type VARCHAR(64) NOT NULL,
    patient_id VARCHAR(32),
    encounter_id VARCHAR(32),
    risk_level VARCHAR(16) NOT NULL, -- LOW, MEDIUM, HIGH, CRITICAL
    requires_approval BOOLEAN DEFAULT FALSE,
    proposal_payload JSONB DEFAULT '{}'::jsonb,
    rationale TEXT NOT NULL,
    confidence_score FLOAT DEFAULT 1.0,
    status VARCHAR(32) NOT NULL DEFAULT 'PROPOSED', -- PROPOSED, APPROVED, MODIFIED, REJECTED, EXECUTED
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_messages (
    id VARCHAR(32) PRIMARY KEY,
    sender_agent VARCHAR(64) NOT NULL,
    recipient_agent VARCHAR(64) NOT NULL,
    message_type VARCHAR(64) NOT NULL,
    payload JSONB DEFAULT '{}'::jsonb,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS optimization_runs (
    id VARCHAR(32) PRIMARY KEY,
    objective VARCHAR(64) NOT NULL,
    solver_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED',
    score FLOAT,
    solution_payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crew_runs (
    id VARCHAR(32) PRIMARY KEY,
    crew_name VARCHAR(64) NOT NULL,
    tasks_count INTEGER DEFAULT 1,
    status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED',
    output_summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS langgraph_checkpoints (
    id VARCHAR(32) PRIMARY KEY,
    thread_id VARCHAR(64) NOT NULL,
    step_number INTEGER NOT NULL,
    state_payload JSONB DEFAULT '{}'::jsonb,
    checkpoint_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS approval_items (
    id VARCHAR(32) PRIMARY KEY,
    decision_id VARCHAR(32) NOT NULL REFERENCES agent_decisions(id),
    agent_id VARCHAR(64) NOT NULL,
    recommendation_type VARCHAR(64) NOT NULL,
    patient_id VARCHAR(32),
    encounter_id VARCHAR(32),
    risk_level VARCHAR(16) NOT NULL,
    proposed_payload JSONB DEFAULT '{}'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING', -- PENDING, APPROVED, MODIFIED, REJECTED
    human_notes TEXT,
    reviewed_by VARCHAR(64),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id VARCHAR(32) PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    entity_type VARCHAR(64) NOT NULL,
    entity_id VARCHAR(64) NOT NULL,
    field_changed VARCHAR(64) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_by VARCHAR(64) NOT NULL,
    change_reason TEXT NOT NULL,
    decision_id VARCHAR(32),
    approval_id VARCHAR(32)
);
