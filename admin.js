// ─── SkillMe Admin Console — JS ───
function getAPI() {
  if (window.SKILLME_API) return window.SKILLME_API;
  const isLocal = (
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1' ||
    window.location.hostname.startsWith('192.168.')
  );
  return isLocal ? 'http://localhost:8000' : 'https://skill-me.onrender.com';
}

// Dynamically resolves API to prevent stale localhost fallbacks
var API = getAPI();
try {
  Object.defineProperty(window, 'API', {
    get: function() { return getAPI(); },
    set: function(v) { window.SKILLME_API = v; },
    configurable: true
  });
} catch(e) {}

// ─── THEME COLOURS ───
// CSS variables can't be used inside <canvas>, so charts read the resolved token values.
const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
function cssColor(name, alpha) {
  const v = cssVar(name);
  if (alpha === undefined) return v;
  const m = /^#([0-9a-f]{6})$/i.exec(v);
  if (!m) return v;
  const n = parseInt(m[1], 16);
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}
// Translucent version of any CSS colour (including var(--x)) for inline HTML styles.
const tint = (color, pct) => `color-mix(in srgb, ${color} ${pct}%, transparent)`;

let adminKey = '';
let allStudents = [];
let allAlumni = [];
let currentPage = 'overview';
let appStarted = false;

const STUDENTS_PAGE_SIZE = 15;
// Server-side paginated lists — only one page (15 rows) is ever in memory/DOM.
const studentsState = { page: 1, q: '', status: '', total: 0, totalPages: 1 };
const alumniState   = { page: 1, q: '', total: 0, totalPages: 1 };

const PAGE_META = {
  overview:  { title: 'Overview',  subtitle: 'Platform summary and recent activity' },
  students:  { title: 'Students',  subtitle: 'Shortlist and enroll applicants' },
  alumni:    { title: 'Alumni',    subtitle: 'Students who completed their internship' },
  analytics: { title: 'Analytics', subtitle: 'Domain performance, completion rates and revenue at a glance' },
  email:     { title: 'Email Settings', subtitle: 'Brevo SMTP relay — test and monitor email delivery' },
  submissions: { title: 'Submissions', subtitle: 'Review and approve/reject weekly LinkedIn submissions' },
  'urgent-requests': { title: 'Urgent Requests', subtitle: 'Expedited (24h) certificate/LOR/portfolio processing requests' },
  announcements: { title: 'Announcements', subtitle: 'Send platform-wide update emails to students' },
};

// ─── AUTH ───
async function handleLogin(e) {
  if (e && e.preventDefault) e.preventDefault();
  return adminLogin();
}

async function adminLogin() {
  const keyInput = document.getElementById('admin-key-input') || document.getElementById('api-key-input');
  const key = keyInput ? keyInput.value.trim() : '';
  const errEl = document.getElementById('login-error');
  const btn = document.getElementById('admin-login-btn') || document.getElementById('login-btn');
  if (!key) { if (errEl) errEl.textContent = 'Please enter your secret passkey.'; return; }

  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Verifying Passkey...';
  }
  try {
    const res = await fetch(`${getAPI()}/api/admin/stats`, {
      headers: { 'X-Admin-Key': key }
    });
    if (res.status === 403) {
      if (errEl) errEl.textContent = 'Invalid admin passkey. Please try again.';
      if (btn) { btn.disabled = false; btn.textContent = 'Access console →'; }
      return;
    }
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `Server error (${res.status})`);
    }
    adminKey = key;
    sessionStorage.setItem('skillme_admin_key', key);

    showApp(await res.json().catch(() => null));
    if (btn) { btn.disabled = false; btn.textContent = 'Access console →'; }

  } catch (e) {
    console.error("Admin login error:", e);
    if (errEl) errEl.textContent = e.message || 'Could not connect to backend.';
    if (btn) { btn.disabled = false; btn.textContent = 'Access console →'; }
  }
}

function showApp(prefetchedStats) {
  const overlay = document.getElementById('login-overlay');
  if (overlay) {
    overlay.style.display = 'none';
    overlay.style.opacity = '0';
    overlay.style.pointerEvents = 'none';
    overlay.classList.add('hidden');
  }
  const app = document.getElementById('app');
  if (app) {
    app.style.display = 'flex';
  }
  // Both the saved-key check and adminLogin() can land here on page load —
  // only start the render loops, clock and data fetches once.
  if (appStarted) return;
  appStarted = true;
  loadOverview(prefetchedStats);
}

function logoutAdmin() {
  sessionStorage.removeItem('skillme_admin_key');
  adminKey = '';
  const overlay = document.getElementById('login-overlay');
  const app = document.getElementById('app');
  if (overlay) {
    overlay.style.display = 'grid';
    overlay.style.opacity = '1';
    overlay.style.pointerEvents = '';
    overlay.classList.remove('hidden');
  }
  if (app) app.style.display = 'none';
}

window.addEventListener('themechange', () => { if (currentPage === 'analytics') loadAnalytics(); });

document.addEventListener('DOMContentLoaded', () => {
  localStorage.removeItem('skillme_admin_key'); // older sessions kept the key forever
});

// ─── NAVIGATION ───
function navigate(page) {
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.page').forEach(el => el.classList.remove('active'));
  document.getElementById(`nav-${page}`)?.classList.add('active');
  document.getElementById(`page-${page}`)?.classList.add('active');
  const meta = PAGE_META[page] || {};
  document.getElementById('topbar-title').textContent = meta.title || page;
  document.getElementById('topbar-subtitle').textContent = meta.subtitle || '';
  currentPage = page;
  if (page === 'overview') loadOverview();
  if (page === 'students') loadStudents();
  if (page === 'alumni') loadAlumni();
  if (page === 'analytics') loadAnalytics();
  if (page === 'email') { loadEmailStatus(); loadEmailDirectory(); loadEmailLogs(); loadEmailAggStats(); }
  if (page === 'submissions') loadSubmissions();
  if (page === 'urgent-requests') loadUrgentRequests();
  if (page === 'announcements') previewAnnouncement();
  if (page === 'reminders') loadInactiveStudents();
}

function refreshCurrentPage() { navigate(currentPage); }

// ─── API HELPER ───
async function api(path, opts = {}) {
  const res = await fetch(`${getAPI()}${path}`, {
    ...opts,
    headers: { 'X-Admin-Key': adminKey, 'Content-Type': 'application/json', ...(opts.headers || {}) }
  });
  if (res.status === 403 && adminKey) {
    logoutAdmin();
    const errEl = document.getElementById('login-error');
    if (errEl) errEl.textContent = 'Session expired. Please enter your passkey again.';
    throw new Error('Session expired');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// ─── TOAST ───
function toast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  const icon = type === 'success' ? '✅' : '❌';
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  // textContent, never innerHTML — messages often contain student-supplied names
  const iconEl = document.createElement('span');
  iconEl.textContent = icon;
  const msgEl = document.createElement('span');
  msgEl.textContent = message;
  el.append(iconEl, msgEl);
  container.appendChild(el);
  setTimeout(() => {
    el.style.animation = 'toast-out 0.3s ease forwards';
    setTimeout(() => el.remove(), 300);
  }, 3500);
}

// ─── MODALS ───
function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }

// Close modal on backdrop click
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.classList.remove('open'); });
});

