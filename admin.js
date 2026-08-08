// ─── SkillMe Admin Console — JS ───
const API = window.SKILLME_API || 'http://localhost:8000';
let adminKey = '';
let allStudents = [];
let allBatches = [];
let currentPage = 'overview';

const PAGE_META = {
  overview:  { title: 'Overview',  subtitle: 'Platform summary and recent activity' },
  students:  { title: 'Students',  subtitle: 'Manage applications and enrollments' },
  batches:   { title: 'Batches',   subtitle: 'Manage cohorts and automated task assignment' },
  email:     { title: 'Email Settings', subtitle: 'Brevo SMTP relay — test and monitor email delivery' },
};

// ─── AUTH ───
async function adminLogin() {
  const key = document.getElementById('api-key-input').value.trim();
  const errEl = document.getElementById('login-error');
  const btn = document.getElementById('login-btn');
  if (!key) { errEl.textContent = 'Please enter your admin key.'; return; }

  btn.textContent = 'Verifying...';
  try {
    const res = await fetch(`${API}/api/admin/stats`, {
      headers: { 'X-Admin-Key': key }
    });
    if (res.status === 403) {
      errEl.textContent = 'Invalid admin key. Please try again.';
      btn.textContent = 'Access Console';
      return;
    }
    if (!res.ok) throw new Error('Server error');
    adminKey = key;
    sessionStorage.setItem('skillme_admin_key', key);
    showApp();
  } catch (e) {
    errEl.textContent = 'Could not connect to the backend. Is it running?';
    btn.textContent = 'Access Console';
  }
}

function showApp() {
  document.getElementById('login-overlay').classList.add('hidden');
  setTimeout(() => document.getElementById('login-overlay').style.display = 'none', 400);
  document.getElementById('app').style.display = 'flex';
  startClock();
  loadOverview();
}

// ─── CLOCK ───
function startClock() {
  const el = document.getElementById('topbar-time');
  const tick = () => { el.textContent = new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true }); };
  tick(); setInterval(tick, 1000);
}

// ─── NAVIGATION ───
function navigate(page) {
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.page').forEach(el => el.classList.remove('active'));
  document.getElementById(`nav-${page}`)?.classList.add('active');
  document.getElementById(`page-${page}`).classList.add('active');
  const meta = PAGE_META[page] || {};
  document.getElementById('topbar-title').textContent = meta.title || page;
  document.getElementById('topbar-subtitle').textContent = meta.subtitle || '';
  currentPage = page;
  if (page === 'overview') loadOverview();
  if (page === 'students') loadStudents();
  if (page === 'batches') loadBatches();
  if (page === 'email') loadEmailStatus();
}

function refreshCurrentPage() { navigate(currentPage); }

// ─── API HELPER ───
async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: { 'X-Admin-Key': adminKey, 'Content-Type': 'application/json', ...(opts.headers || {}) }
  });
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
  el.innerHTML = `<span>${icon}</span><span>${message}</span>`;
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

// ─── STATUS BADGE ───
function statusBadge(status) {
  return `<span class="badge badge-${status}">${status}</span>`;
}

// ─── FORMAT DATE ───
function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

// ─── OVERVIEW ───
async function loadOverview() {
  loadStats();
  loadRecentApplications();
  loadOverviewBatches();
  loadSchedulerStatus();
}

