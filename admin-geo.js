// SkillMe admin console: geography. The world map, the Overview "Global reach" panel and the
// Analytics "Geography" tab. Loaded with defer after admin.js and uses its helpers
// (esc, jsArg, fmtINR, navigate). Numbers come from the `geo` block of /api/admin/stats and the
// `geography` block of /api/admin/analytics: one per-student rollup on the server
// (backend/services/analytics_service.py geography_section), so both views always agree.
// Map shapes: assets/world-map.json, built by tools/build_world_map.py (Natural Earth, with
// India drawn per the official Survey of India boundary).

(function () {
  'use strict';

  // /assets/ is cached for a week; bump this whenever the map file is rebuilt.
  const MAP_VERSION = '2';
  let mapPromise = null;
  function loadMap() {
    if (!mapPromise) {
      mapPromise = fetch('/assets/world-map.json?v=' + MAP_VERSION).then(r => {
        if (!r.ok) throw new Error('map ' + r.status);
        return r.json();
      }).catch(e => { mapPromise = null; throw e; });
    }
    return mapPromise;
  }

  const n = v => Number(v || 0).toLocaleString('en-IN');
  const pct = v => (v === null || v === undefined) ? '—' : `${Math.round(v * 10) / 10}%`;

  function flag(iso, w = 18) {
    if (!iso || iso === 'unknown') return `<span class="geo-flag geo-flag-none" style="width:${w}px"></span>`;
    const c = String(iso).toLowerCase();
    return `<img class="geo-flag" src="/assets/flags/${c}.png" srcset="/assets/flags/${c}.png 1x, /assets/flags/${c}@2x.png 2x" width="${w}" height="${Math.round(w * 0.75)}" alt="" loading="lazy">`;
  }
  window.geoFlag = flag;

  // Applicant counts are very uneven (India is ~80%), so colour by order of magnitude.
  const LEVELS = [
    { min: 50, label: '50+' }, { min: 10, label: '10–49' }, { min: 3, label: '3–9' }, { min: 1, label: '1–2' },
  ];
  function level(v) {
    if (!v) return 0;
    for (let i = 0; i < LEVELS.length; i++) if (v >= LEVELS[i].min) return 4 - i;
    return 0;
  }

  const METRICS = {
    applications: { label: 'Applicants', of: r => r.applications },
    paid: { label: 'Paying students', of: r => r.paid },
  };

  // ── Map ─────────────────────────────────────────────────────────────────────
  // Renders into `host`; rows = geography.countries. Returns a promise.
  async function renderMap(host, rows, metric = 'applications') {
    let data;
    try { data = await loadMap(); } catch (e) {
      host.innerHTML = `<div class="geo-map-error">Map couldn't load. Refresh to try again.</div>`;
      return;
    }
    const by = {};
    rows.forEach(r => { by[r.key] = r; });
    const of = METRICS[metric].of;
    const paths = Object.keys(data.paths).map(iso => {
      const r = by[iso];
      const lv = r ? level(of(r)) : 0;
      return `<path d="${data.paths[iso]}" data-iso="${iso}" class="geo-c l${lv}${r ? ' is-on' : ''}"/>`;
    }).join('');
    host.innerHTML = `
      <div class="geo-map-box">
        <svg class="geo-map" viewBox="0 0 ${data.w} ${data.h}" role="img"
             aria-label="World map of ${esc(METRICS[metric].label.toLowerCase())} by country">
          <g class="geo-land">${paths}</g><g class="geo-dots"></g>
        </svg>
        <div class="geo-tip" hidden></div>
      </div>
      <div class="geo-legend" aria-hidden="true">
        <span class="geo-legend-label">${esc(METRICS[metric].label)}</span>
        ${LEVELS.slice().reverse().map((l, i) => `<span class="geo-legend-item"><i class="l${i + 1}"></i>${l.label}</span>`).join('')}
      </div>`;
    const svg = host.querySelector('svg');

    // Countries too small to see as a shape (Singapore, Bahrain, Rwanda…) get a dot.
    const dots = svg.querySelector('.geo-dots');
    const marks = [];
    rows.forEach(r => {
      const v = of(r);
      if (!v || !data.dots[r.key]) return;
      const p = svg.querySelector(`path[data-iso="${r.key}"]`);
      let small = !p;
      if (p) { try { const b = p.getBBox(); small = b.width * b.height < 40; } catch (e) { small = false; } }
      if (small) {
        const [x, y] = data.dots[r.key];
        marks.push(`<circle cx="${x}" cy="${y}" r="${3 + level(v) * 0.6}" data-iso="${r.key}" class="geo-dot l${level(v)}"/>`);
      }
    });
    dots.innerHTML = marks.join('');

    // Tooltip
    const tip = host.querySelector('.geo-tip');
    const box = host.querySelector('.geo-map-box');
    let lastIso = null;
    svg.addEventListener('mousemove', e => {
      const t = e.target.closest('[data-iso]');
      const r = t && by[t.dataset.iso];
      if (!r) { tip.hidden = true; lastIso = null; return; }
      if (lastIso !== r.key) {
        lastIso = r.key;
        tip.innerHTML = `
          <div class="geo-tip-head">${flag(r.key, 18)}<b>${esc(r.label)}</b></div>
          <div class="geo-tip-grid">
            <span>Applicants</span><b>${n(r.applications)}</b>
            <span>Enrolled</span><b>${n(r.enrolled)}</b>
            <span>Completed</span><b>${n(r.completed)}</b>
            <span>Paying</span><b>${n(r.paid)}</b>
            <span>Revenue</span><b>${fmtINR(r.revenue_rupees)}</b>
          </div>`;
      }
      const rect = box.getBoundingClientRect();
      const x = e.clientX - rect.left, y = e.clientY - rect.top;
      tip.hidden = false;
      const tw = tip.offsetWidth, th = tip.offsetHeight;
      tip.style.left = Math.min(rect.width - tw - 4, Math.max(4, x + 14)) + 'px';
      tip.style.top = (y - th - 12 < 0 ? y + 16 : y - th - 12) + 'px';
    });
    svg.addEventListener('mouseleave', () => { tip.hidden = true; lastIso = null; });
    svg.addEventListener('click', e => {
      const t = e.target.closest('[data-iso]');
      if (t && by[t.dataset.iso] && window.geoOpenCountry) window.geoOpenCountry(t.dataset.iso);
    });
  }
  window.geoRenderMap = renderMap;

  // ── Shared pieces ───────────────────────────────────────────────────────────
  function splitRow(label, india, intl, fmt = pct) {
    const a = Math.max(0, Math.min(100, india || 0)), b = Math.max(0, Math.min(100, intl || 0));
    const empty = !a && !b;
    return `<div class="geo-split-row">
      <div class="geo-split-top"><span>${esc(label)}</span><span class="geo-split-vals"><b>${fmt(a)}</b> · <b>${fmt(b)}</b></span></div>
      <div class="geo-split-bar${empty ? ' is-empty' : ''}"><i class="is-in" style="width:${a}%"></i><i class="is-intl" style="width:${b}%"></i></div>
    </div>`;
  }

  // One sentence a founder can act on.
  function insight(g) {
    const i = g.india, x = g.international;
    if (!x.applications) return '';
    if (x.share_applications >= 10 && !x.paid) {
      return `International students are <b>${pct(x.share_applications)}</b> of applicants but <b>none have paid yet</b>. Check that international cards work at checkout and that the price suits markets outside India before spending more on reach.`;
    }
    if (x.paid_rate && i.paid_rate && x.paid_rate < i.paid_rate / 2) {
      return `International converts to paid at <b>${pct(x.paid_rate)}</b> against <b>${pct(i.paid_rate)}</b> in India. Fix that gap before you scale international reach.`;
    }
    return `International brings <b>${pct(x.share_applications)}</b> of applicants and <b>${pct(x.share_revenue)}</b> of revenue.`;
  }

  function topList(rows, metric, limit) {
    const of = METRICS[metric].of;
    const sorted = rows.slice().filter(r => of(r) > 0).sort((a, b) => of(b) - of(a) || b.applications - a.applications);
    if (!sorted.length) return `<div class="geo-empty">No ${esc(METRICS[metric].label.toLowerCase())} yet.</div>`;
    const max = of(sorted[0]) || 1;
    return `<ol class="geo-top">${sorted.slice(0, limit).map(r => `
      <li class="geo-top-row" role="button" tabindex="0" onclick="geoOpenCountry(${jsArg(r.key)})" onkeydown="if(event.key==='Enter')this.click()"
          title="See ${esc(r.label)} applicants">
        ${flag(r.key, 20)}
        <span class="geo-top-name">${esc(r.label)}</span>
        <span class="geo-top-bar"><i style="width:${Math.max(3, of(r) * 100 / max)}%"></i></span>
        <span class="geo-top-num">${n(of(r))}</span>
      </li>`).join('')}</ol>`;
  }

  function newChips(list, limit = 12) {
    if (!list || !list.length) return '';
    const shown = list.slice(0, limit);
    const more = list.length - shown.length;
    return `<div class="geo-new">
      <span class="geo-new-label">New in the last 30 days</span>
      <div class="geo-chips">${shown.map(c => `<button type="button" class="geo-chip" onclick="geoOpenCountry(${jsArg(c.key)})"
        title="First applicant ${esc(c.first_applied)} · ${n(c.applications)} so far">${flag(c.key, 16)}${esc(c.label)}</button>`).join('')}
        ${more > 0 ? `<span class="geo-chip is-more">+${more} more</span>` : ''}</div>
    </div>`;
  }

  // Clicking a country opens the Students page filtered to it.
  window.geoOpenCountry = function (iso) {
    const sel = document.getElementById('country-filter');
    if (sel) {
      if (![...sel.options].some(o => o.value === iso)) sel.add(new Option(iso, iso));
      sel.value = iso;
    }
    if (typeof studentsState !== "undefined") { studentsState.country = iso; studentsState.status = ''; studentsState.page = 1; }
    const st = document.getElementById('status-filter');
    if (st) st.value = '';
    navigate('students');
  };

  // ── Overview: Global reach panel ────────────────────────────────────────────
  const geoState = { metric: 'applications', geo: null };

  window.renderGlobalReach = function (geo) {
    const el = document.getElementById('global-reach');
    if (!el || !geo) return;
    geoState.geo = geo;
    const g = geo, i = g.india, x = g.international;
    const newCount = (g.new_30d || []).length;
    el.innerHTML = `
      <div class="panel-header geo-head">
        <div>
          <div class="panel-title">Global reach</div>
          <div class="panel-subtitle">Where applicants come from, and which markets pay</div>
        </div>
        <div class="seg" role="tablist" aria-label="Colour the map by">
          ${Object.entries(METRICS).map(([k, m]) => `<button type="button" role="tab" class="seg-btn${k === geoState.metric ? ' is-on' : ''}"
            aria-selected="${k === geoState.metric}" onclick="geoSetMetric(${jsArg(k)})">${esc(m.label)}</button>`).join('')}
        </div>
      </div>
      <div class="geo-body">
        <div class="geo-main">
          <div class="geo-map-host" id="geo-map-overview"><div class="geo-map-skeleton"></div></div>
        </div>
        <aside class="geo-side">
          <div class="geo-hero">
            <div class="geo-hero-num">${n(g.country_count)}</div>
            <div class="geo-hero-txt">
              <b>${g.country_count === 1 ? 'country' : 'countries'}</b>
              <span>${newCount ? `+${newCount} new in the last 30 days` : 'no new countries in 30 days'}</span>
            </div>
          </div>
          <div class="geo-block">
            <div class="geo-block-head"><span>India vs international</span>
              <span class="geo-key"><i class="is-in"></i>India <i class="is-intl"></i>Intl</span></div>
            ${splitRow('Applicants', i.share_applications, x.share_applications)}
            ${splitRow('Paying students', i.share_paid, x.share_paid)}
            ${splitRow('Revenue', i.share_revenue, x.share_revenue)}
            ${insight(g) ? `<p class="geo-insight">${insight(g)}</p>` : ''}
          </div>
          <div class="geo-block">
            <div class="geo-block-head"><span>Top countries · ${esc(METRICS[geoState.metric].label.toLowerCase())}</span>
              <button type="button" class="geo-link" onclick="geoShowAll()">All ${n(g.country_count)} →</button></div>
            ${topList(g.countries, geoState.metric, 6)}
          </div>
        </aside>
      </div>
      ${newChips(g.new_30d)}`;
    renderMap(document.getElementById('geo-map-overview'), g.countries, geoState.metric);
  };

  window.geoSetMetric = function (metric) {
    geoState.metric = metric;
    if (geoState.geo) window.renderGlobalReach(geoState.geo);
  };

  window.geoShowAll = function () {
    navigate('analytics');
    if (window.anTab) anTab('geography');
  };

  // ── Analytics: Geography tab ────────────────────────────────────────────────
  window.anGeography = function (d) {
    const g = d.geography;
    if (!g) return `<div class="empty-state"><div class="empty-state-text">Deploy the latest backend to see geography.</div></div>`;
    const i = g.india, x = g.international;
    const cmp = (label, a, b, fmt) => `<tr><td>${label}</td><td>${fmt(a)}</td><td>${fmt(b)}</td></tr>`;
    const rows = g.countries.map(r => `<tr class="an-click" onclick="anSetFilter('country', ${jsArg(r.key)})" title="Filter the whole page to ${esc(r.label)}">
      <td><span class="geo-cell">${flag(r.key, 20)}<b>${esc(r.label)}</b></span></td>
      <td>${n(r.applications)} <span class="an-bar-meta">${pct(r.share)}</span></td>
      <td>${n(r.enrolled)} <span class="an-bar-meta">${pct(r.enroll_rate)}</span></td>
      <td>${n(r.completed)}</td>
      <td>${n(r.paid)} <span class="an-bar-meta">${pct(r.paid_rate)}</span></td>
      <td>${fmtINR(r.revenue_rupees)}</td>
      <td class="an-bar-meta">${esc(r.first_applied || '—')}</td></tr>`);
    setTimeout(() => {
      const host = document.getElementById('geo-map-analytics');
      if (host) renderMap(host, g.countries, 'applications');
    });
    return `
      <div class="stats-grid">
        ${anCard('🌍', g.country_count, 'Countries', `${n((g.new_30d || []).length)} new in the last 30 days`)}
        ${anCard('🇮🇳', i.applications, 'India applicants', `${pct(i.share_applications)} of applicants · ${pct(i.share_revenue)} of revenue`)}
        ${anCard('✈️', x.applications, 'International applicants', `${pct(x.share_applications)} of applicants · ${pct(x.share_revenue)} of revenue`)}
        ${anCard('💸', fmtINR(x.revenue_per_applicant), 'Revenue per intl applicant', `India: ${fmtINR(i.revenue_per_applicant)}`)}
      </div>
      <div class="panel geo-panel-flat">
        <div class="panel-header"><div><div class="panel-title">Applicants by country</div>
          <div class="panel-subtitle">Hover a country for its numbers · click to see its students</div></div></div>
        <div class="geo-map-host geo-map-lg" id="geo-map-analytics"><div class="geo-map-skeleton"></div></div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(380px,100%),1fr));gap:20px;margin-top:20px;">
        ${anPanel('India vs international', 'Same funnel, side by side. Rates are of applicants unless noted.',
          anTable(['', 'India', 'International'], [
            cmp('Applicants', i.applications, x.applications, n),
            cmp('Enrolled', i.enroll_rate, x.enroll_rate, pct),
            cmp('Completed <span class="an-bar-meta">of enrolled</span>', i.completion_rate, x.completion_rate, pct),
            cmp('Paid', i.paid_rate, x.paid_rate, pct),
            cmp('Paying students', i.paid, x.paid, n),
            cmp('Revenue', i.revenue_rupees, x.revenue_rupees, fmtINR),
            cmp('Revenue per applicant', i.revenue_per_applicant, x.revenue_per_applicant, fmtINR),
          ])) }
        ${anPanel('New markets', 'Countries whose first applicant arrived in the last 30 days',
          (g.new_30d || []).length ? `<div class="geo-chips">${g.new_30d.map(c => `<button type="button" class="geo-chip" onclick="anSetFilter('country', ${jsArg(c.key)})"
            title="First applicant ${esc(c.first_applied)}">${flag(c.key, 16)}${esc(c.label)} <span class="an-bar-meta">${n(c.applications)}</span></button>`).join('')}</div>`
            : '<div class="geo-empty">No new countries in the last 30 days.</div>')}
      </div>
      <div style="height:20px"></div>
      ${anPanel('Every country', `${n(g.country_count)} countries${g.unknown ? ` · ${n(g.unknown)} applicant${g.unknown > 1 ? 's' : ''} with no country` : ''}. Click a row to filter the whole page.`,
        anTable(['Country', 'Applicants', 'Enrolled', 'Completed', 'Paying', 'Revenue', 'First applicant'], rows, 'No applicants in this selection.'))}`;
  };
})();