// ─── ESCAPING (student-supplied data is untrusted) ───
function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
// Safe literal for inline onclick handlers — survives names like O'Brien.
function jsArg(v) { return esc(JSON.stringify(String(v ?? ''))); }
function safeUrl(u) { return /^https?:\/\//i.test(String(u || '')) ? esc(u) : ''; }

// ─── STATUS BADGE ───
function statusBadge(status) {
  const s = esc(status);
  return `<span class="badge badge-${s}">${s}</span>`;
}

// ─── FORMAT DATE ───
function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

// ─── OVERVIEW ───
async function loadOverview(prefetchedStats) {
  loadStats(prefetchedStats);
  loadRecentApplications();
  loadShortlisted();
}

// `prefetched` is the /stats payload when the caller already has it (login). Other callers
// pass `true`/nothing, which just means "fetch it".
async function loadStats(prefetched) {
  const grid = document.getElementById('stats-grid');
  // Render hosts spin down when idle; the first request can take a while.
  const wakeHint = setTimeout(() => {
    if (grid && grid.querySelector('.loading-overlay')) {
      grid.innerHTML = `<div class="loading-overlay"><div class="spinner"></div> Waking the server — the first load after a quiet spell can take up to a minute…</div>`;
    }
  }, 4000);
  try {
    const data = prefetched && typeof prefetched === 'object' ? prefetched : await api('/api/admin/stats');
    renderStats(data);
  } catch (e) {
    grid.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><div class="empty-state-text">${esc(e.message)}</div></div>`;
  } finally {
    clearTimeout(wakeHint);
  }
}

function pctChange(now, prev) {
  if (!prev) return now ? 'new this week' : '—';
  const c = Math.round((now - prev) * 100 / prev);
  return `${c >= 0 ? '▲' : '▼'} ${Math.abs(c)}% vs previous 7 days`;
}

function renderStats(data) {
  const grid = document.getElementById('stats-grid');
  grid.innerHTML = `
    ${statCard('👥', data.total_students, 'Total Students', 'var(--accent-wash)', 'var(--accent-text)')}
    ${statCard('📋', data.pending_applications, 'Pending Applications', 'var(--accent-wash)', 'var(--accent-text)')}
    ${statCard('🟢', data.enrolled_students, 'Enrolled Students', 'var(--ok-wash)', 'var(--ok)')}
    ${statCard('📝', data.pending_submissions, 'Pending Submissions', 'var(--accent-wash)', 'var(--accent-text)')}
  `;
  const pulse = document.getElementById('pulse-grid');
  if (pulse && data.apps_7d !== undefined) {
    const reviewed = (data.approved_30d || 0) + (data.rejected_30d || 0);
    const oldest = data.oldest_pending_days;
    pulse.innerHTML = `
      ${analyticsCard('🆕', data.apps_7d || 0, 'Applications (7 days)', `${data.apps_today || 0} today · ${pctChange(data.apps_7d || 0, data.apps_prev_7d || 0)}`)}
      ${analyticsCard('⚡', data.active_7d || 0, 'Active People (7 days)', 'logged in or submitted a task')}
      ${analyticsCard('📤', data.subs_7d || 0, 'Task Submissions (7 days)', pctChange(data.subs_7d || 0, data.subs_prev_7d || 0))}
      ${analyticsCard('🤝', data.enrolled_7d || 0, 'New Enrollments (7 days)', `${(data.shortlisted_students || 0).toLocaleString('en-IN')} shortlisted, waiting to enroll`)}
      ${analyticsCard('✅', reviewed ? `${data.approval_rate_30d}%` : '—', 'Approval Rate (30 days)', `${data.approved_30d || 0} approved · ${data.rejected_30d || 0} rejected`)}
      ${analyticsCard('⏳', oldest === null || oldest === undefined ? '—' : `${oldest}d`, 'Oldest Pending Review', `${data.pending_submissions || 0} submissions waiting`)}
      ${analyticsCard('🏁', data.completed_total || 0, 'Completed All 4 Weeks', 'students with every week approved')}
      ${analyticsCard('🎯', data.eligible_unpaid || 0, 'Eligible but Unpaid', 'finished 3+ weeks, no payment yet — nudge them')}
    `;
  }
  setNavBadge('pending-badge', data.pending_applications);
  setNavBadge('submissions-badge', data.pending_submissions);
  setNavBadge('alumni-badge', data.total_alumni);
  updateUrgentRequestsBadge(data.pending_urgent_requests || 0);
}

function setNavBadge(id, count) {
  const badge = document.getElementById(id);
  if (!badge) return;
  badge.style.display = count > 0 ? 'inline-flex' : 'none';
  badge.textContent = count || 0;
}

function statCard(icon, value, label, bg, color) {
  return `
    <div class="stat-card">
      <div class="stat-card-top">
        <div class="stat-card-label">${label}</div>
        <div class="stat-card-icon">${icon}</div>
      </div>
      <div class="stat-card-value">${(value ?? 0).toLocaleString()}</div>
    </div>`;
}

// Action buttons shared by every student table. Lifecycle is just
// applied → shortlisted → enrolled (→ completed), with drop / re-enroll.
function studentActions(s, { compact = false } = {}) {
  const name = jsArg(`${s.first_name} ${s.last_name}`);
  const email = jsArg(s.email);
  const btns = [];
  if (s.status === 'applied') {
    btns.push(`<button class="btn btn-sm btn-tone-accent" onclick="updateStatus(${s.id},'shortlisted', this)">Shortlist</button>`);
  }
  if (['applied', 'shortlisted', 'dropped'].includes(s.status)) {
    btns.push(`<button class="btn btn-sm btn-tone-ok" onclick="enrollStudent(${s.id}, ${name}, this)">${s.status === 'dropped' ? 'Re-enroll' : 'Enroll'}</button>`);
  }
  if (!compact && ['enrolled', 'completed'].includes(s.status) && s.batch_id) {
    btns.push(`<button class="btn btn-sm btn-tone-accent" onclick="issueCertificate(${s.id}, ${Number(s.batch_id)}, ${name})">🏅 Certificate</button>`);
  }
  if (!compact && s.status !== 'dropped') {
    btns.push(`<button class="btn btn-sm btn-tone-danger" onclick="dropStudent(${s.id}, ${name}, this)">Drop</button>`);
  }
  btns.push(`<button class="btn btn-sm btn-tone-danger" onclick="deleteStudent(${s.id}, ${name}, ${email})" title="Permanently delete entire record from database">🗑️${compact ? '' : ' Delete'}</button>`);
  return `<div style="display:flex;gap:6px;flex-wrap:wrap;">${btns.join('')}</div>`;
}

function compactStudentTable(students, emptyIcon, emptyText) {
  if (!students.length) {
    return `<div class="empty-state"><div class="empty-state-icon">${emptyIcon}</div><div class="empty-state-text">${emptyText}</div></div>`;
  }
  return `
    <table>
      <thead><tr><th>Name</th><th>Domain</th><th>Applied</th><th>Action</th></tr></thead>
      <tbody>
        ${students.map(s => `
          <tr>
            <td>
              <div style="font-weight:500;">${esc(s.first_name)} ${esc(s.last_name)}</div>
              <div style="font-size:0.75rem;color:var(--text-muted);">${esc(s.email)}</div>
            </td>
            <td>${esc(s.domain || '—')}</td>
            <td>${fmtDate(s.created_at)}</td>
            <td>${studentActions(s, { compact: true })}</td>
          </tr>`).join('')}
      </tbody>
    </table>`;
}

async function loadRecentApplications(silent = false) {
  const el = document.getElementById('recent-applications');
  if (!el) return;
  if (!silent && !el.querySelector('table')) {
    el.innerHTML = `<div class="loading-overlay"><div class="spinner"></div></div>`;
  }
  try {
    const data = await api('/api/admin/students?status=applied&limit=5');
    el.innerHTML = compactStudentTable(data.students || [], '🎉', 'No pending applications');
  } catch(e) {
    if (!silent) el.innerHTML = `<div class="empty-state"><div class="empty-state-text">${esc(e.message)}</div></div>`;
  }
}

async function loadShortlisted(silent = false) {
  const el = document.getElementById('overview-shortlisted');
  if (!el) return;
  if (!silent && !el.querySelector('table')) {
    el.innerHTML = `<div class="loading-overlay"><div class="spinner"></div></div>`;
  }
  try {
    const data = await api('/api/admin/students?status=shortlisted&limit=5');
    el.innerHTML = compactStudentTable(data.students || [], '✅', 'No shortlisted students waiting to be enrolled');
    const sub = document.getElementById('overview-shortlisted-count');
    if (sub) sub.textContent = data.total ? `${data.total} waiting to be enrolled` : 'Ready to enroll';
  } catch(e) {
    if (!silent) el.innerHTML = `<div class="empty-state"><div class="empty-state-text">${esc(e.message)}</div></div>`;
  }
}

function refreshStudentViews() {
  if (currentPage === 'overview') {
    loadRecentApplications(true);
    loadShortlisted(true);
  }
  if (currentPage === 'students') loadStudents(true);
  if (currentPage === 'alumni') loadAlumni(true);
  loadStats();
}

// ─── PAGINATION ───
function renderPager(elId, state, loaderName) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (!state.total) { el.innerHTML = ''; return; }
  const pageSize = state.limit || STUDENTS_PAGE_SIZE;
  const from = (state.page - 1) * pageSize + 1;
  const to = Math.min(state.total, state.page * pageSize);
  el.innerHTML = `
    <span>Showing ${from}–${to} of ${state.total} · Page ${state.page} of ${state.totalPages}</span>
    <div style="display:flex;gap:8px;">
      <button class="btn btn-ghost btn-sm" onclick="${loaderName}(${state.page - 1})" ${state.page <= 1 ? 'disabled' : ''}>← Prev</button>
      <button class="btn btn-ghost btn-sm" onclick="${loaderName}(${state.page + 1})" ${state.page >= state.totalPages ? 'disabled' : ''}>Next →</button>
    </div>`;
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// ─── STUDENTS ───
let _studentsReq = 0;
async function loadStudents(silent = false) {
  const tbody = document.getElementById('students-tbody');
  if (!tbody) return;
  if (!silent) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="loading-overlay"><div class="spinner"></div></div></td></tr>`;
  }
  const reqId = ++_studentsReq;
  const params = new URLSearchParams({ page: studentsState.page, limit: STUDENTS_PAGE_SIZE, paid: 'false' });
  if (studentsState.status) params.set('status', studentsState.status);
  if (studentsState.q) params.set('q', studentsState.q);
  try {
    const data = await api(`/api/admin/students?${params}`);
    if (reqId !== _studentsReq) return; // a newer search/page request superseded this one
    studentsState.total = data.total || 0;
    studentsState.totalPages = data.total_pages || 1;
    // Deleting the last row of the last page — step back instead of showing an empty page
    if (!data.students.length && studentsState.page > 1 && studentsState.total) {
      studentsState.page = studentsState.totalPages;
      return loadStudents(silent);
    }
    allStudents = data.students || [];
    renderStudents(allStudents);
    renderPager('students-pagination', studentsState, 'goToStudentsPage');
  } catch(e) {
    if (reqId !== _studentsReq) return;
    if (!silent) {
      tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="empty-state-text">${esc(e.message)}</div></div></td></tr>`;
    }
  }
}

function goToStudentsPage(page) {
  studentsState.page = Math.max(1, Math.min(page, studentsState.totalPages || 1));
  loadStudents();
}

const _debouncedStudentSearch = debounce(() => loadStudents(), 300);
function filterStudents() {
  studentsState.q = (document.getElementById('student-search')?.value || '').trim();
  studentsState.status = document.getElementById('status-filter')?.value || '';
  studentsState.page = 1;
  _debouncedStudentSearch();
}

function showApplicationsToReview() {
  const sel = document.getElementById('status-filter');
  if (sel) sel.value = 'applied';
  studentsState.status = 'applied';
  studentsState.page = 1;
  navigate('students');
}

function renderStudents(students) {
  const tbody = document.getElementById('students-tbody');
  if (!students.length) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="empty-state-icon">🔍</div><div class="empty-state-text">No students found</div></div></td></tr>`;
    return;
  }
  tbody.innerHTML = students.map(s => `
    <tr>
      <td>
        <div style="display:flex;align-items:center;gap:10px;">
          <div class="avatar">${esc(((s.first_name || '?')[0] || '?').toUpperCase())}</div>
          <div>
            <div style="font-weight:500;">${esc(s.first_name)} ${esc(s.last_name)}</div>
            ${s.college ? `<div style="font-size:0.72rem;color:var(--text-muted);">${esc(s.college)}</div>` : ''}
          </div>
        </div>
      </td>
      <td style="color:var(--text-secondary);font-size:0.82rem;">${esc(s.email)}</td>
      <td>${esc(s.domain || '—')}${s.other_domains ? `<div style="font-size:0.72rem;color:var(--text-muted);" title="Same email, other tracks">Also applied: ${esc(s.other_domains)}</div>` : ''}${s.quiz_total ? `<div style="font-size:0.72rem;color:var(--text-muted);" title="Screening quiz score">Quiz ${esc(s.quiz_score)}/${esc(s.quiz_total)}</div>` : ''}</td>
      <td>${statusBadge(s.status)}</td>
      <td style="color:var(--text-muted);font-size:0.82rem;">${fmtDate(s.created_at)}</td>
      <td>${studentActions(s)}</td>
    </tr>`).join('');
}

// ─── ALUMNI ───
let _alumniReq = 0;
async function loadAlumni(silent = false) {
  const tbody = document.getElementById('alumni-tbody');
  if (!tbody) return;
  if (!silent) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="loading-overlay"><div class="spinner"></div></div></td></tr>`;
  }
  const reqId = ++_alumniReq;
  const params = new URLSearchParams({ page: alumniState.page, limit: STUDENTS_PAGE_SIZE, paid: 'true' });
  if (alumniState.q) params.set('q', alumniState.q);
  try {
    const data = await api(`/api/admin/students?${params}`);
    if (reqId !== _alumniReq) return;
    alumniState.total = data.total || 0;
    alumniState.totalPages = data.total_pages || 1;
    if (!data.students.length && alumniState.page > 1 && alumniState.total) {
      alumniState.page = alumniState.totalPages;
      return loadAlumni(silent);
    }
    allAlumni = data.students || [];
    renderAlumni(allAlumni);
    renderPager('alumni-pagination', alumniState, 'goToAlumniPage');
    if (!alumniState.q) setNavBadge('alumni-badge', alumniState.total);
  } catch(e) {
    if (reqId !== _alumniReq) return;
    if (!silent) {
      tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="empty-state-text">${esc(e.message)}</div></div></td></tr>`;
    }
  }
}

