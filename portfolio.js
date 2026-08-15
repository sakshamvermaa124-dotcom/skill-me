document.addEventListener('DOMContentLoaded', async () => {
  const urlParams = new URLSearchParams(window.location.search);
  const pathParts = window.location.pathname.split('/').filter(Boolean);
  const pathUser = (pathParts.length >= 2 && pathParts[0] === 'p') ? pathParts[1] : (pathParts.length === 1 && pathParts[0] !== 'portfolio.html' && pathParts[0] !== 'p' ? pathParts[0] : null);
  const rawUsername = urlParams.get('gh') || urlParams.get('github') || urlParams.get('u') || pathUser || localStorage.getItem('student_github') || '';
  const username = rawUsername.trim().replace(/^@/, '');
  
  const container = document.getElementById('content-container');
  if (!container) return;
  const isPreview = urlParams.get('preview') === '1';

  if (!username || username === 'p' || username === 'portfolio.html') {
    if (!isPreview) {
      container.innerHTML = `
        <div class="locked-card">
          <div class="locked-icon-wrap">🔍</div>
          <div class="locked-title">Invalid Profile Link</div>
          <div class="locked-desc">We couldn't find a valid GitHub username in the URL. Access your verified profile using a link formatted like <code>/portfolio.html?gh=YOUR_GITHUB_USERNAME</code>.</div>
          <a href="dashboard.html" class="nav-btn nav-btn-apply" style="display:inline-flex;">Go to Student Dashboard &rarr;</a>
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
        { title: "feat(auth): implemented OAuth2 JWT authentication pipeline", merged_at: "2026-08-12T14:30:00Z", pr_url: "https://github.com/sakshamvermaa124-dotcom/web-dev-batch-1/pull/14", domain: "web-dev" },
        { title: "fix(pipeline): resolved memory leak in streaming telemetry worker", merged_at: "2026-08-08T10:15:00Z", pr_url: "https://github.com/sakshamvermaa124-dotcom/web-dev-batch-1/pull/9", domain: "machine-learning" },
        { title: "perf(db): optimized Turso SQLite indexing for async query latency", merged_at: "2026-08-04T18:00:00Z", pr_url: "https://github.com/sakshamvermaa124-dotcom/web-dev-batch-1/pull/4", domain: "web-dev" }
      ]
    });
    return;
  }

  try {
    const baseUrl = window.SKILLME_API || window.location.origin;
    const res = await fetch(`${baseUrl}/api/portfolio/${encodeURIComponent(username)}`);
    
    if (res.status === 403) {
      container.innerHTML = `
        <div class="locked-card">
          <div class="locked-icon-wrap">🔒</div>
          <div class="locked-title">Portfolio Currently Private</div>
          <div class="locked-desc">
            This Proof of Work portfolio is currently private.
            <br><br>
            If this is your account, complete your verified internship milestones or activate your credential pass on your Student Dashboard to unlock your public link.
          </div>
          <a href="dashboard.html" class="nav-btn nav-btn-apply" style="display:inline-flex;">Log In to Dashboard &rarr;</a>
        </div>
      `;
      return;
    }

    if (res.status === 404) {
      container.innerHTML = `
        <div class="locked-card">
          <div class="locked-icon-wrap">😕</div>
          <div class="locked-title">Profile Not Found</div>
          <div class="locked-desc">We couldn't locate an engineering portfolio registered for GitHub username <strong>@${username}</strong>.</div>
          <a href="index.html" class="nav-btn nav-btn-dash" style="display:inline-flex; margin-top:12px;">Back to Home &rarr;</a>
        </div>
      `;
      return;
    }

    if (!res.ok) throw new Error("Failed to load portfolio details.");

    const data = await res.json();
    renderPortfolio(data);
  } catch (e) {
    container.innerHTML = `
      <div class="locked-card">
        <div class="locked-icon-wrap">⚠️</div>
        <div class="locked-title">Unable to Load Portfolio</div>
        <div class="locked-desc">${e.message}</div>
        <a href="dashboard.html" class="nav-btn nav-btn-dash" style="display:inline-flex;">Go to Dashboard</a>
      </div>
    `;
  }

  function renderPortfolio(data) {
    const p = data.profile || {};
    const s = data.stats || {};
    const domains = data.domains || ['web-dev'];
    const submissions = data.submissions || [];

    // Title Case Name
    const rawName = p.name || 'Open Source Contributor';
    const name = rawName
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .replace(/[_-]/g, ' ')
      .replace(/\s+/g, ' ').trim()
      .split(' ')
      .map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
      .join(' ');

    // Extract Monogram Initials
    const initials = name
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map(w => w.charAt(0).toUpperCase())
      .join('') || 'SM';

    const gh = p.github_username || username || 'developer';
    const college = p.college || '';

    // Domain Tags
    const domainTagsHtml = domains.map(d => {
      const label = d.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
      return `<span class="domain-tag">${label}</span>`;
    }).join('');

    // Skills Mapping
    const skillMap = {
      'web-dev': ['JavaScript', 'TypeScript', 'React.js', 'Node.js', 'REST APIs', 'Git', 'GitHub Actions', 'CI/CD'],
      'python-dev': ['Python', 'FastAPI', 'PyTest', 'AsyncIO', 'Git', 'GitHub', 'CI/CD'],
      'machine-learning': ['Python', 'PyTorch', 'Scikit-Learn', 'Data Pipelines', 'Git', 'GitHub'],
      'data-science': ['Python', 'Pandas', 'NumPy', 'SQL', 'Data Modeling', 'Git'],
      'android-dev': ['Kotlin', 'Android SDK', 'Jetpack Compose', 'Git', 'GitHub'],
      'java-dev': ['Java', 'Spring Boot', 'SQL', 'Microservices', 'Git']
    };

    const studentSkills = new Set();
    domains.forEach(d => {
      const list = skillMap[d] || ['Git', 'GitHub', 'Open Source', 'CI/CD'];
      list.forEach(skill => studentSkills.add(skill));
    });
    const skillsHtml = Array.from(studentSkills).map(skill => `<span class="skill-pill">${skill}</span>`).join('');

    // Recent PR Submissions
    const submissionsHtml = submissions.length > 0
      ? submissions.map(sub => {
          const rawTs = sub.merged_at || sub.submitted_at || null;
          const rawDate = rawTs ? (rawTs.includes('T') ? rawTs.split('T')[0] : rawTs.split(' ')[0]) : null;
          const dateStr = rawDate
            ? new Date(rawDate + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
            : 'Verified Contribution';
          const repoUrl = sub.pr_url ? sub.pr_url.split('/pull/')[0] : '#';
          const repoName = repoUrl !== '#' ? repoUrl.split('/').slice(-2).join('/') : 'SkillMe Production Repo';
          const prNumber = sub.pr_url ? sub.pr_url.split('/pull/')[1] || '1' : '1';
          const domainLabel = (sub.domain || 'web-dev').replace(/-/g, ' ').toUpperCase();

          return `
            <a href="${sub.pr_url || '#'}" target="_blank" rel="noopener noreferrer" class="pr-bento-card">
              <div class="pr-left-col">
                <div class="pr-git-icon">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="18" r="3"></circle><circle cx="6" cy="6" r="3"></circle><path d="M13 6h3a2 2 0 0 1 2 2v7"></path><line x1="6" y1="9" x2="6" y2="21"></line></svg>
                </div>
                <div class="pr-main-content">
                  <div class="pr-title-text">${sub.title || 'Resolved Assigned Technical Issue'}</div>
                  <div class="pr-meta-row">
                    <span class="badge-pr-status">● Merged #${prNumber}</span>
                    <span class="badge-repo-name">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>
                      ${repoName}
                    </span>
                    <span>&bull;</span>
                    <span>${dateStr}</span>
                    <span>&bull;</span>
                    <span style="color:#f0c97a; font-weight:700;">${domainLabel}</span>
                  </div>
                </div>
              </div>
              <div class="pr-right-action">
                <span>View on GitHub</span>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="7" y1="17" x2="17" y2="7"></line><polyline points="7 7 17 7 17 17"></polyline></svg>
              </div>
            </a>
          `;
        }).join('')
      : `
        <div style="background:var(--bg-surface); border:1px dashed var(--border-subtle); border-radius:14px; padding:40px; text-align:center; color:var(--text-muted);">
          <div style="font-size:24px; margin-bottom:8px;">📦</div>
          <div style="font-weight:700; color:#f8fafc; margin-bottom:4px;">Contributions Syncing Live</div>
          <div style="font-size:0.85rem;">Merged Pull Requests will automatically populate here in real-time as GitHub webhooks sync.</div>
        </div>
      `;

    const fullUrl = `https://skill-me-intern.in/portfolio.html?gh=${encodeURIComponent(gh)}`;

    container.innerHTML = `
      <!-- Hero Header Bento Card -->
      <section class="profile-hero-card">
        <div class="hero-top-row">
          <div class="hero-profile-info">
            <div class="avatar-monogram">
              ${initials}
              <div class="avatar-online-dot" title="Active Contributor"></div>
            </div>
            <div class="hero-meta">
              <div class="hero-badges-row">
                <span class="badge-verified-eng">✓ Verified Open-Source Contributor</span>
                ${college ? `<span class="badge-college"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg> ${college}</span>` : ''}
              </div>
              <h1 class="hero-name">${name}</h1>
              <div class="hero-role-line">
                <span>Engineering Intern at <strong>SkillMe</strong></span>
                <span>&bull;</span>
                <a href="https://github.com/${gh}" target="_blank" rel="noopener noreferrer">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>
                  @${gh} ↗
                </a>
              </div>
            </div>
          </div>

          <div class="hero-actions-deck">
            <button class="btn-hero-action btn-share-linkedin" onclick="shareOnLinkedIn('${name}', '${domains.join(', ')}', '${s.total_prs_merged || 0}', '${fullUrl}')">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z"/></svg>
              Share on LinkedIn
            </button>
            <button class="btn-hero-action btn-copy-link" onclick="copyPortfolioLink('${fullUrl}')">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
              Copy Recruiter Link
            </button>
          </div>
        </div>

        <div class="hero-skills-strip">
          <div class="skills-list">
            <span style="font-size:0.75rem; color:#64748b; font-weight:700; text-transform:uppercase; margin-right:4px;">Skills:</span>
            ${skillsHtml}
          </div>
          <div style="display:flex; gap:8px; align-items:center;">
            ${domainTagsHtml}
          </div>
        </div>
      </section>

      <!-- Stats Bento Grid (4 Cards) -->
      <section class="stats-bento-grid">
        <div class="bento-stat-card" style="--card-accent:#10b981;">
          <div class="bento-stat-top">
            <div class="bento-stat-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="18" cy="18" r="3"></circle><circle cx="6" cy="6" r="3"></circle><path d="M13 6h3a2 2 0 0 1 2 2v7"></path><line x1="6" y1="9" x2="6" y2="21"></line></svg>
            </div>
            <span class="bento-stat-badge" style="color:#34d399; background:rgba(16,185,129,0.1);">Verified</span>
          </div>
          <div class="bento-stat-val">${s.total_prs_merged || 0}</div>
          <div class="bento-stat-label">Pull Requests Merged</div>
        </div>

        <div class="bento-stat-card" style="--card-accent:#c99a4e;">
          <div class="bento-stat-top">
            <div class="bento-stat-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
            </div>
            <span class="bento-stat-badge" style="color:#f0c97a; background:rgba(201,154,78,0.1);">Merit Score</span>
          </div>
          <div class="bento-stat-val">${s.total_score || 0} <span style="font-size:1.1rem; color:#f0c97a; font-weight:700;">pts</span></div>
          <div class="bento-stat-label">Engineering Score</div>
        </div>

        <div class="bento-stat-card" style="--card-accent:#a855f7;">
          <div class="bento-stat-top">
            <div class="bento-stat-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
            </div>
            <span class="bento-stat-badge" style="color:#c084fc; background:rgba(168,85,247,0.1);">CI/CD Passed</span>
          </div>
          <div class="bento-stat-val">${s.total_tasks_completed || 0}</div>
          <div class="bento-stat-label">Tasks &amp; Issues Resolved</div>
        </div>

        <div class="bento-stat-card" style="--card-accent:#3b82f6;">
          <div class="bento-stat-top">
            <div class="bento-stat-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
            </div>
            <span class="bento-stat-badge" style="color:#60a5fa; background:rgba(59,130,246,0.1);">Authentic</span>
          </div>
          <div class="bento-stat-val" style="font-size:1.6rem; color:#60a5fa; margin-top:4px;">Active ●</div>
          <div class="bento-stat-label">Proof of Work Seal</div>
        </div>
      </section>

      <!-- Contributions Feed Section -->
      <section>
        <div class="section-header-row">
          <div class="section-title">
            <span>⚡</span> Verified Open-Source Contributions
            <span class="feed-count-pill">${submissions.length} Merged PRs</span>
          </div>
          <div style="font-size:0.8rem; color:#64748b;">Live GitHub Sync &bull; Automated CI/CD</div>
        </div>

        <div class="pr-feed">
          ${submissionsHtml}
        </div>
      </section>

      <!-- Recruiter Trust & Authenticity Section -->
      <section class="recruiter-trust-box">
        <div class="trust-content">
          <div class="trust-title">
            <span>🛡️</span> Recruiter &amp; Employer Verification Notice
          </div>
          <div class="trust-desc">
            All engineering contributions, Pull Requests, and commits displayed on this portfolio are cryptographically validated by SkillMe maintainers. Every PR passed continuous integration testing before merging into real-world open-source codebases.
          </div>
        </div>
        <div class="trust-actions">
          <a href="verify.html" class="nav-btn nav-btn-apply">Verify Authenticity &rarr;</a>
        </div>
      </section>

      <footer style="margin-top:50px; text-align:center; font-size:0.8rem; color:#64748b; border-top:1px solid rgba(255,255,255,0.06); padding-top:24px;">
        SkillMe Proof of Work Registry &bull; Verified Open Source Engineering Program &bull; <a href="https://www.linkedin.com/company/skill-me-intern/" target="_blank" style="color:#94a3b8; text-decoration:none;">LinkedIn Community ↗</a>
      </footer>
    `;

    document.title = `${name} — Proof of Work Portfolio — SkillMe`;
  }
});

// 1-Click Copy Link
window.copyPortfolioLink = function(url) {
  navigator.clipboard.writeText(url).then(() => {
    showToast('Recruiter profile link copied to clipboard! 📋');
  }).catch(() => {
    showToast('Copied link: ' + url);
  });
};

// 1-Click Share on LinkedIn
window.shareOnLinkedIn = function(name, domains, prCount, url) {
  const text = `🚀 Excited to share my verified open-source engineering Proof of Work portfolio on SkillMe (@skill-me-intern)!

I have contributed and merged ${prCount} verified Pull Requests across real-world GitHub repositories in ${domains}.

Every contribution is tested via CI/CD, peer-reviewed, and merged into production open source.

Check out my live portfolio, merged PRs, and codebase here:
👉 ${url}

Follow SkillMe on LinkedIn: https://www.linkedin.com/company/skill-me-intern/

#SkillMe #OpenSource #ProofOfWork #SoftwareEngineering #WebDevelopment #GitHub #Tech`;

  const shareUrl = `https://www.linkedin.com/feed/?shareActive=true&text=${encodeURIComponent(text)}`;
  window.open(shareUrl, '_blank');
};

function showToast(message) {
  const toast = document.getElementById('portfolio-toast');
  const text = document.getElementById('toast-text');
  if (toast && text) {
    text.textContent = message;
    toast.classList.add('show');
    setTimeout(() => {
      toast.classList.remove('show');
    }, 2800);
  }
}
