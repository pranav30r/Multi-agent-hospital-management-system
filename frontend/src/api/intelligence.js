import { apiGet, apiPost } from './client.js';

export async function getAssessment(encounterId) {
  return apiGet(`/clinical-intelligence/${encounterId}`);
}

export async function triggerDecision(encounterId, data) {
  return apiPost(`/clinical-intelligence/${encounterId}/decide`, data || {});
}

export async function getMessages(encounterId) {
  return apiGet(`/clinical-intelligence/${encounterId}/messages`);
}

export async function getOptimizationRun(encounterId) {
  return apiGet(`/clinical-intelligence/${encounterId}/optimization-run`);
}

export async function coordinateHospitalWorkflow(encounterId, data) {
  return apiPost(`/clinical-intelligence/${encounterId}/workflow-coordinate`, data || {});
}

export async function getWorkflowRecommendations(encounterIds) {
  if (!encounterIds?.length) return [];
  return apiPost('/clinical-intelligence/workflow-recommendations', encounterIds);
}
export async function getWorkflowState(encounterId) {
  return apiGet(`/clinical-intelligence/${encounterId}/workflow-state`);
}