function goToAlumniPage(page) {
  alumniState.page = Math.max(1, Math.min(page, alumniState.totalPages || 1));
  loadAlumni();
}

const _debouncedAlumniSearch = debounce(() => loadAlumni(), 300);
function filterAlumni() {
  alumniState.q = (document.getElementById('alumni-search')?.value || '').trim();
  alumniState.page = 1;
  _debouncedAlumniSearch();
}

function renderAlumni(alumni) {
  const tbody = document.getElementById('alumni-tbody');
  if (!tbody) return;
  if (!alumni.length) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="empty-state-icon">🎓</div><div class="empty-state-text">${alumniState.q ? 'No alumni match your search' : 'No alumni yet — students appear here after completing payment'}</div></div></td></tr>`;
    return;
  }
  tbody.innerHTML = alumni.map(s => {
    const name = jsArg(`${s.first_name} ${s.last_name}`);
    return `
    <tr>
      <td>
        <div style="display:flex;align-items:center;gap:10px;">
          <div class="avatar is-ok">${esc(((s.first_name || '?')[0] || '?').toUpperCase())}</div>
          <div>
            <div style="font-weight:500;">${esc(s.first_name)} ${esc(s.last_name)}</div>
            ${s.college ? `<div style="font-size:0.72rem;color:var(--text-muted);">${esc(s.college)}</div>` : ''}
          </div>
        </div>
      </td>
      <td style="color:var(--text-secondary);font-size:0.82rem;">${esc(s.email)}</td>
      <td>${esc(s.domain || '—')}</td>
      <td><span style="padding:4px 10px;border-radius:20px;font-size:0.72rem;font-weight:600;background:var(--ok-wash);border:1px solid var(--ok-line);color:var(--ok);">✓ Paid</span></td>
      <td style="color:var(--text-muted);font-size:0.82rem;">${fmtDate(s.paid_at || s.created_at)}</td>
      <td>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          ${s.batch_id ? `<button class="btn btn-sm btn-tone-accent" onclick="issueCertificate(${s.id}, ${Number(s.batch_id)}, ${name})">🏅 Certificate</button>` : ''}
          <button class="btn btn-sm btn-tone-danger" onclick="deleteStudent(${s.id}, ${name}, ${jsArg(s.email)})" title="Permanently delete entire record from database">🗑️ Delete</button>
        </div>
      </td>
    </tr>`;
  }).join('');
}

// ─── STUDENT ACTIONS ───
function setBusy(btn, label) {
  if (!btn) return () => {};
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span style="display:inline-block;width:11px;height:11px;border:2px solid currentColor;border-top-color:transparent;border-radius:50%;animation:spin 0.6s linear infinite;vertical-align:middle;margin-right:4px;"></span> ${label}`;
  return () => { btn.disabled = false; btn.innerHTML = orig; };
}

