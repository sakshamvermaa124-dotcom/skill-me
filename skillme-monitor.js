/**
 * SkillMe — Frontend Error Tracking SDK
 * 
 * Captures real student errors on every page:
 *   - Uncaught JS errors (window.onerror + unhandledrejection)
 *   - Failed network requests (fetch monkey-patch)
 *   - Slow API responses (>3s warning, >10s critical)
 *   - Session context (student email, page, user agent)
 * 
 * Reports errors to:
 *   1. Sentry (if configured) for rich error tracking
 *   2. POST /api/monitor/errors on the SkillMe backend for the monitoring dashboard
 * 
 * Lightweight (~3KB), non-blocking, batched reporting.
 */
(function() {
  'use strict';

  const API = window.SKILLME_API || 'https://skill-me.onrender.com';
  const FLUSH_INTERVAL = 10000;   // Batch send every 10s
  const MAX_BATCH = 20;           // Max errors per batch
  const SLOW_THRESHOLD = 3000;    // 3s = slow warning
  const CRITICAL_THRESHOLD = 10000; // 10s = critical

  // Generate a session ID for this page visit
  const SESSION_ID = 'ses_' + Math.random().toString(36).substr(2, 9);

  // Get current page name from URL
  const PAGE = (function() {
    const path = window.location.pathname;
    const filename = path.split('/').pop() || 'index.html';
    return filename.endsWith('.html') ? filename : filename + '.html';
  })();

  // Error queue
  let errorQueue = [];
  let studentEmail = null;

  // ── Try to get student email from JWT/cookie ────────────────────────────
  function detectStudentEmail() {
    try {
      // Check if there's a token in cookie or localStorage
      const cookies = document.cookie.split(';');
      for (const cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'skillme_token' && value) {
          try {
            const payload = JSON.parse(atob(value.split('.')[1]));
            if (payload.email) {
              studentEmail = payload.email;
              return;
            }
          } catch(e) {}
        }
      }
      // Also check localStorage for any stored email
      const stored = localStorage.getItem('skillme_email');
      if (stored) studentEmail = stored;
    } catch(e) {}
  }
  detectStudentEmail();

  // ── Queue an error ─────────────────────────────────────────────────────
  function queueError(errorType, message, extra) {
    if (errorQueue.length >= MAX_BATCH * 2) return; // Prevent memory bloat

    const entry = {
      page: PAGE,
      error_type: errorType,
      message: (message || '').substring(0, 2000),
      stack_trace: (extra.stack || '').substring(0, 5000),
      url: window.location.href,
      user_agent: navigator.userAgent,
      student_email: studentEmail,
      session_id: SESSION_ID,
      request_url: extra.requestUrl || null,
      request_status: extra.requestStatus || null,
    };

    errorQueue.push(entry);

    // Immediately flush critical errors
    if (errorType === 'js_error') {
      flushErrors();
    }
  }

  // ── Flush error queue to backend ───────────────────────────────────────
  function flushErrors() {
    if (errorQueue.length === 0) return;

    const batch = errorQueue.splice(0, MAX_BATCH);

    // Send to SkillMe monitoring backend
    try {
      const payload = JSON.stringify({ errors: batch });
      if (navigator.sendBeacon) {
        navigator.sendBeacon(API + '/api/monitor/errors', new Blob([payload], { type: 'application/json' }));
      } else {
        fetch(API + '/api/monitor/errors', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload,
          keepalive: true,
        }).catch(function() {}); // Silently fail
      }
    } catch(e) {}
  }

  // ── Global error handler ───────────────────────────────────────────────
  window.addEventListener('error', function(event) {
    // Ignore errors from Sentry's own scripts or browser extensions
    if (event.filename && (
      event.filename.includes('sentry') ||
      event.filename.includes('extension://') ||
      event.filename.includes('chrome-extension://')
    )) return;

    queueError('js_error', event.message || 'Unknown JS error', {
      stack: event.error ? event.error.stack : (event.filename + ':' + event.lineno + ':' + event.colno),
    });
  });

  // ── Unhandled promise rejections ───────────────────────────────────────
  window.addEventListener('unhandledrejection', function(event) {
    const reason = event.reason;
    const message = reason instanceof Error ? reason.message : String(reason);
    const stack = reason instanceof Error ? reason.stack : '';

    queueError('js_error', 'Unhandled Promise: ' + message, { stack: stack });
  });

  // ── Monkey-patch fetch to detect failed API calls ─────────────────────
  const originalFetch = window.fetch;
  window.fetch = function(url, options) {
    const requestUrl = typeof url === 'string' ? url : (url instanceof Request ? url.url : String(url));
    const startTime = Date.now();

    return originalFetch.apply(this, arguments)
      .then(function(response) {
        const elapsed = Date.now() - startTime;

        // Only monitor API calls (not analytics, CDN, etc.)
        if (requestUrl.includes('/api/') || requestUrl.includes(API)) {
          // Detect failed API responses
          if (response.status >= 500) {
            queueError('network_error', 'API returned ' + response.status + ': ' + requestUrl, {
              requestUrl: requestUrl,
              requestStatus: response.status,
            });
          }

          // Detect slow responses
          if (elapsed > CRITICAL_THRESHOLD) {
            queueError('network_error', 'Critical: API took ' + elapsed + 'ms: ' + requestUrl, {
              requestUrl: requestUrl,
              requestStatus: response.status,
            });
          } else if (elapsed > SLOW_THRESHOLD) {
            queueError('network_error', 'Slow API (' + elapsed + 'ms): ' + requestUrl, {
              requestUrl: requestUrl,
              requestStatus: response.status,
            });
          }
        }

        return response;
      })
      .catch(function(error) {
        // Network failure (offline, CORS, timeout)
        if (requestUrl.includes('/api/') || requestUrl.includes(API)) {
          queueError('network_error', 'Network error on ' + requestUrl + ': ' + error.message, {
            requestUrl: requestUrl,
            stack: error.stack || '',
          });
        }
        throw error;
      });
  };

  // ── Periodic flush ─────────────────────────────────────────────────────
  setInterval(flushErrors, FLUSH_INTERVAL);

  // ── Flush on page unload ───────────────────────────────────────────────
  window.addEventListener('beforeunload', flushErrors);
  document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'hidden') flushErrors();
  });

  // ── Sentry Integration (if loaded) ─────────────────────────────────────
  // Add Sentry SDK via CDN. Users should add their own DSN.
  // This section auto-initializes Sentry if the DSN is provided.
  if (window.SKILLME_SENTRY_DSN) {
    const sentryScript = document.createElement('script');
    sentryScript.src = 'https://browser.sentry-cdn.com/8.0.0/bundle.min.js';
    sentryScript.crossOrigin = 'anonymous';
    sentryScript.onload = function() {
      if (window.Sentry) {
        window.Sentry.init({
          dsn: window.SKILLME_SENTRY_DSN,
          environment: window.location.hostname === 'localhost' ? 'development' : 'production',
          tracesSampleRate: 0.1,
          replaysSessionSampleRate: 0.0,
          replaysOnErrorSampleRate: 0.5,
          beforeSend: function(event) {
            // Add SkillMe context
            event.tags = event.tags || {};
            event.tags.skillme_page = PAGE;
            event.tags.session_id = SESSION_ID;
            if (studentEmail) {
              event.user = { email: studentEmail };
            }
            return event;
          },
        });
        // Set user context if available
        if (studentEmail) {
          window.Sentry.setUser({ email: studentEmail });
        }
      }
    };
    document.head.appendChild(sentryScript);
  }

  // ── Public API for manual error reporting ──────────────────────────────
  window.SkillMeMonitor = {
    reportError: function(message, extra) {
      queueError('ui_interaction', message, extra || {});
    },
    setStudentEmail: function(email) {
      studentEmail = email;
      if (window.Sentry) {
        window.Sentry.setUser({ email: email });
      }
    },
    flush: flushErrors,
  };

})();