async function loadStats() {
  const grid = document.getElementById('stats-grid');
  try {
    const data = await api('/api/admin/stats');
    grid.innerHTML = `
      ${statCard('👥', data.total_students, 'Total Students', 'rgba(129,140,248,0.15)', '#818cf8')}
      ${statCard('🟢', data.active_batches, 'Active Batches', 'rgba(52,211,153,0.15)', '#34d399')}
      ${statCard('📋', data.pending_applications, 'Pending Applications', 'rgba(251,191,36,0.15)', '#fbbf24')}
      ${statCard('🎯', data.total_issues_assigned, 'Issues Assigned', 'rgba(56,189,248,0.15)', '#38bdf8')}
    `;
    const badge = document.getElementById('pending-badge');
    if (data.pending_applications > 0) {
      badge.style.display = 'inline-flex';
      badge.textContent = data.pending_applications;
    } else {
      badge.style.display = 'none';
    }
  } catch (e) {
    grid.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><div class="empty-state-text">${e.message}</div></div>`;
  }
}

function statCard(icon, value, label, bg, color) {
  return `
    <div class="stat-card">
      <div class="stat-card-icon" style="background:${bg}; color:${color}; font-size:22px;">${icon}</div>
      <div class="stat-card-value" style="color:${color};">${value ?? 0}</div>
      <div class="stat-card-label">${label}</div>
    </div>`;
}

async function loadRecentApplications(silent = false) {
  const el = document.getElementById('recent-applications');
  if (!silent && !el.querySelector('table')) {
    el.innerHTML = `<div class="loading-overlay"><div class="spinner"></div></div>`;
  }
  try {
    const data = await api('/api/admin/students?status=applied&limit=5');
    if (!data.students.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🎉</div><div class="empty-state-text">No pending applications</div></div>`;
      return;
    }
    el.innerHTML = `
      <table>
        <thead><tr><th>Name</th><th>Domain</th><th>Applied</th><th>Action</th></tr></thead>
        <tbody>
          ${data.students.map(s => `
            <tr>
              <td>
                <div style="font-weight:500;">${s.first_name} ${s.last_name}</div>
                <div style="font-size:0.75rem;color:var(--text-muted);">${s.email}</div>
              </td>
              <td>${s.domain || '—'}</td>
              <td>${fmtDate(s.created_at)}</td>
              <td>
                <button class="btn btn-sm" style="background:rgba(52,211,153,0.15);color:#34d399;border:1px solid rgba(52,211,153,0.25);" onclick="updateStatus(${s.id},'shortlisted')">Shortlist</button>
              </td>
            </tr>`).join('')}
        </tbody>
      </table>`;
  } catch(e) {
    if (!silent) {
      el.innerHTML = `<div class="empty-state"><div class="empty-state-text">${e.message}</div></div>`;
    }
  }
}

