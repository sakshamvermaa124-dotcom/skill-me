document.addEventListener('DOMContentLoaded', async () => {
  // Theme Toggle Logic
  const themeBtn = document.getElementById('theme-btn');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const savedTheme = localStorage.getItem('skillme_portfolio_theme');
  
  if (savedTheme === 'light' || (!savedTheme && !prefersDark)) {
    document.documentElement.setAttribute('data-theme', 'light');
  } else {
    document.documentElement.setAttribute('data-theme', 'dark');
  }

  themeBtn.addEventListener('click', () => {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('skillme_portfolio_theme', newTheme);
  });

  // Extract username from /p/{username}
  const pathParts = window.location.pathname.split('/');
  const username = pathParts[pathParts.length - 1] || pathParts[pathParts.length - 2];
  
  const container = document.getElementById('content-container');

  const urlParams = new URLSearchParams(window.location.search);
  const isPreview = urlParams.get('preview') === '1';

  if (!username || username === 'p') {
    if (!isPreview) {
      container.innerHTML = `
        <div class="locked-state">
          <div class="locked-icon">😕</div>
          <div class="locked-title">Invalid Profile Link</div>
          <div class="locked-text">We couldn't find a GitHub username in the URL. Make sure you're using a valid link.</div>
        </div>
      `;
      return;
    }
  }

  if (isPreview) {
      renderPortfolio({
          profile: { name: "Saksham Verma", github_username: "sakshamverma124", college: "IIT Delhi" },
          stats: { total_tasks_completed: 12, total_prs_merged: 12, total_score: 300 },
          domains: ["web-dev", "machine-learning"],
          submissions: [
              { title: "Implemented OAuth2 Login", merged_at: "2026-08-01T12:00:00Z", pr_url: "#", domain: "web-dev" },
              { title: "Fixed Memory Leak in ML Pipeline", merged_at: "2026-08-05T12:00:00Z", pr_url: "#", domain: "machine-learning" }
          ]
      });
      return;
  }

  try {
    // We assume the API runs on the same origin (FastAPI serving static files + API)
    const baseUrl = window.SKILLME_API || window.location.origin;
    const res = await fetch(`${baseUrl}/api/portfolio/${username}`);
    
    if (res.status === 403) {
      // Unpaid or not activated
      container.innerHTML = `
        <div class="locked-state">
          <div class="locked-icon">🔒</div>
          <div class="locked-title">Portfolio Not Activated</div>
          <div class="locked-text">
            This Proof of Work portfolio is currently private. 
            <br><br>
            If this is your profile, you can activate your lifetime public portfolio link by securely completing the certification payment on your SkillMe dashboard.
          </div>
          <a href="/dashboard" style="display:inline-block; padding:12px 24px; background:var(--accent-indigo); color:#111; text-decoration:none; border-radius:8px; font-weight:600; font-family:var(--font-display);">Go to Dashboard</a>
        </div>
      `;
      return;
    }

    if (res.status === 404) {
      container.innerHTML = `
        <div class="locked-state">
          <div class="locked-icon">🔍</div>
          <div class="locked-title">Profile Not Found</div>
          <div class="locked-text">We couldn't find an intern with the GitHub username <strong>${username}</strong>.</div>
        </div>
      `;
      return;
    }

    if (!res.ok) {
      throw new Error("Failed to fetch portfolio data");
    }

    const data = await res.json();
    renderPortfolio(data);
  } catch (e) {
    container.innerHTML = `
      <div class="locked-state">
        <div class="locked-icon">⚠️</div>
        <div class="locked-title">Something went wrong</div>
        <div class="locked-text">Failed to load the portfolio: ${e.message}</div>
      </div>
    `;
  }

  function renderPortfolio(data) {
    const p = data.profile;
    const s = data.stats;
    
    const domainTags = data.domains.map(d => `<span class="pr-domain">${d}</span>`).join(' ');

    const skillMap = {
      'web-dev': ['HTML', 'CSS', 'JavaScript', 'React', 'Node.js', 'Git', 'GitHub'],
      'python-dev': ['Python', 'FastAPI', 'Django', 'Git', 'GitHub'],
      'machine-learning': ['Python', 'PyTorch', 'TensorFlow', 'Scikit-Learn', 'Git', 'GitHub'],
      'data-science': ['Python', 'Pandas', 'NumPy', 'SQL', 'Git', 'GitHub'],
      'android-dev': ['Kotlin', 'Android Studio', 'Java', 'Git', 'GitHub'],
      'java-dev': ['Java', 'Spring Boot', 'SQL', 'Git', 'GitHub']
    };
    
    let studentSkills = new Set();
    data.domains.forEach(d => {
      const skills = skillMap[d] || ['Git', 'GitHub', 'Open Source'];
      skills.forEach(skill => studentSkills.add(skill));
    });
    const skillsHtml = Array.from(studentSkills).map(skill => `<span style="padding:6px 12px; background:rgba(245, 158, 11, 0.1); color:var(--accent-indigo); border-radius:20px; font-size:0.85rem; font-weight:600; border:1px solid rgba(245, 158, 11, 0.2);">${skill}</span>`).join('');

    const submissionsHtml = data.submissions.length > 0 
      ? data.submissions.map(sub => {
          const dateStr = new Date(sub.merged_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
          const repoUrl = sub.pr_url ? sub.pr_url.split('/pull/')[0] : '#';
          const repoName = repoUrl !== '#' ? repoUrl.split('/').slice(-2).join('/') : 'Repository';
          return `
            <div class="pr-card">
              <div class="pr-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="18" cy="18" r="3"></circle>
                  <circle cx="6" cy="6" r="3"></circle>
                  <path d="M13 6h3a2 2 0 0 1 2 2v7"></path>
                  <line x1="6" y1="9" x2="6" y2="21"></line>
                </svg>
              </div>
              <div class="pr-content">
                <div class="pr-title"><a href="${sub.pr_url}" target="_blank" style="color:inherit;text-decoration:none;">${sub.title}</a></div>
                <div class="pr-meta" style="margin-bottom:8px;">
                  <span class="pr-badge">Merged</span>
                  <span>${dateStr}</span>
                  <span class="pr-domain">${sub.domain}</span>
                </div>
                <div class="pr-repo">
                  <a href="${repoUrl}" target="_blank" style="color:var(--accent-indigo);text-decoration:none;font-size:0.85rem;display:inline-flex;align-items:center;gap:4px;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path></svg>
                    ${repoName}
                  </a>
                </div>
              </div>
              <div style="color:var(--text-secondary);">
                <a href="${sub.pr_url}" target="_blank" style="color:inherit;">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="7" y1="17" x2="17" y2="7"></line>
                    <polyline points="7 7 17 7 17 17"></polyline>
                  </svg>
                </a>
              </div>
            </div>
          `;
        }).join('')
      : '<div style="color:var(--text-muted); text-align:center; padding: 24px;">No public PRs available yet.</div>';

    container.innerHTML = `
      <div class="profile-header">
        <div class="profile-name">${p.name}</div>
        <div class="profile-title">Verified Open Source Contributor at <span>SkillMe</span></div>
        <div style="display:flex; justify-content:center; gap:8px; margin-bottom:16px;">
          ${domainTags}
        </div>
        <div style="color:var(--text-secondary); font-size:0.95rem; margin-bottom: 32px;">
          ${p.college ? `<svg style="vertical-align:middle; margin-right:4px;" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg> ${p.college}` : ''}
        </div>
        
        <div style="max-width: 600px; margin: 0 auto;">
          <div style="font-size:0.9rem; color:var(--text-secondary); text-transform:uppercase; letter-spacing:1px; font-weight:600; margin-bottom:12px;">Verified Skills</div>
          <div style="display:flex; flex-wrap:wrap; justify-content:center; gap:8px;">
            ${skillsHtml}
          </div>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-value">${s.total_prs_merged}</div>
          <div class="stat-label">Pull Requests Merged</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${s.total_tasks_completed}</div>
          <div class="stat-label">Tasks Completed</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${s.total_score}</div>
          <div class="stat-label">Total Score</div>
        </div>
      </div>

      <div class="section-title">Recent Contributions</div>
      <div class="pr-feed">
        ${submissionsHtml}
      </div>
      
      <div style="margin-top: 60px; text-align:center; color:var(--text-muted); font-size:0.85rem; border-top: 1px solid rgba(255,255,255,0.05); padding-top:24px;">
        Powered by <a href="/" style="color:var(--text-secondary); text-decoration:none; font-weight:600;">SkillMe Internship</a>
      </div>
    `;
  }
});
