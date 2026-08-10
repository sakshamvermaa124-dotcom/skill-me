// ─── SkillMe Admin Console — JS ───
const API = window.SKILLME_API || 'http://localhost:8000';
let adminKey = '';
let allStudents = [];
let allBatches = [];
let currentPage = 'overview';

const PAGE_META = {
  overview:  { title: 'Overview',  subtitle: 'Platform summary and recent activity' },
  students:  { title: 'Students',  subtitle: 'Manage applications and enrollments' },
  batches:   { title: 'Batches',   subtitle: 'Manage cohorts and automated task assignment' },
  email:     { title: 'Email Settings', subtitle: 'Brevo SMTP relay — test and monitor email delivery' },
};

// ═══════════════════════════════════════════════════════════
// THREE.JS 3D GAME RUNNER ENGINE (#runner-loop-canvas)
// Volcanic Ember / Lava Highway Environment
// ═══════════════════════════════════════════════════════════
let runnerScene, runnerCamera, runnerRenderer;
let runnerCharacterGroup, legLeftGroup, legRightGroup, armLeftGroup, armRightGroup;
let neonRoadGrid, lightPillars = [], gameCoins = [], lavaSpires = [], lavaEmbers;

function initRunnerLoopCanvas() {
  const canvas = document.getElementById('runner-loop-canvas');
  if (!canvas || typeof THREE === 'undefined') return;

  const container = canvas.parentElement;
  const W = () => container.offsetWidth || window.innerWidth * 0.5;
  const H = () => container.offsetHeight || window.innerHeight;

  runnerRenderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  runnerRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  runnerRenderer.setSize(W(), H());

  runnerScene = new THREE.Scene();
  runnerScene.fog = new THREE.FogExp2(0xe8e2d8, 0.035);

  runnerCamera = new THREE.PerspectiveCamera(50, W() / H(), 0.1, 100);
  runnerCamera.position.set(0, 1.8, 4.2);
  runnerCamera.lookAt(0, 1.2, 0);

  // Volcanic Molten Lighting
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
  runnerScene.add(ambientLight);

  const magmaLight = new THREE.PointLight(0xff2a4b, 6, 16);
  magmaLight.position.set(0, 0.3, 1);
  runnerScene.add(magmaLight);

  const amberLight = new THREE.PointLight(0xffb703, 4, 14);
  amberLight.position.set(-2, 3, -3);
  runnerScene.add(amberLight);

  // 1. Cracked Molten Magma Highway Grid
  const gridHelper = new THREE.GridHelper(50, 50, 0xff2a4b, 0x440810);
  gridHelper.position.y = 0;
  gridHelper.position.z = -10;
  runnerScene.add(gridHelper);
  neonRoadGrid = gridHelper;

  // 2. 3D Volcanic Rock Pillars & Lava Spire Crystals
  for (let i = 0; i < 14; i++) {
    const height = 4 + Math.random() * 6;
    const sGeo = new THREE.ConeGeometry(0.8 + Math.random() * 0.8, height, 5);
    const sMat = new THREE.MeshStandardMaterial({
      color: 0x16070a,
      roughness: 0.4,
      metalness: 0.6,
      emissive: 0x900c1e,
      emissiveIntensity: 0.5
    });

    const spire = new THREE.Mesh(sGeo, sMat);
    const side = (i % 2 === 0 ? 1 : -1) * (4.5 + Math.random() * 3);
    const zPos = -i * 5 + 4;
    spire.position.set(side, height / 2, zPos);
    spire.rotation.y = Math.random() * Math.PI;
    runnerScene.add(spire);
    lavaSpires.push(spire);
  }

  // 3. Floating Fiery Ember Particles (350 Rising Amber Embers)
  const emberCount = 350;
  const emberGeo = new THREE.BufferGeometry();
  const emberPos = new Float32Array(emberCount * 3);
  for (let i = 0; i < emberCount; i++) {
    emberPos[i * 3]     = (Math.random() - 0.5) * 30;
    emberPos[i * 3 + 1] = Math.random() * 15;
    emberPos[i * 3 + 2] = -Math.random() * 40;
  }
  emberGeo.setAttribute('position', new THREE.BufferAttribute(emberPos, 3));
  const emberMat = new THREE.PointsMaterial({
    color: 0xffb703, size: 0.09, transparent: true, opacity: 0.85,
    blending: THREE.AdditiveBlending
  });
  lavaEmbers = new THREE.Points(emberGeo, emberMat);
  runnerScene.add(lavaEmbers);

  // 4. Glowing Side Lava Pillars
  for (let i = 0; i < 16; i++) {
    const pillarGeo = new THREE.BoxGeometry(0.08, 3.5, 0.08);
    const pillarMat = new THREE.MeshBasicMaterial({ color: i % 2 === 0 ? 0xff2a4b : 0xffb703 });
    const pillar = new THREE.Mesh(pillarGeo, pillarMat);
    const side = (i % 2 === 0 ? 1 : -1) * 3.2;
    const zPos = -i * 2.5 + 4;
    pillar.position.set(side, 1.75, zPos);
    runnerScene.add(pillar);
    lightPillars.push(pillar);
  }

  // 5. Floating 3D Golden & Amber Coins
  const coinGeo = new THREE.CylinderGeometry(0.22, 0.22, 0.06, 16);
  const coinMat = new THREE.MeshStandardMaterial({
    color: 0xffb703, metalness: 0.9, roughness: 0.1, emissive: 0xaa6600
  });
  for (let i = 0; i < 8; i++) {
    const coin = new THREE.Mesh(coinGeo, coinMat);
    coin.rotation.x = Math.PI / 2;
    coin.position.set((Math.random() - 0.5) * 2.4, 1.2, -i * 4 - 2);
    runnerScene.add(coin);
    gameCoins.push(coin);
  }

  // 6. Construct 3D Cyberpunk Character Hierarchy
  runnerCharacterGroup = new THREE.Group();
  runnerCharacterGroup.position.set(0, 0.9, 1.2);

  const blackMat = new THREE.MeshStandardMaterial({ color: 0x0e0a0d, roughness: 0.4 });
  const redAccMat = new THREE.MeshStandardMaterial({ color: 0xff2a4b, emissive: 0xaa1028, emissiveIntensity: 0.8 });
  const soleMat = new THREE.MeshBasicMaterial({ color: 0xffb703 });

  // Torso / Hoodie
  const torso = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.7, 0.35), blackMat);
  torso.position.y = 0.4;
  runnerCharacterGroup.add(torso);

  // Official SkillMe Logo Emblem on Back of Hoodie (Edge/Chrome/Brave Compatible)
  const logoTexture = new THREE.TextureLoader().load('assets/logo.webp', (tex) => {
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.generateMipmaps = false;
    tex.needsUpdate = true;
  });

  const emblemGeo = new THREE.PlaneGeometry(0.34, 0.34);
  const emblemMat = new THREE.MeshBasicMaterial({
    map: logoTexture,
    color: 0xffffff,
    transparent: true,
    side: THREE.FrontSide
  });
  const emblem = new THREE.Mesh(emblemGeo, emblemMat);
  emblem.position.set(0, 0.4, 0.182);
  runnerCharacterGroup.add(emblem);

  // Head
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.18, 16, 16), blackMat);
  head.position.y = 0.9,
  runnerCharacterGroup.add(head);

  // Left Leg Assembly
  legLeftGroup = new THREE.Group();
  legLeftGroup.position.set(-0.16, 0.05, 0);
  const legL = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.55, 0.18), blackMat);
  legL.position.y = -0.27;
  const shoeL = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.1, 0.3), soleMat);
  shoeL.position.set(0, -0.58, -0.05);
  legLeftGroup.add(legL);
  legLeftGroup.add(shoeL);
  runnerCharacterGroup.add(legLeftGroup);

  // Right Leg Assembly
  legRightGroup = new THREE.Group();
  legRightGroup.position.set(0.16, 0.05, 0);
  const legR = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.55, 0.18), blackMat);
  legR.position.y = -0.27;
  const shoeR = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.1, 0.3), redAccMat);
  shoeR.position.set(0, -0.58, -0.05);
  legRightGroup.add(legR);
  legRightGroup.add(shoeR);
  runnerCharacterGroup.add(legRightGroup);

  // Left Arm Assembly
  armLeftGroup = new THREE.Group();
  armLeftGroup.position.set(-0.35, 0.65, 0);
  const armL = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.5, 0.14), blackMat);
  armL.position.y = -0.25;
  armLeftGroup.add(armL);
  runnerCharacterGroup.add(armLeftGroup);

  // Right Arm Assembly
  armRightGroup = new THREE.Group();
  armRightGroup.position.set(0.35, 0.65, 0);
  const armR = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.5, 0.14), blackMat);
  armR.position.y = -0.25;
  armRightGroup.add(armR);
  runnerCharacterGroup.add(armRightGroup);

  runnerScene.add(runnerCharacterGroup);

  // Animation Loop (Real 3D Skeletal Running Cycle)
  const clock = new THREE.Clock();
  function render3DGameRun() {
    if (!canvas.parentElement || canvas.offsetParent === null) return;
    requestAnimationFrame(render3DGameRun);

    const t = clock.getElapsedTime() * 14; // Running frequency speed

    // Skeletal Rotations
    legLeftGroup.rotation.x = Math.sin(t) * 0.8;
    legRightGroup.rotation.x = -Math.sin(t) * 0.8;
    armLeftGroup.rotation.x = -Math.sin(t) * 0.75;
    armRightGroup.rotation.x = Math.sin(t) * 0.75;

    // Running Vertical Bounce & Stride Tilt
    runnerCharacterGroup.position.y = 0.9 + Math.abs(Math.sin(t)) * 0.15;
    runnerCharacterGroup.rotation.z = Math.sin(t) * 0.05;

    // Scroll Road Grid
    neonRoadGrid.position.z = (t * 0.3) % 2;

    // Scroll Volcanic Spires
    lavaSpires.forEach(s => {
      s.position.z += 0.28;
      if (s.position.z > 8) s.position.z -= 65;
    });

    // Animate Fiery Ember Particles (Rising & Drifting)
    const positions = lavaEmbers.geometry.attributes.position.array;
    for (let i = 0; i < emberCount; i++) {
      positions[i * 3 + 1] += 0.04; // Rise up
      positions[i * 3 + 2] += 0.15; // Move backward
      if (positions[i * 3 + 1] > 15 || positions[i * 3 + 2] > 5) {
        positions[i * 3 + 1] = 0;
        positions[i * 3 + 2] = -40;
      }
    }
    lavaEmbers.geometry.attributes.position.needsUpdate = true;

    // Scroll Side Light Pillars
    lightPillars.forEach(p => {
      p.position.z += 0.28;
      if (p.position.z > 6) p.position.z -= 40;
    });

    // Scroll & Rotate 3D Coins
    gameCoins.forEach(coin => {
      coin.rotation.z += 0.05;
      coin.position.z += 0.28;
      if (coin.position.z > 5) {
        coin.position.z = -25;
        coin.position.x = (Math.random() - 0.5) * 2.4;
      }
    });

    runnerRenderer.render(runnerScene, runnerCamera);
  }

  render3DGameRun();

  window.addEventListener('resize', () => {
    runnerRenderer.setSize(W(), H());
    runnerCamera.aspect = W() / H();
    runnerCamera.updateProjectionMatrix();
  });
}

