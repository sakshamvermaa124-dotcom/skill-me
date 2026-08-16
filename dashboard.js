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
  const urlParams = new URLSearchParams(window.location.search);
  const loginForm = document.getElementById('dash-login-form');
  const loginView = document.getElementById('login-view');
  const dashView = document.getElementById('dashboard-view');
  const errorEl = document.getElementById('login-error');
  const loginBtn = document.getElementById('login-btn');

  let loginState = 'email';

  // --- Auto-Login via Saved Session ---
  async function checkExistingSession() {
    const isPreview = urlParams.get('preview') === '1' || urlParams.get('preview') === 'paid' || urlParams.get('preview') === 'progress' || urlParams.get('preview') === 'milestone';
    
    // Bypass login entirely for preview mode
    if (isPreview) {
        const isProgress = urlParams.get('preview') === 'progress' || urlParams.get('preview') === 'milestone';
        const completedCount = isProgress ? 4 : 12;
        const mockData = {
            student: { id: 999, name: "Saksham Verma", github: "sakshamverma124", domain: "Web Development" },
            progress: [{ week: isProgress ? 1 : 4, issues_completed: completedCount, issues_assigned: 12, prs_merged: completedCount, score: isProgress ? 100 : 300 }],
            submissions: [],
            issues: [
              { id: 1, github_issue_number: 7, title: "Build the Navigation Bar", week_number: 1, difficulty: "easy", status: "completed", github_url: "https://github.com/sakshamvermaa124-dotcom/web-dev-batch-1/issues/7" },
              { id: 2, github_issue_number: 8, title: "Hero Section with Animation", week_number: 1, difficulty: "easy", status: "completed", github_url: "https://github.com/sakshamvermaa124-dotcom/web-dev-batch-1/issues/8" },
              { id: 3, github_issue_number: 9, title: "Responsive Card Grid", week_number: 1, difficulty: "medium", status: isProgress ? "open" : "completed", github_url: "https://github.com/sakshamvermaa124-dotcom/web-dev-batch-1/issues/9" }
            ],
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

    try {
      const token = localStorage.getItem('token');
      const savedEmail = localStorage.getItem('skillme_email');
      const signoutBtn = document.getElementById('signout-btn');
      
      // If we have a saved email in localStorage, restore progress directly
      const emailToUse = savedEmail || (async () => {
        if (!token) return null;
        const meRes = await fetch(`${API}/api/auth/me`, { headers: { 'Authorization': `Bearer ${token}` } });
        if (meRes.ok) { const me = await meRes.json(); return me.email; }
        return null;
      })();

      const resolvedEmail = await Promise.resolve(emailToUse);
      if (resolvedEmail) {
        loginBtn.disabled = true;
        loginBtn.textContent = 'Restoring Session...';
        
        // Show Sign Out button so user can abort if stuck
        if (signoutBtn) signoutBtn.style.display = 'inline-flex';
        
        const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
        const progressRes = await fetch(`${API}/api/students/progress/${encodeURIComponent(resolvedEmail)}`, { headers });
        
        // If user clicked sign out while fetch was pending, abort the restore process
        if (!localStorage.getItem('skillme_email') && !localStorage.getItem('token')) {
          if (signoutBtn) signoutBtn.style.display = 'none';
          return;
        }
        
        if (progressRes.ok) {
          const data = await progressRes.json();
          data._email = resolvedEmail;
          renderDashboard(data);
          
          loginView.style.display = 'none';
          dashView.style.display = 'block';
          dashView.style.opacity = '1';
          dashView.style.transform = 'translateY(0)';
          if (lenis) lenis.resize();
          return;
        } else {
          // If session email fails to load, clear saved session so user can re-login
          localStorage.removeItem('skillme_email');
          if (signoutBtn) signoutBtn.style.display = 'none';
        }
      }
      loginBtn.disabled = false;
      loginBtn.textContent = 'Get Login Code';
      if (document.getElementById('signout-btn')) document.getElementById('signout-btn').style.display = 'none';
    } catch (e) {
      console.log("No active session found.");
      loginBtn.disabled = false;
      loginBtn.textContent = 'Get Login Code';
      if (document.getElementById('signout-btn')) document.getElementById('signout-btn').style.display = 'none';
    }
  }

  // Check on load
  checkExistingSession().catch(err => {
    console.warn("Session check notice:", err);
  });

  const resendBtn = document.getElementById('resend-btn');
  if (resendBtn) {
    resendBtn.addEventListener('click', () => {
      const emailInput = document.getElementById('login-email');
      const email = emailInput.value.trim();
      if (!email) return;
      
      resendBtn.disabled = true;
      resendBtn.textContent = 'Sending...';
      errorEl.style.display = 'none';
      
      fetch(`${API}/api/auth/request-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      }).then(async (res) => {
        if (!res.ok) {
          const errData = await res.json().catch(() => ({ detail: 'Failed to resend OTP email' }));
          errorEl.textContent = errData.detail || 'Failed to resend OTP.';
          errorEl.style.display = 'block';
          resendBtn.textContent = 'Resend Code';
          resendBtn.disabled = false;
        } else {
          resendBtn.textContent = 'Code Sent!';
          setTimeout(() => {
            resendBtn.textContent = 'Resend Code';
            resendBtn.disabled = false;
          }, 30000); // 30 seconds cooldown
        }
      }).catch((err) => {
        errorEl.textContent = 'Network error while resending code.';
        errorEl.style.display = 'block';
        resendBtn.textContent = 'Resend Code';
        resendBtn.disabled = false;
      });
    });
  }

  // Login handler
  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const emailInput = document.getElementById('login-email');
    const otpInput = document.getElementById('login-otp');
    const email = emailInput.value.trim();
    const otp = otpInput.value.trim();

    errorEl.style.display = 'none';

    try {
      if (loginState === 'email') {
        if (!email) throw new Error('Please enter a valid email address');
        
        // INSTANT OPTIMISTIC UI: Reveal OTP field immediately on click
        document.getElementById('otp-wrap').style.display = 'block';
        emailInput.readOnly = true;
        loginState = 'otp';
        loginBtn.textContent = 'Verify OTP & Enter →';
        loginBtn.disabled = false;
        loginBtn.style.opacity = '1';
        otpInput.focus();

        // Dispatch background request for OTP code
        fetch(`${API}/api/auth/request-otp`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email })
        }).then(async (res) => {
          if (!res.ok) {
            const errData = await res.json().catch(() => ({ detail: 'Failed to send OTP email' }));
            errorEl.textContent = errData.detail || 'Failed to send OTP. Please try again.';
            errorEl.style.display = 'block';
          }
        }).catch((err) => {
          console.warn("Background OTP request notice:", err);
        });

      } else if (loginState === 'otp') {
        if (!otp) throw new Error('Please enter the 6-digit OTP code sent to your email');
        
        loginBtn.disabled = true;
        loginBtn.style.opacity = '0.7';
        loginBtn.textContent = 'Verifying Code...';

        const authRes = await fetch(`${API}/api/auth/verify-otp`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, otp })
        });
        
        if (!authRes.ok) {
          loginBtn.disabled = false;
          loginBtn.style.opacity = '1';
          loginBtn.textContent = 'Verify OTP & Enter →';
          const errData = await authRes.json().catch(() => ({ detail: 'Invalid OTP' }));
          throw new Error(errData.detail || 'Invalid or expired OTP');
        }

        const authData = await authRes.json();
        if (authData.token) {
          localStorage.setItem('token', authData.token);
        }
        localStorage.setItem('skillme_email', email);

        // Successfully verified. Now load student dashboard data.
        const res = await fetch(`${API}/api/students/progress/${encodeURIComponent(email)}`, {
          headers: { 'Authorization': `Bearer ${authData.token}` }
        });
        
        if (!res.ok) {
          const errData = await res.json().catch(() => ({ detail: 'Something went wrong loading dashboard' }));
          throw new Error(errData.detail || 'Failed to load dashboard data');
        }

        const data = await res.json();
        data._email = email;
        renderDashboard(data);

        // Transition to dashboard view
        loginView.style.opacity = '0';
        loginView.style.transform = 'translateY(-20px)';
        loginView.style.transition = 'all 0.4s ease';

        setTimeout(() => {
          loginView.style.display = 'none';
          dashView.style.display = 'block';
          dashView.style.opacity = '1';
          dashView.style.transform = 'translateY(0)';
          if (lenis) lenis.resize();
        }, 400);
      }
    } catch (err) {
      errorEl.textContent = err.message || 'An error occurred';
      errorEl.style.display = 'block';
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
    document.getElementById('dash-name').textContent = `Welcome back, ${firstName}`;

    if (student.github) {
      document.getElementById('dash-github').href = `https://github.com/${student.github}`;
    }

    const hodUrl = `offer.html?view=hod&student_id=${student.id || ''}&name=${encodeURIComponent(student.name || '')}&domain=${encodeURIComponent(student.domain || '')}&college=${encodeURIComponent(student.college || '')}`;
    const hodQuickLink = document.getElementById('dash-quick-hod');
    if (hodQuickLink) hodQuickLink.href = hodUrl;

    const hodBannerBtn = document.getElementById('dash-banner-hod-btn');
    if (hodBannerBtn) hodBannerBtn.href = hodUrl;

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
        const org = data.github_org || data.summary?.github_org || 'sakshamvermaa124-dotcom';
        const repoUrl = `https://github.com/${org}/${latest.repo_name}/issues`;
        const guideLink = document.querySelector('.guide-repo-link');
        if (guideLink) {
          guideLink.href = repoUrl;
          const subText = guideLink.querySelector('.guide-repo-link-sub');
          if (subText) subText.textContent = `github.com/${org}/${latest.repo_name}`;
        }
      }

      progress.forEach(p => {
        totalAssigned += Number(p.issues_assigned) || 0;
        totalCompleted += Number(p.issues_completed) || 0;
        totalPrs += Number(p.prs_merged) || 0;
        totalScore += Number(p.score) || 0;
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
    // Always divide by 12 (3 tasks × 4 weeks = full internship).
    // This prevents showing 100% when only Week 1 (3 tasks) is done.
    const cappedCompleted = Math.min(totalCompleted, 12);
    const pct = Math.min(100, Math.round((cappedCompleted / 12) * 100));
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
      // Show 100% completion celebration popup every time
      setTimeout(() => showCompletionPopup(student, data), 800);
    }

    // Animate ring after render
    setTimeout(async () => {
      const circumference = 2 * Math.PI * 52; // r=52
      const offset = circumference - (pct / 100) * circumference;
      const urlParams = new URLSearchParams(window.location.search);
      const isPreview = urlParams.get('preview') === '1';
      
      document.getElementById('progress-ring').style.strokeDashoffset = offset;
      document.getElementById('progress-bar-inner').style.width = `${pct}%`;

      // Update Sprint Milestone Step Cards
      const m1 = document.getElementById('milestone-w1');
      const m2 = document.getElementById('milestone-w2');
      const m3 = document.getElementById('milestone-w3');
      const m4 = document.getElementById('milestone-w4');
      if (m1 && m2 && m3 && m4) {
        [m1, m2, m3, m4].forEach(el => el.classList.remove('active', 'completed'));
        if (pct >= 100) {
          m1.classList.add('completed');
          m2.classList.add('completed');
          m3.classList.add('completed');
          m4.classList.add('completed');
        } else if (pct >= 75) {
          m1.classList.add('completed');
          m2.classList.add('completed');
          m3.classList.add('completed');
          m4.classList.add('active');
        } else if (pct >= 50) {
          m1.classList.add('completed');
          m2.classList.add('completed');
          m3.classList.add('active');
        } else if (pct >= 25) {
          m1.classList.add('completed');
          m2.classList.add('active');
        } else {
          m1.classList.add('active');
        }
      }
      
      // ─── Certificate Banner (Payment Gated) ───
      const certSection = document.getElementById('cert-section');
      if (certSection) {
        if (pct === 100 && student.id && data._batch_id) {
          if (isPreview && urlParams.get('preview') === 'paid') {
              renderCertReady(certSection, student, data);
          } else if (isPreview) {
              renderPaymentBanner(certSection, student, data);
          } else {
            // Production: ALWAYS verify payment server-side
            try {
              const payStatus = await fetch(`${API}/api/payments/status/${student.id}/${data._batch_id}`);
              const payData = await payStatus.json();
              if (payData.status === 'paid') {
                renderCertReady(certSection, student, data);
              } else {
                renderPaymentBanner(certSection, student, data);
              }
            } catch(e) {
              renderPaymentBanner(certSection, student, data);
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

      // ─── Automated Milestone Celebration Popup Trigger ───
      if (pct < 100 && (totalPrs > 0 || totalCompleted > 0 || urlParams.get('preview') === 'progress' || urlParams.get('preview') === 'milestone')) {
        const milestoneNum = Math.max(1, Math.floor(pct / 25) || 1);
        const milestoneSeenKey = `skillme_milestone_seen_${milestoneNum}_student_${student.id || 'guest'}`;
        if (!localStorage.getItem(milestoneSeenKey) || urlParams.get('preview') === 'milestone' || urlParams.get('preview') === 'progress') {
          setTimeout(() => {
            window.openMilestoneShareModal(data);
            if (urlParams.get('preview') !== 'milestone' && urlParams.get('preview') !== 'progress') {
              localStorage.setItem(milestoneSeenKey, 'true');
            }
          }, 850);
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
        // Add visible class immediately for the initial fade-in to prevent invisible cards
        setTimeout(() => card.classList.add('visible'), 50 * i);
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

  // --- Live PR Helper Interactive Generator ---
  window.updatePRHelper = function() {
    const issueInput = document.getElementById('pr-helper-issue-num');
    const descInput = document.getElementById('pr-helper-desc');
    const issueNum = (issueInput ? issueInput.value.trim().replace(/^#/, '') : '') || '1';
    const descText = (descInput ? descInput.value.trim() : '') || 'solve assigned task';
    const slug = descText.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'feature';

    const branchVal = document.getElementById('pr-val-branch');
    const commitVal = document.getElementById('pr-val-commit');
    const titleVal = document.getElementById('pr-val-title');
    const closeVal = document.getElementById('pr-val-close');

    if (branchVal) branchVal.textContent = `fix/issue-${issueNum}-${slug}`;
    if (commitVal) commitVal.textContent = `git commit -m "fix: resolve issue #${issueNum} - ${descText}"`;
    if (titleVal) titleVal.textContent = `fix: resolve issue #${issueNum} - ${descText}`;
    if (closeVal) closeVal.textContent = `Closes #${issueNum}`;
  };

  window.copyHelperVal = function(btn, elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const text = el.textContent.trim();
    window.copyCode(btn, text);
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
            <div class="cert-banner-title">Internship Complete! Activate Your Profile</div>
            <div class="cert-banner-sub">
              A small fee of ₹129 is required to compensate for personalized LORs, verified certificate generation, automated task assignment infrastructure, and hosting your lifetime Proof of Work portfolio link.
            </div>
          </div>
          <div class="cert-banner-actions" style="flex-direction: column; align-items: flex-start; gap: 8px;">
            <div style="display: flex; gap: 8px; width: 100%;">
              <input type="text" id="discount-code" placeholder="Discount Code (Optional)" style="padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-color); background: rgba(0,0,0,0.5); color: #fff; outline: none; font-size: 14px; width: 180px;">
              <button id="pay-btn" class="cert-btn cert-btn-primary" onclick="initiatePayment(${student.id}, ${data._batch_id})" style="flex: 1;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="15" height="15">
                  <rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/>
                </svg>
                Pay &amp; Activate Everything
              </button>
            </div>
            <div style="font-size:11px;color:var(--text-3,#666);margin-top:4px;text-align:center; width: 100%;">
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
    const lorUrl  = `${FRONTEND}/lor.html?student_id=${student.id}&batch_id=${data._batch_id}&name=${encodeURIComponent(student.name)}&domain=${encodeURIComponent(domain)}`;
    const portfolioUrl = student.github ? `${FRONTEND}/portfolio.html?gh=${student.github}` : '#';

    // ── Credential quick-strip (above banner) ─────────────────────────────────
    const credStrip = document.getElementById('cred-strip');
    if (credStrip) {
      credStrip.className = 'cred-strip visible';
      credStrip.innerHTML = `
        <a href="${certUrl}" target="_blank" class="cred-pill" style="border-color:rgba(212,168,83,0.25);">
          <div class="cred-pill-icon" style="background:rgba(212,168,83,0.12);color:#d4a853;">🎓</div>
          <div class="cred-pill-text">
            <div class="cred-pill-label">Certificate</div>
            <div class="cred-pill-name">View &amp; Download</div>
          </div>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="opacity:0.4;flex-shrink:0;"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </a>
        <a href="${lorUrl}" target="_blank" class="cred-pill" style="border-color:rgba(99,102,241,0.2);">
          <div class="cred-pill-icon" style="background:rgba(99,102,241,0.12);color:#a5b4fc;">📄</div>
          <div class="cred-pill-text">
            <div class="cred-pill-label">Letter of Recommendation</div>
            <div class="cred-pill-name">View LOR</div>
          </div>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="opacity:0.4;flex-shrink:0;"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </a>
        <a href="${portfolioUrl}" target="${portfolioUrl !== '#' ? '_blank' : '_self'}" class="cred-pill" style="border-color:rgba(52,211,153,0.2);${portfolioUrl === '#' ? 'opacity:0.5;pointer-events:none;' : ''}">
          <div class="cred-pill-icon" style="background:rgba(52,211,153,0.12);color:#34d399;">🌐</div>
          <div class="cred-pill-text">
            <div class="cred-pill-label">Proof of Work</div>
            <div class="cred-pill-name">Public Portfolio</div>
          </div>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="opacity:0.4;flex-shrink:0;"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </a>
      `;
    }

    // ── Certificate banner ────────────────────────────────────────────────────
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
            <a href="${portfolioUrl}" target="_blank" class="cert-btn" style="background:var(--accent-indigo); color:#fff; border:none; font-weight:700;">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="16" height="16">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line>
              </svg>
              Portfolio
            </a>
            <a href="${certUrl}" target="_blank" class="cert-btn cert-btn-primary">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="15" height="15">
                <rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
                <polyline points="9 12 11 14 15 10"/>
              </svg>
              Certificate
            </a>
            <a href="${lorUrl}" target="_blank" class="cert-btn cert-btn-secondary" style="border-color:rgba(201,154,78,0.4);">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="15" height="15">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
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
    const discountInput = document.getElementById('discount-code');
    const discountCode = discountInput ? discountInput.value.trim() : null;
    
    if (btn) { btn.disabled = true; btn.textContent = 'Creating order...'; }
    if (modalBtn) { modalBtn.disabled = true; modalBtn.textContent = 'Creating order...'; }

    try {
      // 1. Create Razorpay order on backend
      const orderRes = await fetch(`${API}/api/payments/create-order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ student_id: studentId, batch_id: batchId, discount_code: discountCode })
      });
      const orderData = await orderRes.json();

      if (!orderRes.ok) {
        alert(orderData.detail || 'Could not create payment order. Try again.');
        if (btn) { btn.disabled = false; btn.innerHTML = 'Pay &amp; Activate Everything'; }
        if (modalBtn) { modalBtn.disabled = false; modalBtn.innerHTML = 'Pay &amp; Activate Everything'; }
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
    const dashView = document.getElementById('dashboard-view');
    const loginView = document.getElementById('login-view');
    const signoutBtn = document.getElementById('signout-btn');
    
    if (dashView && loginView) {
      dashView.style.display = 'none';
      loginView.style.display = 'flex';
      loginView.style.opacity = '1';
      loginView.style.transform = 'translateY(0)';
      if (signoutBtn) signoutBtn.style.display = 'none';
      // Reset login form inputs
      const emailInput = document.getElementById('login-email');
      const otpWrap = document.getElementById('otp-wrap');
      const loginBtn = document.getElementById('login-btn');
      if (emailInput) { 
        emailInput.value = ''; 
        emailInput.readOnly = false; 
      }
      if (otpWrap) otpWrap.style.display = 'none';
      if (loginBtn) { 
        loginBtn.disabled = false; 
        loginBtn.style.opacity = '1';
        loginBtn.textContent = 'Get Login Code'; 
      }
      
      const resendBtn = document.getElementById('resend-btn');
      if (resendBtn) {
        resendBtn.disabled = false;
        resendBtn.textContent = 'Resend Code';
      }
      
      loginState = 'email';
    } else {
      window.location.href = 'dashboard.html';
    }
  };

});


// ─── 100% Completion Celebration Popup ──────────────────────────────────────
function showCompletionPopup(student, data) {
  // Build credential URLs from available data
  const FRONTEND = window.SKILLME_FRONTEND || window.location.origin;
  const email    = (data && data._email) || '';
  const domain   = (data && data.progress && data.progress[0] && data.progress[0].domain) || 'web-dev';
  const batchId  = (data && data._batch_id) || '';
  const name     = (student && student.name) || '';
  const certUrl  = `${FRONTEND}/certificate.html?email=${encodeURIComponent(email)}&student_id=${student ? student.id : ''}&batch_id=${batchId}&name=${encodeURIComponent(name)}&domain=${encodeURIComponent(domain)}`;
  const lorUrl   = `${FRONTEND}/lor.html?student_id=${student ? student.id : ''}&batch_id=${batchId}&name=${encodeURIComponent(name)}&domain=${encodeURIComponent(domain)}`;
  const portfolioUrl = (student && student.github) ? `${FRONTEND}/portfolio.html?gh=${student.github}` : '#';

  // Create overlay
  const overlay = document.createElement('div');
  overlay.id = 'completion-overlay';
  overlay.style.cssText = `
    position:fixed;inset:0;z-index:9999;
    background:rgba(0,0,0,0.75);backdrop-filter:blur(8px);
    display:flex;align-items:center;justify-content:center;
    opacity:0;transition:opacity 0.4s;
  `;

  const firstName = (student && student.name) ? student.name.split(' ')[0] : 'Intern';

  overlay.innerHTML = `
    <div style="
      background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);
      border:1px solid rgba(201,154,78,0.3);
      border-radius:24px;padding:44px 36px 36px;max-width:500px;width:92%;
      text-align:center;position:relative;overflow:hidden;
      box-shadow:0 0 80px rgba(201,154,78,0.15), 0 24px 64px rgba(0,0,0,0.5);
    ">
      <!-- Glow -->
      <div style="position:absolute;top:-40px;left:50%;transform:translateX(-50%);width:200px;height:200px;background:radial-gradient(circle,rgba(201,154,78,0.18) 0%,transparent 70%);pointer-events:none;"></div>

      <div style="font-size:3.2rem;margin-bottom:12px;position:relative;">🏆</div>
      <div style="font-family:'Space Grotesk',sans-serif;font-size:1.55rem;font-weight:800;color:#fff;margin-bottom:8px;position:relative;">
        Congratulations, ${firstName}!
      </div>
      <div style="font-size:0.9rem;color:rgba(255,255,255,0.6);line-height:1.6;margin-bottom:28px;position:relative;">
        You've completed <strong style="color:#c99a4e;">100%</strong> of your internship tasks!<br>
        Your credentials are now unlocked and ready to share.
      </div>

      <!-- Credential buttons — rendered by JS after payment check -->
      <div id="completion-cred-area" style="margin-bottom:12px;position:relative;">
        <div style="color:rgba(255,255,255,0.4);font-size:0.8rem;text-align:center;padding:16px;">
          Checking payment status…
        </div>
      </div>

      <button onclick="document.getElementById('completion-overlay').remove()" style="
        background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.5);
        border:1px solid rgba(255,255,255,0.1);border-radius:10px;padding:10px 28px;
        font-weight:500;font-size:0.85rem;cursor:pointer;width:100%;
        position:relative;transition:background 0.2s;
      " onmouseover="this.style.background='rgba(255,255,255,0.1)'" onmouseout="this.style.background='rgba(255,255,255,0.06)'">Dismiss</button>

      <canvas id="confetti-canvas" style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none;border-radius:24px;"></canvas>
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
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;">
            <button onclick="window.open('${certUrl}','_blank');document.getElementById('completion-overlay').remove()" style="background:linear-gradient(135deg,#c99a4e,#e8b96e);color:#000;border:none;border-radius:12px;padding:13px 8px;font-weight:700;font-size:0.78rem;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:6px;transition:transform 0.2s;" onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform=''"><span style="font-size:1.3rem;">🎓</span>Certificate</button>
            <button onclick="window.open('${lorUrl}','_blank');document.getElementById('completion-overlay').remove()" style="background:rgba(99,102,241,0.2);color:#a5b4fc;border:1px solid rgba(99,102,241,0.35);border-radius:12px;padding:13px 8px;font-weight:700;font-size:0.78rem;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:6px;transition:transform 0.2s;" onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform=''"><span style="font-size:1.3rem;">📄</span>View LOR</button>
            <button onclick="${portfolioUrl !== '#' ? `window.open('${portfolioUrl}','_blank');` : ''}document.getElementById('completion-overlay').remove()" style="background:rgba(52,211,153,0.15);color:#34d399;border:1px solid rgba(52,211,153,0.3);border-radius:12px;padding:13px 8px;font-weight:700;font-size:0.78rem;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:6px;transition:transform 0.2s;${portfolioUrl === '#' ? 'opacity:0.5;cursor:not-allowed;' : ''}" onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform=''"><span style="font-size:1.3rem;">🌐</span>Portfolio</button>
          </div>`;
      } else {
        // Not paid — show pay CTA
        credArea.innerHTML = `
          <div style="background:rgba(201,154,78,0.08);border:1px solid rgba(201,154,78,0.2);border-radius:14px;padding:18px;text-align:center;">
            <div style="font-size:0.85rem;color:rgba(255,255,255,0.6);margin-bottom:12px;">Activate your Certificate, LOR & Portfolio with a one-time fee of <strong style="color:#c99a4e;">₹129</strong></div>
            <button onclick="document.getElementById('completion-overlay').remove();setTimeout(()=>showPaymentModal(window._dashStudent,window._dashData),200);" style="background:linear-gradient(135deg,#c99a4e,#e8b96e);color:#000;border:none;border-radius:10px;padding:12px 28px;font-weight:700;font-size:0.88rem;cursor:pointer;width:100%;transition:opacity 0.2s;" onmouseover="this.style.opacity='0.9'" onmouseout="this.style.opacity='1'">💳 Pay & Activate Everything</button>
          </div>`;
      }
    } catch(e) {
      credArea.innerHTML = `<div style="color:rgba(255,255,255,0.4);font-size:0.8rem;text-align:center;padding:16px;">Could not load credentials. <a href="javascript:void(0)" onclick="document.getElementById('completion-overlay').remove()" style="color:#c99a4e;">Close</a> and check the dashboard.</div>`;
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
    color: ['#c99a4e','#e8b96e','#fff','#4f46e5','#34d399'][Math.floor(Math.random()*5)],
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
// 🚀 Automated 1-Click LinkedIn & WhatsApp Milestone Share Engine
// ═══════════════════════════════════════════════════════════════

let currentShareTab = 'linkedin';
let milestoneShareData = {
  linkedInText: '',
  whatsAppText: '',
  referralLink: '',
  portfolioUrl: ''
};

window.openMilestoneShareModal = function(customData) {
  const data = customData || window._dashData || {};
  const student = (data && data.student) || window._dashStudent || { name: 'Intern', github: 'developer' };
  const progress = (data && data.progress && data.progress[0]) || {};
  const prs = Number(progress.prs_merged) || 4;
  const score = Number(progress.score) || 100;
  const week = Number(progress.week) || 1;
  const domain = (progress.domain || student.domain || 'Web Development').replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  const batchNum = progress.batch_number || 1;
  
  const studentRefCode = `SKM-${student.id ? String(student.id).padStart(4, '0') : '2026'}`;
  const PROD_BASE = 'https://skill-me-intern.in';
  const referralLink = `${PROD_BASE}/apply.html?ref=${studentRefCode}`;
  const ghUser = (student.github || '').trim().replace(/^@/, '');
  const portfolioUrl = ghUser ? `${PROD_BASE}/portfolio.html?gh=${encodeURIComponent(ghUser)}` : PROD_BASE;
  const offerUrl = `${PROD_BASE}/offer.html?name=${encodeURIComponent(student.name || '')}&domain=${encodeURIComponent(student.domain || '')}`;

  // Format LinkedIn Post
  const linkedInPost = `🚀 Milestone ${week} Sprint Completed on SkillMe (@skill-me-intern)!

Proud to share that I have merged ${prs} verified Pull Requests and resolved core engineering tasks for the ${domain} technical internship!

📊 Verified Proof of Work Stats:
• Pull Requests Merged: ${prs}
• Engineering Score: ${score} pts
• Sprint Milestone: Week ${week} Complete
• Cryptographic Verification: Active

📄 View my verified digital Offer Letter:
👉 ${offerUrl}

Explore my live Proof of Work portfolio & codebase here:
👉 ${portfolioUrl}

Follow SkillMe on LinkedIn: https://www.linkedin.com/company/skill-me-intern/

#SkillMe #ProofOfWork #WebDevelopment #SoftwareEngineering #TechInternship #GitHub`;

  // Format WhatsApp Squad Invite
  const whatsAppInvite = `🚀 Hey! I just completed Milestone ${week} on the SkillMe ${domain} internship with ${prs} verified PRs merged!

Check out my verified offer letter:
👉 ${offerUrl}

Collaborate with me on real repositories and earn verified Proof of Work for your resume:
👉 Join my SkillMe Sprint Squad: ${referralLink}`;

  milestoneShareData = {
    linkedInText: linkedInPost,
    whatsAppText: whatsAppInvite,
    referralLink: referralLink,
    portfolioUrl: portfolioUrl,
    offerUrl: offerUrl
  };

  // Populate DOM elements
  const modal = document.getElementById('milestone-modal');
  if (!modal) return;

  const titleEl = document.getElementById('milestone-title');
  const badgeEl = document.getElementById('milestone-badge');
  const prsEl = document.getElementById('modal-stat-prs');
  const scoreEl = document.getElementById('modal-stat-score');
  const weekEl = document.getElementById('modal-stat-week');

  if (titleEl) titleEl.textContent = `Milestone ${week} Achieved: ${prs} PRs Merged!`;
  if (badgeEl) badgeEl.textContent = `🎉 SPRINT MILESTONE ${week} UNLOCKED`;
  if (prsEl) prsEl.textContent = prs;
  if (scoreEl) scoreEl.textContent = `${score} pts`;
  if (weekEl) weekEl.textContent = `Week ${week}`;

  switchShareTab(currentShareTab);

  modal.style.display = 'flex';
  void modal.offsetWidth;
  modal.classList.add('active');

  // Trigger Confetti
  triggerMilestoneConfetti();
};

window.closeMilestoneModal = function() {
  const modal = document.getElementById('milestone-modal');
  if (modal) {
    modal.classList.remove('active');
    setTimeout(() => { modal.style.display = 'none'; }, 350);
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
  const textToCopy = currentShareTab === 'linkedin' ? milestoneShareData.linkedInText : milestoneShareData.referralLink;
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
    color: ['#c99a4e', '#e8b96e', '#fff', '#38bdf8', '#34d399'][Math.floor(Math.random() * 5)],
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
