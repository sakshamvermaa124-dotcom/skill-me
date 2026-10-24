(function () {
  const PROD_BASE = 'https://www.skill-me-intern.in';
  const WEEKS_PER_TRACK = 4;

  const DOMAIN_LABELS = {
    'web-dev': 'Full Stack Engineer',
    'python': 'Python Development',
    'react': 'Frontend Engineer',
    'node': 'Backend Engineer',
    'java': 'Java Development',
    'ml': 'Machine Learning',
    'data-science': 'Data Science',
    'flutter': 'App Developer',
    'datascience': 'Data Science',
    'devops': 'DevOps',
    'cpp': 'C++ Development',
    'cloud': 'Cloud / AWS',
    'cyber': 'Cybersecurity',
    'uiux': 'UI/UX Design',
    'genai': 'Generative AI',
    'sql': 'SQL & Databases',
    'ai-engineer': 'AI Engineer',
    'fde': 'Forward Deployed Engineer',
    'sde': 'SDE / SWE',
    'ai-pm': 'AI Product Management',
    'qa': 'Software Quality'
  };

  // Hashtag for the kind of work, used in the share post (designers aren't #SoftwareEngineering)
  const FIELD_HASHTAG = {
    uiux: 'UXDesign', cloud: 'CloudComputing', cyber: 'CyberSecurity',
    'ai-pm': 'ProductManagement', qa: 'QualityAssurance'
  };

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
    'sql': ['SQL', 'Database Design', 'Joins & Aggregations', 'Indexes', 'Data Analysis', 'ER Diagrams'],
    'ai-engineer': ['Python', 'LLM APIs', 'RAG', 'Tool Calling', 'Vector Search', 'Evals'],
    'fde': ['API Integration', 'Python', 'Technical Docs', 'Client Tools', 'Debugging', 'Git'],
    'sde': ['Data Structures', 'Algorithms', 'System Design', 'Testing', 'Clean Architecture', 'Git'],
    'ai-pm': ['Product Strategy', 'PRDs', 'AI/LLM Evals', 'User Research', 'Roadmapping', 'Notion'],
    'qa': ['Manual Testing', 'Test Automation', 'Selenium/Playwright', 'Bug Reporting', 'Test Planning', 'Postman']
  };
  SKILL_MAP['datascience'] = SKILL_MAP['data-science'];
  SKILL_MAP['swe'] = SKILL_MAP['sde'];
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
      <div class="wrap"><div class="locked-card">
        <div class="locked-icon-wrap">${icon}</div>
        <div class="locked-title">${title}</div>
        <div class="locked-desc">${descHtml}</div>
        ${actionHtml || ''}
      </div></div>
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

  // ── Theme toggle (same key as the main site + dashboard) ─
  function initThemeToggle() {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;
    const sync = () => {
      const next = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
      btn.setAttribute('aria-label', `Switch to ${next} mode`);
      btn.setAttribute('title', `Switch to ${next} mode`);
      const meta = document.querySelector('meta[name="theme-color"]');
      if (meta) meta.setAttribute('content', next === 'dark' ? '#ffffff' : '#09090a');
    };
    sync();
    btn.addEventListener('click', () => {
      const root = document.documentElement;
      const next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
      root.classList.add('theme-switching');
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('skillme-theme', next); } catch (e) {}
      sync();
      setTimeout(() => root.classList.remove('theme-switching'), 350);
    });
  }

  const prefersReducedMotion = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Public LinkedIn posts can be embedded via their URN; returns null when the link has none.
  function linkedinEmbedUrl(url) {
    const safe = safeUrl(url);
    if (!safe || !/(^|\.)linkedin\.com$/i.test(new URL(safe).hostname)) return null;
    let s = safe;
    try { s = decodeURIComponent(safe); } catch (e) {}
    const TYPES = { activity: 'activity', share: 'share', ugcpost: 'ugcPost' };
    const m = s.match(/urn:li:(activity|share|ugcPost):(\d+)/i) || s.match(/[-_](activity|share|ugcPost)-(\d{10,})/i);
    if (!m) return null;
    return `https://www.linkedin.com/embed/feed/update/urn:li:${TYPES[m[1].toLowerCase()]}:${m[2]}`;
  }

  // ── Post preview modal ──────────────────────────────────
  let lastFocus = null;
  function openPostModal(embedUrl, postUrl, title) {
    const modal = document.getElementById('post-modal');
    const wrap = document.getElementById('post-frame-wrap');
    if (!modal || !wrap) { window.open(postUrl, '_blank', 'noopener'); return; }
    lastFocus = document.activeElement;
    document.getElementById('post-modal-title').textContent = title;
    document.getElementById('post-modal-open').href = postUrl;
    wrap.innerHTML = '<div class="post-loading">Loading post from LinkedIn…</div>';
    const frame = document.createElement('iframe');
    frame.src = embedUrl;
    frame.title = title;
    frame.loading = 'lazy';
    frame.setAttribute('allowfullscreen', '');
    frame.addEventListener('load', () => { const l = wrap.querySelector('.post-loading'); if (l) l.remove(); });
    wrap.appendChild(frame);
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => modal.classList.add('show'));
    document.body.style.overflow = 'hidden';
    document.getElementById('post-modal-close').focus();
  }
  function closePostModal() {
    const modal = document.getElementById('post-modal');
    if (!modal || !modal.classList.contains('open')) return;
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    setTimeout(() => {
      modal.classList.remove('open');
      const wrap = document.getElementById('post-frame-wrap');
      if (wrap) wrap.innerHTML = '';
    }, 250);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  function initPostModal() {
    const modal = document.getElementById('post-modal');
    if (!modal) return;
    document.getElementById('post-modal-close').addEventListener('click', closePostModal);
    modal.addEventListener('click', (e) => { if (e.target === modal) closePostModal(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePostModal(); });
  }

  // ── Motion: scroll reveal, count-up, credential tilt ────
  function initReveal(root) {
    const els = root.querySelectorAll('.reveal');
    if (prefersReducedMotion() || !('IntersectionObserver' in window)) { els.forEach(el => el.classList.add('in')); return; }
    const io = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('in');
        io.unobserve(entry.target);
        entry.target.querySelectorAll('[data-count]').forEach(countUp);
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });
    els.forEach(el => io.observe(el));
  }
  function countUp(el) {
    const end = Number(el.dataset.count);
    if (!isFinite(end) || el.dataset.counted) return;
    el.dataset.counted = '1';
    if (prefersReducedMotion() || end === 0) { el.textContent = end; return; }
    const start = performance.now();
    const dur = 1200;
    const step = (t) => {
      const k = Math.min(1, (t - start) / dur);
      el.textContent = Math.round(end * (1 - Math.pow(1 - k, 3)));
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
  function initTilt(card) {
    if (!card || prefersReducedMotion() || !window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
    card.addEventListener('pointermove', (e) => {
      const r = card.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width;
      const y = (e.clientY - r.top) / r.height;
      card.classList.add('is-tilting');
      card.style.setProperty('--ry', `${((x - 0.5) * 10).toFixed(2)}deg`);
      card.style.setProperty('--rx', `${((0.5 - y) * 8).toFixed(2)}deg`);
      card.style.setProperty('--mx', `${(x * 100).toFixed(1)}%`);
      card.style.setProperty('--my', `${(y * 100).toFixed(1)}%`);
    });
    card.addEventListener('pointerleave', () => {
      card.classList.remove('is-tilting');
      card.style.setProperty('--rx', '0deg');
      card.style.setProperty('--ry', '0deg');
    });
  }

  // ── Render ──────────────────────────────────────────────
  function renderPortfolio(container, data, target) {
    const p = data.profile || data.student || {};
    const s = data.stats || {};
    const submissions = Array.isArray(data.submissions) ? data.submissions : [];
    let domains = Array.isArray(data.domains) ? data.domains.filter(Boolean) : [];
    if (!domains.length && p.domain) domains = [p.domain];

    const name = formatName(p.name || [p.first_name, p.last_name].filter(Boolean).join(' ')) || 'SkillMe Intern';
    const firstName = name.split(' ')[0];
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
    const shownApproved = Math.min(approved, totalMilestones);
    const completion = Math.min(100, Math.round((approved / totalMilestones) * 100));
    const dates = submissions.map(sub => parseDate(sub.reviewed_at || sub.submitted_at)).filter(Boolean).sort((a, b) => a - b);
    const first = dates.length ? dates[0] : null;
    const latest = dates.length ? dates[dates.length - 1] : null;
    const primaryRole = domains.length === 1 ? domainLabel(domains[0]) : (domains.length ? domains.map(domainLabel).join(' · ') : 'Tech');

    // Rings: avatar (r=48 in a 104 box) and the credential seal (r=42 in a 96 box)
    const AV_R = 48, AV_C = 2 * Math.PI * AV_R;
    const SEAL_R = 42, SEAL_C = 2 * Math.PI * SEAL_R;
    const frac = Math.min(1, approved / totalMilestones);

    const skills = new Set();
    domains.forEach(d => (SKILL_MAP[d] || DEFAULT_SKILLS).forEach(sk => skills.add(sk)));
    if (!skills.size) DEFAULT_SKILLS.forEach(sk => skills.add(sk));
    const skillsHtml = Array.from(skills).map(sk => `<span class="skill-pill">${esc(sk)}</span>`).join('');
    const domainTagsHtml = domains.map(d => `<span class="domain-tag">${ICONS.layers.replace('width="17" height="17"', 'width="13" height="13"')}${esc(domainLabel(d))}</span>`).join('');

    // Highlights — only real numbers
    const score = Number(s.total_score) || 0;
    const spanDays = first && latest ? Math.max(1, Math.round((latest - first) / 86400000) + 1) : 0;
    const highlights = [
      { value: shownApproved, suffix: `<small>/${totalMilestones}</small>`, label: 'Milestones verified' },
      { value: completion, suffix: '<small>%</small>', label: 'Program completed' },
      score > 0
        ? { value: score, suffix: '<small>pts</small>', label: 'Merit score' }
        : { value: domains.length || 1, suffix: '', label: (domains.length || 1) === 1 ? 'Internship track' : 'Internship tracks' },
      spanDays
        ? { value: spanDays, suffix: `<small>day${spanDays === 1 ? '' : 's'}</small>`, label: 'From first to last milestone' }
        : { value: null, text: latest ? esc(formatDate(latest, { day: 'numeric', month: 'short' })) : '—', label: 'Last verified' },
    ];
    const highlightsHtml = highlights.map(h => `
      <div class="highlight">
        <div class="highlight-value">${h.value == null ? h.text : `<span data-count="${h.value}">0</span>${h.suffix}`}</div>
        <div class="highlight-label">${h.label}</div>
      </div>`).join('');

    const milestonesHtml = approved
      ? `<ol class="milestones">${submissions.map(sub => {
          const url = safeUrl(sub.linkedin_url);
          const embed = linkedinEmbedUrl(sub.linkedin_url);
          const d = parseDate(sub.reviewed_at || sub.submitted_at);
          const week = esc(sub.week || '');
          const title = `Week ${week} project`;
          return `
            <li class="milestone">
              <span class="milestone-num" aria-hidden="true">${String(sub.week || '').padStart(2, '0')}</span>
              <div class="milestone-top">
                <span class="badge-approved">${ICONS.check} Verified</span>
                ${sub.domain ? `<span class="milestone-domain">${esc(domainLabel(sub.domain))}</span>` : ''}
              </div>
              <div class="milestone-week">Milestone ${week} of ${totalMilestones}</div>
              <h3 class="milestone-title">${esc(title.charAt(0).toUpperCase() + title.slice(1))}</h3>
              ${d ? `<div class="milestone-date">Approved by the SkillMe team on ${esc(formatDate(d))}</div>` : ''}
              ${url ? `
              <div class="milestone-actions">
                ${embed ? `<button type="button" class="btn btn-primary btn-sm" data-preview="${esc(embed)}" data-url="${esc(url)}" data-title="${esc(title.charAt(0).toUpperCase() + title.slice(1))}">Preview post</button>` : ''}
                <a class="btn ${embed ? 'btn-ghost' : 'btn-primary'} btn-sm" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${ICONS.linkedin} Open on LinkedIn</a>
              </div>` : ''}
            </li>`;
        }).join('')}</ol>`
      : `<div class="empty-state"><strong>Milestones syncing</strong>Approved LinkedIn milestone posts appear here once reviewed by the SkillMe team.</div>`;

    const ctaHtml = isOwner
      ? `
        <section class="cta-band reveal">
          <div>
            <div class="cta-title">Your portfolio is live. Put it to work.</div>
            <p class="cta-sub">Share it on LinkedIn, add it to your resume, or send it to recruiters — it stays up to date as new milestones are approved.</p>
          </div>
          <div class="cta-actions">
            <button type="button" class="btn btn-linkedin" data-action="share">${ICONS.linkedin} Share on LinkedIn</button>
            <button type="button" class="btn btn-ghost" data-action="copy">${ICONS.link} Copy link</button>
          </div>
        </section>`
      : `
        <section class="cta-band reveal">
          <div>
            <div class="cta-title">Want a verified portfolio like ${esc(firstName)}'s?</div>
            <p class="cta-sub">Do real weekly projects in a SkillMe internship, get each one reviewed, and earn a public Proof of Work page of your own.</p>
          </div>
          <div class="cta-actions">
            <a href="apply.html" class="btn btn-primary">Apply to SkillMe ${ICONS.arrow}</a>
            <a href="index.html#how-it-works" class="btn btn-ghost">How it works</a>
          </div>
        </section>`;

    container.innerHTML = `
      <section class="profile-hero-card">
        <div class="aurora" aria-hidden="true"><span class="blob blob-1"></span><span class="blob blob-2"></span><span class="blob blob-3"></span></div>
        <div class="wrap hero-grid">
          <div class="hero-identity">
            <div class="avatar" aria-hidden="true">
              <svg class="avatar-ring" width="104" height="104" viewBox="0 0 104 104">
                <circle class="track" cx="52" cy="52" r="${AV_R}" fill="none" stroke-width="3"></circle>
                <circle class="bar" id="avatar-bar" cx="52" cy="52" r="${AV_R}" fill="none" stroke-width="3"
                  stroke-dasharray="${AV_C.toFixed(2)}" stroke-dashoffset="${AV_C.toFixed(2)}"></circle>
              </svg>
              <div class="avatar-monogram">${esc(initials)}</div>
              <span class="avatar-verified" title="Verified by SkillMe">${ICONS.check}</span>
            </div>
            <div class="eyebrow"><span class="pulse"></span> Verified by SkillMe${latest ? ` <span class="muted">· Updated ${esc(formatDate(latest, { day: 'numeric', month: 'short', year: 'numeric' }))}</span>` : ''}</div>
            <h1 class="hero-name">${esc(name)}</h1>
            <p class="hero-role">
              <span>${esc(primaryRole)} Intern at <strong>SkillMe</strong></span>
              ${college ? `<span class="sep" aria-hidden="true"></span><span>${esc(college)}</span>` : ''}
            </p>
            ${domains.length > 1 && domainTagsHtml ? `<div class="domain-row">${domainTagsHtml}</div>` : ''}
            <div class="hero-actions">
              ${isOwner ? `<button type="button" class="btn btn-linkedin" id="btn-share">${ICONS.linkedin} Share on LinkedIn</button>` : ''}
              <button type="button" class="btn ${isOwner ? 'btn-ghost' : 'btn-primary'}" id="btn-copy">${ICONS.link} Copy link</button>
              <button type="button" class="btn btn-ghost" id="btn-print">${ICONS.print} Save as PDF</button>
            </div>
            ${isOwner ? `<div class="owner-tip">Only you see this: when posting on LinkedIn, type <strong>@SkillMe</strong> and pick it from the dropdown so the post tags us officially.</div>` : ''}
          </div>

          <div class="cred-stage">
            <div class="cred-card" id="cred-card" aria-label="${shownApproved} of ${totalMilestones} milestones verified by SkillMe">
              <div class="cred-top">
                <div class="cred-brand"><img src="assets/logo.webp" alt="" onerror="this.src='assets/logo.png'"> SkillMe</div>
                <div class="cred-type">Proof of Work</div>
              </div>
              <div class="cred-main">
                <div class="seal-ring">
                  <svg width="96" height="96" viewBox="0 0 96 96">
                    <circle class="track" cx="48" cy="48" r="${SEAL_R}" fill="none" stroke-width="6"></circle>
                    <circle class="bar" id="seal-bar" cx="48" cy="48" r="${SEAL_R}" fill="none" stroke-width="6"
                      stroke-dasharray="${SEAL_C.toFixed(2)}" stroke-dashoffset="${SEAL_C.toFixed(2)}"></circle>
                  </svg>
                  <div class="seal-center"><div class="seal-value">${shownApproved}<span>/${totalMilestones}</span></div></div>
                </div>
                <div>
                  <div class="cred-claim">${shownApproved >= totalMilestones ? 'All milestones verified' : `${shownApproved} milestone${shownApproved === 1 ? '' : 's'} verified`}</div>
                  <div class="cred-claim-sub">Each reviewed by the SkillMe team</div>
                </div>
              </div>
              <dl class="cred-rows">
                <div class="cred-row"><dt>Holder</dt><dd>${esc(name)}</dd></div>
                <div class="cred-row"><dt>Track</dt><dd>${esc(primaryRole)}</dd></div>
                <div class="cred-row"><dt>Last verified</dt><dd>${latest ? esc(formatDate(latest)) : '—'}</dd></div>
                <div class="cred-row"><dt>Record</dt><dd class="mono">${studentId ? `#${esc(studentId)}` : esc('@' + gh)}</dd></div>
              </dl>
              <span class="cred-stamp">${ICONS.check} Verified</span>
            </div>
          </div>
        </div>
      </section>

      <div class="wrap">
        <section class="highlights reveal" aria-label="Highlights">${highlightsHtml}</section>

        <section class="section reveal" id="proof">
          <div class="section-head">
            <div>
              <div class="section-kicker">Proof of Work</div>
              <h2 class="section-title">Verified milestones</h2>
            </div>
            <p class="section-sub">Every milestone is a public LinkedIn post about real project work, reviewed and approved by the SkillMe team.</p>
          </div>
          ${milestonesHtml}
        </section>

        <section class="section reveal">
          <div class="split">
            <div class="panel">
              <h2 class="panel-title">Skills applied</h2>
              <p class="panel-sub">Core skills practised across the ${esc(primaryRole)} track.</p>
              <div class="skills-list">${skillsHtml}</div>
            </div>
            <div class="panel">
              <h2 class="panel-title">Why you can trust this page</h2>
              <ul class="trust-list">
                <li><span class="trust-ico">${ICONS.check}</span><div><strong>Reviewed by people</strong><span>Every milestone is checked by the SkillMe team before approval.</span></div></li>
                <li><span class="trust-ico">${ICONS.link}</span><div><strong>Linked to the original</strong><span>Each milestone points to the student's public LinkedIn post.</span></div></li>
                <li><span class="trust-ico">${ICONS.shield.replace('width="19" height="19"', 'width="16" height="16"')}</span><div><strong>Can't be edited by the student</strong><span>This page is generated from SkillMe's records.</span></div></li>
              </ul>
              <div class="trust-actions"><a href="verify.html" class="btn btn-ghost btn-sm">Verify a certificate ${ICONS.arrow}</a></div>
            </div>
          </div>
        </section>

        ${ctaHtml}

        <footer class="page-footer">
          <span>SkillMe Proof of Work Registry · Issued by SkillMe · UDYAM-UP-50-0294192</span>
          <a href="https://www.linkedin.com/company/skill-me-intern/" target="_blank" rel="noopener noreferrer">Follow SkillMe on LinkedIn ↗</a>
        </footer>
      </div>
    `;

    // Rings animate in
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const seal = document.getElementById('seal-bar');
      if (seal) seal.setAttribute('stroke-dashoffset', (SEAL_C * (1 - frac)).toFixed(2));
      const av = document.getElementById('avatar-bar');
      if (av) av.setAttribute('stroke-dashoffset', (AV_C * (1 - frac)).toFixed(2));
    }));
    initReveal(container);
    initTilt(document.getElementById('cred-card'));

    // Owners don't need the "Dashboard" link pointed at login; visitors don't need it at all.
    const navDash = document.getElementById('nav-dashboard');
    if (navDash && !isOwner) navDash.textContent = 'Student login';

    const doCopy = () => copyText(shareUrl)
      .then(() => showToast('Portfolio link copied to clipboard'))
      .catch(() => showToast(shareUrl));
    const doShare = () => {
      const trackText = domains.map(domainLabel).join(', ') || 'my SkillMe track';
      const text = `🚀 Excited to share my verified Proof of Work portfolio from SkillMe (@SkillMe)!

I completed ${approved} verified project milestone${approved === 1 ? '' : 's'} in ${trackText}, each reviewed by the SkillMe team before approval.

Check out my live portfolio:
👉 ${shareUrl}

Follow SkillMe on LinkedIn: https://www.linkedin.com/company/skill-me-intern/

#SkillMe #ProofOfWork #${FIELD_HASHTAG[domains[0]] || 'SoftwareEngineering'} #Internship`;
      window.open(`https://www.linkedin.com/feed/?shareActive=true&text=${encodeURIComponent(text)}`, '_blank', 'noopener');
    };

    document.getElementById('btn-copy').addEventListener('click', doCopy);
    document.getElementById('btn-print').addEventListener('click', () => window.print());
    const shareBtn = document.getElementById('btn-share');
    if (shareBtn) shareBtn.addEventListener('click', doShare);

    container.addEventListener('click', (e) => {
      const preview = e.target.closest('[data-preview]');
      if (preview) { openPostModal(preview.dataset.preview, preview.dataset.url, preview.dataset.title); return; }
      const action = e.target.closest('[data-action]');
      if (!action) return;
      if (action.dataset.action === 'copy') doCopy();
      if (action.dataset.action === 'share') doShare();
    });

    document.title = `${name} — Proof of Work Portfolio — SkillMe`;
    const desc = `${name}'s verified SkillMe Proof of Work: ${approved} approved milestone${approved === 1 ? '' : 's'}${domains.length ? ' in ' + domains.map(domainLabel).join(', ') : ''}.`;
    const metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) metaDesc.setAttribute('content', desc);
  }

  // ── Boot ────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', async () => {
    initThemeToggle();
    initPostModal();
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
