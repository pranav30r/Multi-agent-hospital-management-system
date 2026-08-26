-- ============================================================================
-- MULTI-AGENT HOSPITAL MANAGEMENT SYSTEM - SYNTHETIC SEED DATA
-- Populates core hospital infrastructure, disease registry, staff, equipment
-- ============================================================================

-- 1. DEPARTMENTS (9 Facilities)
INSERT INTO departments (id, name, code, floor_number, min_doctors, min_nurses) VALUES
('DEP-ER', 'Emergency Department', 'ER', 1, 2, 3),
('DEP-ICU', 'Intensive Care Unit', 'ICU', 2, 2, 4),
('DEP-WA', 'General Ward A', 'WA', 3, 1, 2),
('DEP-WB', 'General Ward B', 'WB', 3, 1, 2),
('DEP-CAR', 'Cardiology Department', 'CAR', 4, 1, 2),
('DEP-ISO', 'Isolation Unit', 'ISO', 1, 1, 2),
('DEP-RAD', 'Radiology Department', 'RAD', 1, 1, 1),
('DEP-LAB', 'Laboratory Department', 'LAB', 1, 0, 0),
('DEP-SUR', 'Surgery Department', 'SUR', 2, 2, 2)
ON CONFLICT (id) DO NOTHING;

-- 2. BEDS (44 Total Beds across 6 Inpatient Wards)
INSERT INTO beds (id, department_id, bed_number, bed_type, status, is_isolation_capable) VALUES
-- Emergency Room (6 Beds)
('BED-ER-01', 'DEP-ER', 'ER-01', 'ER', 'AVAILABLE', false),
('BED-ER-02', 'DEP-ER', 'ER-02', 'ER', 'AVAILABLE', false),
('BED-ER-03', 'DEP-ER', 'ER-03', 'ER', 'AVAILABLE', false),
('BED-ER-04', 'DEP-ER', 'ER-04', 'ER', 'AVAILABLE', false),
('BED-ER-05', 'DEP-ER', 'ER-05', 'ER', 'AVAILABLE', false),
('BED-ER-06', 'DEP-ER', 'ER-06', 'ER', 'AVAILABLE', false),
-- ICU (8 Beds)
('BED-ICU-01', 'DEP-ICU', 'ICU-01', 'ICU', 'AVAILABLE', false),
('BED-ICU-02', 'DEP-ICU', 'ICU-02', 'ICU', 'AVAILABLE', false),
('BED-ICU-03', 'DEP-ICU', 'ICU-03', 'ICU', 'AVAILABLE', false),
('BED-ICU-04', 'DEP-ICU', 'ICU-04', 'ICU', 'AVAILABLE', false),
('BED-ICU-05', 'DEP-ICU', 'ICU-05', 'ICU', 'AVAILABLE', false),
('BED-ICU-06', 'DEP-ICU', 'ICU-06', 'ICU', 'AVAILABLE', false),
('BED-ICU-07', 'DEP-ICU', 'ICU-07', 'ICU', 'AVAILABLE', false),
('BED-ICU-08', 'DEP-ICU', 'ICU-08', 'ICU', 'AVAILABLE', true),
-- General Ward A (10 Beds)
('BED-WA-01', 'DEP-WA', 'WA-01', 'GENERAL', 'AVAILABLE', false),
('BED-WA-02', 'DEP-WA', 'WA-02', 'GENERAL', 'AVAILABLE', false),
('BED-WA-03', 'DEP-WA', 'WA-03', 'GENERAL', 'AVAILABLE', false),
('BED-WA-04', 'DEP-WA', 'WA-04', 'GENERAL', 'AVAILABLE', false),
('BED-WA-05', 'DEP-WA', 'WA-05', 'GENERAL', 'AVAILABLE', false),
('BED-WA-06', 'DEP-WA', 'WA-06', 'GENERAL', 'AVAILABLE', false),
('BED-WA-07', 'DEP-WA', 'WA-07', 'GENERAL', 'AVAILABLE', false),
('BED-WA-08', 'DEP-WA', 'WA-08', 'GENERAL', 'AVAILABLE', false),
('BED-WA-09', 'DEP-WA', 'WA-09', 'GENERAL', 'AVAILABLE', false),
('BED-WA-10', 'DEP-WA', 'WA-10', 'GENERAL', 'AVAILABLE', false),
-- General Ward B (10 Beds)
('BED-WB-01', 'DEP-WB', 'WB-01', 'GENERAL', 'AVAILABLE', false),
('BED-WB-02', 'DEP-WB', 'WB-02', 'GENERAL', 'AVAILABLE', false),
('BED-WB-03', 'DEP-WB', 'WB-03', 'GENERAL', 'AVAILABLE', false),
('BED-WB-04', 'DEP-WB', 'WB-04', 'GENERAL', 'AVAILABLE', false),
('BED-WB-05', 'DEP-WB', 'WB-05', 'GENERAL', 'AVAILABLE', false),
('BED-WB-06', 'DEP-WB', 'WB-06', 'GENERAL', 'AVAILABLE', false),
('BED-WB-07', 'DEP-WB', 'WB-07', 'GENERAL', 'AVAILABLE', false),
('BED-WB-08', 'DEP-WB', 'WB-08', 'GENERAL', 'AVAILABLE', false),
('BED-WB-09', 'DEP-WB', 'WB-09', 'GENERAL', 'AVAILABLE', false),
('BED-WB-10', 'DEP-WB', 'WB-10', 'GENERAL', 'AVAILABLE', false),
-- Cardiology (6 Beds)
('BED-CAR-01', 'DEP-CAR', 'CAR-01', 'CARDIAC', 'AVAILABLE', false),
('BED-CAR-02', 'DEP-CAR', 'CAR-02', 'CARDIAC', 'AVAILABLE', false),
('BED-CAR-03', 'DEP-CAR', 'CAR-03', 'CARDIAC', 'AVAILABLE', false),
('BED-CAR-04', 'DEP-CAR', 'CAR-04', 'CARDIAC', 'AVAILABLE', false),
('BED-CAR-05', 'DEP-CAR', 'CAR-05', 'CARDIAC', 'AVAILABLE', false),
('BED-CAR-06', 'DEP-CAR', 'CAR-06', 'CARDIAC', 'AVAILABLE', false),
-- Isolation Unit (4 Beds)
('BED-ISO-01', 'DEP-ISO', 'ISO-01', 'ISOLATION', 'AVAILABLE', true),
('BED-ISO-02', 'DEP-ISO', 'ISO-02', 'ISOLATION', 'AVAILABLE', true),
('BED-ISO-03', 'DEP-ISO', 'ISO-03', 'ISOLATION', 'AVAILABLE', true),
('BED-ISO-04', 'DEP-ISO', 'ISO-04', 'ISOLATION', 'AVAILABLE', true)
ON CONFLICT (id) DO NOTHING;

