import { apiGet, apiPost } from './client.js';

export async function createPatient(data) {
  return apiPost('/patients', data);
}

export async function listActiveEncounters() {
  return apiGet('/patients/encounters/active');
}

export async function createEncounter(data) {
  return apiPost('/patients/encounters', data);
}

export async function getPatient(patientId) {
  return apiGet(`/patients/${patientId}`);
}
