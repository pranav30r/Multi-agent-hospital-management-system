function NotFound({ onNavigateHome }) {
  return (
    <div className="not-found-container">
      <div className="not-found-card">
        <div className="not-found-code">404</div>
        <h2>Operational Unit Not Found</h2>
        <p className="not-found-message">
          The requested clinical section or resource identifier is not recognized in the hospital operations catalog.
        </p>
        <button type="button" className="btn btn-primary" onClick={onNavigateHome}>
          Return to Operations Command Center
        </button>
      </div>
    </div>
  );
}

export default NotFound;
