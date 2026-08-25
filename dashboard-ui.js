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
    ring.style.strokeDashoffset = '439.8';
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
    panel.classList.remove('panel-entering');
    void panel.offsetWidth;
    panel.classList.add('panel-entering');
    window.dispatchEvent(new Event('resize'));
  };


  // Interactive milestone roadmap — click a week for its status/details
  window.showMilestoneInfo = function (week, name, el) {
    const tooltip = document.getElementById('milestone-tooltip');
    const container = el.closest('.progress-details');
    if (!tooltip || !container) return;

    if (tooltip.classList.contains('visible') && tooltip.dataset.forEl === el.id) {
      tooltip.classList.remove('visible');
      return;
    }

    let message;
    if (el.classList.contains('completed')) {
      message = `<strong>Week ${week}: ${name}</strong><br>Completed and approved — nice work!`;
    } else if (el.classList.contains('active')) {
      message = `<strong>Week ${week}: ${name}</strong><br>In progress — submit your LinkedIn post in the Work tab to complete it.`;
    } else {
      message = `<strong>Week ${week}: ${name}</strong><br>Unlocks once you complete Week ${week - 1}.`;
    }
    tooltip.innerHTML = message;
    tooltip.dataset.forEl = el.id;
    tooltip.classList.add('visible');

    const containerRect = container.getBoundingClientRect();
    const elRect = el.getBoundingClientRect();
    const ttWidth = tooltip.offsetWidth;
    const ttHeight = tooltip.offsetHeight;
    let left = (elRect.left - containerRect.left) + elRect.width / 2 - ttWidth / 2;
    left = Math.max(0, Math.min(left, container.offsetWidth - ttWidth));
    let top = (elRect.top - containerRect.top) - ttHeight - 10;
    if (top < 0) top = (elRect.bottom - containerRect.top) + 10;
    tooltip.style.left = left + 'px';
    tooltip.style.top = top + 'px';
  };

  document.addEventListener('click', function (e) {
    const tooltip = document.getElementById('milestone-tooltip');
    if (!tooltip || !tooltip.classList.contains('visible')) return;
    if (e.target.closest('.sprint-milestone-step') || e.target.closest('.milestone-tooltip')) return;
    tooltip.classList.remove('visible');
  });

  // Enter/Space activate div[role="button"] elements (milestone steps, ring)
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const target = e.target.closest('[role="button"]');
    if (!target) return;
    e.preventDefault();
    target.click();
  });

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
