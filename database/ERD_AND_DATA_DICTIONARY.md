# Hospital Management System — Database Architecture & Data Dictionary

## 1. Database Overview
- **Database Engine:** PostgreSQL 15+ (ACID Compliant, Row-Level Concurrency)
- **Data Access Layer:** Python SQLAlchemy 2.0 (Async Core + AsyncPG Driver)
- **Design Paradigm:** Relational 3NF with JSONB Clinical Payload Flexibilities
- **Total Tables:** 28 Core Relational Tables

---

## 2. Entity Relationship Diagram (ERD)

```mermaid
erDiagram
    DEPARTMENTS ||--o{ BEDS : contains
    DEPARTMENTS ||--o{ STAFF : employs
    DEPARTMENTS ||--o{ EQUIPMENT : houses
    DEPARTMENTS ||--o{ QUEUES : manages

    PATIENTS ||--o{ ENCOUNTERS : presents
    ENCOUNTERS ||--o{ BED_ASSIGNMENTS : occupies
    BEDS ||--o{ BED_ASSIGNMENTS : assigned_to

    STAFF ||--o{ STAFF_SHIFTS : schedules
    STAFF ||--o{ STAFF_SKILLS : certifies

    EQUIPMENT ||--o{ EQUIPMENT_BOOKINGS : reserves
    ENCOUNTERS ||--o{ EQUIPMENT_BOOKINGS : requests

    WORKFLOW_DEFINITIONS ||--o{ WORKFLOW_INSTANCES : instantiates
    WORKFLOW_INSTANCES ||--o{ WORKFLOW_STEPS : executes
    ENCOUNTERS ||--o{ WORKFLOW_INSTANCES : tracks

    ENCOUNTERS ||--o{ TASKS : assigns
    ENCOUNTERS ||--o{ ADMISSIONS : admits
    ENCOUNTERS ||--o{ TRANSFERS : transfers
    ENCOUNTERS ||--o{ DISCHARGES : concludes

    AGENT_DECISIONS ||--o{ APPROVAL_ITEMS : requires_review
    ENCOUNTERS ||--o{ AGENT_DECISIONS : informs

    DEPARTMENTS {
        string id PK
        string name
        string code UK
        int floor_number
        int min_doctors
        int min_nurses
    }

    BEDS {
        string id PK
        string department_id FK
        string bed_number
        string bed_type
        string status
        boolean is_isolation_capable
    }

    PATIENTS {
        string id PK
        string first_name
        string last_name
        date date_of_birth
        string gender
        jsonb allergies
        jsonb chronic_conditions
    }

    ENCOUNTERS {
        string id PK
        string patient_id FK
        string admission_type
        string status
        string current_department_id FK
        int esi_score
        jsonb initial_vitals
        jsonb presenting_symptoms
    }

    STAFF {
        string id PK
        string first_name
        string last_name
        string role
        string department_id FK
        string status
        int current_workload
        int max_workload
    }

    EQUIPMENT {
        string id PK
        string name
        string resource_type
        string department_id FK
        string status
        int slot_duration_mins
    }

    DISEASES {
        string id PK
        string name
        string icd_code UK
        string category
        boolean is_communicable
        boolean requires_isolation
    }

    APPROVAL_ITEMS {
        string id PK
        string decision_id FK
        string agent_id
        string risk_level
        string status
        jsonb proposed_payload
    }

    AUDIT_LOGS {
        string id PK
        timestamp timestamp
        string entity_type
        string entity_id
        string field_changed
        string old_value
        string new_value
        string changed_by
        string change_reason
    }
```

---

## 3. Data Dictionary Summary (Core 28 Tables)

| Category | Table Name | Purpose | Primary Key | Foreign Keys |
| :--- | :--- | :--- | :--- | :--- |
| **Clinical** | `patients` | Master patient demographic and allergy records | `id` | None |
| **Clinical** | `encounters` | Inpatient/Emergency visits, ESI triage, vital signs | `id` | `patient_id`, `current_department_id`, `current_bed_id` |
| **Clinical** | `diseases` | 40 ICD-10 disease registry with isolation flags | `id` | None (`icd_code` unique) |
| **Infrastructure** | `departments` | 9 hospital departments (ER, ICU, Ward A/B, etc.) | `id` | None (`code` unique) |
| **Infrastructure** | `beds` | 44 beds with state tracking (AVAILABLE, RESERVED, OCCUPIED) | `id` | `department_id` |
| **Infrastructure** | `bed_assignments` | Historical timeline of patient bed occupancy | `id` | `bed_id`, `encounter_id`, `patient_id` |
| **Workforce** | `staff` | 33 staff members with workload tracking | `id` | `department_id` |
| **Workforce** | `staff_shifts` | Shift schedules (Morning, Evening, Night) | `id` | `staff_id`, `department_id` |
| **Workforce** | `staff_skills` | Certifications (ICU, Trauma, ACLS, BLS) | `id` | `staff_id` |
| **Resources** | `equipment` | 15 critical devices (CT, MRI, Ventilators, OTs) | `id` | `department_id` |
| **Resources** | `equipment_bookings` | Patient diagnostic and surgical reservations | `id` | `equipment_id`, `encounter_id`, `patient_id` |
| **Workflows** | `workflow_definitions` | Clinical pathway templates (Emergency, OPD, Transfer) | `id` | None |
| **Workflows** | `workflow_instances` | Live executed patient care pathways | `id` | `workflow_definition_id`, `encounter_id`, `patient_id` |
| **Workflows** | `workflow_steps` | Step progression and timestamp adherence | `id` | `instance_id` |
| **Workflows** | `queues` | Department queue depths and wait estimations | `id` | `department_id` |
| **Workflows** | `tasks` | Clinical task backlog and staff assignments | `id` | `encounter_id`, `assigned_to_id` |
| **Workflows** | `admissions` | Inpatient admission events | `id` | `encounter_id`, `patient_id`, `bed_id` |
| **Workflows** | `transfers` | Inter-department transfer requests and states | `id` | `encounter_id` |
| **Workflows** | `discharges` | Final discharge summaries and timestamps | `id` | `encounter_id`, `patient_id` |
| **Emergency** | `emergency_events` | Hospital surges (Mass Casualty, Epidemic) | `id` | None |
| **Analytics** | `prediction_runs` | Model inference logs, surge forecasts, latency | `id` | None |
| **AI Multi-Agent** | `agent_decisions` | Raw agent proposals with confidence and rationale | `id` | None |
| **AI Multi-Agent** | `agent_messages` | Inter-agent communication event payloads | `id` | None |
| **AI Multi-Agent** | `optimization_runs`| Mathematical solver optimization runs | `id` | None |
| **AI Multi-Agent** | `crew_runs` | CrewAI task executions and summaries | `id` | None |
| **AI Multi-Agent** | `langgraph_checkpoints` | State graph thread checkpoints | `id` | None |
| **Governance** | `approval_items` | Human-in-the-loop verification queue | `id` | `decision_id` |
| **Governance** | `audit_logs` | Immutable HIPAA security and change trail | `id` | None |
