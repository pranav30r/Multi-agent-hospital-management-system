-- ============================================================================
-- 04_seed_workflows.sql
-- Core Clinical & Operational Workflow Definitions
-- Target Engine: PostgreSQL 15+ / ACID Relational SQL
-- ============================================================================

INSERT INTO workflow_definitions (id, name, category, steps_json, is_active) VALUES
(
    'WFD-EMERGENCY-ADMISSION',
    'Emergency Admission Workflow',
    'EMERGENCY',
    '[{"step_number": 1, "name": "Registration", "expected_duration_min": 5, "required": true}, {"step_number": 2, "name": "ESI Triage Assessment", "expected_duration_min": 10, "required": true}, {"step_number": 3, "name": "Doctor Examination", "expected_duration_min": 15, "required": true}, {"step_number": 4, "name": "Diagnostic Investigation", "expected_duration_min": 30, "required": false}, {"step_number": 5, "name": "Bed Allocation & Reservation", "expected_duration_min": 10, "required": true}, {"step_number": 6, "name": "Patient Transport to Bed", "expected_duration_min": 15, "required": true}, {"step_number": 7, "name": "Clinical Handoff", "expected_duration_min": 10, "required": true}, {"step_number": 8, "name": "Inpatient Admission", "expected_duration_min": 10, "required": true}, {"step_number": 9, "name": "Discharge Planning", "expected_duration_min": 15, "required": true}, {"step_number": 10, "name": "Final Discharge", "expected_duration_min": 10, "required": true}]',
    true
),
(
    'WFD-OPD-VISIT',
    'Outpatient (OPD) Visit Workflow',
    'OPD',
    '[{"step_number": 1, "name": "Registration", "expected_duration_min": 5, "required": true}, {"step_number": 2, "name": "ESI Triage Assessment", "expected_duration_min": 10, "required": true}, {"step_number": 3, "name": "Doctor Assignment", "expected_duration_min": 5, "required": true}, {"step_number": 4, "name": "Doctor Examination", "expected_duration_min": 15, "required": true}, {"step_number": 5, "name": "Investigation (Optional)", "expected_duration_min": 20, "required": false}, {"step_number": 6, "name": "Diagnosis & Treatment Plan", "expected_duration_min": 10, "required": true}, {"step_number": 7, "name": "OPD Discharge", "expected_duration_min": 5, "required": true}]',
    true
),
(
    'WFD-TRANSFER',
    'Inter-Department Transfer Workflow',
    'TRANSFER',
    '[{"step_number": 1, "name": "Transfer Request", "expected_duration_min": 5, "required": true}, {"step_number": 2, "name": "Destination Bed Search", "expected_duration_min": 5, "required": true}, {"step_number": 3, "name": "Transfer Approval", "expected_duration_min": 10, "required": true}, {"step_number": 4, "name": "Handoff Preparation", "expected_duration_min": 10, "required": true}, {"step_number": 5, "name": "Physical Transfer", "expected_duration_min": 15, "required": true}, {"step_number": 6, "name": "Receiving Handoff Confirmation", "expected_duration_min": 10, "required": true}]',
    true
)
ON CONFLICT (id) DO NOTHING;
