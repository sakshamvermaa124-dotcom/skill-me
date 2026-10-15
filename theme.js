/* =============================================================
   theme.js — SkillMe shared behaviour (load with `defer`)
   - Light/dark toggle on any [data-theme-toggle] (key: skillme-theme)
   - .site-nav gets .is-scrolled once the page scrolls
   - Mobile drawer: [data-nav-toggle] opens #nav-drawer
   - .reveal elements fade in on scroll
   - [data-year] gets the current year

   The initial theme is applied by the inline snippet in each page <head>
   (before first paint), so this file only handles changes.
   ============================================================= */
(function () {
  'use strict';

  var KEY = 'skillme-theme';
  var BG = { light: '#ffffff', dark: '#09090a' };
  var root = document.documentElement;
  root.classList.remove('no-js');

  function current() { return root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'; }

  function syncUi() {
    var theme = current();
    var next = theme === 'dark' ? 'light' : 'dark';
    document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
      btn.setAttribute('aria-label', 'Switch to ' + next + ' mode');
      btn.setAttribute('title', 'Switch to ' + next + ' mode');
      var label = btn.querySelector('[data-theme-label]');
      if (label) label.textContent = next === 'light' ? 'Light mode' : 'Dark mode';
    });
    document.querySelectorAll('meta[name="theme-color"]').forEach(function (m) { m.setAttribute('content', BG[theme]); });
  }

  function setTheme(theme) {
    if (theme !== 'light' && theme !== 'dark') return;
    root.classList.add('theme-switching');
    root.setAttribute('data-theme', theme);
    try { localStorage.setItem(KEY, theme); } catch (e) {}
    syncUi();
    window.dispatchEvent(new CustomEvent('themechange', { detail: { theme: theme } }));
    setTimeout(function () { root.classList.remove('theme-switching'); }, 340);
  }
  window.SkillMeTheme = { get: current, set: setTheme, toggle: function () { setTheme(current() === 'dark' ? 'light' : 'dark'); } };

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-theme-toggle]');
    if (btn) { e.preventDefault(); window.SkillMeTheme.toggle(); }
  });

  // Follow the OS only while the visitor hasn't chosen explicitly
  if (window.matchMedia) {
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    var onOs = function (ev) {
      var saved = null;
      try { saved = localStorage.getItem(KEY); } catch (e) {}
      if (saved === 'light' || saved === 'dark') return;
      root.setAttribute('data-theme', ev.matches ? 'dark' : 'light');
      syncUi();
    };
    if (mq.addEventListener) mq.addEventListener('change', onOs); else if (mq.addListener) mq.addListener(onOs);
  }

  function init() {
    syncUi();

    // Nav border once scrolled
    var nav = document.querySelector('.site-nav');
    if (nav) {
      var onScroll = function () { nav.classList.toggle('is-scrolled', window.scrollY > 8); };
      onScroll();
      window.addEventListener('scroll', onScroll, { passive: true });
    }

    // Mobile drawer
    var drawer = document.getElementById('nav-drawer');
    document.querySelectorAll('[data-nav-toggle]').forEach(function (btn) {
      btn.setAttribute('aria-controls', 'nav-drawer');
      btn.setAttribute('aria-expanded', 'false');
      btn.addEventListener('click', function () {
        if (!drawer) return;
        var open = !drawer.classList.contains('is-open');
        drawer.classList.toggle('is-open', open);
        btn.setAttribute('aria-expanded', String(open));
        btn.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
      });
    });
    if (drawer) {
      drawer.addEventListener('click', function (e) {
        if (!e.target.closest('a')) return;
        drawer.classList.remove('is-open');
        document.querySelectorAll('[data-nav-toggle]').forEach(function (b) { b.setAttribute('aria-expanded', 'false'); });
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && drawer.classList.contains('is-open')) {
          drawer.classList.remove('is-open');
          document.querySelectorAll('[data-nav-toggle]').forEach(function (b) { b.setAttribute('aria-expanded', 'false'); });
        }
      });
    }

    // Scroll reveal
    var reveals = document.querySelectorAll('.reveal');
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce || !('IntersectionObserver' in window)) {
      reveals.forEach(function (el) { el.classList.add('is-in'); });
    } else {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('is-in');
          io.unobserve(entry.target);
        });
      }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
      reveals.forEach(function (el) { io.observe(el); });
      // Safety net: never leave content hidden (e.g. printing, odd viewports)
      window.addEventListener('beforeprint', function () { reveals.forEach(function (el) { el.classList.add('is-in'); }); });
    }

    document.querySelectorAll('[data-year]').forEach(function (el) { el.textContent = new Date().getFullYear(); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
