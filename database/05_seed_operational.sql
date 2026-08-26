-- ============================================================================
-- 05_seed_operational.sql
-- Operational Staff, Shifts, and Roles
-- Target Engine: PostgreSQL 15+ / ACID Relational SQL
-- Default credential password hash: bcrypt("hospital@123")
-- ============================================================================

INSERT INTO staff (id, first_name, last_name, role, department_id, specialization, status, current_workload, max_workload, password_hash, created_at) VALUES
-- Doctors (8)
('DOC-001', 'Rajesh', 'Sharma', 'DOCTOR', 'DEP-ER', 'Emergency Medicine', 'AVAILABLE', 0, 8, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('DOC-002', 'Priya', 'Patel', 'DOCTOR', 'DEP-ICU', 'Critical Care', 'AVAILABLE', 0, 6, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('DOC-003', 'Anil', 'Deshmukh', 'DOCTOR', 'DEP-CAR', 'Cardiology', 'AVAILABLE', 0, 8, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('DOC-004', 'Sunita', 'Verma', 'DOCTOR', 'DEP-WA', 'General Medicine', 'AVAILABLE', 0, 10, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('DOC-005', 'Vikram', 'Singh', 'DOCTOR', 'DEP-SUR', 'General Surgery', 'AVAILABLE', 0, 6, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('DOC-006', 'Kavita', 'Reddy', 'DOCTOR', 'DEP-ISO', 'Infectious Disease', 'AVAILABLE', 0, 6, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('DOC-007', 'Amit', 'Joshi', 'DOCTOR', 'DEP-RAD', 'Radiology', 'AVAILABLE', 0, 12, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('DOC-008', 'Neha', 'Gupta', 'DOCTOR', 'DEP-ER', 'Emergency Medicine', 'AVAILABLE', 0, 8, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),

-- Charge Nurses (3)
('CHN-001', 'Mary', 'D''Souza', 'CHARGE_NURSE', 'DEP-ER', 'Emergency Triage', 'AVAILABLE', 0, 10, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('CHN-002', 'Deepa', 'Nair', 'CHARGE_NURSE', 'DEP-ICU', 'ICU Coordination', 'AVAILABLE', 0, 8, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('CHN-003', 'Suresh', 'Kumar', 'CHARGE_NURSE', 'DEP-WA', 'Ward Supervision', 'AVAILABLE', 0, 12, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),

-- Nurses (15)
('NUR-001', 'Nurse_1', 'Staff', 'NURSE', 'DEP-ER', NULL, 'AVAILABLE', 0, 5, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('NUR-002', 'Nurse_2', 'Staff', 'NURSE', 'DEP-ER', NULL, 'AVAILABLE', 0, 5, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('NUR-003', 'Nurse_3', 'Staff', 'NURSE', 'DEP-ER', NULL, 'AVAILABLE', 0, 5, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('NUR-004', 'Nurse_4', 'Staff', 'NURSE', 'DEP-ER', NULL, 'AVAILABLE', 0, 5, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('NUR-005', 'Nurse_5', 'Staff', 'NURSE', 'DEP-ER', NULL, 'AVAILABLE', 0, 5, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('NUR-006', 'Nurse_6', 'Staff', 'NURSE', 'DEP-ICU', NULL, 'AVAILABLE', 0, 3, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('NUR-007', 'Nurse_7', 'Staff', 'NURSE', 'DEP-ICU', NULL, 'AVAILABLE', 0, 3, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('NUR-008', 'Nurse_8', 'Staff', 'NURSE', 'DEP-ICU', NULL, 'AVAILABLE', 0, 3, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('NUR-009', 'Nurse_9', 'Staff', 'NURSE', 'DEP-ICU', NULL, 'AVAILABLE', 0, 3, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('NUR-010', 'Nurse_10', 'Staff', 'NURSE', 'DEP-ICU', NULL, 'AVAILABLE', 0, 3, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('NUR-011', 'Nurse_11', 'Staff', 'NURSE', 'DEP-WA', NULL, 'AVAILABLE', 0, 6, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('NUR-012', 'Nurse_12', 'Staff', 'NURSE', 'DEP-WA', NULL, 'AVAILABLE', 0, 6, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('NUR-013', 'Nurse_13', 'Staff', 'NURSE', 'DEP-WA', NULL, 'AVAILABLE', 0, 6, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('NUR-014', 'Nurse_14', 'Staff', 'NURSE', 'DEP-WA', NULL, 'AVAILABLE', 0, 6, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('NUR-015', 'Nurse_15', 'Staff', 'NURSE', 'DEP-WA', NULL, 'AVAILABLE', 0, 6, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),

-- Technicians (4)
('TECH-001', 'Rohan', 'Mehta', 'TECHNICIAN', 'DEP-RAD', 'CT / MRI Specialist', 'AVAILABLE', 0, 10, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('TECH-002', 'Pooja', 'Shah', 'TECHNICIAN', 'DEP-RAD', 'X-Ray Specialist', 'AVAILABLE', 0, 10, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('TECH-003', 'Vijay', 'Yadav', 'TECHNICIAN', 'DEP-LAB', 'Blood Analyzer', 'AVAILABLE', 0, 15, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('TECH-004', 'Anita', 'Rao', 'TECHNICIAN', 'DEP-LAB', 'Pathology', 'AVAILABLE', 0, 15, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),

-- Receptionists & Admin (3)
('REC-001', 'Aakash', 'Tiwari', 'RECEPTIONIST', 'DEP-ER', 'Intake Specialist', 'AVAILABLE', 0, 20, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('REC-002', 'Sneha', 'Kulkarni', 'RECEPTIONIST', 'DEP-ER', 'Discharge Specialist', 'AVAILABLE', 0, 20, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP),
('ADM-001', 'Dr. Pranav', 'Rathi', 'ADMINISTRATOR', 'DEP-ER', 'Hospital Administration', 'AVAILABLE', 0, 50, '$2b$12$4r9WG7Ypnc2FoQUBV5Eq1eyx3HV8N35TwDlSdIFdtrcekTuiKoCWi', CURRENT_TIMESTAMP)
ON CONFLICT (id) DO NOTHING;
