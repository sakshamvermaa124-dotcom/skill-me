/* ========================================
   SkillMe — Interactive Scripts v4
   Three.js Particle Galaxy  •  GSAP ScrollTrigger  •  Floating Wireframes
   Web3D Integration Patterns (Layered Separation Architecture)
   ======================================== */

document.addEventListener('DOMContentLoaded', () => {

  // ═══════════════════════════════════════════════════════════
  // LAYER 1: SMOOTH SCROLL (Lenis)
  // ═══════════════════════════════════════════════════════════
  const lenis = new Lenis({
    autoRaf: true,
    duration: 1.2,
    easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
    smoothWheel: true,
  });

  // ═══════════════════════════════════════════════════════════
  // SMART APPLY HANDLER (Quiz Gated vs Direct Application)
  // ═══════════════════════════════════════════════════════════
  window.handleApplyClick = function(e) {
    if (e && e.preventDefault) e.preventDefault();
    const quizDone = localStorage.getItem('skillme_quiz_result');
    if (quizDone) {
      window.location.href = 'apply.html';
    } else {
      window.location.href = 'quiz.html';
    }
  };

  document.querySelectorAll('#nav-apply-btn, #hero-apply-btn, #cta-apply-btn, .nav-cta').forEach(btn => {
    btn.addEventListener('click', window.handleApplyClick);
  });

  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', (e) => {
      const href = anchor.getAttribute('href');
      if (!href || href === '#') return;
      e.preventDefault();
      const target = document.querySelector(href);
      if (target) {
        lenis.scrollTo(target, { offset: -80, duration: 1.5 });
        navLinks.classList.remove('open');
        navToggle.classList.remove('active');
      }
    });
  });

  // ═══════════════════════════════════════════════════════════
  // NAVBAR
  // ═══════════════════════════════════════════════════════════
  const navbar    = document.getElementById('navbar');
  const navToggle = document.getElementById('nav-toggle');
  const navLinks  = document.getElementById('nav-links-center');

  if (navbar) {
    lenis.on('scroll', ({ scroll }) => navbar.classList.toggle('scrolled', scroll > 50));
  }

  if (navToggle && navLinks) {
    navToggle.addEventListener('click', () => {
      const isOpen = navLinks.classList.toggle('open');
      navToggle.classList.toggle('active', isOpen);
      document.body.style.overflow = isOpen ? 'hidden' : '';
    });
  }

  if (navLinks) {
    navLinks.querySelectorAll('a').forEach(link => link.addEventListener('click', () => {
      if (navToggle) navToggle.classList.remove('active');
      navLinks.classList.remove('open');
      document.body.style.overflow = '';
    }));
  }
  // Close mobile menu on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && navLinks && navLinks.classList.contains('open')) {
      if (navToggle) navToggle.classList.remove('active');
      navLinks.classList.remove('open');
      document.body.style.overflow = '';
    }
  });

  // Close mobile menu when clicking outside of it
  document.addEventListener('click', (e) => {
    if (navLinks && navLinks.classList.contains('open') &&
        !navLinks.contains(e.target) &&
        (!navToggle || !navToggle.contains(e.target))) {
      if (navToggle) navToggle.classList.remove('active');
      navLinks.classList.remove('open');
      document.body.style.overflow = '';
    }
  });

  // ═══════════════════════════════════════════════════════════
  // THEME TOGGLE — Light / Dark with localStorage persistence
  // ═══════════════════════════════════════════════════════════
  const themeToggle = document.getElementById('theme-toggle');
  const html = document.documentElement;

  // Restore saved preference
  const savedTheme = localStorage.getItem('skillme-theme') || 'dark';
  html.setAttribute('data-theme', savedTheme);

  themeToggle && themeToggle.addEventListener('click', () => {
    const current = html.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('skillme-theme', next);

    // Notify Three.js scenes of theme change
    window.dispatchEvent(new CustomEvent('themechange', { detail: { theme: next } }));

    // Animate the toggle button
    themeToggle.style.transform = 'rotate(360deg) scale(1.15)';
    setTimeout(() => { themeToggle.style.transform = ''; }, 500);
  });

  // ═══════════════════════════════════════════════════════════
  // LAYER 3: GSAP + ScrollTrigger (Taste-Skill Motion)
  // Fast, sub-300ms entrances without layout reflows or 3D blur
  // ═══════════════════════════════════════════════════════════
  (function initGSAP() {
    if (typeof gsap === 'undefined') return;

    gsap.registerPlugin(ScrollTrigger);

    // Sync ScrollTrigger with Lenis
    lenis.on('scroll', ScrollTrigger.update);
    gsap.ticker.add((time) => lenis.raf(time * 1000));
    gsap.ticker.lagSmoothing(0);

    // ── 1. Horizontal stagger reveal for step cards ──
    gsap.fromTo('.step-card', {
      opacity: 0, y: 24,
    }, {
      opacity: 1, y: 0,
      duration: 0.3,
      ease: 'power2.out',
      stagger: 0.08,
      scrollTrigger: {
        trigger: '.steps-grid',
        start: 'top 85%',
        toggleActions: 'play none none none',
      },
    });

    // ── 2. Benefit cards ──
    gsap.fromTo('.benefit-card', {
      opacity: 0, y: 24,
    }, {
      opacity: 1, y: 0,
      duration: 0.3,
      ease: 'power2.out',
      stagger: 0.06,
      scrollTrigger: {
        trigger: '.benefits-grid',
        start: 'top 85%',
        toggleActions: 'play none none none',
      },
    });

    // ── 3. Domain cards ──
    gsap.fromTo('.domain-card', {
      opacity: 0, y: 20,
    }, {
      opacity: 1, y: 0,
      duration: 0.25,
      ease: 'power2.out',
      stagger: 0.03,
      scrollTrigger: {
        trigger: '.domains-grid',
        start: 'top 85%',
        toggleActions: 'play none none none',
      },
    });

    // ── 4. Section headers ──
    gsap.utils.toArray('.section-header').forEach(header => {
      gsap.fromTo(header, {
        opacity: 0, y: 20,
      }, {
        opacity: 1, y: 0,
        duration: 0.35,
        ease: 'power2.out',
        scrollTrigger: {
          trigger: header,
          start: 'top 85%',
          toggleActions: 'play none none none',
        },
      });
    });

    // ── 5. Testimonials ──
    gsap.fromTo('.testimonial-card', {
      opacity: 0, y: 24,
    }, {
      opacity: 1, y: 0,
      duration: 0.3,
      ease: 'power2.out',
      stagger: 0.08,
      scrollTrigger: {
        trigger: '.testimonials-grid',
        start: 'top 85%',
        toggleActions: 'play none none none',
      },
    });

    // ── 6. CTA box ──
    gsap.fromTo('.cta-box', {
      opacity: 0, y: 24,
    }, {
      opacity: 1, y: 0,
      duration: 0.35,
      ease: 'power2.out',
      scrollTrigger: {
        trigger: '.cta-section',
        start: 'top 80%',
        toggleActions: 'play none none none',
      },
    });

    // ── 7. Credibility strip — pinned horizontal parallax ──
    gsap.to('.strip-track', {
      x: -60,
      ease: 'none',
      scrollTrigger: {
        trigger: '.credibility-strip',
        start: 'top bottom',
        end: 'bottom top',
        scrub: 1,
      },
    });



    // ── 9. Hero title — staggered word entrance on load ──
    gsap.fromTo('.hero-title .line', {
      opacity: 0, y: 80,
    }, {
      opacity: 1, y: 0,
      duration: 1.2,
      ease: 'power4.out',
      stagger: 0.2,
      delay: 0.3,
    });

    gsap.fromTo(['.hero-badge', '.hero-description', '.hero-highlight', '.hero-actions', '.hero-stats'], {
      opacity: 0, y: 40,
    }, {
      opacity: 1, y: 0,
      duration: 1.0,
      ease: 'power3.out',
      stagger: 0.12,
      delay: 0.6,
    });

    gsap.fromTo('.hero-visual', {
      opacity: 0, x: 60, rotateY: -10,
    }, {
      opacity: 1, x: 0, rotateY: 0,
      duration: 1.4,
      ease: 'power3.out',
      delay: 0.5,
    });

  })();

  // ═══════════════════════════════════════════════════════════
  // SCROLL REVEAL (fallback for non-GSAP elements)
  // ═══════════════════════════════════════════════════════════
  const revealElements = document.querySelectorAll('.reveal');
  const revealObs = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('visible'); });
  }, { threshold: 0, rootMargin: '0px 0px -30px 0px' });
  revealElements.forEach(el => revealObs.observe(el));

  window.addEventListener('load', () => {
    revealElements.forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.top < window.innerHeight && r.bottom > 0) el.classList.add('visible');
    });
  });

  // ═══════════════════════════════════════════════════════════
  // TERMINAL ANIMATION
  // ═══════════════════════════════════════════════════════════
  const terminalBody = document.getElementById('terminal-body');
  const terminalLines = [
    { type: 'command', prompt: '$ ', text: 'git clone https://github.com/skillme-oss/web-project.git', delay: 0 },
    { type: 'output',  text: 'Cloning into \'web-project\'...', delay: 700 },
    { type: 'output',  text: '✓ Done.', class: 'success', delay: 1200 },
    { type: 'empty',   delay: 1500 },
    { type: 'command', prompt: '$ ', text: 'git checkout -b fix/navbar-bug', delay: 1900 },
    { type: 'output',  text: 'Switched to new branch \'fix/navbar-bug\'', delay: 2600 },
    { type: 'empty',   delay: 2900 },
    { type: 'comment', text: '# Fix the issue, write clean code...', delay: 3200 },
    { type: 'empty',   delay: 3500 },
    { type: 'command', prompt: '$ ', text: 'git add . && git commit -m "fix: resolve navbar overflow"', delay: 3900 },
    { type: 'output',  text: '[fix/navbar-bug 3a2f1c9] fix: resolve navbar overflow', delay: 4600 },
    { type: 'command', prompt: '$ ', text: 'git push origin fix/navbar-bug', delay: 5100 },
    { type: 'output',  text: 'PR → https://github.com/skillme-oss/.../pull/42', class: 'url', delay: 5800 },
    { type: 'empty',   delay: 6100 },
    { type: 'output',  text: '✅ PR merged! +350 contribution score added.', class: 'success', delay: 6600 },
  ];

  let terminalDone = false;
  function animateTerminal() {
    if (terminalDone || !terminalBody) return;
    terminalDone = true;
    terminalBody.innerHTML = '';
    terminalLines.forEach(line => {
      const el = document.createElement('div');
      el.classList.add('terminal-line');
      el.style.animationDelay = `${line.delay}ms`;
      if (line.type === 'empty') {
        el.innerHTML = '&nbsp;';
      } else if (line.type === 'command') {
        el.innerHTML = `<span class="prompt">${line.prompt}</span><span class="command">${line.text}</span>`;
      } else if (line.type === 'comment') {
        el.innerHTML = `<span class="comment">${line.text}</span>`;
      } else {
        el.innerHTML = `<span class="${line.class || 'output'}">${line.text}</span>`;
      }
      terminalBody.appendChild(el);
    });
    const cursor = document.createElement('div');
    cursor.classList.add('terminal-line');
    cursor.style.animationDelay = `${terminalLines.at(-1).delay + 700}ms`;
    cursor.innerHTML = `<span class="prompt">$ </span><span class="terminal-cursor"></span>`;
    terminalBody.appendChild(cursor);
  }

  new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) {
      setTimeout(animateTerminal, 400);
      entries[0].target._observer?.unobserve(entries[0].target);
    }
  }, { threshold: 0.2 }).observe(document.getElementById('terminal-card') || document.body);

  // ═══════════════════════════════════════════════════════════
  // FAQ ACCORDION
  // ═══════════════════════════════════════════════════════════
  document.querySelectorAll('.faq-item').forEach(item => {
    item.querySelector('.faq-question').addEventListener('click', () => {
      const isActive = item.classList.contains('active');
      document.querySelectorAll('.faq-item').forEach(i => {
        i.classList.remove('active');
        i.querySelector('.faq-question').setAttribute('aria-expanded', 'false');
      });
      if (!isActive) {
        item.classList.add('active');
        item.querySelector('.faq-question').setAttribute('aria-expanded', 'true');
      }
    });
  });

  // ═══════════════════════════════════════════════════════════
  // 3D TILT — shared for all interactive cards
  // ═══════════════════════════════════════════════════════════
  function addTilt(selector, strength = 6) {
    // Skip tilt on touch devices
    if (!matchMedia('(hover: hover) and (pointer: fine)').matches) return;
    document.querySelectorAll(selector).forEach(card => {
      card.addEventListener('mousemove', (e) => {
        const r = card.getBoundingClientRect();
        const rX = ((e.clientY - r.top)  / r.height - 0.5) * strength;
        const rY = ((e.clientX - r.left) / r.width  - 0.5) * -strength;
        card.style.transform = `perspective(800px) rotateX(${rX}deg) rotateY(${rY}deg) translateY(-3px)`;
      });
      card.addEventListener('mouseenter', () => { card.style.transition = 'transform 0.1s ease'; });
      card.addEventListener('mouseleave', () => {
        card.style.transform = 'perspective(800px) rotateX(0) rotateY(0) translateY(0)';
        card.style.transition = 'transform 0.5s cubic-bezier(0.23,1,0.32,1)';
      });
    });
  }

  addTilt('.domain-card', 5);
  addTilt('.testimonial-card', 4);
  addTilt('.step-card', 5);

  // ═══════════════════════════════════════════════════════════
  // LIVE REAL-TIME PROOF-OF-WORK ACTIVITY TICKER ENGINE
  // ═══════════════════════════════════════════════════════════
  (function initLiveActivityTicker() {
    const ribbon = document.getElementById('live-activity-ribbon');
    const item = document.getElementById('live-ticker-item');
    const avatarEl = document.getElementById('ticker-avatar');
    const userEl = document.getElementById('ticker-user');
    const collegeEl = document.getElementById('ticker-college');
    const actionEl = document.getElementById('ticker-action');
    const timeEl = document.getElementById('ticker-time');
    const prCountEl = document.getElementById('ticker-pr-count');
    const collegeCountEl = document.getElementById('ticker-college-count');

    if (!ribbon || !item) return;

    // Resilient starter pool for instant render without network lag
    let activities = [
      { initials: "RS", name: "Rahul S.", college: "AKTU", action: "merged PR for FastAPI Endpoint Auth", time: "3m ago" },
      { initials: "SM", name: "Sneha M.", college: "VTU", action: "completed 4-Week Python & API Track", time: "11m ago" },
      { initials: "AV", name: "Aman V.", college: "IPU Delhi", action: "merged Model Evaluation Pipeline", time: "19m ago" },
      { initials: "PK", name: "Priya K.", college: "Anna Univ", action: "unlocked Verified Full-Stack LOR", time: "34m ago" },
      { initials: "RD", name: "Rohan D.", college: "Pune Univ", action: "resolved Responsive Grid System issue", time: "52m ago" },
      { initials: "TG", name: "Tanvi G.", college: "RTU Kota", action: "qualified for Monthly Performance Stipend", time: "1h ago" },
      { initials: "HN", name: "Harsh N.", college: "GTU", action: "merged PR #33 on SQLite Database Client", time: "1h 15m ago" }
    ];

    let currentIndex = 0;
    let isPaused = false;
    let rotationInterval = null;

    function renderItem(act) {
      if (!act) return;
      item.classList.add('switching');
      setTimeout(() => {
        if (avatarEl) avatarEl.textContent = act.student_initials || act.initials || "SM";
        if (userEl) userEl.textContent = act.student_name || act.name || "Student Contributor";
        if (collegeEl) collegeEl.textContent = act.college || "Engineering College";
        if (actionEl) actionEl.textContent = act.action_text || act.action || "merged verified PR";
        if (timeEl) timeEl.textContent = act.time_ago || act.time || "Just now";
        item.classList.remove('switching');
      }, 350);
    }

    function nextActivity() {
      if (isPaused || activities.length === 0) return;
      currentIndex = (currentIndex + 1) % activities.length;
      renderItem(activities[currentIndex]);
    }

    function startRotation() {
      if (rotationInterval) clearInterval(rotationInterval);
      rotationInterval = setInterval(nextActivity, 4500);
    }

    // Hover pause
    ribbon.addEventListener('mouseenter', () => { isPaused = true; });
    ribbon.addEventListener('mouseleave', () => { isPaused = false; });
    ribbon.addEventListener('touchstart', () => { isPaused = true; }, { passive: true });
    ribbon.addEventListener('touchend', () => { isPaused = false; }, { passive: true });

    // Fetch live production feed asynchronously from API
    async function fetchLiveFeed() {
      try {
        const apiBase = window.SKILLME_API || (window.location.hostname === 'localhost' ? 'http://localhost:8000' : 'https://skill-me.onrender.com');
        const res = await fetch(`${apiBase}/api/students/public-activity`);
        if (res.ok) {
          const data = await res.json();
          if (data && data.activities && data.activities.length > 0) {
            activities = data.activities;
          }
          if (data && data.stats) {
            if (prCountEl && data.stats.total_prs_merged) {
              prCountEl.textContent = `${data.stats.total_prs_merged}+`;
            }
            if (collegeCountEl && data.stats.total_colleges) {
              collegeCountEl.textContent = `${data.stats.total_colleges}+`;
            }
          }
        }
      } catch (err) {
        // Silently preserve offline resilient pool without crashing
      }
    }

    fetchLiveFeed();
    // Poll updates every 60 seconds in the background
    setInterval(fetchLiveFeed, 60000);
    startRotation();
  })();

  // ═══════════════════════════════════════════════════════════
  // BENEFIT CARD SPOTLIGHT
  // ═══════════════════════════════════════════════════════════
  document.querySelectorAll('.benefit-card').forEach(card => {
    if (!matchMedia('(hover: hover) and (pointer: fine)').matches) return;
    card.addEventListener('mousemove', (e) => {
      const r = card.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      const color = card.classList.contains('featured')
        ? 'rgba(52, 211, 153, 0.05)'
        : card.classList.contains('placement')
          ? 'rgba(245, 158, 11, 0.05)'
          : 'rgba(34, 211, 238, 0.035)';
      card.style.background = `radial-gradient(circle 240px at ${x}px ${y}px, ${color}, var(--bg-card))`;
    });
    card.addEventListener('mouseleave', () => { card.style.background = ''; });
  });

  // ═══════════════════════════════════════════════════════════
  // MAGNETIC BUTTONS
  // ═══════════════════════════════════════════════════════════
  if (matchMedia('(hover: hover) and (pointer: fine)').matches) {
    document.querySelectorAll('.btn-primary, .nav-cta').forEach(btn => {
      btn.addEventListener('mousemove', (e) => {
        const r = btn.getBoundingClientRect();
        const x = (e.clientX - r.left - r.width  / 2) * 0.12;
        const y = (e.clientY - r.top  - r.height / 2) * 0.12;
        btn.style.transform = `translate(${x}px, ${y}px) translateY(-2px)`;
      });
      btn.addEventListener('mouseenter', () => { btn.style.transition = 'transform 0.1s ease, box-shadow 0.3s ease'; });
      btn.addEventListener('mouseleave', () => {
        btn.style.transform = '';
        btn.style.transition = 'transform 0.5s cubic-bezier(0.23,1,0.32,1), box-shadow 0.3s ease';
      });
    });
  }

  // ═══════════════════════════════════════════════════════════
  // DOMAIN CATEGORY TAB FILTERING
  // ═══════════════════════════════════════════════════════════
  const filterTabs = document.querySelectorAll('.filter-tab');
  const domainCards = document.querySelectorAll('.domain-card');

  filterTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      filterTabs.forEach(t => {
        t.classList.remove('active');
        t.setAttribute('aria-selected', 'false');
      });
      tab.classList.add('active');
      tab.setAttribute('aria-selected', 'true');

      const selectedCat = tab.getAttribute('data-category');

      domainCards.forEach(card => {
        const cardCat = card.getAttribute('data-category');
        if (selectedCat === 'all' || cardCat === selectedCat) {
          card.classList.remove('hidden');
        } else {
          card.classList.add('hidden');
        }
      });
    });
  });

  // ═══════════════════════════════════════════════════════════
  // FAQ CATEGORY TABS & INSTANT SEARCH
  // ═══════════════════════════════════════════════════════════
  const faqFilterPills = document.querySelectorAll('.faq-filter-pill');
  const faqItems = document.querySelectorAll('.faq-item');
  const faqSearchInput = document.getElementById('faq-search-input');

  let activeFaqCategory = 'all';
  let faqSearchQuery = '';

  function updateFaqVisibility() {
    faqItems.forEach(item => {
      const itemCat = item.getAttribute('data-category');
      const itemText = item.textContent.toLowerCase();

      const matchesCat = activeFaqCategory === 'all' || itemCat === activeFaqCategory;
      const matchesSearch = !faqSearchQuery || itemText.includes(faqSearchQuery);

      if (matchesCat && matchesSearch) {
        item.classList.remove('hidden');
      } else {
        item.classList.add('hidden');
      }
    });
  }

  faqFilterPills.forEach(pill => {
    pill.addEventListener('click', () => {
      faqFilterPills.forEach(p => {
        p.classList.remove('active');
        p.setAttribute('aria-selected', 'false');
      });
      pill.classList.add('active');
      pill.setAttribute('aria-selected', 'true');

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

  // ═══════════════════════════════════════════════════════════
  // CTA LAUNCHPAD DOMAIN SELECTOR
  // ═══════════════════════════════════════════════════════════
  const ctaTrackPills = document.querySelectorAll('.cta-track-pill');
  const ctaBtnLabel = document.getElementById('cta-btn-label');
  const ctaApplyBtn = document.getElementById('cta-apply-btn');

  ctaTrackPills.forEach(pill => {
    pill.addEventListener('click', () => {
      ctaTrackPills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');

      const domain = pill.getAttribute('data-domain');
      const name = pill.getAttribute('data-name');

      if (ctaBtnLabel) {
        ctaBtnLabel.textContent = `Start Screening for ${name}`;
      }
      if (ctaApplyBtn) {
        ctaApplyBtn.href = `quiz.html?domain=${domain}`;
      }
    });
  });

});



