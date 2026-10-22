import { useState } from 'react';

function TermsAndConditions() {
  const [activeSection, setActiveSection] = useState('clinical-responsibility');

  const scrollTo = (id) => {
    setActiveSection(id);
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="card legal-page-card">
      <div className="legal-header">
        <h2 className="legal-title">Terms of Service</h2>
        <p className="legal-subtitle">
          Operational terms and clinician responsibilities.
        </p>
      </div>

      <div className="legal-layout-grid">
        <aside className="legal-toc">
          <span className="toc-title">TABLE OF CONTENTS</span>
          <button
            type="button"
            className={`toc-link ${activeSection === 'clinical-responsibility' ? 'active' : ''}`}
            onClick={() => scrollTo('clinical-responsibility')}
          >
            1. Attending Clinician Responsibility
          </button>
          <button
            type="button"
            className={`toc-link ${activeSection === 'credential-usage' ? 'active' : ''}`}
            onClick={() => scrollTo('credential-usage')}
          >
            2. Institutional Credential Use
          </button>
          <button
            type="button"
            className={`toc-link ${activeSection === 'emergency-override' ? 'active' : ''}`}
            onClick={() => scrollTo('emergency-override')}
          >
            3. Manual Emergency Override
          </button>
          <button
            type="button"
            className={`toc-link ${activeSection === 'system-availability' ? 'active' : ''}`}
            onClick={() => scrollTo('system-availability')}
          >
            4. Service Level & Fallbacks
          </button>
        </aside>

        <article className="legal-body">
          <section id="clinical-responsibility" className="legal-section">
            <h3>1. Attending Clinician Responsibility</h3>
            <p>
              The CITY HOSPITAL platform provides clinical decision support tools. All automated predictions, ESI acuity classifications, and bed allocations constitute recommendations only.
            </p>
            <p>
              The attending physician, triage officer, or charge nurse retains full and exclusive responsibility for patient care decisions, triage confirmation, and medication administration.
            </p>
          </section>

          <section id="credential-usage" className="legal-section">
            <h3>2. Institutional Credential Use</h3>
            <p>
              Staff accounts (including DOC-001, ADM-001, and nursing credentials) are assigned individually. Sharing of authentication tokens, passwords, or session IDs constitutes a severe breach of hospital compliance.
            </p>
          </section>

          <section id="emergency-override" className="legal-section">
            <h3>3. Manual Emergency Override Protocol</h3>
            <p>
              In mass-casualty or code-blue incidents, clinical supervisors possess immediate authority to execute manual bed assignments and bypass automated multi-agent constraints. All manual overrides are flagged for post-incident review.
            </p>
          </section>

          <section id="system-availability" className="legal-section">
            <h3>4. Service Level & Fallbacks</h3>
            <p>
              The platform guarantees 99.9% uptime for core triage services. In the event of network disruption or database failover, local paper-based disaster triage procedures must be initiated immediately.
            </p>
          </section>
        </article>
      </div>
    </div>
  );
}

export default TermsAndConditions;
