import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { getAiRecommendedBed } from '../utils/aiAllocation.js';

describe('AI Bed Allocation and Decision Recommendation', () => {
  const sampleBeds = [
    { id: 'BED-ER-01', department_id: 'DEP-ER', bed_type: 'EMERGENCY_BAY', status: 'AVAILABLE' },
    { id: 'BED-ER-02', department_id: 'DEP-ER', bed_type: 'EMERGENCY_BAY', status: 'OCCUPIED' },
    { id: 'BED-ICU-01', department_id: 'DEP-ICU', bed_type: 'ICU_VENTILATOR', status: 'OCCUPIED' },
    { id: 'BED-ICU-02', department_id: 'DEP-ICU', bed_type: 'ICU_VENTILATOR', status: 'AVAILABLE' },
    { id: 'BED-CAR-01', department_id: 'DEP-CARD', bed_type: 'CARDIAC_MONITOR', status: 'AVAILABLE' },
    { id: 'BED-GEN-01', department_id: 'DEP-GEN', bed_type: 'STANDARD_INPATIENT', status: 'AVAILABLE' },
  ];

  test('preserves already assigned bed if encounter is already allocated', () => {
    const enc = {
      id: 'ENC-100',
      assigned_bed_id: 'BED-ER-02',
      triage_score: 1,
    };
    const bed = getAiRecommendedBed(enc, sampleBeds);
    assert.equal(bed, 'BED-ER-02');
  });

  test('recommends available ICU ventilator bed for ESI-1 or Cath Lab presentation', () => {
    const enc = {
      id: 'ENC-101',
      triage_score: 1,
      chief_complaint: 'Cardiac arrest resuscitated in field',
      ai_recommendation: 'Immediate Cath Lab transfer and ICU telemetry',
    };
    const bed = getAiRecommendedBed(enc, sampleBeds);
    assert.equal(bed, 'BED-ICU-02', 'Should target the available ICU ventilator bed');
  });

  test('recommends available Cardiac Monitor bed for ESI-2 telemetry presentation', () => {
    const enc = {
      id: 'ENC-102',
      triage_score: 2,
      chief_complaint: 'Crushing chest pain radiating to left jaw',
      ai_recommendation: 'Step-Down telemetry bed with continuous ECG',
    };
    const bed = getAiRecommendedBed(enc, sampleBeds);
    assert.equal(bed, 'BED-CAR-01', 'Should target available cardiac monitor bed');
  });

  test('recommends available Emergency Bay for ESI-3 urgent presentation', () => {
    const enc = {
      id: 'ENC-103',
      triage_score: 3,
      chief_complaint: 'Severe abdominal pain and fever',
      ai_recommendation: 'Assign to Emergency Bay for IV workup',
    };
    const bed = getAiRecommendedBed(enc, sampleBeds);
    assert.equal(bed, 'BED-ER-01', 'Should target available emergency bay');
  });

  test('recommends available General Inpatient bed for ESI-4 or 5 non-critical patients', () => {
    const enc = {
      id: 'ENC-104',
      triage_score: 4,
      chief_complaint: 'Minor distal radius fracture splint check',
      ai_recommendation: 'Outpatient fast-track or standard observation bay',
    };
    const bed = getAiRecommendedBed(enc, sampleBeds);
    assert.equal(bed, 'BED-GEN-01', 'Should target standard inpatient bed');
  });

  test('falls back gracefully to any available bed when preferred unit is full', () => {
    const bedsNoIcu = [
      { id: 'BED-ICU-01', department_id: 'DEP-ICU', bed_type: 'ICU_VENTILATOR', status: 'OCCUPIED' },
      { id: 'BED-GEN-02', department_id: 'DEP-GEN', bed_type: 'STANDARD_INPATIENT', status: 'AVAILABLE' },
    ];
    const enc = {
      id: 'ENC-105',
      triage_score: 1,
      chief_complaint: 'Septic shock',
      ai_recommendation: 'ICU ventilator required',
    };
    const bed = getAiRecommendedBed(enc, bedsNoIcu);
    assert.equal(bed, 'BED-GEN-02', 'Should gracefully select available fallback bed');
  });

  test('simulating Yes (Approval) executes atomic bed assignment and updates state', async () => {
    let bookedBedId = null;

    const mockBookBed = async (payload) => {
      bookedBedId = payload.bed_id;
      return { id: payload.bed_id, status: 'RESERVED' };
    };

    const enc = {
      id: 'ENC-200',
      patient_id: 'PAT-200',
      patient_name: 'Amit Patel',
      triage_score: 2,
    };
    const proposedBed = getAiRecommendedBed(enc, sampleBeds);

    // Doctor clicks "✓ Yes"
    const result = await mockBookBed({
      bed_id: proposedBed,
      encounter_id: enc.id,
      patient_id: enc.patient_id,
      reason: 'Clinician approved AI allocation',
    });

    assert.equal(bookedBedId, 'BED-CAR-01');
    assert.equal(result.status, 'RESERVED');
  });

  test('prevents duplicate bed recommendations across multiple waiting patients in triage queue', () => {
    const queue = [
      { id: 'ENC-301', triage_score: 3, chief_complaint: 'Surgical consult, pre-op' },
      { id: 'ENC-302', triage_score: 3, chief_complaint: 'Orthopedic splinting' },
      { id: 'ENC-303', triage_score: 3, chief_complaint: 'Minor procedure suture station' },
    ];
    const availableErBeds = [
      { id: 'BED-ER-06', department_id: 'DEP-ER', bed_type: 'EMERGENCY_BAY', status: 'AVAILABLE' },
      { id: 'BED-ER-07', department_id: 'DEP-ER', bed_type: 'EMERGENCY_BAY', status: 'AVAILABLE' },
      { id: 'BED-ER-08', department_id: 'DEP-ER', bed_type: 'EMERGENCY_BAY', status: 'AVAILABLE' },
    ];

    const claimed = new Set();
    const allocated = queue.map((enc) => {
      const bed = getAiRecommendedBed(enc, availableErBeds, claimed);
      claimed.add(bed);
      return bed;
    });

    assert.equal(allocated[0], 'BED-ER-06');
    assert.equal(allocated[1], 'BED-ER-07');
    assert.equal(allocated[2], 'BED-ER-08');
    assert.equal(new Set(allocated).size, 3, 'All 3 patients must be proposed distinct beds without collision');
  });
});
