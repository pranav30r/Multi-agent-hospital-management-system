import { AuthProvider, useAuth } from "./context/AuthContext.jsx";
import { EventProvider } from "./context/EventContext.jsx";
import Login from "./components/Login.jsx";
import Header from "./components/Header.jsx";
import EmergencyBanner from "./components/EmergencyBanner.jsx";
import MetricCards from "./components/MetricCards.jsx";
import EmergencyQueue from "./components/EmergencyQueue.jsx";
import BedGrid from "./components/BedGrid.jsx";
import PatientIntakeForm from "./components/PatientIntakeForm.jsx";
import ApprovalsPanel from "./components/ApprovalsPanel.jsx";
import Footer from "./components/Footer.jsx";

function Dashboard() {
  return (
    <EventProvider>
      <Header />
      <EmergencyBanner />
      <MetricCards />
      <EmergencyQueue />
      <BedGrid />
      <PatientIntakeForm />
      <ApprovalsPanel />
      <Footer />
    </EventProvider>
  );
}

function AppContent() {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="login-container">
        <p className="loading">Loading...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Login />;
  }

  return <Dashboard />;
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;