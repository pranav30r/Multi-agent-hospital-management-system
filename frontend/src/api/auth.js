import { apiPost, apiGet } from './client.js';

export async function login(staffId, password) {
  return apiPost('/auth/login', { staff_id: staffId, password });
}

export async function getMe() {
  return apiGet('/auth/me');
}
