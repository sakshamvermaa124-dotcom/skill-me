/* =============================================================
   legal.js — table of contents + section anchors for legal pages
   - Builds the TOC in [data-toc] from `.legal-body h2[id]`
   - Adds a "#" anchor link to each heading (click copies the URL)
   - Highlights the section currently being read
   - TOC is a collapsed disclosure on mobile, always open on desktop
   ============================================================= */
(function () {
  'use strict';

  function init() {
    var body = document.querySelector('[data-legal-body]');
    var list = document.querySelector('[data-toc]');
    var aside = document.querySelector('[data-toc-wrap]');
    if (!body || !list || !aside) return;

    var headings = Array.prototype.slice.call(body.querySelectorAll('h2[id]'));
    if (!headings.length) return;

    var links = [];
    headings.forEach(function (h) {
      var numEl = h.querySelector('.sec-num');
      var num = numEl ? numEl.textContent.trim().replace(/\.$/, '') : '';
      var title = h.querySelector('.sec-title');
      var label = (title ? title.textContent : h.textContent).trim();

      // TOC entry
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = '#' + h.id;
      if (num) {
        var n = document.createElement('span');
        n.className = 'num';
        n.textContent = num.length < 2 ? '0' + num : num;
        a.appendChild(n);
      }
      var t = document.createElement('span');
      t.textContent = label;
      a.appendChild(t);
      li.appendChild(a);
      list.appendChild(li);
      links.push(a);

      // Heading anchor
      var anchor = document.createElement('a');
      anchor.className = 'heading-anchor';
      anchor.href = '#' + h.id;
      anchor.setAttribute('aria-label', 'Link to section: ' + label);
      anchor.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>';
      anchor.addEventListener('click', function () {
        var url = location.href.split('#')[0] + '#' + h.id;
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(url).then(function () { toast('Link copied'); }, function () {});
        }
      });
      h.appendChild(anchor);
    });
    aside.hidden = false;

    // Mobile: collapsed disclosure; desktop: always open
    var details = aside.querySelector('details');
    var mq = window.matchMedia('(min-width: 961px)');
    function syncDetails() { if (details) details.open = mq.matches; }
    syncDetails();
    if (mq.addEventListener) mq.addEventListener('change', syncDetails); else if (mq.addListener) mq.addListener(syncDetails);
    if (details) {
      details.querySelector('summary').addEventListener('click', function (e) {
        if (mq.matches) e.preventDefault(); // keep it open on desktop
      });
    }

    // Active section
    // After a TOC jump the clicked entry stays active until the smooth scroll
    // settles, so a short final section that can't reach the top still lights up.
    var jumping = false, jumpTimer;
    function endJumpSoon(ms) {
      clearTimeout(jumpTimer);
      jumpTimer = setTimeout(function () { jumping = false; }, ms);
    }
    function setActive(i) {
      links.forEach(function (a, j) {
        var on = j === i;
        a.classList.toggle('is-active', on);
        if (on) a.setAttribute('aria-current', 'location'); else a.removeAttribute('aria-current');
      });
    }
    function compute() {
      if (jumping) { endJumpSoon(200); return; }
      var offset = (parseInt(getComputedStyle(document.documentElement).getPropertyValue('--nav-h'), 10) || 64) + 48;
      var idx = -1;
      headings.forEach(function (h, i) { if (h.getBoundingClientRect().top - offset <= 0) idx = i; });
      var atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4;
      if (atBottom) idx = headings.length - 1;
      setActive(Math.max(idx, 0));
    }
    var ticking = false;
    window.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () { ticking = false; compute(); });
    }, { passive: true });
    window.addEventListener('resize', compute);

    function activateHash() {
      var id = decodeURIComponent(location.hash.slice(1));
      var i = headings.findIndex(function (h) { return h.id === id; });
      if (i < 0) return false;
      setActive(i);
      jumping = true;
      endJumpSoon(400);
      return true;
    }
    links.forEach(function (a) {
      a.addEventListener('click', function () {
        if (!mq.matches && details) details.open = false;
        setTimeout(activateHash, 0);
      });
    });
    window.addEventListener('hashchange', activateHash);
    if (!activateHash()) compute();
  }

  var toastEl, toastTimer;
  function toast(msg) {
    if (!toastEl) {
      toastEl = document.createElement('div');
      toastEl.className = 'toast';
      toastEl.setAttribute('role', 'status');
      toastEl.setAttribute('aria-live', 'polite');
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = msg;
    requestAnimationFrame(function () { toastEl.classList.add('is-visible'); });
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove('is-visible'); }, 1800);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
