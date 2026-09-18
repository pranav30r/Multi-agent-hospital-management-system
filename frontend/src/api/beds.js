import { apiGet } from './client.js';

export async function listBeds(departmentId, status) {
  const params = new URLSearchParams();
  if (departmentId) params.set('department_id', departmentId);
  if (status) params.set('bed_status', status);
  const qs = params.toString();
  return apiGet(`/beds${qs ? '?' + qs : ''}`);
}

export async function listDepartments() {
  return apiGet('/departments');
}
