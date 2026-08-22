// === dashboard-ui.js v1 ===
// App shell: section router, theme toggle, sidebar show/hide
// Loaded defer after dashboard.js. Only touches elements the HTML shell owns.
(function () {
  'use strict';

  const PANELS = ['panel-overview', 'panel-work', 'panel-credentials', 'panel-guide'];
  const NAV_IDS = {
    'panel-overview':    'nav-overview',
    'panel-work':        'nav-work',
    'panel-credentials': 'nav-credentials',
    'panel-guide':       'nav-guide',
  };
  const TAB_IDS = {
    'panel-overview':    'tab-overview',
    'panel-work':        'tab-work',
    'panel-credentials': 'tab-credentials',
    'panel-guide':       'tab-guide',
  };

  // R8: re-trigger ring transition after panel becomes visible
  function replayRing(panel) {
    const ring = panel && panel.querySelector('#progress-ring');
    if (!ring) return;
    const saved = ring.style.strokeDashoffset;
    ring.style.transition = 'none';
    ring.style.strokeDashoffset = '326.7';
    void ring.getBoundingClientRect();
    ring.style.transition = '';
    ring.style.strokeDashoffset = saved;
  }

  // Section router — Rule A: only touches .dash-panel wrappers
  window.dashShowPanel = function (id) {
    if (!PANELS.includes(id)) return;
    PANELS.forEach(function (pid) {
      const el = document.getElementById(pid);
      if (!el) return;
      if (pid === id) {
        el.removeAttribute('hidden');
        el.style.display = 'block';
      } else {
        el.setAttribute('hidden', '');
        el.style.display = 'none';
      }
    });
    Object.keys(NAV_IDS).forEach(function (pid) {
      var btn = document.getElementById(NAV_IDS[pid]);
      if (btn) btn.classList.toggle('is-active', pid === id);
    });
    Object.keys(TAB_IDS).forEach(function (pid) {
      var btn = document.getElementById(TAB_IDS[pid]);
      if (btn) btn.classList.toggle('is-active', pid === id);
    });
    var panel = document.getElementById(id);
    if (!panel) return;
    // R4: ensure sub-cards are visible in newly-shown panel
    panel.querySelectorAll('.sub-card:not(.visible)').forEach(function (c) { c.classList.add('visible'); });
    replayRing(panel);
    window.dispatchEvent(new Event('resize'));
  };


  // Sidebar visibility — MutationObserver on #dashboard-view
  document.addEventListener('DOMContentLoaded', function () {
    var dashViewEl = document.getElementById('dashboard-view');
    if (!dashViewEl) return;

    function syncShell() {
      var vis = dashViewEl.style.display !== '' && dashViewEl.style.display !== 'none';
      document.body.classList.toggle('dash-app', vis);
    }
    syncShell();
    var mo = new MutationObserver(syncShell);
    mo.observe(dashViewEl, { attributes: true, attributeFilter: ['style'] });
  });
})();
