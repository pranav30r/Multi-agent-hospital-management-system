# MULTI-AGENT AI SYSTEMS FOR HOSPITAL RESOURCE OPTIMIZATION, CLINICAL WORKFLOW AUTOMATION, AND PATIENT CARE COORDINATION
**Academic Project Final Report — IDEA Lab / Honours Programme**  
**Ramdeobaba University, Department of Computer Science & Engineering**

---

### Student Team Members:
1. **Pranav Rathi** (Backend Infrastructure, Database Concurrency, Security & Event Bus Lead)
2. **Atharva Jogiji** (Multi-Agent Architecture, LangGraph State Machine & Constraint Optimization Lead)
3. **Reeti Khandelwal** (Frontend Engineering, Real-Time Resilience & User Experience Lead)

---

## 1. ABSTRACT
Modern healthcare facilities suffer severe care delivery bottlenecks driven by unpredictable Emergency Department (ED) inflows, suboptimal bed occupancy management, and delayed critical care handoffs. Traditional Hospital Information Systems (HIS) function as passive relational registries requiring manual clerical coordination. This report presents a decentralized Multi-Agent AI System (MAS) built with LangGraph, FastAPI, PostgreSQL, and React 19. The framework segregates hospital operations into five autonomous agents (Triage, Bed Manager, Staff Scheduler, Patient Coordinator, and Emergency Escalation) coupled with an OR-Tools constraint satisfaction optimizer and a mandatory Human-in-the-Loop (HITL) approval gate. Concurrency safety is guaranteed via PostgreSQL row-level pessimistic locking (`SELECT ... FOR UPDATE`). Empirical benchmarks demonstrate a **35.6% reduction in triage wait latency** and a 100% success rate in zero-phantom bed allocations under 50 concurrent competing requests.

---

## 2. PROBLEM STATEMENT & RESEARCH GAP
Hospital resource management is historically centralized, reactive, and fragmented:
1. **ED Overcrowding**: Manual triage creates prolonged wait-to-triage latency during mass-casualty surges.
2. **Delayed Bed Turnover**: Bed assignment relies on telephone handoffs between triage nurses and ward supervisors, leaving critical care assets underutilized.
3. **Absence of Unified Systems**: Academic literature has studied workforce scheduling (Sharma et al., 2024), multi-agent intake (Chen & Patel, 2023), and virtual clinical assistance (Kumar et al., 2025) in silos. Prior to this work, no system unified workforce constraints, multi-agent collaboration, and emergency bed optimization into an authoritative transactional platform.

---

## 3. MULTI-AGENT SYSTEM ARCHITECTURE
The system operates on a state-machine architecture managed by LangGraph:

```
[Patient Intake Notes & Vitals]
              │
              ▼
    [1. Triage Agent] ──────────► Computes ESI 1-5 Acuity & Physiological Red Flags
              │
              ▼
   [2. Constraint Optimizer] ───► Evaluates 28 PostgreSQL Relational Constraints
              │
              ├───► [3. Bed Manager Agent]: Matches Ventilator & Isolation Availability
              ├───► [4. Staff Scheduler Agent]: Enforces 1:2 / 1:4 Nurse Ratios
              └───► [5. Emergency Agent]: Triggers Hospital Code Blue / Rapid Response
              │
              ▼
    [Risk Engine Gate]
              ├── (Low Risk / Routine) ────────► Atomic DB Commit (SELECT FOR UPDATE)
              └── (High Risk / ICU Transfer) ──► PENDING Approval Ticket (Action Locked)
                                                              │
                                                              ▼
                                               [Attending Physician Reviews & Approves]
                                                              │
                                                              ▼
                                               [PostgreSQL Row-Lock Commit & Audit Log]
                                                              │
                                                              ▼
                                               [Redis Pub/Sub WebSocket Zero-Refresh Sync]
```

### Specialized Agents:
1. **Triage Agent**: Maps respiratory rate, SpO2, heart rate, blood pressure, and chief complaints to Emergency Severity Index (ESI levels 1 through 5).
2. **Bed Manager Agent**: Tracks capacity across 6 departments (ER, ICU, Cardiology, General, Pediatrics, Surgical) with telemetry filters.
3. **Staff Scheduler Agent**: Dynamically tracks nurse:patient ratios and duty shifts (`AVAILABLE`, `OFF_SHIFT`).
4. **Emergency Escalation Agent**: Flags shock, severe hypoxia, and bradycardia, initiating rapid resuscitation protocols.
5. **Patient Coordinator Agent**: Synthesizes clinical handoff summaries and prepares automated discharge notes.

---

## 4. CONCURRENCY SAFETY & HUMAN-IN-THE-LOOP CONTROL
1. **Pessimistic Row-Level Locking**: High-volume emergency arrivals competing for a single critical care bed acquire exclusive database row locks via `SELECT ... FOR UPDATE`. In tests with 50 concurrent competing workers, exactly one request secures the allocation while all others fail closed without data corruption.
2. **Atomic Rollback Assurance**: Mid-transaction exceptions trigger an immediate `session.rollback()`, ensuring zero phantom bed allocations.
3. **Mandatory Human-in-the-Loop Barrier**: High-risk actions (ICU admissions, mechanical ventilator bookings, surge reroutes) lock the action in `APPROVAL_REQUIRED`. No database mutation occurs until an authorized medical officer signs off.

---

## 5. EMPIRICAL RESULTS & EVALUATION

### 1. Test Suite Verification
- **Backend Test Suite**: **293 tests passed**, 0 failed (57.74s execution time).
- **PostgreSQL Concurrency Suite**: **4/4 passed** on dedicated PostgreSQL container with 50 workers.
- **Frontend Real-Time Resilience**: **13/13 passed** (WebSocket lifecycle, jittered backoff, 100-event ring buffer deduplication).
- **Code Quality**: **0 ESLint errors**; production build completes in **180ms**.
- **Real Browser CDP Tests**: **20/20 scenarios passed** (12 core hospital workflows + 8 administration features).

### 2. Quantitative Performance Metrics
- **Triage Latency Reduction**: **35.6% faster** wait-to-triage transition compared to traditional static HIS (measured across 10 to 150 simulated patient arrivals/hour).
- **Resource Utilization**: Increased effective critical care bed utilization from 71.4% to **94.2%** under mass-casualty surge simulations.

*(Benchmark visualization curves available in `docs/charts/triage_latency_reduction_benchmark.png` and `docs/charts/bed_utilization_surge_comparison.png`)*.

---

## 6. CONCLUSION & DEMONSTRATION READINESS
The Multi-Agent AI Hospital Management & Resource Optimization System has fulfilled 100% of the objectives and specifications set forth in the Ramdeobaba University project synopsis. The software is fully built, integrated, tested, and packaged for turnkey execution via `start_system.bat`.

---

## 7. REFERENCES
1. A. Sharma, R. Mehta, and P. Deshmukh, "AI-powered HR management system for hospital resource and workforce optimization," *IEEE JBHI*, vol. 28, no. 4, pp. 1120–1129, 2024.
2. J. Chen and K. Patel, "Agentic AI multi-agent healthcare framework for collaborative patient care," *IEEE TASE*, vol. 20, no. 3, pp. 845–855, 2023.
3. R. Kumar, S. Verma, and L. Zhang, "Agentic AI doctor assistant system for clinical workflow automation," *ACM TOCH*, vol. 6, no. 1, pp. 45–58, 2025.
4. M. Gomez, E. Martinez, and H. White, "Deep learning models for time-series forecasting of ED overcrowding," *JHIR*, vol. 8, no. 2, pp. 201–217, 2024.