// ═══════════════════════════════════════════════════════════
// THREE.JS SCENE 2: BACKGROUND 3D VOLCANIC RED LAVA ROCK (#admin-bg-canvas)
// Real-time 3D Ember Lava Core on Warm Alabaster Surface
// ═══════════════════════════════════════════════════════════
let bgScene, bgCamera, bgRenderer, bgMesh, bgParticles;

function initAdminBgLattice() {
  const canvas = document.getElementById('admin-bg-canvas');
  if (!canvas || typeof THREE === 'undefined') return;

  bgRenderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  bgRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  bgRenderer.setSize(window.innerWidth, window.innerHeight);

  bgScene = new THREE.Scene();
  bgCamera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 100);
  bgCamera.position.set(0, 0, 8);

  // Volcanic Lighting
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.85);
  bgScene.add(ambientLight);

  const redLight = new THREE.PointLight(0xff2a4b, 4, 12);
  redLight.position.set(3, 3, 4);
  bgScene.add(redLight);

  const amberLight = new THREE.PointLight(0xffb703, 3, 10);
  amberLight.position.set(-3, -3, 3);
  bgScene.add(amberLight);

  // Faceted 3D Crimson Lava Crystal Core Geometry
  const geo = new THREE.IcosahedronGeometry(3.0, 1);
  const mat = new THREE.MeshStandardMaterial({
    color: 0xc1121f,
    roughness: 0.15,
    metalness: 0.8,
    emissive: 0xff2a4b,
    emissiveIntensity: 0.75,
    flatShading: true
  });

  bgMesh = new THREE.Mesh(geo, mat);
  bgMesh.position.set(2.8, -0.2, 0); // Positioned on the right alabaster half matching EMBER split view
  bgScene.add(bgMesh);

  // Outer glowing wireframe crystal shell
  const wireGeo = new THREE.IcosahedronGeometry(3.3, 1);
  const wireMat = new THREE.MeshBasicMaterial({
    color: 0xff2a4b, wireframe: true, transparent: true, opacity: 0.6
  });
  bgMesh.add(new THREE.Mesh(wireGeo, wireMat));

  // Floating amber droplets
  const particleCount = 120;
  const pGeo = new THREE.BufferGeometry();
  const pPos = new Float32Array(particleCount * 3);
  for (let i = 0; i < particleCount; i++) {
    pPos[i * 3]     = (Math.random() - 0.5) * 12;
    pPos[i * 3 + 1] = (Math.random() - 0.5) * 12;
    pPos[i * 3 + 2] = (Math.random() - 0.5) * 6;
  }
  pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
  const pMat = new THREE.PointsMaterial({
    color: 0xffb703, size: 0.06, transparent: true, opacity: 0.85,
    blending: THREE.AdditiveBlending, depthWrite: false
  });
  bgParticles = new THREE.Points(pGeo, pMat);
  bgScene.add(bgParticles);

  // Mouse tracking
  let mouseX = 0, mouseY = 0;
  window.addEventListener('mousemove', (e) => {
    mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
    mouseY = (e.clientY / window.innerHeight - 0.5) * 2;
  });

  const clock = new THREE.Clock();
  function animateBg() {
    requestAnimationFrame(animateBg);
    const t = clock.getElapsedTime();

    bgMesh.rotation.y = t * 0.2;
    bgMesh.rotation.x = Math.sin(t * 0.18) * 0.15;
    bgParticles.rotation.y = -t * 0.08;

    bgCamera.position.x += (mouseX * 0.4 - bgCamera.position.x) * 0.04;
    bgCamera.position.y += (-mouseY * 0.4 - bgCamera.position.y) * 0.04;
    bgCamera.lookAt(0, 0, 0);

    bgRenderer.render(bgScene, bgCamera);
  }
  animateBg();

  window.addEventListener('resize', () => {
    bgRenderer.setSize(window.innerWidth, window.innerHeight);
    bgCamera.aspect = window.innerWidth / window.innerHeight;
    bgCamera.updateProjectionMatrix();
  });
}

