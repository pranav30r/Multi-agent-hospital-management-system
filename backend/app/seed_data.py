import asyncio
import logging
from sqlalchemy import select
from app.database import AsyncSessionLocal, init_db
from app.models import (
    Department, Bed, Staff, Equipment, Disease, WorkflowDefinition
)

logger = logging.getLogger("seed_data")

DEPARTMENTS_DATA = [
    {"id": "DEP-ER", "name": "Emergency Department", "code": "ER", "total_beds": 6, "min_doctors": 2, "min_nurses": 3, "nurse_patient_ratio": "1:3"},
    {"id": "DEP-ICU", "name": "Intensive Care Unit", "code": "ICU", "total_beds": 8, "min_doctors": 2, "min_nurses": 4, "nurse_patient_ratio": "1:2"},
    {"id": "DEP-WA", "name": "General Ward A", "code": "WA", "total_beds": 10, "min_doctors": 1, "min_nurses": 2, "nurse_patient_ratio": "1:5"},
    {"id": "DEP-WB", "name": "General Ward B", "code": "WB", "total_beds": 10, "min_doctors": 1, "min_nurses": 2, "nurse_patient_ratio": "1:5"},
    {"id": "DEP-CAR", "name": "Cardiology Department", "code": "CAR", "total_beds": 6, "min_doctors": 1, "min_nurses": 2, "nurse_patient_ratio": "1:3"},
    {"id": "DEP-ISO", "name": "Isolation Unit", "code": "ISO", "total_beds": 4, "min_doctors": 1, "min_nurses": 2, "nurse_patient_ratio": "1:2"},
    {"id": "DEP-RAD", "name": "Radiology Department", "code": "RAD", "total_beds": 0, "min_doctors": 1, "min_nurses": 1, "nurse_patient_ratio": "1:5"},
    {"id": "DEP-LAB", "name": "Laboratory Department", "code": "LAB", "total_beds": 0, "min_doctors": 0, "min_nurses": 0, "nurse_patient_ratio": "1:5"},
    {"id": "DEP-SUR", "name": "Surgery Department", "code": "SUR", "total_beds": 0, "min_doctors": 2, "min_nurses": 2, "nurse_patient_ratio": "1:2"},
]

BEDS_DATA = [
    # ICU Beds (8)
    *[{"id": f"BED-ICU-{i:02d}", "department_id": "DEP-ICU", "bed_type": "ICU", "has_ventilator": True, "has_telemetry": True} for i in range(1, 9)],
    # Emergency Beds (6)
    *[{"id": f"BED-ER-{i:02d}", "department_id": "DEP-ER", "bed_type": "EMERGENCY", "has_telemetry": True} for i in range(1, 7)],
    # Ward A Beds (10)
    *[{"id": f"BED-WA-{i:02d}", "department_id": "DEP-WA", "bed_type": "GENERAL"} for i in range(1, 11)],
    # Ward B Beds (10)
    *[{"id": f"BED-WB-{i:02d}", "department_id": "DEP-WB", "bed_type": "GENERAL"} for i in range(1, 11)],
    # Cardiology Beds (6)
    *[{"id": f"BED-CAR-{i:02d}", "department_id": "DEP-CAR", "bed_type": "CARDIAC_MONITOR", "has_telemetry": True} for i in range(1, 7)],
    # Isolation Beds (4)
    *[{"id": f"BED-ISO-{i:02d}", "department_id": "DEP-ISO", "bed_type": "ISOLATION", "is_isolation": True} for i in range(1, 5)],
]

