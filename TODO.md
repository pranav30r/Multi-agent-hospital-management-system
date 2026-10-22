# CITY HOSPITAL - Backend Integration & TODO List

## 1. Overview
The CITY HOSPITAL Operations Suite is structured to operate with complete clinical fidelity using PostgreSQL and Redis microservices, while providing graceful local client fallbacks for newly provisioned executive features.

---

## 2. Active Live Endpoints
The following endpoints are connected directly to PostgreSQL via SQLAlchemy 2.0 and active in Docker container `hospital_backend`:

- `POST /api/v1/auth/login`: Authenticates staff against bcrypt hashes and issues cryptographically signed JWT bearer tokens with tenant isolation (`ADM-001`, `DOC-001`).
- `GET /api/v1/auth/me`: Resolves logged-in clinician profile and roles.
- `GET /api/v1/system/metrics`: Live server telemetry, memory consumption, CPU utilization, DB pool status, and feature flags.
- `GET /api/v1/staff`: Queries 33 rostered physicians, nurses, technicians, and administrators.
- `PATCH /api/v1/staff/{staff_id}/status`: Live operational toggle between `AVAILABLE` and `OFF_DUTY`.
- `GET /api/v1/beds`: Retrieves telemetry and occupancy for all physical stations across hospital wards.
- `GET /api/v1/departments`: Retrieves configured clinical units (`DEP-ER`, `DEP-ICU`, `DEP-GEN`, `DEP-PED`).
- `POST /api/v1/beds/book-manual`: Assigns an active encounter to an available bed station.
- `POST /api/v1/beds/{bed_id}/confirm-patient-in-bed`: Transitions bed state from `RESERVED` to `OCCUPIED`.
- `POST /api/v1/beds/{bed_id}/release`: Releases bed for sanitization and returns it to `AVAILABLE`.
- `GET /api/v1/patients/encounters/active`: Live emergency triage queue.
- `POST /api/v1/patients`: Demographics registration.
- `POST /api/v1/patients/encounters`: Records vitals and initiates automated triage score calculation.
- `GET /api/v1/audit`: Immutable append-only audit trail ledger for hospital operations.

---

## 3. Client Mock Fallback Layer (Ready for Backend Migration)
The following administrative settings are currently backed by the high-performance local client storage layer and ready for dedicated FastAPI database tables:

| Feature | Current State | Target Backend Endpoint | Notes |
| :--- | :--- | :--- | :--- |
| **Staff Invitations** | UI simulation & audit note | `POST /api/v1/staff/invite` | Should trigger email SMTP dispatch and temporary password generation |
| **Custom Bed Stations** | Local storage cache + live merge | `POST /api/v1/beds` | Provision new physical bed stations dynamically |
| **AI Governance Rules** | Config store with auto-escalation | `PUT /api/v1/ai/governance` | Synchronize risk thresholds with LangGraph multi-agent runner |
| **Facility Settings** | Client configuration store | `PUT /api/v1/system/settings` | Persist hospital name, emergency hotline, and timezone across cluster |
| **Demo Mode** | Instant 1-click clinical toggle | `POST /api/v1/simulation/demo` | Seeds 14 realistic Indian hospital patients, telemetry vitals, and pending AI decisions |

---

## 4. Multi-Agent System Reliability
- **Triage Agent**: Evaluates vitals (HR, SpO2, BP) and assigns ESI Levels 1 through 5.
- **Bed Agent**: Enforces constraint optimization across ICU ventilator and isolation units.
- **Human-in-the-Loop Barrier**: Intercepts high-risk decisions (>0.85 risk) into the Clinical AI Approvals queue before database commit.
