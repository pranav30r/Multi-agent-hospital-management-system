# RAMDEOBABA UNIVERSITY
### Department of Computer Science & Engineering

**PROJECT SYNOPSIS**
*Session: 2026–2027 | Semester: 5th | Programme: B.Tech CSE (Honours / Minors / IDEA Lab)*

---

### **Project Title:**
## Multi-Agent AI Systems for Hospital Resource Optimization, Clinical Workflow Automation, and Patient Care Coordination

**Submitted by:**
- [Student 1 Name], Roll No: [Roll No 1]
- [Student 2 Name], Roll No: [Roll No 2]
- [Student 3 Name], Roll No: [Roll No 3]

**Under the Guidance of:**
[Guide Name], [Designation]

**Date of Submission:** 08 / 08 / 2026

---

### **Formatting Guidelines Summary**
| Parameter | Specification |
| :--- | :--- |
| **Font** | Times New Roman |
| **Title** | 16 pt, Bold, Uppercase |
| **Section Headings** | 14 pt, Bold |
| **Body Text** | 12 pt, Regular, 1.5 line spacing |
| **References** | 10 pt, IEEE (Numbered) |
| **Margins** | 1 inch on all sides |

---

## 1. Background and Motivation
Modern healthcare facilities face unprecedented operational pressure driven by unpredictable patient inflows, crowded Emergency Departments (ED), inefficient bed allocation, and delayed ICU transfers. Traditional Hospital Information Systems (HIS) function as static relational databases that rely heavily on manual administrative intervention and fragmented phone/paper communication between department staff. This structural friction results in severe care bottlenecks, extended patient waiting times, clinician burnout, and compromised emergency outcomes.

The advent of **Multi-Agent AI Systems (MAS)** powered by Large Language Models (LLMs) and autonomous decision frameworks offers a transformative paradigm shift. By orchestrating specialized, autonomous AI agents—each acting as a dedicated domain expert (e.g., Triage Specialist, Bed Inventory Manager, Duty Scheduler, Patient Care Coordinator)—hospitals can transition from reactive management to real-time proactive orchestration. Multi-agent negotiation protocols enable these AI entities to continuously exchange data, predict dynamic bottlenecks, and negotiate resource allocation autonomously. Implementing an intelligent multi-agent framework will streamline clinical handoffs, maximize bed utilization, and elevate patient care quality while reducing human administrative overhead.

---

## 2. Problem Statement
Current hospital resource management systems are centralized, reactive, and incapable of dynamic real-time adaptation during peak surges or emergency crises. Clinical workflows are impeded by manual triage, delayed bed updates, and poor cross-departmental coordination, leading to long emergency wait times and underutilized medical assets. There is a critical need for a decentralized Multi-Agent AI ecosystem capable of continuously monitoring patient status, predicting room/ICU demand, automatically negotiating resource assignments, and executing routine clinical task handoffs with minimal human delay.

---

## 3. Objectives
- **Design a Decentralized Multi-Agent Architecture:** Implement a multi-agent framework (using CrewAI / LangGraph) consisting of specialized agents: Triage Agent, Bed Manager Agent, Staff Scheduler Agent, Patient Coordinator Agent, and Emergency Escalation Agent.
- **Automate Dynamic Triage & Risk Stratification:** Utilize Natural Language Processing (NLP/LLM) algorithms to process patient intake notes, assign urgency scores, and route patients to appropriate queues.
- **Implement Intelligent Resource & Bed Allocation:** Develop predictive algorithms for real-time tracking, forecasting bed occupancy, and automating ICU transfer prioritization.
- **Enable Inter-Agent Negotiation Protocols:** Establish asynchronous message-passing protocols allowing agents to negotiate shift coverage, equipment sharing, and discharge workflows autonomously.
- **Develop a Real-Time Clinical Control Dashboard:** Build a responsive web interface for doctors and administrators to visually track live patient flows, agent actions, resource metrics, and manual override controls.

---

## 4. Literature Review and Research Gap

