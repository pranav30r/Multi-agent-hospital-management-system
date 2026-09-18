import { useState } from "react";
import { createPatient } from "../api/patients.js";
import { createEncounter } from "../api/patients.js";

function PatientIntakeForm() {
  const [isOpen, setIsOpen] = useState(false);
  const [step, setStep] = useState(1); // 1 = patient registration, 2 = encounter vitals
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [createdPatientId, setCreatedPatientId] = useState(null);

  // Step 1: Patient Registration fields
  const [patientData, setPatientData] = useState({
    first_name: "",
    last_name: "",
    age: "",
    gender: "M",
    blood_group: "O+",
    contact_phone: "",
    emergency_contact: "",
  });

  // Step 2: Encounter / Vitals fields
  const [encounterData, setEncounterData] = useState({
    chief_complaint: "",
    encounter_type: "EMERGENCY",
    current_department_id: "DEP-ER",
    heart_rate: "",
    bp_systolic: "",
    bp_diastolic: "",
    spo2: "",
    temperature_f: "",
    pain_level: "",
    respiratory_rate: "",
  });

  const handlePatientChange = (e) => {
    const { name, value } = e.target;
    setPatientData((prev) => ({ ...prev, [name]: value }));
  };

  const handleEncounterChange = (e) => {
    const { name, value } = e.target;
    setEncounterData((prev) => ({ ...prev, [name]: value }));
  };

  const resetForm = () => {
    setStep(1);
    setCreatedPatientId(null);
    setError(null);
    setSuccess(null);
    setPatientData({
      first_name: "", last_name: "", age: "", gender: "M",
      blood_group: "O+", contact_phone: "", emergency_contact: "",
    });
    setEncounterData({
      chief_complaint: "", encounter_type: "EMERGENCY", current_department_id: "DEP-ER",
      heart_rate: "", bp_systolic: "", bp_diastolic: "", spo2: "",
      temperature_f: "", pain_level: "", respiratory_rate: "",
    });
  };

  const handleRegisterPatient = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      const payload = {
        first_name: patientData.first_name.trim(),
        last_name: patientData.last_name.trim(),
        age: parseInt(patientData.age, 10),
        gender: patientData.gender,
        blood_group: patientData.blood_group,
        contact_phone: patientData.contact_phone.trim(),
        emergency_contact: patientData.emergency_contact.trim(),
      };
      const result = await createPatient(payload);
      setCreatedPatientId(result.id);
      setStep(2);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleCreateEncounter = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      // Parse temperature in Fahrenheit directly
      const tempF = encounterData.temperature_f ? parseFloat(encounterData.temperature_f) : undefined;

      const payload = {
        patient_id: createdPatientId,
        chief_complaint: encounterData.chief_complaint.trim(),
        encounter_type: encounterData.encounter_type,
        current_department_id: encounterData.current_department_id || undefined,
        heart_rate: encounterData.heart_rate ? parseInt(encounterData.heart_rate, 10) : undefined,
        bp_systolic: encounterData.bp_systolic ? parseInt(encounterData.bp_systolic, 10) : undefined,
        bp_diastolic: encounterData.bp_diastolic ? parseInt(encounterData.bp_diastolic, 10) : undefined,
        spo2: encounterData.spo2 ? parseInt(encounterData.spo2, 10) : undefined,
        temperature_f: tempF !== undefined && !isNaN(tempF) ? Math.round(tempF * 10) / 10 : undefined,
        pain_level: encounterData.pain_level ? parseInt(encounterData.pain_level, 10) : undefined,
        respiratory_rate: encounterData.respiratory_rate ? parseInt(encounterData.respiratory_rate, 10) : undefined,
      };

      // Remove undefined keys so backend doesn't get null-typed fields
      Object.keys(payload).forEach(k => payload[k] === undefined && delete payload[k]);

      await createEncounter(payload);
      setSuccess(`Patient ${createdPatientId} registered and encounter created successfully.`);
      setTimeout(() => {
        resetForm();
        setIsOpen(false);
      }, 2000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="intake-section">
      <h2>Patient Intake</h2>

      <button className="open-form-button" onClick={() => { resetForm(); setIsOpen(true); }}>
        + Add Patient
      </button>

      {isOpen && (
        <div className="modal-overlay">
          <div className="intake-modal">
            {step === 1 ? (
              <>
                <h2>Step 1: Register Patient</h2>

                {error && <p className="error-message">{error}</p>}

                <form className="intake-form" onSubmit={handleRegisterPatient}>
                  <label>
                    First Name
                    <input type="text" name="first_name" value={patientData.first_name}
                      onChange={handlePatientChange} placeholder="John" required />
                  </label>
                  <label>
                    Last Name
                    <input type="text" name="last_name" value={patientData.last_name}
                      onChange={handlePatientChange} placeholder="Doe" required />
                  </label>
                  <label>
                    Age
                    <input type="number" name="age" value={patientData.age}
                      onChange={handlePatientChange} placeholder="45" min="0" max="120" required />
                  </label>
                  <label>
                    Gender
                    <select name="gender" value={patientData.gender} onChange={handlePatientChange}>
                      <option value="M">Male</option>
                      <option value="F">Female</option>
                      <option value="OTHER">Other</option>
                    </select>
                  </label>
                  <label>
                    Blood Group
                    <select name="blood_group" value={patientData.blood_group} onChange={handlePatientChange}>
                      <option>O+</option><option>O-</option>
                      <option>A+</option><option>A-</option>
                      <option>B+</option><option>B-</option>
                      <option>AB+</option><option>AB-</option>
                    </select>
                  </label>
                  <label>
                    Contact Phone
                    <input type="text" name="contact_phone" value={patientData.contact_phone}
                      onChange={handlePatientChange} placeholder="+91-9876543210" required />
                  </label>
                  <label>
                    Emergency Contact
                    <input type="text" name="emergency_contact" value={patientData.emergency_contact}
                      onChange={handlePatientChange} placeholder="+91-9876543211" required />
                  </label>
                  <div className="form-buttons">
                    <button type="submit" disabled={submitting}>
                      {submitting ? "Registering..." : "Register & Continue"}
                    </button>
                    <button type="button" className="clear-button" onClick={() => setIsOpen(false)}>
                      Cancel
                    </button>
                  </div>
                </form>
              </>
            ) : (
              <>
                <h2>Step 2: Clinical Encounter — {createdPatientId}</h2>

                {error && <p className="error-message">{error}</p>}
                {success && <p className="success-message">{success}</p>}

                <form className="intake-form" onSubmit={handleCreateEncounter}>
                  <label>
                    Chief Complaint
                    <input type="text" name="chief_complaint" value={encounterData.chief_complaint}
                      onChange={handleEncounterChange} placeholder="Severe chest pain" required />
                  </label>
                  <label>
                    Department
                    <select name="current_department_id" value={encounterData.current_department_id}
                      onChange={handleEncounterChange}>
                      <option value="DEP-ER">Emergency</option>
                      <option value="DEP-ICU">ICU</option>
                      <option value="DEP-WA">General Ward A</option>
                      <option value="DEP-CAR">Cardiology</option>
                      <option value="DEP-SUR">Surgery</option>
                    </select>
                  </label>
                  <label>
                    Heart Rate (bpm)
                    <input type="number" name="heart_rate" value={encounterData.heart_rate}
                      onChange={handleEncounterChange} placeholder="80" min="30" max="250" />
                  </label>
                  <label>
                    BP Systolic (mmHg)
                    <input type="number" name="bp_systolic" value={encounterData.bp_systolic}
                      onChange={handleEncounterChange} placeholder="120" min="50" max="300" />
                  </label>
                  <label>
                    BP Diastolic (mmHg)
                    <input type="number" name="bp_diastolic" value={encounterData.bp_diastolic}
                      onChange={handleEncounterChange} placeholder="80" min="20" max="200" />
                  </label>
                  <label>
                    SpO₂ (%)
                    <input type="number" name="spo2" value={encounterData.spo2}
                      onChange={handleEncounterChange} placeholder="98" min="50" max="100" />
                  </label>
                  <label>
                    Temperature (°F)
                    <input type="number" step="0.1" name="temperature_f" value={encounterData.temperature_f}
                      onChange={handleEncounterChange} placeholder="98.6" min="85" max="110" />
                  </label>
                  <label>
                    Respiratory Rate (/min)
                    <input type="number" name="respiratory_rate" value={encounterData.respiratory_rate}
                      onChange={handleEncounterChange} placeholder="16" min="5" max="60" />
                  </label>
                  <label>
                    Pain Level (0-10)
                    <input type="number" name="pain_level" value={encounterData.pain_level}
                      onChange={handleEncounterChange} placeholder="5" min="0" max="10" />
                  </label>
                  <div className="form-buttons">
                    <button type="submit" disabled={submitting || !!success}>
                      {submitting ? "Creating Encounter..." : "Create Encounter"}
                    </button>
                    <button type="button" className="clear-button" onClick={() => setIsOpen(false)}>
                      Close
                    </button>
                  </div>
                </form>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

export default PatientIntakeForm;