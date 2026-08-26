-- ============================================================================
-- MULTI-AGENT HOSPITAL MANAGEMENT SYSTEM - INDEXES & ANALYTIC VIEWS
-- Optimizes high-throughput clinical queries and real-time dashboard state
-- ============================================================================

-- 1. PERFORMANCE B-TREE INDEXES
CREATE INDEX IF NOT EXISTS idx_encounters_patient_id ON encounters(patient_id);
CREATE INDEX IF NOT EXISTS idx_encounters_status_dept ON encounters(status, current_department_id);
CREATE INDEX IF NOT EXISTS idx_encounters_esi_score ON encounters(esi_score);
CREATE INDEX IF NOT EXISTS idx_beds_dept_status ON beds(department_id, status);
CREATE INDEX IF NOT EXISTS idx_beds_isolation ON beds(is_isolation_capable, status);
CREATE INDEX IF NOT EXISTS idx_staff_dept_role_status ON staff(department_id, role, status);
CREATE INDEX IF NOT EXISTS idx_equipment_dept_status ON equipment(department_id, status);
CREATE INDEX IF NOT EXISTS idx_approval_items_status ON approval_items(status);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp DESC);

-- 2. LIVE DASHBOARD CAPACITY VIEW
CREATE OR REPLACE VIEW v_hospital_live_capacity AS
SELECT
    d.id AS department_id,
    d.name AS department_name,
    d.code AS department_code,
    COUNT(b.id) AS total_beds,
    SUM(CASE WHEN b.status = 'AVAILABLE' THEN 1 ELSE 0 END) AS available_beds,
    SUM(CASE WHEN b.status = 'OCCUPIED' THEN 1 ELSE 0 END) AS occupied_beds,
    SUM(CASE WHEN b.status = 'RESERVED' THEN 1 ELSE 0 END) AS reserved_beds,
    SUM(CASE WHEN b.status = 'CLEANING' THEN 1 ELSE 0 END) AS cleaning_beds,
    ROUND(
        (SUM(CASE WHEN b.status IN ('OCCUPIED', 'RESERVED') THEN 1 ELSE 0 END)::NUMERIC / 
        NULLIF(COUNT(b.id), 0)::NUMERIC) * 100, 1
    ) AS utilization_percentage
FROM departments d
LEFT JOIN beds b ON d.id = b.department_id
GROUP BY d.id, d.name, d.code
ORDER BY d.id;

-- 3. STAFFING RATIOS & COMPLIANCE VIEW
CREATE OR REPLACE VIEW v_staffing_ratios AS
SELECT
    d.id AS department_id,
    d.name AS department_name,
    COUNT(DISTINCT CASE WHEN s.role = 'DOCTOR' AND s.status IN ('AVAILABLE', 'BUSY') THEN s.id END) AS active_doctors,
    COUNT(DISTINCT CASE WHEN s.role IN ('NURSE', 'CHARGE_NURSE') AND s.status IN ('AVAILABLE', 'BUSY') THEN s.id END) AS active_nurses,
    d.min_doctors,
    d.min_nurses,
    CASE 
        WHEN COUNT(DISTINCT CASE WHEN s.role = 'DOCTOR' AND s.status IN ('AVAILABLE', 'BUSY') THEN s.id END) >= d.min_doctors
         AND COUNT(DISTINCT CASE WHEN s.role IN ('NURSE', 'CHARGE_NURSE') AND s.status IN ('AVAILABLE', 'BUSY') THEN s.id END) >= d.min_nurses
        THEN TRUE ELSE FALSE 
    END AS is_staffing_adequate
FROM departments d
LEFT JOIN staff s ON d.id = s.department_id
GROUP BY d.id, d.name, d.min_doctors, d.min_nurses;

-- 4. PENDING HUMAN-IN-THE-LOOP APPROVALS VIEW
CREATE OR REPLACE VIEW v_pending_approvals AS
SELECT
    a.id AS approval_id,
    a.decision_id,
    a.agent_id,
    a.recommendation_type,
    a.risk_level,
    a.patient_id,
    a.encounter_id,
    a.proposed_payload,
    a.created_at,
    e.chief_complaint,
    e.esi_score
FROM approval_items a
LEFT JOIN encounters e ON a.encounter_id = e.id
WHERE a.status = 'PENDING'
ORDER BY a.created_at ASC;