async function updateStatus(studentId, newStatus, btn) {
  const restore = setBusy(btn, 'Saving...');
  try {
    await api(`/api/admin/students/${studentId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status: newStatus })
    });
    toast(`Student status updated to "${newStatus}"`);
    refreshStudentViews();
  } catch(e) {
    toast(e.message, 'error');
    restore();
  }
}

async function dropStudent(studentId, name, btn) {
  if (!confirm(`Drop ${name}?\n\nTheir progress, payments and certificates are kept — you can re-enroll them later and they will continue where they left off.`)) return;
  return updateStatus(studentId, 'dropped', btn);
}

async function deleteStudent(studentId, name, email) {
  if (!confirm(`Are you sure you want to PERMANENTLY DELETE "${name}" (${email}) from the database?\n\nThis will completely wipe:\n- Student profile & application\n- Enrollment & weekly progress\n- Task submissions & urgent requests\n- Certificates & payment records\n- OTP tokens & email logs\n\nWhen this user returns, they will be treated as a completely brand-new user.\n\nThis action cannot be undone.`)) {
    return;
  }
  try {
    await api(`/api/admin/students/${studentId}`, { method: 'DELETE' });
    toast(`🗑️ Permanently deleted ${name} (${email}) from database.`);
    refreshStudentViews();
  } catch(e) {
    toast(`Failed to delete student: ${e.message}`, 'error');
  }
}

async function issueCertificate(studentId, batchId, name) {
  // Open the tab synchronously so popup blockers allow it, then point it at the certificate.
  const win = window.open('', '_blank');
  try {
    const data = await api(`/api/certificates/issue/${studentId}/${batchId}`, { method: 'POST' });
    toast(`Certificate ${data.cert_id} issued to ${name}!`);
    const certUrl = `${window.SKILLME_FRONTEND || window.location.origin}/certificate.html?cert_id=${encodeURIComponent(data.cert_id)}`;
    if (win) win.location.href = certUrl; else window.open(certUrl, '_blank');
  } catch(e) {
    if (win) win.close();
    toast(e.message, 'error');
  }
}

async function enrollStudent(studentId, name, btn) {
  const restore = setBusy(btn, 'Enrolling...');
  try {
    const data = await api(`/api/admin/students/${studentId}/enroll`, { method: 'POST' });
    toast(data.reactivated ? `✅ Re-enrolled ${name} — previous progress kept` : `✅ Enrolled ${name}! Offer letter is on its way.`);
    refreshStudentViews();
  } catch(e) {
    toast(`Enrollment failed: ${e.message}`, 'error');
    restore();
  }
}

// ─── EMAIL SETTINGS ───
async function loadEmailStatus() {
  const badge = document.getElementById('email-status-badge');
  const fromEl = document.getElementById('email-from-display');
  if (!badge) return;
  try {
    // Try sending a test via a simple health ping to the backend
    const res = await fetch(`${API}/api/admin/stats`, { headers: { 'X-Admin-Key': adminKey } });
    if (res.ok) {
      badge.style.background = 'var(--ok-wash)';
      badge.style.borderColor = 'var(--ok-line)';
      badge.style.color = 'var(--ok)';
      badge.textContent = '\u25cf Email Enabled';
    }
  } catch(e) {
    badge.style.background = 'var(--danger-wash)';
    badge.style.borderColor = 'var(--danger-line)';
    badge.style.color = 'var(--danger)';
    badge.textContent = '\u25cf Offline';
  }
  // Show from email from .env config — we can infer from backend info
  if (fromEl) fromEl.textContent = 'noreply@skillme.in';
}

async function sendTestEmail() {
  const input = document.getElementById('test-email-input');
  const btn = document.getElementById('test-email-btn');
  const result = document.getElementById('test-email-result');
  const email = input.value.trim();
  if (!email || !email.includes('@')) {
    result.style.display = 'block';
    result.style.color = 'var(--danger)';
    result.textContent = '\u274c Please enter a valid email address.';
    return;
  }
  btn.textContent = 'Sending...';
  btn.disabled = true;
  result.style.display = 'none';
  try {
    const data = await api('/api/admin/email/test', {
      method: 'POST',
      body: JSON.stringify({ to_email: email })
    });
    result.style.display = 'block';
    if (data.status === 'sent') {
      result.style.color = 'var(--ok)';
      result.textContent = `\u2705 Test email sent successfully to ${email}! Check your inbox.`;
      toast('Test email sent!');
    } else {
      result.style.color = 'var(--danger)';
      result.textContent = `\u274c ${data.message || 'Failed to send email. Check SMTP credentials.'}`;
    }
  } catch(e) {
    result.style.display = 'block';
    result.style.color = 'var(--danger)';
    result.textContent = `\u274c ${e.message}`;
  } finally {
    btn.textContent = 'Send Test';
    btn.disabled = false;
  }
}

// ─── EMAIL DIRECTORY (per-student contact + delivery health) ───
const emailDirectoryState = { page: 1, q: '', total: 0, totalPages: 1, limit: STUDENTS_PAGE_SIZE };
let _emailDirReq = 0;

async function loadEmailDirectory(silent = false) {
  const tbody = document.getElementById('email-directory-tbody');
  if (!tbody) return;
  if (!silent) {
    tbody.innerHTML = `<tr><td colspan="8"><div class="loading-overlay"><div class="spinner"></div></div></td></tr>`;
  }
  const reqId = ++_emailDirReq;
  const params = new URLSearchParams({ page: emailDirectoryState.page, limit: emailDirectoryState.limit });
  if (emailDirectoryState.q) params.set('q', emailDirectoryState.q);
  try {
    const data = await api(`/api/admin/email/directory?${params}`);
    if (reqId !== _emailDirReq) return;
    emailDirectoryState.total = data.total || 0;
    emailDirectoryState.totalPages = data.total_pages || 1;
    if (!data.students.length && emailDirectoryState.page > 1 && emailDirectoryState.total) {
      emailDirectoryState.page = emailDirectoryState.totalPages;
      return loadEmailDirectory(silent);
    }
    renderEmailDirectory(data.students || []);
    renderPager('email-directory-pagination', emailDirectoryState, 'goToEmailDirectoryPage');
  } catch(e) {
    if (reqId !== _emailDirReq) return;
    tbody.innerHTML = `<tr><td colspan="8"><div class="empty-state"><div class="empty-state-text">${esc(e.message)}</div></div></td></tr>`;
  }
}

function renderEmailDirectory(students) {
  const tbody = document.getElementById('email-directory-tbody');
  if (!tbody) return;
  if (!students.length) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--text-secondary);padding:32px;">No students found.</td></tr>`;
    return;
  }
  tbody.innerHTML = students.map(s => {
    const bounced = s.emails_bounced > 0
      ? `<span style="color:var(--danger);font-weight:700;">${s.emails_bounced}</span>`
      : `<span style="color:var(--text-secondary);">0</span>`;
    const failed = s.emails_failed > 0
      ? `<span style="color:var(--warn);font-weight:700;">${s.emails_failed}</span>`
      : `<span style="color:var(--text-secondary);">0</span>`;
    return `
    <tr>
      <td style="font-weight:500;">${esc(s.first_name)} ${esc(s.last_name)}</td>
      <td style="font-size:0.82rem;color:var(--text-secondary);">${esc(s.email)}</td>
      <td>${esc(s.domain || '—')}</td>
      <td>${statusBadge(s.status)}</td>
      <td>${s.emails_sent || 0}</td>
      <td>${failed}</td>
      <td>${bounced}</td>
      <td style="font-size:0.8rem;color:var(--text-secondary);">${s.last_email_type ? esc(s.last_email_type) + ' · ' + fmtDate(s.last_email_at) : '—'}</td>
    </tr>`;
  }).join('');
}

function goToEmailDirectoryPage(page) {
  emailDirectoryState.page = Math.max(1, Math.min(page, emailDirectoryState.totalPages || 1));
  loadEmailDirectory();
}

const _debouncedEmailDirSearch = debounce(() => loadEmailDirectory(), 300);
function debounceEmailDirectory() {
  emailDirectoryState.q = (document.getElementById('email-directory-search')?.value || '').trim();
  emailDirectoryState.page = 1;
  _debouncedEmailDirSearch();
}

// ─── EMAIL SEND LOG ───
const emailLogState = { page: 1, total: 0, totalPages: 1, limit: 50 };
let _emailLogReq = 0;

async function loadEmailLogs(silent = false) {
  const tbody = document.getElementById('email-log-tbody');
  if (!tbody) return;
  if (!silent) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="loading-overlay"><div class="spinner"></div></td></tr>`;
  }
  const reqId = ++_emailLogReq;
  const type = document.getElementById('email-log-type-filter')?.value || '';
  const recipient = (document.getElementById('email-log-recipient-filter')?.value || '').trim();
  const status = document.getElementById('email-log-status-filter')?.value || '';
  const params = new URLSearchParams({ page: emailLogState.page, limit: emailLogState.limit });
  if (type) params.set('email_type', type);
  if (recipient) params.set('recipient', recipient);
  if (status) params.set('status', status);
  try {
    const data = await api(`/api/admin/email/logs?${params}`);
    if (reqId !== _emailLogReq) return;
    emailLogState.total = data.total || 0;
    emailLogState.totalPages = data.total_pages || 1;
    renderEmailLogs(data.logs || []);
    renderPager('email-log-pagination', emailLogState, 'goToEmailLogPage');
  } catch(e) {
    if (reqId !== _emailLogReq) return;
    tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state"><div class="empty-state-text">${esc(e.message)}</div></div></td></tr>`;
  }
}

function renderEmailLogs(logs) {
  const tbody = document.getElementById('email-log-tbody');
  if (!tbody) return;
  if (!logs.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-secondary);padding:32px;">No emails match these filters.</td></tr>`;
    return;
  }
  tbody.innerHTML = logs.map(l => {
    const statusChip = l.status === 'sent'
      ? `<span style="color:var(--ok);font-weight:600;">Sent</span>`
      : `<span style="color:var(--danger);font-weight:600;" title="${esc(l.error_message || '')}">Failed</span>`;
    const engagement = [];
    if (l.delivered_at) engagement.push('📬 Delivered');
    if (l.opened_at) engagement.push(`👁️ Opened${l.opened_count > 1 ? ' x' + l.opened_count : ''}`);
    if (l.clicked_at) engagement.push(`🖱️ Clicked${l.clicked_count > 1 ? ' x' + l.clicked_count : ''}`);
    if (l.bounced_at) engagement.push(`⚠️ Bounced${l.bounce_type ? ' (' + esc(l.bounce_type) + ')' : ''}`);
    if (l.spam_reported_at) engagement.push('🚫 Spam');
    if (l.unsubscribed_at) engagement.push('✋ Unsubscribed');
    return `
    <tr>
      <td style="font-size:0.78rem;color:var(--text-secondary);">${fmtDate(l.sent_at)}</td>
      <td style="font-size:0.8rem;">${esc(l.email_type)}</td>
      <td style="font-size:0.82rem;">${esc(l.recipient_email)}</td>
      <td style="font-size:0.82rem;color:var(--text-secondary);">${esc(l.subject)}</td>
      <td style="font-size:0.8rem;color:var(--text-secondary);">${esc(l.student_name || '—')}</td>
      <td>${statusChip}</td>
      <td style="font-size:0.72rem;color:var(--text-secondary);">${engagement.join('<br>') || '—'}</td>
    </tr>`;
  }).join('');
}