STAFF_DATA = [
    # Doctors (8)
    {"id": "DOC-001", "first_name": "Rajesh", "last_name": "Sharma", "role": "DOCTOR", "department_id": "DEP-ER", "specialization": "Emergency Medicine"},
    {"id": "DOC-002", "first_name": "Priya", "last_name": "Patel", "role": "DOCTOR", "department_id": "DEP-ICU", "specialization": "Critical Care"},
    {"id": "DOC-003", "first_name": "Anil", "last_name": "Deshmukh", "role": "DOCTOR", "department_id": "DEP-CAR", "specialization": "Cardiology"},
    {"id": "DOC-004", "first_name": "Sunita", "last_name": "Verma", "role": "DOCTOR", "department_id": "DEP-WA", "specialization": "General Medicine"},
    {"id": "DOC-005", "first_name": "Vikram", "last_name": "Singh", "role": "DOCTOR", "department_id": "DEP-SUR", "specialization": "General Surgery"},
    {"id": "DOC-006", "first_name": "Kavita", "last_name": "Reddy", "role": "DOCTOR", "department_id": "DEP-ISO", "specialization": "Infectious Disease"},
    {"id": "DOC-007", "first_name": "Amit", "last_name": "Joshi", "role": "DOCTOR", "department_id": "DEP-RAD", "specialization": "Radiology"},
    {"id": "DOC-008", "first_name": "Neha", "last_name": "Gupta", "role": "DOCTOR", "department_id": "DEP-ER", "specialization": "Emergency Medicine"},
    
    # Charge Nurses (3)
    {"id": "CHN-001", "first_name": "Mary", "last_name": "D'Souza", "role": "CHARGE_NURSE", "department_id": "DEP-ER"},
    {"id": "CHN-002", "first_name": "Deepa", "last_name": "Nair", "role": "CHARGE_NURSE", "department_id": "DEP-ICU"},
    {"id": "CHN-003", "first_name": "Suresh", "last_name": "Kumar", "role": "CHARGE_NURSE", "department_id": "DEP-WA"},
    
    # Nurses (15)
    *[{"id": f"NUR-{i:03d}", "first_name": f"Nurse_{i}", "last_name": "Staff", "role": "NURSE", "department_id": "DEP-ER" if i<=5 else ("DEP-ICU" if i<=10 else "DEP-WA")} for i in range(1, 16)],
    
    # Technicians (4)
    {"id": "TECH-001", "first_name": "Rohan", "last_name": "Mehta", "role": "TECHNICIAN", "department_id": "DEP-RAD", "specialization": "CT / MRI Specialist"},
    {"id": "TECH-002", "first_name": "Pooja", "last_name": "Shah", "role": "TECHNICIAN", "department_id": "DEP-RAD", "specialization": "X-Ray Specialist"},
    {"id": "TECH-003", "first_name": "Vijay", "last_name": "Yadav", "role": "TECHNICIAN", "department_id": "DEP-LAB", "specialization": "Blood Analyzer"},
    {"id": "TECH-004", "first_name": "Anita", "last_name": "Rao", "role": "TECHNICIAN", "department_id": "DEP-LAB", "specialization": "Pathology"},
    
    # Receptionists & Admins
    {"id": "REC-001", "first_name": "Aakash", "last_name": "Tiwari", "role": "RECEPTIONIST", "department_id": "DEP-ER"},
    {"id": "REC-002", "first_name": "Sneha", "last_name": "Kulkarni", "role": "RECEPTIONIST", "department_id": "DEP-ER"},
    {"id": "ADM-001", "first_name": "Dr. Pranav", "last_name": "Rathi", "role": "ADMINISTRATOR", "department_id": "DEP-ER"},
]