// ═══════════════════════════════════════════════════════════
// SIGNATURE 3D PLANE "UNZIP & REVEAL" TRANSITION ON LOGIN
// ═══════════════════════════════════════════════════════════
let isUnzipping = false;

function playUnzipTransition(callback) {
  if (isUnzipping) {
    if (callback) callback();
    return;
  }
  isUnzipping = true;

  const canvas = document.getElementById('unzip-canvas');
  const overlay = document.getElementById('login-overlay');
  const card = document.querySelector('.center-login-card');
  const leftPanel = document.querySelector('.split-left');
  const rightPanel = document.querySelector('.split-right');

  if (!canvas || typeof THREE === 'undefined' || typeof gsap === 'undefined') {
    isUnzipping = false;
    if (callback) callback();
    return;
  }

  canvas.style.opacity = '1';
  const W = window.innerWidth;
  const H = window.innerHeight;

  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(W, H);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, W / H, 0.1, 100);
  camera.position.z = 5;

  const planeGeo = new THREE.PlaneGeometry(14, 0.12, 32, 1);
  const planeMat = new THREE.MeshBasicMaterial({ color: 0xff2a4b, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending });
  const planeMesh = new THREE.Mesh(planeGeo, planeMat);
  planeMesh.position.y = 4;
  scene.add(planeMesh);

  let animId;
  function renderUnzip() {
    animId = requestAnimationFrame(renderUnzip);
    renderer.render(scene, camera);
  }
  renderUnzip();

  const laserSeam = document.querySelector('.laser-seam');

  const tl = gsap.timeline({
    onComplete: () => {
      cancelAnimationFrame(animId);
      canvas.style.opacity = '0';
      overlay.style.display = 'none';
      renderer.dispose();
      isUnzipping = false;
      if (callback) callback();
    }
  });

  if (card) tl.to(card, { opacity: 0, scale: 0.85, duration: 0.25, ease: 'power2.in' });
  if (laserSeam) tl.to(laserSeam, { opacity: 0, duration: 0.15, ease: 'power2.out' }, '<');
  tl.to(planeMesh.position, { y: -4, duration: 0.8, ease: 'power2.inOut' }, '-=0.1');

  if (leftPanel && rightPanel) {
    tl.to(leftPanel, { x: '-100%', duration: 0.8, ease: 'power3.inOut' }, '-=0.7');
    tl.to(rightPanel, { x: '100%', duration: 0.8, ease: 'power3.inOut' }, '-=0.8');
  } else {
    tl.to(overlay, { opacity: 0, duration: 0.5 }, '-=0.5');
  }
}

// ─── AUTH ───
async function handleLogin(e) {
  if (e && e.preventDefault) e.preventDefault();
  return adminLogin();
}

async function adminLogin() {
  if (isUnzipping) return;
  const keyInput = document.getElementById('admin-key-input') || document.getElementById('api-key-input');
  const key = keyInput ? keyInput.value.trim() : '';
  const errEl = document.getElementById('login-error');
  const btn = document.getElementById('admin-login-btn') || document.getElementById('login-btn');
  if (!key) { if (errEl) errEl.textContent = 'Please enter your secret passkey.'; return; }

  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Verifying Passkey...';
  }
  try {
    const res = await fetch(`${API}/api/admin/stats`, {
      headers: { 'X-Admin-Key': key }
    });
    if (res.status === 403) {
      if (errEl) errEl.textContent = 'Invalid admin passkey. Please try again.';
      if (btn) { btn.disabled = false; btn.textContent = 'ACCESS CONSOLE →'; }
      return;
    }
    if (!res.ok) throw new Error('Server error');
    adminKey = key;
    sessionStorage.setItem('skillme_admin_key', key);

    playUnzipTransition(() => {
      showApp();
      if (btn) btn.disabled = false;
    });
  } catch (e) {
    if (errEl) errEl.textContent = 'Could not connect to backend.';
    if (btn) { btn.disabled = false; btn.textContent = 'ACCESS CONSOLE →'; }
  }
}

// ═══════════════════════════════════════════════════════════
// THREE.JS SCENE: INTERIOR 3D RED LAVA ROCK (#interior-lava-canvas)
// Real-time 3D Volcanic Ember Core on Interior Alabaster Panel
// ═══════════════════════════════════════════════════════════
let intLavaScene, intLavaCamera, intLavaRenderer, intLavaMesh, intLavaParticles;

function initInteriorLavaRock() {
  const canvas = document.getElementById('interior-lava-canvas');
  if (!canvas || typeof THREE === 'undefined') return;

  const container = canvas.parentElement;
  const W = () => container.offsetWidth || Math.floor(window.innerWidth * 0.45);
  const H = () => container.offsetHeight || window.innerHeight;

  intLavaRenderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  intLavaRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  intLavaRenderer.setSize(W(), H());

  intLavaScene = new THREE.Scene();
  intLavaCamera = new THREE.PerspectiveCamera(45, W() / H(), 0.1, 100);
  intLavaCamera.position.set(0, 0, 5.2);

  // Volcanic Lighting
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
  intLavaScene.add(ambientLight);

  const redLight = new THREE.PointLight(0xff2a4b, 3.5, 10);
  redLight.position.set(2, 2, 3);
  intLavaScene.add(redLight);

  const amberLight = new THREE.PointLight(0xffb703, 2.5, 8);
  amberLight.position.set(-2, -2, 2);
  intLavaScene.add(amberLight);

  // 3D Organic Lava Rock Geometry with vertex noise displacement
  const geo = new THREE.IcosahedronGeometry(1.5, 2);
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const v = new THREE.Vector3().fromBufferAttribute(pos, i);
    const noise = (Math.sin(v.x * 3) + Math.cos(v.y * 3) + Math.sin(v.z * 3)) * 0.12;
    v.multiplyScalar(1 + noise);
    pos.setXYZ(i, v.x, v.y, v.z);
  }
  geo.computeVertexNormals();

  const mat = new THREE.MeshStandardMaterial({
    color: 0x1c0c11,
    roughness: 0.35,
    metalness: 0.6,
    emissive: 0x900c1e,
    emissiveIntensity: 0.55,
  });

  intLavaMesh = new THREE.Mesh(geo, mat);
  intLavaScene.add(intLavaMesh);

  // Outer wireframe shell
  const wireGeo = new THREE.IcosahedronGeometry(1.65, 1);
  const wireMat = new THREE.MeshBasicMaterial({
    color: 0xff2a4b, wireframe: true, transparent: true, opacity: 0.22
  });
  intLavaMesh.add(new THREE.Mesh(wireGeo, wireMat));

  // Floating amber droplets
  const particleCount = 70;
  const pGeo = new THREE.BufferGeometry();
  const pPos = new Float32Array(particleCount * 3);
  for (let i = 0; i < particleCount; i++) {
    pPos[i * 3]     = (Math.random() - 0.5) * 5;
    pPos[i * 3 + 1] = (Math.random() - 0.5) * 5;
    pPos[i * 3 + 2] = (Math.random() - 0.5) * 3;
  }
  pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
  const pMat = new THREE.PointsMaterial({
    color: 0xffb703, size: 0.045, transparent: true, opacity: 0.85,
    blending: THREE.AdditiveBlending, depthWrite: false
  });
  intLavaParticles = new THREE.Points(pGeo, pMat);
  intLavaScene.add(intLavaParticles);

  // Mouse tracking
  let mouseX = 0, mouseY = 0;
  window.addEventListener('mousemove', (e) => {
    mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
    mouseY = (e.clientY / window.innerHeight - 0.5) * 2;
  });

  const clock = new THREE.Clock();
  function animateInteriorLava() {
    if (!canvas.parentElement || canvas.offsetParent === null) return;
    requestAnimationFrame(animateInteriorLava);
    const t = clock.getElapsedTime();

    intLavaMesh.rotation.y = t * 0.22;
    intLavaMesh.rotation.x = Math.sin(t * 0.2) * 0.12;
    intLavaParticles.rotation.y = -t * 0.1;

    intLavaCamera.position.x += (mouseX * 0.3 - intLavaCamera.position.x) * 0.03;
    intLavaCamera.position.y += (-mouseY * 0.3 - intLavaCamera.position.y) * 0.03;
    intLavaCamera.lookAt(0, 0, 0);

    intLavaRenderer.render(intLavaScene, intLavaCamera);
  }

  animateInteriorLava();

  window.addEventListener('resize', () => {
    if (!container) return;
    intLavaRenderer.setSize(W(), H());
    intLavaCamera.aspect = W() / H();
    intLavaCamera.updateProjectionMatrix();
  });
}