### Literature Summary Table
| Sr. No. | Author(s) & Year | Title / Focus | Methodology / Key Contribution | Limitation / Gap |
| :---: | :--- | :--- | :--- | :--- |
| **1** | A. Sharma et al. (2024) | AI-Driven Hospital Bed Management | Random Forest time-series forecasting for predicting bed turnover. | Lacks dynamic real-time agent collaboration and patient re-routing capabilities. |
| **2** | J. Chen & K. Patel (2023) | Multi-Agent Systems in Healthcare Workflows | Rule-based agent simulation for Emergency Department patient queue management. | Static decision rules without natural language understanding (LLMs). |
| **3** | R. Kumar et al. (2025) | LLM-Based Clinical Task Automation | Fine-tuned LLMs for clinical note summarization and electronic health record parsing. | Operates as a standalone tool without awareness of real-world operational constraints. |
| **4** | M. Gomez et al. (2024) | Predictive Analytics for ED Crowding | Deep Learning (LSTM) for predicting daily patient arrival surges. | Focuses strictly on forecasting without offering automated execution mechanisms. |
| **5** | S. Gupta & V. Nair (2023) | Decentralized Resource Scheduling in Smart Hospitals | Constraint Satisfaction Problem (CSP) solvers for nurse shift scheduling. | High computational complexity; cannot adjust dynamically to emergency influxes. |

### Research Gap
While prior research addresses isolated challenges—such as predictive models for bed occupancy or LLMs for medical note parsing—existing solutions lack an integrated, cooperative **Multi-Agent framework** that combines natural language reasoning with real-time operational constraint satisfaction. Current systems fail to support autonomous inter-agent negotiation for immediate bed reallocation, emergency escalation, and automated discharge handoffs under dynamic hospital conditions.

---

## 5. Proposed Methodology / Plan of Work

```
 +-----------------------------------------------------------------------------------+
 |                               PATIENT INTAKE / EHR                                |
 +-----------------------------------------------------------------------------------+
                                           |
                                           v
 +-----------------------------------------------------------------------------------+
 |                                TRIAGE AI AGENT                                    |
 |                    (NLP/LLM Risk Scoring & Priority Routing)                      |
 +-----------------------------------------------------------------------------------+
                                           |
                   +-----------------------+-----------------------+
                   |                                               |
                   v                                               v
 +-----------------------------------+           +-----------------------------------+
 |     BED MANAGEMENT AI AGENT       |           |   PATIENT CARE COORDINATOR AGENT  |
 | (Real-Time Occupancy & Allocation)|           | (Clinical Task Handoff & Summary) |
 +-----------------------------------+           +-----------------------------------+
                   |                                               |
                   +-----------------------+-----------------------+
                                           |
                                           v
 +-----------------------------------------------------------------------------------+
 |                          STAFF SCHEDULER & ESCALATION AGENTS                      |
 |                 (Resource Negotiation & Emergency ICU Escalation)                 |
 +-----------------------------------------------------------------------------------+
                                           |
                                           v
 +-----------------------------------------------------------------------------------+
 |                     REAL-TIME CLINICAL MANAGEMENT DASHBOARD                       |
 +-----------------------------------------------------------------------------------+
```

1. **System Architecture Setup:** Build a modular framework using **LangGraph / CrewAI** to define autonomous agent personas, tools, and communication state graphs.
2. **Data Pipeline & Simulation Engine:** Synthesize anonymized patient arrival records and hospital resource datasets (beds, ICU units, ventilator status, nurse shifts).
3. **Agent Implementation & Prompt Engineering:**
   - **Triage Agent:** Analyzes symptoms via LLM, computes Emergency Severity Index (ESI 1–5), and queues patients.
   - **Bed Manager Agent:** Queries database state, monitors discharge readiness, and assigns rooms.
   - **Coordinator Agent:** Auto-generates clinical handoff notes, discharge instructions, and follow-up alerts.
   - **Scheduler Agent:** Balances staff workload dynamically when surge thresholds are triggered.
4. **Inter-Agent Communication Layer:** Use an event-driven architecture (Redis / FastAPI WebSockets) to pass structured JSON messages and handle resource negotiation requests between agents.
5. **Dashboard Development:** Create a Next.js / React web interface featuring live system health, room occupancy heatmaps, queue status, and human-in-the-loop intervention panels.

---

## 6. Technology, Tools and Platforms
- **Programming Languages:** Python 3.11+, TypeScript
- **Multi-Agent & AI Frameworks:** LangGraph, CrewAI, OpenAI GPT-4o / Ollama (Llama 3 local inference)
- **Web Frontend:** React.js / Next.js, TailwindCSS, Lucide Icons, Recharts
- **Backend & Database:** FastAPI, PostgreSQL, Redis (Message Broker / State Management)
- **Development Tools:** Git, VS Code, Postman, Docker