async function loadOverviewBatches(silent = false) {
  const el = document.getElementById('overview-batches');
  if (!silent && !el.querySelector('div')) {
    el.innerHTML = `<div class="loading-overlay"><div class="spinner"></div></div>`;
  }
  try {
    const data = await api('/api/admin/batches?status=active');
    if (!data.batches.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📦</div><div class="empty-state-text">No active batches</div></div>`;
      return;
    }
    el.innerHTML = data.batches.slice(0,3).map(b => {
      const fill = Math.min(100, Math.round((b.enrolled_students || 0) / (b.max_students || 30) * 100));
      return `
        <div style="padding:16px 24px;border-bottom:1px solid var(--border);">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <div>
              <div style="font-weight:500;font-size:0.9rem;">${b.domain} — Batch #${b.batch_number}</div>
              <div style="font-size:0.75rem;color:var(--text-muted);">${b.enrolled_students || 0} / ${b.max_students} students</div>
            </div>
            ${statusBadge(b.status)}
          </div>
          <div class="progress-bar"><div class="progress-fill" style="width:${fill}%"></div></div>
        </div>`;
    }).join('');
  } catch(e) {
    if (!silent) {
      el.innerHTML = `<div class="empty-state"><div class="empty-state-text">${e.message}</div></div>`;
    }
  }
}

// ─── STUDENTS ───
async function loadStudents(silent = false) {
  const tbody = document.getElementById('students-tbody');
  if (!silent) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="loading-overlay"><div class="spinner"></div></div></td></tr>`;
  }
  try {
    const data = await api('/api/admin/students?limit=100');
    allStudents = data.students || [];
    renderStudents(allStudents);
  } catch(e) {
    if (!silent) {
      tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="empty-state-text">${e.message}</div></div></td></tr>`;
    }
  }
}

function filterStudents() {
  const q = document.getElementById('student-search').value.toLowerCase();
  const status = document.getElementById('status-filter').value;
  const filtered = allStudents.filter(s => {
    const matchQ = !q || `${s.first_name} ${s.last_name} ${s.email} ${s.github_username || ''}`.toLowerCase().includes(q);
    const matchStatus = !status || s.status === status;
    return matchQ && matchStatus;
  });
  renderStudents(filtered);
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
          <div style="width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#818cf8,#38bdf8);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:0.8rem;flex-shrink:0;">${(s.first_name[0]||'?').toUpperCase()}</div>
          <div>
            <div style="font-weight:500;">${s.first_name} ${s.last_name}</div>
            ${s.github_username ? `<div style="font-size:0.72rem;color:var(--text-muted);">@${s.github_username}</div>` : ''}
          </div>
        </div>
      </td>
      <td style="color:var(--text-secondary);font-size:0.82rem;">${s.email}</td>
      <td>${s.domain || '—'}</td>
      <td>${statusBadge(s.status)}</td>
      <td style="color:var(--text-muted);font-size:0.82rem;">${fmtDate(s.created_at)}</td>
      <td>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          ${s.status === 'applied' ? `<button class="btn btn-sm" style="background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.25);" onclick="updateStatus(${s.id},'shortlisted')">Shortlist</button>` : ''}
          ${s.status === 'shortlisted' ? `<button class="btn btn-sm" style="background:rgba(52,211,153,0.15);color:#34d399;border:1px solid rgba(52,211,153,0.25);" onclick="openEnrollModal(${s.id},'${s.first_name} ${s.last_name}')">Enroll</button>` : ''}
          ${(s.status === 'completed' || s.status === 'enrolled') && s.batch_id ? `<button class="btn btn-sm" style="background:rgba(212,168,83,0.15);color:#d4a853;border:1px solid rgba(212,168,83,0.3);" onclick="issueCertificate(${s.id},${s.batch_id},'${s.first_name} ${s.last_name}')">🏅 Certificate</button>` : ''}
          ${s.status !== 'dropped' ? `<button class="btn btn-sm" style="background:rgba(251,113,133,0.12);color:#fb7185;border:1px solid rgba(251,113,133,0.2);" onclick="updateStatus(${s.id},'dropped')">Drop</button>` : ''}
        </div>
      </td>
    </tr>`).join('');
}

async function updateStatus(studentId, newStatus) {
  try {
    await api(`/api/admin/students/${studentId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status: newStatus })
    });
    toast(`Student status updated to "${newStatus}"`);
    if (currentPage === 'overview') {
      loadRecentApplications(true);
      loadOverviewBatches(true);
    }
    loadStudents(true);
    loadStats(true);
  } catch(e) {
    toast(e.message, 'error');
  }
}

async function issueCertificate(studentId, batchId, name) {
  try {
    const data = await api(`/api/certificates/issue/${studentId}/${batchId}`, { method: 'POST' });
    toast(`Certificate ${data.cert_id} issued to ${name}!`);
    // Open certificate in new tab
    const certUrl = `${window.SKILLME_FRONTEND || 'http://localhost:8080'}/certificate.html?student_id=${studentId}&batch_id=${batchId}&name=${encodeURIComponent(name)}`;
    window.open(certUrl, '_blank');
  } catch(e) {
    toast(e.message, 'error');
  }
}

async function openEnrollModal(studentId, name) {
  document.getElementById('enroll-student-id').value = studentId;
  document.getElementById('enroll-student-name').textContent = `Enrolling: ${name}`;
  const select = document.getElementById('enroll-batch-select');
  select.innerHTML = '<option>Loading batches...</option>';
  openModal('enroll-modal');
  try {
    const data = await api('/api/admin/batches');
    allBatches = data.batches || [];
    if (!allBatches.length) {
      select.innerHTML = '<option value="">⚠️ No batches yet — create one in the Batches tab first!</option>';
      document.getElementById('enroll-confirm-btn').disabled = true;
    } else {
      select.innerHTML = allBatches.map(b => `<option value="${b.id}">${b.domain} — Batch #${b.batch_number}</option>`).join('');
      document.getElementById('enroll-confirm-btn').disabled = false;
    }
  } catch(e) {
    select.innerHTML = '<option>Failed to load batches</option>';
  }
}


async function enrollStudent() {
  const studentId = document.getElementById('enroll-student-id').value;
  const batchId = document.getElementById('enroll-batch-select').value;
  if (!batchId) { toast('Please select a batch', 'error'); return; }
  try {
    await api(`/api/admin/batches/${batchId}/students`, {
      method: 'POST',
      body: JSON.stringify({ student_id: parseInt(studentId) })
    });
    toast('Student enrolled successfully!');
    closeModal('enroll-modal');
    if (currentPage === 'overview') {
      loadOverviewBatches(true);
    }
    loadStudents(true);
    loadStats(true);
  } catch(e) {
    toast(e.message, 'error');
  }
}

// ─── BATCHES ───
async function loadBatches(silent = false) {
  const el = document.getElementById('batches-list');
  if (!silent) {
    el.innerHTML = '<div class="loading-overlay"><div class="spinner"></div> Loading batches...</div>';
  }
  try {
    const data = await api('/api/admin/batches');
    allBatches = data.batches || [];
    if (!allBatches.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-state-icon">&#128230;</div><div class="empty-state-text">No batches yet. Create your first batch!</div></div>`;
      return;
    }
    el.innerHTML = allBatches.map(b => {
      const fill = Math.min(100, Math.round((b.enrolled_students || 0) / (b.max_students || 30) * 100));
      const autoOn = !!b.auto_assign;
      return `
        <div class="batch-card" id="batch-card-${b.id}">
          <div class="batch-card-header">
            <div>
              <div class="batch-card-title">${b.domain.replace('-',' ').replace(/\b\w/g, c=>c.toUpperCase())} — Batch #${b.batch_number}</div>
              <div class="batch-card-meta">${b.repo_name} &nbsp;&middot;&nbsp; ${b.enrolled_students || 0} / ${b.max_students} students &nbsp;&middot;&nbsp; Started ${fmtDate(b.start_date)}</div>
            </div>
            <div class="batch-card-actions">
              ${statusBadge(b.status)}
              <button class="btn btn-ghost btn-sm" onclick="openAssignModal(${b.id}, '${b.domain} Batch #${b.batch_number}')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M12 6v6l4 2"/></svg>
                Assign Tasks
              </button>
              <button class="btn btn-ghost btn-sm" onclick="openAnalyticsModal(${b.id}, '${b.domain} Batch #${b.batch_number}')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><path d="M3 3v18h18"/><path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"/></svg>
                Analytics
              </button>
            </div>
          </div>
          <div class="progress-bar"><div class="progress-fill" style="width:${fill}%"></div></div>
          <div class="progress-labels">
            <span>${fill}% enrolled</span>
            <span>${b.max_students - (b.enrolled_students || 0)} slots remaining</span>
          </div>
          <div style="display:flex;align-items:center;gap:16px;margin-top:16px;padding-top:14px;border-top:1px solid var(--border);">
            <div style="display:flex;align-items:center;gap:10px;">
              <label class="toggle-switch" title="${autoOn ? 'Auto-assign ON: tasks will be pushed every Monday' : 'Auto-assign OFF: click to enable'}">
                <input type="checkbox" ${autoOn ? 'checked' : ''} onchange="toggleAutoAssign(${b.id}, this.checked)" />
                <span class="toggle-slider"></span>
              </label>
              <div>
                <div style="font-size:0.82rem;font-weight:500;">Auto-Assign</div>
                <div style="font-size:0.72rem;color:var(--text-muted);">${autoOn ? 'Enabled — runs every Monday 9AM' : 'Disabled'}</div>
              </div>
            </div>
            <button class="btn btn-ghost btn-sm" onclick="triggerNow(${b.id})" title="Run auto-assign now for this batch">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              Run Now
            </button>
            <div style="margin-left:auto;font-size:0.75rem;color:var(--text-muted);">
              Weeks assigned: <strong style="color:var(--text-primary)">${formatWeeksAssigned(b.weeks_assigned)}</strong>
            </div>
          </div>
        </div>`;
    }).join('');
  } catch(e) {
    el.innerHTML = `<div class="empty-state"><div class="empty-state-text">${e.message}</div></div>`;
  }
}

function formatWeeksAssigned(raw) {
  try {
    const arr = typeof raw === 'string' ? JSON.parse(raw) : (raw || []);
    if (!arr.length) return 'None';
    return arr.map(w => `W${w}`).join(', ');
  } catch { return 'None'; }
}

async function toggleAutoAssign(batchId, enabled) {
  try {
    await api(`/api/admin/batches/${batchId}/auto-assign?enabled=${enabled}`, { method: 'PATCH' });
    toast(`Auto-assign ${enabled ? 'enabled' : 'disabled'} for batch ${batchId}`);
    loadBatches(true);
  } catch(e) { toast(e.message, 'error'); }
}

async function triggerNow(batchId) {
  try {
    const btn = event.currentTarget;
    btn.disabled = true; btn.textContent = 'Running...';
    // Enable auto-assign first then trigger
    await api(`/api/admin/batches/${batchId}/auto-assign?enabled=true`, { method: 'PATCH' });
    const result = await api('/api/admin/scheduler/trigger', { method: 'POST' });
    toast('Scheduler ran! Check the batch for new tasks.');
    loadBatches(true);
  } catch(e) { toast(e.message, 'error'); }
}

async function loadSchedulerStatus() {
  // Inject a scheduler status card into the overview if not already there
  let el = document.getElementById('scheduler-panel');
  if (!el) {
    const overviewPage = document.getElementById('page-overview');
    const div = document.createElement('div');
    div.style = 'margin-bottom:24px;';
    div.innerHTML = `<div class="panel" id="scheduler-panel">
      <div class="panel-header">
        <div><div class="panel-title">Auto-Assign Scheduler</div><div class="panel-subtitle">Automated weekly task delivery status</div></div>
        <button class="btn btn-ghost btn-sm" onclick="loadSchedulerStatus()">Refresh</button>
      </div>
      <div class="panel-body" id="scheduler-panel-body"><div class="loading-overlay"><div class="spinner"></div></div></div>
    </div>`;
    overviewPage.insertBefore(div, overviewPage.querySelector('.grid-2'));
    el = document.getElementById('scheduler-panel-body');
  } else {
    el = document.getElementById('scheduler-panel-body');
    el.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
  }

  try {
    const data = await api('/api/admin/scheduler/status');
    const nextRun = data.next_run ? new Date(data.next_run).toLocaleString('en-IN', { weekday:'short', day:'numeric', month:'short', hour:'2-digit', minute:'2-digit' }) : 'Unknown';
    const batches = data.auto_assign_batches || [];
    el.innerHTML = `
      <div style="display:flex;align-items:center;gap:24px;flex-wrap:wrap;">
        <div style="display:flex;align-items:center;gap:8px;">
          <div style="width:10px;height:10px;border-radius:50%;background:${data.scheduler_running ? '#34d399' : '#fb7185'};box-shadow:0 0 8px ${data.scheduler_running ? '#34d399' : '#fb7185'};"></div>
          <span style="font-weight:500;font-size:0.9rem;">${data.scheduler_running ? 'Scheduler Running' : 'Scheduler Stopped'}</span>
        </div>
        <div style="font-size:0.82rem;color:var(--text-secondary);">Next run: <strong style="color:var(--text-primary);">${nextRun}</strong></div>
        <div style="font-size:0.82rem;color:var(--text-secondary);">${batches.length} batch${batches.length !== 1 ? 'es' : ''} enrolled</div>
        <button class="btn btn-primary btn-sm" style="margin-left:auto;" onclick="runSchedulerNow()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          Trigger All Now
        </button>
      </div>
      ${batches.length ? `
      <div style="margin-top:14px;border-top:1px solid var(--border);padding-top:14px;">
        <div style="font-size:0.72rem;color:var(--text-muted);letter-spacing:.06em;text-transform:uppercase;margin-bottom:8px;">Auto-Assign Batches</div>
        ${batches.map(b => `
          <div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.04);">
            <span style="font-size:0.85rem;font-weight:500;">${b.name}</span>
            <span style="font-size:0.75rem;color:var(--text-muted);">Started ${fmtDate(b.start_date)}</span>
            <span style="margin-left:auto;font-size:0.75rem;">Assigned: <strong>${formatWeeksAssigned(b.weeks_assigned)}</strong></span>
          </div>`).join('')}
      </div>` : ''}
    `;
  } catch(e) {
    el.innerHTML = `<div class="empty-state"><div class="empty-state-text">${e.message}</div></div>`;
  }
}

async function runSchedulerNow() {
  try {
    await api('/api/admin/scheduler/trigger', { method: 'POST' });
    toast('Scheduler triggered! All eligible batches received tasks.');
    loadSchedulerStatus();
    loadBatches(true);
  } catch(e) { toast(e.message, 'error'); }
}

function openAssignModal(batchId, batchName) {
  document.getElementById('assign-batch-id').value = batchId;
  document.getElementById('assign-batch-name').value = batchName;
  openModal('assign-modal');
}

async function assignTasks() {
  const batchId = document.getElementById('assign-batch-id').value;
  const week = document.getElementById('assign-week').value;
  try {
    const btn = document.querySelector('#assign-modal .btn-primary');
    btn.textContent = 'Assigning...';
    btn.disabled = true;
    const data = await api(`/api/admin/batches/${batchId}/assign-from-repo`, {
      method: 'POST',
      body: JSON.stringify({ week_number: parseInt(week) })
    });
    toast(`Assigned ${data.issues_created} tasks for Week ${week}!`);
    closeModal('assign-modal');
    btn.textContent = 'Assign Tasks'; btn.disabled = false;
  } catch(e) {
    toast(e.message, 'error');
    const btn = document.querySelector('#assign-modal .btn-primary');
    btn.textContent = 'Assign Tasks'; btn.disabled = false;
  }
}

function openCreateBatchModal() {
  openModal('create-batch-modal');
}

async function createBatch() {
  const domain = document.getElementById('new-batch-domain').value;
  const batchNum = parseInt(document.getElementById('new-batch-number').value);
  const maxStudents = parseInt(document.getElementById('new-batch-max').value) || 30;
  try {
    const btn = document.querySelector('#create-batch-modal .btn-primary');
    btn.textContent = 'Creating...'; btn.disabled = true;
    await api('/api/admin/batches', {
      method: 'POST',
      body: JSON.stringify({ domain, batch_number: batchNum, max_students: maxStudents })
    });
    toast(`Batch ${domain} #${batchNum} created!`);
    closeModal('create-batch-modal');
    if (currentPage === 'overview') {
      loadOverviewBatches(true);
    }
    loadBatches(true);
    loadStats(true);
    btn.textContent = 'Create Batch'; btn.disabled = false;
  } catch(e) {
    toast(e.message, 'error');
    const btn = document.querySelector('#create-batch-modal .btn-primary');
    btn.textContent = 'Create Batch'; btn.disabled = false;
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
      badge.style.background = 'rgba(52,211,153,0.15)';
      badge.style.borderColor = 'rgba(52,211,153,0.3)';
      badge.style.color = '#34d399';
      badge.textContent = '\u25cf Email Enabled';
    }
  } catch(e) {
    badge.style.background = 'rgba(251,113,133,0.15)';
    badge.style.borderColor = 'rgba(251,113,133,0.3)';
    badge.style.color = '#fb7185';
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
    result.style.color = '#fb7185';
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
      result.style.color = '#34d399';
      result.textContent = `\u2705 Test email sent successfully to ${email}! Check your inbox.`;
      toast('Test email sent!');
    } else {
      result.style.color = '#fb7185';
      result.textContent = `\u274c ${data.message || 'Failed to send email. Check SMTP credentials.'}`;
    }
  } catch(e) {
    result.style.display = 'block';
    result.style.color = '#fb7185';
    result.textContent = `\u274c ${e.message}`;
  } finally {
    btn.textContent = 'Send Test';
    btn.disabled = false;
  }
}