-- 3. CRITICAL EQUIPMENT & RESOURCES (15 Units)
INSERT INTO equipment (id, name, resource_type, department_id, status, slot_duration_mins) VALUES
('RES-CT-01', 'Siemens Somatom CT Scanner 1', 'CT_SCANNER', 'DEP-RAD', 'AVAILABLE', 30),
('RES-CT-02', 'GE Revolution CT Scanner 2', 'CT_SCANNER', 'DEP-RAD', 'AVAILABLE', 30),
('RES-MRI-01', 'Philips Ingenia 3T MRI', 'MRI', 'DEP-RAD', 'AVAILABLE', 45),
('RES-XRAY-01', 'Digital X-Ray Suite 1', 'XRAY', 'DEP-RAD', 'AVAILABLE', 15),
('RES-XRAY-02', 'Portable X-Ray Suite 2', 'XRAY', 'DEP-RAD', 'AVAILABLE', 15),
('RES-US-01', 'Ultrasound Diagnostic System', 'ULTRASOUND', 'DEP-RAD', 'AVAILABLE', 20),
('RES-VENT-01', 'ICU Ventilator 1', 'VENTILATOR', 'DEP-ICU', 'AVAILABLE', 60),
('RES-VENT-02', 'ICU Ventilator 2', 'VENTILATOR', 'DEP-ICU', 'AVAILABLE', 60),
('RES-VENT-03', 'ER Emergency Ventilator 3', 'VENTILATOR', 'DEP-ER', 'AVAILABLE', 60),
('RES-ECG-01', '12-Lead ECG Machine 1', 'ECG_MACHINE', 'DEP-CAR', 'AVAILABLE', 15),
('RES-ECG-02', 'Portable ECG Machine 2', 'ECG_MACHINE', 'DEP-ER', 'AVAILABLE', 15),
('RES-LAB-01', 'Roche Cobas Hematology Analyzer', 'LAB_ANALYZER', 'DEP-LAB', 'AVAILABLE', 20),
('RES-LAB-02', 'Abbott Biochemistry Analyzer', 'LAB_ANALYZER', 'DEP-LAB', 'AVAILABLE', 20),
('RES-OT-01', 'Major Surgical Operating Theatre 1', 'OPERATING_THEATRE', 'DEP-SUR', 'AVAILABLE', 120),
('RES-OT-02', 'Laparoscopic Operating Theatre 2', 'OPERATING_THEATRE', 'DEP-SUR', 'AVAILABLE', 120)
ON CONFLICT (id) DO NOTHING;