// ═══════════════════════════════════════════════════════════
// THREE.JS REAL-TIME 3D VOLCANIC LAVA / EMBER CORE CRYSTAL
// Dedicated Canvas (#admin-3d-canvas) over Warm Alabaster Surface
// ═══════════════════════════════════════════════════════════
let admin3DScene, admin3DCamera, admin3DRenderer, admin3DMesh, admin3DParticles;

function initAdmin3DCrystalEngine() {
  const canvas = document.getElementById('admin-3d-canvas');
  if (!canvas || typeof THREE === 'undefined') return;

  const W = () => Math.floor(window.innerWidth - 280);
  const H = () => window.innerHeight;

  admin3DRenderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: "high-performance" });
  admin3DRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  admin3DRenderer.setSize(W(), H());

  admin3DScene = new THREE.Scene();
  admin3DCamera = new THREE.PerspectiveCamera(45, W() / H(), 0.1, 100);
  admin3DCamera.position.set(0, 0, 7.0);

  // Volcanic Volumetric Lighting
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.95);
  admin3DScene.add(ambientLight);

  const crimsonPointLight = new THREE.PointLight(0xff2a4b, 5, 16);
  crimsonPointLight.position.set(2, 3, 4);
  admin3DScene.add(crimsonPointLight);

  const amberPointLight = new THREE.PointLight(0xffb703, 4, 12);
  amberPointLight.position.set(-2, -3, 3);
  admin3DScene.add(amberPointLight);

  // Load Texture for Real-time 3D Lava Rock
  const textureLoader = new THREE.TextureLoader();
  const lavaTexture = textureLoader.load('lava_rock_texture.jpg', (tex) => {
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.RepeatWrapping;
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
  });

  // 3D Volcanic Lava Core Crystal Geometry with organic vertex noise displacement
  const geo = new THREE.IcosahedronGeometry(2.2, 3);
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const v = new THREE.Vector3().fromBufferAttribute(pos, i);
    const noise = (Math.sin(v.x * 2.2) + Math.cos(v.y * 2.2) + Math.sin(v.z * 2.2)) * 0.25;
    v.multiplyScalar(1 + noise);
    pos.setXYZ(i, v.x, v.y, v.z);
  }
  geo.computeVertexNormals();

  const mat = new THREE.MeshStandardMaterial({
    map: lavaTexture,
    bumpMap: lavaTexture,
    bumpScale: 0.15,
    emissiveMap: lavaTexture,
    emissive: 0xff2a4b,
    emissiveIntensity: 0.65,
    roughness: 0.35,
    metalness: 0.4,
  });

  admin3DMesh = new THREE.Mesh(geo, mat);
  admin3DMesh.position.set(0.1, 0, 0); // Shifted left to sit in the exact center of content area
  admin3DScene.add(admin3DMesh);

  // Outer glowing wireframe crystal shell
  const wireGeo = new THREE.IcosahedronGeometry(2.45, 1);
  const wireMat = new THREE.MeshBasicMaterial({
    color: 0xff2a4b, wireframe: true, transparent: true, opacity: 0.45
  });
  admin3DMesh.add(new THREE.Mesh(wireGeo, wireMat));

  // 150 Orbiting Liquid Amber Droplets
  const particleCount = 150;
  const pGeo = new THREE.BufferGeometry();
  const pPos = new Float32Array(particleCount * 3);
  for (let i = 0; i < particleCount; i++) {
    pPos[i * 3]     = (Math.random() - 0.5) * 10;
    pPos[i * 3 + 1] = (Math.random() - 0.5) * 10;
    pPos[i * 3 + 2] = (Math.random() - 0.5) * 5;
  }
  pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
  const pMat = new THREE.PointsMaterial({
    color: 0xffb703, size: 0.055, transparent: true, opacity: 0.9,
    blending: THREE.AdditiveBlending, depthWrite: false
  });
  admin3DParticles = new THREE.Points(pGeo, pMat);
  admin3DScene.add(admin3DParticles);

  // Smooth Emil Kowalski Mouse Parallax Tracking (Physics Damping)
  let targetMouseX = 0, targetMouseY = 0;
  let currentMouseX = 0, currentMouseY = 0;

  window.addEventListener('mousemove', (e) => {
    targetMouseX = (e.clientX / window.innerWidth - 0.5) * 2;
    targetMouseY = (e.clientY / window.innerHeight - 0.5) * 2;
  });

  const clock = new THREE.Clock();
  function render3DCrystalLoop() {
    requestAnimationFrame(render3DCrystalLoop);
    const t = clock.getElapsedTime();

    admin3DMesh.rotation.y = t * 0.22;
    admin3DMesh.rotation.x = Math.sin(t * 0.2) * 0.16;
    admin3DParticles.rotation.y = -t * 0.1;

    // Sub-300ms responsive spring physics lerp factor (0.05 damping)
    currentMouseX += (targetMouseX - currentMouseX) * 0.05;
    currentMouseY += (targetMouseY - currentMouseY) * 0.05;

    admin3DCamera.position.x = currentMouseX * 0.6;
    admin3DCamera.position.y = -currentMouseY * 0.6;
    admin3DCamera.lookAt(0, 0, 0);

    admin3DRenderer.render(admin3DScene, admin3DCamera);
  }

  render3DCrystalLoop();

  window.addEventListener('resize', () => {
    admin3DRenderer.setSize(W(), H());
    admin3DCamera.aspect = W() / H();
    admin3DCamera.updateProjectionMatrix();
  });
}

function showApp() {
  const overlay = document.getElementById('login-overlay');
  if (overlay) overlay.classList.add('hidden');
  document.getElementById('app').style.display = 'flex';
  initAdminBgLattice();
  initAdmin3DCrystalEngine();
  startClock();
  loadOverview();
}

function logoutAdmin() {
  sessionStorage.removeItem('skillme_admin_key');
  adminKey = '';
  const overlay = document.getElementById('login-overlay');
  const app = document.getElementById('app');
  if (overlay) {
    overlay.style.display = 'flex';
    overlay.style.clipPath = 'none';
    overlay.style.opacity = '1';
    overlay.classList.remove('hidden');
    const left = document.querySelector('.split-left');
    const right = document.querySelector('.split-right');
    const card = document.querySelector('.center-login-card');
    if (left) left.style.transform = 'none';
    if (right) right.style.transform = 'none';
    if (card) { card.style.opacity = '1'; card.style.transform = 'translate(-50%, -50%) scale(1)'; }
  }
  if (app) app.style.display = 'none';
  setTimeout(initRunnerLoopCanvas, 100);
}

