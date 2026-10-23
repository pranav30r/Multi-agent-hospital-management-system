import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { listActiveEncounters, assignEncounterStaff } from '../api/patients.js';
import { listStaff } from '../api/admin.js';
import { listBeds, updateBedStatus, bookBedManual, confirmPatientInBed } from '../api/beds.js';
import { useEvents } from '../context/EventContext.jsx';
import { useDemo } from '../context/DemoContext.jsx';
import { Icon } from './common/Icon.jsx';
import { Drawer } from './common/Components.jsx';
import { getAiRecommendedBed } from '../utils/aiAllocation.js';
import { coordinateHospitalWorkflow, getWorkflowRecommendations } from '../api/intelligence.js';
import { reviewApproval } from '../api/approvals.js';

export { getAiRecommendedBed };

function EmergencyQueue({ onAssignBed }) {
  const { lastEvent } = useEvents();
  const { demoMode, demoData, updateDemoPatientBed } = useDemo();
  const [encounters, setEncounters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterEsi, setFilterEsi] = useState('ALL');
  const [search, setSearch] = useState('');
  const [selectedEncounter, setSelectedEncounter] = useState(null);
  const [bedsList, setBedsList] = useState([]);
  const [selectedBedToAssign, setSelectedBedToAssign] = useState("");
  const [assignLoading, setAssignLoading] = useState(false);
  const [rowLoadingId, setRowLoadingId] = useState(null);
  const [assignSuccess, setAssignSuccess] = useState(null);
  const [assignError, setAssignError] = useState(null);
  const [bannerNotice, setBannerNotice] = useState(null);
  const [showManualOverride, setShowManualOverride] = useState(false);
  const [allocationReason, setAllocationReason] = useState("Immediate triage admission");
  const [currentTime, setCurrentTime] = useState(0);
  const [workflowResults, setWorkflowResults] = useState({});
  const [staffList, setStaffList] = useState([]);
  const [manualDoctorId, setManualDoctorId] = useState('');
  const [manualNurseId, setManualNurseId] = useState('');

  const handleGenerateRecommendation = async (enc, forceRecalculate = false) => {
    setAssignLoading(true);
    setRowLoadingId(enc.id);
    setAssignError(null);
    setAssignSuccess(null);
    try {
      if (demoMode) throw new Error("Live workflow recommendations are unavailable in demo mode.");
      const result = await coordinateHospitalWorkflow(enc.id, {
        trigger_reason: forceRecalculate ? "STAFF_REQUESTED_REFRESH" : "FRONTEND_REQUEST",
        force_recalculate: forceRecalculate,
      });
      setWorkflowResults((previous) => ({ ...previous, [enc.id]: result }));
      setAssignSuccess("Coordinated recommendation generated. Review its status and rationale.");
      setSelectedEncounter(enc);
      window.dispatchEvent(new CustomEvent("app:refresh-authoritative"));
    } catch (err) {
      setAssignError(err.message || "Failed to generate coordinated recommendation");
    } finally {
      setAssignLoading(false);
      setRowLoadingId(null);
    }
  };

  const handleRejectAiBed = (enc) => {
    setSelectedEncounter(enc);
    setShowManualOverride(true);
    setAssignError(`Choose an alternative bed for ${enc.patient_name || enc.patient_id}.`);
    if (onAssignBed) onAssignBed(enc);
  };

  const fetchEncounters = useCallback(async () => {
    if (demoMode) {
      setEncounters(demoData.patients);
      setLoading(false);
      return;
    }
    try {
      setError(null);
      const data = await listActiveEncounters();
      const normalizedEncounters = (data || []).map((encounter) => ({
        ...encounter,
        initial_vitals: {
          ...(encounter.initial_vitals || encounter.vitals || {}),
          heart_rate: encounter.heart_rate ?? encounter.initial_vitals?.heart_rate ?? encounter.vitals?.heart_rate,
          spo2: encounter.spo2 ?? encounter.initial_vitals?.spo2 ?? encounter.vitals?.spo2,
          bp_systolic: encounter.bp_systolic ?? encounter.initial_vitals?.bp_systolic ?? encounter.vitals?.bp_systolic,
          bp_diastolic: encounter.bp_diastolic ?? encounter.initial_vitals?.bp_diastolic ?? encounter.vitals?.bp_diastolic,
          temperature_f: encounter.temperature_f ?? encounter.initial_vitals?.temperature_f ?? encounter.vitals?.temperature_f,
          respiratory_rate: encounter.respiratory_rate ?? encounter.initial_vitals?.respiratory_rate ?? encounter.vitals?.respiratory_rate,
          gcs_score: encounter.gcs_score ?? encounter.initial_vitals?.gcs_score ?? encounter.vitals?.gcs_score,
        },
      }));
      setEncounters(normalizedEncounters);
      try {
        const savedRecommendations = await getWorkflowRecommendations(normalizedEncounters.map((encounter) => encounter.id));
        setWorkflowResults((previous) => ({
          ...previous,
          ...Object.fromEntries(savedRecommendations.map((result) => [result.encounter_id, result]))
        }));
      } catch {
        // Keep the encounter list usable if recommendation history is unavailable.
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [demoMode, demoData]);

  const fetchBeds = useCallback(async () => {
    try {
      const beds = await listBeds();
      if (beds && beds.length > 0) {
        setBedsList(beds);
        return;
      }
    } catch {
      // Fallback beds
    }
    setBedsList((prev) => (prev && prev.length > 0 ? prev : [
      { id: "BED-ER-01", department_id: "DEP-ER", bed_type: "EMERGENCY_BAY", status: "AVAILABLE" },
      { id: "BED-ER-02", department_id: "DEP-ER", bed_type: "EMERGENCY_BAY", status: "AVAILABLE" },
      { id: "BED-ICU-01", department_id: "DEP-ICU", bed_type: "ICU_VENTILATOR", status: "AVAILABLE" },
      { id: "BED-ICU-02", department_id: "DEP-ICU", bed_type: "ICU_VENTILATOR", status: "AVAILABLE" },
      { id: "BED-CAR-01", department_id: "DEP-CARD", bed_type: "CARDIAC_MONITOR", status: "AVAILABLE" },
      { id: "BED-GEN-01", department_id: "DEP-GEN", bed_type: "STANDARD_INPATIENT", status: "AVAILABLE" },
    ]));
  }, []);

  const fetchStaff = useCallback(async () => {
    if (demoMode) return;
    try {
      setStaffList(await listStaff());
    } catch {
      setStaffList([]);
    }
  }, [demoMode]);

  const debounceTimerRef = useRef(null);
  const debouncedFetch = useCallback(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      fetchEncounters();
      fetchBeds();
      fetchStaff();
    }, 200);
  }, [fetchEncounters, fetchBeds, fetchStaff]);

  useEffect(() => {
    fetchEncounters();
    fetchBeds();
    fetchStaff();
    setCurrentTime(Date.now());
    const timer = setInterval(() => setCurrentTime(Date.now()), 30000);
    return () => {
      clearInterval(timer);
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [fetchEncounters, fetchBeds, fetchStaff]);

  const handleManualStaffAssignment = async (encounter) => {
    if (!encounter || (!manualDoctorId && !manualNurseId)) return;
    setAssignLoading(true);
    setAssignError(null);
    try {
      await assignEncounterStaff(encounter.id, {
        doctor_id: manualDoctorId || null,
        nurse_id: manualNurseId || null,
      });
      setEncounters((previous) => previous.map((item) => item.id === encounter.id
        ? { ...item, assigned_doctor_id: manualDoctorId || item.assigned_doctor_id, assigned_nurse_id: manualNurseId || item.assigned_nurse_id }
        : item));
      setSelectedEncounter((previous) => previous?.id === encounter.id
        ? { ...previous, assigned_doctor_id: manualDoctorId || previous.assigned_doctor_id, assigned_nurse_id: manualNurseId || previous.assigned_nurse_id }
        : previous);
      setAssignSuccess('Clinician assignment saved. Those clinicians are now reserved for this active patient.');
      setManualDoctorId('');
      setManualNurseId('');
      fetchStaff();
      window.dispatchEvent(new CustomEvent('app:refresh-authoritative'));
    } catch (err) {
      setAssignError(err.message || 'Could not manually assign clinicians');
    } finally {
      setAssignLoading(false);
    }
  };

  useEffect(() => {
    if (selectedEncounter) {
      setAssignSuccess(null);
      setAssignError(null);
      setShowManualOverride(false);
      const avail = (bedsList || []).filter((b) => b.status === "AVAILABLE");
      if (avail.length > 0) {
        setSelectedBedToAssign(avail[0].id);
      } else if (bedsList && bedsList.length > 0) {
        setSelectedBedToAssign(bedsList[0].id);
      }
    }
  }, [selectedEncounter, bedsList]);

  const handleApproveAiBed = async (enc, proposedBedId) => {
    if (!demoMode) return handleGenerateRecommendation(enc);
    if (!enc || !proposedBedId) return;
    setAssignLoading(true);
    setRowLoadingId(enc.id);
    setAssignError(null);
    setAssignSuccess(null);
    try {
      if (!demoMode) {
        try {
          await bookBedManual({
            bed_id: proposedBedId,
            encounter_id: enc.id,
            patient_id: enc.patient_id,
            reason: `Clinician approved AI allocation (${enc.ai_recommendation || 'Emergency Triage'})`,
          });
          try {
            await confirmPatientInBed(proposedBedId);
          } catch {
            await updateBedStatus(
              proposedBedId,
              "OCCUPIED",
              `Allocated to ${enc.patient_name || enc.patient_id} (AI Recommendation Approved)`,
              enc.patient_id,
              enc.id
            );
          }
        } catch {
          // Direct occupancy update
          await updateBedStatus(
            proposedBedId,
            "OCCUPIED",
            `Allocated to ${enc.patient_name || enc.patient_id} (AI Recommendation Approved)`,
            enc.patient_id,
            enc.id
          );
        }
      } else if (updateDemoPatientBed) {
        updateDemoPatientBed(enc.patient_id || enc.id, proposedBedId);
      }

      setEncounters((prev) =>
        prev.map((e) =>
          e.id === enc.id || e.patient_id === enc.patient_id
            ? { ...e, assigned_bed_id: proposedBedId, current_bed_id: proposedBedId }
            : e
        )
      );

      setBedsList((prev) =>
        prev.map((b) =>
          b.id === proposedBedId
            ? {
                ...b,
                status: "OCCUPIED",
                current_patient_id: enc.patient_id,
                current_encounter_id: enc.id,
              }
            : b
        )
      );

      if (selectedEncounter && (selectedEncounter.id === enc.id || selectedEncounter.patient_id === enc.patient_id)) {
        setSelectedEncounter((prev) => ({ ...prev, assigned_bed_id: proposedBedId, current_bed_id: proposedBedId }));
      }

      const successMsg = `Bed ${proposedBedId} allocated to ${enc.patient_name || enc.patient_id}`;
      setAssignSuccess(`✓ ${successMsg}`);
      setBannerNotice({
        type: "success",
        message: `✓ AI Recommendation Approved: ${successMsg}`,
      });

      window.dispatchEvent(
        new CustomEvent("bed:updated", {
          detail: {
            bedId: proposedBedId,
            status: "OCCUPIED",
            patientId: enc.patient_id,
            encounterId: enc.id,
            patientName: enc.patient_name,
          },
        })
      );
      window.dispatchEvent(new CustomEvent("patient:updated"));
      setTimeout(() => setBannerNotice(null), 4000);
      setTimeout(() => setAssignSuccess(null), 3500);
    } catch (err) {
      const errMsg = err.message || "Failed to approve AI bed allocation";
      setAssignError(errMsg);
      setBannerNotice({
        type: "error",
        message: `Allocation failed: ${errMsg}`,
      });
      setTimeout(() => setBannerNotice(null), 5000);
    } finally {
      setAssignLoading(false);
      setRowLoadingId(null);
    }
  };

  const handleWorkflowDecision = async (enc, action) => {
    const workflow = workflowResults[enc.id];
    const recommendation = workflow?.recommendation;
    const approvalId = recommendation?.approval_item_id;
    const bedId = recommendation?.recommended_bed_id;
    if (!approvalId || !bedId) {
      setAssignError("This recommendation has no pending bed approval. Refresh the workflow or review the Approvals panel.");
      return;
    }

    setAssignLoading(true);
    setRowLoadingId(enc.id);
    setAssignError(null);
    setAssignSuccess(null);
    try {
      await reviewApproval(approvalId, action === "APPROVE"
        ? { action }
        : { action, rejection_reason: "Clinician declined the recommended bed allocation." });

      if (action === "APPROVE") {
        let bedStatus = "RESERVED";
        let arrivalError = null;
        try {
          await confirmPatientInBed(bedId);
          bedStatus = "OCCUPIED";
        } catch (err) {
          arrivalError = err.message || "Patient arrival could not be confirmed.";
        }
        setEncounters((previous) => previous.map((item) => item.id === enc.id
          ? {
              ...item,
              assigned_bed_id: bedStatus === "OCCUPIED" ? bedId : (item.assigned_bed_id || item.current_bed_id || bedId),
              current_bed_id: bedStatus === "OCCUPIED" ? bedId : (item.current_bed_id || bedId),
            }
          : item));
        setBedsList((previous) => previous.map((bed) => bed.id === bedId
          ? { ...bed, status: bedStatus, current_patient_id: enc.patient_id, current_encounter_id: enc.id }
          : bed));
        setWorkflowResults((previous) => ({
          ...previous,
          [enc.id]: { ...workflow, workflow_status: "ALLOCATED", approval_status: "APPROVED" }
        }));
        setAssignSuccess(bedStatus === "OCCUPIED"
          ? `Bed ${bedId} approved and marked occupied.`
          : `Bed ${bedId} approved and reserved.`);
        setBannerNotice({
          type: arrivalError ? "error" : "success",
          message: arrivalError
            ? `Bed ${bedId} was approved and reserved, but arrival confirmation failed: ${arrivalError}`
            : `Bed ${bedId} approved and marked occupied.`,
        });
        if (arrivalError) setAssignError(`The recommendation was approved, but bed arrival confirmation failed: ${arrivalError}`);
        window.dispatchEvent(new CustomEvent("bed:updated", {
          detail: { bedId, status: bedStatus, patientId: enc.patient_id, encounterId: enc.id }
        }));
      } else {
        setWorkflowResults((previous) => ({
          ...previous,
          [enc.id]: { ...workflow, workflow_status: "REJECTED", approval_status: "REJECTED" }
        }));
        setAssignSuccess(`Bed recommendation ${bedId} rejected; no bed was allocated.`);
        setBannerNotice({ type: "success", message: `Bed recommendation ${bedId} rejected; no bed was allocated.` });
      }

      window.dispatchEvent(new CustomEvent("app:refresh-authoritative"));
    } catch (err) {
      setAssignError(err.message || `Failed to ${action.toLowerCase()} bed recommendation`);
      setBannerNotice({ type: "error", message: err.message || `Failed to ${action.toLowerCase()} bed recommendation` });
      window.dispatchEvent(new CustomEvent("app:refresh-authoritative"));
    } finally {
      setAssignLoading(false);
      setRowLoadingId(null);
      setTimeout(() => setBannerNotice(null), 5000);
    }
  };

  const handleAssignBed = async (e) => {
    if (e) e.preventDefault();
    if (!selectedBedToAssign || !selectedEncounter) return;
    setAssignLoading(true);
    setAssignError(null);
    setAssignSuccess(null);
    try {
      if (!demoMode) {
        try {
          await updateBedStatus(
            selectedBedToAssign,
            "OCCUPIED",
            `Allocated to ${selectedEncounter.patient_name || selectedEncounter.patient_id} (${allocationReason})`,
            selectedEncounter.patient_id,
            selectedEncounter.id
          );
        } catch (err) {
          console.warn("API update bed note:", err);
        }
      } else if (updateDemoPatientBed) {
        updateDemoPatientBed(selectedEncounter.patient_id || selectedEncounter.id, selectedBedToAssign);
      }

      setEncounters((prev) =>
        prev.map((enc) =>
          enc.id === selectedEncounter.id || enc.patient_id === selectedEncounter.patient_id
            ? { ...enc, assigned_bed_id: selectedBedToAssign, current_bed_id: selectedBedToAssign }
            : enc
        )
      );

      setBedsList((prev) =>
        prev.map((b) =>
          b.id === selectedBedToAssign
            ? {
                ...b,
                status: "OCCUPIED",
                current_patient_id: selectedEncounter.patient_id,
                current_encounter_id: selectedEncounter.id,
              }
            : b
        )
      );

      setSelectedEncounter((prev) => ({
        ...prev,
        assigned_bed_id: selectedBedToAssign,
        current_bed_id: selectedBedToAssign,
      }));

      setAssignSuccess(`Bed ${selectedBedToAssign} successfully assigned!`);
      window.dispatchEvent(
        new CustomEvent("bed:updated", {
          detail: {
            bedId: selectedBedToAssign,
            status: "OCCUPIED",
            patientId: selectedEncounter.patient_id,
            encounterId: selectedEncounter.id,
            patientName: selectedEncounter.patient_name,
          },
        })
      );
      window.dispatchEvent(new CustomEvent("patient:updated"));
      setTimeout(() => setAssignSuccess(null), 3500);
    } catch (err) {
      setAssignError(err.message || "Failed to assign bed");
    } finally {
      setAssignLoading(false);
    }
  };

  const handleDischargeFromBed = async (bedId) => {
    if (!bedId) return;
    setAssignLoading(true);
    try {
      if (!demoMode) {
        await updateBedStatus(bedId, "AVAILABLE", "Patient discharged or moved");
      } else if (updateDemoPatientBed) {
        updateDemoPatientBed(selectedEncounter.patient_id || selectedEncounter.id, null);
      }
      setEncounters((prev) =>
        prev.map((enc) =>
          enc.id === selectedEncounter.id || enc.patient_id === selectedEncounter.patient_id
            ? { ...enc, assigned_bed_id: null, current_bed_id: null }
            : enc
        )
      );
      setBedsList((prev) =>
        prev.map((b) =>
          b.id === bedId
            ? { ...b, status: "AVAILABLE", current_patient_id: null, current_encounter_id: null }
            : b
        )
      );
      setSelectedEncounter((prev) => ({ ...prev, assigned_bed_id: null, current_bed_id: null }));
      setAssignSuccess(`Bed ${bedId} released to available pool.`);
      window.dispatchEvent(
        new CustomEvent("bed:updated", {
          detail: { bedId, status: "AVAILABLE", patientId: null },
        })
      );
      window.dispatchEvent(new CustomEvent("patient:updated"));
      setTimeout(() => setAssignSuccess(null), 3000);
    } catch (err) {
      setAssignError(err.message || "Failed to release bed");
    } finally {
      setAssignLoading(false);
    }
  };



  useEffect(() => {
    if (lastEvent && ['PATIENT_REGISTERED', 'ENCOUNTER_CREATED', 'PATIENT_INTAKE_COMPLETED', 'TRIAGE_UPDATED', 'BED_RESERVED', 'BED_OCCUPIED', 'BED_RELEASED', 'APPROVAL_REQUIRED', 'APPROVAL_DECIDED', 'RECOMMENDATION_GENERATED', 'EMERGENCY_DECLARED', 'EMERGENCY_ESCALATED', 'SYSTEM_CONNECTED'].includes(lastEvent.event_type)) {
      debouncedFetch();
    }
  }, [lastEvent, debouncedFetch]);

  useEffect(() => {
    const handler = () => debouncedFetch();
    window.addEventListener("websocket:reconnected", handler);
    window.addEventListener("app:refresh-authoritative", handler);
    window.addEventListener("app:poll-refresh", handler);
    return () => {
      window.removeEventListener("websocket:reconnected", handler);
      window.removeEventListener("app:refresh-authoritative", handler);
      window.removeEventListener("app:poll-refresh", handler);
    };
  }, [debouncedFetch]);

  const filtered = encounters.filter((enc) => {
    const score = workflowResults[enc.id]?.triage_result?.esi_level || enc.triage_score || enc.esi_level || 3;
    const matchesEsi = filterEsi === 'ALL' || String(score) === filterEsi;
    const hay = `${enc.patient_id} ${enc.patient_name || ''} ${enc.chief_complaint || ''}`.toLowerCase();
    const matchesSearch = hay.includes(search.toLowerCase().trim());
    return matchesEsi && matchesSearch;
  });

  // Distribute unique available beds across waiting triage encounters (zero duplication)
  const proposedBedsMap = useMemo(() => {
    const claimed = new Set();
    encounters.forEach((e) => {
      const assigned = e.assigned_bed_id || e.current_bed_id;
      if (assigned) claimed.add(assigned);
    });

    const mapping = {};
    filtered.forEach((enc) => {
      const assigned = enc.assigned_bed_id || enc.current_bed_id;
      if (assigned) {
        mapping[enc.id] = assigned;
        claimed.add(assigned);
      } else {
        const proposed = getAiRecommendedBed(enc, bedsList, claimed);
        mapping[enc.id] = proposed;
        claimed.add(proposed);
      }
    });
    return mapping;
  }, [filtered, encounters, bedsList]);

  const getEsiBadgeClass = (score) => {
    switch (Number(score)) {
      case 1: return 'esi-resuscitation';
      case 2: return 'esi-emergent';
      case 3: return 'esi-urgent';
      case 4: return 'esi-less-urgent';
      case 5: return 'esi-non-urgent';
      default: return 'esi-urgent';
    }
  };

  const getEsiLabel = (score) => {
    switch (Number(score)) {
      case 1: return 'ESI-1 Resuscitation';
      case 2: return 'ESI-2 Emergent';
      case 3: return 'ESI-3 Urgent';
      case 4: return 'ESI-4 Less Urgent';
      case 5: return 'ESI-5 Non-Urgent';
      default: return `ESI-${score}`;
    }
  };

  return (
    <div className="card triage-queue-card">
      <div className="card-top-bar">
        <div>
          <h2 className="card-heading">Emergency Triage Queue</h2>
          <p className="card-subheading">
            {filtered.length} patients prioritized by Emergency Severity Index (ESI) & hemodynamic risk.
          </p>
        </div>

        <div className="queue-controls">
          <div className="search-input-group compact">
            <Icon name="search" size={14} className="search-icon" />
            <input
              type="text"
              className="form-input search-input"
              placeholder="Search patient, complaint..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          <div className="segmented-control">
            {['ALL', '1', '2', '3', '4', '5'].map((esi) => (
              <button
                key={esi}
                type="button"
                className={`segment-btn ${filterEsi === esi ? 'active' : ''}`}
                onClick={() => setFilterEsi(esi)}
              >
                {esi === 'ALL' ? 'All ESI' : `ESI ${esi}`}
              </button>
            ))}
          </div>
        </div>
      </div>

      {bannerNotice && (
        <div className={`alert-banner alert-${bannerNotice.type}`} role="status" style={{ marginBottom: "16px" }}>
          <span>{bannerNotice.message}</span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setBannerNotice(null)}
            style={{ marginLeft: "auto", padding: "0 6px" }}
          >
            ✕
          </button>
        </div>
      )}

      {loading ? (
        <div className="loading-state-card">
          <div className="spinner-border" />
          <span>Refreshing triage priority scores...</span>
        </div>
      ) : error ? (
        <div className="alert-banner alert-error">
          <span>Failed to load triage queue: {error}</span>
          <button type="button" onClick={fetchEncounters} className="btn btn-secondary btn-sm" style={{ marginLeft: 'auto' }}>
            Retry
          </button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state-card">
          <div className="empty-state-icon-circle">
            <Icon name="check-circle" size={24} />
          </div>
          <h3 className="empty-state-title">No Patients Waiting in Triage</h3>
          <p className="empty-state-description">All incoming clinical encounters have been assigned to treatment bays or discharged.</p>
        </div>
      ) : (
        <div className="table-responsive">
          <table className="clinical-table">
            <thead>
              <tr>
                <th>Acuity Tier</th>
                <th>Patient Details</th>
                <th>Chief Complaint / Presentation</th>
                <th>Vitals Snapshot</th>
                <th>Wait Time</th>
                <th>Coordinated Recommendation</th>
                <th className="text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((enc) => {
                const esi = workflowResults[enc.id]?.triage_result?.esi_level || enc.triage_score || enc.esi_level || 3;
                const vitals = enc.initial_vitals || enc.vitals || {};
                const hr = enc.heart_rate || vitals.heart_rate || '—';
                const spo2 = enc.spo2 || vitals.spo2 || '—';
                const bp = enc.bp || (vitals.bp_systolic ? `${vitals.bp_systolic}/${vitals.bp_diastolic}` : '—');
                const createdTime = enc.created_at ? new Date(enc.created_at).getTime() : 0;
                const waitMins = enc.wait_time_minutes || (createdTime > 0 && currentTime > 0 ? Math.max(1, Math.floor((currentTime - createdTime) / 60000)) : 12);
                const workflow = workflowResults[enc.id];
                const proposedBed = workflow?.recommendation?.recommended_bed_id;

                return (
                  <tr
                    key={enc.id}
                    className={`queue-row ${esi <= 2 ? 'high-acuity-row' : ''}`}
                    onClick={() => setSelectedEncounter(enc)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td>
                      <span className={`esi-acuity-pill ${getEsiBadgeClass(esi)}`}>
                        {getEsiLabel(esi)}
                      </span>
                    </td>
                    <td>
                      <div className="patient-meta-cell">
                        <span className="patient-name-bold">{enc.patient_name || enc.patient_id}</span>
                        <span className="patient-sub-info">
                          {enc.patient_id} • {enc.age ? `${enc.age}y` : ''} {enc.gender || ''}
                        </span>
                      </div>
                    </td>
                    <td className="complaint-cell">
                      <p className="complaint-text">{enc.chief_complaint}</p>
                    </td>
                    <td>
                      <div className="vitals-micro-grid tabular-nums">
                        <span className={`vital-tag ${Number(hr) > 100 ? 'vital-alert' : ''}`}>HR: {hr}</span>
                        <span className={`vital-tag ${Number(spo2) < 94 ? 'vital-alert' : ''}`}>SpO2: {spo2}%</span>
                        <span className="vital-tag">BP: {bp}</span>
                      </div>
                    </td>
                    <td>
                      <span className={`wait-timer-badge tabular-nums ${waitMins > 30 ? 'wait-delayed' : ''}`}>
                        ⏱ {waitMins}m
                      </span>
                    </td>
                    <td>
                      <div className="ai-rec-tag">
                        <Icon name="sparkles" size={13} className="text-primary" />
                        <div className="ai-rec-cell">
                          <span className="ai-rec-text">{workflow ? `${workflow.recommendation?.recommended_department || 'Department pending'}${proposedBed ? ` · Bed ${proposedBed}` : ''}` : 'No coordinated recommendation yet'}</span>
                          {workflow && <span className="ai-target-tag">Doctor: <strong>{workflow.workforce_assessment?.assigned_doctor_id || 'Unavailable'}</strong>{workflow.workforce_assessment?.assigned_nurse_id ? ` · Nurse: ${workflow.workforce_assessment.assigned_nurse_id}` : ''}</span>}
                          {workflow && <span className="ai-target-tag">Status: <strong>{workflow.workflow_status}</strong></span>}
                        </div>
                      </div>
                    </td>
                    <td className="text-right" onClick={(e) => e.stopPropagation()}>
                      {(enc.assigned_bed_id || enc.current_bed_id) && workflow?.approval_status !== "PENDING" ? (
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm assigned-bed-btn"
                          onClick={() => setSelectedEncounter(enc)}
                          title={`Assigned Bed: ${enc.assigned_bed_id || enc.current_bed_id}`}
                        >
                          🛏 {(enc.assigned_bed_id || enc.current_bed_id).replace("BED-", "")}
                        </button>
                      ) : workflow?.recommendation?.recommended_bed_id && workflow.approval_status === "PENDING" ? (
                        <div className="ai-decision-cell" style={{ minWidth: "150px" }}>
                          <button type="button" className="btn btn-primary btn-sm" disabled={assignLoading && rowLoadingId === enc.id} onClick={() => handleWorkflowDecision(enc, "APPROVE")} title="Approve the recommendation and mark the bed occupied">
                            {assignLoading && rowLoadingId === enc.id ? "Processing..." : "Accept & Occupy"}
                          </button>
                          <button type="button" className="btn btn-outline btn-sm" disabled={assignLoading && rowLoadingId === enc.id} onClick={() => handleWorkflowDecision(enc, "REJECT")} title="Reject without allocating the bed">
                            Reject
                          </button>
                        </div>
                      ) : workflow?.approval_status === "APPROVED" ? (
                        <span className="status-pill status-occupied">OCCUPIED</span>
                      ) : workflow?.approval_status === "REJECTED" ? (
                        <span className="status-pill status-occupied">REJECTED</span>
                      ) : (
                        <div className="ai-decision-cell">
                          <button
                            type="button"
                            className="btn btn-primary btn-sm ai-btn-yes"
                            disabled={assignLoading && rowLoadingId === enc.id}
                            onClick={() => handleGenerateRecommendation(enc)}
                            title="Run coordinated agents; route any required allocation approval to clinicians"
                          >
                            {assignLoading && rowLoadingId === enc.id ? 'Analyzing...' : workflow ? 'Refresh recommendation' : 'Run workflow'}
                          </button>
                          <button
                            type="button"
                            className="btn btn-outline btn-sm ai-btn-no"
                            disabled={assignLoading && rowLoadingId === enc.id}
                            onClick={() => handleRejectAiBed(enc)}
                            title="Choose a different bed manually"
                          >
                            Manual
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Patient Detail Drawer */}
      <Drawer
        isOpen={!!selectedEncounter}
        onClose={() => setSelectedEncounter(null)}
        title={`Patient Encounter: ${selectedEncounter?.patient_id}`}
        subtitle={selectedEncounter?.patient_name || "Emergency Department Intake"}
      >
        {selectedEncounter && (() => {
          const selectedProposedBed = proposedBedsMap[selectedEncounter.id] || getAiRecommendedBed(selectedEncounter, bedsList);
          const selectedWorkflow = workflowResults[selectedEncounter.id];
          const selectedRecommendation = selectedWorkflow?.recommendation;
          const assignedElsewhere = new Set(encounters
            .filter((item) => item.id !== selectedEncounter.id)
            .flatMap((item) => [item.assigned_doctor_id, item.assigned_nurse_id])
            .filter(Boolean));
          const availableDoctors = staffList.filter((staff) => staff.role === 'DOCTOR'
            && staff.status === 'AVAILABLE' && staff.current_workload < staff.max_workload
            && (!assignedElsewhere.has(staff.id) || staff.id === selectedEncounter.assigned_doctor_id));
          const availableNurses = staffList.filter((staff) => ['NURSE', 'CHARGE_NURSE'].includes(staff.role)
            && staff.status === 'AVAILABLE' && staff.current_workload < staff.max_workload
            && (!assignedElsewhere.has(staff.id) || staff.id === selectedEncounter.assigned_nurse_id));
          const busyClinicians = staffList.filter((staff) => assignedElsewhere.has(staff.id)
            || staff.status !== 'AVAILABLE' || staff.current_workload >= staff.max_workload);
          return (
          <div className="patient-drawer-content">
            <div className="drawer-section">
              <span className="drawer-label">TRIAGE ASSESSMENT</span>
              <div className={`esi-banner ${getEsiBadgeClass(selectedWorkflow?.triage_result?.esi_level || selectedEncounter.triage_score || selectedEncounter.esi_level || 3)}`}>
                <span className="esi-banner-title">{getEsiLabel(selectedWorkflow?.triage_result?.esi_level || selectedEncounter.triage_score || selectedEncounter.esi_level || 3)}</span>
                <span className="esi-banner-desc">Physiologic stability requiring continuous hemodynamic observation</span>
              </div>
            </div>

            <div className="drawer-section">
              <span className="drawer-label">CLINICAL PRESENTATION</span>
              <p className="drawer-text">{selectedEncounter.chief_complaint}</p>
            </div>

            <div className="drawer-section">
              <span className="drawer-label">RECORDED VITALS</span>
              <div className="vitals-detail-grid">
                <div className="vital-box">
                  <span className="v-label">Heart Rate</span>
                  <span className="v-val font-mono">{selectedEncounter.heart_rate || selectedEncounter.initial_vitals?.heart_rate || '—'} bpm</span>
                </div>
                <div className="vital-box">
                  <span className="v-label">SpO2</span>
                  <span className="v-val font-mono">{selectedEncounter.spo2 || selectedEncounter.initial_vitals?.spo2 || '—'} %</span>
                </div>
                <div className="vital-box">
                  <span className="v-label">Blood Pressure</span>
                  <span className="v-val font-mono">{selectedEncounter.bp || `${selectedEncounter.initial_vitals?.bp_systolic || '—'}/${selectedEncounter.initial_vitals?.bp_diastolic || '—'}`}</span>
                </div>
                <div className="vital-box">
                  <span className="v-label">Temperature</span>
                  <span className="v-val font-mono">{selectedEncounter.temp || selectedEncounter.initial_vitals?.temperature_f || '—'} °F</span>
                </div>
              </div>
            </div>

            <div className="drawer-section">
              <span className="drawer-label">MULTI-AGENT DECISION SUPPORT</span>
              <div className="ai-support-box">
                <div className="ai-support-header">
                  <Icon name="sparkles" size={16} color="var(--color-primary)" />
                  <strong>Clinical Rationale Proposal:</strong>
                </div>
                <p className="ai-support-body">
                  {selectedEncounter.ai_recommendation || "Patient symptoms warrant immediate telemetry monitoring and formal assessment by the attending ER physician."}
                </p>

                {demoMode && !(selectedEncounter.assigned_bed_id || selectedEncounter.current_bed_id) && (
                  <div className="ai-drawer-proposal-banner">
                    <div className="ai-drawer-proposal-info">
                      <span className="ai-proposal-label">AI Recommended Bed:</span>
                      <span className="ai-proposal-value">🛏 {selectedProposedBed}</span>
                    </div>
                    <div className="ai-drawer-proposal-actions">
                      <button
                        type="button"
                        className="btn btn-success btn-sm"
                        disabled={assignLoading}
                        onClick={() => handleApproveAiBed(selectedEncounter, selectedProposedBed)}
                        style={{ flex: 1, justifyContent: "center" }}
                      >
                        {assignLoading ? "Assigning..." : `✓ Yes, Approve Bed ${selectedProposedBed}`}
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        onClick={() => setShowManualOverride(true)}
                        style={{ flex: 1, justifyContent: "center" }}
                      >
                        ✕ No, Change Bed
                      </button>
                    </div>
                  </div>
                )}

                <div className="ai-disclaimer-subtle">
                  Operational proposal only. Does not replace physician diagnosis.
                </div>
              </div>
            </div>

            <div className="drawer-section">
              <span className="drawer-label">COORDINATED WORKFLOW RESULT</span>
              {!selectedWorkflow ? (
                <>
                  <p className="drawer-text">No coordinated workflow result is loaded. Run the workflow to see current resource matching and agent rationale.</p>
                  <button type="button" className="btn btn-primary btn-sm" disabled={assignLoading && rowLoadingId === selectedEncounter.id} onClick={() => handleGenerateRecommendation(selectedEncounter)}>
                    {assignLoading && rowLoadingId === selectedEncounter.id ? "Running agents..." : "Generate coordinated recommendation"}
                  </button>
                </>
              ) : (
                <div className="ai-support-box">
                  <span className="status-pill status-reserved">{selectedWorkflow.workflow_status}</span>
                  <p className="ai-support-body"><strong>Approval status:</strong> {selectedWorkflow.approval_status}</p>
                  <p className="ai-support-body"><strong>Recommended department:</strong> {selectedRecommendation?.recommended_department || "Not specified"}</p>
                  <p className="ai-support-body"><strong>Recommended bed:</strong> {selectedRecommendation?.recommended_bed_id || "No compatible bed recommended"}</p>
                  <p className="ai-support-body"><strong>Triage rationale:</strong> {selectedRecommendation?.triage_rationale || selectedWorkflow.triage_result?.rationale || "Not available"}</p>
                  <p className="ai-support-body"><strong>Patient-flow rationale:</strong> {selectedWorkflow.patient_flow_result?.rationale || selectedRecommendation?.patient_flow_action || "Not available"}</p>
                  <p className="ai-support-body"><strong>Workforce rationale:</strong> {selectedWorkflow.workforce_assessment?.rationale || "No staffing rationale returned"}</p>
                  {!!selectedRecommendation?.required_resources?.length && <p className="ai-support-body"><strong>Required resources:</strong> {selectedRecommendation.required_resources.join(", ")}</p>}
                  {!!selectedRecommendation?.candidate_alternatives?.length && <p className="ai-support-body"><strong>Alternatives:</strong> {selectedRecommendation.candidate_alternatives.map((alternative) => alternative.target_bed_id || alternative.bed_id || alternative.description).filter(Boolean).join(", ")}</p>}
                  {!!selectedWorkflow.warnings?.length && <p className="ai-support-body"><strong>Warnings:</strong> {selectedWorkflow.warnings.join("; ")}</p>}
                  {selectedWorkflow.approval_status === "PENDING" && <p className="ai-support-body"><strong>Human review required:</strong> Review approval {selectedRecommendation?.approval_item_id || "in the Approvals panel"}.</p>}
                  <button type="button" className="btn btn-outline btn-sm" disabled={assignLoading && rowLoadingId === selectedEncounter.id} onClick={() => handleGenerateRecommendation(selectedEncounter, true)}>
                    {assignLoading && rowLoadingId === selectedEncounter.id ? "Refreshing..." : "Refresh recommendation"}
                  </button>
                </div>
              )}
            </div>

            {!demoMode && (
              <div className="drawer-section">
                <span className="drawer-label">MANUAL CLINICIAN ASSIGNMENT</span>
                <p className="drawer-text">
                  AI suggestions use clinicians not already assigned to another active patient. Busy clinicians become selectable again after their assignment is cleared.
                </p>
                {busyClinicians.length > 0 && <p className="drawer-text"><strong>Busy / unavailable:</strong> {busyClinicians.map((staff) => `${staff.first_name} ${staff.last_name} (${staff.id})`).join(', ')}. They can be assigned again when their active case is completed or released.</p>}
                <div className="form-grid">
                  <label>
                    Doctor
                    <select value={manualDoctorId} onChange={(event) => setManualDoctorId(event.target.value)}>
                      <option value="">Select available doctor</option>
                      {availableDoctors.map((staff) => <option key={staff.id} value={staff.id}>{staff.first_name} {staff.last_name} ({staff.id})</option>)}
                    </select>
                  </label>
                  <label>
                    Nurse
                    <select value={manualNurseId} onChange={(event) => setManualNurseId(event.target.value)}>
                      <option value="">Select available nurse</option>
                      {availableNurses.map((staff) => <option key={staff.id} value={staff.id}>{staff.first_name} {staff.last_name} ({staff.id})</option>)}
                    </select>
                  </label>
                </div>
                {availableDoctors.length === 0 || availableNurses.length === 0
                  ? <p className="drawer-text">{availableDoctors.length === 0 ? 'No unassigned doctor is currently available. ' : ''}{availableNurses.length === 0 ? 'No unassigned nurse is currently available.' : ''} Review the roster or wait for an active assignment to be released.</p>
                  : null}
                <button type="button" className="btn btn-outline btn-sm" disabled={assignLoading || (!manualDoctorId && !manualNurseId)} onClick={() => handleManualStaffAssignment(selectedEncounter)}>
                  {assignLoading ? 'Saving...' : 'Save manual clinician assignment'}
                </button>
              </div>
            )}

            {/* Bed Allocation Panel */}
            <div className="drawer-section drawer-bed-section">
              <span className="drawer-label">BED ALLOCATION & ADMISSION</span>

              {assignSuccess && (
                <div className="alert-banner alert-success" role="status" style={{ marginBottom: "12px" }}>
                  <span>✓ {assignSuccess}</span>
                </div>
              )}

              {assignError && (
                <div className="alert-banner alert-error" role="alert" style={{ marginBottom: "12px" }}>
                  <span>{assignError}</span>
                </div>
              )}

              {(selectedEncounter.assigned_bed_id || selectedEncounter.current_bed_id) ? (
                <div className="assigned-bed-card">
                  <div className="assigned-bed-info">
                    <span className="assigned-bed-badge">
                      🛏 Assigned Bed: <strong>{selectedEncounter.assigned_bed_id || selectedEncounter.current_bed_id}</strong>
                    </span>
                    <span className="assigned-bed-status">Status: Occupied / Active Care</span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-outline btn-sm"
                    style={{ color: "#dc2626", borderColor: "#fca5a5" }}
                    onClick={() => handleDischargeFromBed(selectedEncounter.assigned_bed_id || selectedEncounter.current_bed_id)}
                    disabled={assignLoading}
                  >
                    {assignLoading ? "Vacating..." : "Vacate / Discharge Bed"}
                  </button>
                </div>
              ) : showManualOverride ? (
                <form onSubmit={handleAssignBed} className="bed-assignment-form">
                  <div className="form-group" style={{ marginBottom: "12px" }}>
                    <label htmlFor="drawer_bed_select" style={{ fontSize: "13px", fontWeight: "600", display: "block", marginBottom: "6px" }}>Select Available Bed</label>
                    <div className="custom-select-wrapper">
                      <select
                        id="drawer_bed_select"
                        className="form-select"
                        value={selectedBedToAssign}
                        onChange={(e) => setSelectedBedToAssign(e.target.value)}
                        required
                      >
                        {bedsList.map((b) => (
                          <option key={b.id} value={b.id}>
                            {b.id} • {b.department_id} ({b.status})
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="form-group" style={{ marginBottom: "16px" }}>
                    <label htmlFor="drawer_assign_reason" style={{ fontSize: "13px", fontWeight: "600", display: "block", marginBottom: "6px" }}>Allocation Rationale</label>
                    <input
                      id="drawer_assign_reason"
                      type="text"
                      className="form-input"
                      value={allocationReason}
                      onChange={(e) => setAllocationReason(e.target.value)}
                      placeholder="e.g. Immediate ICU care requirement"
                    />
                  </div>

                  <div style={{ display: "flex", gap: "8px" }}>
                    <button
                      type="submit"
                      className="btn btn-primary"
                      style={{ flex: 1, justifyContent: "center" }}
                      disabled={assignLoading || !selectedBedToAssign}
                    >
                      {assignLoading ? "Allocating Bed..." : `Assign ${selectedBedToAssign || "Bed"} Manually`}
                    </button>
                    <button
                      type="button"
                      className="btn btn-outline"
                      onClick={() => setShowManualOverride(false)}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              ) : (
                <div style={{ textAlign: "center", padding: "10px 0" }}>
                  <button
                    type="button"
                    className="btn btn-outline btn-sm"
                    style={{ width: "100%", justifyContent: "center" }}
                    onClick={() => setShowManualOverride(true)}
                  >
                    Need an override? Choose Different Bed Manually
                  </button>
                </div>
              )}
            </div>
          </div>
          );
        })()}
      </Drawer>
    </div>
  );
}

export default EmergencyQueue;