---

## 7. Expected Outcomes, Deliverables and Functional Specifications
- **Multi-Agent Engine:** Functional Python-based backend running coordinated autonomous AI agents for triage, bed management, and clinical handoffs.
- **Web-Based Management Control Center:** Interactive real-time dashboard visualizing bed state, triage priority queues, and agent activity logs.
- **Performance Optimization Metrics:** Demonstrated reduction in simulated triage processing times (up to 35%) and improved emergency bed allocation response time.
- **Documentation & Codebase:** Complete clean source code repository, API specs, IEEE format final report, and user demonstration video.

---

## 8. Project Scope
The project focuses on Emergency Department triage automation, dynamic ward/ICU bed allocation, staff duty optimization, and clinical task handoff summaries within a simulated hospital environment. 

*Out of Scope:* Direct automated medical diagnosis or prescription without clinical supervision (regulatory medical device compliance is excluded; system operates strictly as an administrative support assistant).

---

## 9. Project Timeline

| Phase | Duration | Milestone / Deliverable |
| :--- | :--- | :--- |
| **Literature Review & Requirement Analysis** | Weeks 1 – 3 | Complete paper review, finalize system requirements & dataset design. |
| **System Design & Architecture Finalization** | Weeks 4 – 6 | Define multi-agent state graph, communication schema & API contracts. |
| **Implementation & Agent Development** | Weeks 7 – 10 | Build Triage, Bed, and Coordinator agents; integrate FastAPI & Redis. |
| **Testing, Simulation & UI Integration** | Weeks 11 – 13 | Develop Next.js dashboard; conduct load testing & agent response verification. |
| **Documentation & Final Submission** | Weeks 14 – 16 | Finalize project report, user documentation, and prepare presentation/demo. |

---

## 10. References
1. [1] A. Sharma, R. Mehta, and P. Deshmukh, "AI-driven dynamic hospital bed management systems," *IEEE Journal of Biomedical and Health Informatics*, vol. 28, no. 4, pp. 1120–1129, 2024.
2. [2] J. Chen and K. Patel, "Multi-agent systems for emergency department patient triage and queue optimization," *IEEE Transactions on Automation Science and Engineering*, vol. 20, no. 3, pp. 845–855, 2023.
3. [3] R. Kumar, S. Verma, and L. Zhang, "Clinical workflow automation using fine-tuned Large Language Models," *ACM Transactions on Computing for Healthcare*, vol. 6, no. 1, pp. 45–58, 2025.
4. [4] M. Gomez, E. Martinez, and H. White, "Deep learning models for time-series forecasting of emergency department overcrowding," *Journal of Healthcare Informatics Research*, vol. 8, no. 2, pp. 201–217, 2024.
5. [5] S. Gupta and V. Nair, "Decentralized constraint satisfaction algorithms for clinical staff scheduling," *IEEE Systems Journal*, vol. 17, no. 2, pp. 1430–1441, 2023.
6. [6] H. Wang et al., "Survey on Large Language Model based Autonomous Agents in Healthcare," *IEEE Reviews in Biomedical Engineering*, vol. 17, pp. 90–104, 2024.
7. [7] T. Wu et al., "AutoGen: Enabling next-gen LLM applications via multi-agent conversation," *arXiv preprint arXiv:2308.08155*, 2023.
8. [8] M. Wooldridge, *An Introduction to MultiAgent Systems*, 2nd ed. Chichester, UK: John Wiley & Sons, 2009.

---

### **Group Member Details**

| Roll No. | Name and Signature of Student |
| :--- | :--- |
| [Roll No 1] | [Student 1 Name] |
| [Roll No 2] | [Student 2 Name] |
| [Roll No 3] | [Student 3 Name] |

---

### **Approved by:**

\
___________________________ \
**(Name of Guide and Signature)** \
*Project Guide*

\
___________________________ \
*Project Co-Coordinator*

\
___________________________ \
*Project Coordinator*

\
___________________________ \
*Associate Head of Department*

\
___________________________ \
*Dean CSE*

---
*Note: The synopsis must be approved and signed by the project guide before submission. A signed hard copy is to be submitted to the Project Coordinator by the deadline notified for the session.*
