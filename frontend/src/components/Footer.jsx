function Footer({ onSelectTab }) {
  const handleNav = (tab) => {
    if (onSelectTab) onSelectTab(tab);
  };

  return (
    <footer className="app-footer">
      <div className="footer-meta">
        <span className="footer-copyright">
          MEDICENTER Clinical Operations &copy; {new Date().getFullYear()}
        </span>
        <span className="footer-separator">&bull;</span>
        <span className="footer-note">
          Clinical decision support system. Requires attending physician oversight.
        </span>
      </div>
      <div className="footer-links">
        <button
          type="button"
          className="footer-nav-link"
          onClick={() => handleNav("privacy")}
        >
          Privacy Policy
        </button>
        <span className="footer-separator">&bull;</span>
        <button
          type="button"
          className="footer-nav-link"
          onClick={() => handleNav("terms")}
        >
          Terms of Service
        </button>
      </div>
    </footer>
  );
}

export default Footer;
