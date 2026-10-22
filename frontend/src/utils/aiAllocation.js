/**
 * Multi-Agent AI Bed Allocation Helper
 * Computes the optimal available bed proposal based on clinical acuity (ESI),
 * patient symptoms, triage recommendations, and live bed inventory.
 */
export function getAiRecommendedBed(enc, beds = [], claimedBedIds = new Set()) {
  if (!enc) return 'BED-ER-01';
  if (enc.assigned_bed_id) return enc.assigned_bed_id;
  if (enc.proposed_bed_id && !claimedBedIds.has(enc.proposed_bed_id)) return enc.proposed_bed_id;
  if (enc.recommended_bed_id && !claimedBedIds.has(enc.recommended_bed_id)) return enc.recommended_bed_id;
  if (enc.target_bed_id && !claimedBedIds.has(enc.target_bed_id)) return enc.target_bed_id;

  const score = Number(enc.triage_score || enc.esi_level || 3);
  const recText = (enc.ai_recommendation || '').toLowerCase();
  const complaint = (enc.chief_complaint || '').toLowerCase();

  const availableBeds = (beds || []).filter(
    (b) => b.status === 'AVAILABLE' && !claimedBedIds.has(b.id)
  );

  // Priority 1: High acuity (ESI 1 or ESI 2 or ICU / Cardiac / Cath lab)
  if (
    score === 1 ||
    recText.includes('cath lab') ||
    recText.includes('icu') ||
    complaint.includes('cardiac') ||
    complaint.includes('arrest') ||
    complaint.includes('stroke')
  ) {
    const icuBed = availableBeds.find((b) => b.department_id === 'DEP-ICU' || b.bed_type === 'ICU_VENTILATOR');
    if (icuBed) return icuBed.id;
    const cardBed = availableBeds.find((b) => b.department_id === 'DEP-CARD' || b.bed_type === 'CARDIAC_MONITOR');
    if (cardBed) return cardBed.id;
    const erBed = availableBeds.find((b) => b.department_id === 'DEP-ER');
    if (erBed) return erBed.id;
  }

  // Priority 2: ESI 2 or Step-down / Telemetry
  if (
    score === 2 ||
    recText.includes('telemetry') ||
    recText.includes('step-down') ||
    complaint.includes('chest pain') ||
    complaint.includes('angina')
  ) {
    const cardBed = availableBeds.find((b) => b.department_id === 'DEP-CARD' || b.bed_type === 'CARDIAC_MONITOR');
    if (cardBed) return cardBed.id;
    const erBed = availableBeds.find((b) => b.department_id === 'DEP-ER');
    if (erBed) return erBed.id;
    const icuBed = availableBeds.find((b) => b.department_id === 'DEP-ICU');
    if (icuBed) return icuBed.id;
  }

  // Priority 3: Standard Inpatient / General / Low Acuity (ESI 4 or 5)
  if (score >= 4) {
    const genBed = availableBeds.find((b) => b.department_id === 'DEP-GEN' || b.bed_type === 'STANDARD_INPATIENT');
    if (genBed) return genBed.id;
    const erBed = availableBeds.find((b) => b.department_id === 'DEP-ER');
    if (erBed) return erBed.id;
  }

  // Priority 4: Urgent / Emergency Bay (ESI 3)
  if (score === 3 || recText.includes('emergency bay') || recText.includes('er bay') || complaint.includes('pain') || complaint.includes('fracture')) {
    const erBed = availableBeds.find((b) => b.department_id === 'DEP-ER' || b.bed_type === 'EMERGENCY_BAY');
    if (erBed) return erBed.id;
    const genBed = availableBeds.find((b) => b.department_id === 'DEP-GEN');
    if (genBed) return genBed.id;
  }

  // Fallback to first available unclaimed bed in facility
  if (availableBeds.length > 0) {
    return availableBeds[0].id;
  }

  const remainingAny = (beds || []).filter((b) => !claimedBedIds.has(b.id));
  if (remainingAny.length > 0) {
    return remainingAny[0].id;
  }

  // Fallback default targets when hospital inventory is currently saturated
  if (score === 1) return 'BED-ICU-01';
  if (score === 2) return 'BED-CAR-01';
  return 'BED-ER-01';
}
