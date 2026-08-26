-- ============================================================================
-- 02_seed_infrastructure.sql
-- Core Hospital Infrastructure: Departments, Beds, Equipment
-- Target Engine: PostgreSQL 15+ / ACID Relational SQL
-- ============================================================================

-- 1. DEPARTMENTS (9 Facilities)
INSERT INTO departments (id, name, code, total_beds, current_occupancy, min_doctors, min_nurses, nurse_patient_ratio, created_at) VALUES
('DEP-ER', 'Emergency Department', 'ER', 6, 0, 2, 3, '1:3', CURRENT_TIMESTAMP),
('DEP-ICU', 'Intensive Care Unit', 'ICU', 8, 0, 2, 4, '1:2', CURRENT_TIMESTAMP),
('DEP-WA', 'General Ward A', 'WA', 10, 0, 1, 2, '1:5', CURRENT_TIMESTAMP),
('DEP-WB', 'General Ward B', 'WB', 10, 0, 1, 2, '1:5', CURRENT_TIMESTAMP),
('DEP-CAR', 'Cardiology Department', 'CAR', 6, 0, 1, 2, '1:3', CURRENT_TIMESTAMP),
('DEP-ISO', 'Isolation Unit', 'ISO', 4, 0, 1, 2, '1:2', CURRENT_TIMESTAMP),
('DEP-RAD', 'Radiology Department', 'RAD', 0, 0, 1, 1, '1:5', CURRENT_TIMESTAMP),
('DEP-LAB', 'Laboratory Department', 'LAB', 0, 0, 0, 0, '1:5', CURRENT_TIMESTAMP),
('DEP-SUR', 'Surgery Department', 'SUR', 0, 0, 2, 2, '1:2', CURRENT_TIMESTAMP)
ON CONFLICT (id) DO NOTHING;

