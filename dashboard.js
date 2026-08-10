// ============================================================
// SkillMe Student Dashboard - Premium Edition
// Lenis Smooth Scroll + Aurora UI + Glassmorphism
// ============================================================

// API base URL — reads from config.js (auto-detects local vs production)
const API = window.SKILLME_API || '${API}';
const FRONTEND = window.SKILLME_FRONTEND || '${FRONTEND}';

// --- Lenis Smooth Scrolling (from darkroomengineering/lenis) ---
let lenis;
if (typeof Lenis !== 'undefined') {
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
  const loginForm = document.getElementById('dash-login-form');
  const loginView = document.getElementById('login-view');
  const dashView = document.getElementById('dashboard-view');
  const errorEl = document.getElementById('login-error');
  const loginBtn = document.getElementById('login-btn');

  let loginState = 'email';

  // --- Auto-Login via existing HTTP-Only Cookie ---
  async function checkExistingSession() {
    const urlParams = new URLSearchParams(window.location.search);
    const isPreview = urlParams.get('preview') === '1' || urlParams.get('preview') === 'paid';
    
    // Bypass login entirely for preview mode
    if (isPreview) {
        const mockData = {
            student: { id: 999, name: "Saksham Verma", github: "sakshamverma124", domain: "Web Development" },
            progress: [{ week: 1, issues_completed: 4, issues_assigned: 4, prs_merged: 4, score: 100 }],
            submissions: [],
            _batch_id: 1,
            _email: "test@example.com"
        };
        renderDashboard(mockData);
        loginView.style.display = 'none';
        dashView.style.display = 'block';
        if (lenis) lenis.resize();
        animateDashboardEntrance();
        return;
    }

      try {
        const token = localStorage.getItem('token');
        if (!token) throw new Error("No token");
        
        const meRes = await fetch(`${API}/api/auth/me`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
      if (meRes.ok) {
        const me = await meRes.json();
        if (me.email) {
          loginBtn.disabled = true;
            loginBtn.textContent = 'Restoring Session...';
            const progressRes = await fetch(`${API}/api/students/progress/${encodeURIComponent(me.email)}`, {
              headers: { 'Authorization': `Bearer ${token}` }
            });
            if (progressRes.ok) {
            const data = await progressRes.json();
            data._email = me.email;
            renderDashboard(data);
            
            // Transition directly to dashboard
            loginView.style.opacity = '0';
            setTimeout(() => {
              loginView.style.display = 'none';
              dashView.style.display = 'block';
              setTimeout(() => {
                dashView.style.opacity = '1';
                dashView.style.transform = 'translateY(0)';
              }, 50);
            }, 400);
          } else {
              loginBtn.disabled = false;
              loginBtn.textContent = 'Continue';
          }
        }
      }
    } catch (e) {
      console.log("No active session found.");
    }
  }

  // Check on load
  checkExistingSession();

  // Login handler
  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const emailInput = document.getElementById('login-email');
    const otpInput = document.getElementById('login-otp');
    const email = emailInput.value.trim();
    const otp = otpInput.value.trim();

    errorEl.style.display = 'none';
    loginBtn.disabled = true;
    loginBtn.style.opacity = '0.7';
    loginBtn.textContent = 'Loading...';

    try {
      if (loginState === 'email') {
        const res = await fetch(`${API}/api/auth/request-otp`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email })
        });
        
        if (!res.ok) {
          const errData = await res.json().catch(() => ({ detail: 'Failed to request OTP' }));
          throw new Error(errData.detail || 'Failed to request OTP');
        }
        
        // Show OTP field
        document.getElementById('otp-wrap').style.display = 'block';
        emailInput.readOnly = true;
        loginState = 'otp';
        otpInput.focus();
        
      } else if (loginState === 'otp') {
        if (!otp) throw new Error('Please enter the 6-digit OTP');
        
        const authRes = await fetch(`${API}/api/auth/verify-otp`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, otp })
        });
        
        if (!authRes.ok) {
          const errData = await authRes.json().catch(() => ({ detail: 'Invalid OTP' }));
          throw new Error(errData.detail || 'Invalid or expired OTP');
        }

        const authData = await authRes.json();
        if (authData.token) {
          localStorage.setItem('token', authData.token);
        }

        // Successfully verified and cookie set. Now load dashboard data.
        const res = await fetch(`${API}/api/students/progress/${encodeURIComponent(email)}`, {
          headers: { 'Authorization': `Bearer ${authData.token}` }
        });
        
        if (!res.ok) {
          const errData = await res.json().catch(() => ({ detail: 'Something went wrong loading dashboard' }));
          throw new Error(errData.detail || 'Failed to load dashboard data');
        }

        const data = await res.json();
        data._email = email;  // store for cert URL
        renderDashboard(data);

        // Transition
        loginView.style.opacity = '0';
        loginView.style.transform = 'translateY(-20px)';
        loginView.style.transition = 'all 0.4s ease';

        setTimeout(() => {
          loginView.style.display = 'none';
          dashView.style.display = 'block';
          lenis.resize();
          animateDashboardEntrance();
        }, 400);
      }
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.style.display = 'block';
    } finally {
      loginBtn.disabled = false;
      loginBtn.style.opacity = '1';
      loginBtn.textContent = loginState === 'email' ? 'Get Login Code' : 'Verify & Login';
    }
  });

  // --- Render Dashboard ---
  async function renderDashboard(data) {
    const { student, progress, submissions } = data;
    
    // Store globally for Razorpay callback
    window._dashData = data;
    window._dashStudent = student;

    // Header
    const firstName = student.name.split(' ')[0];
    document.getElementById('dash-name').textContent = `Welcome back, ${firstName}`;

    if (student.github) {
      document.getElementById('dash-github').href = `https://github.com/${student.github}`;
    }

    // Progress
    let totalAssigned = 0, totalCompleted = 0, totalPrs = 0, totalScore = 0, maxWeek = 1;

    if (progress && progress.length > 0) {
      const latest = progress[progress.length - 1];
      document.getElementById('dash-domain').innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/></svg>
        ${(latest.domain || 'web-dev').replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}`;
      document.getElementById('dash-batch').innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/></svg>
        Batch ${latest.batch_number}`;

      // Calculate week based on batch start_date if available
      if (latest.start_date) {
        try {
          const startDate = new Date(latest.start_date);
          const diffDays = Math.floor((new Date() - startDate) / (1000 * 60 * 60 * 24));
          const calculatedWeek = Math.min(4, Math.max(1, Math.floor(diffDays / 7) + 1));
          maxWeek = Math.max(maxWeek, calculatedWeek);
        } catch(e) {}
      }

      // Update dynamic GitHub Repo Link in Beginner Guide Step 1
      if (latest.repo_name) {
        const org = 'skill-me-intern';
        const repoUrl = `https://github.com/${org}/${latest.repo_name}/issues`;
        const guideLink = document.querySelector('.guide-repo-link');
        if (guideLink) {
          guideLink.href = repoUrl;
          const subText = guideLink.querySelector('.guide-repo-link-sub');
          if (subText) subText.textContent = `github.com/${org}/${latest.repo_name}`;
        }
      }

      progress.forEach(p => {
        totalAssigned += p.issues_assigned || 0;
        totalCompleted += p.issues_completed || 0;
        totalPrs += p.prs_merged || 0;
        totalScore += p.score || 0;
        maxWeek = Math.max(maxWeek, p.week || 1);
      });

      // Store batch_id for certificate download
      data._batch_id = latest.batch_id || data._batch_id;
    }

    document.getElementById('stat-completed').textContent = totalCompleted;
    document.getElementById('stat-assigned').textContent = totalAssigned;
    document.getElementById('stat-prs').textContent = totalPrs;
    document.getElementById('stat-week').textContent = maxWeek;
    document.getElementById('stat-score').textContent = totalScore;

    // Progress ring + bar
    const pct = totalAssigned > 0 ? Math.round((totalCompleted / totalAssigned) * 100) : 0;
    document.getElementById('progress-pct').textContent = `${pct}%`;

    // Update description based on progress
    const descEl = document.getElementById('progress-desc');
    if (pct === 0) {
      descEl.textContent = "You're just getting started. Submit your first PR to see your progress update in real-time.";
    } else if (pct < 50) {
      descEl.textContent = `Great start! You've completed ${totalCompleted} out of ${totalAssigned} issues. Keep the momentum going!`;
    } else if (pct < 100) {
      descEl.textContent = `Impressive progress! ${totalCompleted} of ${totalAssigned} issues done. You're on track for a strong finish.`;
    } else {
      descEl.textContent = `Outstanding! You've completed all ${totalAssigned} assigned issues. You're a star intern!`;
    }

    // Animate ring after render
    setTimeout(async () => {
      const circumference = 2 * Math.PI * 52; // r=52
      const offset = circumference - (pct / 100) * circumference;
      const urlParams = new URLSearchParams(window.location.search);
      const isPreview = urlParams.get('preview') === '1';
      const isPaidPreview = urlParams.get('preview') === 'paid';
      
      document.getElementById('progress-ring').style.strokeDashoffset = offset;
      document.getElementById('progress-bar-inner').style.width = `${pct}%`;
      
      // ─── Certificate Banner (Payment Gated) ───
      const certSection = document.getElementById('cert-section');
      if (certSection) {
        if ((pct === 100 || isPreview || isPaidPreview) && student.id && data._batch_id) {
          if (isPaidPreview) {
              renderCertReady(certSection, student, data);
          } else if (isPreview) {
              renderPaymentBanner(certSection, student, data);
              showPaymentModal(student, data);
          } else {
            // Check if already paid
            try {
              const payStatus = await fetch(`${API}/api/payments/status/${student.id}/${data._batch_id}`);
              const payData = await payStatus.json();
              if (payData.status === 'paid') {
                renderCertReady(certSection, student, data);
              } else {
                renderPaymentBanner(certSection, student, data);
                showPaymentModal(student, data);
              }
            } catch(e) {
              renderPaymentBanner(certSection, student, data);
              showPaymentModal(student, data);
            }
          }
        } else if (pct > 0) {
          certSection.style.display = 'block';
          certSection.innerHTML = `
            <div class="cert-progress-hint">
              <div style="display:flex;align-items:center;gap:12px;">
                <div style="font-size:1.4rem;">&#128196;</div>
                <div>
                  <div style="font-weight:600;font-size:0.88rem;margin-bottom:2px;">Certificate unlocks at 100%</div>
                  <div style="font-size:0.78rem;color:var(--text-3);">${100-pct}% more to go — finish all your assigned issues to earn your certificate.</div>
                </div>
              </div>
              <div class="cert-mini-bar"><div class="cert-mini-fill" style="width:${pct}%"></div></div>
            </div>`;
        }
      }
    }, 600);


    // Submissions
    const subList = document.getElementById('sub-list');
    const subEmpty = document.getElementById('sub-empty');
    const subCount = document.getElementById('sub-count');
    subList.innerHTML = '';

    if (submissions && submissions.length > 0) {
      subEmpty.style.display = 'none';
      subCount.textContent = `${submissions.length} PR${submissions.length !== 1 ? 's' : ''}`;

      submissions.forEach((sub, i) => {
        const status = (sub.status || 'open').toLowerCase();
        const dateStr = sub.submitted_at
          ? new Date(sub.submitted_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
          : '';

        const card = document.createElement('div');
        card.className = 'sub-card';
        card.style.transitionDelay = `${i * 0.08}s`;
        card.innerHTML = `
          <div class="sub-dot ${status}"></div>
          <div class="sub-info">
            <div class="sub-title">${sub.issue_title || `Pull Request #${sub.pr_number || '?'}`}</div>
            <div class="sub-meta">
              <span>Week ${sub.week_number || '?'}</span>
              <span>${dateStr}</span>
            </div>
          </div>
          <span class="sub-status ${status}">${status}</span>
          ${sub.pr_url ? `<a href="${sub.pr_url}" target="_blank" class="sub-link" title="View PR">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
          </a>` : ''}
        `;
        subList.appendChild(card);
        subObserver.observe(card);
      });
    } else {
      subEmpty.style.display = 'block';
      subCount.textContent = '0 PRs';
    }

    // Render Assigned Tasks
    renderTasks(data.issues || []);
  }

  function renderTasks(issues) {
    const tasksList = document.getElementById('tasks-list');
    const tasksEmpty = document.getElementById('tasks-empty');
    const tasksCount = document.getElementById('tasks-count');
    if (!tasksList) return;

    tasksList.innerHTML = '';
    if (issues && issues.length > 0) {
      if (tasksEmpty) tasksEmpty.style.display = 'none';
      if (tasksCount) tasksCount.textContent = `${issues.length} Task${issues.length !== 1 ? 's' : ''}`;

      issues.forEach((task, i) => {
        const status = (task.status || 'open').toLowerCase();
        const diffColor = task.difficulty === 'easy' ? '#34d399' : (task.difficulty === 'medium' ? '#fbbf24' : '#f87171');
        const card = document.createElement('div');
        card.className = 'sub-card task-card';
        card.style.transitionDelay = `${i * 0.08}s`;
        card.innerHTML = `
          <div class="sub-dot ${status === 'completed' ? 'merged' : 'open'}"></div>
          <div class="sub-info">
            <div class="sub-title">${task.title || `Task #${task.github_issue_number || task.id}`}</div>
            <div class="sub-meta">
              <span>Week ${task.week_number || 1}</span>
              <span style="color:${diffColor};font-weight:600;">${(task.difficulty || 'medium').toUpperCase()}</span>
            </div>
          </div>
          <span class="sub-status ${status === 'completed' ? 'merged' : 'open'}">${status}</span>
          ${task.github_url ? `<a href="${task.github_url}" target="_blank" class="sub-link" title="Open GitHub Issue">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
          </a>` : ''}
        `;
        tasksList.appendChild(card);
      });
    } else {
      if (tasksEmpty) tasksEmpty.style.display = 'block';
      if (tasksCount) tasksCount.textContent = '0 Tasks';
    }
  }

  function signOut() {
    localStorage.removeItem('token');
    fetch(`${API}/api/auth/logout`, { method: 'POST' }).catch(() => {});
    window.location.reload();
  }
  window.signOut = signOut;

  // --- Staggered Entrance Animations ---
  function animateDashboardEntrance() {
    const delays = [
      ['dash-header-el', 0],
      ['stat-card-1', 100],
      ['stat-card-2', 180],
      ['stat-card-3', 260],
      ['stat-card-4', 340],
      ['progress-section-el', 450],
      ['guide-section-el', 600],
      ['submissions-section-el', 700],
    ];

    delays.forEach(([id, delay]) => {
      const el = document.getElementById(id);
      if (el) {
        setTimeout(() => el.classList.add('visible'), delay);
      }
    });
  }

  // --- Guide: Tab Switching ---
  window.switchGuideTab = function(tab) {
    // Toggle tab buttons
    document.querySelectorAll('.guide-tab').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    // Toggle panels
    document.querySelectorAll('.guide-panel').forEach(panel => {
      panel.classList.toggle('active', panel.id === `panel-${tab}`);
    });
  };

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
      btn.classList.remove('expanded');
      text.textContent = 'Show Guide';
    }
  };

  // --- Intersection Observer for Submission Cards ---
  const subObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        subObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

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
      if (modal) {
        modal.classList.remove('active');
        setTimeout(() => modal.style.display = 'none', 400); // match transition duration
      }
    };
    
    function showPaymentModal(student, data) {
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
      }
    }

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
            <div class="cert-banner-title">Internship Complete! Activate Your Profile</div>
            <div class="cert-banner-sub">
              A small fee of ₹129 is required to compensate for personalized LORs, verified certificate generation, automated task assignment infrastructure, and hosting your lifetime Proof of Work portfolio link.
            </div>
          </div>
          <div class="cert-banner-actions">
            <button id="pay-btn" class="cert-btn cert-btn-primary" onclick="initiatePayment(${student.id}, ${data._batch_id})">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="15" height="15">
                <rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/>
              </svg>
              Pay ₹129 &amp; Activate Everything
            </button>
            <div style="font-size:11px;color:var(--text-3,#666);margin-top:4px;text-align:center;">
              Secured by Razorpay · UPI / Card / NetBanking
            </div>
          </div>
        </div>
      </div>`;
  }

  function renderCertReady(certSection, student, data) {
    const email = data._email || '';
    const domain = (data.progress[0] && data.progress[0].domain) || 'web-dev';
    const certUrl = `${FRONTEND}/certificate.html?email=${encodeURIComponent(email)}&student_id=${student.id}&batch_id=${data._batch_id}&name=${encodeURIComponent(student.name)}&domain=${encodeURIComponent(domain)}`;
    const dlUrl   = `${API}/api/certificates/download/${student.id}/${data._batch_id}`;
    const portfolioUrl = `${FRONTEND}/p/${student.github || ''}`;
    
    certSection.style.display = 'block';
    certSection.innerHTML = `
      <div class="cert-banner">
        <div class="cert-banner-content">
          <div class="cert-banner-icon">✨</div>
          <div class="cert-banner-text">
            <div class="cert-banner-title">Congratulations! Everything is activated.</div>
            <div class="cert-banner-sub">Payment confirmed • Access your Proof of Work Portfolio, LOR, and Certificate below!</div>
          </div>
          <div class="cert-banner-actions" style="flex-wrap: wrap; gap: 8px;">
            <a href="${portfolioUrl}" target="_blank" class="cert-btn" style="background:var(--accent-indigo); color:#111; border:none; font-weight:700;">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="16" height="16">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line>
              </svg>
              View Public Portfolio
            </a>
            <a href="${certUrl}" target="_blank" class="cert-btn cert-btn-primary">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="15" height="15">
                <rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
                <polyline points="9 12 11 14 15 10"/>
              </svg>
              Certificate
            </a>
            <a href="${FRONTEND}/lor.html?cert_id=SM-${String(student.id).padStart(4,'0')}-${String(data._batch_id).padStart(4,'0')}" target="_blank" class="cert-btn cert-btn-secondary" style="border-color:#818cf8; color:#818cf8;">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="15" height="15">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>
              </svg>
              LOR
            </a>
            <a href="${dlUrl}" target="_blank" class="cert-btn cert-btn-secondary">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="15" height="15">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              Download PDF
            </a>
          </div>
        </div>
      </div>
    `;
  }

  // Exposed globally so the onclick in the banner HTML can call it
  window.initiatePayment = async function(studentId, batchId) {
    const btn = document.getElementById('pay-btn');
    const modalBtn = document.getElementById('modal-pay-btn');
    
    if (btn) { btn.disabled = true; btn.textContent = 'Creating order...'; }
    if (modalBtn) { modalBtn.disabled = true; modalBtn.textContent = 'Creating order...'; }

    try {
      // 1. Create Razorpay order on backend
      const orderRes = await fetch(`${API}/api/payments/create-order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ student_id: studentId, batch_id: batchId })
      });
      const orderData = await orderRes.json();

      if (!orderRes.ok) {
        alert(orderData.detail || 'Could not create payment order. Try again.');
        if (btn) { btn.disabled = false; btn.innerHTML = 'Pay ₹129 &amp; Activate Everything'; }
        if (modalBtn) { modalBtn.disabled = false; modalBtn.innerHTML = 'Pay ₹129 &amp; Activate Everything'; }
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
          color: "#4f46e5"
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
            const verifyData = await verifyRes.json();
            if (verifyRes.ok && verifyData.status === 'success') {
              // 5. Show download banner!
              const certSection = document.getElementById('cert-section');
              renderCertReady(certSection, window._dashStudent, window._dashData);
              window.closePaymentModal();
            } else {
              alert('Payment verification failed: ' + (verifyData.detail || 'Please contact support.'));
              if (btn) { btn.disabled = false; btn.innerHTML = 'Pay ₹129 &amp; Activate Everything'; }
              if (modalBtn) { modalBtn.disabled = false; modalBtn.innerHTML = 'Pay ₹129 &amp; Activate Everything'; }
            }
          } catch(err) {
            alert('Network error during verification. Your payment may have been processed — please refresh.');
            if (btn) { btn.disabled = false; btn.innerHTML = 'Pay ₹129 &amp; Activate Everything'; }
            if (modalBtn) { modalBtn.disabled = false; modalBtn.innerHTML = 'Pay ₹129 &amp; Activate Everything'; }
          }
        }
      };
      const rzp = new window.Razorpay(options);
      rzp.open();

    } catch(err) {
      console.error('Payment error:', err);
      alert('Payment service unavailable. Please try again.');
      if (btn) { btn.disabled = false; btn.innerHTML = '💳 Pay ₹249 &amp; Get Certificate'; }
    }
  };

});