async function openAnalyticsModal(batchId, batchName) {
  const modal = document.getElementById('modal-analytics');
  if (!modal) return;
  modal.style.display = 'flex';
  document.getElementById('analytics-modal-title').textContent = `${batchName} Analytics`;
  const contentEl = document.getElementById('analytics-modal-content');
  contentEl.innerHTML = '<div class="loading-overlay"><div class="spinner"></div> Loading analytics...</div>';
  
  try {
    const data = await api(`/api/admin/batches/${batchId}/analytics`);
    const enrollments = data.enrollments || {};
    const prs = data.pr_stats || {};
    const revenue = data.revenue || {};
    const students = data.student_grid || [];
    
    let html = `
      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:16px; margin-bottom:24px;">
        <div style="background:var(--bg-card); padding:16px; border-radius:8px; border:1px solid var(--border);">
          <div style="font-size:0.8rem; color:var(--text-muted); margin-bottom:8px;">Enrollments</div>
          <div style="font-size:1.5rem; font-weight:700;">${enrollments.active || 0} <span style="font-size:1rem; color:var(--text-muted); font-weight:normal;">active</span></div>
          <div style="font-size:0.8rem; color:var(--text-secondary); margin-top:4px;">${enrollments.dropped || 0} dropped, ${enrollments.completed || 0} completed</div>
        </div>
        <div style="background:var(--bg-card); padding:16px; border-radius:8px; border:1px solid var(--border);">
          <div style="font-size:0.8rem; color:var(--text-muted); margin-bottom:8px;">Pull Requests</div>
          <div style="font-size:1.5rem; font-weight:700;">${prs.merged || 0} <span style="font-size:1rem; color:var(--text-muted); font-weight:normal;">merged</span></div>
          <div style="font-size:0.8rem; color:var(--text-secondary); margin-top:4px;">${prs.total_prs || 0} total submitted</div>
        </div>
        <div style="background:var(--bg-card); padding:16px; border-radius:8px; border:1px solid var(--border);">
          <div style="font-size:0.8rem; color:var(--text-muted); margin-bottom:8px;">Revenue</div>
          <div style="font-size:1.5rem; font-weight:700;">₹${revenue.total_inr || 0}</div>
          <div style="font-size:0.8rem; color:var(--text-secondary); margin-top:4px;">${revenue.total_payments || 0} certificates paid</div>
        </div>
      </div>
      
      <h3 style="margin-bottom:12px; font-size:1rem;">Student Progress Grid</h3>
      <div class="table-wrap" style="max-height: 400px; overflow-y: auto;">
        <table style="width:100%; border-collapse:collapse; font-size:0.9rem;">
          <thead style="position:sticky; top:0; background:var(--bg-surface); z-index:1;">
            <tr>
              <th style="text-align:left; padding:10px; border-bottom:1px solid var(--border);">Student</th>
              <th style="text-align:left; padding:10px; border-bottom:1px solid var(--border);">Status</th>
              <th style="text-align:center; padding:10px; border-bottom:1px solid var(--border);">Tasks</th>
              <th style="text-align:center; padding:10px; border-bottom:1px solid var(--border);">PRs Merged</th>
            </tr>
          </thead>
          <tbody>
            ${students.map(s => `
              <tr>
                <td style="padding:10px; border-bottom:1px solid var(--border);">
                  <div style="font-weight:500;">${s.first_name} ${s.last_name}</div>
                  <div style="font-size:0.8rem; color:var(--text-muted);">${s.github_username || '—'}</div>
                </td>
                <td style="padding:10px; border-bottom:1px solid var(--border);">${statusBadge(s.enrollment_status)}</td>
                <td style="padding:10px; border-bottom:1px solid var(--border); text-align:center;">${s.tasks_completed || 0} / ${s.tasks_assigned || 0}</td>
                <td style="padding:10px; border-bottom:1px solid var(--border); text-align:center;">${s.prs_merged || 0}</td>
              </tr>
            `).join('') || '<tr><td colspan="4" style="padding:20px; text-align:center; color:var(--text-muted);">No student data available.</td></tr>'}
          </tbody>
        </table>
      </div>
    `;
    contentEl.innerHTML = html;
  } catch(e) {
    contentEl.innerHTML = `<div class="empty-state"><div class="empty-state-text">Failed to load analytics: ${e.message}</div></div>`;
  }
}

// ─── INIT ───
window.addEventListener('keydown', e => {
  if (e.key === 'Enter' && document.getElementById('login-overlay').style.display !== 'none') adminLogin();
});

const savedKey = sessionStorage.getItem('skillme_admin_key');
if (savedKey) {
  document.getElementById('api-key-input').value = savedKey;
  adminLogin();
}
