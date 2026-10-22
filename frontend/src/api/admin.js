import { get, patch } from './client.js';

export async function getSystemMetrics() {
  return get('/system/metrics');
}

export async function listStaff() {
  return get('/staff');
}

export async function getStaff(staffId) {
  return get(`/staff/${staffId}`);
}

export async function updateStaffStatus(staffId, status, reason = "Status updated via Admin Portal") {
  return patch(`/staff/${staffId}/status`, { status, reason });
}

export async function updateStaffWorkload(staffId, workload) {
  return patch(`/staff/${staffId}/workload?workload=${encodeURIComponent(workload)}`);
}

export async function listAuditLogs(limit = 100) {
  return get(`/audit?limit=${limit}`);
}

export async function getAuditStats() {
  return get('/audit/stats');
}

// Local mock storage helpers for admin settings that don't have dedicated backend persistence yet
const SETTINGS_KEY = 'medicenter_admin_settings';
const AI_APPROVAL_CONFIG_KEY = 'medicenter_ai_approval_config';
const EXTRA_BEDS_KEY = 'medicenter_extra_beds';
const EXTRA_DEPTS_KEY = 'medicenter_extra_depts';
const EXTRA_STAFF_KEY = 'medicenter_extra_staff';

export function getHospitalSettings() {
  const fallback = {
    hospitalName: 'MEDICENTER Central Hospital',
    facilityCode: 'MC-CENTRAL-01',
    timeZone: 'Asia/Kolkata (IST)',
    emergencyContact: '+91 1800-425-9999',
    notificationEmail: 'ops-alerts@medicenter.hospital',
    autoRefreshIntervalSec: 15,
    enableAuditExport: true,
  };
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
}

export function saveHospitalSettings(settings) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    return true;
  } catch {
    return false;
  }
}

export function getAiApprovalSettings() {
  const fallback = {
    requirePhysicianForIcu: true,
    requirePhysicianForEmergencySurge: true,
    requirePhysicianForVentilator: true,
    riskThresholdHigh: 0.85,
    approvalTimeoutMinutes: 15,
    fallbackActionOnTimeout: 'ESCALATE_TO_CHIEF_RESIDENT',
  };
  try {
    const raw = localStorage.getItem(AI_APPROVAL_CONFIG_KEY);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
}

export function saveAiApprovalSettings(config) {
  try {
    localStorage.setItem(AI_APPROVAL_CONFIG_KEY, JSON.stringify(config));
    return true;
  } catch {
    return false;
  }
}

export function getCustomDepartments() {
  try {
    return JSON.parse(localStorage.getItem(EXTRA_DEPTS_KEY) || '[]');
  } catch {
    return [];
  }
}

export function saveCustomDepartments(depts) {
  localStorage.setItem(EXTRA_DEPTS_KEY, JSON.stringify(depts));
}

export function getCustomBeds() {
  try {
    return JSON.parse(localStorage.getItem(EXTRA_BEDS_KEY) || '[]');
  } catch {
    return [];
  }
}

export function saveCustomBeds(beds) {
  localStorage.setItem(EXTRA_BEDS_KEY, JSON.stringify(beds));
}

export function getCustomStaff() {
  try {
    return JSON.parse(localStorage.getItem(EXTRA_STAFF_KEY) || '[]');
  } catch {
    return [];
  }
}

export function saveCustomStaff(staff) {
  localStorage.setItem(EXTRA_STAFF_KEY, JSON.stringify(staff));
}
