import { apiGet, apiPost } from './client.js';

export async function listPendingApprovals() {
  return apiGet('/approvals/pending');
}

export async function listApprovalHistory() {
  return apiGet('/approvals/history');
}

export async function reviewApproval(approvalId, data) {
  return apiPost(`/approvals/${approvalId}/review`, data);
}
