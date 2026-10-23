// ============================================================
// SkillMe Student Dashboard - Premium Edition
// Lenis Smooth Scroll + Aurora UI + Glassmorphism
// ============================================================

// API base URL — reads from config.js (auto-detects local vs production)
const API = window.SKILLME_API || '${API}';
// Certificate payment is asked for at the end — 3 of 4 approved tasks (see backend PAYMENT_UNLOCK_TASKS)
const PAYMENT_UNLOCK_PCT = 75;
const FRONTEND = window.SKILLME_FRONTEND || '${FRONTEND}';

// Task guides are markdown from the curriculum; render them sanitized, or as plain text
// if the CDN libraries didn't load.
function renderMarkdown(md) {
  const src = md || '';
  if (window.marked && window.DOMPurify) return DOMPurify.sanitize(marked.parse(src));
  const div = document.createElement('div');
  div.textContent = src;
  return div.innerHTML.split(/\n{2,}/).map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('');
}

// Short, non-blocking notice (replaces alert()). tone: 'ok' | 'error'
let dashToastTimer = null;
function dashToast(msg, tone) {
  const el = document.getElementById('dash-toast');
  if (!el) return;
  el.textContent = msg;
  el.dataset.tone = tone || 'ok';
  requestAnimationFrame(() => el.classList.add('is-visible'));
  clearTimeout(dashToastTimer);
  dashToastTimer = setTimeout(() => el.classList.remove('is-visible'), tone === 'error' ? 6000 : 3000);
}

// Dialogs: focus moves into the dialog on open and returns to the trigger on close.
let modalReturnFocus = null;
function modalOpened(modal) {
  modalReturnFocus = document.activeElement;
  const first = modal.querySelector('.payment-modal-close, .milestone-modal-close') || modal.querySelector('button, [href], input');
  if (first) first.focus({ preventScroll: true });
}
function modalClosed() {
  if (modalReturnFocus && document.contains(modalReturnFocus)) modalReturnFocus.focus({ preventScroll: true });
  modalReturnFocus = null;
}

// One email can hold several applications (one per track). The dashboard opens the one
// picked last time on this device, else the backend's default (an active internship).
const APP_KEY = 'skillme_student_id';
async function loadDashboardData() {
  const appsRes = await fetch(`${API}/api/students/applications`, { headers: authHeaders() });
  if (!appsRes.ok) throw Object.assign(new Error('applications'), { status: appsRes.status });
  const { applications = [], default_student_id } = await appsRes.json();
  if (!applications.length) throw Object.assign(new Error('no applications'), { status: 404 });
  const saved = Number(localStorage.getItem(APP_KEY));
  const chosen = applications.some(a => a.student_id === saved) ? saved : default_student_id;
  const res = await fetch(`${API}/api/students/progress/id/${chosen}`, { headers: authHeaders() });
  if (!res.ok) throw Object.assign(new Error('progress'), { status: res.status });
  const data = await res.json();
  data._applications = applications;
  return data;
}

// "Internship: [Python ▾]" — only when the student has applied to more than one track.
function renderAppSwitcher(data) {
  const apps = data._applications || [];
  document.querySelectorAll('.app-switcher').forEach(el => el.remove());
  if (apps.length < 2) return;
  const STATUS = { active: 'active', completed: 'completed', dropped: 'closed' };
  const build = () => {
    const wrap = document.createElement('label');
    wrap.className = 'app-switcher';
    const text = document.createElement('span');
    text.textContent = 'Internship';
    const select = document.createElement('select');
    apps.forEach(a => {
      const opt = document.createElement('option');
      opt.value = a.student_id;
      const state = a.enrollment_status ? STATUS[a.enrollment_status] || a.enrollment_status : (a.status === 'applied' ? 'under review' : a.status);
      opt.textContent = `${a.domain_label || a.domain} · ${state}`;
      opt.selected = data.student && a.student_id === data.student.id;
      select.append(opt);
    });
    select.addEventListener('change', () => {
      localStorage.setItem(APP_KEY, select.value);
      window.location.reload();
    });
    wrap.append(text, select);
    return wrap;
  };
  const greet = document.querySelector('#dash-header-el .ov-greet');
  if (greet) greet.append(build());
  const unenrolledCard = document.querySelector('#unenrolled-view .login-card');
  if (unenrolledCard) unenrolledCard.insertBefore(build(), unenrolledCard.querySelector('.login-btn'));
}

// Signed in but no active internship: under review, or dropped.
function showUnenrolled(data) {
  const summary = (data && data.summary) || {};
  const dropped = summary.enrollment_status === 'dropped' || summary.application_status === 'dropped';
  if (dropped) {
    document.getElementById('unenrolled-title').textContent = 'Your internship is no longer active';
    const p = document.getElementById('unenrolled-text');
    p.textContent = 'Your enrollment was closed. If you think this is a mistake or want to be reconsidered, write to ';
    const a = document.createElement('a');
    a.href = 'mailto:admin@skill-me-intern.in';
    a.textContent = 'admin@skill-me-intern.in';
    p.append(a, '.');
  }
  document.getElementById('unenrolled-view').style.display = 'flex';
}

// Student API calls carry the session token from the OTP login.
function authHeaders(extra) {
  const token = localStorage.getItem('token');
  return Object.assign({}, extra || {}, token ? { 'Authorization': `Bearer ${token}` } : {});
}

// --- Lenis Smooth Scrolling (from darkroomengineering/lenis) ---
let lenis;
// Smooth scrolling is motion: skip it for people who ask for less.
const prefersReducedMotion = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
if (typeof Lenis !== 'undefined' && !prefersReducedMotion) {
  lenis = new Lenis({
    duration: 1.2,
    easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
    orientation: 'vertical',
    gestureOrientation: 'vertical',
    smoothWheel: true,
    wheelMultiplier: 1,
    touchMultiplier: 2,
    infinite: false,
  });

  function raf(time) {
    lenis.raf(time);
    requestAnimationFrame(raf);
  }
  requestAnimationFrame(raf);
}

