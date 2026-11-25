// SkillMe admin console: email log page + page titles.
// Loaded with defer AFTER admin.js, so these definitions intentionally replace
// admin.js's loadEmailLogs / debounceEmailLogs / loadEmailAggStats.
// ─── Email Logs ───────────────────────────────────────────────────────────────
const EMAIL_TYPE_LABELS = {
  application_confirmation: { label: 'Application',        color: 'var(--info)', bg: 'var(--info-wash)' },
  shortlisted:              { label: 'Shortlisted',         color: 'var(--violet)', bg: 'var(--violet-wash)' },
  offer_letter:             { label: 'Offer Letter',        color: 'var(--ok)', bg: 'var(--ok-wash)' },
  weekly_tasks:             { label: 'Weekly Tasks',        color: 'var(--warn)', bg: 'var(--warn-wash)'  },
  certificate_ready:        { label: 'Certificate',         color: 'var(--danger)', bg: 'var(--danger-wash)' },
  github_invite_reminder:   { label: 'Invite Reminder',     color: 'var(--warn)', bg: 'var(--warn-wash)'  },
  test:                     { label: 'Test',                color: 'var(--text-3)', bg: 'var(--neutral-wash)' },
  task_approved:             { label: 'Task Approved',       color: 'var(--ok)', bg: 'var(--ok-wash)' },
  task_rejected:             { label: 'Task Rejected',       color: 'var(--danger)', bg: 'var(--danger-wash)' },
  task_reminder:            { label: 'Task Reminder',       color: 'var(--warn)', bg: 'var(--warn-wash)' },
  submission_flow_update:    { label: 'Flow Update',         color: 'var(--violet)', bg: 'var(--violet-wash)' },
  urgent_request_fulfilled:  { label: 'Urgent Fulfilled',    color: 'var(--primary)', bg: 'var(--primary-wash)' },
};

// ─── PAGE_META entry for Submissions ─────────────────────────────────────────
if (typeof PAGE_META !== 'undefined') {
  PAGE_META['submissions'] = { title: 'Submissions', subtitle: 'Review and approve/reject weekly LinkedIn submissions' };
  PAGE_META['urgent-requests'] = { title: 'Urgent Requests', subtitle: 'Expedited (24h) certificate/LOR/portfolio processing requests' };
  PAGE_META['reminders'] = { title: 'Task Reminders', subtitle: 'Nudge inactive students who haven\'t submitted their weekly tasks' };
}

let _emailLogOffset = 0;
const _emailLogLimit = 20;
let _emailLogDebounce = null;

function debounceEmailLogs() {
  clearTimeout(_emailLogDebounce);
  _emailLogDebounce = setTimeout(loadEmailLogs, 300);
}

