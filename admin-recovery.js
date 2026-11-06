/* SkillMe admin: Student Recovery workspace.
 * Additive page. Reuses admin.js helpers (api, esc, jsArg, toast, openModal, closeModal, setBusy,
 * ensureChartJs, _drawChart, chartBase, cssColor). Nothing here changes another page. */
(function () {
  const BASE = '/api/admin/activation';
  const STALE = 'The backend is still running the previous version. Deploy the latest backend, then press Refresh.';
  const $ = id => document.getElementById(id);

  const STAGE_TONE = { never_logged_in: 'danger', no_first_task: 'warn', first_task_submitted: 'info',
    stuck_week_1: 'violet', stuck_week_2: 'accent', stuck_week_3: 'accent', completed: 'ok', __inactive: 'muted' };
  const TRIGGER_COPY = {
    onboarding_no_login: ['No login after enrollment', 'Onboarding email with login and OTP guidance, then reminders until the student logs in.'],
    login_no_first_task: ['Login without first task', 'Track-specific first-task email, then a follow-up until the first submission.'],
    milestone_stall: ['No progress after an approved week', 'Nudges toward the next milestone after the student goes quiet.'],
    inactivity: ['Inactive for N days', 'Generic comeback email. Off by default because the existing daily reminder already covers this.'],
    internship_completed: ['Internship completed', 'One congratulations email when all four weeks are approved.'],
  };
  const REASON = { cohort_ended: 'Internship window ended', opted_out: 'Opted out of reminders', bounced: 'Email bounced',
    spam_reported: 'Marked as spam', unsubscribed: 'Unsubscribed', frequency_cap: 'Emailed recently',
    nothing_to_send: 'Nothing to send (awaiting review)', not_enrolled: 'Not enrolled', holdout: 'Control group',
    no_longer_applies: 'Already progressed', duplicate: 'Already sent' };
  const TRIG_SHORT = { onboarding_no_login: 'Onboarding', login_no_first_task: 'First task', milestone_stall: 'Milestone',
    inactivity: 'Inactive', internship_completed: 'Completed' };

  const rc = { tab: 'students', summary: null, cfg: null, req: 0, page: 1, limit: 25, list: null, selected: new Set(),
    f: { stage: '', inactive: false, domain: '', from: '', to: '', activity: '', milestone: '', eligibility: '', q: '' },
    logPage: 1, log: { status: '', trigger: '' }, group: 'month', supStatus: 'open' };

  const post = (path, body) => api(BASE + path, { method: 'POST', body: JSON.stringify(body || {}) });
  const loading = '<div class="loading-overlay"><div class="spinner"></div> Loading…</div>';
  const empty = (title, text) => `<div class="rc-empty"><b>${esc(title)}</b>${esc(text || '')}</div>`;
  const rel = iso => {
    if (!iso) return '—';
    const d = new Date(iso); if (isNaN(d)) return '—';
    const mins = Math.max(0, Math.round((Date.now() - d.getTime()) / 60000));
    if (mins < 60) return mins <= 1 ? 'just now' : `${mins}m ago`;
    if (mins < 1440) return `${Math.round(mins / 60)}h ago`;
    const days = Math.round(mins / 1440);
    return days < 60 ? `${days}d ago` : `${Math.round(days / 30)}mo ago`;
  };
  const fdt = iso => String(iso || '').replace('T', ' ').slice(0, 16) || '—';
  const num = v => (v === null || v === undefined) ? '—' : v;
  const pctTxt = v => (v === null || v === undefined) ? '—' : `${v}%`;
  const staleMsg = e => (e && (e.message === 'Not Found' || /Unexpected token/.test(e.message))) ? STALE : (e && e.message) || 'Something went wrong.';

  // ─── Modal helper (one reusable dialog) ───
  function rcModal(title, body, foot) {
    $('rc-modal-title').textContent = title;
    $('rc-modal-body').innerHTML = body;
    const f = $('rc-modal-foot');
    f.style.display = foot ? '' : 'none';
    f.innerHTML = foot || '';
    openModal('rc-modal');
  }

  // ─── Page load ───
  async function loadRecovery() {
    const root = $('rc-root');
    root.innerHTML = loading;
    try {
      const s = await api(BASE + '/summary');
      if (!s || !Array.isArray(s.stages)) throw new Error(STALE);
      rc.summary = s; rc.cfg = null;
      badge();
      shell();
      await tab(rc.tab);
    } catch (e) {
      root.innerHTML = `<div class="empty-state"><div class="empty-state-text">${esc(staleMsg(e))}</div></div>`;
    }
  }
  function badge() {
    const b = $('recovery-badge'); if (!b || !rc.summary) return;
    const n = rc.summary.support_open || 0;
    b.textContent = n; b.style.display = n ? '' : 'none';
  }

  function modePill(m) {
    const cls = m.effective === 'live' ? 'is-live' : m.effective === 'dry_run' ? 'is-dry' : 'is-off';
    const label = m.effective === 'live' ? 'Live: sending emails' : m.effective === 'dry_run' ? 'Dry run: nothing is sent' : 'Automation off';
    return `<span class="rc-pill ${cls}" title="${esc(m.note || '')}">${label}</span>`;
  }

  function shell() {
    const s = rc.summary, last = s.last_run;
    const lastTxt = last ? `Last run ${rel(last.ran_at)}: ${last.sent} sent, ${last.would_send} would send, ${last.suppressed} suppressed` : 'No automation run yet';
    $('rc-root').innerHTML = `
      <div class="rc-head">
        <div class="rc-head-l">${modePill(s.mode)}<span class="rc-sub">${esc(lastTxt)}</span></div>
        <div class="rc-head-r">
          <button class="btn btn-secondary btn-sm" onclick="rcRunNow(this)">${s.mode.effective === 'live' ? 'Run automations now' : 'Run a dry run now'}</button>
        </div>
      </div>
      ${s.mode.note ? `<div class="rc-banner">${esc(s.mode.note)}</div>` : ''}
      <div class="rc-stages" id="rc-cards" role="group" aria-label="Filter by stage"></div>
      <div class="rc-filters" id="rc-filters"></div>
      <div class="rc-chips" id="rc-chips"></div>
      <div class="an-tabs" role="tablist">
        ${[['students', 'Students'], ['automations', 'Automations'], ['log', 'Reminder log'], ['report', 'Cohort report'],
          ['support', `Support${s.support_open ? ` <span class="an-count">${s.support_open}</span>` : ''}`]]
          .map(([k, l]) => `<button class="an-tab ${rc.tab === k ? 'active' : ''}" role="tab" onclick="rcTab('${k}')">${l}</button>`).join('')}
      </div>
      <div id="rc-tab"></div>`;
    cards(); filters(); chips();
  }

  // ─── Stage cards ───
  function cards() {
    const s = rc.summary, total = s.total || 0;
    const items = s.stages.map(x => ({ key: x.key, label: x.label, count: x.count }));
    items.push({ key: '__inactive', label: `Inactive ${s.inactive_days || 7}+ days`, count: s.inactive_7d });
    $('rc-cards').innerHTML = items.map(x => {
      const active = x.key === '__inactive' ? rc.f.inactive : rc.f.stage === x.key;
      return `<button class="rc-stage rc-tone-${STAGE_TONE[x.key]} ${active ? 'is-active' : ''}" aria-pressed="${active}" onclick="rcCard('${x.key}')">
        <div class="rc-stage-label">${esc(x.label)}</div><div class="rc-stage-val">${x.count}</div>
        <div class="rc-stage-pct">${total ? Math.round(x.count * 100 / total) : 0}% of enrolled</div></button>`;
    }).join('');
  }
  function rcCard(key) {
    if (key === '__inactive') rc.f.inactive = !rc.f.inactive;
    else rc.f.stage = rc.f.stage === key ? '' : key;
    rc.page = 1; rc.selected.clear();
    if (rc.tab !== 'students') { tab('students'); } else { cards(); chips(); loadList(); }
  }

  // ─── Filters ───
  function filters() {
    const s = rc.summary, f = rc.f;
    const opt = (v, l, cur) => `<option value="${esc(v)}" ${String(cur) === String(v) ? 'selected' : ''}>${esc(l)}</option>`;
    $('rc-filters').innerHTML = `
      <label class="an-field"><span>Track</span><select class="filter-select" onchange="rcSetF('domain', this.value)">${opt('', 'All tracks', f.domain)}${s.domains.map(d => opt(d.key, d.label, f.domain)).join('')}</select></label>
      <label class="an-field"><span>Enrolled from</span><input type="date" value="${esc(f.from)}" onchange="rcSetF('from', this.value)"></label>
      <label class="an-field"><span>Enrolled to</span><input type="date" value="${esc(f.to)}" onchange="rcSetF('to', this.value)"></label>
      <label class="an-field"><span>Last activity</span><select class="filter-select" onchange="rcSetF('activity', this.value)">
        ${opt('', 'Any time', f.activity)}${opt('0-3', 'Within 3 days', f.activity)}${opt('3-7', '3 to 7 days ago', f.activity)}${opt('7-14', '7 to 14 days ago', f.activity)}${opt('14+', 'Over 14 days ago', f.activity)}${opt('never', 'Never active', f.activity)}</select></label>
      <label class="an-field"><span>Current milestone</span><select class="filter-select" onchange="rcSetF('milestone', this.value)">
        ${opt('', 'Any', f.milestone)}${[1, 2, 3, 4].map(n => opt(n, `Week ${n}`, f.milestone)).join('')}</select></label>
      <label class="an-field"><span>Internship window</span><select class="filter-select" onchange="rcSetF('eligibility', this.value)">
        ${opt('', 'All', f.eligibility)}${opt('active', 'Still open', f.eligibility)}${opt('ended', 'Ended', f.eligibility)}</select></label>
      <label class="an-field"><span>Search</span><input type="search" placeholder="Name or email" value="${esc(f.q)}" oninput="rcSearch(this.value)"></label>`;
  }
  const rcSearch = debounce(v => rcSetF('q', v.trim(), true), 300);
  function rcSetF(k, v, keepFocus) {
    rc.f[k] = v; rc.page = 1; rc.selected.clear();
    if (rc.tab !== 'students') { tab('students'); return; }
    cards(); chips(); if (!keepFocus) { /* selects keep their own state */ } loadList();
  }
  function chips() {
    const f = rc.f, out = [];
    const add = (k, label) => out.push(`<span class="rc-chip">${esc(label)}<button aria-label="Remove filter" onclick="rcClearF('${k}')">&times;</button></span>`);
    const dom = rc.summary.domains.find(d => d.key === f.domain);
    if (f.stage) add('stage', rc.summary.stages.find(x => x.key === f.stage)?.label || f.stage);
    if (f.inactive) add('inactive', 'Inactive');
    if (f.domain) add('domain', dom ? dom.label : f.domain);
    if (f.from) add('from', `From ${f.from}`);
    if (f.to) add('to', `To ${f.to}`);
    if (f.activity) add('activity', `Activity: ${f.activity === 'never' ? 'never' : f.activity + 'd'}`);
    if (f.milestone) add('milestone', `Week ${f.milestone}`);
    if (f.eligibility) add('eligibility', f.eligibility === 'ended' ? 'Window ended' : 'Window open');
    if (f.q) add('q', `"${f.q}"`);
    if (out.length > 1) out.push('<button class="btn btn-ghost btn-sm" onclick="rcClearAll()">Clear all</button>');
    $('rc-chips').innerHTML = out.join('');
  }
  function rcClearF(k) { rc.f[k] = k === 'inactive' ? false : ''; filters(); rcSetF(k, rc.f[k]); }
  function rcClearAll() { Object.keys(rc.f).forEach(k => rc.f[k] = k === 'inactive' ? false : ''); filters(); rcSetF('stage', ''); }

  // ─── Tabs ───
  async function tab(t) {
    rc.tab = t;
    document.querySelectorAll('#rc-root .an-tab').forEach((el, i) => el.classList.toggle('active', ['students', 'automations', 'log', 'report', 'support'][i] === t));
    cards(); chips();
    const show = t === 'students';   // stage cards stay visible as navigation; filters only apply to the student list
    $('rc-filters').style.display = show ? '' : 'none';
    $('rc-chips').style.display = show ? '' : 'none';
    const box = $('rc-tab'); box.innerHTML = loading;
    try {
      if (t === 'students') await loadList();
      else if (t === 'automations') await automations();
      else if (t === 'log') await logTab();
      else if (t === 'report') await report();
      else if (t === 'support') await support();
    } catch (e) { box.innerHTML = `<div class="empty-state"><div class="empty-state-text">${esc(staleMsg(e))}</div></div>`; }
  }

  // ─── Students list ───
  const dots = (done, next) => `<span class="rc-dots" title="Approved weeks: ${done.join(', ') || 'none'}">${[1, 2, 3, 4].map(w =>
    `<i class="rc-dot ${done.includes(w) ? 'is-done' : w === next ? 'is-next' : ''}"></i>`).join('')}</span>`;
  const STAGE_BADGE = { never_logged_in: 'badge-danger', no_first_task: 'badge-warn', first_task_submitted: 'badge-pending', stuck_week_1: 'badge-shortlisted', stuck_week_2: 'badge-shortlisted', stuck_week_3: 'badge-shortlisted', completed: 'badge-ok' };
  const stageBadge = s => `<span class="badge ${STAGE_BADGE[s.stage] || 'badge-enrolled'}">${esc(s.stage_label)}</span>`;

  function remCell(r) {
    if (!r) return '<span class="rc-sub">None yet</span>';
    const dry = r.status === 'dry_run';
    return `<div>${esc(TRIG_SHORT[r.trigger] || r.trigger)} · ${dry ? 'dry run' : esc(r.status)}</div>
      <div class="rc-sub">${rel(r.at)}${dry ? '' : `<span class="rc-ico ${r.opened ? 'is-on' : ''}">opened</span><span class="rc-ico ${r.clicked ? 'is-on' : ''}">clicked</span>`}</div>`;
  }

  async function loadList() {
    const my = ++rc.req, f = rc.f;
    const q = new URLSearchParams({ page: rc.page, limit: rc.limit });
    if (f.stage) q.set('stage', f.stage); if (f.inactive) q.set('inactive', 'true'); if (f.domain) q.set('domain', f.domain);
    if (f.from) q.set('enrolled_from', f.from); if (f.to) q.set('enrolled_to', f.to);
    if (f.activity) q.set('activity', f.activity); if (f.milestone) q.set('milestone', f.milestone);
    if (f.eligibility) q.set('eligibility', f.eligibility); if (f.q) q.set('q', f.q);
    const box = $('rc-tab');
    if (!rc.list) box.innerHTML = loading;
    const d = await api(`${BASE}/students?${q}`);
    if (my !== rc.req) return;              // a newer request superseded this one
    if (!d || !Array.isArray(d.students)) throw new Error(STALE);
    rc.list = d;
    renderList();
  }

  function renderList() {
    const d = rc.list, box = $('rc-tab');
    if (!d.students.length) { box.innerHTML = `<div class="panel"><div class="panel-body">${empty('No students match these filters', 'Try clearing a filter or choosing another stage.')}</div></div>`; return; }
    const pageIds = d.students.map(s => s.id), allPage = pageIds.every(id => rc.selected.has(id));
    const n = rc.selected.size;
    box.innerHTML = `
      <div id="rc-bulk">${n ? bulkBar() : ''}</div>
      <div class="panel"><div class="table-wrap"><table>
        <thead><tr><th style="width:34px"><input type="checkbox" aria-label="Select all on this page" ${allPage ? 'checked' : ''} onchange="rcSelPage(this.checked)"></th>
          <th>Student</th><th>Track</th><th>Stage</th><th>Weeks</th><th>Last activity</th><th>Last reminder</th><th>Window</th><th></th></tr></thead>
        <tbody>${d.students.map(s => `<tr class="rc-row-click" onclick="rcView(${s.id})">
          <td onclick="event.stopPropagation()"><input type="checkbox" aria-label="Select ${esc(s.name)}" ${rc.selected.has(s.id) ? 'checked' : ''} onchange="rcSel(${s.id}, this.checked)"></td>
          <td><div class="rc-who">${esc(s.name)}${s.is_test ? ' <span class="badge badge-pending">test</span>' : ''}<small>${esc(s.email)}</small></div></td>
          <td>${esc(s.domain_label)}</td><td>${stageBadge(s)}</td>
          <td>${dots(s.weeks_approved, s.current_milestone)}</td>
          <td>${s.last_activity_at ? rel(s.last_activity_at) : 'Never'}${s.inactive ? ' <span class="rc-ico">idle</span>' : ''}</td>
          <td>${remCell(s.last_reminder)}</td>
          <td>${s.eligibility === 'ended' ? '<span class="badge badge-dropped" title="Automated reminders are paused for this cohort">Ended</span>' : '<span class="badge badge-ok">Open</span>'}${s.holdout ? ' <span class="rc-ico" title="In the control group: no automated reminders">control</span>' : ''}</td>
          <td onclick="event.stopPropagation()" style="white-space:nowrap">
            <button class="btn btn-secondary btn-sm" ${s.recommended ? '' : 'disabled title="Nothing to send right now"'} onclick="rcSend([${s.id}])">Remind</button></td>
        </tr>`).join('')}</tbody></table></div></div>
      <div class="list-pagination" id="rc-pager"></div>`;
    pager();
  }
  function bulkBar() {
    const n = rc.selected.size, tot = rc.list.total, more = rc.list.ids.length;
    return `<div class="rc-bulk"><div><b>${n}</b> selected${tot > n && n >= rc.list.students.length && more > n ? ` · <a href="#" onclick="rcSelAll();return false;">Select all ${Math.min(tot, more)} matching</a>` : ''}
      · <a href="#" onclick="rcSelNone();return false;">Clear</a></div>
      <button class="btn btn-primary btn-sm" onclick="rcSend([...rc_sel()])">Send recommended reminder to ${n}</button></div>`;
  }
  window.rc_sel = () => rc.selected;
  function bulkRefresh() { const el = $('rc-bulk'); if (el) el.innerHTML = rc.selected.size ? bulkBar() : ''; }
  function rcSel(id, on) { on ? rc.selected.add(id) : rc.selected.delete(id); bulkRefresh(); }
  function rcSelPage(on) { rc.list.students.forEach(s => on ? rc.selected.add(s.id) : rc.selected.delete(s.id)); renderList(); }
  function rcSelAll() { rc.list.ids.forEach(id => rc.selected.add(id)); renderList(); }
  function rcSelNone() { rc.selected.clear(); renderList(); }
  function pager() {
    const d = rc.list, el = $('rc-pager'); if (!el) return;
    el.innerHTML = `<span class="rc-sub">${d.total} student${d.total === 1 ? '' : 's'} · page ${d.page} of ${d.total_pages}</span>
      <button class="btn btn-secondary btn-sm" ${d.page <= 1 ? 'disabled' : ''} onclick="rcPage(${d.page - 1})">Previous</button>
      <button class="btn btn-secondary btn-sm" ${d.page >= d.total_pages ? 'disabled' : ''} onclick="rcPage(${d.page + 1})">Next</button>`;
  }
  function rcPage(p) { rc.page = p; loadList().catch(e => toast(staleMsg(e), 'error')); }

  // ─── Send / preview / confirm ───
  async function rcSend(ids, override = false) {
    rcModal('Send reminder', loading);
    try {
      const p = await post('/preview', { student_ids: ids, override_ended: override });
      const m = p.mode, live = m.effective === 'live', off = m.effective === 'off';
      const reasons = Object.entries(p.excluded_by_reason || {}).map(([r, n]) => `<span class="badge badge-pending">${n} · ${esc(REASON[r] || r)}</span>`).join('');
      const canOverride = (p.excluded_by_reason || {}).cohort_ended || override;
      const body = `
        ${off ? '<div class="rc-banner">Automation is off, so nothing can be sent. Switch to Dry run in the Automations tab to preview.</div>'
          : live ? '<div class="rc-banner is-ok"><b>Live.</b> These emails will be delivered to students.</div>'
          : `<div class="rc-banner"><b>Dry run.</b> ${esc(m.note || 'Nothing is emailed. The send is only recorded so you can review it.')}</div>`}
        <p style="margin:0 0 6px"><b>${p.eligible.length}</b> of ${ids.length} selected student${ids.length === 1 ? '' : 's'} will get a reminder.</p>
        ${reasons ? `<div class="rc-reasons">${reasons}</div>` : ''}
        ${canOverride ? `<label style="display:flex;gap:8px;align-items:center;margin-bottom:14px;font-size:0.85rem"><input type="checkbox" ${override ? 'checked' : ''} onchange="rcSend(${JSON.stringify(ids)}, this.checked)"> Also include students whose internship window has ended</label>` : ''}
        ${p.ended_included ? '<div class="rc-banner">Some recipients are past their internship window. Only include them if you are sure.</div>' : ''}
        ${p.sample ? `<div class="rc-sub" style="margin-bottom:6px">Preview for ${esc(p.sample.student)} · subject: <b>${esc(p.sample.subject)}</b></div>
          <iframe class="rc-preview" sandbox srcdoc="${esc(p.sample.html)}" title="Email preview"></iframe>` : empty('No one to send to', 'Every selected student was excluded.')}`;
      const label = live ? `Send ${p.eligible.length} email${p.eligible.length === 1 ? '' : 's'}` : `Record dry run for ${p.eligible.length}`;
      rcModal('Send reminder', body, `<button class="btn btn-secondary" onclick="closeModal('rc-modal')">Cancel</button>
        <button class="btn ${live ? 'btn-primary' : 'btn-secondary'}" id="rc-go" ${(off || !p.eligible.length) ? 'disabled' : ''}
          onclick='rcConfirmSend(${JSON.stringify(p.eligible.map(e => e.student_id))}, ${override}, this)'>${label}</button>`);
    } catch (e) { rcModal('Send reminder', `<div class="empty-state"><div class="empty-state-text">${esc(staleMsg(e))}</div></div>`); }
  }
  async function rcConfirmSend(ids, override, btn) {
    const done = setBusy(btn, 'Working…');
    try {
      const r = await post('/send', { student_ids: ids, override_ended: override, confirm: true });
      closeModal('rc-modal');
      toast(r.queued ? `Sending ${r.queued} email(s) in the background` : r.sent ? `Sent ${r.sent} email(s)` : `Dry run recorded for ${r.would_send || 0}`);
      rc.selected.clear(); setTimeout(() => loadRecovery(), r.queued ? 2500 : 0);
    } catch (e) { toast(e.message, 'error'); done(); }
  }
  async function rcRunNow(btn) {
    const done = setBusy(btn, 'Running…');
    try {
      const r = await post('/run');
      toast(r.queued ? 'Automation pass started' : `Dry run: ${r.would_send} would send, ${r.suppressed} suppressed`);
      await loadRecovery();
    } catch (e) { toast(e.message, 'error'); } finally { done(); }
  }

  // ─── Student drawer ───
  async function rcView(id) {
    rcModal('Student progress', loading);
    try {
      const d = await api(`${BASE}/students/${id}`);
      const s = d.student;
      const tl = [
        ...(d.events || []).map(e => ({ at: e.occurred_at, label: `${String(e.event_type).replace(/_/g, ' ')}${e.source === 'backfill' ? ' (from history)' : ''}` })),
        ...(d.reminders || []).map(r => ({ at: r.created_at, label: `Reminder ${r.status === 'dry_run' ? '(dry run)' : r.status}: ${TRIG_SHORT[r.trigger_key] || r.trigger_key} step ${r.step}${r.reason && r.reason !== 'would_send' ? ` · ${REASON[r.reason] || r.reason}` : ''}${r.clicked_at ? ' · clicked' : ''}${r.opened_at ? ' · opened' : ''}` })),
        ...((d.journey && d.journey.timeline) || []).map(e => ({ at: e.at, label: e.label })),
      ].filter(x => x.at).sort((a, b) => String(b.at).localeCompare(String(a.at)));
      const seen = new Set(), rows = tl.filter(x => { const k = `${String(x.at).slice(0, 16)}|${x.label}`; if (seen.has(k)) return false; seen.add(k); return true; });
      rcModal(s.name, `
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">${stageBadge(s)}
          <span class="badge ${s.eligibility === 'ended' ? 'badge-dropped' : 'badge-ok'}">${s.eligibility === 'ended' ? 'Internship window ended' : 'Internship open'}</span>
          ${s.inactive ? '<span class="badge badge-pending">Inactive</span>' : ''}</div>
        <dl class="an-kv" style="margin-bottom:16px">
          <dt>Email</dt><dd>${esc(s.email)}</dd><dt>Track</dt><dd>${esc(s.domain_label)}</dd>
          <dt>Enrolled</dt><dd>${fdt(s.enrolled_at)}</dd><dt>Last activity</dt><dd>${s.last_activity_at ? `${fdt(s.last_activity_at)} (${rel(s.last_activity_at)})` : 'Never'}</dd>
          <dt>Weeks approved</dt><dd>${dots(s.weeks_approved, s.current_milestone)} ${s.weeks_approved.length} of 4${s.current_milestone ? ` · next: Week ${s.current_milestone}` : ''}</dd>
          <dt>Next best action</dt><dd>${esc(d.recommended_label || 'Nothing to send right now')}</dd></dl>
        ${(d.support || []).length ? `<h4 style="margin:0 0 8px">Help requests</h4>${d.support.map(q => `<div class="rc-sup"><b>${esc(q.category || 'other')}</b> · ${esc(q.status)} · ${rel(q.created_at)}<div>${esc(q.message || '')}</div></div>`).join('')}<div style="height:14px"></div>` : ''}
        <h4 style="margin:0 0 8px">Timeline</h4>
        ${rows.length ? `<ul class="an-timeline">${rows.slice(0, 60).map(e => `<li><span class="at">${esc(fdt(e.at))}</span>${esc(e.label)}</li>`).join('')}</ul>` : '<div class="rc-sub">No events yet. Run Backfill in the Automations tab to import history.</div>'}`,
        `<button class="btn btn-secondary" onclick="closeModal('rc-modal')">Close</button>
         <button class="btn btn-primary" ${s.recommended ? '' : 'disabled'} onclick="rcSend([${s.id}])">Send reminder</button>`);
    } catch (e) { rcModal('Student progress', `<div class="empty-state"><div class="empty-state-text">${esc(staleMsg(e))}</div></div>`); }
  }

  // ─── Automations ───
  async function automations() {
    const d = await api(BASE + '/settings');
    if (!d || !d.config) throw new Error(STALE);
    rc.cfg = d.config; const c = d.config, m = d.mode;
    const modeCard = (v, t, desc, disabled) => `<label class="rc-trig" style="display:block;cursor:${disabled ? 'not-allowed' : 'pointer'};opacity:${disabled ? .55 : 1};${c.mode === v ? 'border-color:var(--primary)' : ''}">
      <div class="rc-trig-h"><div><div class="rc-trig-t">${t}</div><div class="rc-trig-d">${desc}</div></div><input type="radio" name="rc-mode" value="${v}" ${c.mode === v ? 'checked' : ''} ${disabled ? 'disabled' : ''}></div></label>`;
    $('rc-tab').innerHTML = `
      <div class="panel"><div class="panel-header"><div><div class="panel-title">Delivery mode</div><div class="panel-subtitle">Start in Dry run, review who would be emailed, then go Live.</div></div></div><div class="panel-body" style="max-height:none">
        ${modeCard('off', 'Off', 'No automated or manual reminders. The default.')}
        ${modeCard('dry_run', 'Dry run', 'Everything is evaluated and recorded, but no email is sent. Safe for review.')}
        ${modeCard('live', 'Live', m.live_allowed ? 'Sends real emails to students, within the rules below.' : 'Locked: the server has not enabled live sending (ENGAGEMENT_LIVE_ALLOWED).', !m.live_allowed)}
      </div></div>
      <div class="panel" style="margin-top:16px"><div class="panel-header"><div><div class="panel-title">Student dashboard checklist</div><div class="panel-subtitle">Shows the guided first-task card and next-milestone card on the student dashboard.</div></div>
        <label class="rc-switch"><input type="checkbox" id="rc-ui" ${c.student_ui ? 'checked' : ''}><i></i></label></div></div>
      <h3 style="margin:22px 0 10px">Triggers</h3>
      ${Object.keys(TRIGGER_COPY).map(k => {
        const t = c.triggers[k] || {}, [title, desc] = TRIGGER_COPY[k];
        return `<div class="rc-trig"><div class="rc-trig-h"><div><div class="rc-trig-t">${title}</div><div class="rc-trig-d">${desc}</div></div>
          <label class="rc-switch"><input type="checkbox" id="rc-t-${k}" ${t.enabled ? 'checked' : ''}><i></i></label></div>
          <div class="rc-inline"><label>Send at (hours after the trigger, comma separated)<input id="rc-d-${k}" value="${esc((t.delays_h || []).join(', '))}"></label>
          ${k === 'inactivity' ? `<label>Cooldown (days)<input type="number" min="1" max="90" id="rc-cd-${k}" value="${t.cooldown_days || 7}"></label>` : ''}</div></div>`;
      }).join('')}
      <h3 style="margin:22px 0 10px">Rules</h3>
      <div class="panel"><div class="panel-body" style="max-height:none"><div class="rc-inline" style="margin-top:0">
        <label>Inactive after (days)<input type="number" min="1" max="90" id="rc-inactive" value="${c.inactive_days}"></label>
        <label>Grace after 28 days (days)<input type="number" min="0" max="180" id="rc-grace" value="${c.grace_days}"></label>
        <label>Min hours between different emails<input type="number" min="0" max="720" id="rc-cap" value="${c.frequency_cap_hours}"></label>
        <label>Control group (%)<input type="number" min="0" max="50" id="rc-hold" value="${c.holdout_pct}"></label></div>
        <p class="rc-sub" style="margin:12px 0 0">Students past their internship window plus grace are never emailed automatically. Opted-out, bounced and spam-reported addresses are always skipped. The control group gets no automated reminders so we can measure whether they work.</p></div></div>
      <div style="display:flex;gap:10px;margin-top:18px;flex-wrap:wrap">
        <button class="btn btn-primary" onclick="rcSaveSettings(this)">Save settings</button>
        <button class="btn btn-secondary" onclick="rcBackfill(this)">Import history (backfill events)</button></div>`;
  }
  async function rcSaveSettings(btn) {
    const mode = (document.querySelector('input[name="rc-mode"]:checked') || {}).value || rc.cfg.mode;
    const triggers = {};
    for (const k of Object.keys(TRIGGER_COPY)) {
      const raw = $(`rc-d-${k}`).value.split(',').map(x => x.trim()).filter(Boolean).map(Number);
      if (!raw.length || raw.some(n => !isFinite(n) || n < 0 || n > 1440)) { toast(`Check the send times for "${TRIGGER_COPY[k][0]}".`, 'error'); return; }
      triggers[k] = { enabled: $(`rc-t-${k}`).checked, delays_h: raw };
      if (k === 'inactivity') triggers[k].cooldown_days = Number($(`rc-cd-${k}`).value) || 7;
    }
    const body = { mode, student_ui: $('rc-ui').checked, triggers, inactive_days: Number($('rc-inactive').value), grace_days: Number($('rc-grace').value),
      frequency_cap_hours: Number($('rc-cap').value), holdout_pct: Number($('rc-hold').value) };
    const goingLive = mode === 'live' && rc.cfg.mode !== 'live';
    const save = async (b) => {
      const done = setBusy(b, 'Saving…');
      try { if (goingLive) body.confirm_live = true; await api(BASE + '/settings', { method: 'PUT', body: JSON.stringify(body) });
        closeModal('rc-modal'); toast('Settings saved'); await loadRecovery(); }
      catch (e) { toast(e.message, 'error'); done(); }
    };
    if (goingLive) {
      window.rcLiveGo = b => save(b);
      rcModal('Switch to Live?', `<div class="rc-banner"><b>Real emails will be sent to students.</b> Automations run hourly between 9 am and 8 pm IST. Each reminder is sent once, and students who progress stop receiving it.</div>
        <p style="margin:0">Have you reviewed a dry run? You can switch back to Dry run or Off at any time.</p>`,
        `<button class="btn btn-secondary" onclick="closeModal('rc-modal')">Not yet</button><button class="btn btn-primary" onclick="rcLiveGo(this)">Yes, go Live</button>`);
    } else save(btn);
  }
  async function rcBackfill(btn) {
    const done = setBusy(btn, 'Importing…');
    try { const r = await post('/backfill'); toast(`History imported: ${r.created} new event(s)`); } catch (e) { toast(e.message, 'error'); } finally { done(); }
  }

  // ─── Reminder log ───
  async function logTab() {
    const q = new URLSearchParams({ page: rc.logPage, limit: 25 });
    if (rc.log.status) q.set('status', rc.log.status); if (rc.log.trigger) q.set('trigger', rc.log.trigger);
    const d = await api(`${BASE}/reminders?${q}`);
    if (!d || !Array.isArray(d.reminders)) throw new Error(STALE);
    const sel = (id, cur, opts) => `<select class="filter-select" onchange="rcLogF('${id}', this.value)">${opts.map(([v, l]) => `<option value="${v}" ${cur === v ? 'selected' : ''}>${l}</option>`).join('')}</select>`;
    $('rc-tab').innerHTML = `
      <div class="rc-filters"><label class="an-field"><span>Status</span>${sel('status', rc.log.status, [['', 'All'], ['sent', 'Sent'], ['dry_run', 'Dry run'], ['suppressed', 'Suppressed'], ['failed', 'Failed']])}</label>
        <label class="an-field"><span>Trigger</span>${sel('trigger', rc.log.trigger, [['', 'All'], ...Object.keys(TRIGGER_COPY).map(k => [k, TRIG_SHORT[k]])])}</label></div>
      ${d.reminders.length ? `<div class="panel"><div class="table-wrap"><table><thead><tr><th>When</th><th>Student</th><th>Trigger</th><th>Step</th><th>Status</th><th>Opened</th><th>Clicked</th></tr></thead><tbody>
        ${d.reminders.map(r => `<tr class="rc-row-click" onclick="rcView(${r.student_id})"><td>${fdt(r.created_at)}</td><td><div class="rc-who">${esc(r.name || '—')}<small>${esc(r.email || '')}</small></div></td>
          <td>${esc(TRIG_SHORT[r.trigger_key] || r.trigger_key)}</td><td>${r.step}</td>
          <td><span class="badge ${r.status === 'sent' ? 'badge-ok' : r.status === 'failed' ? 'badge-danger' : 'badge-pending'}">${esc(r.status === 'dry_run' ? 'dry run' : r.status)}</span>${r.reason && r.reason !== 'would_send' ? `<div class="rc-sub">${esc(REASON[r.reason] || r.reason)}</div>` : ''}</td>
          <td>${r.opened_at ? 'Yes' : '—'}</td><td>${r.clicked_at ? 'Yes' : '—'}</td></tr>`).join('')}</tbody></table></div></div>
        <div class="list-pagination"><span class="rc-sub">${d.total} reminder${d.total === 1 ? '' : 's'} · page ${d.page} of ${d.total_pages}</span>
          <button class="btn btn-secondary btn-sm" ${d.page <= 1 ? 'disabled' : ''} onclick="rcLogPage(${d.page - 1})">Previous</button>
          <button class="btn btn-secondary btn-sm" ${d.page >= d.total_pages ? 'disabled' : ''} onclick="rcLogPage(${d.page + 1})">Next</button></div>`
        : `<div class="panel"><div class="panel-body">${empty('No reminders yet', 'Run a dry run from the header to see who would be contacted.')}</div></div>`}`;
  }
  function rcLogF(k, v) { rc.log[k] = v; rc.logPage = 1; logTab().catch(e => toast(staleMsg(e), 'error')); }
  function rcLogPage(p) { rc.logPage = p; logTab().catch(e => toast(staleMsg(e), 'error')); }

  // ─── Cohort report ───
  async function report() {
    const d = await api(`${BASE}/report?group=${rc.group}`);
    if (!d || !d.total || !Array.isArray(d.cohorts)) throw new Error(STALE);
    const t = d.total, b = d.baseline, g = d.targets;
    const kpi = (label, cur, unit, base, target, status) => `<div class="rc-kpi"><div class="rc-kpi-l">${label}</div>
      <div class="rc-kpi-v ${status === 'good' ? 'is-good' : status === 'off' ? 'is-off' : ''}">${cur === null || cur === undefined ? '—' : cur + unit}</div>
      <div class="rc-kpi-m"><span>Baseline ${base}${unit}</span>${target !== undefined ? `<span>Target ${target}${unit}</span>` : ''}</div></div>`;
    const cell = (v, st, unit) => `<td class="${st === 'good' ? 'rc-good' : st === 'off' ? 'rc-off' : ''}">${v === null || v === undefined ? '—' : v + unit}</td>`;
    $('rc-tab').innerHTML = `
      <div class="rc-head"><div class="rc-sub">Enrolled students grouped by enrollment ${rc.group}. Definitions match the Analytics page.</div>
        <select class="filter-select" onchange="rcGroup(this.value)"><option value="month" ${rc.group === 'month' ? 'selected' : ''}>By month</option><option value="week" ${rc.group === 'week' ? 'selected' : ''}>By week</option></select></div>
      <div class="rc-kpis">
        ${kpi('First login', t.first_login_pct, '%', b.first_login_pct)}
        ${kpi('First task (of logged in)', t.first_task_pct, '%', b.first_task_pct, g.first_task_pct, t.status.first_task_pct)}
        ${kpi('Completion (of first task)', t.completion_pct, '%', b.completion_pct, g.completion_pct, t.status.completion_pct)}
        ${kpi('Median login to first task', t.median_login_to_task_days, ' days', b.median_login_to_task_days, g.median_login_to_task_days, t.status.median_login_to_task_days)}
        ${kpi('Weekly active students', t.weekly_active, '', b.weekly_active)}</div>
      ${d.cohorts.length ? `<div class="panel"><div class="panel-header"><div class="panel-title">Trend by cohort</div></div><div class="panel-body" style="max-height:none"><div style="position:relative;height:240px"><canvas id="rc-chart"></canvas></div></div></div>
      <div class="panel" style="margin-top:16px"><div class="panel-header"><div class="panel-title">Cohorts</div><div class="panel-subtitle">Green meets the target, amber does not yet.</div></div>
        <div class="table-wrap"><table><thead><tr><th>Cohort</th><th>Enrolled</th><th>Logged in</th><th>First task</th><th>Completion</th><th>Median days</th><th>Viewed task</th></tr></thead><tbody>
        ${d.cohorts.map(c => `<tr><td><b>${esc(c.cohort)}</b></td><td>${c.enrolled}</td><td>${c.logged_in} <span class="rc-sub">(${c.first_login_pct}%)</span></td>
          ${cell(c.first_task_pct, c.status.first_task_pct, '%')}${cell(c.completion_pct, c.status.completion_pct, '%')}${cell(c.median_login_to_task_days, c.status.median_login_to_task_days, 'd')}<td>${c.first_task_viewed_pct}%</td></tr>`).join('')}
        </tbody></table></div></div>` : `<div class="panel"><div class="panel-body">${empty('No enrolled students yet')}</div></div>`}
      <div class="panel" style="margin-top:16px"><div class="panel-header"><div><div class="panel-title">Do reminders work?</div><div class="panel-subtitle">Reminded students versus the control group, same ${d.experiments[0] ? d.experiments[0].window_hours : 72}-hour window.</div></div></div>
        ${d.experiments.length ? `<div class="table-wrap"><table><thead><tr><th>Trigger</th><th>Reminded</th><th>Progressed</th><th>Control</th><th>Progressed</th><th>Lift</th><th>Opened</th><th>Clicked</th></tr></thead><tbody>
          ${d.experiments.map(e => `<tr><td>${esc(TRIG_SHORT[e.trigger] || e.trigger)}</td><td>${e.treated.n}</td><td>${pctTxt(e.treated.rate)}</td><td>${e.holdout.n}</td><td>${pctTxt(e.holdout.rate)}</td>
            <td>${e.enough_data ? `<b class="${e.lift_pts > 0 ? 'rc-good' : 'rc-off'}">${e.lift_pts > 0 ? '+' : ''}${num(e.lift_pts)} pts</b>` : `<span class="badge badge-pending" title="Needs at least ${d.min_sample} students in each group">Not enough data</span>`}</td>
            <td>${pctTxt(e.treated.open_rate)}</td><td>${pctTxt(e.treated.click_rate)}</td></tr>`).join('')}</tbody></table></div>`
          : `<div class="panel-body">${empty('No results yet', 'Results appear once automated reminders have been sent live.')}</div>`}</div>`;
    if (d.cohorts.length) ensureChartJs().then(() => {
      const asc = [...d.cohorts].reverse(), col = n => cssColor(n);
      _drawChart('rc-chart', { type: 'line', data: { labels: asc.map(c => c.cohort), datasets: [
        { label: 'First task %', data: asc.map(c => c.first_task_pct), borderColor: col('--primary'), backgroundColor: col('--primary'), tension: .3 },
        { label: 'Completion %', data: asc.map(c => c.completion_pct), borderColor: col('--ok'), backgroundColor: col('--ok'), tension: .3 },
        { label: 'First login %', data: asc.map(c => c.first_login_pct), borderColor: col('--info'), backgroundColor: col('--info'), tension: .3, borderDash: [5, 4] }] },
        options: { ...chartBase(), scales: { ...(chartBase().scales || {}), x: { ...((chartBase().scales || {}).x || {}), type: 'category' }, y: { ...((chartBase().scales || {}).y || {}), min: 0, max: 100 } } } });
    }).catch(() => {});
  }
  function rcGroup(v) { rc.group = v; report().catch(e => toast(staleMsg(e), 'error')); }

  // ─── Support inbox ───
  async function support() {
    const d = await api(`${BASE}/support?status=${rc.supStatus}`);
    if (!d || !Array.isArray(d.requests)) throw new Error(STALE);
    $('rc-tab').innerHTML = `
      <div class="rc-filters"><label class="an-field"><span>Show</span><select class="filter-select" onchange="rcSupF(this.value)">
        <option value="open" ${rc.supStatus === 'open' ? 'selected' : ''}>Open</option><option value="resolved" ${rc.supStatus === 'resolved' ? 'selected' : ''}>Resolved</option></select></label></div>
      ${d.requests.length ? d.requests.map(q => `<div class="rc-sup"><div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">
        <div><b>${esc(q.name || 'Student')}</b> <span class="rc-sub">${esc(q.email || '')} · ${esc(q.domain || '')}</span></div><span class="rc-sub">${rel(q.created_at)}</span></div>
        <div style="margin:8px 0"><span class="badge badge-pending">${esc((q.category || 'other').replace(/_/g, ' '))}</span></div>
        <div>${esc(q.message || 'No message')}</div>${q.admin_note ? `<div class="rc-sub" style="margin-top:6px">Note: ${esc(q.admin_note)}</div>` : ''}
        <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap"><button class="btn btn-secondary btn-sm" onclick="rcView(${q.student_id})">View student</button>
          <a class="btn btn-secondary btn-sm" href="mailto:${esc(q.email || '')}">Reply by email</a>
          ${q.status === 'open' ? `<button class="btn btn-primary btn-sm" onclick="rcResolve(${q.id}, this)">Mark resolved</button>` : `<button class="btn btn-ghost btn-sm" onclick="rcReopen(${q.id}, this)">Reopen</button>`}</div></div>`).join('')
        : `<div class="panel"><div class="panel-body">${empty(rc.supStatus === 'open' ? 'No open requests' : 'Nothing resolved yet', 'Students can ask for help from their dashboard.')}</div></div>`}`;
  }
  function rcSupF(v) { rc.supStatus = v; support().catch(e => toast(staleMsg(e), 'error')); }
  async function rcResolve(id, btn) {
    const note = window.prompt('Add a note for your team (optional):', '');
    if (note === null) return;
    const done = setBusy(btn, 'Saving…');
    try { await api(`${BASE}/support/${id}`, { method: 'PATCH', body: JSON.stringify({ status: 'resolved', admin_note: note || null }) });
      toast('Marked resolved'); rc.summary.support_open = Math.max(0, (rc.summary.support_open || 1) - 1); badge(); await support(); }
    catch (e) { toast(e.message, 'error'); done(); }
  }
  async function rcReopen(id, btn) {
    const done = setBusy(btn, 'Saving…');
    try { await api(`${BASE}/support/${id}`, { method: 'PATCH', body: JSON.stringify({ status: 'open' }) }); toast('Reopened'); rc.summary.support_open = (rc.summary.support_open || 0) + 1; badge(); await support(); }
    catch (e) { toast(e.message, 'error'); done(); }
  }

  Object.assign(window, { loadRecovery, rcSearch, rcTab: tab, rcCard, rcSetF, rcClearF, rcClearAll, rcSel, rcSelPage, rcSelAll, rcSelNone, rcPage, rcSend,
    rcConfirmSend, rcRunNow, rcView, rcSaveSettings, rcBackfill, rcLogF, rcLogPage, rcGroup, rcSupF, rcResolve, rcReopen });
})();