// --- DOM Ready ---
document.addEventListener('DOMContentLoaded', () => {
  const urlParams = new URLSearchParams(window.location.search);
  const loginForm = document.getElementById('dash-login-form');
  const loginView = document.getElementById('login-view');
  const dashView = document.getElementById('dashboard-view');
  const errorEl = document.getElementById('login-error');
  const loginBtn = document.getElementById('login-btn');

  let loginState = 'email';

  // --- Auto-Login via Saved Session ---
  async function checkExistingSession() {
    const isPreview = urlParams.get('preview') === '1' || urlParams.get('preview') === 'paid' || urlParams.get('preview') === 'progress' || urlParams.get('preview') === 'milestone' || urlParams.get('preview') === 'pending';
    
    // Bypass login entirely for preview mode
    if (isPreview) {
        const isProgress = urlParams.get('preview') === 'progress' || urlParams.get('preview') === 'milestone';
        const completedCount = isProgress ? 1 : 4;
        const mockData = {
            student: { id: 999, first_name: "Saksham", last_name: "Verma", name: "Saksham Verma", email: "test@example.com", domain: "Web Development", college: "Test College" },
            progress: [{ week: isProgress ? 1 : 4, issues_completed: completedCount, score: isProgress ? 100 : 300, domain: "web-dev", batch_id: 1, start_date: new Date().toISOString() }],
            submissions: [
              { id: 1, week: 1, linkedin_url: "https://www.linkedin.com/posts/example", status: "approved", admin_note: null, submitted_at: new Date().toISOString(), reviewed_at: new Date().toISOString(), domain: "web-dev" }
            ],
            summary: { total_tasks: 4, completed_tasks: completedCount, completion_pct: Math.round((completedCount / 4) * 100) },
            _batch_id: 1,
            _email: "test@example.com"
        };
        renderDashboard(mockData);
        loginView.style.display = 'none';
        dashView.style.display = 'block';
        dashView.style.opacity = '1';
        dashView.style.transform = 'translateY(0)';
        if (lenis) lenis.resize();
        return;
    }

    const signoutBtn = document.getElementById('signout-btn');
    const cancelWrap = document.getElementById('login-cancel-wrap');
    const resetLoginButton = () => {
      loginView.classList.remove('is-restoring');
      loginBtn.disabled = false;
      loginBtn.textContent = 'Get login code';
      if (signoutBtn) signoutBtn.style.display = 'none';
      if (cancelWrap) cancelWrap.style.display = 'none';
    };
    const showLoginNotice = (msg) => {
      errorEl.textContent = msg;
      errorEl.style.display = 'block';
    };

    const token = localStorage.getItem('token');
    const savedEmail = localStorage.getItem('skillme_email');
    if (!token) {
      // Sessions from before sign-in tokens were required can't load data any more.
      if (savedEmail) {
        localStorage.removeItem('skillme_email');
        const emailInput = document.getElementById('login-email');
        if (emailInput) emailInput.value = savedEmail;
        showLoginNotice('Please sign in again to open your dashboard.');
      }
      resetLoginButton();
      return;
    }

    // Returning student: show "Opening your dashboard…" instead of a disabled login form.
    loginView.classList.add('is-restoring');
    loginBtn.disabled = true;
    loginBtn.textContent = 'Opening your dashboard...';
    // Show Sign Out button so user can abort if stuck
    if (signoutBtn) signoutBtn.style.display = 'inline-flex';
    if (cancelWrap) cancelWrap.style.display = 'block';

    try {
      let resolvedEmail = savedEmail;
      if (!resolvedEmail) {
        const meRes = await fetch(`${API}/api/auth/me`, { headers: authHeaders() });
        if (meRes.ok) resolvedEmail = (await meRes.json()).email;
      }
      if (!resolvedEmail) throw Object.assign(new Error('expired'), { status: 401 });

      const data = await loadDashboardData();

      // If user clicked sign out while fetch was pending, abort the restore process
      if (!localStorage.getItem('skillme_email') && !localStorage.getItem('token')) {
        resetLoginButton();
        return;
      }

      data._email = resolvedEmail;
      renderDashboard(data);
      renderAppSwitcher(data);

      loginView.style.display = 'none';
      if (data.progress && data.progress.length === 0) {
        showUnenrolled(data);
      } else {
        dashView.style.display = 'block';
        dashView.style.opacity = '1';
        dashView.style.transform = 'translateY(0)';
      }
      if (lenis) lenis.resize();
    } catch (e) {
      resetLoginButton();
      if (e && (e.status === 401 || e.status === 403 || e.status === 404)) {
        // Only a rejected session signs the student out — a server hiccup keeps it.
        localStorage.removeItem('token');
        localStorage.removeItem('skillme_email');
        showLoginNotice('Your session has expired. Please sign in again.');
      } else {
        showLoginNotice("We couldn't reach SkillMe right now. Check your connection and ");
        const retry = document.createElement('button');
        retry.type = 'button';
        retry.className = 'login-retry-link';
        retry.textContent = 'try again';
        retry.addEventListener('click', () => { errorEl.style.display = 'none'; checkExistingSession(); });
        errorEl.append(retry, '.');
      }
    }
  }

  // --- Intersection Observer for Submission Cards ---
  // Must exist before checkExistingSession() runs below: preview mode calls
  // renderDashboard(mockData) synchronously with no prior await, so renderSubmissionsList
  // (which calls subObserver.observe) can run before this file finishes its top-to-bottom
  // pass — subObserver has to be initialized ahead of that call, not just defined "later".
  const subObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        subObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

  // Task view state — declared before checkExistingSession(): preview mode renders synchronously.
  let lastTasks = null;     // most recent task list from /api/tasks/current
  let selectedWeek = null;  // week currently open in the Tasks panel

  // Check on load
  checkExistingSession().catch(err => {
    console.warn("Session check notice:", err);
  });

  // --- OTP login ---
  const emailInput = document.getElementById('login-email');
  const otpInput = document.getElementById('login-otp');
  const otpWrap = document.getElementById('otp-wrap');
  const otpSentTo = document.getElementById('otp-sent-to');
  const resendBtn = document.getElementById('resend-btn');
  const changeEmailBtn = document.getElementById('change-email-btn');
  const LABEL_EMAIL = 'Get login code';
  const LABEL_OTP = 'Sign in';
  const RESEND_SECONDS = 30;
  let resendTimer = null;

  function showLoginError(msg) {
    errorEl.textContent = msg;
    errorEl.style.display = 'block';
  }

  function setLoginBusy(busy, label) {
    loginBtn.disabled = busy;
    loginBtn.style.opacity = busy ? '0.7' : '1';
    loginBtn.textContent = label;
  }

  // "Resend in 29s" countdown, then the button comes back.
  function startResendCountdown() {
    clearInterval(resendTimer);
    let left = RESEND_SECONDS;
    resendBtn.disabled = true;
    resendBtn.textContent = `Resend in ${left}s`;
    resendTimer = setInterval(() => {
      left -= 1;
      if (left <= 0) {
        clearInterval(resendTimer);
        resendBtn.disabled = false;
        resendBtn.textContent = 'Resend code';
      } else {
        resendBtn.textContent = `Resend in ${left}s`;
      }
    }, 1000);
  }

  function showEmailStep() {
    clearInterval(resendTimer);
    loginState = 'email';
    otpWrap.style.display = 'none';
    otpInput.value = '';
    emailInput.readOnly = false;
    setLoginBusy(false, LABEL_EMAIL);
    emailInput.focus();
  }

  function showOtpStep(email) {
    loginState = 'otp';
    otpWrap.style.display = 'block';
    emailInput.readOnly = true;
    if (otpSentTo) otpSentTo.textContent = email;
    setLoginBusy(false, LABEL_OTP);
    otpInput.focus();
    startResendCountdown();
  }

  async function requestCode(email) {
    const res = await fetch(`${API}/api/auth/request-otp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email })
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || "We couldn't send a code to that email. Check it and try again.");
    }
  }

  resendBtn.addEventListener('click', async () => {
    const email = emailInput.value.trim();
    if (!email) return;
    errorEl.style.display = 'none';
    resendBtn.disabled = true;
    resendBtn.textContent = 'Sending...';
    try {
      await requestCode(email);
      startResendCountdown();
    } catch (err) {
      showLoginError(err instanceof TypeError ? "We couldn't reach SkillMe. Check your connection and try again." : err.message);
      resendBtn.disabled = false;
      resendBtn.textContent = 'Resend code';
    }
  });

  changeEmailBtn.addEventListener('click', () => {
    errorEl.style.display = 'none';
    showEmailStep();
  });

  // Codes arrive as "123456" or "123 456": keep digits only, and sign in once all 6 are there.
  otpInput.addEventListener('input', () => {
    const digits = otpInput.value.replace(/\D/g, '').slice(0, 6);
    if (otpInput.value !== digits) otpInput.value = digits;
    if (digits.length === 6 && loginState === 'otp' && !loginBtn.disabled) loginForm.requestSubmit();
  });

  // Login handler
  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = emailInput.value.trim();
    const otp = otpInput.value.trim();

    errorEl.style.display = 'none';

    if (loginState === 'email') {
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return showLoginError('Please enter the email address you applied with.');

      // Optimistic: show the code field right away (cold starts can be slow), and step
      // back to the email field if the code can't be sent.
      showOtpStep(email);
      try {
        await requestCode(email);
      } catch (err) {
        showEmailStep();
        showLoginError(err instanceof TypeError ? "We couldn't reach SkillMe. Check your connection and try again." : err.message);
      }
      return;
    }

    if (otp.length !== 6) return showLoginError('Enter the 6-digit code from your email.');

    setLoginBusy(true, 'Signing in...');
    try {
      const authRes = await fetch(`${API}/api/auth/verify-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, otp })
      });
      if (!authRes.ok) {
        const errData = await authRes.json().catch(() => ({}));
        throw new Error(errData.detail || 'That code is wrong or has expired. Try again or resend it.');
      }

      const authData = await authRes.json();
      if (authData.token) localStorage.setItem('token', authData.token);
      localStorage.setItem('skillme_email', email);

      // Successfully verified. Now load student dashboard data.
      let data;
      try {
        data = await loadDashboardData();
      } catch (e) {
        if (e instanceof TypeError) throw e;
        throw new Error("Signed in, but we couldn't load your dashboard. Please refresh.");
      }
      data._email = email;
      clearInterval(resendTimer);
      renderDashboard(data);
      renderAppSwitcher(data);

      // Transition to dashboard view
      loginView.style.opacity = '0';
      loginView.style.transform = 'translateY(-20px)';
      loginView.style.transition = 'all 0.4s ease';

      setTimeout(() => {
        loginView.style.display = 'none';
        if (data.progress && data.progress.length === 0) {
          showUnenrolled(data);
        } else {
          dashView.style.display = 'block';
          dashView.style.opacity = '1';
          dashView.style.transform = 'translateY(0)';
        }
        if (lenis) lenis.resize();
      }, 400);
    } catch (err) {
      setLoginBusy(false, LABEL_OTP);
      showLoginError(err instanceof TypeError ? "We couldn't reach SkillMe. Check your connection and try again." : (err.message || 'Something went wrong. Please try again.'));
      otpInput.select();
    }
  });

  // --- Render Dashboard ---
  async function renderDashboard(data) {
    const { student, progress, submissions } = data;
    
    // Store globally for Razorpay callback
    window._dashData = data;
    window._dashStudent = student;

    // Show Sign Out button in navbar when logged into dashboard
    const signoutBtn = document.getElementById('signout-btn');
    
    if (signoutBtn) signoutBtn.style.display = 'inline-flex';

    // Header
    const firstName = student.name.split(' ')[0];
    const dashNameEl = document.getElementById('dash-name');
    if (dashNameEl) dashNameEl.textContent = `Welcome back, ${firstName}`;
    const sidebarNameEl = document.getElementById('dash-sidebar-name');
    if (sidebarNameEl) sidebarNameEl.textContent = student.name;
    const mobileHeaderNameEl = document.getElementById('mobile-header-name');
    if (mobileHeaderNameEl) mobileHeaderNameEl.textContent = student.name;
    const avatarEl = document.getElementById('dash-avatar');
    if (avatarEl) {
      const initials = String(student.name || '').trim().split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase();
      avatarEl.textContent = initials || '·';
    }

    const hodUrl = `/offer?view=hod&student_id=${student.id || ''}&ref=${encodeURIComponent(student.offer_ref || '')}&name=${encodeURIComponent(student.name || '')}&domain=${encodeURIComponent(student.domain || '')}&college=${encodeURIComponent(student.college || '')}`;
    const hodQuickLink = document.getElementById('dash-quick-hod');
    if (hodQuickLink) hodQuickLink.href = hodUrl;

    const hodBannerBtn = document.getElementById('dash-banner-hod-btn');
    if (hodBannerBtn) hodBannerBtn.href = hodUrl;

    // Progress
    let totalAssigned = (data.summary && data.summary.total_tasks) || 4;
    let totalCompleted = (data.summary && data.summary.completed_tasks) || 0;
    let totalScore = 0, maxWeek = 1;
    const approvedCount = (submissions || []).filter(s => (s.status || '').toLowerCase() === 'approved').length;

    if (progress && progress.length > 0) {
      const latest = progress[progress.length - 1];
      const domainHtml = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align: middle; margin-right: 4px; margin-top: -2px;"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/></svg>
        ${(latest.domain || 'web-dev').replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}`;
      
      const dashDomain = document.getElementById('dash-domain');
      if (dashDomain) dashDomain.innerHTML = domainHtml;
      
      const mobileDashDomain = document.getElementById('mobile-dash-domain');
      if (mobileDashDomain) mobileDashDomain.innerHTML = domainHtml;

      // Calculate week based on the enrollment start_date if available
      if (latest.start_date) {
        try {
          const startDate = new Date(latest.start_date);
          const diffDays = Math.floor((new Date() - startDate) / (1000 * 60 * 60 * 24));
          const calculatedWeek = Math.min(4, Math.max(1, Math.floor(diffDays / 7) + 1));
          maxWeek = Math.max(maxWeek, calculatedWeek);
        } catch(e) {}
      }

      progress.forEach(p => {
        totalScore += Number(p.score) || 0;
        maxWeek = Math.max(maxWeek, p.week || 1);
      });

      // Store the internal enrollment reference (batch_id) for tasks/payments/certificate links
      data._batch_id = latest.batch_id || data._batch_id;
    }

    const flexPdfBtn = document.getElementById('flex-pdf-btn');
    if (flexPdfBtn && student && data._batch_id) {
        flexPdfBtn.href = `/tasks?student_id=${student.id}&batch_id=${data._batch_id}`;
    }

    document.getElementById('stat-completed').textContent = totalCompleted;
    document.getElementById('stat-assigned').textContent = totalAssigned;
    document.getElementById('stat-prs').textContent = approvedCount;
    document.getElementById('stat-week').textContent = maxWeek;
    document.getElementById('stat-score').textContent = totalScore;

    // Progress ring + bar
    // Prefer the backend-computed completion percentage (based on admin-approved submissions).
    const pct = (data.summary && typeof data.summary.completion_pct === 'number')
      ? Math.min(100, Math.max(0, Math.round(data.summary.completion_pct)))
      : Math.min(100, Math.round((totalCompleted / (totalAssigned || 4)) * 100));
    const progressPctEl = document.getElementById('progress-pct');
    const prevPct = parseInt(progressPctEl.textContent, 10) || 0;
    progressPctEl.textContent = prevPct;

    // Update description based on progress
    const descEl = document.getElementById('progress-desc');
    if (pct >= PAYMENT_UNLOCK_PCT) {
      if (pct < 100) {
        descEl.textContent = `Impressive progress! ${totalCompleted} of ${totalAssigned} tasks done. You have met the minimum requirements to claim your certificate!`;
      } else {
        descEl.textContent = `Outstanding! You've completed all ${totalAssigned} assigned tasks. You're a star intern!`;
      }
      // Show once per student per completion bracket (75/100), not on every dashboard load.
      const eligibilitySeenKey = `skillme_eligibility_seen_s${student && student.id ? student.id : 'guest'}_pct${pct}`;
      if (!localStorage.getItem(eligibilitySeenKey)) {
        localStorage.setItem(eligibilitySeenKey, 'true');
        setTimeout(() => showCompletionPopup(student, data, pct), 800);
      }
    } else {
      if (pct === 0) {
        descEl.textContent = "You're just getting started. Submit your first LinkedIn post for a task to see your progress update once it's approved.";
      } else {
        descEl.textContent = `Great start! You've completed ${totalCompleted} out of ${totalAssigned} tasks. Keep the momentum going!`;
      }
      const tasksForUnlock = Math.ceil((totalAssigned || 4) * PAYMENT_UNLOCK_PCT / 100);
      const tasksRemaining = Math.max(1, tasksForUnlock - totalCompleted);
      const taskWord = tasksRemaining === 1 ? 'task' : 'tasks';
      const nudgeBanner = document.getElementById('cred-nudge-banner');
      if (nudgeBanner) {
        nudgeBanner.style.display = 'inline-flex';
        const nudgeStrong = nudgeBanner.querySelector('strong');
        if (nudgeStrong) nudgeStrong.textContent = `${tasksRemaining} more ${taskWord}`;
      }
    }

    // Animate ring after render
    setTimeout(async () => {
      const r = 70;
      const cx = 82, cy = 82;
      const circumference = 2 * Math.PI * r;
      const offset = circumference - (pct / 100) * circumference;
      const urlParams = new URLSearchParams(window.location.search);

      document.getElementById('progress-ring').style.strokeDashoffset = offset;
      document.getElementById('progress-bar-inner').style.width = `${pct}%`;

      // Animated count-up on the hero percentage + a leading glow dot that travels the arc
      animateValue(progressPctEl, prevPct, pct, 1600);
      const ringHead = document.getElementById('progress-ring-head');
      if (ringHead) {
        const angle = (-90 + (pct / 100) * 360) * (Math.PI / 180);
        ringHead.style.opacity = pct > 0 ? '1' : '0';
        ringHead.setAttribute('cx', cx + r * Math.cos(angle));
        ringHead.setAttribute('cy', cy + r * Math.sin(angle));
      }
      const ringWrap = document.querySelector('.progress-ring-wrap');
      if (ringWrap) {
        setTimeout(() => {
          ringWrap.classList.remove('pop');
          void ringWrap.offsetWidth;
          ringWrap.classList.add('pop');
        }, 1600);
      }

      // Journey timeline + unlock meter reflect each week's real review status
      renderJourney(data, lastTasks);

      // ─── Certificate Banner (Payment Gated) ───
      // Payment is visible directly at >=75% completion (3 of 4 tasks). Below that, a student must
      // file an urgent request (panel-urgent) and have an admin fulfill it — which
      // sets summary.payment_unlocked — before the payment banner appears.
      const paymentUnlocked = !!(data.summary && data.summary.payment_unlocked);
      const certSection = document.getElementById('cert-section');
      const credLockedStrip = document.getElementById('cred-locked-strip');
      const credNudgeBanner = document.getElementById('cred-nudge-banner');
      const hideCredHints = () => {
        if (credLockedStrip) credLockedStrip.style.display = 'none';
        if (credNudgeBanner) credNudgeBanner.style.display = 'none';
      };
      // 'paid' | 'unpaid' | 'unknown'. 'unknown' (the check failed) must never show the
      // pay banner — a student who already paid could be charged twice.
      async function fetchPayState() {
        if (!student.id || !data._batch_id) return 'unpaid';
        if (urlParams.get('preview') === 'paid') return 'paid';
        try {
          const payStatus = await fetch(`${API}/api/payments/status/${student.id}/${data._batch_id}`);
          if (!payStatus.ok) return 'unknown';
          const payData = await payStatus.json();
          return payData.status === 'paid' ? 'paid' : 'unpaid';
        } catch (e) {
          return 'unknown';
        }
      }
      async function renderCredentials() {
        const eligible = pct >= PAYMENT_UNLOCK_PCT || paymentUnlocked;
        const payState = await fetchPayState();
        if (payState === 'paid') {
          renderCertReady(certSection, student, data);
          hideCredHints();
        } else if (eligible && payState === 'unknown') {
          certSection.style.display = 'block';
          certSection.innerHTML = `<div class="cert-status-error" role="alert">
              <p><strong>We couldn't confirm your certificate payment.</strong> Please check again before paying, so you're never charged twice.</p>
              <button type="button" class="cert-btn cert-btn-primary pay-status-retry">Check again</button>
            </div>`;
          certSection.querySelector('.pay-status-retry').addEventListener('click', renderCredentials);
          hideCredHints();
        } else if (eligible) {
          renderPaymentBanner(certSection, student, data);
          hideCredHints();
        } else {
          certSection.style.display = 'none';
          certSection.innerHTML = '';
          if (credLockedStrip) credLockedStrip.style.display = 'grid';
        }
      }
      if (certSection) await renderCredentials();

      // ─── Urgent (24h) Processing Request Panel ───
      loadUrgentRequestPanel(student, data, pct, paymentUnlocked);

      // ─── Automated Milestone Celebration Popup Trigger ───
      // Automatically triggers celebration modal on first visit after merging a new PR / completing a task
      const milestoneContext = resolveMilestoneContext(data);
      if (pct < 100 && milestoneContext.hasCompletedTasks) {
        const milestoneCelebrationKey = `skillme_milestone_seen_s${milestoneContext.student.id || 'guest'}_pr${milestoneContext.totalPrs}_t${milestoneContext.latestTaskId || milestoneContext.taskNum}_w${milestoneContext.weekNum}`;
        if (!localStorage.getItem(milestoneCelebrationKey) || urlParams.get('preview') === 'milestone' || urlParams.get('preview') === 'progress') {
          setTimeout(() => {
            window.openMilestoneShareModal(data);
            if (urlParams.get('preview') !== 'milestone' && urlParams.get('preview') !== 'progress') {
              localStorage.setItem(milestoneCelebrationKey, 'true');
            }
          }, 850);
        }
      }
    }, 600);

    // "Your next step" card — first pass from submissions; refined once task titles load
    renderNextStep(data, null);

    // Submissions (LinkedIn task review history)
    renderSubmissionsList(submissions || []);

    // Render Assigned Tasks + per-week LinkedIn submission UI
    loadAndRenderTasks(data);

    // Removed pdfBtn onclick to rely on standard HTML anchor tag for popup blocker bypass

  }

  function escHtml(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Open a panel and (optionally) scroll to a week's task card.
  function goToTask(panelId, week) {
    if (week) selectTaskWeek(week);
    if (typeof window.dashShowPanel === 'function') window.dashShowPanel(panelId);
    if (lenis) lenis.scrollTo(0, { immediate: true }); else window.scrollTo(0, 0);
  }

  // Per-week review status from the student's submissions.
  function weekStatus(data, week) {
    const s = ((data && data.submissions) || []).find(x => Number(x.week) === Number(week));
    return s ? (s.status || 'pending').toLowerCase() : 'not_submitted';
  }

  // Home "4-week journey" tiles + the credentials unlock meter.
  function renderJourney(data, tasks) {
    if (!data) return;
    const summary = data.summary || {};
    const total = Number(summary.total_tasks) || 4;
    const pct = typeof summary.completion_pct === 'number' ? summary.completion_pct : 0;
    const approvedSubs = (data.submissions || []).filter(s => (s.status || '').toLowerCase() === 'approved').length;
    const approved = Math.max(Number(summary.completed_tasks) || 0, approvedSubs);
    const allDone = pct >= 100;
    const firstOpen = [1, 2, 3, 4].find(w => ['not_submitted', 'rejected'].includes(weekStatus(data, w)));

    const STATE = {
      approved:      { cls: 'completed', text: 'Approved' },
      pending:       { cls: 'review',    text: 'In review' },
      rejected:      { cls: 'rejected',  text: 'Needs changes' },
      not_submitted: { cls: '',          text: 'Not started' },
    };
    [1, 2, 3, 4].forEach(w => {
      const el = document.querySelector(`#sprint-milestones-row [data-week="${w}"]`);
      if (!el) return;
      const status = allDone ? 'approved' : weekStatus(data, w);
      let { cls, text } = STATE[status] || STATE.not_submitted;
      if (status === 'not_submitted' && w === firstOpen) { cls = 'active'; text = 'Up next'; }
      el.classList.remove('active', 'completed', 'review', 'rejected');
      if (cls) el.classList.add(cls);
      const stateEl = el.querySelector('.milestone-state');
      if (stateEl) stateEl.textContent = text;
      const task = (tasks || []).find(t => Number(t.week_number) === w);
      const nameEl = el.querySelector('.milestone-name');
      if (nameEl && task && task.title) nameEl.textContent = task.title;
      el.setAttribute('aria-label', `Week ${w}${task && task.title ? ': ' + task.title : ''} — ${text}`);
    });

    // Unlock meter (credentials) + certificate fact (home)
    const needed = Math.ceil(total * PAYMENT_UNLOCK_PCT / 100);
    const unlocked = pct >= PAYMENT_UNLOCK_PCT || !!summary.payment_unlocked;
    const done = Math.min(approved, needed);
    const fill = document.getElementById('unlock-meter-fill');
    if (fill) fill.style.width = `${Math.round((done / (needed || 1)) * 100)}%`;
    const countEl = document.getElementById('unlock-count');
    if (countEl) countEl.textContent = `${done} of ${needed}`;
    const remaining = Math.max(0, needed - approved);
    const factEl = document.getElementById('fact-unlock');
    if (factEl) factEl.innerHTML = unlocked
      ? '<span class="fact-ok">Unlocked</span>'
      : `${remaining}<span class="stat-unit"> more approval${remaining === 1 ? '' : 's'}</span>`;
    const homeCred = document.getElementById('home-cred-status');
    if (homeCred) homeCred.textContent = unlocked ? 'Unlocked — ready to claim' : `Unlocks after ${remaining} more approval${remaining === 1 ? '' : 's'}`;

    // Sidebar badge: how many tasks still need action
    const badge = document.getElementById('nav-work-badge');
    if (badge) {
      const open = allDone ? 0 : [1, 2, 3, 4].filter(w => ['not_submitted', 'rejected'].includes(weekStatus(data, w))).length;
      badge.textContent = open;
      badge.hidden = open === 0;
    }
  }

  // Show one week's task card in the Tasks panel.
  function selectTaskWeek(week) {
    selectedWeek = Number(week);
    document.querySelectorAll('#tasks-list .task-card').forEach(card => {
      card.hidden = Number(card.dataset.week) !== selectedWeek;
    });
    document.querySelectorAll('#task-week-tabs .week-tab').forEach(tab => {
      const on = Number(tab.dataset.week) === selectedWeek;
      tab.classList.toggle('is-selected', on);
      tab.setAttribute('aria-selected', on ? 'true' : 'false');
      tab.tabIndex = on ? 0 : -1;
      // Keep the selected week visible when the switcher scrolls sideways (mobile)
      if (on && tab.parentElement && tab.parentElement.scrollWidth > tab.parentElement.clientWidth) {
        const strip = tab.parentElement;
        strip.scrollTo({ left: tab.offsetLeft - strip.offsetLeft - 16, behavior: 'smooth' });
      }
    });
  }

  window.dashOpenWeek = function(week) { goToTask('panel-work', week); };

  // "Your next step" card on the overview — one clear action derived from live status.
  function renderNextStep(data, tasks) {
    const el = document.getElementById('dash-next-step');
    if (!el || !data) return;
    const summary = data.summary || {};
    const subs = data.submissions || [];
    const total = Number(summary.total_tasks) || (tasks && tasks.length) || 4;
    const weeks = (tasks && tasks.length)
      ? [...tasks].map((t, i) => Number(t.week_number) || (i + 1)).sort((a, b) => a - b)
      : Array.from({ length: total }, (_, i) => i + 1);
    const statusOf = (w) => {
      const s = subs.find(x => Number(x.week) === Number(w));
      return s ? (s.status || 'pending').toLowerCase() : 'not_submitted';
    };
    const titleOf = (w) => {
      const t = (tasks || []).find(x => Number(x.week_number) === Number(w));
      return t && t.title ? t.title : `Week ${w} task`;
    };
    const weeksLabel = (ws) => ws.length === 1 ? `Week ${ws[0]}` : `Weeks ${ws.slice(0, -1).join(', ')} & ${ws[ws.length - 1]}`;

    const approved = subs.filter(s => (s.status || '').toLowerCase() === 'approved').length;
    const pct = typeof summary.completion_pct === 'number' ? summary.completion_pct : Math.round((approved / (total || 4)) * 100);
    const rejected = weeks.find(w => statusOf(w) === 'rejected');
    const todo = weeks.find(w => statusOf(w) === 'not_submitted');
    const pending = weeks.filter(w => statusOf(w) === 'pending');

    const ICONS = {
      accent: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
      danger: '<path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>',
      review: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
      ok: '<circle cx="12" cy="8" r="6"/><path d="M15.48 12.89 17 22l-5-3-5 3 1.52-9.11"/>',
    };

    let s;
    if (pct >= 100) {
      s = { tone: 'ok', label: 'All tasks complete', title: "You've finished the internship 🎉", desc: 'Your Certificate, LOR and Portfolio are waiting in the Credentials tab.', cta: 'Open Credentials', panel: 'panel-credentials' };
    } else if (rejected) {
      s = { tone: 'danger', label: 'Action needed', title: `Resubmit Week ${rejected}: ${titleOf(rejected)}`, desc: 'Your post was rejected. Read the admin note on the task, fix your post and paste the new link.', cta: 'Fix & resubmit', panel: 'panel-work', week: rejected };
    } else if (pct >= PAYMENT_UNLOCK_PCT) {
      s = { tone: 'ok', label: 'Credentials unlocked', title: 'Your certificate is ready to claim', desc: todo ? `You can still finish Week ${todo} to complete all ${total} tasks.` : 'Open the Credentials tab to view or claim them.', cta: 'Open Credentials', panel: 'panel-credentials' };
    } else if (todo) {
      s = { tone: 'accent', label: 'Your next step', title: `Week ${todo}: ${titleOf(todo)}`, desc: pending.length ? `${weeksLabel(pending)} is under review. Meanwhile, complete this task and submit your LinkedIn post.` : 'Complete the task, share it on LinkedIn and submit the post link for review.', cta: 'Open task', panel: 'panel-work', week: todo };
    } else if (pending.length) {
      s = { tone: 'review', label: 'Under review', title: `${weeksLabel(pending)} ${pending.length > 1 ? 'are' : 'is'} being reviewed`, desc: 'Nothing to do right now — your progress updates automatically once an admin approves it.', cta: 'View submissions', panel: 'panel-work' };
    } else {
      s = { tone: 'accent', label: 'Your next step', title: 'Open your weekly tasks', desc: 'Complete each task and submit your LinkedIn post for review.', cta: 'Open tasks', panel: 'panel-work' };
    }

    el.dataset.tone = s.tone;
    el.innerHTML = `
      <div class="next-step-body">
        <div class="next-step-label"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">${ICONS[s.tone]}</svg>${escHtml(s.label)}</div>
        <div class="next-step-title">${escHtml(s.title)}</div>
        <div class="next-step-desc">${escHtml(s.desc)}</div>
        <button type="button" class="cert-btn ${s.tone === 'review' ? 'cert-btn-secondary' : 'cert-btn-primary'}">${escHtml(s.cta)}
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
        </button>
      </div>`;
    el.querySelector('button').addEventListener('click', () => goToTask(s.panel, s.week));
  }

  function renderSubmissionsList(submissions) {
    const subList = document.getElementById('sub-list');
    const subEmpty = document.getElementById('sub-empty');
    const subCount = document.getElementById('sub-count');
    if (!subList) return;
    subList.innerHTML = '';

    if (submissions && submissions.length > 0) {
      if (subEmpty) subEmpty.style.display = 'none';
      if (subCount) subCount.textContent = `${submissions.length} Submitted`;

      const sortedSubs = [...submissions].sort((a, b) => (a.week || 0) - (b.week || 0));
      sortedSubs.forEach((sub, i) => {
        const status = (sub.status || 'pending').toLowerCase();
        const dotClass = status === 'approved' ? 'merged' : (status === 'rejected' ? 'failed' : 'open');
        const dateStr = sub.submitted_at
          ? new Date(sub.submitted_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
          : '';

        const card = document.createElement('div');
        card.className = 'sub-card';
        card.style.transitionDelay = `${i * 0.08}s`;
        card.innerHTML = `
          <div class="sub-dot ${dotClass}"></div>
          <div class="sub-info">
            <div class="sub-title">Week ${sub.week || '?'} LinkedIn Submission</div>
            <div class="sub-meta">
              ${dateStr ? `<span>Submitted ${dateStr}</span>` : ''}
              ${sub.admin_note ? `<span title="Admin note">📝 ${escHtml(sub.admin_note)}</span>` : ''}
            </div>
          </div>
          <span class="sub-status ${dotClass}">${status}</span>
          ${sub.linkedin_url ? `<a href="${escHtml(sub.linkedin_url)}" target="_blank" rel="noopener noreferrer" class="sub-link" title="View LinkedIn Post">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
          </a>` : ''}
        `;
        subList.appendChild(card);
        subObserver.observe(card);
      });
    } else {
      if (subEmpty) subEmpty.style.display = 'block';
      if (subCount) subCount.textContent = '0 Submitted';
    }
  }

  // Fetch the current 4-week task set (with ready-made LinkedIn captions) and render it
  // alongside the student's submission status for each week.
  async function loadAndRenderTasks(data) {
    const student = data.student;
    const batchId = data._batch_id;
    const submissions = data.submissions || [];

    if (!student || !student.id || !batchId) {
      renderTasks([], {}, submissions, null);
      return;
    }

    setTasksError(false);
    try {
      const res = await fetch(`${API}/api/tasks/current/${student.id}/${batchId}`);
      if (!res.ok) throw new Error('tasks ' + res.status);
      const taskData = await res.json();
      renderTasks(taskData.tasks || [], taskData.linkedin_templates || {}, submissions, { studentId: student.id, batchId });
    } catch (e) {
      // A failed load is not "no tasks yet": say so, and offer a retry.
      renderTasks([], {}, submissions, { studentId: student.id, batchId });
      setTasksError(true, () => loadAndRenderTasks(data));
    }
  }

  function setTasksError(on, retry) {
    const box = document.getElementById('tasks-empty');
    if (!box) return;
    const h3 = box.querySelector('h3');
    const p = box.querySelector('p');
    if (!box.dataset.defaultTitle) {
      box.dataset.defaultTitle = h3.textContent;
      box.dataset.defaultText = p.textContent;
    }
    const oldBtn = box.querySelector('.tasks-retry');
    if (oldBtn) oldBtn.remove();
    if (!on) {
      h3.textContent = box.dataset.defaultTitle;
      p.textContent = box.dataset.defaultText;
      return;
    }
    h3.textContent = "We couldn't load your tasks";
    p.textContent = 'This is usually a connection hiccup. Your progress is safe.';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'cert-btn cert-btn-secondary tasks-retry';
    btn.textContent = 'Try again';
    btn.addEventListener('click', () => { btn.disabled = true; btn.textContent = 'Loading...'; retry(); });
    box.append(btn);
  }

  function renderTasks(tasks, templates, submissions, ctx) {
    const tasksList = document.getElementById('tasks-list');
    const tasksEmpty = document.getElementById('tasks-empty');
    const tasksCount = document.getElementById('tasks-count');
    if (!tasksList) return;

    tasksList.innerHTML = '';
    lastTasks = tasks && tasks.length ? tasks : null;
    const weekTabs = document.getElementById('task-week-tabs');
    if (weekTabs) weekTabs.innerHTML = '';

    if (tasks && tasks.length > 0) {
      if (tasksEmpty) tasksEmpty.style.display = 'none';
      if (tasksCount) tasksCount.textContent = `${tasks.length} Task${tasks.length !== 1 ? 's' : ''}`;

      const sortedTasks = [...tasks].sort((a, b) => (a.week_number || 0) - (b.week_number || 0));
      const statusForWeek = (w) => {
        const s = (submissions || []).find(x => Number(x.week) === Number(w));
        return s ? (s.status || 'pending').toLowerCase() : 'not_submitted';
      };
      const weeks = sortedTasks.map((t, i) => Number(t.week_number) || (i + 1));
      // The first week that still needs a submission is the "current" one.
      const activeWeek = weeks.find(w => ['not_submitted', 'rejected'].includes(statusForWeek(w))) || null;
      if (!weeks.includes(Number(selectedWeek))) selectedWeek = activeWeek || weeks[weeks.length - 1];

      const TAB_STATE = {
        approved: { cls: 'is-approved', text: 'Approved' },
        pending: { cls: 'is-pending', text: 'In review' },
        rejected: { cls: 'is-rejected', text: 'Needs changes' },
        not_submitted: { cls: '', text: 'Not started' },
      };
      const esc = escHtml;

      sortedTasks.forEach((task, i) => {
        const week = weeks[i];
        const diffLevel = { 'Beginner': 1, 'Beginner+': 2, 'Intermediate': 3, 'Intermediate+': 4 }[task.difficulty] || 3;
        const sub = (submissions || []).find(s => Number(s.week) === Number(week));
        const subStatus = sub ? (sub.status || 'pending').toLowerCase() : 'not_submitted';
        const caption = (templates && templates[String(week)]) || '';
        const isActive = Number(week) === Number(activeWeek);

        // Week tab
        if (weekTabs) {
          const st = TAB_STATE[subStatus] || TAB_STATE.not_submitted;
          const tab = document.createElement('button');
          tab.type = 'button';
          tab.className = `week-tab ${st.cls}${isActive && subStatus === 'not_submitted' ? ' is-next' : ''}`;
          tab.dataset.week = week;
          tab.setAttribute('role', 'tab');
          tab.innerHTML = `
            <span class="week-tab-top"><span class="week-tab-num">Week ${week}</span><span class="week-tab-dot" aria-hidden="true"></span></span>
            <span class="week-tab-title">${esc(task.title || `Week ${week} task`)}</span>
            <span class="week-tab-state">${isActive && subStatus === 'not_submitted' ? 'Up next' : st.text}</span>`;
          tab.addEventListener('click', () => selectTaskWeek(week));
          weekTabs.appendChild(tab);
        }

        let badgeClass = 'idle', badgeText = 'Not submitted';
        if (subStatus === 'pending') { badgeClass = 'open'; badgeText = 'Pending review'; }
        else if (subStatus === 'approved') { badgeClass = 'merged'; badgeText = 'Approved ✓'; }
        else if (subStatus === 'rejected') { badgeClass = 'failed'; badgeText = 'Needs changes'; }

        // Only a rejected (or never-submitted) task accepts a new link — the backend enforces the same rule.
        const isLocked = subStatus === 'approved' || subStatus === 'pending';
        const inputId = `sub-url-input-w${week}`;
        const btnId = `sub-submit-btn-w${week}`;
        const btnLabel = { approved: 'Approved ✓', pending: 'Under Review', rejected: 'Resubmit' }[subStatus] || 'Submit for Review';
        const guidance = {
          approved: { tone: 'ok', text: 'Approved — this task counts toward your progress. Nothing more to do here.' },
          pending: { tone: 'warn', text: "Your post is being reviewed. You'll be able to submit a new link only if it's rejected." },
          rejected: { tone: 'danger', text: 'This submission was rejected. Read the admin note, fix your LinkedIn post, then submit the new link below.' },
        }[subStatus];
        const dateStr = sub && sub.submitted_at ? new Date(sub.submitted_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '';
        const doneStep = isLocked ? ' is-done' : '';

        const card = document.createElement('div');
        card.className = `sub-card task-card is-${subStatus === 'approved' ? 'approved' : subStatus}${isActive ? ' is-active' : ''}`;
        card.dataset.week = week;
        card.setAttribute('role', 'tabpanel');
        card.innerHTML = `
          <div class="task-head">
            <div class="task-week"><small>Week</small><strong>${week}</strong></div>
            <div class="sub-info">
              <div class="sub-title">${esc(task.title || `Week ${week} Task`)}</div>
              <div class="sub-meta">
                <span class="diff diff-${diffLevel}">${esc(task.difficulty || 'Medium')}</span>
                ${task.est_hours ? `<span>~${esc(task.est_hours)} hrs</span>` : ''}
                ${dateStr ? `<span>Submitted ${dateStr}</span>` : ''}
              </div>
            </div>
            <span class="sub-status ${badgeClass}">${badgeText}</span>
          </div>
          ${guidance || (sub && sub.admin_note && subStatus === 'rejected') ? `
          <div class="task-alerts">
            ${guidance ? `<div class="task-guidance tone-${guidance.tone}">${guidance.text}</div>` : ''}
            ${sub && sub.admin_note && subStatus === 'rejected' ? `<div class="task-admin-note"><strong>Admin note:</strong> ${esc(sub.admin_note)}</div>` : ''}
          </div>` : ''}
          <ol class="task-steps">
            <li class="task-step${doneStep}">
              <span class="task-step-marker">1</span>
              <div class="task-step-main">
                ${task.description ? `
                <details class="task-step-details"${isLocked ? '' : ' open'}>
                  <summary><span class="task-step-title">Read the brief &amp; do the work</span><span class="task-step-toggle"></span></summary>
                  <div class="task-step-content dash-markdown">${renderMarkdown(task.description)}</div>
                </details>` : `<div class="task-step-title">Do the work</div><p class="task-step-desc">Follow the task in the PDF guide for this week.</p>`}
              </div>
            </li>
            <li class="task-step${doneStep}">
              <span class="task-step-marker">2</span>
              <div class="task-step-main">
                <div class="task-step-title">Share it on LinkedIn</div>
                <p class="task-step-desc">Post your work with screenshots or a short demo and tag <strong>@SkillMe</strong>. Put your project link inside the post or its first comment.</p>
                ${caption && !isLocked ? `
                <div class="task-caption-box">
                  <div class="task-caption-head">
                    <span class="task-caption-label">Suggested caption</span>
                    <button class="guide-code-copy" data-caption="${esc(caption)}" onclick="copyCode(this, this.getAttribute('data-caption'))">Copy Caption</button>
                  </div>
                  <pre data-lenis-prevent class="task-pre">${esc(caption)}</pre>
                </div>` : ''}
              </div>
            </li>
            <li class="task-step${doneStep}">
              <span class="task-step-marker">3</span>
              <div class="task-step-main">
                <div class="task-step-title">${isLocked ? 'Your submitted post' : 'Submit your post link'}</div>
                <div class="task-submit">
                  <div class="login-input-wrap">
                    <input type="url" id="${inputId}" placeholder="https://www.linkedin.com/posts/…" aria-label="LinkedIn post URL for week ${week}" aria-describedby="${inputId}-error" value="${sub && sub.linkedin_url ? esc(sub.linkedin_url) : ''}" ${isLocked ? 'disabled' : ''}>
                  </div>
                  <button id="${btnId}" class="cert-btn cert-btn-primary" ${isLocked ? 'disabled' : ''}
                    onclick="window.submitTaskForReview(${ctx ? ctx.studentId : 'null'}, ${ctx ? ctx.batchId : 'null'}, ${week}, this)">
                    ${btnLabel}
                  </button>
                </div>
                <p class="task-submit-error" id="${inputId}-error" role="alert" hidden></p>
                ${isLocked
                  ? (sub && sub.linkedin_url ? `<a class="task-view-post" href="${esc(sub.linkedin_url)}" target="_blank" rel="noopener noreferrer">View post on LinkedIn ↗</a>` : '')
                  : `<p class="task-hint">On your post, click <strong>⋯ → Copy link to post</strong>. GitHub, Figma, notebook or live-site links go inside the post, not here.</p>`}
              </div>
            </li>
          </ol>
          ${sub && sub.feedback ? `
          <details class="task-section">
            <summary>📝 Feedback for this submission</summary>
            <div class="task-section-body"><pre data-lenis-prevent class="task-pre">${esc(sub.feedback)}</pre></div>
          </details>` : ''}
        `;
        tasksList.appendChild(card);
        card.classList.add('visible');
      });

      // Arrow-key navigation between week tabs
      if (weekTabs && !weekTabs.dataset.keys) {
        weekTabs.dataset.keys = '1';
        weekTabs.addEventListener('keydown', (e) => {
          if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
          const tabs = [...weekTabs.querySelectorAll('.week-tab')];
          const idx = tabs.findIndex(t => t.classList.contains('is-selected'));
          const next = tabs[(idx + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
          if (next) { selectTaskWeek(next.dataset.week); next.focus(); }
        });
      }
      selectTaskWeek(selectedWeek);
    } else {
      if (tasksEmpty) tasksEmpty.style.display = 'block';
      if (tasksCount) tasksCount.textContent = '0 Tasks';
    }
    renderJourney(window._dashData, lastTasks);
    renderNextStep(window._dashData, tasks);
  }

  // Explain the common wrong-link cases (a Figma/GitHub/live-site link, or a profile link)
  // instead of a generic "invalid URL", since designers and cloud interns have several links.
  function linkedinPostUrlProblem(url) {
    const lower = url.toLowerCase();
    const where = 'Add it to your LinkedIn post (or its first comment), then paste the link to the post here.';
    if (!/^https:\/\/(www\.)?linkedin\.com\//i.test(url)) {
      if (lower.includes('figma.com')) return `That's your Figma link. ${where}`;
      if (lower.includes('github.com') || lower.includes('github.io')) return `That's a GitHub link. ${where}`;
      if (lower.includes('colab.research.google.com') || lower.includes('kaggle.com')) return `That's your notebook link. ${where}`;
      if (/amazonaws\.com|cloudfront\.net|netlify\.app|vercel\.app|onrender\.com|web\.app/.test(lower)) return `That looks like your live project link. ${where}`;
      if (lower.includes('lnkd.in')) return 'That\'s a shortened LinkedIn link. Open it in your browser and paste the full linkedin.com address instead.';
      return 'Please paste the link to your LinkedIn post. It starts with https://www.linkedin.com/';
    }
    if (/linkedin\.com\/in\/[^/]+\/?$/i.test(url)) {
      return 'That\'s your LinkedIn profile link, not a post. Open your post, click ⋯ → Copy link to post, and paste that here.';
    }
    return null;
  }

  // --- Submit a week's LinkedIn post URL for admin review ---
  window.submitTaskForReview = async function(studentId, batchId, week, btn) {
    const input = document.getElementById(`sub-url-input-w${week}`);
    const errEl = document.getElementById(`sub-url-input-w${week}-error`);
    // Problems with the link show right under the field, not in a pop-up.
    const showFieldError = (msg) => {
      if (errEl) { errEl.textContent = msg; errEl.hidden = !msg; }
      if (input) {
        if (msg) input.setAttribute('aria-invalid', 'true'); else input.removeAttribute('aria-invalid');
        if (msg) input.focus();
      }
    };
    if (input && !input.dataset.errWired) {
      input.dataset.errWired = '1';
      input.addEventListener('input', () => showFieldError(''));
    }
    if (!studentId || !batchId) {
      showFieldError("We couldn't find your enrollment. Please refresh the page and try again.");
      return;
    }
    const url = input ? input.value.trim() : '';
    if (!url) {
      showFieldError('Paste your LinkedIn post link first.');
      return;
    }
    const urlProblem = linkedinPostUrlProblem(url);
    if (urlProblem) {
      showFieldError(urlProblem);
      return;
    }
    showFieldError('');

    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Submitting...';

    try {
      const res = await fetch(`${API}/api/students/submit-task`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ student_id: studentId, batch_id: batchId, week, linkedin_url: url })
      });
      const resData = await res.json().catch(() => ({}));

      if (!res.ok) {
        if (res.status === 401) return sessionExpired();
        showFieldError(resData.detail || 'Could not submit for review. Please try again.');
        btn.disabled = false;
        btn.textContent = originalText;
        return;
      }
      dashToast(`Week ${week} submitted. We'll review it and email you.`);

      // Update local cache and re-render both the task card and the submissions history
      if (window._dashData) {
        window._dashData.submissions = window._dashData.submissions || [];
        const existingIdx = window._dashData.submissions.findIndex(s => Number(s.week) === Number(week));
        const newSub = {
          id: resData.submission_id,
          week,
          linkedin_url: url,
          status: resData.status || 'pending',
          admin_note: null,
          feedback: resData.feedback_text || null,
          submitted_at: new Date().toISOString(),
          reviewed_at: null
        };
        if (existingIdx >= 0) window._dashData.submissions[existingIdx] = newSub;
        else window._dashData.submissions.push(newSub);

        renderSubmissionsList(window._dashData.submissions);
        loadAndRenderTasks(window._dashData);
      }
    } catch (e) {
      showFieldError("We couldn't reach SkillMe. Check your connection and try again.");
      btn.disabled = false;
      btn.textContent = originalText;
    }
  };

  // A 401 mid-session: the token expired. Send the student back to sign in.
  function sessionExpired() {
    localStorage.removeItem('token');
    localStorage.removeItem('skillme_email');
    dashToast('Your session has expired. Please sign in again.', 'error');
    setTimeout(() => window.location.reload(), 1800);
  }

  // --- Staggered Entrance Animations ---
  function animateDashboardEntrance() {
    const delays = [
      ['dash-header-el', 0],
      ['stat-card-1', 40],
      ['stat-card-2', 80],
      ['stat-card-3', 120],
      ['stat-card-4', 160],
      ['progress-section-el', 200],
      ['guide-section-el', 240],
      ['tasks-section-el', 280],
      ['submissions-section-el', 320],
    ];

    delays.forEach(([id, delay]) => {
      const el = document.getElementById(id);
      if (el) {
        setTimeout(() => el.classList.add('visible'), delay);
      }
    });
  }

  // --- Guide: Copy to Clipboard ---
  window.copyCode = function(btn, text) {
    navigator.clipboard.writeText(text).then(() => {
      const orig = btn.textContent;
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.textContent = orig;
        btn.classList.remove('copied');
      }, 2000);
    }).catch(() => {
      // Fallback for older browsers
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;left:-9999px;';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.textContent = 'Copy';
        btn.classList.remove('copied');
      }, 2000);
    });
  };

  // --- Guide: Toggle Collapse ---
  window.toggleGuide = function() {
    const body = document.getElementById('guide-body');
    const btn = document.getElementById('guide-toggle-btn');
    const text = document.getElementById('guide-toggle-text');
    if (body.classList.contains('collapsed')) {
      body.classList.remove('collapsed');
      body.style.maxHeight = body.scrollHeight + 'px';
      body.style.opacity = '1';
      btn.classList.add('expanded');
      text.textContent = 'Hide Guide';
    } else {
      body.classList.add('collapsed');
      body.style.maxHeight = null;
      body.style.opacity = null;
      btn.classList.remove('expanded');
      text.textContent = 'Show Guide';
    }
  };

  // --- Animated Number Counter ---
  function animateValue(el, start, end, duration) {
    if (start === end) return;
    const range = end - start;
    const startTime = performance.now();
    
    function update(currentTime) {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      const current = Math.round(start + range * eased);
      el.textContent = current;
      if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
  }

  // ─────────────────────────────────────────────────────────────
    // 🏆🏆🏆 Payment Modal Helpers 🏆🏆🏆
    window.closePaymentModal = function() {
      const modal = document.getElementById('payment-modal');
      if (modal && modal.classList.contains('active')) {
        modal.classList.remove('active');
        setTimeout(() => modal.style.display = 'none', 400); // match transition duration
        modalClosed();
      }
    };
    
    window.showPaymentModal = function(student, data) {
      const modal = document.getElementById('payment-modal');
      if (modal) {
        // Wire up the pay button dynamically
        const payBtn = document.getElementById('modal-pay-btn');
        if (payBtn) {
          payBtn.onclick = () => window.initiatePayment(student.id, data._batch_id);
        }
        modal.style.display = 'flex';
        // Force reflow
        void modal.offsetWidth;
        modal.classList.add('active');
        modalOpened(modal);
      }
    };

    // 🏆🏆🏆 Razorpay Payment Helpers 🏆🏆🏆─────────────────────────────────
  // ─────────────────────────────────────────────────────────────

  function renderPaymentBanner(certSection, student, data) {
    certSection.style.display = 'block';
    certSection.innerHTML = `
      <div class="cert-banner" id="payment-banner">
        <div class="cert-banner-glow"></div>
        <div class="cert-banner-content">
          <div class="cert-banner-icon">✨</div>
          <div class="cert-banner-text">
            <div class="cert-banner-title">Your credentials are unlocked</div>
            <div class="cert-banner-sub">
              A one-time ₹129 covers your verified certificate, personalized LOR and lifetime hosting for your Proof of Work portfolio.
            </div>
          </div>
          <div class="cert-banner-actions" style="width: 100%;">
            <div class="cert-pay-row">
              <input type="text" id="discount-code" class="dash-input" placeholder="Have a discount code?">
              <button id="pay-btn" class="cert-btn cert-btn-primary" onclick="initiatePayment(${student.id}, ${data._batch_id})">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="15" height="15">
                  <rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/>
                </svg>
                Unlock My Certificate — ₹129
              </button>
            </div>
            <div class="secure-note">
              🔒 Secured by Razorpay · UPI / Card / NetBanking · Every certificate is independently verifiable
            </div>
          </div>
        </div>
      </div>`;
  }

  function renderCertReady(certSection, student, data) {
    const domain = (data.progress[0] && data.progress[0].domain) || 'web-dev';
    const certUrl = `${FRONTEND}/certificate.html?student_id=${student.id}&batch_id=${data._batch_id}&name=${encodeURIComponent(student.name)}&domain=${encodeURIComponent(domain)}`;
    const lorUrl  = `${FRONTEND}/lor.html?student_id=${student.id}&batch_id=${data._batch_id}&name=${encodeURIComponent(student.name)}&domain=${encodeURIComponent(domain)}`;
    const portfolioUrl = student.id ? `${FRONTEND}/portfolio.html?student_id=${student.id}` : '#';

    // ── Credential quick-strip (above banner) ─────────────────────────────────
    const credStrip = document.getElementById('cred-strip');
    if (credStrip) {
      credStrip.className = 'cred-strip visible';
      credStrip.innerHTML = `
        <a href="${certUrl}" target="_blank" class="cred-pill">
          <div class="cred-pill-icon">🎓</div>
          <div class="cred-pill-text">
            <div class="cred-pill-label">Certificate</div>
            <div class="cred-pill-name">View &amp; Download</div>
          </div>
          <svg class="cred-pill-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </a>
        <a href="${lorUrl}" target="_blank" class="cred-pill">
          <div class="cred-pill-icon tone-info">📄</div>
          <div class="cred-pill-text">
            <div class="cred-pill-label">Letter of Recommendation</div>
            <div class="cred-pill-name">View LOR</div>
          </div>
          <svg class="cred-pill-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </a>
        <a href="${portfolioUrl}" target="${portfolioUrl !== '#' ? '_blank' : '_self'}" class="cred-pill${portfolioUrl === '#' ? ' is-disabled' : ''}">
          <div class="cred-pill-icon tone-ok">🌐</div>
          <div class="cred-pill-text">
            <div class="cred-pill-label">Proof of Work</div>
            <div class="cred-pill-name">Public Portfolio</div>
          </div>
          <svg class="cred-pill-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </a>
      `;
    }

    // ── Certificate banner ────────────────────────────────────────────────────
    certSection.style.display = 'block';
    certSection.innerHTML = `
      <div class="cert-banner">
        <div class="cert-banner-glow"></div>
        <div class="cert-banner-content">
          <div class="cert-banner-icon">🏆</div>
          <div class="cert-banner-text">
            <div class="cert-banner-title">Your credentials are ready</div>
            <div class="cert-banner-sub">Payment confirmed — view, download and share them anywhere.</div>
          </div>
          <div class="cert-banner-actions">
            <a href="${certUrl}" target="_blank" class="cert-btn cert-btn-primary">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="15" height="15">
                <rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
                <polyline points="9 12 11 14 15 10"/>
              </svg>
              View Certificate
            </a>
            <a href="${lorUrl}" target="_blank" class="cert-btn cert-btn-secondary">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="15" height="15">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline>
              </svg>
              View LOR
            </a>
            ${portfolioUrl !== '#' ? `<a href="${portfolioUrl}" target="_blank" class="cert-btn cert-btn-secondary">Portfolio ↗</a>` : ''}
          </div>
        </div>
      </div>`;

    const modalBtn = document.getElementById('modal-pay-btn');
    if (modalBtn) {
      modalBtn.innerHTML = 'Paid &amp; Unlocked';
      modalBtn.disabled = true;
    }
  }

  // ─────────────────────────────────────────────────────────────
  // ⚡ Urgent (24h) Processing Request Panel
  // ─────────────────────────────────────────────────────────────
  async function loadUrgentRequestPanel(student, data, pct, paymentUnlocked) {
    const content = document.getElementById('urgent-request-content');
    if (!content) return;
    const urgentCard = document.getElementById('urgent-card');

    if (pct >= PAYMENT_UNLOCK_PCT) {
      // Credentials are claimable directly — no need to offer priority processing.
      if (urgentCard) urgentCard.hidden = true;
      content.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon tone-ok">
            <svg width="28" height="28" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          </div>
          <h3>Not Needed</h3>
          <p>You're at ${pct}% completion — you can claim your credentials directly, no request required.</p>
        </div>`;
      return;
    }

    if (paymentUnlocked) {
      content.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon tone-ok">
            <svg width="28" height="28" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          </div>
          <h3>Approved ✅</h3>
          <p>Your priority request was approved — you can now claim your credentials above.</p>
        </div>`;
      return;
    }

    if (!student.id || !data._batch_id) {
      content.innerHTML = `<div class="empty-state"><p>Missing enrollment info. Please refresh the page.</p></div>`;
      return;
    }

    try {
      const res = await fetch(`${API}/api/students/urgent-request/status/${student.id}/${data._batch_id}`, { headers: authHeaders() });
      const resData = await res.json().catch(() => ({}));
      renderUrgentRequestState(student, data, resData.request || null);
    } catch (e) {
      content.innerHTML = `<div class="empty-state"><p>Could not load request status. Please try again later.</p></div>`;
    }
  }

  function renderUrgentRequestState(student, data, request) {
    const content = document.getElementById('urgent-request-content');
    if (!content) return;

    const urgentCard = document.getElementById('urgent-card');
    if (urgentCard && request) urgentCard.open = true;

    if (!request) {
      content.innerHTML = `
        <div class="urgent-panel">
          <p class="urgent-intro">Haven't reached 3 approvals yet but need your Certificate, LOR or Portfolio urgently? Tell us what you need and our team will process it within 24 hours.</p>
          <div class="urgent-form">
            <div class="urgent-options" role="radiogroup" aria-label="What do you need processed?">
              <label class="urgent-option"><input type="radio" name="urgent-request-type" value="certificate" checked> Certificate</label>
              <label class="urgent-option"><input type="radio" name="urgent-request-type" value="lor"> Letter of Recommendation</label>
              <label class="urgent-option"><input type="radio" name="urgent-request-type" value="portfolio"> Portfolio</label>
              <label class="urgent-option"><input type="radio" name="urgent-request-type" value="all"> All three</label>
            </div>
            <textarea id="urgent-request-note" class="dash-input" placeholder="Optional note for the admin team..." rows="3"></textarea>
            <button id="urgent-request-submit-btn" class="cert-btn cert-btn-primary" onclick="window.submitUrgentRequest()">
              Request Priority Processing
            </button>
          </div>
        </div>`;
      return;
    }

    if (request.status === 'pending') {
      content.innerHTML = `
        <div class="urgent-panel">
          <div class="guide-header">
            <div class="guide-header-icon">⏳</div>
            <h2>Request submitted</h2>
          </div>
          <p class="guide-subtitle">Our team will process your <strong>${request.request_type}</strong> request within 24 hours.</p>
          <p class="urgent-meta">Submitted ${new Date(request.created_at).toLocaleString()}</p>
          ${request.note ? `<p class="urgent-meta"><strong>Your note:</strong> ${escHtml(request.note)}</p>` : ''}
        </div>`;
      return;
    }

    const statusLabel = request.status === 'fulfilled' ? 'Fulfilled ✅' : 'Rejected ❌';
    content.innerHTML = `
      <div class="urgent-panel">
        <div class="guide-header">
          <div class="guide-header-icon">${request.status === 'fulfilled' ? '✅' : '❌'}</div>
          <h2>${statusLabel}</h2>
        </div>
        <p class="guide-subtitle">Your <strong>${request.request_type}</strong> request was ${request.status} on ${request.resolved_at ? new Date(request.resolved_at).toLocaleString() : ''}.</p>
        ${request.admin_note ? `<p class="urgent-meta"><strong>Admin note:</strong> ${escHtml(request.admin_note)}</p>` : ''}
      </div>`;
  }

  window.submitUrgentRequest = async function() {
    const btn = document.getElementById('urgent-request-submit-btn');
    const student = window._dashStudent;
    const data = window._dashData;
    if (!student || !data || !student.id || !data._batch_id) {
      dashToast('Your dashboard is still loading. Please refresh the page.', 'error');
      return;
    }

    const typeInput = document.querySelector('input[name="urgent-request-type"]:checked');
    const requestType = typeInput ? typeInput.value : 'certificate';
    const noteInput = document.getElementById('urgent-request-note');
    const note = noteInput ? noteInput.value.trim() : '';

    if (btn) { btn.disabled = true; btn.textContent = 'Submitting...'; }

    try {
      const res = await fetch(`${API}/api/students/urgent-request`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ student_id: student.id, batch_id: data._batch_id, request_type: requestType, note: note || null })
      });
      const resData = await res.json().catch(() => ({}));

      if (!res.ok) {
        if (res.status === 401) return sessionExpired();
        dashToast(resData.detail || 'Could not submit request. Please try again.', 'error');
        if (btn) { btn.disabled = false; btn.textContent = 'Request Priority Processing'; }
        return;
      }
      dashToast('Request sent. We\'ll review it within 24 hours.');

      renderUrgentRequestState(student, data, {
        request_type: requestType,
        note: note || null,
        status: 'pending',
        admin_note: null,
        created_at: new Date().toISOString(),
        resolved_at: null
      });
    } catch (e) {
      dashToast("We couldn't reach SkillMe. Check your connection and try again.", 'error');
      if (btn) { btn.disabled = false; btn.textContent = 'Request Priority Processing'; }
    }
  };

  // Exposed globally so the onclick in the banner HTML can call it
  window.initiatePayment = async function(studentId, batchId) {
      const btn = document.getElementById('pay-btn');
      const modalBtn = document.getElementById('modal-pay-btn');
      const discountInputBanner = document.getElementById('discount-code');
      const discountInputMilestone = document.getElementById('discount-code-milestone');
      const discountCode = (discountInputBanner && discountInputBanner.value.trim()) || (discountInputMilestone && discountInputMilestone.value.trim()) || null;
      
      const PAY_LABEL = 'Unlock My Certificate — ₹129';
      const resetPayButtons = () => {
        if (btn) { btn.disabled = false; btn.textContent = PAY_LABEL; }
        if (modalBtn) { modalBtn.disabled = false; modalBtn.textContent = PAY_LABEL; }
      };
      // Charged but not confirmed: keep this on screen (not a pop-up) with what support needs.
      const showPaymentProblem = (title, paymentId) => {
        window.closePaymentModal();
        const certSection = document.getElementById('cert-section');
        if (!certSection) return dashToast(title, 'error');
        certSection.style.display = 'block';
        certSection.innerHTML = `<div class="cert-status-error" role="alert">
            <p><strong>${escHtml(title)}</strong> If money left your account, it is safe: write to
            <a href="mailto:admin@skill-me-intern.in?subject=${encodeURIComponent('Payment check ' + (paymentId || ''))}">admin@skill-me-intern.in</a>${paymentId ? ` with payment ID <code>${escHtml(paymentId)}</code>` : ''} and we'll sort it out.</p>
            <button type="button" class="cert-btn cert-btn-secondary" onclick="window.location.reload()">Refresh status</button>
          </div>`;
      };

      if (btn) { btn.disabled = true; btn.textContent = 'Creating order...'; }
      if (modalBtn) { modalBtn.disabled = true; modalBtn.textContent = 'Creating order...'; }

    try {
      // 1. Create Razorpay order on backend
      const orderRes = await fetch(`${API}/api/payments/create-order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ student_id: studentId, batch_id: batchId, discount_code: discountCode })
      });
      const orderData = await orderRes.json().catch(() => ({}));

      if (!orderRes.ok) {
        dashToast(orderData.detail || 'Could not start the payment. Please try again.', 'error');
        resetPayButtons();
        return;
      }

      // If already paid (edge case)
      if (orderData.already_paid) {
        const certSection = document.getElementById('cert-section');
        renderCertReady(certSection, window._dashStudent, window._dashData);
        window.closePaymentModal();
        return;
      }

      // 2. Load Razorpay script dynamically if not already present
      if (!window.Razorpay) {
        await new Promise((resolve, reject) => {
          const s = document.createElement('script');
          s.src = 'https://checkout.razorpay.com/v1/checkout.js';
          s.onload = resolve;
          s.onerror = () => reject(new Error('Failed to load Razorpay'));
          document.head.appendChild(s);
        });
      }

      // 3. Open Razorpay checkout modal
      const options = {
        key: orderData.key_id,
        amount: orderData.amount,
        currency: orderData.currency,
        name: "SkillMe Internship",
        description: "Verified Certificate & Portfolio Activation",
        order_id: orderData.order_id,
        prefill: {
          name: orderData.student_name,
          email: window._dashData._email || ''
        },
        theme: {
          color: "#e5322d"
        },
        modal: {
          ondismiss: function () {
            // User closed Razorpay popup without completing payment
            resetPayButtons();
          }
        },
        handler: async function (response) {
          // 4. Verify payment on backend
          if (btn) { btn.textContent = 'Verifying...'; }
          if (modalBtn) { modalBtn.textContent = 'Verifying...'; }
          try {
            const verifyRes = await fetch(`${API}/api/payments/verify`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                student_id: studentId,
                batch_id: batchId,
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature
              })
            });
            const verifyData = await verifyRes.json().catch(() => ({}));
            if (verifyRes.ok && verifyData.status === 'success') {
              // 5. Show download banner!
              const certSection = document.getElementById('cert-section');
              renderCertReady(certSection, window._dashStudent, window._dashData);
              window.closePaymentModal();
              dashToast('Payment confirmed. Your certificate is ready.');
            } else {
              showPaymentProblem("We couldn't confirm your payment yet.", response.razorpay_payment_id);
            }
          } catch(err) {
            showPaymentProblem('Your payment may have gone through, but we lost connection while confirming it.', response.razorpay_payment_id);
          }
        }
      };
      const rzp = new window.Razorpay(options);
      rzp.open();

    } catch(err) {
      console.error('Payment error:', err);
      dashToast('The payment service is unavailable right now. Please try again in a minute.', 'error');
      resetPayButtons();
    }
  };

  function renderDevPreviewBox(container, student, data) {
    if (!container) return;
    const devBox = document.createElement('div');
    devBox.className = 'dev-preview-box-container';
    devBox.style.marginBottom = '20px';
    devBox.innerHTML = `
      <details style="background: rgba(201, 154, 78, 0.08); border: 1px solid rgba(201, 154, 78, 0.3); border-radius: 10px; padding: 12px 18px; color: var(--text-primary);">
        <summary style="font-weight: 700; font-size: 0.88rem; cursor: pointer; color: var(--accent-indigo); display: flex; align-items: center; justify-content: space-between;">
          <span>⚙️ Developer Testing &amp; Preview Controls</span>
          <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 500;">Click to Expand</span>
        </summary>
        <div style="margin-top: 12px; font-size: 0.82rem; color: var(--text-secondary); line-height: 1.6;">
          <p style="margin-bottom: 10px;">You are testing in <strong>Developer Preview Mode</strong> (<code>?preview=1</code>). Select an action below to test UI states on-demand without blocking the dashboard:</p>
          <div style="display: flex; gap: 10px; flex-wrap: wrap;">
            <button onclick="showPaymentModal(window._dashStudent, window._dashData)" style="padding: 7px 15px; background: linear-gradient(135deg, #c99a4e, #b5873d); border: none; border-radius: 6px; color: #000; font-weight: 700; font-size: 0.8rem; cursor: pointer;">
              💳 Open Payment Modal Preview
            </button>
            <button onclick="renderCertReady(document.getElementById('cert-section'), window._dashStudent, window._dashData)" style="padding: 7px 15px; background: rgba(255, 255, 255, 0.06); border: 1px solid rgba(235, 230, 224, 0.2); border-radius: 6px; color: #fff; font-weight: 600; font-size: 0.8rem; cursor: pointer;">
              📜 Test Issued Certificate Banner
            </button>
          </div>
        </div>
      </details>
    `;
    container.prepend(devBox);
  }

  window.signOut = function() {
    localStorage.removeItem('token');
    localStorage.removeItem('skillme_email');
    localStorage.removeItem(APP_KEY);
    fetch(`${API}/api/auth/logout`, { method: 'POST' }).catch(() => {});
    window.location.reload();
  };

});


// ─── 100% Completion Celebration Popup ──────────────────────────────────────
function showCompletionPopup(student, data, pct) {
  const isFullyComplete = typeof pct === 'number' && pct >= 100;
  // Build credential URLs from available data
  const FRONTEND = window.SKILLME_FRONTEND || window.location.origin;
  const domain   = (data && data.progress && data.progress[0] && data.progress[0].domain) || 'web-dev';
  const batchId  = (data && data._batch_id) || '';
  const name     = (student && student.name) || '';
  const certUrl  = `${FRONTEND}/certificate.html?student_id=${student ? student.id : ''}&batch_id=${batchId}&name=${encodeURIComponent(name)}&domain=${encodeURIComponent(domain)}`;
  const lorUrl   = `${FRONTEND}/lor.html?student_id=${student ? student.id : ''}&batch_id=${batchId}&name=${encodeURIComponent(name)}&domain=${encodeURIComponent(domain)}`;
  const portfolioUrl = student ? `${FRONTEND}/portfolio.html?student_id=${student.id}` : '#';

  const flexPdfBtn = document.getElementById('flex-pdf-btn');
  if (flexPdfBtn && student) {
      flexPdfBtn.href = `/tasks?student_id=${student.id}&batch_id=${batchId}`;
  }

  // Create overlay
  const overlay = document.createElement('div');
  overlay.id = 'completion-overlay';
  overlay.className = 'completion-overlay';

  const firstName = (student && student.name) ? student.name.split(' ')[0] : 'Intern';

  overlay.innerHTML = `
    <div class="completion-card" role="dialog" aria-modal="true">
      <div class="completion-glow"></div>
      <div class="completion-trophy">🏆</div>
      <div class="completion-title">Congratulations, ${firstName}!</div>
      <div class="completion-text">
        ${isFullyComplete
          ? `You've completed <strong>100%</strong> of your internship tasks!`
          : `You've reached <strong>${pct}%</strong> completion — enough to unlock your credentials!`}<br>
        Your Certificate, LOR, and Portfolio are ready to claim.
      </div>

      <!-- Credential buttons — rendered by JS after payment check -->
      <div id="completion-cred-area" class="completion-cred-area">
        <div class="completion-loading">Checking payment status…</div>
      </div>

      <button onclick="document.getElementById('completion-overlay').remove()" class="completion-dismiss">Dismiss</button>

      <canvas id="confetti-canvas" class="completion-canvas"></canvas>
    </div>
  `;

  document.body.appendChild(overlay);
  requestAnimationFrame(() => overlay.style.opacity = '1');

  // Payment-gated credential area in popup
  (async () => {
    const credArea = overlay.querySelector('#completion-cred-area');
    if (!credArea || !student || !student.id || !batchId) return;
    try {
      const payStatus = await fetch(`${API}/api/payments/status/${student.id}/${batchId}`);
      const payData = await payStatus.json();
      if (payData.status === 'paid') {
        // Paid — show real credential links
        credArea.innerHTML = `
          <div class="completion-cred-grid">
            <button class="completion-cred-btn is-primary" onclick="window.open('${certUrl}','_blank');document.getElementById('completion-overlay').remove()"><span>🎓</span>Certificate</button>
            <button class="completion-cred-btn" onclick="window.open('${lorUrl}','_blank');document.getElementById('completion-overlay').remove()"><span>📄</span>View LOR</button>
            <button class="completion-cred-btn" ${portfolioUrl === '#' ? 'disabled' : ''} onclick="${portfolioUrl !== '#' ? `window.open('${portfolioUrl}','_blank');` : ''}document.getElementById('completion-overlay').remove()"><span>🌐</span>Portfolio</button>
          </div>`;
      } else {
        // Not paid — show pay CTA
        credArea.innerHTML = `
          <div class="completion-pay">
            <p>One-time ₹129 unlocks your Certificate, LOR &amp; Portfolio — verified, downloadable, and yours for life</p>
            <button class="cert-btn cert-btn-primary cert-btn-block" onclick="document.getElementById('completion-overlay').remove();setTimeout(()=>showPaymentModal(window._dashStudent,window._dashData),200);">Unlock My Certificate — ₹129</button>
          </div>`;
      }
    } catch(e) {
      credArea.innerHTML = `<div class="completion-loading">Could not load credentials. <a href="javascript:void(0)" onclick="document.getElementById('completion-overlay').remove()">Close</a> and check the dashboard.</div>`;
    }
  })();

  // Confetti burst
  const canvas = overlay.querySelector('#confetti-canvas');
  const ctx = canvas.getContext('2d');
  canvas.width = canvas.offsetWidth;
  canvas.height = canvas.offsetHeight;

  const particles = Array.from({length: 80}, () => ({
    x: Math.random() * canvas.width,
    y: Math.random() * canvas.height * -1,
    r: Math.random() * 5 + 2,
    d: Math.random() * 30 + 10,
    color: ['#ef3e36','#ff7a2f','#fbbf24','#a1a1aa','#4ade80'][Math.floor(Math.random()*5)],
    tilt: Math.floor(Math.random() * 10) - 10,
    tiltAngle: 0, tiltAngleInc: (Math.random() * 0.07) + 0.05
  }));

  let angle = 0, tick = 0;
  function drawConfetti() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    angle += 0.01; tick++;
    particles.forEach(p => {
      p.tiltAngle += p.tiltAngleInc;
      p.y += (Math.cos(angle + p.d) + 1 + p.r/2) * 1.2;
      p.x += Math.sin(angle);
      p.tilt = Math.sin(p.tiltAngle) * 12;
      ctx.beginPath();
      ctx.lineWidth = p.r;
      ctx.strokeStyle = p.color;
      ctx.moveTo(p.x + p.tilt + p.r/3, p.y);
      ctx.lineTo(p.x + p.tilt, p.y + p.tilt + p.r/5);
      ctx.stroke();
      if (p.y > canvas.height) { p.y = -10; p.x = Math.random() * canvas.width; }
    });
    if (document.getElementById('completion-overlay')) requestAnimationFrame(drawConfetti);
  }
  requestAnimationFrame(drawConfetti);

  // Auto-close after 8 seconds
  setTimeout(() => {
    if (document.getElementById('completion-overlay')) {
      overlay.style.opacity = '0';
      setTimeout(() => overlay.remove(), 400);
    }
  }, 8000);
}

// ═══════════════════════════════════════════════════════════════
// 🚀 Dynamic Milestone Share Engine (LinkedIn Submission Based)
// ═══════════════════════════════════════════════════════════════

let currentShareTab = 'linkedin';
let milestoneShareData = {
  linkedInText: '',
  whatsAppText: '',
  inviteLink: '',
  portfolioUrl: '',
  offerUrl: '',
  linkedinUrl: ''
};

/**
 * Display label, hashtags and a "what kind of work" phrase for a student's domain, so share
 * posts read right for designers and cloud interns as well as coders. Accepts any stored
 * domain value (slug like "ui-ux" or label like "UI/UX Design").
 */
function describeDomain(rawDomain) {
  const key = String(rawDomain || '').toLowerCase().replace(/[^a-z0-9+]/g, '');
  const DOMAINS = [
    // [match, label, hashtag, kind]
    ['uiux',        'UI/UX Design',       'UIUX',           'design'],
    ['design',      'UI/UX Design',       'UIUX',           'design'],
    ['genai',       'Generative AI',      'GenerativeAI',   'code'],
    ['generative',  'Generative AI',      'GenerativeAI',   'code'],
    ['cyber',       'Cybersecurity',      'CyberSecurity',  'code'],
    ['security',    'Cybersecurity',      'CyberSecurity',  'code'],
    ['datascien',   'Data Science',       'DataScience',    'code'],
    ['devops',      'DevOps / CI-CD',     'DevOps',         'code'],  // before cloud: old label "DevOps / Cloud"
    ['cloud',       'Cloud / AWS',        'AWS',            'cloud'],
    ['aws',         'Cloud / AWS',        'AWS',            'cloud'],
    ['react',       'Frontend Engineer',  'ReactJS',        'code'],
    ['node',        'Backend Engineer',   'NodeJS',         'code'],
    ['java',        'Java / Spring Boot', 'Java',           'code'],
    ['flutter',     'App Developer',      'Flutter',        'code'],
    ['mobile',      'App Developer',      'Flutter',        'code'],
    ['sql',         'SQL / Databases',    'SQL',            'code'],
    ['cpp',         'C++ / Algorithms',   'CPlusPlus',      'code'],
    ['c++',         'C++ / Algorithms',   'CPlusPlus',      'code'],
    ['machinelearning', 'Machine Learning', 'MachineLearning', 'code'],
    ['ml',          'Machine Learning',   'MachineLearning', 'code'],
    ['python',      'Python',             'Python',         'code'],
    ['aiengineer',  'AI Engineer',        'AIEngineering',  'code'],
    ['llmengineer', 'AI Engineer',        'AIEngineering',  'code'],
    ['fde',         'Forward Deployed Engineer', 'SoftwareEngineering', 'code'],
    ['forwarddeployed', 'Forward Deployed Engineer', 'SoftwareEngineering', 'code'],
    ['sde',         'SDE / SWE',          'SoftwareEngineering', 'code'],
    ['swe',         'SDE / SWE',          'SoftwareEngineering', 'code'],
    ['aipm',        'AI Product Management', 'ProductManagement', 'product'],
    ['productmanag', 'AI Product Management', 'ProductManagement', 'product'],
    ['qa',          'Software Quality',   'QualityAssurance', 'qa'],
    ['softwarequality', 'Software Quality', 'QualityAssurance', 'qa'],
    ['softwaretesting', 'Software Quality', 'QualityAssurance', 'qa'],
    ['web',         'Full Stack Engineer', 'WebDevelopment', 'code'],
  ];
  const hit = DOMAINS.find(([match]) => key === match || key.includes(match));
  const fallbackLabel = String(rawDomain || 'Tech').replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  const [, label, hashtag, kind] = hit || [null, fallbackLabel, fallbackLabel.replace(/[^a-zA-Z0-9]/g, '') || 'Tech', 'code'];
  const KINDS = {
    code:    { work: 'hands-on projects',        fieldHashtag: 'SoftwareEngineering' },
    design:  { work: 'hands-on design projects', fieldHashtag: 'UXDesign' },
    cloud:   { work: 'hands-on cloud projects',  fieldHashtag: 'CloudComputing' },
    product: { work: 'hands-on product work',    fieldHashtag: 'ProductManagement' },
    qa:      { work: 'hands-on testing projects', fieldHashtag: 'QualityAssurance' },
  };
  return { label, hashtag, ...KINDS[kind] };
}

/**
 * Resolves the milestone and task context dynamically from live dashboard data.
 * Data now comes from admin-approved LinkedIn submissions rather than merged
 * GitHub Pull Requests / closed issues (legacy).
 */
function resolveMilestoneContext(data) {
  const student = (data && data.student) || window._dashStudent || { name: 'Intern' };
  const rawSubmissions = (data && data.submissions) || [];
  const rawProgress = (data && data.progress) || [];
  const summary = (data && data.summary) || {};

  const totalAssigned = Number(summary.total_tasks) || 4;
  let totalCompleted = Number(summary.completed_tasks) || 0;
  let totalScore = 0;
  let maxWeek = 1;

  rawProgress.forEach(p => {
    totalScore += Number(p.score) || 0;
    maxWeek = Math.max(maxWeek, Number(p.week) || 1);
  });

  const approvedSubmissions = rawSubmissions.filter(s => (s.status || '').toLowerCase() === 'approved');
  if (totalCompleted === 0 && approvedSubmissions.length > 0) {
    totalCompleted = approvedSubmissions.length;
  }
  const totalApproved = approvedSubmissions.length;

  const domainInfo = describeDomain(student.domain || (rawProgress[0] && rawProgress[0].domain) || 'web-dev');
  const domain = domainInfo.label;
  const domainHashtag = domainInfo.hashtag;

  const PROD_BASE = 'https://www.skill-me-intern.in';
  const inviteLink = `${PROD_BASE}/apply`;
  // Portfolio pages are keyed off the student's ID.
  // The LinkedIn-based submission flow handles verification natively.
  const portfolioUrl = student.id ? `${PROD_BASE}/portfolio.html?student_id=${student.id}` : '#';
  const offerUrl = `${PROD_BASE}/offer.html?name=${encodeURIComponent(student.name || '')}&domain=${encodeURIComponent(domain)}&student_id=${student.id || ''}&ref=${encodeURIComponent(student.offer_ref || '')}&college=${encodeURIComponent(student.college || '')}`;
  const certUrl = `${PROD_BASE}/certificate.html?student_id=${student.id || ''}&domain=${encodeURIComponent(domain)}`;

  // Identify the latest approved LinkedIn submission (the "latest milestone")
  const sortedApproved = [...approvedSubmissions].sort((a, b) => (Number(b.week) || 0) - (Number(a.week) || 0));
  const latestSubmission = sortedApproved[0] || null;

  const hasCompletedTasks = (latestSubmission !== null) || (totalApproved > 0) || (totalCompleted > 0);
  const isAllComplete = (typeof summary.completion_pct === 'number' && summary.completion_pct >= 100)
    || (totalAssigned > 0 && totalCompleted >= totalAssigned);

  let weekNum = 1;
  let taskTitle = 'Weekly Task';
  let validatedLinkedinUrl = null;
  let latestTaskId = 0;

  if (latestSubmission) {
    weekNum = Number(latestSubmission.week) || 1;
    taskTitle = `Week ${weekNum} Task`;
    latestTaskId = latestSubmission.id || weekNum;
    if (latestSubmission.linkedin_url && /^https:\/\/(www\.)?linkedin\.com\//i.test(latestSubmission.linkedin_url)) {
      validatedLinkedinUrl = latestSubmission.linkedin_url;
    }
  }

  return {
    student,
    domain,
    domainHashtag,
    work: domainInfo.work,
    fieldHashtag: domainInfo.fieldHashtag,
    totalAssigned,
    totalCompleted,
    totalPrs: totalApproved,
    totalScore,
    maxWeek,
    hasCompletedTasks,
    isAllComplete,
    latestTaskId,
    weekNum,
    taskNum: weekNum,
    taskTitle,
    validatedLinkedinUrl,
    inviteLink,
    portfolioUrl,
    offerUrl,
    certUrl
  };
}

window.openMilestoneShareModal = function(customData) {
  const data = customData || window._dashData || {};
  const ctx = resolveMilestoneContext(data);

  let linkedInPost = '';
  let whatsAppInvite = '';
  let badgeText = '';
  let titleText = '';
  let subText = '';

  if (ctx.isAllComplete) {
    // ─── Case 1: 100% Completed Sprint ───
    badgeText = `🏆 INTERNSHIP COMPLETED`;
    titleText = `100% Milestone Completed!`;
    subText = `You've completed all tasks across the 4-week sprint. Share your achievement:`;

    const linkedinBlock = ctx.validatedLinkedinUrl
      ? `🔗 Final Verified Milestone Post:\n👉 ${ctx.validatedLinkedinUrl}\n\n`
      : '';

    linkedInPost = `I'm thrilled to announce that I have successfully completed the 4-week ${ctx.domain} Virtual Internship at SkillMe (@SkillMe)! 🎓🚀

Over the past month, I completed ${ctx.work} every week, got ${ctx.totalPrs} weekly submissions approved, and built verifiable Proof of Work. It was an incredible hands-on learning journey!

📊 Verified Sprint Summary:
• Track: ${ctx.domain}
• Progress: 100% Curriculum Completed (All 4 Weeks)
• Total Task Submissions Approved: ${ctx.totalPrs}
• XP Score: ${ctx.totalScore} pts
• Final Milestone Task: Week ${ctx.weekNum} — ${ctx.taskTitle}

${linkedinBlock}🌐 View my live Proof of Work portfolio:
👉 ${ctx.portfolioUrl}

📄 View my verified digital Certificate & LOR:
👉 ${ctx.certUrl}

Follow SkillMe on LinkedIn: https://www.linkedin.com/company/skill-me-intern/

#SkillMe #ProofOfWork #${ctx.domainHashtag} #${ctx.fieldHashtag} #TechInternship`;

    whatsAppInvite = `🏆 I just completed the SkillMe ${ctx.domain} internship with 100% tasks solved and ${ctx.totalPrs} submissions approved!

Check out my verified Proof of Work portfolio:
👉 ${ctx.portfolioUrl}

Join me on SkillMe and earn verified credentials for your resume:
👉 Join my SkillMe Squad: ${ctx.inviteLink}`;

  } else if (!ctx.hasCompletedTasks) {
    // ─── Case 2: 0 Submissions Approved (Offer Milestone) ───
    badgeText = `🎉 OFFICIAL OFFER UNLOCKED`;
    titleText = `You're Enrolled at SkillMe!`;
    subText = `Your official internship offer is confirmed. Share the news:`;

    linkedInPost = `I'm thrilled to share that I have been selected for the ${ctx.domain} Virtual Internship at SkillMe (@SkillMe)! 🚀

Over the next 4 weeks, I will be working on ${ctx.work}, sharing my progress on LinkedIn, and building verifiable Proof of Work.

🎯 Program Highlights:
• Track: ${ctx.domain}
• A new project milestone every week, reviewed by the SkillMe team
• MSME Recognized & Cryptographically Verifiable Credentials
• Lifetime Public Proof-of-Work Portfolio

📄 View my official verified digital Offer Letter:
👉 ${ctx.offerUrl}

Follow SkillMe on LinkedIn: https://www.linkedin.com/company/skill-me-intern/

#SkillMe #ProofOfWork #${ctx.domainHashtag} #${ctx.fieldHashtag} #TechInternship`;

    whatsAppInvite = `🚀 Hey! I've been selected for the SkillMe ${ctx.domain} Virtual Internship!

Check out my verified digital Offer Letter:
👉 ${ctx.offerUrl}

Join me to work on real projects and build verified Proof of Work for your resume:
👉 Join my SkillMe Squad: ${ctx.inviteLink}`;

  } else {
    // ─── Case 3: After Every Approved LinkedIn Submission / Task Completion ───
    badgeText = `🎉 SPRINT MILESTONE UNLOCKED`;
    titleText = `Week ${ctx.weekNum} Task Completed!`;
    subText = `Your LinkedIn submission for "${ctx.taskTitle}" was approved. Share your verifiable achievement:`;

    const linkedinBlock = ctx.validatedLinkedinUrl
      ? `🔗 Verified LinkedIn Milestone Post:\n👉 ${ctx.validatedLinkedinUrl}\n\n`
      : '';

    linkedInPost = `Week ${ctx.weekNum} task completed at SkillMe (@SkillMe)! 🚀

My submission for "${ctx.taskTitle}" was just approved for the ${ctx.domain} Virtual Internship.

At SkillMe, interns complete real-world projects week by week and build tamper-proof Proof of Work.

📊 Milestone Highlights:
• Milestone: Week ${ctx.weekNum} — ${ctx.taskTitle}
• Status: Submission Approved & Verified ✅
• Total Submissions Approved: ${ctx.totalPrs}
• Current Score: ${ctx.totalScore} pts

${linkedinBlock}🌐 View my live Proof of Work portfolio:
👉 ${ctx.portfolioUrl}

Follow SkillMe on LinkedIn: https://www.linkedin.com/company/skill-me-intern/

#SkillMe #ProofOfWork #${ctx.domainHashtag} #${ctx.fieldHashtag} #TechInternship`;

    whatsAppInvite = `🚀 Milestone update! My Week ${ctx.weekNum} submission ("${ctx.taskTitle}") at SkillMe was just approved!

${ctx.validatedLinkedinUrl ? `Check out my verified milestone post:\n👉 ${ctx.validatedLinkedinUrl}\n\n` : ''}View my live Proof of Work portfolio:
👉 ${ctx.portfolioUrl}

Join me on SkillMe to work on real projects and level up your resume:
👉 Join my SkillMe Sprint Squad: ${ctx.inviteLink}`;
  }

  milestoneShareData = {
    linkedInText: linkedInPost,
    whatsAppText: whatsAppInvite,
    inviteLink: ctx.inviteLink,
    portfolioUrl: ctx.portfolioUrl,
    offerUrl: ctx.offerUrl,
    linkedinUrl: ctx.validatedLinkedinUrl || ''
  };

  // Populate DOM elements
  const modal = document.getElementById('milestone-modal');
  if (!modal) return;

  const titleEl = document.getElementById('milestone-title');
  const badgeEl = document.getElementById('milestone-badge');
  const subEl = document.getElementById('milestone-sub');
  const prsEl = document.getElementById('modal-stat-prs');
  const scoreEl = document.getElementById('modal-stat-score');
  const weekEl = document.getElementById('modal-stat-week');

  if (titleEl) titleEl.textContent = titleText;
  if (badgeEl) badgeEl.textContent = badgeText;
  if (subEl) subEl.textContent = subText;
  if (prsEl) prsEl.textContent = ctx.totalPrs;
  if (scoreEl) scoreEl.textContent = `${ctx.totalScore} pts`;
  if (weekEl) weekEl.textContent = ctx.hasCompletedTasks ? `W${ctx.weekNum} · T${ctx.taskNum}` : `Week ${ctx.maxWeek}`;

  switchShareTab(currentShareTab);

  const actionsRow = modal.querySelector('.milestone-actions-row');
  if (actionsRow) {
    let offerBtn = document.getElementById('btn-view-offer');
    if (!ctx.hasCompletedTasks && ctx.offerUrl) {
      if (!offerBtn) {
        offerBtn = document.createElement('button');
        offerBtn.id = 'btn-view-offer';
        offerBtn.className = 'btn-share-main btn-share-offer';
        offerBtn.innerHTML = 'View Official Offer Letter 📄';
        actionsRow.parentElement.appendChild(offerBtn);
      }
      offerBtn.onclick = () => window.open(ctx.offerUrl, '_blank');
      offerBtn.style.display = 'block';
    } else {
      if (offerBtn) offerBtn.style.display = 'none';
    }
  }

  modal.style.display = 'flex';
  void modal.offsetWidth;
  modal.classList.add('active');
  modalOpened(modal);

  // Trigger Confetti
  triggerMilestoneConfetti();
};

window.closeMilestoneModal = function() {
  const modal = document.getElementById('milestone-modal');
  if (modal && modal.classList.contains('active')) {
    modal.classList.remove('active');
    setTimeout(() => { modal.style.display = 'none'; }, 350);
    modalClosed();
  }
};

window.switchShareTab = function(tab) {
  currentShareTab = tab;
  const tabLinkedin = document.getElementById('tab-btn-linkedin');
  const tabWhatsapp = document.getElementById('tab-btn-whatsapp');
  const previewBox = document.getElementById('milestone-post-preview');
  const mainShareBtn = document.getElementById('btn-main-share');
  const copyBtn = document.getElementById('btn-copy-share');

  if (tab === 'linkedin') {
    if (tabLinkedin) tabLinkedin.classList.add('active');
    if (tabWhatsapp) tabWhatsapp.classList.remove('active');
    if (previewBox) previewBox.textContent = milestoneShareData.linkedInText;
    if (mainShareBtn) {
      mainShareBtn.className = 'btn-share-main btn-share-linkedin';
      mainShareBtn.innerHTML = 'Share on LinkedIn ↗';
    }
    if (copyBtn) copyBtn.innerHTML = 'Copy Post Text 📋';
  } else {
    if (tabWhatsapp) tabWhatsapp.classList.add('active');
    if (tabLinkedin) tabLinkedin.classList.remove('active');
    if (previewBox) previewBox.textContent = milestoneShareData.whatsAppText;
    if (mainShareBtn) {
      mainShareBtn.className = 'btn-share-main btn-share-whatsapp';
      mainShareBtn.innerHTML = 'Invite via WhatsApp 💬';
    }
    if (copyBtn) copyBtn.innerHTML = 'Copy Invite Link 🔗';
  }
};

window.executeShareAction = function() {
  if (currentShareTab === 'linkedin') {
    navigator.clipboard.writeText(milestoneShareData.linkedInText).catch(() => {});
    const shareUrl = `https://www.linkedin.com/feed/?shareActive=true&text=${encodeURIComponent(milestoneShareData.linkedInText)}`;
    window.open(shareUrl, '_blank', 'noopener,noreferrer');
  } else {
    const waUrl = `https://api.whatsapp.com/send?text=${encodeURIComponent(milestoneShareData.whatsAppText)}`;
    window.open(waUrl, '_blank', 'noopener,noreferrer');
  }
};

window.copyShareContent = function() {
  const textToCopy = currentShareTab === 'linkedin' ? milestoneShareData.linkedInText : milestoneShareData.inviteLink;
  navigator.clipboard.writeText(textToCopy).then(() => {
    const copyBtn = document.getElementById('btn-copy-share');
    if (copyBtn) {
      const orig = copyBtn.innerHTML;
      copyBtn.innerHTML = 'Copied! ✅';
      copyBtn.style.borderColor = '#34d399';
      copyBtn.style.color = '#34d399';
      setTimeout(() => {
        copyBtn.innerHTML = orig;
        copyBtn.style.borderColor = '';
        copyBtn.style.color = '';
      }, 2000);
    }
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = textToCopy;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  });
};

function triggerMilestoneConfetti() {
  const canvas = document.getElementById('milestone-confetti-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  canvas.width = canvas.offsetWidth;
  canvas.height = canvas.offsetHeight;

  const particles = Array.from({ length: 65 }, () => ({
    x: Math.random() * canvas.width,
    y: Math.random() * canvas.height * -0.5,
    r: Math.random() * 4 + 2,
    d: Math.random() * 25 + 10,
    color: ['#ef3e36', '#ff7a2f', '#fbbf24', '#a1a1aa', '#4ade80'][Math.floor(Math.random() * 5)],
    tilt: Math.floor(Math.random() * 10) - 10,
    tiltAngle: 0,
    tiltAngleInc: Math.random() * 0.08 + 0.04
  }));

  let angle = 0;
  let tick = 0;
  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    angle += 0.01;
    tick++;
    particles.forEach(p => {
      p.tiltAngle += p.tiltAngleInc;
      p.y += (Math.cos(angle + p.d) + 1 + p.r / 2) * 1.3;
      p.x += Math.sin(angle);
      p.tilt = Math.sin(p.tiltAngle) * 10;
      ctx.beginPath();
      ctx.lineWidth = p.r;
      ctx.strokeStyle = p.color;
      ctx.moveTo(p.x + p.tilt + p.r / 3, p.y);
      ctx.lineTo(p.x + p.tilt, p.y + p.tilt + p.r / 5);
      ctx.stroke();
      if (p.y > canvas.height) {
        p.y = -10;
        p.x = Math.random() * canvas.width;
      }
    });
    const modal = document.getElementById('milestone-modal');
    if (modal && modal.classList.contains('active')) {
      requestAnimationFrame(draw);
    }
  }
  requestAnimationFrame(draw);
}



