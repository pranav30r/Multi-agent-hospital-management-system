-- ============================================================================
-- 03_seed_clinical.sql
-- Clinical Disease Registry Catalog (40 Standard ICD-10 Diagnoses)
-- Target Engine: PostgreSQL 15+ / ACID Relational SQL
-- ============================================================================

INSERT INTO diseases (id, name, icd_code, category, is_communicable, requires_isolation, added_by, created_at, is_active) VALUES
('DIS-01', 'Hypertension', 'I10', 'Cardiovascular', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-02', 'Acute Myocardial Infarction', 'I21', 'Cardiovascular', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-03', 'Congestive Heart Failure', 'I50', 'Cardiovascular', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-04', 'Atrial Fibrillation', 'I48', 'Cardiovascular', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-05', 'Deep Vein Thrombosis', 'I82', 'Cardiovascular', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-06', 'Pulmonary Embolism', 'I26', 'Cardiovascular', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-07', 'Aortic Aneurysm', 'I71', 'Cardiovascular', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-08', 'Asthma Exacerbation', 'J45', 'Respiratory', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-09', 'COPD Exacerbation', 'J44', 'Respiratory', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-10', 'Bacterial Pneumonia', 'J18', 'Respiratory', true, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-11', 'Acute Bronchitis', 'J20', 'Respiratory', true, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-12', 'Chronic Sinusitis', 'J32', 'Respiratory', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-13', 'COVID-19 Infection', 'U07.1', 'Infectious', true, true, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-14', 'Pulmonary Tuberculosis', 'A15', 'Infectious', true, true, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-15', 'Dengue Fever', 'A90', 'Infectious', true, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-16', 'Malaria', 'B50', 'Infectious', true, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-17', 'Hepatitis B', 'B16', 'Infectious', true, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-18', 'HIV/AIDS', 'B20', 'Infectious', true, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-19', 'Bacterial Meningitis', 'G00', 'Infectious', true, true, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-20', 'Acute Tonsillitis', 'J03', 'Infectious', true, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-21', 'Type 2 Diabetes Mellitus', 'E11', 'Endocrine', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-22', 'Diabetic Ketoacidosis', 'E10.1', 'Endocrine', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-23', 'Acute Appendicitis', 'K35', 'Gastrointestinal', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-24', 'Acute Pancreatitis', 'K85', 'Gastrointestinal', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-25', 'Liver Cirrhosis', 'K74', 'Gastrointestinal', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-26', 'Acute Gastroenteritis', 'K52', 'Gastrointestinal', true, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-27', 'Ischemic Stroke', 'I63', 'Neurology', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-28', 'Epilepsy', 'G40', 'Neurology', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-29', 'Migraine', 'G43', 'Neurology', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-30', 'Acute Kidney Injury', 'N17', 'Nephrology', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-31', 'Kidney Stone', 'N20', 'Nephrology', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-32', 'Femur Fracture', 'S72', 'Orthopedics', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-33', 'Osteoarthritis', 'M15', 'Orthopedics', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-34', 'Severe Sepsis', 'R65.2', 'Critical Care', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-35', 'Multi-Organ Dysfunction', 'R65.1', 'Critical Care', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-36', 'Cellulitis', 'L03', 'Dermatology', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-37', 'Urinary Tract Infection', 'N39', 'Urology', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-38', 'Depression', 'F32', 'Psychiatry', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-39', 'Severe Burns', 'T30', 'Trauma', false, false, 'REC-001', CURRENT_TIMESTAMP, true),
('DIS-40', 'Anemia', 'D64', 'Hematology', false, false, 'REC-001', CURRENT_TIMESTAMP, true)
ON CONFLICT (id) DO NOTHING;