async function loadEmailLogs(offset = 0) {
  _emailLogOffset = offset;
  const type      = document.getElementById('email-log-type-filter')?.value || '';
  const recipient = document.getElementById('email-log-recipient-filter')?.value || '';
  const status    = document.getElementById('email-log-status-filter')?.value || '';
  const tbody     = document.getElementById('email-log-tbody');
  const statsEl   = document.getElementById('email-log-stats');
  const pageEl    = document.getElementById('email-log-pagination');
  if (!tbody) return;

  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:32px;color:var(--text-secondary);">Loading...</td></tr>';

  const params = new URLSearchParams({ limit: _emailLogLimit, offset });
  if (type)      params.set('email_type', type);
  if (recipient) params.set('recipient',  recipient);
  if (status)    params.set('status',     status);

  try {
    const data = await api(`/api/admin/email/logs?${params}`);
    const logs = data.logs || [];
    const total = data.total || 0;

    // ── Stats bar ──────────────────────────────────────────────────────
    const sentCount   = logs.filter(l => l.status === 'sent').length;
    const failedCount = logs.filter(l => l.status === 'failed').length;
    if (statsEl) {
      statsEl.innerHTML = [
        { label: 'Total (page)', val: logs.length, color: 'var(--text-3)', bg: 'var(--neutral-wash)' },
        { label: 'Sent', val: sentCount, color: 'var(--ok)', bg: 'var(--ok-wash)' },
        { label: 'Failed', val: failedCount, color: 'var(--danger)', bg: 'var(--danger-wash)' },
        { label: 'Grand Total', val: total, color: 'var(--violet)', bg: 'var(--violet-wash)' },
      ].map(s => `<div style="padding:8px 16px;border-radius:8px;background:${s.bg};border:1px solid ${tint(s.color,20)};font-size:0.8rem;">
        <span style="color:var(--text-secondary);">${s.label}: </span>
        <strong style="color:${s.color};">${s.val}</strong>
      </div>`).join('');
    }

    // ── Table rows ────────────────────────────────────────────────────
    if (logs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:32px;color:var(--text-secondary);">No email logs found</td></tr>';
    } else {
      tbody.innerHTML = logs.map(log => {
        const t = EMAIL_TYPE_LABELS[log.email_type] || { label: log.email_type, color: 'var(--text-3)', bg: 'var(--neutral-wash)' };
        const statusBadge = log.status === 'sent'
          ? '<span style="padding:2px 8px;border-radius:10px;background:var(--ok-wash);color:var(--ok);font-size:0.72rem;font-weight:600;">✅ Sent</span>'
          : log.status === 'failed'
            ? '<span style="padding:2px 8px;border-radius:10px;background:var(--danger-wash);color:var(--danger);font-size:0.72rem;font-weight:600;">❌ Failed</span>' + emailFailureDetail(log)
            : `<span style="padding:2px 8px;border-radius:10px;background:var(--neutral-wash);color:var(--text-3);font-size:0.72rem;font-weight:600;">⏳ ${esc(log.status || 'pending')}</span>`;
        const d = new Date(log.sent_at && !log.sent_at.endsWith('Z') ? log.sent_at.replace(' ', 'T') + 'Z' : log.sent_at);
        const timeStr = isNaN(d) ? log.sent_at : `${d.toLocaleDateString('en-IN')} ${d.toLocaleTimeString('en-IN', {hour:'2-digit',minute:'2-digit'})}`;
        const subject = log.subject?.length > 50 ? log.subject.slice(0, 50) + '…' : (log.subject || '—');
        const encodedBody = encodeURIComponent(log.body || 'No body content available.').replace(/'/g, "%27");

        return `<tr style="cursor:pointer; transition:background-color 0.2s;" onmouseover="this.style.backgroundColor='var(--violet-wash)'" onmouseout="this.style.backgroundColor='transparent'" onclick="openEmailBodyModal('${encodedBody}')" title="Click anywhere to view full email body">
          <td style="font-size:0.78rem;color:var(--text-secondary);white-space:nowrap;">${timeStr}</td>
          <td><span style="padding:3px 10px;border-radius:10px;background:${t.bg};color:${t.color};font-size:0.72rem;font-weight:600;white-space:nowrap;">${t.label}</span></td>
          <td style="font-size:0.82rem;word-break:break-all;">${log.recipient_email || '—'}</td>
          <td style="font-size:0.78rem;">
            <div style="font-size:0.75rem;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-primary);font-weight:500;">
              📄 ${subject}
            </div>
          </td>
          <td style="font-size:0.82rem;">${log.student_name || '—'}</td>
          <td>${statusBadge}</td>
          <td>${emailEngagementBadges(log)}</td>
        </tr>`;
      }).join('');
    }

    // ── Pagination ────────────────────────────────────────────────────
    if (pageEl) {
      const page = Math.floor(offset / _emailLogLimit) + 1;
      const totalPages = Math.ceil(total / _emailLogLimit);
      pageEl.innerHTML = `
        <span>${total} total emails · Page ${page} of ${Math.max(1, totalPages)}</span>
        <div style="display:flex;gap:8px;">
          <button class="btn btn-ghost" style="padding:4px 12px;font-size:0.78rem;"
            onclick="loadEmailLogs(${Math.max(0, offset - _emailLogLimit)})" ${offset === 0 ? 'disabled' : ''}>← Prev</button>
          <button class="btn btn-ghost" style="padding:4px 12px;font-size:0.78rem;"
            onclick="loadEmailLogs(${offset + _emailLogLimit})" ${offset + _emailLogLimit >= total ? 'disabled' : ''}>Next →</button>
        </div>`;
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--danger);">Error loading logs: ${err.message}</td></tr>`;
  }
}

const EMAIL_FAILURE_LABELS = {
  quota_exhausted:   'Out of daily quota',
  recipient_refused: 'Recipient refused',
  smtp_error:        'SMTP error',
  not_configured:    'SMTP not configured',
};

// Reason (stored in error_message as "<code>: <detail>") + a Resend button, under a Failed badge.
// Rows that failed before reasons were recorded have no error_message and show "Reason not recorded".
function emailFailureDetail(log) {
  const raw = log.error_message || '';
  const m = raw.match(/^(\w+):\s*([\s\S]*)$/);
  const label = m ? (EMAIL_FAILURE_LABELS[m[1]] || m[1]) : (raw ? 'Error' : 'Reason not recorded');
  const detail = m ? m[2] : raw;
  const canResend = !!log.body;
  return `<div style="margin-top:4px;font-size:0.7rem;color:var(--text-secondary);max-width:180px;" title="${esc(detail)}">
      ${esc(label)}
    </div>${canResend ? `<button class="btn btn-ghost" style="margin-top:4px;padding:2px 10px;font-size:0.72rem;"
      onclick="event.stopPropagation(); resendEmailLog(${Number(log.id)}, this)">↻ Resend</button>` : ''}`;
}

async function resendEmailLog(id, btn) {
  if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
  try {
    const res = await api(`/api/admin/email/logs/${id}/resend`, { method: 'POST' });
    if (res.status === 'sent') toast('Email resent');
    else toast(`Resend failed: ${res.error || 'unknown error'}`, 'error');
  } catch (err) {
    toast(`Resend failed: ${err.message}`, 'error');
  }
  loadEmailLogs(_emailLogOffset);
  loadEmailAggStats();
}

// Renders per-row delivery/open/click/bounce/spam badges from email_logs tracking columns.
// These columns are only populated once the Brevo webhook is configured (see /api/webhooks/brevo) —
// rows sent before that will show "No tracking data" here even though they were sent successfully.
function emailEngagementBadges(log) {
  const chips = [];
  if (log.opened_at) chips.push(`<span title="Opened${log.opened_count > 1 ? ' ' + log.opened_count + 'x' : ''}" style="color:var(--ok);">👁️ Opened${log.opened_count > 1 ? ' ×' + log.opened_count : ''}</span>`);
  if (log.clicked_at) chips.push(`<span title="Link clicked${log.clicked_count > 1 ? ' ' + log.clicked_count + 'x' : ''}" style="color:var(--info);">🔗 Clicked</span>`);
  if (log.spam_reported_at) chips.push(`<span title="Recipient marked this as spam" style="color:var(--danger);">🚫 Spam</span>`);
  if (log.bounced_at) chips.push(`<span title="Bounce type: ${log.bounce_type || 'unknown'}" style="color:var(--warn);">⚠️ Bounced</span>`);
  if (log.unsubscribed_at) chips.push(`<span style="color:var(--text-3);">🔕 Unsubscribed</span>`);
  if (!chips.length && log.delivered_at) chips.push(`<span style="color:var(--text-3);">📬 Delivered</span>`);
  if (!chips.length) return '<span style="color:var(--text-muted);font-size:0.72rem;">—</span>';
  return `<div style="display:flex;flex-direction:column;gap:2px;font-size:0.72rem;font-weight:600;">${chips.join('')}</div>`;
}

// All-time aggregate deliverability/engagement stats (independent of the current page/filters)
async function loadEmailAggStats() {
  const el = document.getElementById('email-agg-stats');
  if (!el) return;
  try {
    const data = await api('/api/admin/email/stats');
    const total = data.total || 0;
    const pct = (n) => total ? Math.round((n || 0) / total * 100) : 0;
    const cards = [
      { label: 'Sent',      val: data.sent || 0,      color: 'var(--text-3)' },
      { label: 'Failed',    val: data.failed || 0,     color: 'var(--danger)' },
      { label: 'Delivered', val: data.delivered || 0,  color: 'var(--info)', pct: pct(data.delivered) },
      { label: 'Opened',    val: data.opened || 0,     color: 'var(--ok)', pct: pct(data.opened) },
      { label: 'Clicked',   val: data.clicked || 0,    color: 'var(--violet)', pct: pct(data.clicked) },
      { label: 'Bounced',   val: data.bounced || 0,    color: 'var(--warn)', pct: pct(data.bounced) },
      { label: 'Marked Spam', val: data.spam_reported || 0, color: 'var(--danger)', pct: pct(data.spam_reported) },
    ];
    el.innerHTML = cards.map(c => `<div style="padding:10px 16px;border-radius:8px;background:${tint(c.color,8)};border:1px solid ${tint(c.color,20)};font-size:0.8rem;min-width:110px;">
      <div style="color:var(--text-secondary);font-size:0.72rem;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;">${c.label}</div>
      <div style="color:${c.color};font-weight:700;font-size:1.1rem;">${c.val}${c.pct !== undefined ? ` <span style="font-size:0.72rem;font-weight:600;opacity:0.8;">(${c.pct}%)</span>` : ''}</div>
    </div>`).join('');
    if (!total) {
      el.innerHTML += `<div style="font-size:0.78rem;color:var(--text-secondary);align-self:center;">No emails logged yet.</div>`;
    }
  } catch (err) {
    el.innerHTML = `<div style="font-size:0.78rem;color:var(--danger);">Failed to load stats: ${err.message}</div>`;
  }
}

// Per-account Brevo credits left today (Brevo's own counter when its API key works, else our estimate)
async function loadEmailQuota() {
  const el = document.getElementById('email-quota-accounts');
  if (!el) return;
  try {
    const data = await api('/api/admin/email/quota');
    const accounts = data.accounts || [];
    if (!accounts.length) {
      el.innerHTML = '<div style="font-size:0.8rem;color:var(--text-secondary);">No Brevo accounts configured.</div>';
      return;
    }
    el.innerHTML = accounts.map((a, i) => {
      const cap = a.daily_credits || 300;
      const left = Math.max(0, a.credits_left ?? 0);
      const pctLeft = Math.round(left / cap * 100);
      const color = a.exhausted || pctLeft <= 0 ? 'var(--danger)' : pctLeft <= 10 ? 'var(--warn)' : 'var(--ok)';
      const source = a.credits_source === 'brevo'
        ? 'live from Brevo'
        : `estimated from our logs (${a.used_today} sent today) — Brevo API key not working`;
      return `<div style="background:var(--bg-card-hover);border:1px solid var(--border);border-radius:10px;padding:14px 16px;">
        <div style="display:flex;justify-content:space-between;gap:8px;margin-bottom:8px;">
          <div style="font-family:var(--font-mono);font-size:0.8rem;color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;">${esc(a.account)}</div>
          <div style="font-size:0.7rem;color:var(--text-secondary);flex-shrink:0;">${i === 0 ? 'Primary' : 'Backup'}</div>
        </div>
        <div style="font-size:1.25rem;font-weight:700;color:${color};">${left} <span style="font-size:0.8rem;font-weight:500;color:var(--text-secondary);">/ ${cap} left${a.exhausted ? ' · OUT' : ''}</span></div>
        <div style="height:6px;border-radius:3px;background:var(--border);margin:8px 0 6px;overflow:hidden;">
          <div style="height:100%;width:${pctLeft}%;background:${color};"></div>
        </div>
        <div style="font-size:0.72rem;color:var(--text-secondary);">${source}</div>
      </div>`;
    }).join('');
  } catch (err) {
    el.innerHTML = `<div style="font-size:0.8rem;color:var(--danger);">Failed to load quota: ${esc(err.message)}</div>`;
  }
}

// Auto-load email logs when navigating to the email page
const _origNavigate = typeof navigate === 'function' ? navigate : null;
if (_origNavigate) {
  window._emailNavigatePatched = true;
}
document.addEventListener('DOMContentLoaded', () => {
  // Patch navigate to auto-load email logs on tab switch
  const navItems = document.querySelectorAll('.nav-item');
  navItems.forEach(item => {
    if (item.getAttribute('onclick')?.includes("'email'")) {
      item.addEventListener('click', () => setTimeout(() => { loadEmailLogs(); loadEmailAggStats(); }, 100));
    }
  });
});

function openEmailBodyModal(encodedBody) {
  const iframe = document.getElementById('email-body-iframe');
  if (iframe) {
    iframe.srcdoc = decodeURIComponent(encodedBody);
  }
  openModal('email-body-modal');
}
