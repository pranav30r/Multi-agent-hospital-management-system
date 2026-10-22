import { useState } from 'react';

function PrivacyPolicy() {
  const [activeSection, setActiveSection] = useState('data-collection');

  const scrollTo = (id) => {
    setActiveSection(id);
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="card legal-page-card">
      <div className="legal-header">
        <h2 className="legal-title">Privacy Policy</h2>
        <p className="legal-subtitle">
          How patient and operational data is handled in MEDICENTER.
        </p>
      </div>

      <div className="legal-layout-grid">
        <aside className="legal-toc">
          <span className="toc-title">TABLE OF CONTENTS</span>
          <button
            type="button"
            className={`toc-link ${activeSection === 'data-collection' ? 'active' : ''}`}
            onClick={() => scrollTo('data-collection')}
          >
            1. Protected Health Information (PHI)
          </button>
          <button
            type="button"
            className={`toc-link ${activeSection === 'multi-agent-use' ? 'active' : ''}`}
            onClick={() => scrollTo('multi-agent-use')}
          >
            2. Multi-Agent AI Model Processing
          </button>
          <button
            type="button"
            className={`toc-link ${activeSection === 'retention' ? 'active' : ''}`}
            onClick={() => scrollTo('retention')}
          >
            3. Cryptographic Storage & Retention
          </button>
          <button
            type="button"
            className={`toc-link ${activeSection === 'audit' ? 'active' : ''}`}
            onClick={() => scrollTo('audit')}
          >
            4. Immutable Audit Provenance
          </button>
          <button
            type="button"
            className={`toc-link ${activeSection === 'rights' ? 'active' : ''}`}
            onClick={() => scrollTo('rights')}
          >
            5. Patient & Clinician Data Rights
          </button>
        </aside>

        <article className="legal-body">
          <section id="data-collection" className="legal-section">
            <h3>1. Protected Health Information (PHI) Collection</h3>
            <p>
              CITY HOSPITAL collects patient demographics, vital signs, clinical triage notes, and attending clinician identifiers exclusively to facilitate safe, rapid emergency resource management and bed allocation within the institution.
            </p>
            <p>
              All identifying attributes (including Contact Phone, Emergency Relative details, and National Health IDs) are encrypted at rest using AES-256-GCM and in transit via TLS 1.3.
            </p>
          </section>

          <section id="multi-agent-use" className="legal-section">
            <h3>2. Multi-Agent AI Model Processing</h3>
            <p>
              Multi-agent algorithms operate strictly on ephemeral, memory-safe data structures. Automated recommendations (e.g. Bed Rerouting, Acuity Scoring, Ventilator Preemption) are purely advisory proposals.
            </p>
            <p>
              No patient data is ever exported to public large language models or external commercial third parties. All decision engines execute locally within the hospital’s sovereign compute boundary.
            </p>
          </section>

          <section id="retention" className="legal-section">
            <h3>3. Cryptographic Storage & Retention</h3>
            <p>
              In accordance with statutory clinical retention directives, encounter records and vital telemetry are preserved for a period of ten (10) years. Deprecated records are securely expunged utilizing DoD 5220.22-M sanitization standards.
            </p>
          </section>

          <section id="audit" className="legal-section">
            <h3>4. Immutable Audit Provenance</h3>
            <p>
              Every access event, patient record modification, AI proposal review, and user authentication timestamp is immutably appended to the system audit ledger. Audit records cannot be modified or truncated by any user or administrator.
            </p>
          </section>

          <section id="rights" className="legal-section">
            <h3>5. Patient & Clinician Data Rights</h3>
            <p>
              Patients maintain the right to inspect their clinical audit trail and request rectification of clerical recording errors through the Office of Medical Records Administration.
            </p>
          </section>
        </article>
      </div>
    </div>
  );
}

export default PrivacyPolicy;