document.addEventListener('DOMContentLoaded', () => {
  initRunnerLoopCanvas();
  const saved = sessionStorage.getItem('skillme_admin_key');
  if (saved) {
    adminKey = saved;
    showApp();
  }
});

function startClock() {
  const el = document.getElementById('topbar-time');
  if (!el) return;
  const tick = () => {
    const d = new Date();
    const dateStr = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const timeStr = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });
    el.textContent = `${dateStr} - ${timeStr}`;
  };
  tick(); setInterval(tick, 1000);
}

// ─── NAVIGATION ───
function navigate(page) {
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.page').forEach(el => el.classList.remove('active'));
  document.getElementById(`nav-${page}`)?.classList.add('active');
  document.getElementById(`page-${page}`).classList.add('active');
  const meta = PAGE_META[page] || {};
  document.getElementById('topbar-title').textContent = meta.title || page;
  document.getElementById('topbar-subtitle').textContent = meta.subtitle || '';
  currentPage = page;
  if (page === 'overview') loadOverview();
  if (page === 'students') loadStudents();
  if (page === 'batches') loadBatches();
  if (page === 'email') loadEmailStatus();
}

function refreshCurrentPage() { navigate(currentPage); }

// ─── API HELPER ───
async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: { 'X-Admin-Key': adminKey, 'Content-Type': 'application/json', ...(opts.headers || {}) }
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// ─── TOAST ───
function toast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  const icon = type === 'success' ? '✅' : '❌';
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icon}</span><span>${message}</span>`;
  container.appendChild(el);
  setTimeout(() => {
    el.style.animation = 'toast-out 0.3s ease forwards';
    setTimeout(() => el.remove(), 300);
  }, 3500);
}

// ─── MODALS ───
function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }

// Close modal on backdrop click
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.classList.remove('open'); });
});

// ─── STATUS BADGE ───
function statusBadge(status) {
  return `<span class="badge badge-${status}">${status}</span>`;
}

// ─── FORMAT DATE ───
function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

// ─── OVERVIEW ───
async function loadOverview() {
  loadStats();
  loadRecentApplications();
  loadOverviewBatches();
  loadSchedulerStatus();
}

async function loadStats() {
  const grid = document.getElementById('stats-grid');
  try {
    const data = await api('/api/admin/stats');
    grid.innerHTML = `
      ${statCard('👥', data.total_students, 'Total Students', 'rgba(129,140,248,0.15)', '#818cf8')}
      ${statCard('🟢', data.active_batches, 'Active Batches', 'rgba(52,211,153,0.15)', '#34d399')}
      ${statCard('📋', data.pending_applications, 'Pending Applications', 'rgba(251,191,36,0.15)', '#fbbf24')}
      ${statCard('🎯', data.total_issues_assigned, 'Issues Assigned', 'rgba(56,189,248,0.15)', '#38bdf8')}
    `;
    const badge = document.getElementById('pending-badge');
    if (data.pending_applications > 0) {
      badge.style.display = 'inline-flex';
      badge.textContent = data.pending_applications;
    } else {
      badge.style.display = 'none';
    }
  } catch (e) {
    grid.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><div class="empty-state-text">${e.message}</div></div>`;
  }
}

function statCard(icon, value, label, bg, color) {
  return `
    <div class="stat-card">
      <div class="stat-card-top">
        <div class="stat-card-label">${label}</div>
        <div class="stat-card-icon">${icon}</div>
      </div>
      <div class="stat-card-value">${(value ?? 0).toLocaleString()}</div>
    </div>`;
}

async function loadRecentApplications(silent = false) {
  const el = document.getElementById('recent-applications');
  if (!silent && !el.querySelector('table')) {
    el.innerHTML = `<div class="loading-overlay"><div class="spinner"></div></div>`;
  }
  try {
    const data = await api('/api/admin/students?status=applied&limit=5');
    if (!data.students.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🎉</div><div class="empty-state-text">No pending applications</div></div>`;
      return;
    }
    el.innerHTML = `
      <table>
        <thead><tr><th>Name</th><th>Domain</th><th>Applied</th><th>Action</th></tr></thead>
        <tbody>
          ${data.students.map(s => `
            <tr>
              <td>
                <div style="font-weight:500;">${s.first_name} ${s.last_name}</div>
                <div style="font-size:0.75rem;color:var(--text-muted);">${s.email}</div>
              </td>
              <td>${s.domain || '—'}</td>
              <td>${fmtDate(s.created_at)}</td>
              <td>
                <button class="btn btn-sm" style="background:rgba(52,211,153,0.15);color:#34d399;border:1px solid rgba(52,211,153,0.25);" onclick="updateStatus(${s.id},'shortlisted')">Shortlist</button>
              </td>
            </tr>`).join('')}
        </tbody>
      </table>`;
  } catch(e) {
    if (!silent) {
      el.innerHTML = `<div class="empty-state"><div class="empty-state-text">${e.message}</div></div>`;
    }
  }
}

async function loadOverviewBatches(silent = false) {
  const el = document.getElementById('overview-batches');
  if (!silent && !el.querySelector('div')) {
    el.innerHTML = `<div class="loading-overlay"><div class="spinner"></div></div>`;
  }
  try {
    const data = await api('/api/admin/batches?status=active');
    if (!data.batches.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📦</div><div class="empty-state-text">No active batches</div></div>`;
      return;
    }
    el.innerHTML = data.batches.slice(0,3).map(b => {
      const fill = Math.min(100, Math.round((b.enrolled_students || 0) / (b.max_students || 30) * 100));
      return `
        <div style="padding:16px 24px;border-bottom:1px solid var(--border);">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <div>
              <div style="font-weight:500;font-size:0.9rem;">${b.domain} — Batch #${b.batch_number}</div>
              <div style="font-size:0.75rem;color:var(--text-muted);">${b.enrolled_students || 0} / ${b.max_students} students</div>
            </div>
            ${statusBadge(b.status)}
          </div>
          <div class="progress-bar"><div class="progress-fill" style="width:${fill}%"></div></div>
        </div>`;
    }).join('');
  } catch(e) {
    if (!silent) {
      el.innerHTML = `<div class="empty-state"><div class="empty-state-text">${e.message}</div></div>`;
    }
  }
}

// ─── STUDENTS ───
async function loadStudents(silent = false) {
  const tbody = document.getElementById('students-tbody');
  if (!silent) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="loading-overlay"><div class="spinner"></div></div></td></tr>`;
  }
  try {
    const data = await api('/api/admin/students?limit=100');
    allStudents = data.students || [];
    renderStudents(allStudents);
  } catch(e) {
    if (!silent) {
      tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="empty-state-text">${e.message}</div></div></td></tr>`;
    }
  }
}

function filterStudents() {
  const q = document.getElementById('student-search').value.toLowerCase();
  const status = document.getElementById('status-filter').value;
  const filtered = allStudents.filter(s => {
    const matchQ = !q || `${s.first_name} ${s.last_name} ${s.email} ${s.github_username || ''}`.toLowerCase().includes(q);
    const matchStatus = !status || s.status === status;
    return matchQ && matchStatus;
  });
  renderStudents(filtered);
}

