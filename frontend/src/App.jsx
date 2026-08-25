import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import MetricCards from './components/MetricCards';
import BedGrid from './components/BedGrid';
import EmergencyQueue from './components/EmergencyQueue';
import PatientIntakeForm from './components/PatientIntakeForm';
import ApprovalQueue from './components/ApprovalQueue';
import EmergencyModal from './components/EmergencyModal';
import AddDiseaseModal from './components/AddDiseaseModal';
import { api } from './api/client';
import './App.css';

export default function App() {
  const [departments, setDepartments] = useState([]);
  const [beds, setBeds] = useState([]);
  const [encounters, setEncounters] = useState([]);
  const [pendingApprovals, setPendingApprovals] = useState([]);

  const [showIntakeModal, setShowIntakeModal] = useState(false);
  const [showEmergencyModal, setShowEmergencyModal] = useState(false);
  const [showAddDiseaseModal, setShowAddDiseaseModal] = useState(false);

  const loadData = async () => {
    try {
      const [deptsData, bedsData, encsData, apprsData] = await Promise.all([
        api.getDepartments(),
        api.getBeds(),
        api.getActiveEncounters(),
        api.getPendingApprovals()
      ]);
      setDepartments(deptsData);
      setBeds(bedsData);
      setEncounters(encsData);
      setPendingApprovals(apprsData);
    } catch (err) {
      console.error('Failed to load dashboard telemetry data:', err);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 3000); // 3s polling for real-time live updates
    return () => clearInterval(interval);
  }, []);

  const handleIntakeSubmit = async (formData) => {
    try {
      const patient = await api.createPatient({
        first_name: formData.first_name,
        last_name: formData.last_name,
        age: parseInt(formData.age),
        gender: formData.gender,
        blood_group: formData.blood_group,
        contact_phone: formData.contact_phone,
        emergency_contact: formData.emergency_contact
      });

      await api.createEncounter({
        patient_id: patient.id,
        chief_complaint: formData.chief_complaint,
        heart_rate: parseInt(formData.heart_rate),
        bp_systolic: parseInt(formData.bp_systolic),
        bp_diastolic: parseInt(formData.bp_diastolic),
        spo2: parseInt(formData.spo2),
        temperature_f: parseFloat(formData.temperature_f),
        pain_level: parseInt(formData.pain_level)
      });

      setShowIntakeModal(false);
      loadData();
    } catch (err) {
      alert('Intake Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleEmergencySubmit = async (emergencyData) => {
    try {
      await api.declareEmergency(emergencyData);
      setShowEmergencyModal(false);
      alert('🚨 EMERGENCY DECLARED! All emergency agents activated.');
      loadData();
    } catch (err) {
      alert('Emergency Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleAddDiseaseSubmit = async (diseaseData) => {
    try {
      await api.addDisease(diseaseData);
      setShowAddDiseaseModal(false);
      alert(`🦠 Registered disease '${diseaseData.name}' to ICD-10 registry!`);
      loadData();
    } catch (err) {
      alert('Disease Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleConfirmInBed = async (bedId) => {
    try {
      await api.confirmPatientInBed(bedId);
      loadData();
    } catch (err) {
      alert('Bed Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleReviewApproval = async (approvalId, reviewData) => {
    try {
      await api.reviewApproval(approvalId, reviewData);
      loadData();
    } catch (err) {
      alert('Approval Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  return (
    <div className="app-container">
      <Header 
        onOpenEmergency={() => setShowEmergencyModal(true)}
        onOpenIntake={() => setShowIntakeModal(true)}
        onOpenAddDisease={() => setShowAddDiseaseModal(true)}
      />

      <main className="dashboard-main">
        <MetricCards 
          departments={departments}
          activeEncounters={encounters}
          pendingApprovals={pendingApprovals}
        />

        <div className="dashboard-columns">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <EmergencyQueue encounters={encounters} />
            <BedGrid 
              beds={beds} 
              departments={departments} 
              onConfirmInBed={handleConfirmInBed}
            />
          </div>

          <div>
            <ApprovalQueue 
              pendingItems={pendingApprovals} 
              onReview={handleReviewApproval}
            />
          </div>
        </div>
      </main>

      {showIntakeModal && (
        <PatientIntakeForm 
          onClose={() => setShowIntakeModal(false)}
          onSubmit={handleIntakeSubmit}
        />
      )}

      {showEmergencyModal && (
        <EmergencyModal 
          onClose={() => setShowEmergencyModal(false)}
          onSubmit={handleEmergencySubmit}
        />
      )}

      {showAddDiseaseModal && (
        <AddDiseaseModal 
          onClose={() => setShowAddDiseaseModal(false)}
          onSubmit={handleAddDiseaseSubmit}
        />
      )}
    </div>
  );
}
