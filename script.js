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
  const navLinks  = document.getElementById('nav-links');

  lenis.on('scroll', ({ scroll }) => navbar.classList.toggle('scrolled', scroll > 50));

  navToggle.addEventListener('click', () => {
    const isOpen = navLinks.classList.toggle('open');
    navToggle.classList.toggle('active', isOpen);
    document.body.style.overflow = isOpen ? 'hidden' : '';
  });

  navLinks.querySelectorAll('a').forEach(link => link.addEventListener('click', () => {
    navToggle.classList.remove('active');
    navLinks.classList.remove('open');
    document.body.style.overflow = '';
  }));

  // Close mobile menu on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && navLinks.classList.contains('open')) {
      navToggle.classList.remove('active');
      navLinks.classList.remove('open');
      document.body.style.overflow = '';
    }
  });

  // Close mobile menu when clicking outside of it
  document.addEventListener('click', (e) => {
    if (navLinks.classList.contains('open') &&
        !navLinks.contains(e.target) &&
        !navToggle.contains(e.target)) {
      navToggle.classList.remove('active');
      navLinks.classList.remove('open');
      document.body.style.overflow = '';
    }
  });

  // ═══════════════════════════════════════════════════════════
  // THEME TOGGLE — Light / Dark with localStorage persistence
  // ═══════════════════════════════════════════════════════════
  

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
    if (terminalDone) return;
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

});
