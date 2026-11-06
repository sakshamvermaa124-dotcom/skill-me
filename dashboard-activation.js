/* SkillMe student dashboard: guided first-task and next-milestone card.
 * Purely additive. If the feature flag is off, the API is unavailable, or anything fails,
 * nothing is rendered and the dashboard behaves exactly as before. Reads /api/activation/me only;
 * it never changes tasks, submissions, payments or certificates. */
(function () {
  'use strict';
  var API = window.SKILLME_API || '';
  var state = { data: null, ctx: null, viewedSent: false, busy: false };

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]; }); }
  function headers(json) {
    var h = {}, t = localStorage.getItem('token');
    if (t) h.Authorization = 'Bearer ' + t;
    if (json) h['Content-Type'] = 'application/json';
    return h;
  }
  function slot() { return document.getElementById('activation-slot'); }

  async function fetchState() {
    var c = state.ctx;
    var q = 'student_id=' + encodeURIComponent(c.studentId) + (c.batchId ? '&batch_id=' + encodeURIComponent(c.batchId) : '');
    var r = await fetch(API + '/api/activation/me?' + q, { headers: headers(false), credentials: 'include' });
    if (!r.ok) return null;
    var d = await r.json();
    return d && d.enabled ? d : null;
  }

  async function refresh() {
    if (!state.ctx) return;
    try { state.data = await fetchState(); } catch (e) { state.data = null; }
    render();
  }

  window.renderActivation = function (data) {
    try {
      var student = data && data.student, prog = data && data.progress && data.progress[0];
      if (!student || !prog || !slot()) return;
      state.ctx = { studentId: student.id, batchId: prog.batch_id || null };
      state.viewedSent = false;
      refresh();
    } catch (e) { /* never affect the dashboard */ }
  };

  // ── Icons ──
  var ICON = {
    check: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>',
    clock: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>',
    arrow: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>',
    help: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7"/><line x1="12" y1="17" x2="12" y2="17.01"/></svg>'
  };

  function list(items) { return '<ul class="act-list">' + items.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>'; }

  function render() {
    var el = slot(), d = state.data;
    if (!el) return;
    if (!d || !d.stage || d.stage === 'completed') { el.innerHTML = ''; el.hidden = true; return; }
    el.hidden = false;
    if (d.first_task) el.innerHTML = firstTaskCard(d);
    else if (d.milestone) el.innerHTML = milestoneCard(d);
    else { el.innerHTML = ''; el.hidden = true; }
  }

  function helpLink(d) {
    return '<button type="button" class="act-link" onclick="actOpenHelp()">' + ICON.help + (d.support && d.support.open_request ? 'Help requested' : 'Need help?') + '</button>';
  }

  function firstTaskCard(d) {
    var ft = d.first_task, items = d.checklist || [], done = items.filter(function (i) { return i.done; }).length;
    var review = !!d.awaiting_review, pct = Math.round(done * 100 / Math.max(items.length, 1));
    var nextIdx = items.findIndex(function (i) { return !i.done; });
    var steps = items.map(function (i, n) {
      var cls = i.done ? 'is-done' : (n === nextIdx ? 'is-next' : '');
      return '<li class="act-step ' + cls + '"><span class="act-tick">' + (i.done ? ICON.check : (n + 1)) + '</span><span><b>' + esc(i.label) + '</b>' +
        (!i.done && i.hint ? '<small>' + esc(i.hint) + '</small>' : '') + '</span></li>';
    }).join('');
    var title = review ? 'Your first task is in review' : 'Start your first task';
    var eyebrow = review ? 'Nice work' : 'Get started · ' + done + ' of ' + items.length + ' done';
    var lead = review
      ? 'You submitted <b>' + esc(ft.title) + '</b>. We will email you when it is reviewed. You can fix and resubmit it from the Tasks tab if a change is requested.'
      : esc(ft.project_name) + ' · Week 1: <b>' + esc(ft.title) + '</b>';
    var cta = review
      ? '<button type="button" class="act-btn act-btn-ghost" onclick="dashShowPanel(\'panel-work\')">View my submission</button>'
      : '<button type="button" class="act-btn" onclick="actStart()">Start first task ' + ICON.arrow + '</button>';
    return '<div role="region" class="act-card" aria-labelledby="act-title">' +
      '<div class="act-main">' +
        '<p class="act-eyebrow">' + esc(eyebrow) + '</p>' +
        '<h2 class="act-title" id="act-title">' + title + '</h2>' +
        '<p class="act-lead">' + lead + '</p>' +
        '<div class="act-chips"><span class="act-chip">' + ICON.clock + esc(ft.time_label) + '</span><span class="act-chip">' + esc(ft.difficulty) + '</span></div>' +
        '<div class="act-actions">' + cta + helpLink(d) + '</div>' +
        (review ? '' :
          '<details class="act-more"><summary>What exactly do I submit?</summary>' +
            '<div class="act-cols"><div><h3>You will hand in</h3>' + list(ft.deliverables) + '</div>' +
            '<div><h3>Before you start</h3>' + list(ft.setup) + '</div></div>' +
            '<h3>How to submit</h3><ol class="act-ol">' + ft.submit_steps.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('') + '</ol>' +
            '<p class="act-note">' + esc(ft.review_note) + '</p></details>') +
      '</div>' +
      '<aside class="act-side" aria-label="Your progress">' +
        '<div class="act-bar" role="progressbar" aria-valuenow="' + pct + '" aria-valuemin="0" aria-valuemax="100"><i style="width:' + pct + '%"></i></div>' +
        '<ol class="act-steps">' + steps + '</ol></aside></div>';
  }

  function milestoneCard(d) {
    var m = d.milestone, approved = d.approved_weeks || [];
    var segs = [1, 2, 3, 4].map(function (w) {
      return '<i class="' + (approved.indexOf(w) >= 0 ? 'is-done' : (w === m.next_week ? 'is-next' : '')) + '" title="Week ' + w + '"></i>';
    }).join('');
    var cta = m.already_submitted
      ? '<button type="button" class="act-btn act-btn-ghost" onclick="dashShowPanel(\'panel-work\')">View Week ' + m.next_week + ' submission</button>'
      : '<button type="button" class="act-btn" onclick="actContinue(' + m.next_week + ')">Continue with Week ' + m.next_week + ' ' + ICON.arrow + '</button>';
    return '<div role="region" class="act-card act-card-ms" aria-labelledby="act-title">' +
      '<div class="act-main"><p class="act-eyebrow">Next milestone · ' + approved.length + ' of 4 weeks approved</p>' +
        '<h2 class="act-title" id="act-title">' + (m.already_submitted ? 'Week ' + m.next_week + ' is in review' : 'Week ' + m.last_approved + ' approved. On to Week ' + m.next_week) + '</h2>' +
        '<p class="act-lead">' + (m.already_submitted ? 'We will email you when it is reviewed.' : 'Up next: <b>' + esc(m.next_title) + '</b>') + '</p>' +
        '<div class="act-chips"><span class="act-chip">' + ICON.clock + esc(m.time_label) + '</span><span class="act-chip">' + m.remaining + ' week' + (m.remaining === 1 ? '' : 's') + ' left</span></div>' +
        (m.already_submitted || !m.deliverables.length ? '' : '<h3 class="act-h3">Week ' + m.next_week + ' asks for</h3>' + list(m.deliverables.slice(0, 3))) +
        '<div class="act-actions">' + cta + helpLink(d) + '</div></div>' +
      '<aside class="act-side"><div class="act-segs" role="img" aria-label="' + approved.length + ' of 4 weeks approved">' + segs + '</div>' +
        '<p class="act-side-t">' + approved.length + ' of 4 approved</p></aside></div>';
  }

  // ── Actions ──
  function recordViewed() {
    var d = state.data, c = state.ctx;
    if (state.viewedSent || !d || !d.checklist || d.stage !== 'no_first_task') return;
    state.viewedSent = true;
    fetch(API + '/api/activation/events', { method: 'POST', headers: headers(true), credentials: 'include',
      body: JSON.stringify({ student_id: c.studentId, batch_id: c.batchId, event: 'first_task_viewed' }) })
      .then(function () { if (d.checklist[1]) d.checklist[1].done = true; render(); })
      .catch(function () { state.viewedSent = false; });
  }
  window.actStart = function () { if (window.dashOpenWeek) window.dashOpenWeek(1); else if (window.dashShowPanel) window.dashShowPanel('panel-work'); recordViewed(); };
  window.actContinue = function (w) { if (window.dashOpenWeek) window.dashOpenWeek(w); else if (window.dashShowPanel) window.dashShowPanel('panel-work'); };

  // Opening the Tasks tab by any route counts as having looked at the brief.
  function wrapOnce(name, after) {
    var orig = window[name];
    if (typeof orig !== 'function' || orig.__act) return;
    var wrapped = function () { var r = orig.apply(this, arguments); try { after.apply(null, arguments); } catch (e) { /* ignore */ } return r; };
    wrapped.__act = true; window[name] = wrapped;
  }
  function install() {
    wrapOnce('dashShowPanel', function (id) { if (id === 'panel-work') recordViewed(); });
    var orig = window.submitTaskForReview;
    if (typeof orig === 'function' && !orig.__act) {
      var w = async function () { var r = await orig.apply(this, arguments); setTimeout(refresh, 700); return r; };
      w.__act = true; window.submitTaskForReview = w;
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install); else install();
  window.addEventListener('load', install);

  // ── Help dialog ──
  var CATS = [['stuck_on_task', 'I am stuck on the task'], ['login_access', 'I cannot log in or reach my dashboard'], ['submission_problem', 'My submission is not working'], ['other', 'Something else']];
  window.actOpenHelp = function () {
    var dlg = document.getElementById('act-help');
    if (!dlg) { dlg = document.createElement('dialog'); dlg.id = 'act-help'; dlg.className = 'act-dialog'; document.body.appendChild(dlg); }
    var sent = state.data && state.data.support && state.data.support.open_request;
    dlg.innerHTML = '<form method="dialog" class="act-form" id="act-help-form"><h2>How can we help?</h2>' +
      (sent ? '<p class="act-note">You already have an open request. Our team will reply by email. You can add more details below.</p>' : '<p class="act-note">Tell us where you are stuck. A real person will email you back.</p>') +
      '<fieldset>' + CATS.map(function (c, i) { return '<label class="act-radio"><input type="radio" name="cat" value="' + c[0] + '"' + (i === 0 ? ' checked' : '') + '> ' + c[1] + '</label>'; }).join('') + '</fieldset>' +
      '<label class="act-field">Details (optional)<textarea name="msg" rows="4" maxlength="1000" placeholder="What did you try? What did you see?"></textarea></label>' +
      '<p class="act-err" id="act-help-err" role="alert" hidden></p>' +
      '<div class="act-form-actions"><button type="button" class="act-btn act-btn-ghost" onclick="document.getElementById(\'act-help\').close()">Cancel</button><button type="submit" class="act-btn" id="act-help-send">Send request</button></div></form>';
    dlg.querySelector('form').addEventListener('submit', function (ev) { ev.preventDefault(); sendHelp(dlg); });
    if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open', '');
  };
  async function sendHelp(dlg) {
    var f = dlg.querySelector('form'), btn = dlg.querySelector('#act-help-send'), err = dlg.querySelector('#act-help-err');
    var body = { student_id: state.ctx.studentId, batch_id: state.ctx.batchId, category: f.cat.value, message: f.msg.value };
    btn.disabled = true; btn.textContent = 'Sending…'; err.hidden = true;
    try {
      var r = await fetch(API + '/api/activation/support', { method: 'POST', headers: headers(true), credentials: 'include', body: JSON.stringify(body) });
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok) throw new Error(j.detail || 'Could not send your request. Please try again.');
      dlg.innerHTML = '<div class="act-form"><h2>Request received</h2><p class="act-note">' + esc(j.message || 'Our team will email you shortly.') + '</p><div class="act-form-actions"><button type="button" class="act-btn" onclick="document.getElementById(\'act-help\').close()">Done</button></div></div>';
      if (state.data) { state.data.support = state.data.support || {}; state.data.support.open_request = true; render(); }
    } catch (e) { err.textContent = e.message; err.hidden = false; btn.disabled = false; btn.textContent = 'Send request'; }
  }
})();
