import { apiGet, apiPost } from './client.js';

export async function getRecommendation(encounterId) {
  return apiGet(`/clinical-priority/${encounterId}`);
}

export async function evaluatePriority(encounterId) {
  return apiPost(`/clinical-priority/${encounterId}/evaluate`);
}

export async function acknowledgePriority(encounterId, data) {
  return apiPost(`/clinical-priority/${encounterId}/acknowledge`, data || {});
}

export async function overridePriority(encounterId, data) {
  return apiPost(`/clinical-priority/${encounterId}/override`, data);
}