EQUIPMENT_DATA = [
    {"id": "RES-CT-01", "name": "Siemens Somatom CT Scanner 1", "resource_type": "CT_SCANNER", "department_id": "DEP-RAD", "slot_duration_mins": 30},
    {"id": "RES-CT-02", "name": "GE Revolution CT Scanner 2", "resource_type": "CT_SCANNER", "department_id": "DEP-RAD", "slot_duration_mins": 30},
    {"id": "RES-MRI-01", "name": "Philips Ingenia 3T MRI", "resource_type": "MRI", "department_id": "DEP-RAD", "slot_duration_mins": 45},
    {"id": "RES-XRAY-01", "name": "Digital X-Ray Suite 1", "resource_type": "XRAY", "department_id": "DEP-RAD", "slot_duration_mins": 15},
    {"id": "RES-XRAY-02", "name": "Portable X-Ray Suite 2", "resource_type": "XRAY", "department_id": "DEP-RAD", "slot_duration_mins": 15},
    {"id": "RES-US-01", "name": "Ultrasound Diagnostic System", "resource_type": "ULTRASOUND", "department_id": "DEP-RAD", "slot_duration_mins": 20},
    {"id": "RES-VENT-01", "name": "ICU Ventilator 1", "resource_type": "VENTILATOR", "department_id": "DEP-ICU", "slot_duration_mins": 60},
    {"id": "RES-VENT-02", "name": "ICU Ventilator 2", "resource_type": "VENTILATOR", "department_id": "DEP-ICU", "slot_duration_mins": 60},
    {"id": "RES-VENT-03", "name": "ER Emergency Ventilator 3", "resource_type": "VENTILATOR", "department_id": "DEP-ER", "slot_duration_mins": 60},
    {"id": "RES-ECG-01", "name": "12-Lead ECG Machine 1", "resource_type": "ECG_MACHINE", "department_id": "DEP-CAR", "slot_duration_mins": 15},
    {"id": "RES-ECG-02", "name": "Portable ECG Machine 2", "resource_type": "ECG_MACHINE", "department_id": "DEP-ER", "slot_duration_mins": 15},
    {"id": "RES-LAB-01", "name": "Roche Cobas Hematology Analyzer", "resource_type": "LAB_ANALYZER", "department_id": "DEP-LAB", "slot_duration_mins": 20},
    {"id": "RES-LAB-02", "name": "Abbott Biochemistry Analyzer", "resource_type": "LAB_ANALYZER", "department_id": "DEP-LAB", "slot_duration_mins": 20},
    {"id": "RES-OT-01", "name": "Major Surgical Operating Theatre 1", "resource_type": "OPERATING_THEATRE", "department_id": "DEP-SUR", "slot_duration_mins": 120},
    {"id": "RES-OT-02", "name": "Laparoscopic Operating Theatre 2", "resource_type": "OPERATING_THEATRE", "department_id": "DEP-SUR", "slot_duration_mins": 120},
]

