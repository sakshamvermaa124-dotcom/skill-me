// SkillMe admin console: Analytics page.
// Loaded with defer AFTER admin.js and uses its shared helpers (api, esc, jsArg, toast, openModal,
// closeModal, fmtINR, fmtDate, cssColor, ensureChartJs, _drawChart, chartBase, analyticsCard).
// Every number comes from GET /api/admin/analytics, which is computed by ONE per-student rollup on the
// server (backend/services/analytics_service.py), so tabs and drill-downs always agree.

const an = {
  tab: 'overview',
  f: { range: 'all', from: '', to: '', domain: '', source: '', campaign: '', test: false },
  data: null, quality: null, payments: null,
  inactiveDays: 7, payStatus: '', payPage: 1, payQ: '',
  drill: { stage: '', title: '', page: 1, q: '' },
  req: 0,
};

const AN_TABS = ['overview', 'funnel', 'acquisition', 'domains', 'payments', 'engagement', 'quality'];
const num = n => Number(n || 0).toLocaleString('en-IN');
const pctTxt = v => (v === null || v === undefined) ? '—' : `${v}%`;
const dayTxt = v => (v === null || v === undefined) ? '—' : `${v}d`;

// ─── Filters ───────────────────────────────────────────────────────────────
function anIstToday() { return new Date(Date.now() + 5.5 * 3600 * 1000); }
function anIstDate(daysAgo) {
  const d = anIstToday();
  d.setUTCDate(d.getUTCDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}

function anReadFilters() {
  const v = id => (document.getElementById(id) || {}).value || '';
  an.f.range = v('an-range') || 'all';
  an.f.domain = v('an-domain');
  an.f.source = v('an-source');
  an.f.campaign = v('an-campaign');
  an.f.test = !!(document.getElementById('an-test') || {}).checked;
  if (an.f.range === 'custom') { an.f.from = v('an-from'); an.f.to = v('an-to'); }
  else if (an.f.range === 'all') { an.f.from = ''; an.f.to = ''; }
  else { an.f.from = anIstDate(Number(an.f.range) - 1); an.f.to = anIstDate(0); }
}

function anQuery(extra = {}) {
  const p = new URLSearchParams();
  if (an.f.from) p.set('from', an.f.from);
  if (an.f.to) p.set('to', an.f.to);
  if (an.f.domain) p.set('domain', an.f.domain);
  if (an.f.source) p.set('source', an.f.source);
  if (an.f.campaign) p.set('campaign', an.f.campaign);
  if (an.f.test) p.set('include_test', 'true');
  Object.entries(extra).forEach(([k, v]) => { if (v !== '' && v !== null && v !== undefined) p.set(k, v); });
  return p.toString();
}

function anSetRange(value) {
  document.getElementById('an-custom').style.display = value === 'custom' ? 'inline-flex' : 'none';
  if (value !== 'custom') anApplyFilters();
}

function anApplyFilters() { anReadFilters(); an.quality = null; loadAnalytics(); }

function anSetFilter(key, value) {
  // Row click in Acquisition/Domains narrows the whole page to that slice.
  const el = document.getElementById({ domain: 'an-domain', source: 'an-source', campaign: 'an-campaign' }[key]);
  if (el) el.value = value;
  anApplyFilters();
}

function anFillSelect(id, options, allLabel) {
  const el = document.getElementById(id);
  if (!el) return;
  const keep = el.value;
  el.innerHTML = `<option value="">${esc(allLabel)}</option>` +
    options.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join('');
  if (keep && options.some(([v]) => v === keep)) el.value = keep;
}

// ─── Loading ───────────────────────────────────────────────────────────────
async function loadAnalytics(fresh = false) {
  const body = document.getElementById('an-body');
  if (!body) return;
  anReadFilters();
  const reqId = ++an.req;
  try {
    const [data] = await Promise.all([
      api(`/api/admin/analytics?${anQuery({ fresh: fresh === true ? 'true' : '', inactive_days: an.inactiveDays })}`),
      ensureChartJs(),
    ]);
    if (reqId !== an.req) return;
    // The frontend (Vercel) and backend (Cloud Run) deploy separately. An older backend returns
    // the previous response shape, so say that plainly instead of failing on a missing field.
    if (!data || !data.overview || !data.funnel || !data.funnel.learning) {
      throw new Error('The backend is still running the previous version. Deploy the latest backend to Cloud Run, then press Refresh.');
    }
    an.data = data;
    if (fresh === true) { an.quality = null; an.payments = null; }
    const o = data.options || {};
    anFillSelect('an-domain', (o.domains || []).map(([k, l]) => [k, l]), 'All tracks');
    anFillSelect('an-source', (o.sources || []).map(s => [s, s]), 'All sources');
    anFillSelect('an-campaign', (o.campaigns || []).map(s => [s, s]), 'All campaigns');
    anScopeNote();
    anQualityBadge();
    anRender();
  } catch (e) {
    if (reqId !== an.req) return;
    body.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><div class="empty-state-text">${esc(e.message)}</div></div>`;
  }
}

function anScopeNote() {
  const d = an.data, f = d.filters || {};
  const range = f.date_from || f.date_to ? `applied ${esc(f.date_from || '…')} to ${esc(f.date_to || 'today')} (IST)` : 'all applications';
  const bits = [range, f.domain && `track: ${esc(f.domain)}`, f.source && `source: ${esc(f.source)}`,
    f.campaign && `campaign: ${esc(f.campaign)}`, f.include_test ? 'INCLUDING test data' : 'test accounts and test payments excluded'].filter(Boolean);
  document.getElementById('an-scope-note').innerHTML =
    `Cohort: ${bits.join(' · ')} · ${num(d.overview.applicants)} applicants · updated ${esc(f.generated_at || '')}. ` +
    `The date range filters by <b>application date</b> and applies to every tab.`;
}

function anQualityBadge() {
  const n = (an.data.validation || []).filter(w => w.level === 'error' || w.level === 'warning').length;
  const el = document.getElementById('an-quality-count');
  if (!el) return;
  el.hidden = !n;
  el.textContent = n;
}

function anTab(tab) {
  an.tab = tab;
  document.querySelectorAll('#an-tabs .an-tab').forEach(b => {
    const on = b.dataset.tab === tab;
    b.classList.toggle('active', on);
    b.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  if (an.data) anRender();
}

async function anRender() {
  Object.keys(_analyticsCharts).forEach(k => { _analyticsCharts[k].destroy(); delete _analyticsCharts[k]; });
  const body = document.getElementById('an-body');
  const d = an.data;
  const views = {
    overview: anOverview, funnel: anFunnel, acquisition: anAcquisition, domains: anDomains,
    payments: anPayments, engagement: anEngagement, quality: anQuality,
  };
  body.innerHTML = '';
  const out = await views[an.tab](d);
  if (typeof out === 'string') body.innerHTML = out;
  anCharts();
}

// ─── Small building blocks ────────────────────────────────────────────────
function anDef(key) { return esc((an.data.definitions || {})[key] || ''); }

function anCard(icon, value, label, sub, stage, defKey) {
  const click = stage ? ` onclick="anDrill(${jsArg(stage)}, ${jsArg(label)})" role="button" tabindex="0" onkeydown="if(event.key==='Enter')this.click()"` : '';
  return `<div class="stat-card ${stage ? 'an-click' : ''}" title="${anDef(defKey)}"${click}>
    <div class="stat-card-top"><div class="stat-card-label">${esc(label)}</div><div class="stat-card-icon">${icon}</div></div>
    <div class="stat-card-value">${typeof value === 'number' ? num(value) : value}</div>
    ${sub ? `<div class="stat-card-sub">${sub}</div>` : ''}</div>`;
}

function anPanel(title, subtitle, inner, extra = '') {
  return `<div class="panel" ${extra}><div class="panel-header"><div><div class="panel-title">${title}</div>
    ${subtitle ? `<div class="panel-subtitle">${subtitle}</div>` : ''}</div></div>
    <div class="panel-body" style="max-height:none;">${inner}</div></div>`;
}

function anTable(head, rows, empty = 'Nothing to show.') {
  if (!rows.length) return `<div class="empty-state" style="padding:24px;"><div class="empty-state-text">${esc(empty)}</div></div>`;
  return `<div class="table-wrap"><table><thead><tr>${head.map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
}

const anCanvas = (id, h = 240) => `<div style="position:relative;height:${h}px;"><canvas id="${id}"></canvas></div>`;
const anGrid = (cols, inner, mt = 20) => `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(${cols}px,100%),1fr));gap:20px;margin-top:${mt}px;">${inner}</div>`;
const anCards = inner => `<div class="stats-grid">${inner}</div>`;

let _anChartQueue = [];
function anQueueChart(id, cfg) { _anChartQueue.push([id, cfg]); }
function anCharts() { const q = _anChartQueue; _anChartQueue = []; q.forEach(([id, cfg]) => _drawChart(id, cfg)); }

const anBarOpts = (extra = {}) => ({ ...chartBase(), ...extra });
const C = () => ({ primary: cssColor('--primary'), ok: cssColor('--ok'), info: cssColor('--info'), warn: cssColor('--warn'),
  danger: cssColor('--danger'), violet: cssColor('--violet'), muted: cssColor('--text-3') });

// ─── Overview ──────────────────────────────────────────────────────────────
function anOverview(d) {
  const o = d.overview, g = d.growth, t = d.engagement.task_level;
  const warns = (d.validation || []).filter(w => w.level === 'error' || w.level === 'warning');
  const strip = warns.length
    ? `<div class="panel" style="margin-bottom:20px;border-color:var(--warn-line);"><div class="panel-body" style="max-height:none;">
        ⚠️ <b>${warns.length} metric check${warns.length > 1 ? 's' : ''} need attention.</b>
        ${warns.map(w => `<div style="font-size:0.82rem;margin-top:6px;">${esc(w.message)}</div>`).join('')}
        <button class="btn btn-secondary" style="margin-top:10px;font-size:0.78rem;" onclick="anTab('quality')">Open Data quality</button></div></div>`
    : '';
  const certSub = `${num(d.payments.lifecycle.paid)} after real payment · rest are early, admin-issued or test-linked`;
  anQueueChart('chart-an-monthly', { type: 'bar', data: { labels: g.monthly_applications.map(m => _monthLabel(m.month)),
    datasets: [{ label: 'Applications', data: g.monthly_applications.map(m => m.count), backgroundColor: C().primary, borderRadius: 4 }] },
    options: anBarOpts({ plugins: { legend: { display: false } } }) });
  const wk = d.engagement.weekly;
  anQueueChart('chart-an-weekly', { type: 'bar', data: { labels: wk.map(w => `Week ${w.week}`),
    datasets: [{ label: 'Students who submitted', data: wk.map(w => w.students_reached), backgroundColor: C().info, borderRadius: 4 },
               { label: 'Students approved', data: wk.map(w => w.students_approved), backgroundColor: C().ok, borderRadius: 4 }] }, options: anBarOpts() });
  return strip +
    anCards(
      anCard('📝', o.applicants, 'Applicants', `${num(o.unique_people)} unique people`, 'applied', 'applicant') +
      anCard('🤝', o.enrolled, 'Enrolled students', `${pctTxt(d.funnel.learning[1].pct_of_top)} of applicants`, 'enrolled', 'enrolled') +
      anCard('⚡', o.active_7d, 'Active students (7 days)', 'signed in or submitted a task', '', 'started') +
      anCard('🏁', o.completed, 'Completed (4/4 weeks)', 'students, not submissions', 'completed', 'completed') +
      anCard('🎓', o.certificates, 'Certificates issued', certSub, 'certified_any', 'certificate') +
      anCard('💳', o.paying_students, 'Paying students', 'real payments only', 'paid_any', 'paid') +
      anCard('💰', fmtINR(o.revenue_rupees), 'Revenue', `test payments excluded: ${fmtINR(d.payments.excluded_test.rupees)}`, '', 'paid') +
      anCard('🎯', o.eligible_unpaid, 'Eligible but unpaid', '3+ weeks approved, no payment yet', 'eligible_unpaid', 'eligible')) +
    anGrid(420, anPanel('Applications per month', 'IST, by application date', anCanvas('chart-an-monthly')) +
      anPanel('Weekly progress (students)', 'Student-level: each student counted once per week', anCanvas('chart-an-weekly'))) +
    `<div class="an-unit">Task-level (not students): ${num(t.approved_submissions)} approved, ${num(t.rejected_submissions)} rejected, ${num(t.pending_submissions)} pending <b>submissions</b>.
      One student can have up to 4 approved submissions, so this is never comparable to the student counts above.</div>`;
}

// ─── Funnel ────────────────────────────────────────────────────────────────
function anBars(rows, stagePrefix) {
  return rows.map(r => `<div class="an-bar-row an-click" role="button" tabindex="0" title="${anDef(r.key === 'started' ? 'started' : r.key === 'completed' ? 'completed' : '')}"
      onclick="anDrill(${jsArg(r.key)}, ${jsArg(r.label)})" onkeydown="if(event.key==='Enter')this.click()">
      <div style="font-weight:600;font-size:0.85rem;">${esc(r.label)}</div>
      <div class="an-bar-track"><div class="an-bar-fill" style="width:${Math.max(0, Math.min(100, r.pct_of_top))}%"></div></div>
      <div class="an-bar-meta"><b style="color:var(--text);">${num(r.count)}</b> · ${pctTxt(r.pct_of_top)} of top${r.drop_off === null ? '' :
        `<br>step ${pctTxt(r.step_conversion)} · <span style="color:var(--danger);">−${num(r.drop_off)} (${pctTxt(r.drop_off_pct)})</span>`}</div></div>`).join('');
}

function anFunnel(d) {
  const f = d.funnel;
  const rows = f.timings.map(t => `<tr><td>${esc(t.from)} → <b>${esc(t.to)}</b></td><td>${dayTxt(t.median_days)}</td><td>${dayTxt(t.p90_days)}</td><td>${num(t.n)}</td></tr>`);
  return anPanel('Learning funnel', 'Students reaching each stage. Click a stage to see exactly which students. Drop-off = students lost since the previous stage.', anBars(f.learning)) +
    `<div style="height:20px"></div>` +
    anPanel('Payment funnel', 'Among students eligible for payment (3 of 4 weeks approved, or unlocked by an admin). Kept separate because certificates are issued at payment, before 4/4 completion.', anBars(f.revenue)) +
    `<div style="height:20px"></div>` +
    anPanel('Time between stages', 'Each row names its start point, so two "first task" figures can no longer conflict. Medians of students who reached both stages.',
      anTable(['From → To', 'Median', '90th percentile', 'Students'], rows));
}

// ─── Acquisition ───────────────────────────────────────────────────────────
function anAcqTable(rows, filterKey, nameLabel = 'Source') {
  return anTable([nameLabel, 'Applications', 'Activated', 'Completed', 'Paid', 'Revenue', 'Paid %'],
    rows.map(r => `<tr class="${filterKey ? 'an-click' : ''}" ${filterKey ? `onclick="anSetFilter(${jsArg(filterKey)}, ${jsArg(r.key)})" title="Filter the whole page to this ${esc(filterKey)}"` : ''}>
      <td style="font-weight:600;">${esc(r.label)}</td><td>${num(r.applications)}</td><td>${num(r.activated)} <span class="an-bar-meta">${pctTxt(r.activation_rate)}</span></td>
      <td>${num(r.completed)} <span class="an-bar-meta">${pctTxt(r.completion_rate)}</span></td><td>${num(r.paid)}</td><td>${fmtINR(r.revenue_rupees)}</td><td>${pctTxt(r.paid_rate)}</td></tr>`),
    'No data for this selection.');
}

function anAcquisition(d) {
  const a = d.acquisition, cov = a.coverage, au = d.audience;
  const src = a.sources.slice(0, 10);
  anQueueChart('chart-an-source', { type: 'bar', data: { labels: src.map(s => s.label),
    datasets: [{ label: 'Applications', data: src.map(s => s.applications), backgroundColor: C().info, borderRadius: 4 },
               { label: 'Activated', data: src.map(s => s.activated), backgroundColor: C().warn, borderRadius: 4 },
               { label: 'Completed', data: src.map(s => s.completed), backgroundColor: C().ok, borderRadius: 4 },
               { label: 'Paid', data: src.map(s => s.paid), backgroundColor: C().primary, borderRadius: 4 }] }, options: anBarOpts() });
  const banner = cov.pre_tracking_unknown
    ? `<div class="panel" style="margin-bottom:20px;border-color:var(--info-line);"><div class="panel-body" style="max-height:none;font-size:0.85rem;">
        ℹ️ <b>${num(cov.pre_tracking_unknown)} of ${num(cov.total)} applicants (${pctTxt(100 - cov.tracked_pct)})</b> applied before source tracking existed.
        Their real source cannot be recovered, so they appear as <b>unknown (pre-tracking)</b>, not guessed. New applications are tracked
        (UTM, referrer, landing page, first and last touch); ${num(cov.tracked)} so far.</div></div>` : '';
  const ref = a.referrals || {};
  const quiz = au.quiz_bands.map(q => `<tr><td style="font-weight:600;">${esc(q.key)}</td><td>${num(q.applications)}</td><td>${pctTxt(q.completion_rate)}</td><td>${pctTxt(q.paid_rate)}</td></tr>`);
  const cols = au.colleges.map(c => `<tr><td>${esc(c.label)}</td><td>${num(c.applications)}</td><td>${num(c.completed)}</td><td>${num(c.paid)}</td></tr>`);
  const yrs = au.years.map(c => `<tr><td>${esc(c.label)}</td><td>${num(c.applications)}</td><td>${num(c.completed)}</td><td>${num(c.paid)}</td></tr>`);
  return banner +
    anPanel('Applications to paid, by first-touch source', 'Click a row to filter the whole dashboard to that source.', anCanvas('chart-an-source', 260) + '<div style="height:14px"></div>' + anAcqTable(a.sources, 'source')) +
    anGrid(480, anPanel('Campaigns', 'source / utm_campaign (first touch)', anAcqTable(a.campaigns, '', 'Source / campaign')) +
      anPanel('What applicants said (self-reported)', 'The "how did you hear about us" answer. Kept separate from tracked source.', anAcqTable(a.self_reported, '', 'Answer'))) +
    anGrid(320, anPanel('Referral program', 'From referral_conversions', `<div style="font-size:0.9rem;">Clicked ${num(ref.clicked)} · Applied ${num(ref.applied)} · Enrolled ${num(ref.enrolled)}</div>`) +
      anPanel('Quiz score bands', '', anTable(['Band', 'Applicants', 'Completion', 'Paid'], quiz)) +
      anPanel('Top colleges', '', anTable(['College', 'Applicants', 'Completed', 'Paid'], cols, 'No college data.')) +
      anPanel('Year of study', '', anTable(['Year', 'Applicants', 'Completed', 'Paid'], yrs, 'No data.')));
}

// ─── Domains ───────────────────────────────────────────────────────────────
function anDomains(d) {
  const ds = d.domains;
  anQueueChart('chart-an-domains', { type: 'bar', data: { labels: ds.map(x => x.label),
    datasets: [{ label: 'Applications', data: ds.map(x => x.applications), backgroundColor: C().info, borderRadius: 4 },
               { label: 'First task', data: ds.map(x => x.first_task), backgroundColor: C().warn, borderRadius: 4 },
               { label: 'Completed', data: ds.map(x => x.completed), backgroundColor: C().ok, borderRadius: 4 },
               { label: 'Paid', data: ds.map(x => x.paid), backgroundColor: C().primary, borderRadius: 4 }] }, options: anBarOpts() });
  const perf = ds.map(x => `<tr class="an-click" onclick="anSetFilter('domain', ${jsArg(x.key)})" title="Filter the whole page to this track">
    <td style="font-weight:600;">${esc(x.label)}</td><td>${num(x.applications)}</td><td>${num(x.activated)}</td><td>${num(x.first_task)}</td>
    <td>${num(x.completed)} <span class="an-bar-meta">${pctTxt(x.completed_of_started_pct)} of started</span></td>
    <td>${num(x.certified)}${x.certified_not_completed ? ` <span class="an-bar-meta" title="Certificates held by students who have not completed 4/4 (3-of-4 payment rule or admin issue)">(${x.certified_not_completed} before 4/4)</span>` : ''}</td>
    <td>${num(x.paid)}</td><td>${fmtINR(x.revenue_rupees)}</td></tr>`);
  const ret = ds.map(x => `<tr><td style="font-weight:600;">${esc(x.label)}</td>${x.retention.map(r => `<td>${num(r.reached)} <span class="an-bar-meta">${pctTxt(r.pct_of_week1)}</span></td>`).join('')}</tr>`);
  return anPanel('Track performance', 'Applications, activation (signed in), first task, completion, certificates and revenue. Certified can exceed Completed because certificates are issued at payment, after 3 of 4 weeks.',
      anCanvas('chart-an-domains', 280) + '<div style="height:14px"></div>' +
      anTable(['Track', 'Applications', 'Activated', 'First task', 'Completed (4/4)', 'Certificates', 'Paid', 'Revenue'], perf, 'No applications.')) +
    '<div style="height:20px"></div>' +
    anPanel('Retention by week', 'Students who submitted each week, and % of those who submitted week 1', anTable(['Track', 'Week 1', 'Week 2', 'Week 3', 'Week 4'], ret));
}

// ─── Payments ──────────────────────────────────────────────────────────────
function anRecoveryTable(rows, empty) {
  return anTable(['Student', 'Track', 'Weeks', 'Orders', 'Last order', 'Detail', ''],
    rows.map(r => `<tr><td><b>${esc(r.name)}</b><br><a href="mailto:${esc(r.email)}" style="font-size:0.75rem;color:var(--text-3);">${esc(r.email)}</a></td>
      <td>${esc(r.domain)}</td><td>${r.weeks_approved}/4</td><td>${r.orders}</td><td>${esc((r.last_order_at || '—').slice(0, 10))}</td>
      <td style="font-size:0.78rem;">${r.failure_reason ? esc(r.failure_reason) : r.legacy ? '<span class="an-bar-meta">legacy: outcome unknown</span>' : r.unlocked_by_admin ? 'unlocked by admin' : ''}</td>
      <td><button class="btn btn-secondary" style="font-size:0.72rem;padding:3px 10px;" onclick="anJourney(${r.student_id})">Journey</button></td></tr>`), empty);
}

async function anPayments(d) {
  const p = d.payments, l = p.lifecycle, r = p.revenue;
  const trend = r.trend;
  anQueueChart('chart-an-revenue', { type: 'bar', data: { labels: trend.map(m => _monthLabel(m.month)),
    datasets: [{ label: 'Revenue (₹)', data: trend.map(m => m.revenue_rupees), backgroundColor: C().ok, borderRadius: 4 }] },
    options: anBarOpts({ plugins: { legend: { display: false } } }) });
  anQueueChart('chart-an-paystate', { type: 'bar', data: { labels: ['Eligible', 'Checkout initiated', 'Pending', 'Paid', 'Failed', 'Abandoned'],
    datasets: [{ data: [l.eligible, l.checkout_initiated, l.pending, l.paid, l.failed, l.abandoned],
      backgroundColor: [C().info, C().violet, C().warn, C().ok, C().danger, C().muted], borderRadius: 4 }] },
    options: anBarOpts({ plugins: { legend: { display: false } } }) });
  const tiers = r.tiers.map(t => `<span class="chip-stat"><b>${fmtINR(t.price_rupees)}</b> × ${t.orders} = ${fmtINR(t.revenue_rupees)}</span>`).join('') || '<span class="an-bar-meta">No paid orders.</span>';
  const tx = await anLoadPayments();
  return anCards(
      anCard('🎯', l.eligible, 'Eligible for payment', '3+ weeks approved or unlocked', 'eligible', 'eligible') +
      anCard('🔔', l.eligible_unpaid, 'Eligible, unpaid', `${num(l.eligible_never_started_checkout)} never opened checkout`, 'eligible_unpaid', 'eligible') +
      anCard('🛒', l.checkout_initiated, 'Checkout initiated', 'students with a real order', '', 'checkout_initiated') +
      anCard('⏳', l.pending, 'Pending', 'attempted, not confirmed yet', 'pay_pending', 'pending') +
      anCard('✅', l.paid, 'Paid', `${fmtINR(r.total_rupees)} collected`, 'paid_any', 'paid') +
      anCard('❌', l.failed, 'Failed', 'a failure reason is stored when reported', 'pay_failed', 'failed') +
      anCard('🚪', l.abandoned, 'Abandoned', l.abandoned_legacy_unknown ? `${num(l.abandoned_legacy_unknown)} are legacy orders with unknown outcome` : 'checkout opened, never paid', 'pay_abandoned', 'abandoned')) +
    anGrid(420, anPanel('Payment lifecycle', 'Students by state', anCanvas('chart-an-paystate')) +
      anPanel('Revenue by payment month', esc(r.paid_date_note), `<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">${tiers}</div>` + anCanvas('chart-an-revenue', 170) +
        `<div class="an-unit">Excluded as test: ${num(p.excluded_test.paid_orders)} paid order(s) worth ${fmtINR(p.excluded_test.rupees)} (flagged test or seeded ids). They are kept in the database, never counted as revenue.</div>`)) +
    '<div style="height:20px"></div>' +
    anPanel('Recover: eligible but unpaid', 'Highest approved weeks first', anRecoveryTable(p.recovery.eligible_unpaid, 'Everyone eligible has paid.')) +
    '<div style="height:20px"></div>' +
    anPanel('Recover: abandoned checkouts', 'Opened checkout, never paid', anRecoveryTable(p.recovery.abandoned, 'No abandoned checkouts.')) +
    '<div style="height:20px"></div>' +
    anPanel('Failed payments', '', anRecoveryTable(p.recovery.failed, 'No failed payments recorded.')) +
    '<div style="height:20px"></div>' + tx;
}

async function anLoadPayments() {
  const q = new URLSearchParams({ page: an.payPage, limit: 15 });
  if (an.payStatus) q.set('status', an.payStatus);
  if (an.payQ) q.set('q', an.payQ);
  let res;
  try { res = await api(`/api/admin/payments?${q}`); } catch (e) { return anPanel('Transactions', '', `<div class="an-note">${esc(e.message)}</div>`); }
  const statuses = ['', 'paid', 'pending', 'created', 'failed', 'abandoned', 'test'];
  const rows = res.payments.map(x => `<tr>
    <td>${x.id}</td><td><b>${esc(x.student_name || '—')}</b><br><span class="an-bar-meta">${esc(x.email || '')}</span></td>
    <td class="an-bar-meta">${esc(x.razorpay_order_id || '')}<br>${esc(x.razorpay_payment_id || '—')}</td>
    <td>${fmtINR((x.amount || 0) / 100)}${x.discount_code ? `<br><span class="an-bar-meta">${esc(x.discount_code)}</span>` : ''}</td>
    <td><span class="badge badge-${x.lifecycle === 'paid' ? 'approved' : x.lifecycle === 'failed' ? 'rejected' : 'pending'}">${esc(x.lifecycle)}</span>${x.is_test ? ' <span class="an-sev an-sev-info">test</span>' : ''}${x.legacy ? ' <span class="an-bar-meta">legacy</span>' : ''}</td>
    <td class="an-bar-meta">${esc((x.initiated_at || x.created_at || '').slice(0, 16))}<br>${esc((x.paid_at || '').slice(0, 16) || '—')}</td>
    <td style="font-size:0.78rem;">${esc(x.failure_reason || '')}${x.confirmed_via ? `<span class="an-bar-meta">via ${esc(x.confirmed_via)}</span>` : ''}</td>
    <td><button class="btn btn-secondary" style="font-size:0.7rem;padding:2px 8px;" onclick="anFlagPayment(${x.id}, ${x.is_test ? 'false' : 'true'})">${x.is_test ? 'Mark real' : 'Mark test'}</button></td></tr>`);
  const controls = `<div class="filter-row" style="margin-bottom:12px;">
    <select class="filter-select" onchange="an.payStatus=this.value;an.payPage=1;anRender()" aria-label="Payment status">
      ${statuses.map(s => `<option value="${s}" ${s === an.payStatus ? 'selected' : ''}>${s ? s[0].toUpperCase() + s.slice(1) : 'All orders'}</option>`).join('')}</select>
    <input class="search-input" placeholder="Search name, email, order or payment id" value="${esc(an.payQ)}" onchange="an.payQ=this.value;an.payPage=1;anRender()"></div>`;
  return anPanel('Transactions', 'Order-level lifecycle: initiated → pending → paid / failed. Abandoned is derived from age.', controls +
    anTable(['#', 'Student', 'Order / payment id', 'Amount', 'Status', 'Initiated / paid', 'Detail', ''], rows, 'No payments match.') + anPager(res, 'an.payPage'));
}

async function anFlagPayment(id, flag) {
  try { await api(`/api/admin/payments/${id}/test-flag`, { method: 'PATCH', body: JSON.stringify({ is_test: flag }) }); toast(flag ? 'Payment marked as test' : 'Payment marked as real'); loadAnalytics(true); }
  catch (e) { toast(e.message, 'error'); }
}

function anPager(res, stateExpr) {
  if (!res || res.total_pages <= 1) return `<div class="an-unit">${num(res ? res.total : 0)} total</div>`;
  const go = p => `${stateExpr}=${p};${stateExpr.startsWith('an.drill') ? 'anLoadDrill()' : 'anRender()'}`;
  return `<div style="display:flex;gap:10px;align-items:center;justify-content:flex-end;margin-top:12px;font-size:0.8rem;">
    <button class="btn btn-secondary" style="padding:3px 10px;" ${res.page <= 1 ? 'disabled' : ''} onclick="${go(res.page - 1)}">‹ Prev</button>
    <span>Page ${res.page} of ${res.total_pages} · ${num(res.total)} total</span>
    <button class="btn btn-secondary" style="padding:3px 10px;" ${res.page >= res.total_pages ? 'disabled' : ''} onclick="${go(res.page + 1)}">Next ›</button></div>`;
}

// ─── Engagement ────────────────────────────────────────────────────────────
function anEngagement(d) {
  const e = d.engagement, rw = e.review_wait;
  anQueueChart('chart-an-eng', { type: 'bar', data: { labels: e.weekly.map(w => `Week ${w.week}`),
    datasets: [{ label: 'Students submitted', data: e.weekly.map(w => w.students_reached), backgroundColor: C().info, borderRadius: 4 },
               { label: 'Students approved', data: e.weekly.map(w => w.students_approved), backgroundColor: C().ok, borderRadius: 4 }] }, options: anBarOpts() });
  const wk = e.weekly.map(w => `<tr><td style="font-weight:600;">Week ${w.week}</td><td>${num(w.students_reached)}</td><td style="color:var(--ok);">${num(w.students_approved)}</td>
    <td>${num(w.submissions)}</td><td>${num(w.approved_submissions)}</td><td style="color:${w.rejected_submissions ? 'var(--danger)' : 'var(--text-3)'};">${num(w.rejected_submissions)}</td>
    <td>${num(w.pending_submissions)}</td><td>${w.avg_attempts ?? '—'}</td></tr>`);
  const inactive = anTable(['Student', 'Track', 'Weeks approved', 'Last activity', 'Inactive', ''],
    e.inactive.map(s => `<tr><td><b>${esc(s.name)}</b><br><a href="mailto:${esc(s.email)}" style="font-size:0.75rem;color:var(--text-3);">${esc(s.email)}</a></td><td>${esc(s.domain)}</td>
      <td>${s.weeks_approved}/4</td><td>${esc(s.last_activity)}</td><td>${s.days_inactive}d</td>
      <td><button class="btn btn-secondary" style="font-size:0.72rem;padding:3px 10px;" onclick="anJourney(${s.student_id})">Journey</button></td></tr>`),
    'No inactive students for this selection.');
  return anCards(
      anCard('📅', e.wau, 'Weekly active people', 'signed in or submitted, last 7 days', '', 'started') +
      anCard('🗓️', e.mau, 'Monthly active people', 'last 30 days', '', 'started') +
      anCard('🔑', e.logins_30d, 'Logins (30 days)', 'verified sign-ins', '', 'started') +
      anCard('🚫', e.never_logged_in, 'Enrolled, never signed in', 'never opened the dashboard', 'never_logged_in', 'started') +
      anCard('🕳️', e.enrolled_no_task, 'Enrolled, no first task', 'signed up but never submitted', 'enrolled_no_task', 'first_task') +
      anCard('📝', e.first_task_students, 'Submitted a first task', 'students', 'first_task', 'first_task') +
      anCard('⏱️', rw.median_hours === null ? '—' : `${rw.median_hours}h`, 'Review wait (median)', `90th percentile ${rw.p90_hours === null ? '—' : rw.p90_hours + 'h'} · ${num(rw.reviews)} reviews`, '', '') +
      anCard('😴', e.inactive_count, `Inactive ${e.inactive_days}+ days`, 'enrolled, not completed', '', '')) +
    anGrid(420, anPanel('Weekly progress', 'Students who submitted vs got approved', anCanvas('chart-an-eng')) +
      anPanel('Week-by-week detail', 'Student columns and submission columns are different units and are labelled',
        anTable(['Week', 'Students submitted', 'Students approved', 'Submissions', 'Approved subs', 'Rejected subs', 'Pending subs', 'Avg tries'], wk))) +
    '<div style="height:20px"></div>' +
    anPanel('Inactive students', `<span>Enrolled, not completed, no sign-in or submission in the last <select class="filter-select" style="height:28px;font-size:0.78rem;" onchange="an.inactiveDays=Number(this.value);loadAnalytics()">
      ${[7, 14, 30].map(n => `<option value="${n}" ${n === e.inactive_days ? 'selected' : ''}>${n}</option>`).join('')}</select> days.</span> Send nudges from the Reminders page.`, inactive);
}

// ─── Data quality ──────────────────────────────────────────────────────────
async function anQuality(d) {
  if (!an.quality) {
    try { an.quality = await api('/api/admin/analytics/data-quality'); } catch (e) { return `<div class="empty-state"><div class="empty-state-text">${esc(e.message)}</div></div>`; }
  }
  const warn = (d.validation || []).map(w => `<tr><td><span class="an-sev an-sev-${esc(w.level === 'error' ? 'error' : w.level)}">${esc(w.level)}</span></td><td>${esc(w.message)}</td></tr>`);
  const checks = an.quality.checks.map(c => {
    const items = c.items.map(i => `<tr><td><b>${esc(i.name || i.table || '')}</b>${i.email ? `<br><span class="an-bar-meta">${esc(i.email)}</span>` : ''}</td><td>${esc(i.domain || '')}</td>
      <td class="an-bar-meta">${esc(Object.entries(i).filter(([k]) => !['student_id', 'name', 'email', 'domain', 'is_test', 'table'].includes(k)).map(([k, v]) => `${k}: ${v}`).join(' · '))}</td>
      <td>${i.student_id ? `<button class="btn btn-secondary" style="font-size:0.72rem;padding:3px 8px;" onclick="anJourney(${i.student_id})">Journey</button>
        ${c.key === 'test_payment_accounts' ? `<button class="btn btn-tone-warn" style="font-size:0.72rem;padding:3px 8px;" onclick="anFlagStudent(${i.student_id}, true)">Mark account as test</button>` : ''}` : ''}</td></tr>`);
    const body = c.items.length ? anTable(['Record', 'Track', 'Detail', ''], items) : '';
    return `<div class="panel" style="margin-bottom:14px;"><div class="panel-header"><div><div class="panel-title">${esc(c.label)}</div>
      ${c.note ? `<div class="panel-subtitle">${esc(c.note)}</div>` : ''}</div>
      <div><span class="an-sev an-sev-${esc(c.severity)}">${esc(c.severity)}</span> <b style="margin-left:6px;">${num(c.count)}</b></div></div>
      ${body ? `<div class="panel-body" style="max-height:340px;">${body}${c.count > c.items.length ? `<div class="an-unit">Showing first ${c.items.length} of ${num(c.count)}.</div>` : ''}</div>` : ''}</div>`;
  }).join('');
  return anPanel('Metric validation', 'Computed on every load. Errors mean two numbers contradict each other; info explains an expected difference.',
      anTable(['Level', 'Check'], warn, '✅ Every funnel, domain and payment total reconciles.')) +
    '<div style="height:20px"></div><div class="an-note">Nothing on this page is changed automatically. Historical records are only flagged, never rewritten.</div>' + checks;
}

async function anFlagStudent(id, flag) {
  if (!confirm(flag ? 'Mark this account as a test account? It is kept in the database but dropped from all analytics.' : 'Mark as a real account again?')) return;
  try { await api(`/api/admin/students/${id}/test-flag`, { method: 'PATCH', body: JSON.stringify({ is_test: flag }) }); toast('Updated'); an.quality = null; loadAnalytics(true); }
  catch (e) { toast(e.message, 'error'); }
}

// ─── Drill-down + student journey ──────────────────────────────────────────
function anDrill(stage, title) {
  an.drill = { stage, title, page: 1, q: '' };
  openModal('an-drill-modal');
  anLoadDrill();
}

async function anLoadDrill() {
  const body = document.getElementById('an-drill-body');
  document.getElementById('an-drill-title').textContent = an.drill.title;
  body.innerHTML = '<div class="loading-overlay"><div class="spinner"></div> Loading…</div>';
  try {
    const res = await api(`/api/admin/analytics/students?${anQuery({ stage: an.drill.stage, page: an.drill.page, q: an.drill.q, limit: 15 })}`);
    const rows = res.students.map(s => `<tr class="an-click" onclick="anJourney(${s.id}, true)">
      <td><b>${esc(s.name)}</b>${s.is_test ? ' <span class="an-sev an-sev-info">test</span>' : ''}<br><span class="an-bar-meta">${esc(s.email)}</span></td><td>${esc(s.domain)}</td>
      <td class="an-bar-meta">${esc((s.applied_at || '').slice(0, 10))}</td><td>${s.started ? '✓' : '—'}</td><td>${s.weeks_approved}/4${s.completed ? ' 🏁' : ''}</td>
      <td>${s.certificate ? '🎓' : '—'}</td><td>${esc(s.pay_state)}</td><td class="an-bar-meta">${esc(s.source)}</td></tr>`);
    body.innerHTML = `<div class="filter-row" style="margin-bottom:10px;"><input class="search-input" placeholder="Search name, email or track" value="${esc(an.drill.q)}"
        onchange="an.drill.q=this.value;an.drill.page=1;anLoadDrill()"><span class="an-bar-meta">${num(res.total)} student${res.total === 1 ? '' : 's'} · same filters as the dashboard</span></div>` +
      anTable(['Student', 'Track', 'Applied', 'Signed in', 'Weeks', 'Cert', 'Payment', 'Source'], rows, 'No students at this stage.') + anPager(res, 'an.drill.page');
  } catch (e) { body.innerHTML = `<div class="empty-state"><div class="empty-state-text">${esc(e.message)}</div></div>`; }
}

async function anJourney(id, fromDrill = false) {
  const body = document.getElementById('an-drill-body');
  openModal('an-drill-modal');
  document.getElementById('an-drill-title').textContent = 'Student journey';
  body.innerHTML = '<div class="loading-overlay"><div class="spinner"></div> Loading…</div>';
  try {
    const j = await api(`/api/admin/students/${id}/journey`);
    const s = j.student;
    const kv = [['Name', `${s.first_name} ${s.last_name}${s.is_test ? ' (TEST ACCOUNT)' : ''}`], ['Email', s.email], ['Track', s.domain], ['College', s.college || '—'],
      ['Applied', s.created_at], ['First touch', s.attribution_captured ? (s.first_touch_source || 'direct') : 'unknown (pre-tracking)'],
      ['Last touch', s.last_touch_source ? `${s.last_touch_source}${s.last_touch_campaign ? ' / ' + s.last_touch_campaign : ''}` : '—'],
      ['UTM', [s.utm_source, s.utm_medium, s.utm_campaign].filter(Boolean).join(' / ') || '—'], ['Landing page', s.landing_page || '—'],
      ['Referrer', s.referrer || '—'], ['Referral code', s.referral_code || '—'], ['Said they heard via', s.referral_source || '—']];
    body.innerHTML = `${fromDrill ? '<button class="btn btn-secondary" style="margin-bottom:12px;font-size:0.78rem;" onclick="anLoadDrill()">‹ Back to list</button>' : ''}
      <dl class="an-kv" style="margin-bottom:18px;">${kv.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
      <ul class="an-timeline">${j.timeline.map(e => `<li><span class="at">${esc(String(e.at || '').replace('T', ' ').slice(0, 16))}</span>${esc(e.label)}</li>`).join('')}</ul>`;
  } catch (e) { body.innerHTML = `<div class="empty-state"><div class="empty-state-text">${esc(e.message)}</div></div>`; }
}

window.loadAnalytics = loadAnalytics;
