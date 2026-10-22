import { useState } from "react";
import { AuthProvider, useAuth } from "./context/AuthContext.jsx";
import { EventProvider } from "./context/EventContext.jsx";
import { DemoProvider } from "./context/DemoContext.jsx";
import Login from "./components/Login.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Header from "./components/Header.jsx";
import EmergencyBanner from "./components/EmergencyBanner.jsx";
import MetricCards from "./components/MetricCards.jsx";
import EmergencyQueue from "./components/EmergencyQueue.jsx";
import BedGrid from "./components/BedGrid.jsx";
import PatientIntakeForm from "./components/PatientIntakeForm.jsx";
import ApprovalsPanel from "./components/ApprovalsPanel.jsx";
import PrivacyPolicy from "./components/PrivacyPolicy.jsx";
import TermsAndConditions from "./components/TermsAndConditions.jsx";
import NotFound from "./components/NotFound.jsx";
import Footer from "./components/Footer.jsx";
import { CommandPalette } from "./components/CommandPalette.jsx";

// Admin Section Components
import AdminDashboard from "./components/admin/AdminDashboard.jsx";
import AdminUsers from "./components/admin/AdminUsers.jsx";
import AdminBeds from "./components/admin/AdminBeds.jsx";
import AdminAudit from "./components/admin/AdminAudit.jsx";
import AdminAiSettings from "./components/admin/AdminAiSettings.jsx";
import AdminSettings from "./components/admin/AdminSettings.jsx";

function Dashboard() {
  const { user } = useAuth();
  const isAdmin = user && user.role === "ADMINISTRATOR";
  const [activeTab, setActiveTab] = useState("overview");
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [cmdkOpen, setCmdkOpen] = useState(false);
  const [overviewSubView, setOverviewSubView] = useState("all");

  const renderContent = () => {
    // Route guards: redirect non-admins attempting to access admin views
    if (activeTab.startsWith("admin_") && !isAdmin) {
      return (
        <div className="card" style={{ maxWidth: "600px", margin: "40px auto", textAlign: "center", padding: "40px 24px" }}>
          <div className="empty-state-icon-circle" style={{ margin: "0 auto 16px" }}>
            <span style={{ fontSize: "24px" }}>🔒</span>
          </div>
          <h2 style={{ fontSize: "20px", fontWeight: "700", color: "var(--text-primary)", marginBottom: "8px" }}>
            403 Forbidden: Institutional Administrative Access Required
          </h2>
          <p style={{ color: "var(--text-muted)", fontSize: "14px", marginBottom: "20px" }}>
            Your current clinical credential role ({user?.role}) does not have privileges for this administrative module.
          </p>
          <button type="button" className="btn btn-primary" onClick={() => setActiveTab("overview")}>
            Return to Command Center Overview
          </button>
        </div>
      );
    }

    switch (activeTab) {
      case "overview":
        return (
          <div className="tab-pane overview-pane">
            <MetricCards />

            {/* Single clean toolbar row: tabs + button */}
            <div className="command-center-toolbar">
              <div className="switcher-pills">
                <button
                  type="button"
                  className={`switcher-pill ${overviewSubView === "all" ? "active" : ""}`}
                  onClick={() => setOverviewSubView("all")}
                >
                  Complete Operations View
                </button>
                <button
                  type="button"
                  className={`switcher-pill ${overviewSubView === "triage" ? "active" : ""}`}
                  onClick={() => setOverviewSubView("triage")}
                >
                  Triage Queue Focus
                </button>
                <button
                  type="button"
                  className={`switcher-pill ${overviewSubView === "beds" ? "active" : ""}`}
                  onClick={() => setOverviewSubView("beds")}
                >
                  Bed Management Focus
                </button>
              </div>

              <button
                type="button"
                className="btn-quick-intake"
                onClick={() => setActiveTab("intake")}
              >
                + New Patient Intake
              </button>
            </div>

            {(overviewSubView === "all" || overviewSubView === "triage") && (
              <section className="operations-section">
                <EmergencyQueue />
              </section>
            )}

            {(overviewSubView === "all" || overviewSubView === "beds") && (
              <section className="operations-section">
                <BedGrid />
              </section>
            )}

            {overviewSubView === "all" && (
              <section className="operations-section">
                <ApprovalsPanel />
              </section>
            )}
          </div>
        );

      case "beds":
        return (
          <div className="tab-pane">
            <BedGrid />
          </div>
        );

      case "patients":
        return (
          <div className="tab-pane">
            <EmergencyQueue />
          </div>
        );

      case "intake":
        return (
          <div className="tab-pane">
            <PatientIntakeForm onComplete={() => setActiveTab("overview")} />
          </div>
        );

      case "approvals":
        return (
          <div className="tab-pane">
            <ApprovalsPanel />
          </div>
        );

      // Administration Sub-pages
      case "admin_dashboard":
        return (
          <div className="tab-pane">
            <AdminDashboard onNavigateTab={(tab) => setActiveTab(tab)} />
          </div>
        );

      case "admin_users":
        return (
          <div className="tab-pane">
            <AdminUsers />
          </div>
        );

      case "admin_beds":
        return (
          <div className="tab-pane">
            <AdminBeds />
          </div>
        );

      case "admin_audit":
        return (
          <div className="tab-pane">
            <AdminAudit />
          </div>
        );

      case "admin_ai":
        return (
          <div className="tab-pane">
            <AdminAiSettings />
          </div>
        );

      case "admin_settings":
        return (
          <div className="tab-pane">
            <AdminSettings />
          </div>
        );

      case "privacy":
        return (
          <div className="tab-pane">
            <PrivacyPolicy />
          </div>
        );

      case "terms":
        return (
          <div className="tab-pane">
            <TermsAndConditions />
          </div>
        );

      default:
        return (
          <div className="tab-pane">
            <NotFound onGoHome={() => setActiveTab("overview")} />
          </div>
        );
    }
  };

  return (
    <div className="app-layout">
      <Sidebar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        isOpen={mobileSidebarOpen}
        onCloseMobile={() => setMobileSidebarOpen(false)}
        isCollapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
      />

      {mobileSidebarOpen && (
        <div
          className="mobile-backdrop"
          onClick={() => setMobileSidebarOpen(false)}
        />
      )}

      <div className="app-main-content">
        <Header
          activeTab={activeTab}
          onToggleMobile={() => setMobileSidebarOpen((prev) => !prev)}
          onOpenCmdk={() => setCmdkOpen(true)}
        />

        <main className="app-content-body">
          <EmergencyBanner />
          {renderContent()}
        </main>

        <Footer onSelectTab={setActiveTab} />
      </div>

      <CommandPalette
        isOpen={cmdkOpen}
        onClose={() => setCmdkOpen(false)}
        onNavigate={(tab) => setActiveTab(tab)}
      />
    </div>
  );
}

function Main() {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="app-loading-screen">
        <div className="spinner-border" />
        <span className="loading-text">Initializing CITY HOSPITAL Operations Console...</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Login />;
  }

  return (
    <EventProvider>
      <DemoProvider>
        <Dashboard />
      </DemoProvider>
    </EventProvider>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Main />
    </AuthProvider>
  );
}