DISEASES_DATA = [
    # Cardiovascular (7)
    {"name": "Hypertension", "icd_code": "I10", "category": "Cardiovascular", "is_communicable": False, "requires_isolation": False},
    {"name": "Acute Myocardial Infarction", "icd_code": "I21", "category": "Cardiovascular", "is_communicable": False, "requires_isolation": False},
    {"name": "Congestive Heart Failure", "icd_code": "I50", "category": "Cardiovascular", "is_communicable": False, "requires_isolation": False},
    {"name": "Atrial Fibrillation", "icd_code": "I48", "category": "Cardiovascular", "is_communicable": False, "requires_isolation": False},
    {"name": "Deep Vein Thrombosis", "icd_code": "I82", "category": "Cardiovascular", "is_communicable": False, "requires_isolation": False},
    {"name": "Pulmonary Embolism", "icd_code": "I26", "category": "Cardiovascular", "is_communicable": False, "requires_isolation": False},
    {"name": "Aortic Aneurysm", "icd_code": "I71", "category": "Cardiovascular", "is_communicable": False, "requires_isolation": False},
    # Respiratory (5)
    {"name": "Asthma Exacerbation", "icd_code": "J45", "category": "Respiratory", "is_communicable": False, "requires_isolation": False},
    {"name": "COPD Exacerbation", "icd_code": "J44", "category": "Respiratory", "is_communicable": False, "requires_isolation": False},
    {"name": "Bacterial Pneumonia", "icd_code": "J18", "category": "Respiratory", "is_communicable": True, "requires_isolation": False},
    {"name": "Acute Bronchitis", "icd_code": "J20", "category": "Respiratory", "is_communicable": True, "requires_isolation": False},
    {"name": "Chronic Sinusitis", "icd_code": "J32", "category": "Respiratory", "is_communicable": False, "requires_isolation": False},
    # Infectious (8)
    {"name": "COVID-19 Infection", "icd_code": "U07.1", "category": "Infectious", "is_communicable": True, "requires_isolation": True},
    {"name": "Pulmonary Tuberculosis", "icd_code": "A15", "category": "Infectious", "is_communicable": True, "requires_isolation": True},
    {"name": "Dengue Fever", "icd_code": "A90", "category": "Infectious", "is_communicable": True, "requires_isolation": False},
    {"name": "Malaria", "icd_code": "B50", "category": "Infectious", "is_communicable": True, "requires_isolation": False},
    {"name": "Hepatitis B", "icd_code": "B16", "category": "Infectious", "is_communicable": True, "requires_isolation": False},
    {"name": "HIV/AIDS", "icd_code": "B20", "category": "Infectious", "is_communicable": True, "requires_isolation": False},
    {"name": "Bacterial Meningitis", "icd_code": "G00", "category": "Infectious", "is_communicable": True, "requires_isolation": True},
    {"name": "Acute Tonsillitis", "icd_code": "J03", "category": "Infectious", "is_communicable": True, "requires_isolation": False},
    # Endocrine (2)
    {"name": "Type 2 Diabetes Mellitus", "icd_code": "E11", "category": "Endocrine", "is_communicable": False, "requires_isolation": False},
    {"name": "Diabetic Ketoacidosis", "icd_code": "E10.1", "category": "Endocrine", "is_communicable": False, "requires_isolation": False},
    # Gastrointestinal (4)
    {"name": "Acute Appendicitis", "icd_code": "K35", "category": "Gastrointestinal", "is_communicable": False, "requires_isolation": False},
    {"name": "Acute Pancreatitis", "icd_code": "K85", "category": "Gastrointestinal", "is_communicable": False, "requires_isolation": False},
    {"name": "Liver Cirrhosis", "icd_code": "K74", "category": "Gastrointestinal", "is_communicable": False, "requires_isolation": False},
    {"name": "Acute Gastroenteritis", "icd_code": "K52", "category": "Gastrointestinal", "is_communicable": True, "requires_isolation": False},
    # Neurology (3)
    {"name": "Ischemic Stroke", "icd_code": "I63", "category": "Neurology", "is_communicable": False, "requires_isolation": False},
    {"name": "Epilepsy", "icd_code": "G40", "category": "Neurology", "is_communicable": False, "requires_isolation": False},
    {"name": "Migraine", "icd_code": "G43", "category": "Neurology", "is_communicable": False, "requires_isolation": False},
    # Nephrology (2)
    {"name": "Acute Kidney Injury", "icd_code": "N17", "category": "Nephrology", "is_communicable": False, "requires_isolation": False},
    {"name": "Kidney Stone", "icd_code": "N20", "category": "Nephrology", "is_communicable": False, "requires_isolation": False},
    # Orthopedics (2)
    {"name": "Femur Fracture", "icd_code": "S72", "category": "Orthopedics", "is_communicable": False, "requires_isolation": False},
    {"name": "Osteoarthritis", "icd_code": "M15", "category": "Orthopedics", "is_communicable": False, "requires_isolation": False},
    # Critical Care (2)
    {"name": "Severe Sepsis", "icd_code": "R65.2", "category": "Critical Care", "is_communicable": False, "requires_isolation": False},
    {"name": "Multi-Organ Dysfunction", "icd_code": "R65.1", "category": "Critical Care", "is_communicable": False, "requires_isolation": False},
    # Dermatology / Other (3)
    {"name": "Cellulitis", "icd_code": "L03", "category": "Dermatology", "is_communicable": False, "requires_isolation": False},
    {"name": "Urinary Tract Infection", "icd_code": "N39", "category": "Urology", "is_communicable": False, "requires_isolation": False},
    {"name": "Depression", "icd_code": "F32", "category": "Psychiatry", "is_communicable": False, "requires_isolation": False},
    # Burns / Trauma (2)
    {"name": "Severe Burns", "icd_code": "T30", "category": "Trauma", "is_communicable": False, "requires_isolation": False},
    {"name": "Anemia", "icd_code": "D64", "category": "Hematology", "is_communicable": False, "requires_isolation": False},
]

