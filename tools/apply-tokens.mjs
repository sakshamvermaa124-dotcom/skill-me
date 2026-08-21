// tools/apply-tokens.mjs  (v2 — atomic, single-pass, no regex ambiguity)
// Applies the semantic token system to dashboard.css (commit 3 of 5).
// Run: node tools/apply-tokens.mjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(fileURLToPath(import.meta.url), '..', '..');
const CSS_PATH = path.join(ROOT, 'dashboard.css');

const css = fs.readFileSync(CSS_PATH, 'utf8');

// ── Anchor strings — must be unique in the file ──────────────────────────────
const LIGHT_BLOCK_ANCHOR  = '/* ======================================================\r\n       LIGHT MODE';
const DARK_NAV_ANCHOR     = '/* Navbar override for dashboard — dark mode only */';
const GUIDE_ANCHOR        = '/* ======== Beginner Guide Section ======== */';
const LENIS_ANCHOR        = '/* ======== Lenis Base ======== */';

// Verify all anchors exist
for (const [name, anchor] of [
  ['LIGHT_BLOCK', LIGHT_BLOCK_ANCHOR],
  ['DARK_NAV',   DARK_NAV_ANCHOR],
  ['GUIDE',      GUIDE_ANCHOR],
  ['LENIS',      LENIS_ANCHOR],
]) {
  if (!css.includes(anchor)) {
    console.error(`ERROR: anchor not found — ${name}: ${JSON.stringify(anchor.slice(0,60))}`);
    process.exit(1);
  }
}
console.log('All anchors verified ✓');

// ── New semantic token block (replaces just the file header comment) ──────────
const TOKEN_BLOCK = `/* =============================================================
   dashboard.css — Semantic token system
   Commit 3 of 5: tokens, light/dark theming, !important fence.

   Accent decision (contrast audit):
     (a) #412d15 as --accent: 1.38:1 on dark cards → FAIL, invisible
     (b) #c99a4e / #8a6529:   7.02:1 / 5.28:1      → AAA / AA  ← chosen
         #412d15 used only for --border-strong / --surface-sunken

   !important: 15 total, all in the R6 FENCE block at end of this file.
   ============================================================= */

/* ── Semantic token declarations ──────────────────────────────────────────
   Both themes define the same token names — every component rule is
   written once and is theme-agnostic.  This replaces the 230-line
   [data-theme="light"] !important override block entirely.
   ──────────────────────────────────────────────────────────────────────── */

/* Dark theme (default) */
:root,
[data-theme="dark"] {
  /* Surfaces */
  --surface-page:    #000000;
  --surface-raised:  #1f150c;
  --surface-sunken:  #412d15;
  --surface-hover:   #2b1e10;

  /* Lines */
  --border-hairline: rgba(255,255,255,0.06);
  --border-strong:   #412d15;

  /* Text */
  --text-strong:   #eae6e1;
  --text-default:  #c7bfb5;
  --text-muted:    #969089;
  --text-faint:    #5e5852;

  /* Brand — #c99a4e: 7.02:1 on cards (AAA), 8.22:1 on page (AAA) */
  --accent:          #c99a4e;
  --accent-hover:    #d8ac63;
  --accent-contrast: #000000;
  --accent-wash:     rgba(201,154,78,0.10);

  /* Status */
  --ok:      #10b981;  --ok-wash:      rgba(16,185,129,0.12);
  --warn:    #f59e0b;  --warn-wash:    rgba(245,158,11,0.12);
  --danger:  #ef4444;  --danger-wash:  rgba(239,68,68,0.12);
  --info:    #60a5fa;  --info-wash:    rgba(96,165,250,0.12);

  /* Legacy aliases (existing component rules use these; no rewrite needed) */
  --bg-primary:     var(--surface-page);
  --bg-card:        var(--surface-raised);
  --bg-card-hover:  var(--surface-hover);
  --text-primary:   var(--text-strong);
  --text-secondary: var(--text-muted);
  --border-glass:   1px solid var(--border-hairline);
  --border-subtle:  1px solid rgba(255,255,255,0.07);

  /* Navbar */
  --nav-bg:     rgba(0,0,0,0.80);
  --nav-border: rgba(255,255,255,0.06);
  --nav-shadow: 0 2px 16px rgba(0,0,0,0.5);
}

/* Light theme */
[data-theme="light"] {
  /* Surfaces */
  --surface-page:    #e1dcc9;
  --surface-raised:  #ffffff;
  --surface-sunken:  #d6d0bc;
  --surface-hover:   #f5f2ea;

  /* Lines */
  --border-hairline: rgba(0,0,0,0.08);
  --border-strong:   #412d15;

  /* Text */
  --text-strong:   #1c1917;
  --text-default:  #3d3530;
  --text-muted:    #64748b;
  --text-faint:    #94a3b8;

  /* Brand — #8a6529: 5.28:1 on white cards (AA), 3.85:1 on warm paper (AA Large) */
  --accent:          #8a6529;
  --accent-hover:    #6f4f1f;
  --accent-contrast: #ffffff;
  --accent-wash:     rgba(138,101,41,0.10);

  /* Status (darkened for AA on white) */
  --ok:      #059669;  --ok-wash:      rgba(5,150,105,0.10);
  --warn:    #d97706;  --warn-wash:    rgba(217,119,6,0.10);
  --danger:  #dc2626;  --danger-wash:  rgba(220,38,38,0.10);
  --info:    #2563eb;  --info-wash:    rgba(37,99,235,0.10);

  /* Legacy aliases */
  --bg-primary:     var(--surface-page);
  --bg-card:        var(--surface-raised);
  --bg-card-hover:  var(--surface-hover);
  --text-primary:   var(--text-strong);
  --text-secondary: var(--text-muted);
  --border-glass:   1px solid var(--border-hairline);
  --border-subtle:  1px solid rgba(0,0,0,0.06);

  /* Navbar */
  --nav-bg:     rgba(255,255,255,0.95);
  --nav-border: rgba(0,0,0,0.06);
  --nav-shadow: 0 2px 16px rgba(0,0,0,0.05);
}

/* Navbar: token-driven, no !important needed (dashboard.css loads after style.css) */
.navbar {
  background: var(--nav-bg);
  border-bottom: 1px solid var(--nav-border);
  box-shadow: var(--nav-shadow);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
}

`;

