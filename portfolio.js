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

  if (!username || username === 'p') {
    container.innerHTML = `
      <div class="locked-state">
        <div class="locked-icon">😕</div>
        <div class="locked-title">Invalid Profile Link</div>
        <div class="locked-text">We couldn't find a GitHub username in the URL. Make sure you're using a valid link.</div>
      </div>
    `;
    return;
  }

  try {
    // We assume the API runs on the same origin (FastAPI serving static files + API)
    const baseUrl = window.location.origin;
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

    const submissionsHtml = data.submissions.length > 0 
      ? data.submissions.map(sub => {
          const dateStr = new Date(sub.merged_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
          return `
            <a href="${sub.pr_url}" target="_blank" class="pr-card">
              <div class="pr-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="18" cy="18" r="3"></circle>
                  <circle cx="6" cy="6" r="3"></circle>
                  <path d="M13 6h3a2 2 0 0 1 2 2v7"></path>
                  <line x1="6" y1="9" x2="6" y2="21"></line>
                </svg>
              </div>
              <div class="pr-content">
                <div class="pr-title">${sub.title}</div>
                <div class="pr-meta">
                  <span class="pr-badge">Merged</span>
                  <span>${dateStr}</span>
                  <span class="pr-domain">${sub.domain}</span>
                </div>
              </div>
              <div style="color:var(--text-secondary);">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="7" y1="17" x2="17" y2="7"></line>
                  <polyline points="7 7 17 7 17 17"></polyline>
                </svg>
              </div>
            </a>
          `;
        }).join('')
      : '<div style="color:var(--text-muted); text-align:center; padding: 24px;">No public PRs available yet.</div>';

    container.innerHTML = `
      <div class="profile-header">
        <div class="profile-avatar">
          <img src="https://github.com/${p.github_username}.png?size=240" alt="${p.name}">
        </div>
        <div class="profile-name">${p.name}</div>
        <div class="profile-title">Verified Open Source Contributor at <span>SkillMe</span></div>
        <div style="display:flex; justify-content:center; gap:8px; margin-bottom:24px;">
          ${domainTags}
        </div>
        <div style="color:var(--text-secondary); font-size:0.95rem;">
          ${p.college ? `<svg style="vertical-align:middle; margin-right:4px;" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg> ${p.college}` : ''}
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