function goToEmailLogPage(page) {
  emailLogState.page = Math.max(1, Math.min(page, emailLogState.totalPages || 1));
  loadEmailLogs();
}

const _debouncedEmailLogSearch = debounce(() => { emailLogState.page = 1; loadEmailLogs(); }, 300);
function debounceEmailLogs() { _debouncedEmailLogSearch(); }

async function loadEmailAggStats() {
  const el = document.getElementById('email-agg-stats');
  if (!el) return;
  try {
    const s = await api('/api/admin/email/stats');
    const chip = (label, value, color) => `
      <div style="padding:10px 16px;border-radius:8px;background:${tint(color,10)};border:1px solid ${tint(color,30)};font-size:0.8rem;min-width:110px;">
        <div style="color:var(--text-secondary);font-size:0.68rem;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;">${label}</div>
        <div style="color:${color};font-weight:700;font-size:1.05rem;">${(value ?? 0).toLocaleString()}</div>
      </div>`;
    el.innerHTML = [
      chip('Total Sent', s.total, 'var(--accent-text)'),
      chip('Delivered', s.delivered, 'var(--ok)'),
      chip('Opened', s.opened, 'var(--info)'),
      chip('Clicked', s.clicked, 'var(--violet)'),
      chip('Failed', s.failed, 'var(--danger)'),
      chip('Bounced', s.bounced, 'var(--warn)'),
      chip('Spam Reports', s.spam_reported, 'var(--danger)'),
    ].join('');
  } catch(e) {
    el.innerHTML = `<div class="empty-state-text" style="font-size:0.8rem;">${esc(e.message)}</div>`;
  }
}

// ─── SUBMISSIONS (LinkedIn URL Review Queue) ───
let allSubmissions = [];
let selectedSubmissionIds = new Set();
let allUrgentRequests = [];

async function loadSubmissions() {
  const tbody = document.getElementById('submissions-tbody');
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="8"><div class="loading-overlay"><div class="spinner"></div></div></td></tr>`;
  selectedSubmissionIds.clear();
  updateSubmissionsBulkBar();
  const status = document.getElementById('submission-status-filter')?.value || 'pending';
  try {
    const qs = status ? `?status=${encodeURIComponent(status)}` : '';
    const data = await api(`/api/admin/submissions${qs}`);
    allSubmissions = data.submissions || [];
    renderSubmissions(allSubmissions);
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="8"><div class="empty-state"><div class="empty-state-text">${e.message}</div></div></td></tr>`;
  }
}

function renderSubmissions(submissions) {
  const tbody = document.getElementById('submissions-tbody');
  if (!tbody) return;
  if (!submissions.length) {
    tbody.innerHTML = `<tr><td colspan="8"><div class="empty-state"><div class="empty-state-icon">📝</div><div class="empty-state-text">No submissions found</div></div></td></tr>`;
    return;
  }
  tbody.innerHTML = submissions.map(s => `
    <tr>
      <td><input type="checkbox" class="submission-row-check" data-id="${s.id}" ${selectedSubmissionIds.has(s.id) ? 'checked' : ''} onchange="toggleSubmissionSelected(${s.id}, this.checked)" /></td>
      <td>
        <div style="font-weight:500;">${esc(s.first_name)} ${esc(s.last_name)}</div>
        <div style="font-size:0.75rem;color:var(--text-muted);">${esc(s.domain)}</div>
      </td>
      <td style="color:var(--text-secondary);font-size:0.82rem;">${esc(s.email || '—')}</td>
      <td>Week ${Number(s.week) || '—'}</td>
      <td>${safeUrl(s.linkedin_url) ? `<a href="${safeUrl(s.linkedin_url)}" target="_blank" rel="noopener noreferrer" style="color:var(--info);">View Post ↗</a>` : esc(s.linkedin_url || '—')}</td>
      <td style="color:var(--text-muted);font-size:0.8rem;">${fmtDate(s.submitted_at)}</td>
      <td>${statusBadge(s.status)}</td>
      <td>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          ${s.status === 'pending' ? `
            <button class="btn btn-sm btn-tone-ok" onclick="approveSubmission(${s.id})">✅ Approve</button>
            <button class="btn btn-sm btn-tone-danger" onclick="rejectSubmission(${s.id})">❌ Reject</button>
          ` : '—'}
        </div>
      </td>
    </tr>`).join('');
}

function toggleSubmissionSelected(id, checked) {
  if (checked) selectedSubmissionIds.add(id);
  else selectedSubmissionIds.delete(id);
  updateSubmissionsBulkBar();
}

function toggleSelectAllSubmissions(checked) {
  selectedSubmissionIds.clear();
  if (checked) {
    allSubmissions.filter(s => s.status === 'pending').forEach(s => selectedSubmissionIds.add(s.id));
  }
  document.querySelectorAll('.submission-row-check').forEach(cb => {
    const id = parseInt(cb.dataset.id);
    cb.checked = selectedSubmissionIds.has(id);
  });
  updateSubmissionsBulkBar();
}

function clearSubmissionSelection() {
  selectedSubmissionIds.clear();
  document.querySelectorAll('.submission-row-check').forEach(cb => cb.checked = false);
  const selectAll = document.getElementById('submissions-select-all');
  if (selectAll) selectAll.checked = false;
  updateSubmissionsBulkBar();
}

function updateSubmissionsBulkBar() {
  const bar = document.getElementById('submissions-bulk-bar');
  const countEl = document.getElementById('submissions-selected-count');
  if (!bar) return;
  const count = selectedSubmissionIds.size;
  if (count > 0) {
    bar.style.display = 'flex';
    if (countEl) countEl.textContent = `${count} selected`;
  } else {
    bar.style.display = 'none';
  }
}

async function approveSubmission(id) {
  try {
    await api(`/api/admin/submissions/${id}/approve`, { method: 'POST', body: JSON.stringify({}) });
    toast('Submission approved');
    loadSubmissions();
    loadStats(true);
  } catch(e) {
    toast(e.message, 'error');
  }
}

async function rejectSubmission(id) {
  if (!confirm('Are you sure you want to reject this submission?')) return;
  try {
    await api(`/api/admin/submissions/${id}/reject`, { method: 'POST', body: JSON.stringify({}) });
    toast('Submission rejected');
    loadSubmissions();
    loadStats(true);
  } catch(e) {
    toast(e.message, 'error');
  }
}

async function bulkApproveSubmissions() {
  const ids = Array.from(selectedSubmissionIds);
  if (!ids.length) return;
  if (!confirm(`Approve ${ids.length} selected submission${ids.length !== 1 ? 's' : ''}?`)) return;
  try {
    await api('/api/admin/submissions/bulk-approve', {
      method: 'POST',
      body: JSON.stringify({ submission_ids: ids })
    });
    toast(`Approved ${ids.length} submission${ids.length !== 1 ? 's' : ''}`);
    loadSubmissions();
    loadStats(true);
  } catch(e) {
    toast(e.message, 'error');
  }
}

async function bulkRejectSubmissions() {
  const ids = Array.from(selectedSubmissionIds);
  if (!ids.length) return;
  if (!confirm(`Reject ${ids.length} selected submission${ids.length !== 1 ? 's' : ''}?`)) return;
  try {
    await api('/api/admin/submissions/bulk-reject', {
      method: 'POST',
      body: JSON.stringify({ submission_ids: ids })
    });
    toast(`Rejected ${ids.length} submission${ids.length !== 1 ? 's' : ''}`);
    loadSubmissions();
    loadStats(true);
  } catch(e) {
    toast(e.message, 'error');
  }
}

// ─── URGENT REQUESTS ───
async function loadUrgentRequests() {
  const tbody = document.getElementById('urgent-requests-tbody');
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="7"><div class="loading-overlay"><div class="spinner"></div></div></td></tr>`;
  const status = document.getElementById('urgent-request-status-filter')?.value || 'pending';
  try {
    const qs = status ? `?status=${encodeURIComponent(status)}` : '';
    const data = await api(`/api/admin/urgent-requests${qs}`);
    allUrgentRequests = data.requests || [];
    renderUrgentRequests(allUrgentRequests);
    updateUrgentRequestsBadge(status === 'pending' ? data.count : allUrgentRequests.length);
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state"><div class="empty-state-text">${e.message}</div></div></td></tr>`;
  }
}

