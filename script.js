/* =============================================================
   script.js — SkillMe home page (index.html only)
   Theme, sticky nav, mobile drawer and .reveal are handled by theme.js.
   This file keeps the page's functional features:
   - Apply links (quiz-gated: apply.html once the quiz is done)
   - Same-page anchor scrolling
   - Live activity ticker   GET /api/students/public-activity
   - Wall of work           GET /api/students/wall?limit=12
   - Domain category filter + domain card links
   - FAQ search, category filter, single-open accordion
   - Final CTA track pills (label + link)
   ============================================================= */
document.addEventListener('DOMContentLoaded', () => {
  'use strict';

  const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const apiBase = () => window.SKILLME_API || (window.location.hostname === 'localhost' ? 'http://localhost:8000' : 'https://skill-me.onrender.com');
  const quizDone = () => { try { return !!localStorage.getItem('skillme_quiz_result'); } catch (e) { return false; } };

  // ── Apply links: once the quiz is done, go straight to the application ──
  window.handleApplyClick = function (e) {
    if (e && e.preventDefault) e.preventDefault();
    const targetUrl = (e && e.currentTarget && e.currentTarget.getAttribute('href')) || '';
    if (quizDone()) {
      window.location.href = 'apply.html';
    } else if (targetUrl && targetUrl.startsWith('quiz.html')) {
      window.location.href = targetUrl;
    } else {
      window.location.href = 'quiz.html';
    }
  };
  document.querySelectorAll('#nav-apply-btn, #hero-apply-btn, #cta-apply-btn, [data-apply]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      // Let modified clicks (new tab, etc.) behave like a normal link
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button === 1) return;
      window.handleApplyClick(e);
    });
  });

  // ── Same-page anchors (#id and index.html#id) ──
  document.querySelectorAll('a[href^="#"], a[href^="index.html#"]').forEach(anchor => {
    anchor.addEventListener('click', (e) => {
      const hash = anchor.getAttribute('href').replace(/^index\.html/, '');
      if (!hash || hash === '#') return;
      const target = document.getElementById(decodeURIComponent(hash.slice(1)));
      if (!target || target.hidden) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
      if (history.pushState) history.pushState(null, '', hash);
      // Move focus for keyboard / screen reader users without a second jump
      if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
      target.focus({ preventScroll: true });
    });
  });

  // ── Live activity ticker (real approved submissions only; hidden until data) ──
  (function initLiveActivityTicker() {
    const ribbon = document.getElementById('live-activity-ribbon');
    const item = document.getElementById('live-ticker-item');
    if (!ribbon || !item) return;
    const avatarEl = document.getElementById('ticker-avatar');
    const userEl = document.getElementById('ticker-user');
    const collegeEl = document.getElementById('ticker-college');
    const actionEl = document.getElementById('ticker-action');
    const timeEl = document.getElementById('ticker-time');
    const prCountEl = document.getElementById('ticker-pr-count');
    const collegeCountEl = document.getElementById('ticker-college-count');
    const statEl = document.getElementById('live-ticker-stat');

    let activities = [];
    let currentIndex = 0;
    let isPaused = false;

    function renderItem(act) {
      if (!act) return;
      item.classList.add('switching');
      setTimeout(() => {
        if (avatarEl) avatarEl.textContent = act.student_initials || act.initials || 'SM';
        if (userEl) userEl.textContent = act.student_name || act.name || 'Student Contributor';
        if (collegeEl) collegeEl.textContent = act.college || 'Engineering College';
        if (actionEl) actionEl.textContent = act.action_text || act.action || 'had a milestone approved';
        if (timeEl) timeEl.textContent = act.time_ago || act.time || 'Just now';
        item.classList.remove('switching');
      }, reduceMotion ? 0 : 250);
    }

    function nextActivity() {
      if (isPaused || activities.length < 2) return;
      currentIndex = (currentIndex + 1) % activities.length;
      renderItem(activities[currentIndex]);
    }

    ribbon.addEventListener('mouseenter', () => { isPaused = true; });
    ribbon.addEventListener('mouseleave', () => { isPaused = false; });
    ribbon.addEventListener('focusin', () => { isPaused = true; });
    ribbon.addEventListener('focusout', () => { isPaused = false; });
    ribbon.addEventListener('touchstart', () => { isPaused = true; }, { passive: true });
    ribbon.addEventListener('touchend', () => { isPaused = false; }, { passive: true });

    async function fetchLiveFeed() {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 6000);
        const res = await fetch(`${apiBase()}/api/students/public-activity`, { signal: controller.signal });
        clearTimeout(timeoutId);
        if (!res.ok) return;
        const data = await res.json();
        if (data && data.activities && data.activities.length > 0) {
          const firstLoad = activities.length === 0;
          activities = data.activities;
          if (firstLoad) {
            currentIndex = 0;
            renderItem(activities[0]);
            ribbon.style.display = '';
          }
        }
        if (data && data.stats) {
          if (prCountEl) prCountEl.textContent = `${data.stats.total_submissions_approved || 0}`;
          if (collegeCountEl) collegeCountEl.textContent = `${data.stats.total_colleges || 0}`;
          if (statEl) statEl.hidden = !data.stats.total_submissions_approved;
        }
      } catch (err) {
        // Offline / API down: keep the ribbon hidden, never break the page
      }
    }

    fetchLiveFeed();
    setInterval(fetchLiveFeed, 60000);
    setInterval(nextActivity, 4500);
  })();

  // ── Wall of work: real approved LinkedIn posts; section stays hidden if there are none ──
  (async function initWallOfWork() {
    const section = document.getElementById('wall-of-work');
    const grid = document.getElementById('wall-grid');
    if (!section || !grid) return;
    try {
      const res = await fetch(`${apiBase()}/api/students/wall?limit=12`);
      if (!res.ok) return;
      const posts = ((await res.json()).posts || [])
        .filter(p => /^https:\/\/([a-z]{2,3}\.)?(www\.)?linkedin\.com\//i.test(p.url || ''));
      if (!posts.length) return;

      const el = (tag, cls, text) => {
        const node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text) node.textContent = text;
        return node;
      };
      posts.forEach(p => {
        const card = el('a', 'wall-card');
        card.href = p.url;
        card.target = '_blank';
        card.rel = 'noopener noreferrer';

        const head = el('div', 'wall-card-head');
        const initials = (p.name || 'S').split(/\s+/).map(w => w[0] || '').join('').slice(0, 2).toUpperCase();
        head.appendChild(el('div', 'wall-avatar', initials));
        const who = el('div', 'wall-who');
        who.appendChild(el('div', 'wall-name', p.name));
        if (p.college) who.appendChild(el('div', 'wall-college', p.college));
        head.appendChild(who);
        card.appendChild(head);

        const meta = el('div', 'wall-meta');
        meta.appendChild(el('strong', null, `Week ${p.week} approved`));
        meta.appendChild(document.createTextNode(` · ${p.domain}`));
        card.appendChild(meta);
        card.appendChild(el('span', 'wall-link', 'View post on LinkedIn ↗'));
        grid.appendChild(card);
      });
      section.hidden = false;
    } catch (_) {
      // Leave the section hidden — never show an empty or broken wall
    }
  })();

  // ── Domain category filter ──
  const filterTabs = document.querySelectorAll('.filter-tab');
  const domainCards = document.querySelectorAll('.domain-card');
  const domainCount = document.getElementById('domain-count');

  // Show a count on each category chip
  filterTabs.forEach(tab => {
    const cat = tab.getAttribute('data-category');
    if (cat === 'all' || tab.querySelector('.chip-count')) return;
    const n = Array.from(domainCards).filter(c => c.getAttribute('data-category') === cat).length;
    const badge = document.createElement('span');
    badge.className = 'chip-count mono';
    badge.textContent = n;
    tab.appendChild(document.createTextNode(' '));
    tab.appendChild(badge);
  });

  filterTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      filterTabs.forEach(t => {
        t.classList.remove('active');
        t.setAttribute('aria-pressed', 'false');
      });
      tab.classList.add('active');
      tab.setAttribute('aria-pressed', 'true');

      const selectedCat = tab.getAttribute('data-category');
      let shown = 0;
      domainCards.forEach(card => {
        const match = selectedCat === 'all' || card.getAttribute('data-category') === selectedCat;
        card.hidden = !match;
        card.classList.toggle('hidden', !match);
        if (match) shown++;
      });
      if (domainCount) domainCount.textContent = `Showing ${shown} domain${shown === 1 ? '' : 's'}`;
    });
  });

  // Domain cards: quiz first, or straight to the application once the quiz is done
  domainCards.forEach(card => {
    card.addEventListener('click', (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button === 1) return;
      e.preventDefault();
      const domainId = card.id.replace('domain-', '');
      window.location.href = quizDone() ? `apply.html?domain=${domainId}` : `quiz.html?domain=${domainId}`;
    });
  });

  // ── FAQ: single-open accordion, category filter and instant search ──
  const faqItems = document.querySelectorAll('.faq-item');
  const faqFilterPills = document.querySelectorAll('.faq-filter-pill');
  const faqSearchInput = document.getElementById('faq-search-input');
  const faqEmpty = document.getElementById('faq-empty');
  const faqCount = document.getElementById('faq-count');
  let activeFaqCategory = 'all';
  let faqSearchQuery = '';

  faqItems.forEach(item => {
    item.addEventListener('toggle', () => {
      item.classList.toggle('active', item.open);
      if (!item.open) return;
      faqItems.forEach(other => { if (other !== item && other.open) other.open = false; });
    });
    item.classList.toggle('active', item.open);
  });

  function updateFaqVisibility() {
    let shown = 0;
    faqItems.forEach(item => {
      const matchesCat = activeFaqCategory === 'all' || item.getAttribute('data-category') === activeFaqCategory;
      const matchesSearch = !faqSearchQuery || item.textContent.toLowerCase().includes(faqSearchQuery);
      const visible = matchesCat && matchesSearch;
      item.hidden = !visible;
      item.classList.toggle('hidden', !visible);
      if (visible) shown++;
    });
    if (faqEmpty) faqEmpty.hidden = shown > 0;
    if (faqCount) faqCount.textContent = `${shown} question${shown === 1 ? '' : 's'} shown`;
  }

  faqFilterPills.forEach(pill => {
    pill.addEventListener('click', () => {
      faqFilterPills.forEach(p => {
        p.classList.remove('active');
        p.setAttribute('aria-pressed', 'false');
      });
      pill.classList.add('active');
      pill.setAttribute('aria-pressed', 'true');
      activeFaqCategory = pill.getAttribute('data-category');
      updateFaqVisibility();
    });
  });

  if (faqSearchInput) {
    faqSearchInput.addEventListener('input', (e) => {
      faqSearchQuery = e.target.value.trim().toLowerCase();
      updateFaqVisibility();
    });
  }

  // ── Final CTA track pills: update the button label + quiz link ──
  const ctaTrackPills = document.querySelectorAll('.cta-track-pill');
  const ctaBtnLabel = document.getElementById('cta-btn-label');
  const ctaApplyBtn = document.getElementById('cta-apply-btn');

  ctaTrackPills.forEach(pill => {
    pill.addEventListener('click', () => {
      ctaTrackPills.forEach(p => {
        p.classList.remove('active');
        p.setAttribute('aria-pressed', 'false');
      });
      pill.classList.add('active');
      pill.setAttribute('aria-pressed', 'true');

      const domain = pill.getAttribute('data-domain');
      const name = pill.getAttribute('data-name');
      if (ctaBtnLabel) ctaBtnLabel.textContent = `Start screening for ${name}`;
      if (ctaApplyBtn) ctaApplyBtn.href = `quiz.html?domain=${domain}`;
    });
  });

  // ── Week explorer: accessible tabs (click + arrow keys) ──
  (function initWeekTabs() {
    const tabs = Array.from(document.querySelectorAll('.weeks-tab'));
    const bar = document.getElementById('weeks-bar');
    if (!tabs.length) return;

    function select(index, focus) {
      tabs.forEach((tab, i) => {
        const on = i === index;
        tab.setAttribute('aria-selected', String(on));
        tab.tabIndex = on ? 0 : -1;
        const panel = document.getElementById(tab.getAttribute('aria-controls'));
        if (panel) panel.hidden = !on;
      });
      if (bar) bar.style.width = `${((index + 1) / tabs.length) * 100}%`;
      if (focus) tabs[index].focus();
    }

    tabs.forEach((tab, i) => {
      tab.addEventListener('click', () => select(i, false));
      tab.addEventListener('keydown', (e) => {
        let next = null;
        if (e.key === 'ArrowRight') next = (i + 1) % tabs.length;
        else if (e.key === 'ArrowLeft') next = (i - 1 + tabs.length) % tabs.length;
        else if (e.key === 'Home') next = 0;
        else if (e.key === 'End') next = tabs.length - 1;
        if (next === null) return;
        e.preventDefault();
        select(next, true);
      });
    });
  })();

  // ── Nav scroll-spy: highlight the section in view ──
  (function initScrollSpy() {
    if (!('IntersectionObserver' in window)) return;
    const links = Array.from(document.querySelectorAll('.nav-links a[href^="index.html#"]'));
    const byId = new Map();
    links.forEach(a => {
      const section = document.getElementById(a.getAttribute('href').split('#')[1]);
      if (section) byId.set(section.id, a);
    });
    if (!byId.size) return;
    const io = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        const link = byId.get(entry.target.id);
        if (!link) return;
        if (entry.isIntersecting) {
          links.forEach(l => l.classList.remove('is-active'));
          link.classList.add('is-active');
        } else {
          link.classList.remove('is-active');
        }
      });
    }, { rootMargin: '-45% 0px -50% 0px' });
    byId.forEach((_, id) => io.observe(document.getElementById(id)));
  })();

  // ── Mobile sticky CTA: visible after the hero, hidden again at the final CTA ──
  (function initStickyCta() {
    const bar = document.getElementById('sticky-cta');
    const hero = document.getElementById('hero');
    const finalCta = document.getElementById('apply');
    if (!bar || !hero || !('IntersectionObserver' in window)) return;
    bar.hidden = false;
    let pastHero = false;
    let atFinal = false;
    const update = () => {
      const show = pastHero && !atFinal;
      bar.classList.toggle('is-visible', show);
      bar.setAttribute('aria-hidden', String(!show));
      bar.querySelectorAll('a').forEach(a => { a.tabIndex = show ? 0 : -1; });
    };
    new IntersectionObserver(([entry]) => {
      pastHero = !entry.isIntersecting && entry.boundingClientRect.top < 0;
      update();
    }).observe(hero);
    if (finalCta) {
      new IntersectionObserver(([entry]) => { atFinal = entry.isIntersecting; update(); }).observe(finalCta);
    }
    update();
  })();
});