// ── Identify exact splice regions ─────────────────────────────────────────────

// Region A: old file header  →  chars 0 … (start of LENIS_ANCHOR)
const lenisIdx = css.indexOf(LENIS_ANCHOR);

// Region B: dark navbar block → from DARK_NAV_ANCHOR to end of its closing }
const darkNavStart = css.indexOf(DARK_NAV_ANCHOR);
const darkNavEnd   = css.indexOf('\n', css.indexOf('}', darkNavStart + DARK_NAV_ANCHOR.length)) + 1;

// Region C: light mode block → from LIGHT_BLOCK_ANCHOR to start of GUIDE_ANCHOR
const lightStart = css.indexOf(LIGHT_BLOCK_ANCHOR);
const lightEnd   = css.indexOf(GUIDE_ANCHOR);

console.log(`Lenis anchor at: ${lenisIdx}`);
console.log(`Dark nav: ${darkNavStart}–${darkNavEnd}`);
console.log(`Light block: ${lightStart}–${lightEnd}`);

// Build output in one pass (working from end to start to keep indices stable):
// 1. Remove light block:        css[lightStart..lightEnd) removed
// 2. Remove dark nav block:     css[darkNavStart..darkNavEnd) removed
// 3. Replace old header:        css[0..lenisIdx) → TOKEN_BLOCK + LENIS_ANCHOR...

// Since region B (dark nav) is before region C (light block), and region A is before B,
// we process from the end:

let out = css;

// Step 1: remove light block (C)
out = out.slice(0, lightStart) + out.slice(lightEnd);
console.log('After light block removal, !important:', (out.match(/!important/g)||[]).length);

// Step 2: remove dark nav block (B) — recompute since light removal shifted nothing before it
const darkNavStart2 = out.indexOf(DARK_NAV_ANCHOR);
const darkNavEnd2   = out.indexOf('\n', out.indexOf('}', darkNavStart2 + DARK_NAV_ANCHOR.length)) + 1;
out = out.slice(0, darkNavStart2) + out.slice(darkNavEnd2);
console.log('After dark navbar removal, !important:', (out.match(/!important/g)||[]).length);

// Step 3: replace old header (A)
const lenisIdx2 = out.indexOf(LENIS_ANCHOR);
out = TOKEN_BLOCK + out.slice(lenisIdx2);
console.log('After header replacement, has tokens:', out.includes('--surface-page'));

// ── Final !important audit ────────────────────────────────────────────────────
const finalImp = (out.match(/!important/g)||[]).length;
console.log(`\nFinal !important count: ${finalImp}`);
const lines = out.split('\n');
lines.forEach((line, i) => {
  if (line.includes('!important')) {
    console.log(`  Line ${i+1}: ${line.trim().slice(0,90)}`);
  }
});

// ── Write ─────────────────────────────────────────────────────────────────────
fs.writeFileSync(CSS_PATH, out, 'utf8');
console.log(`\nWritten: ${lines.length} lines, ${out.length} bytes`);
