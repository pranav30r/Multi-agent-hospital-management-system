import { useState, useEffect } from "react";
import { listStaff, updateStaffStatus, getCustomStaff, saveCustomStaff } from "../../api/admin.js";

const generateStaffId = () => `STF-${Date.now().toString().slice(-4)}`;

function AdminUsers() {
  const [staffList, setStaffList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("ALL");
  const [updatingId, setUpdatingId] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  // Invite modal state
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [newStaff, setNewStaff] = useState({
    first_name: "",
    last_name: "",
    role: "DOCTOR",
    department_id: "DEP-ER",
    specialization: "Emergency Medicine",
  });

  const fetchStaff = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listStaff();
      const customStaff = getCustomStaff();
      const apiIds = new Set((data || []).map((s) => s.id));
      const nonDuplicateCustom = customStaff.filter((s) => !apiIds.has(s.id));
      setStaffList([...(data || []), ...nonDuplicateCustom]);
    } catch (err) {
      const customStaff = getCustomStaff();
      if (customStaff.length > 0) {
        setStaffList(customStaff);
      } else {
        setError(err.message || "Failed to load hospital personnel");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStaff();
  }, []);

  const handleToggleStatus = async (staff) => {
    setUpdatingId(staff.id);
    const nextStatus = staff.status === "AVAILABLE" ? "OFF_SHIFT" : "AVAILABLE";
    try {
      const customStaff = getCustomStaff();
      const isCustom = customStaff.some((s) => s.id === staff.id);
      if (isCustom) {
        const updatedCustom = customStaff.map((s) => (s.id === staff.id ? { ...s, status: nextStatus } : s));
        saveCustomStaff(updatedCustom);
        setStaffList((prev) => prev.map((s) => (s.id === staff.id ? { ...s, status: nextStatus } : s)));
      } else {
        await updateStaffStatus(staff.id, nextStatus);
        setStaffList((prev) => prev.map((s) => (s.id === staff.id ? { ...s, status: nextStatus } : s)));
      }
      setSuccessMsg(`Status for ${staff.first_name} ${staff.last_name} (${staff.id}) updated to ${nextStatus === "AVAILABLE" ? "On Duty" : "Off Duty"}.`);
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err) {
      setError(err.message || "Failed to update staff status");
    } finally {
      setUpdatingId(null);
    }
  };

  const handleInviteStaff = (e) => {
    e.preventDefault();
    if (!newStaff.first_name.trim() || !newStaff.last_name.trim()) return;

    const staffId = generateStaffId();
    const createdMember = {
      id: staffId,
      first_name: newStaff.first_name.trim(),
      last_name: newStaff.last_name.trim(),
      role: newStaff.role,
      department_id: newStaff.department_id,
      specialization: newStaff.specialization.trim() || formatRole(newStaff.role),
      status: "AVAILABLE",
      current_workload: 0,
      max_workload: newStaff.role === "DOCTOR" ? 8 : 6,
    };

    const existingCustom = getCustomStaff();
    const updated = [createdMember, ...existingCustom];
    saveCustomStaff(updated);
    setStaffList((prev) => [createdMember, ...prev]);

    setSuccessMsg(`Staff member ${createdMember.first_name} ${createdMember.last_name} (${createdMember.id}) enrolled.`);
    setInviteModalOpen(false);
    setNewStaff({
      first_name: "",
      last_name: "",
      role: "DOCTOR",
      department_id: "DEP-ER",
      specialization: "Emergency Medicine",
    });
    setTimeout(() => setSuccessMsg(null), 3500);
  };

  const filteredStaff = staffList.filter((s) => {
    const matchesRole = roleFilter === "ALL" || s.role === roleFilter;
    const nameMatch = `${s.first_name} ${s.last_name} ${s.id} ${s.specialization || ""}`.toLowerCase();
    const matchesSearch = nameMatch.includes(searchQuery.toLowerCase().trim());
    return matchesRole && matchesSearch;
  });

  const roleLabels = {
    DOCTOR: "Doctor",
    CHARGE_NURSE: "Charge Nurse",
    NURSE: "Staff Nurse",
    ADMINISTRATOR: "Hospital Administrator",
    TECHNICIAN: "Lab Technician",
    RECEPTIONIST: "Receptionist",
    TRIAGE_NURSE: "Triage Nurse",
  };

  const departmentLabels = {
    "DEP-ER": "Emergency Department",
    "DEP-ICU": "Intensive Care Unit",
    "DEP-GEN": "General Ward",
    "DEP-SURG": "Surgical Ward",
    "DEP-CARD": "Cardiology",
    "DEP-PED": "Pediatrics",
  };

  const formatRole = (role) => roleLabels[role] || (role ? role.replace(/_/g, " ") : "Clinical Staff");
  const formatDepartment = (deptId) => departmentLabels[deptId] || deptId;

  const roles = [
    { value: "ALL", label: "All Roles" },
    { value: "DOCTOR", label: "Doctor" },
    { value: "CHARGE_NURSE", label: "Charge Nurse" },
    { value: "NURSE", label: "Staff Nurse" },
    { value: "ADMINISTRATOR", label: "Hospital Administrator" },
    { value: "TECHNICIAN", label: "Lab Technician" },
    { value: "RECEPTIONIST", label: "Receptionist" },
  ];

  return (
    <div className="admin-subpage">
      <div className="admin-page-header">
        <div>
          <h2 className="admin-title">Personnel & Role Management</h2>
          <p className="admin-subtitle">
            Authorize clinical roles, monitor duty status, and grant executive access for hospital staff.
          </p>
        </div>

        <button type="button" className="btn btn-primary" onClick={() => setInviteModalOpen(true)}>
          + Invite / Add Staff Member
        </button>
      </div>

      {successMsg && (
        <div className="alert-banner alert-success" role="status">
          <span>{successMsg}</span>
        </div>
      )}

      {error && (
        <div className="alert-banner alert-error" role="alert">
          <span>{error}</span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={fetchStaff} style={{ marginLeft: "auto" }}>
            Retry
          </button>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="admin-filter-bar">
        <div className="search-input-group">
          <span className="search-icon">🔍</span>
          <input
            type="text"
            className="form-input search-input"
            placeholder="Search by staff ID, doctor name, or department..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="custom-select-wrapper inline-select">
          <select
            className="form-select"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
          >
            {roles.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="card">
          <div className="loading-state-card">
            <div className="spinner-border" />
            <span>Retrieving hospital roster...</span>
          </div>
        </div>
      ) : (
        <div className="card admin-table-card">
          <div className="table-responsive">
            <table className="clinical-table">
              <thead>
                <tr>
                  <th>Staff ID</th>
                  <th>Full Name</th>
                  <th>Clinical Role</th>
                  <th>Department</th>
                  <th>Duty Status</th>
                  <th>Workload Capacity</th>
                  <th className="text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredStaff.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-6 text-muted">
                      No staff members match the selected criteria.
                    </td>
                  </tr>
                ) : (
                  filteredStaff.map((staff) => (
                    <tr key={staff.id}>
                      <td className="font-mono text-xs font-semibold">{staff.id}</td>
                      <td>
                        <div className="staff-user-cell">
                          <div>
                            <div className="staff-cell-name">{staff.first_name} {staff.last_name}</div>
                            <span className="staff-cell-spec">{staff.specialization || "Clinical Staff"}</span>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className={`role-badge role-${staff.role.toLowerCase()}`}>
                          {formatRole(staff.role)}
                        </span>
                      </td>
                      <td>
                        <div className="dept-cell">
                          <span className="dept-name">{formatDepartment(staff.department_id)}</span>
                          <span className="dept-code">{staff.department_id}</span>
                        </div>
                      </td>
                      <td>
                        <span className={`status-pill ${staff.status === "AVAILABLE" ? "status-available" : "status-occupied"}`}>
                          {staff.status === "AVAILABLE" ? "On Duty" : "Off Duty"}
                        </span>
                      </td>
                      <td>
                        <div className="workload-bar-wrap">
                          <span className="workload-text">{staff.current_workload} / {staff.max_workload}</span>
                          <div className="workload-progress">
                            <div
                              className="workload-fill"
                              style={{ width: `${Math.min(100, (staff.current_workload / (staff.max_workload || 1)) * 100)}%` }}
                            />
                          </div>
                        </div>
                      </td>
                      <td className="text-right">
                        <button
                          type="button"
                          className="btn btn-outline btn-sm"
                          onClick={() => handleToggleStatus(staff)}
                          disabled={updatingId === staff.id}
                        >
                          {updatingId === staff.id
                            ? "Updating..."
                            : staff.status === "AVAILABLE"
                            ? "Set Off-Duty"
                            : "Set Available"}
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Invite Staff Modal */}
      {inviteModalOpen && (
        <div className="modern-modal-overlay" onClick={() => setInviteModalOpen(false)}>
          <div className="modern-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header-modern">
              <div>
                <h3 className="modal-title">Invite Clinical Staff Member</h3>
                <span className="modal-subtitle">Provision credentials for institutional hospital access</span>
              </div>
              <button type="button" className="btn-close-modal" onClick={() => setInviteModalOpen(false)}>✕</button>
            </div>

            <form
              className="modal-body-modern"
              onSubmit={handleInviteStaff}
            >
              <div className="form-grid-2col">
                <div className="form-group">
                  <label htmlFor="inv_first_name">First Name *</label>
                  <input
                    id="inv_first_name"
                    type="text"
                    className="form-input"
                    value={newStaff.first_name}
                    onChange={(e) => setNewStaff({ ...newStaff, first_name: e.target.value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="inv_last_name">Last Name *</label>
                  <input
                    id="inv_last_name"
                    type="text"
                    className="form-input"
                    value={newStaff.last_name}
                    onChange={(e) => setNewStaff({ ...newStaff, last_name: e.target.value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="inv_role">Assigned Clinical Role *</label>
                  <div className="custom-select-wrapper">
                    <select
                      id="inv_role"
                      className="form-select"
                      value={newStaff.role}
                      onChange={(e) => setNewStaff({ ...newStaff, role: e.target.value })}
                    >
                      <option value="DOCTOR">Attending Physician (Doctor)</option>
                      <option value="CHARGE_NURSE">Charge Nurse</option>
                      <option value="NURSE">Staff Nurse</option>
                      <option value="ADMINISTRATOR">Hospital Administrator</option>
                      <option value="TECHNICIAN">Diagnostic Technician</option>
                      <option value="RECEPTIONIST">Triage Receptionist</option>
                    </select>
                  </div>
                </div>
                <div className="form-group">
                  <label htmlFor="inv_dept">Assigned Ward / Department *</label>
                  <div className="custom-select-wrapper">
                    <select
                      id="inv_dept"
                      className="form-select"
                      value={newStaff.department_id}
                      onChange={(e) => setNewStaff({ ...newStaff, department_id: e.target.value })}
                    >
                      <option value="DEP-ER">Emergency Department (DEP-ER)</option>
                      <option value="DEP-ICU">Intensive Care Unit (DEP-ICU)</option>
                      <option value="DEP-GEN">General Ward (DEP-GEN)</option>
                      <option value="DEP-PED">Pediatric Ward (DEP-PED)</option>
                    </select>
                  </div>
                </div>
              </div>

              <div className="modal-actions-footer">
                <button type="button" className="btn btn-ghost" onClick={() => setInviteModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Dispatch Credential Invite
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default AdminUsers;