function updateUrgentRequestsBadge(count) {
  const badge = document.getElementById('urgent-requests-badge');
  if (!badge) return;
  if (count > 0) {
    badge.style.display = 'inline-flex';
    badge.textContent = count;
  } else {
    badge.style.display = 'none';
  }
}

function renderUrgentRequests(requests) {
  const tbody = document.getElementById('urgent-requests-tbody');
  if (!tbody) return;
  if (!requests.length) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state"><div class="empty-state-icon">⚡</div><div class="empty-state-text">No urgent requests found</div></div></td></tr>`;
    return;
  }
  tbody.innerHTML = requests.map(r => `
    <tr>
      <td>
        <div style="font-weight:500;">${esc(r.first_name)} ${esc(r.last_name)}</div>
        <div style="font-size:0.75rem;color:var(--text-muted);">${esc(r.email)}</div>
      </td>
      <td style="color:var(--text-secondary);font-size:0.82rem;">${esc(r.domain)}</td>
      <td>${esc(r.request_type)}</td>
      <td style="color:var(--text-secondary);font-size:0.82rem;">${esc(r.note || '—')}</td>
      <td style="color:var(--text-muted);font-size:0.8rem;">${fmtDate(r.created_at)}</td>
      <td>${statusBadge(r.status)}</td>
      <td>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          ${r.status === 'pending' ? `
            <button class="btn btn-sm btn-tone-ok" onclick="fulfillUrgentRequest(${r.id})">✅ Fulfill</button>
            <button class="btn btn-sm btn-tone-danger" onclick="rejectUrgentRequest(${r.id})">❌ Reject</button>
          ` : '—'}
        </div>
      </td>
    </tr>`).join('');
}

async function fulfillUrgentRequest(id) {
  if (!confirm('Fulfilling this request unlocks payment for the student even with fewer than 3 approved tasks. Continue?')) return;
  const adminNote = prompt('Optional note for the student:') || '';
  try {
    await api(`/api/admin/urgent-requests/${id}/fulfill`, { method: 'POST', body: JSON.stringify({ admin_note: adminNote }) });
    toast('Request fulfilled — payment unlocked');
    loadUrgentRequests();
    loadStats(true);
  } catch(e) {
    toast(e.message, 'error');
  }
}

async function rejectUrgentRequest(id) {
  if (!confirm('Are you sure you want to reject this urgent request?')) return;
  const adminNote = prompt('Optional note for the student:') || '';
  try {
    await api(`/api/admin/urgent-requests/${id}/reject`, { method: 'POST', body: JSON.stringify({ admin_note: adminNote }) });
    toast('Request rejected');
    loadUrgentRequests();
    loadStats(true);
  } catch(e) {
    toast(e.message, 'error');
  }
}

// ─── ANNOUNCEMENTS ───
const ANNOUNCEMENT_KEY = 'submission-flow-update';
let announcementPreviewCache = [];

async function previewAnnouncement() {
  const el = document.getElementById('announcement-preview');
  const status = document.getElementById('announcement-status-filter').value;
  el.innerHTML = `<div class="loading-overlay"><div class="spinner"></div> Loading recipients...</div>`;
  try {
    const data = await api(`/api/admin/announcements/${ANNOUNCEMENT_KEY}/preview?status=${encodeURIComponent(status)}`);
    announcementPreviewCache = data.students || [];
    if (!announcementPreviewCache.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-state-text">No students with status "${status}" found.</div></div>`;
      return;
    }
    el.innerHTML = `
      <div style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:10px;">
        <strong style="color:var(--text-primary);">${announcementPreviewCache.length}</strong> student(s) will receive this email:
      </div>
      <div class="table-wrap" style="max-height:280px;overflow-y:auto;">
        <table>
          <thead><tr><th>Name</th><th>Email</th><th>Domain</th></tr></thead>
          <tbody>
            ${announcementPreviewCache.map(s => `
              <tr>
                <td>${esc(s.first_name)} ${esc(s.last_name)}</td>
                <td>${esc(s.email)}</td>
                <td>${esc(s.domain || '-')}</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><div class="empty-state-text">${e.message}</div></div>`;
  }
}

function confirmSendAnnouncement() {
  if (!announcementPreviewCache.length) {
    toast('No recipients to send to — refresh the preview first.', 'error');
    return;
  }
  document.getElementById('announcement-confirm-text').textContent =
    `This will send the "Submission Flow Update" email to ${announcementPreviewCache.length} student(s) right now. This cannot be undone. Continue?`;
  openModal('announcement-confirm-modal');
}

async function sendAnnouncementNow() {
  const status = document.getElementById('announcement-status-filter').value;
  try {
    const data = await api(`/api/admin/announcements/${ANNOUNCEMENT_KEY}/send`, {
      method: 'POST',
      body: JSON.stringify({ status })
    });
    closeModal('announcement-confirm-modal');
    if (data.status === 'no_targets') {
      toast('No matching students found.', 'error');
      return;
    }
    toast(`Sending to ${data.sent_to.length} student(s)...`);
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ─── TASK REMINDERS ───
let _cachedInactiveStudents = [];
let _pendingReminderStudentId = null;

async function loadInactiveStudents() {
  const tbody = document.getElementById('reminder-tbody');
  const statsEl = document.getElementById('reminder-stats');
  const sendBtn = document.getElementById('send-reminders-btn');
  if (!tbody) return;

  tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-secondary);padding:30px;"><div class="spinner" style="margin:0 auto;"></div> Loading inactive students...</td></tr>';
  if (statsEl) statsEl.innerHTML = '';
  if (sendBtn) sendBtn.disabled = true;

  try {
    const data = await api('/api/admin/reminders/preview');
    _cachedInactiveStudents = data.students || [];
    const count = _cachedInactiveStudents.length;

    // Stats card
    if (statsEl) {
      statsEl.innerHTML = `<div style="padding:10px 16px;border-radius:8px;background:var(--warn-wash);border:1px solid var(--warn-line);font-size:0.8rem;min-width:140px;">
        <div style="color:var(--text-secondary);font-size:0.72rem;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;">Inactive Students</div>
        <div style="color:var(--warn);font-weight:700;font-size:1.1rem;">${count}</div>
      </div>`;
    }

    if (count === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-secondary);padding:30px;">✨ All students are on track — no reminders needed right now.</td></tr>';
      return;
    }

    tbody.innerHTML = _cachedInactiveStudents.map(s => {
      const lastAct = s.last_activity ? new Date(s.last_activity).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
      return `<tr>
        <td style="font-weight:600;">${esc(s.first_name)} ${esc(s.last_name)}</td>
        <td style="font-size:0.82rem;color:var(--text-secondary);">${esc(s.email)}</td>
        <td>${esc(s.domain || '—')}</td>
        <td><span style="background:var(--warn-wash);color:var(--warn);padding:3px 10px;border-radius:6px;font-size:0.78rem;font-weight:700;">Week ${s.week_due}</span></td>
        <td style="color:var(--danger);font-weight:600;">${s.days_inactive} days</td>
        <td>${s.completed_tasks}/4</td>
        <td style="font-size:0.82rem;color:var(--text-secondary);">${lastAct}</td>
        <td><button class="btn" style="padding:4px 8px;font-size:0.75rem;background:var(--warn-wash);color:var(--warn);border:1px solid var(--warn-line);" onclick="confirmSendReminders(${s.student_id})">Send</button></td>
      </tr>`;
    }).join('');

    if (sendBtn) sendBtn.disabled = false;
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--danger);padding:30px;">Failed to load: ${err.message}</td></tr>`;
  }
}

function confirmSendReminders(studentId = null) {
  _pendingReminderStudentId = studentId;
  const count = _cachedInactiveStudents.length;
  if (count === 0 && !studentId) {
    toast('No inactive students to remind.', 'error');
    return;
  }
  const textEl = document.getElementById('reminder-confirm-text');
  if (textEl) {
    if (studentId) {
       textEl.innerHTML = `You are about to send a task reminder email to this specific student.<br><br>Are you sure you want to proceed?`;
    } else {
       textEl.innerHTML = `You are about to send <strong>${count}</strong> task reminder email${count > 1 ? 's' : ''} to inactive students.<br><br>Students who received a reminder in the last 7 days are already excluded.<br><br>Are you sure you want to proceed?`;
    }
  }
  openModal('reminder-confirm-modal');
}

