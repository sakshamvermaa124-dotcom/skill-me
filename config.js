/**
 * SkillMe — Global API Configuration
 * Auto-detects whether we're running locally or on production.
 * 
 * After deploying the backend to Render, replace RENDER_URL with your
 * actual Render service URL (found in Render dashboard).
 */

(function() {
  const RENDER_URL = 'https://skillme-api.onrender.com';  // ← UPDATE after Render deploy
  const LOCAL_URL  = 'http://localhost:8000';

  const isLocal = (
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1' ||
    window.location.hostname.startsWith('192.168.')
  );

  window.SKILLME_API      = isLocal ? LOCAL_URL : RENDER_URL;
  window.SKILLME_FRONTEND = isLocal ? 'http://localhost:8080' : window.location.origin;
})();