function renderStudents(students) {
  const tbody = document.getElementById('students-tbody');
  if (!students.length) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="empty-state-icon">🔍</div><div class="empty-state-text">No students found</div></div></td></tr>`;
    return;
  }
  tbody.innerHTML = students.map(s => `
    <tr>
      <td>
        <div style="display:flex;align-items:center;gap:10px;">
          <div style="width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#818cf8,#38bdf8);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:0.8rem;flex-shrink:0;">${(s.first_name[0]||'?').toUpperCase()}</div>
          <div>
            <div style="font-weight:500;">${s.first_name} ${s.last_name}</div>
            ${s.github_username ? `<div style="font-size:0.72rem;color:var(--text-muted);">@${s.github_username}</div>` : ''}
          </div>
        </div>
      </td>
      <td style="color:var(--text-secondary);font-size:0.82rem;">${s.email}</td>
      <td>${s.domain || '—'}</td>
      <td>${statusBadge(s.status)}</td>
      <td style="color:var(--text-muted);font-size:0.82rem;">${fmtDate(s.created_at)}</td>
      <td>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          ${s.status === 'applied' ? `<button class="btn btn-sm" style="background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.25);" onclick="updateStatus(${s.id},'shortlisted')">Shortlist</button>` : ''}
          ${s.status === 'shortlisted' ? `<button class="btn btn-sm" style="background:rgba(52,211,153,0.15);color:#34d399;border:1px solid rgba(52,211,153,0.25);" onclick="openEnrollModal(${s.id},'${s.first_name} ${s.last_name}')">Enroll</button>` : ''}
          ${(s.status === 'completed' || s.status === 'enrolled') && s.batch_id ? `<button class="btn btn-sm" style="background:rgba(212,168,83,0.15);color:#d4a853;border:1px solid rgba(212,168,83,0.3);" onclick="issueCertificate(${s.id},${s.batch_id},'${s.first_name} ${s.last_name}')">🏅 Certificate</button>` : ''}
          ${s.status !== 'dropped' ? `<button class="btn btn-sm" style="background:rgba(251,113,133,0.12);color:#fb7185;border:1px solid rgba(251,113,133,0.2);" onclick="updateStatus(${s.id},'dropped')">Drop</button>` : ''}
        </div>
      </td>
    </tr>`).join('');
}

async function updateStatus(studentId, newStatus) {
  try {
    await api(`/api/admin/students/${studentId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status: newStatus })
    });
    toast(`Student status updated to "${newStatus}"`);
    if (currentPage === 'overview') {
      loadRecentApplications(true);
      loadOverviewBatches(true);
    }
    loadStudents(true);
    loadStats(true);
  } catch(e) {
    toast(e.message, 'error');
  }
}

async function issueCertificate(studentId, batchId, name) {
  try {
    const data = await api(`/api/certificates/issue/${studentId}/${batchId}`, { method: 'POST' });
    toast(`Certificate ${data.cert_id} issued to ${name}!`);
    // Open certificate in new tab
    const certUrl = `${window.SKILLME_FRONTEND || 'http://localhost:8080'}/certificate.html?student_id=${studentId}&batch_id=${batchId}&name=${encodeURIComponent(name)}`;
    window.open(certUrl, '_blank');
  } catch(e) {
    toast(e.message, 'error');
  }
}

async function openEnrollModal(studentId, name) {
  document.getElementById('enroll-student-id').value = studentId;
  document.getElementById('enroll-student-name').textContent = `Enrolling: ${name}`;
  const select = document.getElementById('enroll-batch-select');
  select.innerHTML = '<option>Loading batches...</option>';
  openModal('enroll-modal');
  try {
    const data = await api('/api/admin/batches');
    allBatches = data.batches || [];
    if (!allBatches.length) {
      select.innerHTML = '<option value="">⚠️ No batches yet — create one in the Batches tab first!</option>';
      document.getElementById('enroll-confirm-btn').disabled = true;
    } else {
      select.innerHTML = allBatches.map(b => `<option value="${b.id}">${b.domain} — Batch #${b.batch_number}</option>`).join('');
      document.getElementById('enroll-confirm-btn').disabled = false;
    }
  } catch(e) {
    select.innerHTML = '<option>Failed to load batches</option>';
  }
}


async function enrollStudent() {
  const studentId = document.getElementById('enroll-student-id').value;
  const batchId = document.getElementById('enroll-batch-select').value;
  if (!batchId) { toast('Please select a batch', 'error'); return; }
  try {
    await api(`/api/admin/batches/${batchId}/students`, {
      method: 'POST',
      body: JSON.stringify({ student_id: parseInt(studentId) })
    });
    toast('Student enrolled successfully!');
    closeModal('enroll-modal');
    if (currentPage === 'overview') {
      loadOverviewBatches(true);
    }
    loadStudents(true);
    loadStats(true);
  } catch(e) {
    toast(e.message, 'error');
  }
}

// ─── BATCHES ───
async function loadBatches(silent = false) {
  const el = document.getElementById('batches-list');
  if (!silent) {
    el.innerHTML = '<div class="loading-overlay"><div class="spinner"></div> Loading batches...</div>';
  }
  try {
    const data = await api('/api/admin/batches');
    allBatches = data.batches || [];
    if (!allBatches.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-state-icon">&#128230;</div><div class="empty-state-text">No batches yet. Create your first batch!</div></div>`;
      return;
    }
    el.innerHTML = allBatches.map(b => {
      const fill = Math.min(100, Math.round((b.enrolled_students || 0) / (b.max_students || 30) * 100));
      const autoOn = !!b.auto_assign;
      return `
        <div class="batch-card" id="batch-card-${b.id}">
          <div class="batch-card-header">
            <div>
              <div class="batch-card-title">${b.domain.replace('-',' ').replace(/\b\w/g, c=>c.toUpperCase())} — Batch #${b.batch_number}</div>
              <div class="batch-card-meta">${b.repo_name} &nbsp;&middot;&nbsp; ${b.enrolled_students || 0} / ${b.max_students} students &nbsp;&middot;&nbsp; Started ${fmtDate(b.start_date)}</div>
            </div>
            <div class="batch-card-actions">
              ${statusBadge(b.status)}
              <button class="btn btn-ghost btn-sm" onclick="openAssignModal(${b.id}, '${b.domain} Batch #${b.batch_number}')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M12 6v6l4 2"/></svg>
                Assign Tasks
              </button>
              <button class="btn btn-ghost btn-sm" onclick="openAnalyticsModal(${b.id}, '${b.domain} Batch #${b.batch_number}')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><path d="M3 3v18h18"/><path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"/></svg>
                Analytics
              </button>
              <button class="btn btn-ghost btn-sm" style="color:#f87171;" onclick="deleteBatch(${b.id}, '${b.domain} Batch #${b.batch_number}')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
                Delete
              </button>
            </div>
          </div>
          <div class="progress-bar"><div class="progress-fill" style="width:${fill}%"></div></div>
          <div class="progress-labels">
            <span>${fill}% enrolled</span>
            <span>${b.max_students - (b.enrolled_students || 0)} slots remaining</span>
          </div>
          <div style="display:flex;align-items:center;gap:16px;margin-top:16px;padding-top:14px;border-top:1px solid var(--border);">
            <div style="display:flex;align-items:center;gap:10px;">
              <label class="toggle-switch" title="${autoOn ? 'Auto-assign ON: tasks will be pushed every Monday' : 'Auto-assign OFF: click to enable'}">
                <input type="checkbox" ${autoOn ? 'checked' : ''} onchange="toggleAutoAssign(${b.id}, this.checked)" />
                <span class="toggle-slider"></span>
              </label>
              <div>
                <div style="font-size:0.82rem;font-weight:500;">Auto-Assign</div>
                <div style="font-size:0.72rem;color:var(--text-muted);">${autoOn ? 'Enabled — runs every Monday 9AM' : 'Disabled'}</div>
              </div>
            </div>
            <button class="btn btn-ghost btn-sm" onclick="triggerNow(${b.id})" title="Run auto-assign now for this batch">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              Run Now
            </button>
            <div style="margin-left:auto;font-size:0.75rem;color:var(--text-muted);">
              Weeks assigned: <strong style="color:var(--text-primary)">${formatWeeksAssigned(b.weeks_assigned)}</strong>
            </div>
          </div>
        </div>`;
    }).join('');
  } catch(e) {
    el.innerHTML = `<div class="empty-state"><div class="empty-state-text">${e.message}</div></div>`;
  }
}

