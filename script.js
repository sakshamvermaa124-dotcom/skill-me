/* ========================================
   SkillMe — Interactive Scripts
   Lenis Smooth Scroll + Animations
   ======================================== */

document.addEventListener('DOMContentLoaded', () => {

  // ========================================
  // LENIS SMOOTH SCROLL
  // ========================================
  const lenis = new Lenis({
    autoRaf: true,
    duration: 1.2,
    easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
    orientation: 'vertical',
    smoothWheel: true,
  });

  // Smooth scroll for anchor links
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', (e) => {
      const href = anchor.getAttribute('href');
      if (!href || href === '#') return; // Skip bare hash links
      e.preventDefault();
      const target = document.querySelector(href);
      if (target) {
        lenis.scrollTo(target, {
          offset: -80,
          duration: 1.5,
        });
        // Close mobile menu if open
        navLinks.classList.remove('open');
        navToggle.classList.remove('active');
      }
    });
  });

  // ========================================
  // NAVBAR SCROLL EFFECT
  // ========================================
  const navbar = document.getElementById('navbar');
  
  lenis.on('scroll', ({ scroll }) => {
    if (scroll > 50) {
      navbar.classList.add('scrolled');
    } else {
      navbar.classList.remove('scrolled');
    }
  });

  // ========================================
  // MOBILE MENU TOGGLE
  // ========================================
  const navToggle = document.getElementById('nav-toggle');
  const navLinks = document.getElementById('nav-links');

  navToggle.addEventListener('click', () => {
    navToggle.classList.toggle('active');
    navLinks.classList.toggle('open');
  });

  // Close on link click
  navLinks.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      navToggle.classList.remove('active');
      navLinks.classList.remove('open');
    });
  });

  // ========================================
  // SCROLL REVEAL ANIMATIONS
  // ========================================
  const revealElements = document.querySelectorAll('.reveal');
  
  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        // Don't unobserve — keep it simple
      }
    });
  }, {
    threshold: 0,
    rootMargin: '0px 0px -20px 0px',
  });

  revealElements.forEach(el => revealObserver.observe(el));

  // ========================================
  // TERMINAL TYPING ANIMATION
  // ========================================
  const terminalBody = document.getElementById('terminal-body');
  
  const terminalLines = [
    { type: 'command', prompt: '$ ', text: 'git clone https://github.com/skillme-oss/web-project.git', delay: 0 },
    { type: 'output', text: 'Cloning into \'web-project\'...', delay: 800 },
    { type: 'output', text: 'Done. ✓', class: 'success', delay: 1400 },
    { type: 'empty', delay: 1800 },
    { type: 'command', prompt: '$ ', text: 'cd web-project && git checkout -b fix/navbar-bug', delay: 2200 },
    { type: 'output', text: 'Switched to new branch \'fix/navbar-bug\'', class: 'output', delay: 3000 },
    { type: 'empty', delay: 3400 },
    { type: 'comment', text: '# Fix the issue, write clean code...', delay: 3800 },
    { type: 'empty', delay: 4200 },
    { type: 'command', prompt: '$ ', text: 'git add . && git commit -m "fix: resolve navbar overflow"', delay: 4600 },
    { type: 'output', text: '[fix/navbar-bug 3a2f1c9] fix: resolve navbar overflow', class: 'output', delay: 5400 },
    { type: 'empty', delay: 5800 },
    { type: 'command', prompt: '$ ', text: 'git push origin fix/navbar-bug', delay: 6200 },
    { type: 'output', text: 'remote: Create a pull request:', class: 'output', delay: 7000 },
    { type: 'output', text: 'https://github.com/skillme-oss/web-project/pull/42', class: 'url', delay: 7400 },
    { type: 'empty', delay: 7800 },
    { type: 'output', text: '✅ PR merged! Open source contribution earned.', class: 'success', delay: 8400 },
  ];

  let terminalAnimated = false;

  function animateTerminal() {
    if (terminalAnimated) return;
    terminalAnimated = true;
    
    terminalBody.innerHTML = '';
    
    terminalLines.forEach((line, index) => {
      const lineEl = document.createElement('div');
      lineEl.classList.add('terminal-line');
      lineEl.style.animationDelay = `${line.delay}ms`;
      
      if (line.type === 'empty') {
        lineEl.innerHTML = '&nbsp;';
      } else if (line.type === 'command') {
        lineEl.innerHTML = `<span class="prompt">${line.prompt}</span><span class="command">${line.text}</span>`;
      } else if (line.type === 'comment') {
        lineEl.innerHTML = `<span class="comment">${line.text}</span>`;
      } else if (line.type === 'output') {
        lineEl.innerHTML = `<span class="${line.class || 'output'}">${line.text}</span>`;
      }
      
      terminalBody.appendChild(lineEl);
    });

    // Add blinking cursor at the end
    const cursorLine = document.createElement('div');
    cursorLine.classList.add('terminal-line');
    cursorLine.style.animationDelay = `${terminalLines[terminalLines.length - 1].delay + 800}ms`;
    cursorLine.innerHTML = `<span class="prompt">$ </span><span class="terminal-cursor"></span>`;
    terminalBody.appendChild(cursorLine);
  }

  // Trigger terminal animation when hero is visible
  const heroObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        setTimeout(animateTerminal, 600);
        heroObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.3 });

  const terminalCard = document.getElementById('terminal-card');
  if (terminalCard) heroObserver.observe(terminalCard);

  // ========================================
  // FAQ ACCORDION
  // ========================================
  const faqItems = document.querySelectorAll('.faq-item');

  faqItems.forEach(item => {
    const question = item.querySelector('.faq-question');
    
    question.addEventListener('click', () => {
      const isActive = item.classList.contains('active');
      
      // Close all
      faqItems.forEach(i => {
        i.classList.remove('active');
        i.querySelector('.faq-question').setAttribute('aria-expanded', 'false');
      });
      
      // Open clicked (if it wasn't already open)
      if (!isActive) {
        item.classList.add('active');
        question.setAttribute('aria-expanded', 'true');
      }
    });
  });

  // ========================================
  // DOMAIN CARD HOVER TILT EFFECT
  // ========================================
  const domainCards = document.querySelectorAll('.domain-card');

  domainCards.forEach(card => {
    card.addEventListener('mousemove', (e) => {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      const rotateX = (y - centerY) / 15;
      const rotateY = (centerX - x) / 15;
      
      card.style.transform = `perspective(800px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-4px)`;
    });

    card.addEventListener('mouseleave', () => {
      card.style.transform = 'perspective(800px) rotateX(0) rotateY(0) translateY(0)';
    });
  });

  // ========================================
  // ANIMATED COUNTER (for stats)
  // ========================================
  function animateCounter(element, target, suffix = '') {
    const duration = 2000;
    const start = 0;
    const startTime = performance.now();

    function update(currentTime) {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = Math.floor(start + (target - start) * eased);
      
      element.textContent = current + suffix;
      
      if (progress < 1) {
        requestAnimationFrame(update);
      }
    }

    requestAnimationFrame(update);
  }

  // Observe stats for counter animation
  const statNumbers = document.querySelectorAll('.stat-number[data-count]');
  
  const counterObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const target = parseInt(entry.target.dataset.count, 10);
        animateCounter(entry.target, target, '+');
        counterObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.5 });

  statNumbers.forEach(el => counterObserver.observe(el));

  // ========================================
  // BENEFIT CARD GLOW EFFECT
  // ========================================
  const benefitCards = document.querySelectorAll('.benefit-card');

  benefitCards.forEach(card => {
    card.addEventListener('mousemove', (e) => {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      
      card.style.setProperty('--glow-x', `${x}px`);
      card.style.setProperty('--glow-y', `${y}px`);
      card.style.background = `radial-gradient(circle 200px at ${x}px ${y}px, rgba(59, 130, 246, 0.06), var(--bg-card))`;
    });

    card.addEventListener('mouseleave', () => {
      card.style.background = 'var(--bg-card)';
    });
  });

  // ========================================
  // PRELOADER - Ensure smooth entry
  // ========================================
  window.addEventListener('load', () => {
    document.body.style.opacity = '1';
    
    // Trigger reveal for elements already in viewport
    revealElements.forEach(el => {
      const rect = el.getBoundingClientRect();
      if (rect.top < window.innerHeight && rect.bottom > 0) {
        el.classList.add('visible');
      }
    });
  });

});