async function sendRemindersNow() {
  closeModal('reminder-confirm-modal');
  const resultEl = document.getElementById('reminder-send-result');
  const sendBtn = document.getElementById('send-reminders-btn');
  if (sendBtn) sendBtn.disabled = true;
  if (resultEl) resultEl.textContent = '⏳ Sending reminders in background...';

  const payload = _pendingReminderStudentId ? { student_ids: [_pendingReminderStudentId] } : {};
  _pendingReminderStudentId = null;

  try {
    const data = await api('/api/admin/reminders/send', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    toast(`${data.count} reminder(s) dispatched in background.`, 'success');
    if (resultEl) resultEl.textContent = `✅ ${data.count} reminder(s) dispatched at ${new Date().toLocaleTimeString('en-IN')}.`;
    // Refresh the list after a brief delay (emails take ~1s each)
    setTimeout(() => loadInactiveStudents(), 3000);
  } catch (err) {
    toast(`Failed: ${err.message}`, 'error');
    if (resultEl) resultEl.textContent = `❌ Failed: ${err.message}`;
    if (sendBtn) sendBtn.disabled = false;
  }
}

// ─── ANALYTICS ───
// Chart.js instances, kept keyed by canvas id so a refresh destroys the old
// chart before drawing a new one instead of leaking canvases/listeners.
const _analyticsCharts = {};

const CHART_JS_SRC = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js';
const CHART_JS_SRI = 'sha384-e6nUZLBkQ86NJ6TVVKAeSaK8jWa3NhkYWZFomE39AvDbQWeie9PlQqM3pmYW5d1g';
let _chartJsPromise = null;
// Chart.js is ~200 KB and only the Analytics page needs it — load it on first visit.
function ensureChartJs() {
  if (typeof Chart !== 'undefined') return Promise.resolve();
  if (!_chartJsPromise) {
    _chartJsPromise = new Promise((resolve, reject) => {
      const el = document.createElement('script');
      el.src = CHART_JS_SRC;
      el.integrity = CHART_JS_SRI;
      el.crossOrigin = 'anonymous';
      el.onload = resolve;
      el.onerror = () => { _chartJsPromise = null; reject(new Error('Could not load the chart library')); };
      document.head.appendChild(el);
    });
  }
  return _chartJsPromise;
}

function _drawChart(canvasId, config) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || typeof Chart === 'undefined') return;
  if (_analyticsCharts[canvasId]) _analyticsCharts[canvasId].destroy();
  _analyticsCharts[canvasId] = new Chart(canvas.getContext('2d'), config);
}

const chartBase = () => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { labels: { color: cssColor('--text-2'), boxWidth: 12, font: { size: 11 } } } },
  scales: {
    x: { ticks: { color: cssColor('--text-3'), font: { size: 10 } }, grid: { color: cssColor('--line') } },
    y: { ticks: { color: cssColor('--text-3'), font: { size: 10 }, precision: 0 }, grid: { color: cssColor('--line') }, beginAtZero: true },
  },
});

const fmtINR = n => `₹${Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

function _monthLabel(ym) {
  const [y, m] = String(ym).split('-');
  return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' });
}

let _analyticsReq = 0;
async function loadAnalytics(fresh = false) {
  const grid = document.getElementById('analytics-funnel-grid');
  if (!grid) return;
  const reqId = ++_analyticsReq;
  try {
    const [data] = await Promise.all([
      api(`/api/admin/analytics${fresh === true ? '?fresh=true' : ''}`),
      ensureChartJs(),
    ]);
    if (reqId !== _analyticsReq) return;
    renderAnalyticsFunnel(data.funnel || {});
    renderWeeklyCompletionChart(data.weekly_completion || []);
    renderRevenue(data.revenue || {});
    renderDomainBreakdownChart(data.domains || []);
    renderApplicationsTrendChart(data.applications_trend || []);
    renderDomainTable(data.domains || []);
    renderGrowth(data.growth || {}, data.revenue || {});
    renderAcquisition(data.acquisition || {});
    renderAudience(data.audience || {});
    renderSpeed(data.speed || {}, data.revenue || {});
    renderQuizOutcomes(data.quiz_outcomes || []);
  } catch (e) {
    if (reqId !== _analyticsReq) return;
    grid.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><div class="empty-state-text">${esc(e.message)}</div></div>`;
  }
}

function analyticsCard(icon, value, label, sub) {
  return `
    <div class="stat-card">
      <div class="stat-card-top">
        <div class="stat-card-label">${label}</div>
        <div class="stat-card-icon">${icon}</div>
      </div>
      <div class="stat-card-value">${typeof value === 'number' ? value.toLocaleString('en-IN') : value}</div>
      ${sub ? `<div class="stat-card-sub">${sub}</div>` : ''}
    </div>`;
}

