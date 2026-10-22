# 5-MINUTE VIVA DEMONSTRATION SCRIPT
## Multi-Agent AI Hospital Management & Resource Optimization System
**Ramdeobaba University — IDEA Lab Project Presentation**

---

### PRE-DEMO CHECKLIST (30 SECONDS)
1. Double-click `start_system.bat` in the project root directory.
2. Confirm the browser opens to `http://localhost:5173`.
3. Confirm Backend API docs are accessible at `http://localhost:8000/docs`.

---

### STEP 1: AUTHENTICATION & ACCESS CONTROL (45 SECONDS)
1. **Screen**: Login page (`http://localhost:5173`).
2. **Action**:
   - Enter Staff ID: `ADM-001`
   - Enter Password: `hospital@123`
   - Click **Sign In**.
3. **What to Say to Evaluators**:
   > *"The system enforces multi-tenant role-based access control with Argon2/Bcrypt password hashing and JWT token authorization. Logging in as Administrator ADM-001 loads our Command Center with full governance and live WebSocket connectivity."*

---

### STEP 2: LIVE COMMAND CENTER & BED TOPOLOGY (45 SECONDS)
1. **Screen**: Command Center Dashboard.
2. **Action**:
   - Point out the top **Metric Cards**: Total Inpatients, Emergency Queue, Bed Occupancy %, and Active Discharges.
   - Point out the **Live Stream** green status pill in the top-right corner.
   - Click **Bed Capacity** in the sidebar. Show the 6 hospital wards (ER, ICU, Cardiology, General, Pediatrics, Surgical).
3. **What to Say to Evaluators**:
   > *"The Command Center provides real-time facility telemetry across 28 relational tables in PostgreSQL. The bed matrix monitors 44+ clinical stations with ventilator and negative-pressure isolation filtering."*

---

### STEP 3: PATIENT INTAKE & MULTI-AGENT ESI TRIAGE (60 SECONDS)
1. **Screen**: Click **+ New Patient Intake** in the toolbar.
2. **Action**:
   - **Step 1 (Demographics)**:
     - First Name: `Rajesh`
     - Last Name: `Khanna`
     - Age: `54`
     - Click **Continue to Clinical Vitals**.
   - **Step 2 (Vitals & Complaints)**:
     - Chief Complaint: `Acute severe chest pain radiating to left arm with diaphoresis`
     - Heart Rate: `115` bpm
     - SpO2: `92` %
     - Blood Pressure: `90 / 55` mmHg
     - Click **Execute Intelligent Intake**.
3. **What to Say to Evaluators**:
   > *"The intake triggers our LangGraph Multi-Agent Engine. The Triage Agent ingests the clinical vitals and chief complaint, classifies the patient as ESI-2 (High Acuity), detects hypoxia and cardiac distress, and selects an ICU ventilator station."*

---

### STEP 4: HUMAN-IN-THE-LOOP APPROVAL GATE (60 SECONDS)
1. **Screen**: Click **Approvals** in the sidebar.
2. **Action**:
   - Point out the newly created approval card: `Ticket for Rajesh Khanna (ESI-2, High Acuity Transfer to ICU)`.
   - Point out that the bed is **NOT** allocated yet; the system safely locks state pending physician authorization.
   - Review the AI Decision Rationale card showing the OR-Tools constraint score.
   - Click **Approve**.
3. **What to Say to Evaluators**:
   > *"In compliance with our Human-in-the-Loop safety specifications, high-risk transfers cannot autonomously alter database state. An attending physician must review the clinical rationale. Approving executes a pessimistic row lock (`SELECT FOR UPDATE`), writes an immutable audit log, and reserves the station atomically."*

---

### STEP 5: REAL-TIME ZERO-REFRESH SYNCHRONIZATION (30 SECONDS)
1. **Screen**: Click **Bed Capacity** or **Command Center**.
2. **Action**:
   - Show the target ICU bed now marked **OCCUPIED** with patient `Rajesh Khanna`.
   - Point out that **ZERO** browser refresh was required.
3. **What to Say to Evaluators**:
   > *"The state change was broadcast through our Redis Pub/Sub WebSocket event bus with ring-buffer deduplication and exponential reconnect backoff. The system achieves a 35.6% reduction in triage latency during emergency surges."*

---

### DEMO BACKUP / RECOVERY CONTROLS
- If network disconnects: Point to the automatic fallback polling indicator ("Connected via Polling Fallback").
- To view test proofs: Open `idea lab/scratch/` and show `test_browser_12_perfect.py` (12/12 passed) and `docs/charts/` (latency and capacity plots).
