import { apiGet, apiPost } from './client.js';

export async function listActiveEmergencies() {
  return apiGet('/emergencies/active');
}

export async function declareEmergency(data) {
  return apiPost('/emergencies/declare', data);
}

export async function resolveEmergency(emergencyId) {
  return apiPost(`/emergencies/${emergencyId}/resolve`);
}
