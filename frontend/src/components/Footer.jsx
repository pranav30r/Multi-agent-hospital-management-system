import { useState } from "react";

function Footer() {
  const [modal, setModal] = useState(null); // 'privacy' | 'terms' | null

  return (
    <footer className="footer">
      <div className="footer-links">
        <button type="button" className="footer-link" onClick={() => setModal("privacy")}>
          Privacy Policy
        </button>
        <span className="footer-divider">|</span>
        <button type="button" className="footer-link" onClick={() => setModal("terms")}>
          Terms of Service
        </button>
      </div>
      <p className="footer-copy">
        Hospital Resource Management System. All clinical rights reserved.
      </p>

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            {modal === "privacy" ? (
              <>
                <h2>Privacy Policy</h2>
                <div className="modal-body">
                  <p>
                    This system complies with HIPAA and applicable data protection standards. Patient Health Information (PHI) is isolated by tenant and encrypted at rest and in transit.
                  </p>
                  <p>
                    Audit logs record all access, modifications, and clinician overrides for compliance tracking. No patient data is shared with external commercial platforms.
                  </p>
                </div>
              </>
            ) : (
              <>
                <h2>Terms of Service</h2>
                <div className="modal-body">
                  <p>
                    This application is an operational decision-support tool for authorized hospital staff only. System recommendations do not replace direct clinical judgment.
                  </p>
                  <p>
                    Unauthorized access, session sharing, or modification of clinical workflow records is prohibited.
                  </p>
                </div>
              </>
            )}
            <div className="modal-actions">
              <button type="button" className="action-btn" onClick={() => setModal(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </footer>
  );
}

export default Footer;
