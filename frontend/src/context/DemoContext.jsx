import { createContext, useContext, useState } from 'react';

const DemoContext = createContext(null);

export const DEMO_DATA = {
  kpis: {
    icuOccupancy: 84,
    icuTrend: '+3.2%',
    erQueue: 14,
    erTrend: '-2',
    pendingDecisions: 4,
    availableBeds: 18,
    totalBeds: 60,
  },
  patients: [
    {
      id: "ENC-9021",
      patient_id: "PAT-00412",
      patient_name: "Aarav Sharma",
      age: 58,
      gender: "M",
      esi_level: 1,
      triage_score: 1,
      chief_complaint: "Acute anterior STEMI, severe diaphoresis, BP 85/50",
      heart_rate: 118,
      spo2: 91,
      bp: "85/50",
      temp: "98.4",
      wait_time_minutes: 4,
      ai_recommendation: "Immediate Cath Lab transfer & invasive arterial line monitor",
      assigned_bed_id: "BED-ICU-001",
      created_at: new Date(Date.now() - 4 * 60000).toISOString(),
    },
    {
      id: "ENC-9022",
      patient_id: "PAT-00413",
      patient_name: "Pooja Deshmukh",
      age: 34,
      gender: "F",
      esi_level: 2,
      triage_score: 2,
      chief_complaint: "Severe acute asthma exacerbation, silent chest, pulsus paradoxus",
      heart_rate: 130,
      spo2: 89,
      bp: "142/90",
      temp: "99.1",
      wait_time_minutes: 8,
      ai_recommendation: "ICU Ventilator standby, IV Magnesium & continuous nebulization",
      assigned_bed_id: "BED-ER-003",
      created_at: new Date(Date.now() - 8 * 60000).toISOString(),
    },
    {
      id: "ENC-9023",
      patient_id: "PAT-00414",
      patient_name: "Rohan Kulkarni",
      age: 26,
      gender: "M",
      esi_level: 2,
      triage_score: 2,
      chief_complaint: "Polytrauma, high-speed motorcycle collision, pelvic instability",
      heart_rate: 122,
      spo2: 95,
      bp: "96/60",
      temp: "97.8",
      wait_time_minutes: 11,
      ai_recommendation: "Trauma Bay 1 immediate allocation, rapid massive transfusion protocol",
      assigned_bed_id: "BED-ER-001",
      created_at: new Date(Date.now() - 11 * 60000).toISOString(),
    },
    {
      id: "ENC-9024",
      patient_id: "PAT-00415",
      patient_name: "Sunita Verma",
      age: 67,
      gender: "F",
      esi_level: 3,
      triage_score: 3,
      chief_complaint: "Diabetic ketoacidosis, blood glucose 480 mg/dL, moderate dehydration",
      heart_rate: 104,
      spo2: 97,
      bp: "115/70",
      temp: "100.2",
      wait_time_minutes: 22,
      ai_recommendation: "Step-Down telemetry bed, regular insulin infusion protocol",
      assigned_bed_id: null,
      created_at: new Date(Date.now() - 22 * 60000).toISOString(),
    },
    {
      id: "ENC-9025",
      patient_id: "PAT-00416",
      patient_name: "Vikram Singhania",
      age: 49,
      gender: "M",
      esi_level: 3,
      triage_score: 3,
      chief_complaint: "Suspected acute appendicitis, right lower quadrant rebound tenderness",
      heart_rate: 88,
      spo2: 99,
      bp: "130/82",
      temp: "101.4",
      wait_time_minutes: 35,
      ai_recommendation: "Surgical consult, IV analgesia & pre-op ultrasound",
      assigned_bed_id: null,
      created_at: new Date(Date.now() - 35 * 60000).toISOString(),
    },
    {
      id: "ENC-9026",
      patient_id: "PAT-00417",
      patient_name: "Meera Nair",
      age: 72,
      gender: "F",
      esi_level: 4,
      triage_score: 4,
      chief_complaint: "Left wrist Colles fracture following ground-level fall, neurovascular intact",
      heart_rate: 76,
      spo2: 98,
      bp: "138/85",
      temp: "98.6",
      wait_time_minutes: 48,
      ai_recommendation: "Orthopedic splinting & outpatient reduction",
      assigned_bed_id: null,
      created_at: new Date(Date.now() - 48 * 60000).toISOString(),
    },
    {
      id: "ENC-9027",
      patient_id: "PAT-00418",
      patient_name: "Karan Patel",
      age: 19,
      gender: "M",
      esi_level: 5,
      triage_score: 5,
      chief_complaint: "Superficial forearm laceration from broken glassware, tetanus booster required",
      heart_rate: 72,
      spo2: 100,
      bp: "120/78",
      temp: "98.2",
      wait_time_minutes: 62,
      ai_recommendation: "Minor procedure suture station & wound irrigation",
      assigned_bed_id: null,
      created_at: new Date(Date.now() - 62 * 60000).toISOString(),
    }
  ],
  approvals: [
    {
      id: "APP-DEMO-01",
      agent_id: "triage_agent",
      action_type: "BED_TRANSFER_CRITICAL",
      risk_level: "HIGH",
      confidence: 0.94,
      patient_id: "PAT-00412",
      patient_name: "Aarav Sharma",
      proposed_action: {
        bed_id: "BED-ICU-001",
        patient_id: "PAT-00412",
        target_department: "DEP-ICU",
      },
      reasoning: "Patient exhibits clinical criteria for cardiogenic shock risk (HR 118, BP 85/50). Automatic escalation requires attending physician approval before locking ICU Bed 001 with active intra-aortic balloon pump prep.",
      created_at: new Date(Date.now() - 5 * 60000).toISOString(),
    },
    {
      id: "APP-DEMO-02",
      agent_id: "bed_agent",
      action_type: "SURGE_DISCHARGE_ACCELERATION",
      risk_level: "MEDIUM",
      confidence: 0.89,
      patient_id: "PAT-00388",
      patient_name: "Gaurav Malhotra",
      proposed_action: {
        bed_id: "BED-GEN-004",
        encounter_id: "ENC-8812",
        transition: "DISCHARGE_READY",
      },
      reasoning: "Clinical indicators stable for >24 hours with oral toleration. Recommending early step-down to release general ward capacity during peak intake surge.",
      created_at: new Date(Date.now() - 14 * 60000).toISOString(),
    },
    {
      id: "APP-DEMO-03",
      agent_id: "emergency_agent",
      action_type: "VENTILATOR_PREEMPTION",
      risk_level: "CRITICAL",
      confidence: 0.96,
      patient_id: "PAT-00413",
      patient_name: "Pooja Deshmukh",
      proposed_action: {
        bed_id: "BED-ICU-003",
        patient_id: "PAT-00413",
        allocation: "MECHANICAL_VENTILATOR",
      },
      reasoning: "Imminent respiratory failure secondary to status asthmaticus. Pre-reserving mechanical ventilator in Negative Pressure Isolation Bay.",
      created_at: new Date(Date.now() - 7 * 60000).toISOString(),
    }
  ]
};

export const DemoProvider = ({ children }) => {
  const [demoMode, setDemoMode] = useState(() => {
    return localStorage.getItem('medicenter_demo_mode') === 'true';
  });
  const [demoState, setDemoState] = useState(DEMO_DATA);

  const toggleDemoMode = () => {
    setDemoMode((prev) => {
      const next = !prev;
      localStorage.setItem('medicenter_demo_mode', String(next));
      window.dispatchEvent(new CustomEvent('demo:changed', { detail: next }));
      return next;
    });
  };

  const updateDemoPatientBed = (patientId, bedId) => {
    setDemoState((prev) => ({
      ...prev,
      patients: (prev.patients || []).map((p) =>
        p.patient_id === patientId || p.id === patientId
          ? { ...p, assigned_bed_id: bedId, current_bed_id: bedId }
          : p
      )
    }));
  };

  return (
    <DemoContext.Provider value={{ demoMode, toggleDemoMode, demoData: demoState, updateDemoPatientBed }}>
      {children}
    </DemoContext.Provider>
  );
};

export const useDemo = () => {
  return useContext(DemoContext) || { demoMode: false, toggleDemoMode: () => {}, demoData: DEMO_DATA, updateDemoPatientBed: () => {} };
};