function renderAnalyticsFunnel(f) {
  const grid = document.getElementById('analytics-funnel-grid');
  if (!grid) return;
  grid.innerHTML = `
    ${analyticsCard('👥', f.total || 0, 'Total Applicants', `${(f.never_started || 0).toLocaleString('en-IN')} haven't started yet`)}
    ${analyticsCard('🚀', f.started || 0, 'Started Tasks', `${f.start_rate || 0}% of applicants`)}
    ${analyticsCard('🏁', f.completed || 0, 'Completed 4/4 Weeks', `${f.completion_rate || 0}% of those who started`)}
    ${analyticsCard('🎓', f.certified || 0, 'Certificates Issued', 'includes early unlocks')}
    ${analyticsCard('💳', f.paid || 0, 'Paying Students', `${f.paid_rate || 0}% of applicants`)}
  `;
}

function renderWeeklyCompletionChart(weekly) {
  _drawChart('chart-weekly-completion', {
    type: 'bar',
    data: {
      labels: weekly.map(w => `Week ${w.week}`),
      datasets: [
        { label: 'Approved', data: weekly.map(w => w.approved), backgroundColor: cssColor('--ok'), borderRadius: 4 },
        { label: 'Pending review', data: weekly.map(w => w.pending), backgroundColor: cssColor('--warn'), borderRadius: 4 },
        { label: 'Rejected', data: weekly.map(w => w.rejected), backgroundColor: cssColor('--danger'), borderRadius: 4 },
      ],
    },
    options: {
      ...chartBase(),
      scales: {
        x: { ...chartBase().scales.x, stacked: true },
        y: { ...chartBase().scales.y, stacked: true },
      },
    },
  });
}

function renderRevenue(r) {
  const subtitle = document.getElementById('analytics-revenue-subtitle');
  if (subtitle) {
    subtitle.textContent = `${fmtINR(r.total_revenue_rupees)} from ${r.paid_orders || 0} verified payment${r.paid_orders === 1 ? '' : 's'} · avg ${fmtINR(r.avg_order_rupees)}`;
  }

  const TIER_META = {
    full:       { label: 'Full price',    color: 'var(--ok)' },
    discounted: { label: 'Discount code', color: 'var(--info)' },
    legacy:     { label: 'Older price',   color: 'var(--violet)' },
  };
  const tiersEl = document.getElementById('analytics-revenue-tiers');
  if (tiersEl) {
    const tiers = r.tiers || [];
    tiersEl.innerHTML = tiers.length ? tiers.map(t => {
      const m = TIER_META[t.kind] || TIER_META.legacy;
      return `
        <div style="padding:10px 14px;border-radius:8px;background:${tint(m.color,10)};border:1px solid ${tint(m.color,30)};font-size:0.8rem;min-width:150px;">
          <div style="color:var(--text-secondary);font-size:0.68rem;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;">${m.label} · ${fmtINR(t.price_rupees)}</div>
          <div style="color:${m.color};font-weight:700;font-size:1.05rem;">${fmtINR(t.revenue_rupees)}</div>
          <div style="color:var(--text-muted);font-size:0.72rem;">${t.orders} order${t.orders === 1 ? '' : 's'}</div>
        </div>`;
    }).join('') : `<div style="font-size:0.8rem;color:var(--text-secondary);">No verified payments yet.</div>`;
  }

  const noteEl = document.getElementById('analytics-revenue-note');
  if (noteEl) {
    const parts = [];
    if (r.abandoned_checkouts) parts.push(`${r.abandoned_checkouts} student${r.abandoned_checkouts === 1 ? '' : 's'} opened checkout but never paid.`);
    if (r.excluded_test_orders) parts.push(`${r.excluded_test_orders} test payment record${r.excluded_test_orders === 1 ? '' : 's'} (${fmtINR(r.excluded_test_rupees)}) excluded.`);
    noteEl.textContent = parts.join(' ');
  }

  const trend = r.trend || [];
  _drawChart('chart-revenue-trend', {
    type: 'bar',
    data: {
      labels: trend.map(t => _monthLabel(t.month)),
      datasets: [{ label: 'Revenue (₹)', data: trend.map(t => t.revenue_rupees), backgroundColor: cssColor('--ok'), borderRadius: 4 }],
    },
    options: {
      ...chartBase(),
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => `${fmtINR(ctx.parsed.y)} · ${trend[ctx.dataIndex].orders} orders` } },
      },
    },
  });
}

function renderDomainBreakdownChart(domains) {
  _drawChart('chart-domain-breakdown', {
    type: 'bar',
    data: {
      labels: domains.map(d => d.label),
      datasets: [
        { label: 'Applicants', data: domains.map(d => d.total), backgroundColor: cssColor('--accent', 0.55), borderRadius: 4 },
        { label: 'Started', data: domains.map(d => d.started), backgroundColor: cssColor('--info'), borderRadius: 4 },
        { label: 'Completed', data: domains.map(d => d.completed), backgroundColor: cssColor('--ok'), borderRadius: 4 },
        { label: 'Paid', data: domains.map(d => d.paid), backgroundColor: cssColor('--violet'), borderRadius: 4 },
      ],
    },
    options: { ...chartBase(), indexAxis: 'y' },
  });
}

function renderApplicationsTrendChart(trend) {
  _drawChart('chart-applications-trend', {
    type: 'line',
    data: {
      labels: trend.map(t => _monthLabel(t.month)),
      datasets: [{
        label: 'Applications',
        data: trend.map(t => t.count),
        borderColor: cssColor('--accent'),
        backgroundColor: cssColor('--accent', 0.15),
        fill: true,
        tension: 0.35,
      }],
    },
    options: { ...chartBase(), plugins: { legend: { display: false } } },
  });
}

function renderDomainTable(domains) {
  const tbody = document.getElementById('analytics-domain-tbody');
  if (!tbody) return;
  if (!domains.length) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--text-secondary);padding:32px;">No students yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = domains.map(d => {
    const rate = d.completion_rate || 0;
    const rateCell = d.started
      ? `<div style="display:flex;align-items:center;gap:8px;">
           <div style="flex:1;height:6px;border-radius:3px;background:var(--surface-2);overflow:hidden;">
             <div style="width:${Math.min(rate, 100)}%;height:100%;background:var(--ok);"></div>
           </div>
           <span style="font-size:0.78rem;color:var(--text-secondary);min-width:40px;">${rate}%</span>
         </div>`
      : `<span style="font-size:0.78rem;color:var(--text-muted);">No one started</span>`;
    return `
    <tr>
      <td><div style="font-weight:600;">${esc(d.label)}</div><div style="font-size:0.7rem;color:var(--text-muted);">${esc(d.domain)}</div></td>
      <td>${d.total}</td>
      <td style="color:var(--info);">${d.started}</td>
      <td style="color:var(--ok);">${d.completed}</td>
      <td>${d.certified}</td>
      <td style="color:var(--violet);">${d.paid}</td>
      <td>${fmtINR(d.revenue_rupees)}</td>
      <td>${rateCell}</td>
    </tr>`;
  }).join('');
}

function renderGrowth(g, rev) {
  const grid = document.getElementById('analytics-growth-grid');
  if (grid) {
    grid.innerHTML = `
      ${analyticsCard('🧑', g.unique_people || 0, 'Unique People', `${(g.total_applications || 0).toLocaleString('en-IN')} applications in total`)}
      ${analyticsCard('🔀', `${g.multi_track_rate || 0}%`, 'Apply to Multiple Tracks', 'extra applications per person')}
      ${analyticsCard('📆', g.wau || 0, 'Weekly Active People', 'login or task submission, last 7 days')}
      ${analyticsCard('🗓️', g.mau || 0, 'Monthly Active People', 'last 30 days')}
      ${analyticsCard('💵', fmtINR(rev.per_applicant_rupees), 'Revenue per Applicant', 'verified revenue ÷ all applicants')}
    `;
  }
  const daily = g.daily_applications || [];
  _drawChart('chart-daily-apps', {
    type: 'bar',
    data: {
      labels: daily.map(d => new Date(d.day + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })),
      datasets: [{ label: 'Applications', data: daily.map(d => d.count), backgroundColor: cssColor('--accent'), borderRadius: 3 }],
    },
    options: { ...chartBase(), plugins: { legend: { display: false } } },
  });
}

// One row per group: name | applicants | started (rate) | paid [| paid %]
function _funnelRows(rows, emptyText, withPaidRate) {
  const cols = withPaidRate ? 5 : 4;
  if (!rows.length) {
    return `<tr><td colspan="${cols}" style="text-align:center;color:var(--text-secondary);padding:24px;">${emptyText}</td></tr>`;
  }
  return rows.map(r => `
    <tr>
      <td style="font-weight:500;">${esc(r.label)}</td>
      <td>${r.total}</td>
      <td style="color:var(--info);">${r.started} <span style="color:var(--text-muted);font-size:0.72rem;">(${r.started_rate}%)</span></td>
      <td style="color:var(--violet);">${r.paid}</td>
      ${withPaidRate ? `<td>${r.paid_rate}%</td>` : ''}
    </tr>`).join('');
}

function renderAcquisition(a) {
  const sources = a.sources || [];
  const tbody = document.getElementById('analytics-sources-tbody');
  if (tbody) {
    tbody.innerHTML = _funnelRows(sources, 'No applicants yet.', true);
    if (sources.length && sources.every(s => s.label === 'Unknown')) {
      tbody.insertAdjacentHTML('beforeend', `<tr><td colspan="5" style="color:var(--text-muted);font-size:0.72rem;padding:8px 12px;">Every applicant is "Unknown" — no source has been recorded yet.</td></tr>`);
    }
  }
  const ref = a.referrals || {};
  const sub = document.getElementById('analytics-referral-subtitle');
  if (sub) {
    sub.textContent = ref.clicked
      ? `Referral program: ${ref.clicked} clicked → ${ref.applied} applied → ${ref.enrolled} enrolled`
      : 'Which channels bring people who start and pay · no referral activity yet';
  }
}

function renderAudience(a) {
  const tbody = document.getElementById('analytics-colleges-tbody');
  if (tbody) tbody.innerHTML = _funnelRows(a.colleges || [], 'Not captured yet — no applicant has a college recorded.', false);
  const years = a.years || [];
  _drawChart('chart-years', {
    type: 'bar',
    data: {
      labels: years.map(y => y.label),
      datasets: [
        { label: 'Applicants', data: years.map(y => y.total), backgroundColor: cssColor('--accent', 0.55), borderRadius: 4 },
        { label: 'Started', data: years.map(y => y.started), backgroundColor: cssColor('--info'), borderRadius: 4 },
        { label: 'Paid', data: years.map(y => y.paid), backgroundColor: cssColor('--violet'), borderRadius: 4 },
      ],
    },
    options: chartBase(),
  });
}

function renderSpeed(sp, rev) {
  const el = document.getElementById('analytics-speed-grid');
  if (!el) return;
  const chip = (label, value, note, color) => `
    <div style="padding:10px 14px;border-radius:8px;background:${tint(color,10)};border:1px solid ${tint(color,30)};font-size:0.8rem;min-width:170px;flex:1;">
      <div style="color:var(--text-secondary);font-size:0.68rem;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;">${label}</div>
      <div style="color:${color};font-weight:700;font-size:1.05rem;">${value}</div>
      <div style="color:var(--text-muted);font-size:0.72rem;">${note}</div>
    </div>`;
  const none = v => v === null || v === undefined;
  const days = v => none(v) ? '—' : `${v} day${v === 1 ? '' : 's'}`;
  el.innerHTML = [
    chip('Apply → first task', days(sp.median_days_to_first_task), 'median', 'var(--info)'),
    chip('Apply → payment', days(sp.median_days_to_payment), 'median', 'var(--violet)'),
    chip('Review turnaround', none(sp.avg_review_hours) ? '—' : `${sp.avg_review_hours} h`, 'average, submission to decision', 'var(--ok)'),
    chip('Review backlog', `${sp.pending_reviews || 0} pending`, none(sp.oldest_pending_days) ? 'nothing waiting' : `oldest waiting ${days(sp.oldest_pending_days)}`, 'var(--warn)'),
    chip('Eligible but unpaid', `${rev.eligible_unpaid || 0} students`, 'finished 3+ weeks, not paid yet', 'var(--danger)'),
  ].join('');
}

function renderQuizOutcomes(rows) {
  const tbody = document.getElementById('analytics-quiz-tbody');
  if (!tbody) return;
  if (!rows.some(r => r.total)) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;color:var(--text-secondary);padding:24px;">Not captured yet — no applicant has a quiz score.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td style="font-weight:500;">${esc(r.band)}</td>
      <td>${r.total}</td>
      <td style="color:var(--ok);">${r.completion_rate}%</td>
      <td style="color:var(--violet);">${r.paid_rate}%</td>
    </tr>`).join('');
}

// ─── INIT ───
const savedKey = sessionStorage.getItem('skillme_admin_key');
if (savedKey) {
  const input = document.getElementById('admin-key-input') || document.getElementById('api-key-input');
  if (input) input.value = savedKey;
  adminKey = savedKey;
  showApp();
}
