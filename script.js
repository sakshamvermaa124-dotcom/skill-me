/* =============================================================
   script.js — SkillMe home page (index.html only)
   Theme, sticky nav, mobile drawer and .reveal are handled by theme.js.
   This file keeps the page's functional features:
   - Apply links (quiz-gated: apply.html once the quiz is done)
   - Same-page anchor scrolling
   - Live activity ticker   GET /api/students/public-activity
   - Wall of work           GET /api/students/wall?limit=12
   - Track search + category filter + track card links
   - Week explorer tabs (W1–W4)
   - FAQ search, category filter, single-open accordion
   - Final CTA track pills (label + link)
   - Nav scroll-spy and the mobile sticky CTA
   ============================================================= */
document.addEventListener('DOMContentLoaded', () => {
  'use strict';

  const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const apiBase = () => window.SKILLME_API || '';

  // Homepage track ids → the ids the quiz and backend use (quiz.html has the same map)
  const DOMAIN_ALIASES = { webdev: 'web-dev', datascience: 'data-science', node: 'nodejs', cyber: 'cybersecurity', uiux: 'ui-ux' };
  const normDomain = (id) => DOMAIN_ALIASES[id] || id;
  const quizDomain = () => {
    try { return (JSON.parse(localStorage.getItem('skillme_quiz_result') || 'null') || {}).domain || null; }
    catch (e) { return null; }
  };

  // Where an Apply click should land: the application if the quiz was already taken for
  // this track, otherwise the quiz (pre-selected to the clicked track, if any).
  function applyTarget(domainId) {
    const done = quizDomain();
    if (!domainId) return done ? '/apply' : '/quiz';
    if (done && normDomain(domainId) === done) return '/apply';
    return `/quiz?domain=${encodeURIComponent(domainId)}`;
  }

  // ── Apply links: once the quiz is done for that track, go straight to the application ──
  window.handleApplyClick = function (e) {
    if (e && e.preventDefault) e.preventDefault();
    const targetUrl = (e && e.currentTarget && e.currentTarget.getAttribute('href')) || '';
    const match = targetUrl.match(/[?&]domain=([^&#]+)/);
    window.location.href = applyTarget(match ? decodeURIComponent(match[1]) : null);
  };
  document.querySelectorAll('#nav-apply-btn, #hero-apply-btn, #cta-apply-btn, [data-apply]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      // Let modified clicks (new tab, etc.) behave like a normal link
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      window.handleApplyClick(e);
    });
  });

  // ── Same-page anchors (#id, /#id and index.html#id) ──
  document.querySelectorAll('a[href^="#"], a[href^="/#"], a[href^="/#"]').forEach(anchor => {
    anchor.addEventListener('click', (e) => {
      const hash = anchor.getAttribute('href').replace(/^(index\.html|\/)(?=#)/, '');
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
    setInterval(() => { if (!document.hidden) fetchLiveFeed(); }, 60000);
    if (!reduceMotion) setInterval(() => { if (!document.hidden) nextActivity(); }, 4500);
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

  // ── Tracks: category filter + search ──
  const filterTabs = document.querySelectorAll('.filter-tab');
  const domainCards = document.querySelectorAll('.domain-card');
  const domainCount = document.getElementById('domain-count');
  const domainSearch = document.getElementById('domain-search-input');
  const domainEmpty = document.getElementById('domain-empty');
  let activeDomainCategory = 'all';
  let domainQuery = '';

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

  // Extra words people search for that aren't printed on the card
  const TRACK_KEYWORDS = {
    webdev: 'web website full stack frontend backend html css javascript js',
    react: 'web frontend front end ui react next typescript js',
    node: 'web backend back end server api express javascript js',
    uiux: 'ui ux design designer figma web product',
    python: 'python backend automation scripting',
    'ai-engineer': 'ai llm gpt agents rag machine learning',
    genai: 'ai llm gpt chatgpt prompt generative',
    ml: 'ai machine learning data model deep learning',
    datascience: 'data analytics analysis sql python ai',
    'ai-pm': 'ai product manager management pm',
    sde: 'software engineer swe dsa algorithms coding interview',
    java: 'java spring backend',
    cpp: 'c c++ cpp dsa algorithms competitive',
    devops: 'devops ci cd docker kubernetes cloud',
    cloud: 'cloud aws azure gcp devops',
    flutter: 'mobile app android ios flutter dart',
    cyber: 'security cyber hacking ethical web security',
    sql: 'sql database data postgres mysql',
    fde: 'forward deployed engineer customer solutions',
    qa: 'testing qa quality automation selenium',
  };
  const categoryLabel = (cat) => {
    const chip = Array.from(filterTabs).find(t => t.getAttribute('data-category') === cat);
    return chip ? chip.textContent.replace(/\d+/g, '').trim() : '';
  };
  const searchText = new Map();
  domainCards.forEach(card => {
    const id = card.id.replace('domain-', '');
    const title = card.querySelector('h3') ? card.querySelector('h3').textContent : '';
    const tech = card.querySelector('.domain-tech') ? card.querySelector('.domain-tech').textContent : '';
    searchText.set(card, `${title} ${tech} ${categoryLabel(card.getAttribute('data-category'))} ${TRACK_KEYWORDS[id] || ''}`.toLowerCase());
  });

  // Empty results: say what's filtering them out, and offer one click to reset.
  function renderEmpty(el, what, query, category, reset) {
    el.replaceChildren();
    const filter = category !== 'all' ? ` in “${category}”` : '';
    el.append(query ? `No ${what} match “${query}”${filter}. ` : `No ${what}${filter}. `);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn-link';
    btn.textContent = 'Clear filters';
    btn.addEventListener('click', reset);
    el.append(btn);
  }

  function updateDomainVisibility() {
    let shown = 0;
    domainCards.forEach(card => {
      const matchesCat = activeDomainCategory === 'all' || card.getAttribute('data-category') === activeDomainCategory;
      const matchesSearch = !domainQuery || searchText.get(card).includes(domainQuery);
      const visible = matchesCat && matchesSearch;
      card.hidden = !visible;
      if (visible) shown++;
    });
    if (domainEmpty) {
      domainEmpty.hidden = shown > 0;
      if (!shown) renderEmpty(domainEmpty, 'tracks', domainQuery, categoryLabel(activeDomainCategory) && activeDomainCategory !== 'all' ? categoryLabel(activeDomainCategory) : 'all', resetDomainFilters);
    }
    if (domainCount) domainCount.textContent = `Showing ${shown} track${shown === 1 ? '' : 's'}`;
  }

  function resetDomainFilters() {
    domainQuery = '';
    if (domainSearch) domainSearch.value = '';
    const all = Array.from(filterTabs).find(t => t.getAttribute('data-category') === 'all');
    if (all) all.click(); else updateDomainVisibility();
    if (domainSearch) domainSearch.focus();
  }

  // "All tracks" count comes from the page, not a hand-typed number
  const domainAllCount = document.querySelector('.filter-tab[data-category="all"] .chip-count');
  if (domainAllCount) domainAllCount.textContent = domainCards.length;

  filterTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      filterTabs.forEach(t => t.setAttribute('aria-pressed', 'false'));
      tab.setAttribute('aria-pressed', 'true');
      activeDomainCategory = tab.getAttribute('data-category');
      updateDomainVisibility();
    });
  });

  if (domainSearch) {
    domainSearch.addEventListener('input', (e) => {
      domainQuery = e.target.value.trim().toLowerCase();
      updateDomainVisibility();
    });
  }

  // Domain cards: quiz first, or straight to the application once the quiz is done
  domainCards.forEach(card => {
    card.addEventListener('click', (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      window.location.href = applyTarget(card.id.replace('domain-', ''));
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

  const faqAllCount = document.querySelector('.faq-filter-pill[data-category="all"] .chip-count');
  if (faqAllCount) faqAllCount.textContent = faqItems.length;

  faqItems.forEach(item => {
    item.addEventListener('toggle', () => {
      if (!item.open) return;
      faqItems.forEach(other => { if (other !== item && other.open) other.open = false; });
    });
  });

  function updateFaqVisibility() {
    let shown = 0;
    faqItems.forEach(item => {
      const matchesCat = activeFaqCategory === 'all' || item.getAttribute('data-category') === activeFaqCategory;
      const matchesSearch = !faqSearchQuery || item.textContent.toLowerCase().includes(faqSearchQuery);
      const visible = matchesCat && matchesSearch;
      item.hidden = !visible;
      if (visible) {
        shown++;
        const num = item.querySelector('.faq-num');
        if (num) num.textContent = String(shown).padStart(2, '0');
      }
    });
    // Searching: open the first hit so the matching answer is visible
    if (faqSearchQuery) {
      const first = Array.from(faqItems).find(i => !i.hidden);
      if (first && !first.open) first.open = true;
    }
    if (faqEmpty) {
      faqEmpty.hidden = shown > 0;
      if (!shown) {
        const pill = Array.from(faqFilterPills).find(p => p.getAttribute('data-category') === activeFaqCategory);
        const label = activeFaqCategory === 'all' || !pill ? 'all' : pill.textContent.replace(/\d+/g, '').trim();
        renderEmpty(faqEmpty, 'questions', faqSearchQuery, label, () => {
          faqSearchQuery = '';
          if (faqSearchInput) faqSearchInput.value = '';
          const all = Array.from(faqFilterPills).find(p => p.getAttribute('data-category') === 'all');
          if (all) all.click(); else updateFaqVisibility();
          if (faqSearchInput) faqSearchInput.focus();
        });
        const contact = document.createElement('a');
        contact.href = '/contact';
        contact.className = 'btn-link';
        contact.textContent = 'contact us';
        faqEmpty.append(' or ', contact, '.');
      }
    }
    if (faqCount) faqCount.textContent = `${shown} question${shown === 1 ? '' : 's'} shown`;
  }

  faqFilterPills.forEach(pill => {
    pill.addEventListener('click', () => {
      faqFilterPills.forEach(p => p.setAttribute('aria-pressed', 'false'));
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
      ctaTrackPills.forEach(p => { p.setAttribute('aria-checked', 'false'); p.tabIndex = -1; });
      pill.setAttribute('aria-checked', 'true');
      pill.tabIndex = 0;

      const domain = pill.getAttribute('data-domain');
      const name = pill.getAttribute('data-name');
      if (ctaBtnLabel) ctaBtnLabel.textContent = `Start my ${name} internship`;
      if (ctaApplyBtn) ctaApplyBtn.href = `/quiz?domain=${domain}`;
    });
    // Arrow keys move between the options, like native radios
    pill.addEventListener('keydown', (e) => {
      const list = Array.from(ctaTrackPills);
      const i = list.indexOf(pill);
      const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      if (!step) return;
      e.preventDefault();
      const next = list[(i + step + list.length) % list.length];
      next.click();
      next.focus();
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
    const links = Array.from(document.querySelectorAll('.nav-links a[href^="/#"], .nav-links a[href^="/#"]'));
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
          links.forEach(l => { l.classList.remove('is-active'); l.removeAttribute('aria-current'); });
          link.classList.add('is-active');
          link.setAttribute('aria-current', 'location');
        } else {
          link.classList.remove('is-active');
          link.removeAttribute('aria-current');
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
    let typing = false;
    const update = () => {
      const show = pastHero && !atFinal && !typing;
      bar.classList.toggle('is-visible', show);
      bar.setAttribute('aria-hidden', String(!show));
      bar.querySelectorAll('a').forEach(a => { a.tabIndex = show ? 0 : -1; });
    };
    new IntersectionObserver(([entry]) => {
      pastHero = !entry.isIntersecting && entry.boundingClientRect.top < 0;
      update();
    }).observe(hero);
    if (finalCta) {
      // "At or past" the final CTA: the bar must not come back over the footer
      new IntersectionObserver(([entry]) => {
        atFinal = entry.isIntersecting || entry.boundingClientRect.top < 0;
        update();
      }).observe(finalCta);
    }
    // On phones the bar would ride above the keyboard and cover search results
    document.addEventListener('focusin', (e) => { if (e.target.matches('main input, main textarea')) { typing = true; update(); } });
    document.addEventListener('focusout', (e) => { if (e.target.matches('main input, main textarea')) { typing = false; update(); } });
    update();
  })();
});