-- 4. 40 ICD-10 DISEASE REGISTRY CATALOG
INSERT INTO diseases (id, name, icd_code, category, is_communicable, requires_isolation) VALUES
('DIS-01', 'Hypertension', 'I10', 'Cardiovascular', false, false),
('DIS-02', 'Acute Myocardial Infarction', 'I21', 'Cardiovascular', false, false),
('DIS-03', 'Congestive Heart Failure', 'I50', 'Cardiovascular', false, false),
('DIS-04', 'Atrial Fibrillation', 'I48', 'Cardiovascular', false, false),
('DIS-05', 'Deep Vein Thrombosis', 'I82', 'Cardiovascular', false, false),
('DIS-06', 'Pulmonary Embolism', 'I26', 'Cardiovascular', false, false),
('DIS-07', 'Aortic Aneurysm', 'I71', 'Cardiovascular', false, false),
('DIS-08', 'Asthma Exacerbation', 'J45', 'Respiratory', false, false),
('DIS-09', 'COPD Exacerbation', 'J44', 'Respiratory', false, false),
('DIS-10', 'Bacterial Pneumonia', 'J18', 'Respiratory', true, false),
('DIS-11', 'Acute Bronchitis', 'J20', 'Respiratory', true, false),
('DIS-12', 'Chronic Sinusitis', 'J32', 'Respiratory', false, false),
('DIS-13', 'COVID-19 Infection', 'U07.1', 'Infectious', true, true),
('DIS-14', 'Pulmonary Tuberculosis', 'A15', 'Infectious', true, true),
('DIS-15', 'Dengue Fever', 'A90', 'Infectious', true, false),
('DIS-16', 'Malaria', 'B50', 'Infectious', true, false),
('DIS-17', 'Hepatitis B', 'B16', 'Infectious', true, false),
('DIS-18', 'HIV/AIDS', 'B20', 'Infectious', true, false),
('DIS-19', 'Bacterial Meningitis', 'G00', 'Infectious', true, true),
('DIS-20', 'Acute Tonsillitis', 'J03', 'Infectious', true, false),
('DIS-21', 'Type 2 Diabetes Mellitus', 'E11', 'Endocrine', false, false),
('DIS-22', 'Diabetic Ketoacidosis', 'E10.1', 'Endocrine', false, false),
('DIS-23', 'Acute Appendicitis', 'K35', 'Gastrointestinal', false, false),
('DIS-24', 'Acute Pancreatitis', 'K85', 'Gastrointestinal', false, false),
('DIS-25', 'Liver Cirrhosis', 'K74', 'Gastrointestinal', false, false),
('DIS-26', 'Acute Gastroenteritis', 'K52', 'Gastrointestinal', true, false),
('DIS-27', 'Ischemic Stroke', 'I63', 'Neurology', false, false),
('DIS-28', 'Epilepsy', 'G40', 'Neurology', false, false),
('DIS-29', 'Migraine', 'G43', 'Neurology', false, false),
('DIS-30', 'Acute Kidney Injury', 'N17', 'Nephrology', false, false),
('DIS-31', 'Kidney Stone', 'N20', 'Nephrology', false, false),
('DIS-32', 'Femur Fracture', 'S72', 'Orthopedics', false, false),
('DIS-33', 'Osteoarthritis', 'M15', 'Orthopedics', false, false),
('DIS-34', 'Severe Sepsis', 'R65.2', 'Critical Care', false, false),
('DIS-35', 'Multi-Organ Dysfunction', 'R65.1', 'Critical Care', false, false),
('DIS-36', 'Cellulitis', 'L03', 'Dermatology', false, false),
('DIS-37', 'Urinary Tract Infection', 'N39', 'Urology', false, false),
('DIS-38', 'Depression', 'F32', 'Psychiatry', false, false),
('DIS-39', 'Severe Burns', 'T30', 'Trauma', false, false),
('DIS-40', 'Anemia', 'D64', 'Hematology', false, false)
ON CONFLICT (id) DO NOTHING;
