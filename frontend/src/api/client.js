import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const api = {
  // Departments & Beds
  getDepartments: () => apiClient.get('/departments').then(res => res.data),
  getBeds: (deptId = null) => apiClient.get('/beds', { params: { department_id: deptId } }).then(res => res.data),
  bookBedManually: (bookingData) => apiClient.post('/beds/book-manual', bookingData).then(res => res.data),
  confirmPatientInBed: (bedId) => apiClient.post(`/beds/${bedId}/confirm-patient-in-bed`).then(res => res.data),

  // Patients & Encounters
  getPatients: () => apiClient.get('/patients').then(res => res.data),
  createPatient: (patientData) => apiClient.post('/patients', patientData).then(res => res.data),
  createEncounter: (encounterData) => apiClient.post('/patients/encounters', encounterData).then(res => res.data),
  getActiveEncounters: () => apiClient.get('/patients/encounters/active').then(res => res.data),

  // Diseases
  getDiseases: () => apiClient.get('/diseases').then(res => res.data),
  addDisease: (diseaseData) => apiClient.post('/diseases', diseaseData).then(res => res.data),

  // Emergencies
  declareEmergency: (emergencyData) => apiClient.post('/emergencies/declare', emergencyData).then(res => res.data),
  getActiveEmergencies: () => apiClient.get('/emergencies/active').then(res => res.data),
  resolveEmergency: (emergencyId) => apiClient.post(`/emergencies/${emergencyId}/resolve`).then(res => res.data),

  // Approvals
  getPendingApprovals: () => apiClient.get('/approvals/pending').then(res => res.data),
  reviewApproval: (approvalId, reviewData) => apiClient.post(`/approvals/${approvalId}/review`, reviewData).then(res => res.data),
};
