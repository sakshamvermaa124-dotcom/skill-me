(function () {
  const PROD_BASE = 'https://www.skill-me-intern.in';
  const WEEKS_PER_TRACK = 4;

  const DOMAIN_LABELS = {
    'web-dev': 'Web Development',
    'python': 'Python Development',
    'react': 'React Development',
    'node': 'Node.js Backend',
    'java': 'Java Development',
    'ml': 'Machine Learning',
    'data-science': 'Data Science',
    'flutter': 'Flutter App Development',
    'datascience': 'Data Science',
    'devops': 'DevOps',
    'cpp': 'C++ Development',
    'cloud': 'Cloud / AWS',
    'cyber': 'Cybersecurity',
    'uiux': 'UI/UX Design',
    'genai': 'Generative AI',
    'sql': 'SQL & Databases'
  };

  // Hashtag for the kind of work, used in the share post (designers aren't #SoftwareEngineering)
  const FIELD_HASHTAG = { uiux: 'UXDesign', cloud: 'CloudComputing', cyber: 'CyberSecurity' };

  const SKILL_MAP = {
    'web-dev': ['HTML5', 'CSS3', 'JavaScript', 'Responsive Design', 'REST APIs', 'Git'],
    'python': ['Python', 'FastAPI', 'Automation', 'PyTest', 'SQL', 'Git'],
    'react': ['React', 'JavaScript', 'Hooks', 'State Management', 'REST APIs', 'Git'],
    'node': ['Node.js', 'Express', 'REST APIs', 'Databases', 'Authentication', 'Git'],
    'java': ['Java', 'Spring Boot', 'OOP', 'SQL', 'REST APIs', 'Git'],
    'ml': ['Python', 'Scikit-Learn', 'Pandas', 'Model Evaluation', 'Data Pipelines', 'Git'],
    'data-science': ['Python', 'Pandas', 'NumPy', 'SQL', 'Data Visualization', 'Git'],
    'flutter': ['Flutter', 'Dart', 'Mobile UI', 'State Management', 'REST APIs', 'Git'],
    'devops': ['Docker', 'CI/CD', 'Linux', 'Bash', 'Cloud Deployment', 'Git'],
    'cpp': ['C++', 'Data Structures', 'Algorithms', 'OOP', 'STL', 'Git'],
    'cloud': ['AWS', 'Serverless', 'S3', 'IAM', 'Cloud Architecture', 'Cost Management'],
    'cyber': ['Python', 'Web Security', 'OWASP', 'Hashing', 'Log Analysis', 'Security Reporting'],
    'uiux': ['Figma', 'User Research', 'Wireframing', 'Prototyping', 'Design Systems', 'Usability Testing'],
    'genai': ['Python', 'LLM APIs', 'Prompt Engineering', 'Embeddings', 'Streamlit', 'Git'],
    'sql': ['SQL', 'Database Design', 'Joins & Aggregations', 'Indexes', 'Data Analysis', 'ER Diagrams']
  };
  SKILL_MAP['datascience'] = SKILL_MAP['data-science'];
  const DEFAULT_SKILLS = ['Project Delivery', 'Technical Writing', 'Problem Solving'];

  const ICONS = {
    check: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>',
    link: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>',
    print: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>',
    linkedin: '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z"/></svg>',
    arrow: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="7" y1="17" x2="17" y2="7"></line><polyline points="7 7 17 7 17 17"></polyline></svg>',
    flag: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"></path><line x1="4" y1="22" x2="4" y2="15"></line></svg>',
    percent: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="5" x2="5" y2="19"></line><circle cx="6.5" cy="6.5" r="2.5"></circle><circle cx="17.5" cy="17.5" r="2.5"></circle></svg>',
    layers: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>',
    star: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>',
    calendar: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>',
    shield: '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path><polyline points="9 12 11 14 15 10"></polyline></svg>',
    lock: '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>',
    search: '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>',
    alert: '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>'
  };

  // ── Helpers ─────────────────────────────────────────────
  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // Only allow http(s) links in hrefs so a stored URL can't become a javascript: link.
  function safeUrl(url) {
    try {
      const u = new URL(url);
      return (u.protocol === 'https:' || u.protocol === 'http:') ? u.href : null;
    } catch (e) {
      return null;
    }
  }

  function domainLabel(slug) {
    if (!slug) return '';
    return DOMAIN_LABELS[slug] || slug.replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  // Title-case words typed entirely in one case ("saksham VERMA"), leave mixed case ("McDonald") alone.
  function formatName(raw) {
    return String(raw || '').replace(/\s+/g, ' ').trim().split(' ').map(w => {
      if (w === w.toLowerCase() || w === w.toUpperCase()) {
        return w.toLowerCase().replace(/(^|['’-])(\p{L})/gu, (m, sep, ch) => sep + ch.toUpperCase());
      }
      return w;
    }).join(' ');
  }

  // Accepts "2026-08-12 14:30:00", "2026-08-12T14:30:00Z" or "2026-08-12".
  function parseDate(ts) {
    if (!ts) return null;
    const datePart = String(ts).trim().split(/[T ]/)[0];
    if (!/^\d{4}-\d{2}-\d{2}$/.test(datePart)) return null;
    const d = new Date(datePart + 'T12:00:00');
    return isNaN(d) ? null : d;
  }

  function formatDate(d, opts) {
    return d ? d.toLocaleDateString('en-IN', opts || { day: 'numeric', month: 'short', year: 'numeric' }) : '';
  }

  // UI-only hint: is the logged-in dashboard user looking at their own portfolio?
  function loggedInStudentId() {
    try {
      const token = localStorage.getItem('token');
      if (!token) return null;
      const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
      if (payload.type && payload.type !== 'student') return null;
      if (payload.exp && payload.exp * 1000 < Date.now()) return null;
      return payload.sub ? String(payload.sub) : null;
    } catch (e) {
      return null;
    }
  }

  function showToast(message) {
    const toast = document.getElementById('portfolio-toast');
    const text = document.getElementById('toast-text');
    if (!toast || !text) return;
    text.textContent = message;
    toast.classList.add('show');
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => toast.classList.remove('show'), 2800);
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise((resolve, reject) => {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      ta.remove();
      ok ? resolve() : reject(new Error('copy failed'));
    });
  }

  function stateCard(icon, title, descHtml, actionHtml) {
    return `
      <div class="card locked-card fade-in">
        <div class="locked-icon-wrap">${icon}</div>
        <div class="locked-title">${title}</div>
        <div class="locked-desc">${descHtml}</div>
        ${actionHtml || ''}
      </div>
    `;
  }

  // ── Identify which portfolio to load ────────────────────
  // The URL alone decides whose portfolio is shown — never localStorage — so a
  // recruiter's (or another student's) browser state can't swap the profile.
  function resolveTarget() {
    const params = new URLSearchParams(window.location.search);
    const idParam = (params.get('student_id') || params.get('id') || '').trim();
    if (/^\d+$/.test(idParam)) return { type: 'id', value: idParam };

    const parts = window.location.pathname.split('/').filter(Boolean);
    const pathUser = (parts[0] === 'p' && parts[1]) ? decodeURIComponent(parts[1]) : '';
    const gh = (params.get('gh') || params.get('github') || params.get('u') || pathUser || '').trim().replace(/^@/, '');
    if (gh) return { type: 'gh', value: gh };

    return null;
  }

  // ── Render ──────────────────────────────────────────────
  function renderPortfolio(container, data, target) {
    const p = data.profile || data.student || {};
    const s = data.stats || {};
    const submissions = Array.isArray(data.submissions) ? data.submissions : [];
    let domains = Array.isArray(data.domains) ? data.domains.filter(Boolean) : [];
    if (!domains.length && p.domain) domains = [p.domain];

    const name = formatName(p.name || [p.first_name, p.last_name].filter(Boolean).join(' ')) || 'SkillMe Intern';
    const initials = name.split(' ').filter(Boolean).slice(0, 2).map(w => w.charAt(0).toUpperCase()).join('') || 'SM';
    const college = p.college || '';
    const studentId = p.id != null ? String(p.id) : (target.type === 'id' ? target.value : '');
    const gh = p.github_username || (target.type === 'gh' ? target.value : '');

    const shareUrl = studentId
      ? `${PROD_BASE}/portfolio.html?student_id=${encodeURIComponent(studentId)}`
      : `${PROD_BASE}/p/${encodeURIComponent(gh)}`;
    const isOwner = !!studentId && loggedInStudentId() === studentId;

    // Milestone progress. Matches the dashboard's model: 4 tasks total regardless of
    // how many tracks a student is enrolled in (see dashboard.js completion_pct).
    const totalMilestones = WEEKS_PER_TRACK;
    const approved = submissions.length;
    const completion = Math.min(100, Math.round((approved / totalMilestones) * 100));
    const dates = submissions.map(sub => parseDate(sub.reviewed_at || sub.submitted_at)).filter(Boolean).sort((a, b) => a - b);
    const latest = dates.length ? dates[dates.length - 1] : null;

    const RING_R = 44;
    const RING_C = 2 * Math.PI * RING_R;
    const ringOffset = RING_C * (1 - Math.min(1, approved / totalMilestones));

    const domainTagsHtml = domains.map(d => `<span class="domain-tag">${esc(domainLabel(d))}</span>`).join('');

    const skills = new Set();
    domains.forEach(d => (SKILL_MAP[d] || DEFAULT_SKILLS).forEach(sk => skills.add(sk)));
    if (!skills.size) DEFAULT_SKILLS.forEach(sk => skills.add(sk));
    const skillsHtml = Array.from(skills).map(sk => `<span class="skill-pill">${esc(sk)}</span>`).join('');

    const score = Number(s.total_score) || 0;
    const fourthStat = score > 0
      ? { icon: ICONS.star, cls: '', value: `${score}<small>pts</small>`, label: 'Merit score' }
      : { icon: ICONS.calendar, cls: '', value: latest ? esc(formatDate(latest, { day: 'numeric', month: 'short' })) : '—', label: 'Last verified' };

    const milestonesHtml = approved
      ? `<ol class="timeline">${submissions.map(sub => {
          const url = safeUrl(sub.linkedin_url);
          const d = parseDate(sub.reviewed_at || sub.submitted_at);
          const tag = url ? 'a' : 'div';
          const attrs = url ? ` href="${esc(url)}" target="_blank" rel="noopener noreferrer"` : '';
          return `
            <li>
              <${tag} class="milestone"${attrs}>
                <span class="milestone-node">W${esc(sub.week || '')}</span>
                <span class="milestone-body">
                  <span>
                    <span class="milestone-title">Week ${esc(sub.week || '')} Milestone</span>
                    <span class="milestone-meta">
                      <span class="badge-approved">${ICONS.check} Approved</span>
                      ${d ? `<span>${esc(formatDate(d))}</span>` : ''}
                      ${sub.domain ? `<span class="milestone-domain">${esc(domainLabel(sub.domain))}</span>` : ''}
                    </span>
                  </span>
                  ${url ? `<span class="milestone-cta">View post ${ICONS.arrow}</span>` : ''}
                </span>
              </${tag}>
            </li>`;
        }).join('')}</ol>`
      : `<div class="empty-state"><strong>Milestones syncing</strong>Approved LinkedIn milestone posts appear here once reviewed by the SkillMe team.</div>`;

    container.innerHTML = `
      <section class="card profile-hero-card fade-in">
        <div class="hero-grid">
          <div class="hero-identity">
            <div class="avatar-monogram" aria-hidden="true">
              ${esc(initials)}
              <span class="avatar-verified" title="Verified by SkillMe">${ICONS.check}</span>
            </div>
            <div class="hero-meta">
              <div class="eyebrow"><span class="pulse"></span> Verified Proof of Work</div>
              <h1 class="hero-name">${esc(name)}</h1>
              <p class="hero-role">
                <span>${domains.length === 1 ? esc(domainLabel(domains[0])) + ' ' : ''}Intern at <strong>SkillMe</strong></span>
                ${college ? `<span class="sep">•</span><span>${esc(college)}</span>` : ''}
              </p>
              ${domainTagsHtml ? `<div class="domain-row">${domainTagsHtml}</div>` : ''}
            </div>
          </div>

          <div class="hero-seal" aria-label="${approved} of ${totalMilestones} milestones verified">
            <div class="seal-ring">
              <svg width="104" height="104" viewBox="0 0 104 104">
                <circle class="track" cx="52" cy="52" r="${RING_R}" fill="none" stroke-width="7"></circle>
                <circle class="bar" id="seal-bar" cx="52" cy="52" r="${RING_R}" fill="none" stroke-width="7"
                  stroke-dasharray="${RING_C.toFixed(2)}" stroke-dashoffset="${RING_C.toFixed(2)}"></circle>
              </svg>
              <div class="seal-center"><div class="seal-value">${Math.min(approved, totalMilestones)}<span>/${totalMilestones}</span></div></div>
            </div>
            <div class="seal-label">Milestones verified</div>
          </div>
        </div>

        <div class="hero-footer">
          <div class="hero-actions">
            ${isOwner ? `<button type="button" class="btn btn-primary" id="btn-share">${ICONS.linkedin} Share on LinkedIn</button>` : ''}
            <button type="button" class="btn ${isOwner ? 'btn-ghost' : 'btn-primary'}" id="btn-copy">${ICONS.link} Copy link</button>
            <button type="button" class="btn btn-ghost" id="btn-print">${ICONS.print} Save as PDF</button>
          </div>
          <div class="hero-issued">Issued by <strong>SkillMe</strong> · UDYAM-UP-50-0294192</div>
        </div>
        ${isOwner ? `<div class="owner-tip">Only you see this: when posting on LinkedIn, type <strong>@SkillMe</strong> and pick it from the dropdown so the post tags us officially.</div>` : ''}
      </section>

      <section class="stats-bento-grid fade-in">
        <div class="card stat-card">
          <div class="stat-icon sage">${ICONS.flag}</div>
          <div class="stat-value">${approved}</div>
          <div class="stat-label">Milestones approved</div>
        </div>
        <div class="card stat-card">
          <div class="stat-icon">${ICONS.percent}</div>
          <div class="stat-value">${completion}<small>%</small></div>
          <div class="stat-label">Program completion</div>
        </div>
        <div class="card stat-card">
          <div class="stat-icon">${ICONS.layers}</div>
          <div class="stat-value">${domains.length || 1}</div>
          <div class="stat-label">${(domains.length || 1) === 1 ? 'Internship track' : 'Internship tracks'}</div>
        </div>
        <div class="card stat-card">
          <div class="stat-icon">${fourthStat.icon}</div>
          <div class="stat-value">${fourthStat.value}</div>
          <div class="stat-label">${fourthStat.label}</div>
        </div>
      </section>

      <div class="content-grid fade-in">
        <section class="card panel">
          <div class="panel-head">
            <h2 class="panel-title">Proof of Work</h2>
            <span class="panel-sub">Each milestone is reviewed by the SkillMe team</span>
          </div>
          ${milestonesHtml}
        </section>

        <aside>
          <section class="card panel">
            <div class="panel-head"><h2 class="panel-title">Skills applied</h2></div>
            <div class="skills-list">${skillsHtml}</div>
          </section>

          <section class="card panel recruiter-trust-box">
            <div class="trust-icon">${ICONS.shield}</div>
            <h2 class="panel-title">For recruiters</h2>
            <p class="trust-desc">This portfolio is generated from SkillMe's records — it can't be edited by the student.</p>
            <ul class="trust-list">
              <li>${ICONS.check} Every milestone is manually reviewed before approval</li>
              <li>${ICONS.check} Each milestone links to the original public post</li>
              <li>${ICONS.check} Certificates can be checked independently</li>
            </ul>
            <div class="trust-actions">
              <a href="verify.html" class="btn btn-ghost btn-sm">Verify a certificate &rarr;</a>
            </div>
          </section>
        </aside>
      </div>

      <footer class="page-footer">
        SkillMe Proof of Work Registry &bull;
        <a href="https://www.linkedin.com/company/skill-me-intern/" target="_blank" rel="noopener noreferrer">Follow SkillMe on LinkedIn ↗</a>
      </footer>
    `;

    // Animate the progress ring in
    requestAnimationFrame(() => {
      const bar = document.getElementById('seal-bar');
      if (bar) requestAnimationFrame(() => bar.setAttribute('stroke-dashoffset', ringOffset.toFixed(2)));
    });

    document.getElementById('btn-copy').addEventListener('click', () => {
      copyText(shareUrl)
        .then(() => showToast('Portfolio link copied to clipboard'))
        .catch(() => showToast(shareUrl));
    });
    document.getElementById('btn-print').addEventListener('click', () => window.print());

    const shareBtn = document.getElementById('btn-share');
    if (shareBtn) {
      shareBtn.addEventListener('click', () => {
        const trackText = domains.map(domainLabel).join(', ') || 'my SkillMe track';
        const text = `🚀 Excited to share my verified Proof of Work portfolio from SkillMe (@SkillMe)!

I completed ${approved} verified project milestone${approved === 1 ? '' : 's'} in ${trackText}, each reviewed by the SkillMe team before approval.

Check out my live portfolio:
👉 ${shareUrl}

Follow SkillMe on LinkedIn: https://www.linkedin.com/company/skill-me-intern/

#SkillMe #ProofOfWork #${FIELD_HASHTAG[domains[0]] || 'SoftwareEngineering'} #Internship`;
        window.open(`https://www.linkedin.com/feed/?shareActive=true&text=${encodeURIComponent(text)}`, '_blank', 'noopener');
      });
    }

    document.title = `${name} — Proof of Work Portfolio — SkillMe`;
    const desc = `${name}'s verified SkillMe Proof of Work: ${approved} approved milestone${approved === 1 ? '' : 's'}${domains.length ? ' in ' + domains.map(domainLabel).join(', ') : ''}.`;
    const metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) metaDesc.setAttribute('content', desc);
  }

  // ── Boot ────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', async () => {
    const container = document.getElementById('content-container');
    if (!container) return;

    const params = new URLSearchParams(window.location.search);
    const target = resolveTarget();

    if (params.get('preview') === '1') {
      renderPortfolio(container, {
        profile: { id: 0, name: 'Saksham Verma', college: 'IIT Delhi', domain: 'web-dev' },
        stats: { total_tasks_completed: 0, total_score: 0 },
        domains: ['web-dev'],
        submissions: [
          { week: 1, reviewed_at: '2026-08-04 18:00:00', linkedin_url: 'https://www.linkedin.com/feed/update/urn:li:activity:1', domain: 'web-dev' },
          { week: 2, reviewed_at: '2026-08-08T10:15:00Z', linkedin_url: 'https://www.linkedin.com/feed/update/urn:li:activity:2', domain: 'web-dev' },
          { week: 3, reviewed_at: '2026-08-12T14:30:00Z', linkedin_url: 'https://www.linkedin.com/feed/update/urn:li:activity:3', domain: 'web-dev' }
        ]
      }, target || { type: 'id', value: '0' });
      return;
    }

    if (!target) {
      container.innerHTML = stateCard(
        ICONS.search,
        'Invalid profile link',
        'This link is missing a student reference. Portfolio links look like <code>/portfolio.html?student_id=123</code> — you can copy yours from the Student Dashboard.',
        '<a href="dashboard.html" class="btn btn-primary">Go to Student Dashboard &rarr;</a>'
      );
      return;
    }

    const baseUrl = window.SKILLME_API || window.location.origin;
    const fetchUrl = target.type === 'id'
      ? `${baseUrl}/api/portfolio/id/${encodeURIComponent(target.value)}`
      : `${baseUrl}/api/portfolio/${encodeURIComponent(target.value)}`;

    try {
      const res = await fetch(fetchUrl);

      if (res.status === 403) {
        container.innerHTML = stateCard(
          ICONS.lock,
          'Portfolio not yet public',
          'This Proof of Work portfolio hasn\'t been activated yet.<br><br>If it\'s yours, complete your milestones and activate your credentials from the Student Dashboard to unlock your public link.',
          '<a href="dashboard.html" class="btn btn-primary">Log in to Dashboard &rarr;</a>'
        );
        return;
      }

      if (res.status === 404) {
        container.innerHTML = stateCard(
          ICONS.search,
          'Profile not found',
          `We couldn't find a SkillMe portfolio for <strong>${esc(target.value)}</strong>. Double-check the link and try again.`,
          '<a href="index.html" class="btn btn-ghost">Back to Home &rarr;</a>'
        );
        return;
      }

      if (!res.ok) {
        let errMsg = 'Failed to load portfolio details.';
        try {
          const errData = await res.json();
          if (errData && typeof errData.detail === 'string') errMsg = errData.detail;
        } catch (e) {}
        throw new Error(errMsg);
      }

      renderPortfolio(container, await res.json(), target);
    } catch (e) {
      container.innerHTML = stateCard(
        ICONS.alert,
        'Unable to load portfolio',
        `${esc(e.message || 'Network error')}<br>Please check your connection and try again.`,
        '<button type="button" class="btn btn-primary" onclick="location.reload()">Retry</button>'
      );
    }
  });
})();