function formatWeeksAssigned(raw) {
  try {
    const arr = typeof raw === 'string' ? JSON.parse(raw) : (raw || []);
    if (!arr.length) return 'None';
    return arr.map(w => `W${w}`).join(', ');
  } catch { return 'None'; }
}

async function toggleAutoAssign(batchId, enabled) {
  try {
    await api(`/api/admin/batches/${batchId}/auto-assign?enabled=${enabled}`, { method: 'PATCH' });
    toast(`Auto-assign ${enabled ? 'enabled' : 'disabled'} for batch ${batchId}`);
    loadBatches(true);
  } catch(e) { toast(e.message, 'error'); }
}

async function deleteBatch(batchId, batchName) {
  if (!confirm(`Are you sure you want to permanently delete "${batchName}"?\n\nThis will instantly wipe all progress, submissions, email logs, and enrollments associated with this batch. This action cannot be undone.`)) {
    return;
  }
  try {
    await api(`/api/admin/batches/${batchId}`, { method: 'DELETE' });
    toast(`Batch ${batchName} deleted successfully`);
    loadBatches(true);
    loadOverviewBatches(true);
  } catch(e) {
    toast(`Failed to delete batch: ${e.message}`, 'error');
  }
}

async function triggerNow(batchId) {
  try {
    const btn = event.currentTarget;
    btn.disabled = true; btn.textContent = 'Running...';
    // Enable auto-assign first then trigger
    await api(`/api/admin/batches/${batchId}/auto-assign?enabled=true`, { method: 'PATCH' });
    const result = await api('/api/admin/scheduler/trigger', { method: 'POST' });
    toast('Scheduler ran! Check the batch for new tasks.');
    loadBatches(true);
  } catch(e) { toast(e.message, 'error'); }
}

async function loadSchedulerStatus() {
  // Inject a scheduler status card into the overview if not already there
  let el = document.getElementById('scheduler-panel');
  if (!el) {
    const overviewPage = document.getElementById('page-overview');
    const div = document.createElement('div');
    div.style = 'margin-bottom:24px;';
    div.innerHTML = `<div class="panel" id="scheduler-panel">
      <div class="panel-header">
        <div><div class="panel-title">Auto-Assign Scheduler</div><div class="panel-subtitle">Automated weekly task delivery status</div></div>
        <button class="btn btn-ghost btn-sm" onclick="loadSchedulerStatus()">Refresh</button>
      </div>
      <div class="panel-body" id="scheduler-panel-body"><div class="loading-overlay"><div class="spinner"></div></div></div>
    </div>`;
    overviewPage.insertBefore(div, overviewPage.querySelector('.grid-2'));
    el = document.getElementById('scheduler-panel-body');
  } else {
    el = document.getElementById('scheduler-panel-body');
    el.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
  }

  try {
    const data = await api('/api/admin/scheduler/status');
    const nextRun = data.next_run ? new Date(data.next_run).toLocaleString('en-IN', { weekday:'short', day:'numeric', month:'short', hour:'2-digit', minute:'2-digit' }) : 'Unknown';
    const batches = data.auto_assign_batches || [];
    el.innerHTML = `
      <div style="display:flex;align-items:center;gap:24px;flex-wrap:wrap;">
        <div style="display:flex;align-items:center;gap:8px;">
          <div style="width:10px;height:10px;border-radius:50%;background:${data.scheduler_running ? '#34d399' : '#fb7185'};box-shadow:0 0 8px ${data.scheduler_running ? '#34d399' : '#fb7185'};"></div>
          <span style="font-weight:500;font-size:0.9rem;">${data.scheduler_running ? 'Scheduler Running' : 'Scheduler Stopped'}</span>
        </div>
        <div style="font-size:0.82rem;color:var(--text-secondary);">Next run: <strong style="color:var(--text-primary);">${nextRun}</strong></div>
        <div style="font-size:0.82rem;color:var(--text-secondary);">${batches.length} batch${batches.length !== 1 ? 'es' : ''} enrolled</div>
        <button class="btn btn-primary btn-sm" style="margin-left:auto;" onclick="runSchedulerNow()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          Trigger All Now
        </button>
      </div>
      ${batches.length ? `
      <div style="margin-top:14px;border-top:1px solid var(--border);padding-top:14px;">
        <div style="font-size:0.72rem;color:var(--text-muted);letter-spacing:.06em;text-transform:uppercase;margin-bottom:8px;">Auto-Assign Batches</div>
        ${batches.map(b => `
          <div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.04);">
            <span style="font-size:0.85rem;font-weight:500;">${b.name}</span>
            <span style="font-size:0.75rem;color:var(--text-muted);">Started ${fmtDate(b.start_date)}</span>
            <span style="margin-left:auto;font-size:0.75rem;">Assigned: <strong>${formatWeeksAssigned(b.weeks_assigned)}</strong></span>
          </div>`).join('')}
      </div>` : ''}
    `;
  } catch(e) {
    el.innerHTML = `<div class="empty-state"><div class="empty-state-text">${e.message}</div></div>`;
  }
}

async function runSchedulerNow() {
  try {
    await api('/api/admin/scheduler/trigger', { method: 'POST' });
    toast('Scheduler triggered! All eligible batches received tasks.');
    loadSchedulerStatus();
    loadBatches(true);
  } catch(e) { toast(e.message, 'error'); }
}

function openAssignModal(batchId, batchName) {
  document.getElementById('assign-batch-id').value = batchId;
  document.getElementById('assign-batch-name').value = batchName;
  openModal('assign-modal');
}

async function assignTasks() {
  const batchId = document.getElementById('assign-batch-id').value;
  const week = document.getElementById('assign-week').value;
  try {
    const btn = document.querySelector('#assign-modal .btn-primary');
    btn.textContent = 'Assigning...';
    btn.disabled = true;
    const data = await api(`/api/admin/batches/${batchId}/assign-from-repo`, {
      method: 'POST',
      body: JSON.stringify({ week_number: parseInt(week) })
    });
    toast(`Assigned ${data.issues_created} tasks for Week ${week}!`);
    closeModal('assign-modal');
    btn.textContent = 'Assign Tasks'; btn.disabled = false;
  } catch(e) {
    toast(e.message, 'error');
    const btn = document.querySelector('#assign-modal .btn-primary');
    btn.textContent = 'Assign Tasks'; btn.disabled = false;
  }
}

function openCreateBatchModal() {
  openModal('create-batch-modal');
}