-- 2. BEDS (44 Total Beds across 6 Inpatient Units)
INSERT INTO beds (id, department_id, bed_type, status, has_ventilator, has_telemetry, is_isolation) VALUES
-- ICU Beds (8)
('BED-ICU-01', 'DEP-ICU', 'ICU', 'AVAILABLE', true, true, false),
('BED-ICU-02', 'DEP-ICU', 'ICU', 'AVAILABLE', true, true, false),
('BED-ICU-03', 'DEP-ICU', 'ICU', 'AVAILABLE', true, true, false),
('BED-ICU-04', 'DEP-ICU', 'ICU', 'AVAILABLE', true, true, false),
('BED-ICU-05', 'DEP-ICU', 'ICU', 'AVAILABLE', true, true, false),
('BED-ICU-06', 'DEP-ICU', 'ICU', 'AVAILABLE', true, true, false),
('BED-ICU-07', 'DEP-ICU', 'ICU', 'AVAILABLE', true, true, false),
('BED-ICU-08', 'DEP-ICU', 'ICU', 'AVAILABLE', true, true, true),
-- Emergency Beds (6)
('BED-ER-01', 'DEP-ER', 'EMERGENCY', 'AVAILABLE', false, true, false),
('BED-ER-02', 'DEP-ER', 'EMERGENCY', 'AVAILABLE', false, true, false),
('BED-ER-03', 'DEP-ER', 'EMERGENCY', 'AVAILABLE', false, true, false),
('BED-ER-04', 'DEP-ER', 'EMERGENCY', 'AVAILABLE', false, true, false),
('BED-ER-05', 'DEP-ER', 'EMERGENCY', 'AVAILABLE', false, true, false),
('BED-ER-06', 'DEP-ER', 'EMERGENCY', 'AVAILABLE', false, true, false),
-- Ward A Beds (10)
('BED-WA-01', 'DEP-WA', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WA-02', 'DEP-WA', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WA-03', 'DEP-WA', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WA-04', 'DEP-WA', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WA-05', 'DEP-WA', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WA-06', 'DEP-WA', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WA-07', 'DEP-WA', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WA-08', 'DEP-WA', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WA-09', 'DEP-WA', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WA-10', 'DEP-WA', 'GENERAL', 'AVAILABLE', false, false, false),
-- Ward B Beds (10)
('BED-WB-01', 'DEP-WB', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WB-02', 'DEP-WB', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WB-03', 'DEP-WB', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WB-04', 'DEP-WB', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WB-05', 'DEP-WB', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WB-06', 'DEP-WB', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WB-07', 'DEP-WB', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WB-08', 'DEP-WB', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WB-09', 'DEP-WB', 'GENERAL', 'AVAILABLE', false, false, false),
('BED-WB-10', 'DEP-WB', 'GENERAL', 'AVAILABLE', false, false, false),
-- Cardiology Beds (6)
('BED-CAR-01', 'DEP-CAR', 'CARDIAC_MONITOR', 'AVAILABLE', false, true, false),
('BED-CAR-02', 'DEP-CAR', 'CARDIAC_MONITOR', 'AVAILABLE', false, true, false),
('BED-CAR-03', 'DEP-CAR', 'CARDIAC_MONITOR', 'AVAILABLE', false, true, false),
('BED-CAR-04', 'DEP-CAR', 'CARDIAC_MONITOR', 'AVAILABLE', false, true, false),
('BED-CAR-05', 'DEP-CAR', 'CARDIAC_MONITOR', 'AVAILABLE', false, true, false),
('BED-CAR-06', 'DEP-CAR', 'CARDIAC_MONITOR', 'AVAILABLE', false, true, false),
-- Isolation Beds (4)
('BED-ISO-01', 'DEP-ISO', 'ISOLATION', 'AVAILABLE', false, false, true),
('BED-ISO-02', 'DEP-ISO', 'ISOLATION', 'AVAILABLE', false, false, true),
('BED-ISO-03', 'DEP-ISO', 'ISOLATION', 'AVAILABLE', false, false, true),
('BED-ISO-04', 'DEP-ISO', 'ISOLATION', 'AVAILABLE', false, false, true)
ON CONFLICT (id) DO NOTHING;

-- 3. CRITICAL EQUIPMENT & RESOURCES (15 Units)
INSERT INTO equipment (id, name, resource_type, department_id, status, slot_duration_mins, created_at) VALUES
('RES-CT-01', 'Siemens Somatom CT Scanner 1', 'CT_SCANNER', 'DEP-RAD', 'AVAILABLE', 30, CURRENT_TIMESTAMP),
('RES-CT-02', 'GE Revolution CT Scanner 2', 'CT_SCANNER', 'DEP-RAD', 'AVAILABLE', 30, CURRENT_TIMESTAMP),
('RES-MRI-01', 'Philips Ingenia 3T MRI', 'MRI', 'DEP-RAD', 'AVAILABLE', 45, CURRENT_TIMESTAMP),
('RES-XRAY-01', 'Digital X-Ray Suite 1', 'XRAY', 'DEP-RAD', 'AVAILABLE', 15, CURRENT_TIMESTAMP),
('RES-XRAY-02', 'Portable X-Ray Suite 2', 'XRAY', 'DEP-RAD', 'AVAILABLE', 15, CURRENT_TIMESTAMP),
('RES-US-01', 'Ultrasound Diagnostic System', 'ULTRASOUND', 'DEP-RAD', 'AVAILABLE', 20, CURRENT_TIMESTAMP),
('RES-VENT-01', 'ICU Ventilator 1', 'VENTILATOR', 'DEP-ICU', 'AVAILABLE', 60, CURRENT_TIMESTAMP),
('RES-VENT-02', 'ICU Ventilator 2', 'VENTILATOR', 'DEP-ICU', 'AVAILABLE', 60, CURRENT_TIMESTAMP),
('RES-VENT-03', 'ER Emergency Ventilator 3', 'VENTILATOR', 'DEP-ER', 'AVAILABLE', 60, CURRENT_TIMESTAMP),
('RES-ECG-01', '12-Lead ECG Machine 1', 'ECG_MACHINE', 'DEP-CAR', 'AVAILABLE', 15, CURRENT_TIMESTAMP),
('RES-ECG-02', 'Portable ECG Machine 2', 'ECG_MACHINE', 'DEP-ER', 'AVAILABLE', 15, CURRENT_TIMESTAMP),
('RES-LAB-01', 'Roche Cobas Hematology Analyzer', 'LAB_ANALYZER', 'DEP-LAB', 'AVAILABLE', 20, CURRENT_TIMESTAMP),
('RES-LAB-02', 'Abbott Biochemistry Analyzer', 'LAB_ANALYZER', 'DEP-LAB', 'AVAILABLE', 20, CURRENT_TIMESTAMP),
('RES-OT-01', 'Major Surgical Operating Theatre 1', 'OPERATING_THEATRE', 'DEP-SUR', 'AVAILABLE', 120, CURRENT_TIMESTAMP),
('RES-OT-02', 'Laparoscopic Operating Theatre 2', 'OPERATING_THEATRE', 'DEP-SUR', 'AVAILABLE', 120, CURRENT_TIMESTAMP)
ON CONFLICT (id) DO NOTHING;
