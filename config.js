/**
 * SkillMe — Global API Configuration
 * Auto-detects whether we're running locally or on production.
 * 
 * Production points to Google Cloud Run.
 */

(function() {
  const PROD_API_URL = 'https://skill-me-855405842571.asia-south2.run.app';  // Live GCP
  const LOCAL_URL  = 'http://' + window.location.hostname + ':8000';

  const isLocal = (
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1' ||
    window.location.hostname.startsWith('192.168.')
  );

  // Auto-detect local vs production API
  window.SKILLME_API      = isLocal ? LOCAL_URL : PROD_API_URL;
  window.SKILLME_FRONTEND = window.location.origin;
})();