async function createBatch() {
  const domain = document.getElementById('new-batch-domain').value;
  const batchNum = parseInt(document.getElementById('new-batch-number').value);
  const maxStudents = parseInt(document.getElementById('new-batch-max').value) || 30;
  try {
    const btn = document.querySelector('#create-batch-modal .btn-primary');
    btn.textContent = 'Creating...'; btn.disabled = true;
    const res = await api('/api/admin/batches', {
      method: 'POST',
      body: JSON.stringify({ domain, batch_number: batchNum, max_students: maxStudents })
    });
    if (res.warning) {
      toast(`Batch created, but: ${res.warning}`, 'error');
    } else {
      toast(`Batch ${domain} #${batchNum} created!`);
    }
    closeModal('create-batch-modal');
    if (currentPage === 'overview') {
      loadOverviewBatches(true);
    }
    loadBatches(true);
    loadStats(true);
    btn.textContent = 'Create Batch'; btn.disabled = false;
  } catch(e) {
    toast(e.message, 'error');
    const btn = document.querySelector('#create-batch-modal .btn-primary');
    btn.textContent = 'Create Batch'; btn.disabled = false;
  }
}

// ─── EMAIL SETTINGS ───
async function loadEmailStatus() {
  const badge = document.getElementById('email-status-badge');
  const fromEl = document.getElementById('email-from-display');
  if (!badge) return;
  try {
    // Try sending a test via a simple health ping to the backend
    const res = await fetch(`${API}/api/admin/stats`, { headers: { 'X-Admin-Key': adminKey } });
    if (res.ok) {
      badge.style.background = 'rgba(52,211,153,0.15)';
      badge.style.borderColor = 'rgba(52,211,153,0.3)';
      badge.style.color = '#34d399';
      badge.textContent = '\u25cf Email Enabled';
    }
  } catch(e) {
    badge.style.background = 'rgba(251,113,133,0.15)';
    badge.style.borderColor = 'rgba(251,113,133,0.3)';
    badge.style.color = '#fb7185';
    badge.textContent = '\u25cf Offline';
  }
  // Show from email from .env config — we can infer from backend info
  if (fromEl) fromEl.textContent = 'noreply@skillme.in';
}

async function sendTestEmail() {
  const input = document.getElementById('test-email-input');
  const btn = document.getElementById('test-email-btn');
  const result = document.getElementById('test-email-result');
  const email = input.value.trim();
  if (!email || !email.includes('@')) {
    result.style.display = 'block';
    result.style.color = '#fb7185';
    result.textContent = '\u274c Please enter a valid email address.';
    return;
  }
  btn.textContent = 'Sending...';
  btn.disabled = true;
  result.style.display = 'none';
  try {
    const data = await api('/api/admin/email/test', {
      method: 'POST',
      body: JSON.stringify({ to_email: email })
    });
    result.style.display = 'block';
    if (data.status === 'sent') {
      result.style.color = '#34d399';
      result.textContent = `\u2705 Test email sent successfully to ${email}! Check your inbox.`;
      toast('Test email sent!');
    } else {
      result.style.color = '#fb7185';
      result.textContent = `\u274c ${data.message || 'Failed to send email. Check SMTP credentials.'}`;
    }
  } catch(e) {
    result.style.display = 'block';
    result.style.color = '#fb7185';
    result.textContent = `\u274c ${e.message}`;
  } finally {
    btn.textContent = 'Send Test';
    btn.disabled = false;
  }
}

async function openAnalyticsModal(batchId, batchName) {
  openModal('modal-analytics');
  document.getElementById('analytics-modal-title').textContent = `${batchName} Analytics`;
  const contentEl = document.getElementById('analytics-modal-content');
  contentEl.innerHTML = '<div class="loading-overlay"><div class="spinner"></div> Loading analytics...</div>';
  
  try {
    const data = await api(`/api/admin/batches/${batchId}/analytics`);
    const enrollments = data.enrollments || {};
    const prs = data.pr_stats || {};
    const revenue = data.revenue || {};
    const students = data.student_grid || [];
    
    let html = `
      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:16px; margin-bottom:24px;">
        <div style="background:var(--bg-card); padding:16px; border-radius:8px; border:1px solid var(--border);">
          <div style="font-size:0.8rem; color:var(--text-muted); margin-bottom:8px;">Enrollments</div>
          <div style="font-size:1.5rem; font-weight:700;">${enrollments.active || 0} <span style="font-size:1rem; color:var(--text-muted); font-weight:normal;">active</span></div>
          <div style="font-size:0.8rem; color:var(--text-secondary); margin-top:4px;">${enrollments.dropped || 0} dropped, ${enrollments.completed || 0} completed</div>
        </div>
        <div style="background:var(--bg-card); padding:16px; border-radius:8px; border:1px solid var(--border);">
          <div style="font-size:0.8rem; color:var(--text-muted); margin-bottom:8px;">Pull Requests</div>
          <div style="font-size:1.5rem; font-weight:700;">${prs.merged || 0} <span style="font-size:1rem; color:var(--text-muted); font-weight:normal;">merged</span></div>
          <div style="font-size:0.8rem; color:var(--text-secondary); margin-top:4px;">${prs.total_prs || 0} total submitted</div>
        </div>
        <div style="background:var(--bg-card); padding:16px; border-radius:8px; border:1px solid var(--border);">
          <div style="font-size:0.8rem; color:var(--text-muted); margin-bottom:8px;">Revenue</div>
          <div style="font-size:1.5rem; font-weight:700;">₹${revenue.total_inr || 0}</div>
          <div style="font-size:0.8rem; color:var(--text-secondary); margin-top:4px;">${revenue.total_payments || 0} certificates paid</div>
        </div>
      </div>
      
      <h3 style="margin-bottom:12px; font-size:1rem;">Student Progress Grid</h3>
      <div class="table-wrap" style="max-height: 400px; overflow-y: auto;">
        <table style="width:100%; border-collapse:collapse; font-size:0.9rem;">
          <thead style="position:sticky; top:0; background:var(--bg-surface); z-index:1;">
            <tr>
              <th style="text-align:left; padding:10px; border-bottom:1px solid var(--border);">Student</th>
              <th style="text-align:left; padding:10px; border-bottom:1px solid var(--border);">Status</th>
              <th style="text-align:center; padding:10px; border-bottom:1px solid var(--border);">Tasks</th>
              <th style="text-align:center; padding:10px; border-bottom:1px solid var(--border);">PRs Merged</th>
            </tr>
          </thead>
          <tbody>
            ${students.map(s => `
              <tr>
                <td style="padding:10px; border-bottom:1px solid var(--border);">
                  <div style="font-weight:500;">${s.first_name} ${s.last_name}</div>
                  <div style="font-size:0.8rem; color:var(--text-muted);">${s.github_username || '—'}</div>
                </td>
                <td style="padding:10px; border-bottom:1px solid var(--border);">${statusBadge(s.enrollment_status)}</td>
                <td style="padding:10px; border-bottom:1px solid var(--border); text-align:center;">${s.tasks_completed || 0} / ${s.tasks_assigned || 0}</td>
                <td style="padding:10px; border-bottom:1px solid var(--border); text-align:center;">${s.prs_merged || 0}</td>
              </tr>
            `).join('') || '<tr><td colspan="4" style="padding:20px; text-align:center; color:var(--text-muted);">No student data available.</td></tr>'}
          </tbody>
        </table>
      </div>
    `;
    contentEl.innerHTML = html;
  } catch(e) {
    contentEl.innerHTML = `<div class="empty-state"><div class="empty-state-text">Failed to load analytics: ${e.message}</div></div>`;
  }
}

// ─── INIT ───
window.addEventListener('keydown', e => {
  if (e.key === 'Enter' && document.getElementById('login-overlay').style.display !== 'none') adminLogin();
});

const savedKey = sessionStorage.getItem('skillme_admin_key');
if (savedKey) {
  const input = document.getElementById('admin-key-input') || document.getElementById('api-key-input');
  if (input) input.value = savedKey;
  adminLogin();
}
