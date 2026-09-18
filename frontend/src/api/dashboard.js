import { apiGet } from './client.js';

const HEALTH_URL = import.meta.env.VITE_API_BASE_URL?.replace('/api/v1', '') || 'http://localhost:8000';

export async function getHospitalState() {
  return apiGet('/dashboard/state');
}

export async function getHealth() {
  const res = await fetch(`${HEALTH_URL}/health`);
  if (!res.ok) throw new Error('Health check failed');
  return res.json();
}