WORKFLOW_DEFINITIONS_DATA = [
    {
        "id": "WFD-EMERGENCY-ADMISSION",
        "name": "Emergency Admission Workflow",
        "category": "EMERGENCY",
        "steps_json": [
            {"step_number": 1, "name": "Registration", "expected_duration_min": 5, "required": True},
            {"step_number": 2, "name": "ESI Triage Assessment", "expected_duration_min": 10, "required": True},
            {"step_number": 3, "name": "Doctor Examination", "expected_duration_min": 15, "required": True},
            {"step_number": 4, "name": "Diagnostic Investigation", "expected_duration_min": 30, "required": False},
            {"step_number": 5, "name": "Bed Allocation & Reservation", "expected_duration_min": 10, "required": True},
            {"step_number": 6, "name": "Patient Transport to Bed", "expected_duration_min": 15, "required": True},
            {"step_number": 7, "name": "Clinical Handoff", "expected_duration_min": 10, "required": True},
            {"step_number": 8, "name": "Inpatient Admission", "expected_duration_min": 10, "required": True},
            {"step_number": 9, "name": "Discharge Planning", "expected_duration_min": 15, "required": True},
            {"step_number": 10, "name": "Final Discharge", "expected_duration_min": 10, "required": True},
        ]
    },
    {
        "id": "WFD-OPD-VISIT",
        "name": "Outpatient (OPD) Visit Workflow",
        "category": "OPD",
        "steps_json": [
            {"step_number": 1, "name": "Registration", "expected_duration_min": 5, "required": True},
            {"step_number": 2, "name": "ESI Triage Assessment", "expected_duration_min": 10, "required": True},
            {"step_number": 3, "name": "Doctor Assignment", "expected_duration_min": 5, "required": True},
            {"step_number": 4, "name": "Doctor Examination", "expected_duration_min": 15, "required": True},
            {"step_number": 5, "name": "Investigation (Optional)", "expected_duration_min": 20, "required": False},
            {"step_number": 6, "name": "Diagnosis & Treatment Plan", "expected_duration_min": 10, "required": True},
            {"step_number": 7, "name": "OPD Discharge", "expected_duration_min": 5, "required": True},
        ]
    },
    {
        "id": "WFD-TRANSFER",
        "name": "Inter-Department Transfer Workflow",
        "category": "TRANSFER",
        "steps_json": [
            {"step_number": 1, "name": "Transfer Request", "expected_duration_min": 5, "required": True},
            {"step_number": 2, "name": "Destination Bed Search", "expected_duration_min": 5, "required": True},
            {"step_number": 3, "name": "Transfer Approval", "expected_duration_min": 10, "required": True},
            {"step_number": 4, "name": "Handoff Preparation", "expected_duration_min": 10, "required": True},
            {"step_number": 5, "name": "Physical Transfer", "expected_duration_min": 15, "required": True},
            {"step_number": 6, "name": "Receiving Handoff Confirmation", "expected_duration_min": 10, "required": True},
        ]
    }
]

async def seed_database():
    """Populates the database with initial synthetic hospital infrastructure."""
    await init_db()
    async with AsyncSessionLocal() as session:
        # Check if already seeded
        result = await session.execute(select(Department))
        if result.scalars().first():
            logger.info("Database already seeded. Skipping.")
            return

        logger.info("Seeding hospital infrastructure...")
        
        for dept in DEPARTMENTS_DATA:
            session.add(Department(**dept))
            
        for bed in BEDS_DATA:
            session.add(Bed(**bed))
            
        from app.auth.security import get_password_hash
        default_pwd_hash = get_password_hash("hospital@123")

        for staff in STAFF_DATA:
            staff_dict = {**staff, "password_hash": default_pwd_hash}
            session.add(Staff(**staff_dict))
            
        for eq in EQUIPMENT_DATA:
            session.add(Equipment(**eq))
            
        for dis in DISEASES_DATA:
            session.add(Disease(**dis))
            
        for wfd in WORKFLOW_DEFINITIONS_DATA:
            session.add(WorkflowDefinition(**wfd))

        await session.commit()
        logger.info("Synthetic hospital infrastructure seeded successfully!")

if __name__ == "__main__":
    asyncio.run(seed_database())
