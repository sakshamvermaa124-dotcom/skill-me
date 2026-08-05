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
  // LAYER 2a: THREE.JS — HERO Particle Galaxy
  // Restored from v1 style — colored floating particles
  // with mouse parallax, much denser and more dramatic
  // ═══════════════════════════════════════════════════════════
  (function initHeroParticles() {
    const canvas = document.getElementById('hero-canvas');
    if (!canvas || typeof THREE === 'undefined') return;

    const hero = document.getElementById('hero');
    const W = () => hero.offsetWidth;
    const H = () => hero.offsetHeight;

    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(W(), H());
    renderer.setClearColor(0x000000, 0);

    const scene  = new THREE.Scene();
    // Theme-aware fog
    const isDark = () => html.getAttribute('data-theme') !== 'light';
    scene.fog = new THREE.FogExp2(isDark() ? 0x0b0b0e : 0xfafafa, 0.08);

    const camera = new THREE.PerspectiveCamera(60, W() / H(), 0.1, 100);
    camera.position.z = 5;

    // ── Elegant TorusKnot wireframe centerpiece ──
    const knotGeo = new THREE.TorusKnotGeometry(1.6, 0.45, 200, 32, 2, 3);
    const knotMat = new THREE.MeshBasicMaterial({
      color: 0x6366f1,
      wireframe: true,
      transparent: true,
      opacity: 0.15,
    });
    const knot = new THREE.Mesh(knotGeo, knotMat);
    knot.position.set(1.5, 0, -1);
    scene.add(knot);

    // Second smaller knot — cyan accent
    const knot2Geo = new THREE.TorusKnotGeometry(0.8, 0.25, 128, 20, 3, 5);
    const knot2Mat = new THREE.MeshBasicMaterial({
      color: 0x22d3ee,
      wireframe: true,
      transparent: true,
      opacity: 0.1,
    });
    const knot2 = new THREE.Mesh(knot2Geo, knot2Mat);
    knot2.position.set(-2, -0.5, -2);
    scene.add(knot2);

    // Sparse ambient particles for subtle depth
    const COUNT = 600;
    const positions = new Float32Array(COUNT * 3);
    const colors = new Float32Array(COUNT * 3);
    const palette = [
      new THREE.Color('#6366f1'),
      new THREE.Color('#22d3ee'),
      new THREE.Color('#34d399'),
    ];

    for (let i = 0; i < COUNT; i++) {
      const i3 = i * 3;
      const radius = 3 + Math.random() * 10;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      positions[i3]     = radius * Math.sin(phi) * Math.cos(theta);
      positions[i3 + 1] = radius * Math.sin(phi) * Math.sin(theta) * 0.5;
      positions[i3 + 2] = radius * Math.cos(phi) - 2;
      const c = palette[Math.floor(Math.random() * palette.length)];
      colors[i3] = c.r; colors[i3 + 1] = c.g; colors[i3 + 2] = c.b;
    }

    const particleGeo = new THREE.BufferGeometry();
    particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    particleGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    const particleMat = new THREE.PointsMaterial({
      size: 0.02,
      vertexColors: true,
      transparent: true,
      opacity: 0.4,
      sizeAttenuation: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const particles = new THREE.Points(particleGeo, particleMat);
    scene.add(particles);

    // Mouse parallax
    let mouseX = 0, mouseY = 0;
    let targetX = 0, targetY = 0;
    window.addEventListener('mousemove', (e) => {
      mouseX = (e.clientX / window.innerWidth  - 0.5);
      mouseY = (e.clientY / window.innerHeight - 0.5);
    });

    let scrollProgress = 0;
    lenis.on('scroll', ({ progress }) => { scrollProgress = progress; });

    const clock = new THREE.Clock();
    function animate() {
      requestAnimationFrame(animate);
      const t = clock.getElapsedTime();

      // Slow, graceful rotation
      knot.rotation.x = t * 0.06;
      knot.rotation.y = t * 0.08;
      knot2.rotation.x = -t * 0.05;
      knot2.rotation.y = t * 0.1;

      particles.rotation.y = t * 0.02;

      // Mouse parallax with smooth damping
      targetX += (mouseX - targetX) * 0.03;
      targetY += (mouseY - targetY) * 0.03;
      knot.rotation.y += targetX * 0.3;
      knot.rotation.x += targetY * 0.15;
      particles.rotation.y += targetX * 0.15;

      // Fade as user scrolls away from hero
      const fadeOpacity = Math.max(0, 1 - scrollProgress * 3);
      knotMat.opacity = 0.15 * fadeOpacity;
      knot2Mat.opacity = 0.1 * fadeOpacity;
      particleMat.opacity = 0.4 * fadeOpacity;

      renderer.render(scene, camera);
    }

    animate();

    window.addEventListener('resize', () => {
      renderer.setSize(W(), H());
      camera.aspect = W() / H();
      camera.updateProjectionMatrix();
    });

    // Update fog on theme switch
    window.addEventListener('themechange', (e) => {
      scene.fog.color.set(e.detail.theme === 'light' ? 0xfafafa : 0x0b0b0e);
    });
  })();

  // ═══════════════════════════════════════════════════════════
  // LAYER 2b: THREE.JS — INTERLUDE Wireframe Shapes
  // ═══════════════════════════════════════════════════════════
  (function initFloatingOrbs() {
    const canvas = document.getElementById('float-canvas');
    if (!canvas || typeof THREE === 'undefined') return;

    const section = canvas.parentElement;
    const W = () => section.offsetWidth;
    const H = () => section.offsetHeight || 280;

    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.setSize(W(), H());
    renderer.setClearColor(0x000000, 0);

    const scene  = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(50, W() / H(), 0.1, 100);
    camera.position.z = 6;

    // Uniform dodecahedron wireframes — fewer but more impactful
    const wireColors = [0x6366f1, 0x22d3ee, 0x34d399];
    const orbs = [];

    for (let i = 0; i < 10; i++) {
      const geo = new THREE.DodecahedronGeometry(0.5, 0);
      const col = wireColors[i % wireColors.length];
      const mat = new THREE.MeshBasicMaterial({
        color: col, wireframe: true, transparent: true,
        opacity: 0.12 + Math.random() * 0.12,
      });

      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(
        (Math.random() - 0.5) * 14,
        (Math.random() - 0.5) * 3,
        (Math.random() - 0.5) * 3,
      );
      mesh.scale.setScalar(0.6 + Math.random() * 0.8);
      mesh.userData = {
        rx: (Math.random() - 0.5) * 0.008,
        ry: (Math.random() - 0.5) * 0.012,
        rz: (Math.random() - 0.5) * 0.006,
        baseY: mesh.position.y,
        floatOff: Math.random() * Math.PI * 2,
        floatSpd: 0.25 + Math.random() * 0.45,
      };
      scene.add(mesh);
      orbs.push(mesh);
    }

    let mouseX = 0;
    window.addEventListener('mousemove', (e) => { mouseX = (e.clientX / window.innerWidth - 0.5) * 2; });

    const clock = new THREE.Clock();
    function animate() {
      requestAnimationFrame(animate);
      const t = clock.getElapsedTime();
      orbs.forEach(o => {
        o.rotation.x += o.userData.rx;
        o.rotation.y += o.userData.ry;
        o.rotation.z += o.userData.rz;
        o.position.y = o.userData.baseY + Math.sin(t * o.userData.floatSpd + o.userData.floatOff) * 0.4;
      });
      camera.position.x += (mouseX * 0.7 - camera.position.x) * 0.03;
      renderer.render(scene, camera);
    }

    animate();

    window.addEventListener('resize', () => {
      renderer.setSize(W(), H());
      camera.aspect = W() / H();
      camera.updateProjectionMatrix();
    });
  })();

  // ═══════════════════════════════════════════════════════════
  // LAYER 2c: THREE.JS — BENEFITS Sphere with Orbit Rings
  // ═══════════════════════════════════════════════════════════
  (function initBenefitSphere() {
    const canvas = document.getElementById('sphere-canvas');
    if (!canvas || typeof THREE === 'undefined') return;

    const section = document.getElementById('benefits');
    const W = () => section.offsetWidth;
    const H = () => section.offsetHeight;

    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.setSize(W(), H());
    renderer.setClearColor(0x000000, 0);

    const scene  = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, W() / H(), 0.1, 100);
    camera.position.set(7, 3, 9);
    camera.lookAt(0, 0, 0);

    // Outer wireframe sphere — denser IcosahedronGeometry
    const sphereGeo = new THREE.IcosahedronGeometry(1.8, 2);
    const sphereMat = new THREE.MeshBasicMaterial({
      color: 0x6366f1, wireframe: true, transparent: true, opacity: 0.08,
    });
    const sphere = new THREE.Mesh(sphereGeo, sphereMat);
    scene.add(sphere);

    // Inner point cloud — IcosahedronGeometry for denser, more uniform distribution
    const innerGeo = new THREE.IcosahedronGeometry(1.2, 3);
    const innerMat = new THREE.PointsMaterial({
      color: 0x22d3ee, size: 0.035, transparent: true, opacity: 0.35,
      sizeAttenuation: true, blending: THREE.AdditiveBlending, depthWrite: false,
    });
    const innerPoints = new THREE.Points(innerGeo, innerMat);
    scene.add(innerPoints);

    // Orbit rings — sleeker with thinner tubes
    const ringData = [
      { tiltX: 0,    tiltZ: 0,    color: 0x6366f1, speed: 0.004, radius: 2.5, tube: 0.008 },
      { tiltX: 1.1,  tiltZ: 0.4,  color: 0x22d3ee, speed: -0.006, radius: 3.0, tube: 0.007 },
      { tiltX: 0.6,  tiltZ: -0.8, color: 0x34d399, speed: 0.005, radius: 3.5, tube: 0.006 },
    ];

    const rings = ringData.map(d => {
      const geo = new THREE.TorusGeometry(d.radius, d.tube, 4, 80);
      const mat = new THREE.MeshBasicMaterial({
        color: d.color, transparent: true, opacity: 0.25,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.rotation.x = d.tiltX;
      mesh.rotation.z = d.tiltZ;
      mesh.userData.speed = d.speed;
      scene.add(mesh);
      return mesh;
    });

    // Satellite dots on each ring
    rings.forEach((ring, ri) => {
      const dotGeo = new THREE.SphereGeometry(0.07, 8, 8);
      const dotMat = new THREE.MeshBasicMaterial({
        color: ringData[ri].color, transparent: true, opacity: 0.9,
      });
      const dot = new THREE.Mesh(dotGeo, dotMat);
      dot.userData.radius = ringData[ri].radius;
      dot.userData.speed  = ringData[ri].speed * 3;
      dot.userData.angle  = Math.random() * Math.PI * 2;
      ring.add(dot);
    });

    let scrollY = 0;
    lenis.on('scroll', ({ scroll }) => { scrollY = scroll; });

    const clock = new THREE.Clock();
    function animate() {
      requestAnimationFrame(animate);
      const t = clock.getElapsedTime();

      sphere.rotation.y = t * 0.05;
      sphere.rotation.x = t * 0.025;
      innerPoints.rotation.y = -t * 0.06;

      rings.forEach(ring => {
        ring.rotation.y += ring.userData.speed;
        ring.children.forEach(dot => {
          dot.userData.angle += dot.userData.speed;
          dot.position.x = Math.cos(dot.userData.angle) * dot.userData.radius;
          dot.position.z = Math.sin(dot.userData.angle) * dot.userData.radius;
        });
      });

      // Parallax on scroll
      const section = document.getElementById('benefits');
      if (section) {
        const rect = section.getBoundingClientRect();
        const progress = Math.max(0, Math.min(1, -rect.top / rect.height + 0.5));
        camera.position.y = 2 + progress * 1.5;
      }

      renderer.render(scene, camera);
    }

    animate();

    window.addEventListener('resize', () => {
      renderer.setSize(W(), H());
      camera.aspect = W() / H();
      camera.updateProjectionMatrix();
    });
  })();

  // ═══════════════════════════════════════════════════════════
  // LAYER 2d: THREE.JS — CTA Section DNA Double Helix
  // ═══════════════════════════════════════════════════════════
  (function initDNAHelix() {
    // Insert canvas into CTA section dynamically
    const ctaSection = document.querySelector('.cta-section');
    if (!ctaSection || typeof THREE === 'undefined') return;

    const canvas = document.createElement('canvas');
    canvas.style.cssText = 'position:absolute;inset:0;z-index:0;pointer-events:none;width:100%;height:100%;';
    canvas.setAttribute('aria-hidden', 'true');
    ctaSection.insertBefore(canvas, ctaSection.firstChild);

    const W = () => ctaSection.offsetWidth;
    const H = () => ctaSection.offsetHeight;

    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.setSize(W(), H());
    renderer.setClearColor(0x000000, 0);

    const scene  = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(50, W() / H(), 0.1, 100);
    camera.position.set(0, 0, 7);

    // DNA double helix using points — dense for smooth strands
    const helixCount = 300;
    const strand1Pos = [];
    const strand2Pos = [];
    const connectors = [];

    for (let i = 0; i < helixCount; i++) {
      const t = (i / helixCount) * Math.PI * 8 - Math.PI * 4;
      const y = (i / helixCount) * 10 - 5;

      strand1Pos.push(Math.cos(t) * 1.5, y, Math.sin(t) * 0.4);
      strand2Pos.push(Math.cos(t + Math.PI) * 1.5, y, Math.sin(t + Math.PI) * 0.4);

      // Add connector rung every 8 points
      if (i % 8 === 0) {
        const pts = [
          new THREE.Vector3(Math.cos(t) * 1.5, y, Math.sin(t) * 0.4),
          new THREE.Vector3(Math.cos(t + Math.PI) * 1.5, y, Math.sin(t + Math.PI) * 0.4),
        ];
        const geo = new THREE.BufferGeometry().setFromPoints(pts);
        const mat = new THREE.LineBasicMaterial({ color: 0x34d399, transparent: true, opacity: 0.12 });
        connectors.push(new THREE.Line(geo, mat));
        scene.add(connectors[connectors.length - 1]);
      }
    }

    const s1Geo = new THREE.BufferGeometry();
    s1Geo.setAttribute('position', new THREE.Float32BufferAttribute(strand1Pos, 3));
    const s1Mat = new THREE.PointsMaterial({
      color: 0x6366f1, size: 0.04, transparent: true, opacity: 0.45,
      sizeAttenuation: true, blending: THREE.AdditiveBlending, depthWrite: false,
    });
    const strand1 = new THREE.Points(s1Geo, s1Mat);
    scene.add(strand1);

    const s2Geo = new THREE.BufferGeometry();
    s2Geo.setAttribute('position', new THREE.Float32BufferAttribute(strand2Pos, 3));
    const s2Mat = new THREE.PointsMaterial({
      color: 0x22d3ee, size: 0.04, transparent: true, opacity: 0.45,
      sizeAttenuation: true, blending: THREE.AdditiveBlending, depthWrite: false,
    });
    const strand2 = new THREE.Points(s2Geo, s2Mat);
    scene.add(strand2);

    const group = new THREE.Group();
    group.add(strand1, strand2, ...connectors);
    scene.add(group);

    const clock = new THREE.Clock();
    function animate() {
      requestAnimationFrame(animate);
      const t = clock.getElapsedTime();
      group.rotation.y = t * 0.2;
      group.position.y = Math.sin(t * 0.35) * 0.15;
      renderer.render(scene, camera);
    }

    animate();

    window.addEventListener('resize', () => {
      renderer.setSize(W(), H());
      camera.aspect = W() / H();
      camera.updateProjectionMatrix();
    });
  })();

  // ═══════════════════════════════════════════════════════════
  // LAYER 3: GSAP + ScrollTrigger (Web3D Pattern 1)
  // Scroll-driven 3D text reveals, parallax, and section animations
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
      opacity: 0, y: 60, rotateX: 15,
    }, {
      opacity: 1, y: 0, rotateX: 0,
      duration: 0.9,
      ease: 'power3.out',
      stagger: 0.12,
      scrollTrigger: {
        trigger: '.steps-grid',
        start: 'top 80%',
        end: 'bottom 60%',
        toggleActions: 'play none none none',
      },
    });

    // ── 2. Benefit cards — cascade from left ──
    gsap.fromTo('.benefit-card', {
      opacity: 0, x: -40, scale: 0.95,
    }, {
      opacity: 1, x: 0, scale: 1,
      duration: 0.8,
      ease: 'power2.out',
      stagger: 0.1,
      scrollTrigger: {
        trigger: '.benefits-grid',
        start: 'top 75%',
        toggleActions: 'play none none none',
      },
    });

    // ── 3. Domain cards — scale in ──
    gsap.fromTo('.domain-card', {
      opacity: 0, scale: 0.85, y: 30,
    }, {
      opacity: 1, scale: 1, y: 0,
      duration: 0.6,
      ease: 'back.out(1.5)',
      stagger: 0.04,
      scrollTrigger: {
        trigger: '.domains-grid',
        start: 'top 80%',
        toggleActions: 'play none none none',
      },
    });

    // ── 4. Section headers — slide up with blur ──
    gsap.utils.toArray('.section-header').forEach(header => {
      gsap.fromTo(header, {
        opacity: 0, y: 50, filter: 'blur(8px)',
      }, {
        opacity: 1, y: 0, filter: 'blur(0px)',
        duration: 1.0,
        ease: 'power3.out',
        scrollTrigger: {
          trigger: header,
          start: 'top 85%',
          toggleActions: 'play none none none',
        },
      });
    });

    // ── 5. Testimonials — 3D flip in ──
    gsap.fromTo('.testimonial-card', {
      opacity: 0, rotateY: 20, z: -60, transformOrigin: 'left center',
    }, {
      opacity: 1, rotateY: 0, z: 0,
      duration: 0.9,
      ease: 'power3.out',
      stagger: 0.15,
      scrollTrigger: {
        trigger: '.testimonials-grid',
        start: 'top 80%',
        toggleActions: 'play none none none',
      },
    });

    // ── 6. CTA box — scale + glow entrance ──
    gsap.fromTo('.cta-box', {
      opacity: 0, scale: 0.92,
    }, {
      opacity: 1, scale: 1,
      duration: 1.2,
      ease: 'expo.out',
      scrollTrigger: {
        trigger: '.cta-section',
        start: 'top 75%',
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
    { type: 'output',  text: '✅ PR merged! +₹350 stipend points added.', class: 'success', delay: 6600 },
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
          ? 'rgba(99, 102, 241, 0.05)'
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
  // STAT COUNTERS
  // ═══════════════════════════════════════════════════════════
  const statData = [
    { end: 500, prefix: '', suffix: '+' },
    { end: 10,  prefix: '₹', suffix: 'K' },
    { end: 12,  prefix: '', suffix: '+' },
    { end: 100, prefix: '', suffix: '%' },
  ];

  new IntersectionObserver((entries) => {
    if (!entries[0].isIntersecting) return;
    document.querySelectorAll('.stat-number').forEach((el, i) => {
      if (!statData[i]) return;
      const { end, prefix, suffix } = statData[i];
      const start = performance.now();
      const duration = 1800;
      function tick(now) {
        const t = Math.min((now - start) / duration, 1);
        const ease = 1 - Math.pow(1 - t, 3);
        el.textContent = prefix + Math.floor(end * ease) + suffix;
        if (t < 1) requestAnimationFrame(tick);
      }
      setTimeout(() => requestAnimationFrame(tick), i * 120);
    });
    entries[0].target._obs?.unobserve(entries[0].target);
  }, { threshold: 0.7 }).observe(document.querySelector('.hero-stats') || document.body);

  // ═══════════════════════════════════════════════════════════
  // CURSOR GLOW (subtle ambient glow following cursor)
  // ═══════════════════════════════════════════════════════════
  const cursorGlow = document.createElement('div');
  cursorGlow.style.cssText = `
    position: fixed; pointer-events: none; z-index: 9999;
    width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(99,102,241,0.04) 0%, transparent 70%);
    border-radius: 50%; transform: translate(-50%, -50%);
    transition: opacity 0.3s ease;
    top: 0; left: 0;
  `;
  document.body.appendChild(cursorGlow);

  // Update cursor glow on theme switch
  function updateGlowTheme(theme) {
    const color = theme === 'light'
      ? 'radial-gradient(circle, rgba(0,0,0,0.02) 0%, transparent 70%)'
      : 'radial-gradient(circle, rgba(99,102,241,0.04) 0%, transparent 70%)';
    cursorGlow.style.background = color;
  }
  updateGlowTheme(html.getAttribute('data-theme'));
  window.addEventListener('themechange', (e) => updateGlowTheme(e.detail.theme));

  let glowX = 0, glowY = 0, glowTargetX = 0, glowTargetY = 0;

  document.addEventListener('mousemove', (e) => {
    glowTargetX = e.clientX;
    glowTargetY = e.clientY;
  });

  (function animateGlow() {
    glowX += (glowTargetX - glowX) * 0.08;
    glowY += (glowTargetY - glowY) * 0.08;
    cursorGlow.style.left = glowX + 'px';
    cursorGlow.style.top  = glowY + 'px';
    requestAnimationFrame(animateGlow);
  })();

});
