#!/usr/bin/env node
// tools/dash-contract-check.mjs
// ─────────────────────────────────────────────────────────────────────────────
// Zero-dependency regression guard for the dashboard JS ↔ HTML contract.
// Uses regex, NOT a DOM parser (R11: literal newlines inside onclick values
// would confuse most parsers). Run after every commit; must stay green.
//
// Exit codes:
//   0 — all assertions pass (including baselined pre-existing failures)
//   1 — one or more unexpected failures
//
// Usage:
//   node tools/dash-contract-check.mjs
//   node tools/dash-contract-check.mjs --verbose
// ─────────────────────────────────────────────────────────────────────────────

import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const VERBOSE = process.argv.includes('--verbose');
const ROOT = path.resolve(fileURLToPath(import.meta.url), '..', '..');
const HTML_PATH = path.join(ROOT, 'dashboard.html');
const JS_PATH   = path.join(ROOT, 'dashboard.js');

// ─────────────────────────────────────────────────────────────────────────────
// Load source files
// ─────────────────────────────────────────────────────────────────────────────
const html = fs.readFileSync(HTML_PATH, 'utf8');
const jsOrig = fs.readFileSync(JS_PATH, 'utf8');
const uiJsPath = path.join(ROOT, 'dashboard-ui.js');
const uiJs = fs.existsSync(uiJsPath) ? fs.readFileSync(uiJsPath, 'utf8') : '';
const js = jsOrig + '\n' + uiJs;

// ─────────────────────────────────────────────────────────────────────────────
// Known pre-existing failures — baselined so day-one diff is zero.
// These report as WARN rather than FAIL.  Fix them (J2) removes them here.
// ─────────────────────────────────────────────────────────────────────────────
const KNOWN_FAILURES = new Set([
  // PR Helper: HTML calls these but neither exists in dashboard.js (§1.5A)
  'generatePRTemplate',
  'copyPRHelperOutput',
]);

// ─────────────────────────────────────────────────────────────────────────────
// Ids that dashboard.js *creates* at runtime (not provided by dashboard.html).
// The checker skips these for A1 "all JS-referenced ids exist in HTML".
// ─────────────────────────────────────────────────────────────────────────────
const JS_CREATED_IDS = new Set([
  'completion-overlay',   // js:1044 — created via createElement
  'confetti-canvas',      // js creates canvas
  'completion-cred-area', // js creates div
  'pay-btn',              // js creates button in payment-banner
  'discount-code',        // js creates input in payment-banner
  'payment-banner',       // js creates the entire banner div
  'btn-view-offer',       // js:1484-1494 — createElement, id assigned on creation
]);

// ─────────────────────────────────────────────────────────────────────────────
// Ids that are on the JS side of the PR Helper mismatch (§1.5A).
// dashboard.js reads these ids but the HTML has NEVER provided them —
// that is the pre-existing bug. Baseline them as known-broken rather than
// reporting as unexpected failures.
// ─────────────────────────────────────────────────────────────────────────────
const JS_PR_HELPER_STALE_IDS = new Set([
  'pr-helper-issue-num',  // js:693 — old id, HTML uses pr-helper-issue
  'pr-helper-desc',       // js:694 — old id, HTML uses pr-helper-summary
  'pr-val-branch',        // js:699 — no such element in HTML
  'pr-val-commit',        // js:700 — no such element in HTML
  'pr-val-title',         // js:701 — no such element in HTML
  'pr-val-close',         // js:702 — no such element in HTML
]);

// ─────────────────────────────────────────────────────────────────────────────
// Classes that dashboard.js *emits* via innerHTML (not in the static HTML).
// ─────────────────────────────────────────────────────────────────────────────
const JS_CREATED_CLASSES = new Set([
  'sub-card', 'task-card', 'cred-pill', 'cred-pill-icon',
  'cert-banner', 'cert-banner-icon', 'cert-banner-text', 'cert-banner-actions',
  'completion-overlay', 'confetti-canvas', 'completion-cred-area',
  'milestone-pill', 'pay-btn', 'stat-fill',
]);

// ─────────────────────────────────────────────────────────────────────────────
// Derive the contract from dashboard.js (source of truth per §5.5)
// ─────────────────────────────────────────────────────────────────────────────

/** All ids that dashboard.js looks up with getElementById */
const requiredIds = new Set(
  [...js.matchAll(/getElementById\(\s*['"`]([^'"`]+)['"`]/g)].map(m => m[1])
);

/** All class/attribute selectors used in querySelector(All) calls */
const selectorStrings = [
  ...js.matchAll(/querySelector(?:All)?\(\s*['"`]([^'"`]+)['"`]/g)
].map(m => m[1]);

/** All names exposed on window.* = ... */
const exposedFunctions = new Set(
  [...js.matchAll(/window\.(\w+)\s*=/g)].map(m => m[1])
);

// ─────────────────────────────────────────────────────────────────────────────
// Helper: extract all id="..." values from dashboard.html
// ─────────────────────────────────────────────────────────────────────────────
function extractHtmlIds(source) {
  const ids = new Map(); // id -> count
  for (const m of source.matchAll(/\bid="([^"]+)"/g)) {
    ids.set(m[1], (ids.get(m[1]) ?? 0) + 1);
  }
  return ids;
}

/** Extract class names actually present in static HTML (not in <style>) */
function extractHtmlClasses(source) {
  const noStyle = source.replace(/<style[\s\S]*?<\/style>/gi, '');
  const classes = new Set();
  for (const m of noStyle.matchAll(/\bclass="([^"]+)"/g)) {
    for (const cls of m[1].trim().split(/\s+/)) classes.add(cls);
  }
  return classes;
}

/**
 * Extract top-level inline handler function calls from dashboard.html.
 * "Top-level" means not preceded by a dot (i.e. not a method call like
 * document.getElementById(...) or overlay.remove()).
 * This avoids false positives from chained method calls in multi-statement
 * inline handlers.
 */
function extractInlineHandlerCalls(source) {
  const calls = new Set();
  // Match inline event handler attribute values (handles multiline via /s flag)
  const handlerRe = /\bon\w+="([^"]*)"/gs;
  for (const m of source.matchAll(handlerRe)) {
    const body = m[1];
    // Only capture calls NOT preceded by a dot (to exclude .remove(), .add(), etc.)
    for (const call of body.matchAll(/(?<![.\w])([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(/g)) {
      calls.add(call[1]);
    }
  }
  return calls;
}

// ─────────────────────────────────────────────────────────────────────────────
// Collect HTML facts
// ─────────────────────────────────────────────────────────────────────────────
const htmlIds      = extractHtmlIds(html);
const htmlClasses  = extractHtmlClasses(html);
const inlineCalls  = extractInlineHandlerCalls(html);

// ─────────────────────────────────────────────────────────────────────────────
// Reporting infrastructure
// ─────────────────────────────────────────────────────────────────────────────
let failures = 0;
let warnings = 0;

function pass(msg)  { if (VERBOSE) console.log(`  \u2705  ${msg}`); }
function warn(msg)  { console.warn(`  \u26a0\ufe0f   WARN  ${msg}`); warnings++; }
function fail(msg)  { console.error(`  \u274c  FAIL  ${msg}`); failures++; }

function section(title) { console.log(`\n\u2500\u2500 ${title} \u2500\u2500`); }

// ─────────────────────────────────────────────────────────────────────────────
// ASSERTION 1: Every required id exists in HTML (or allowlists)
// ─────────────────────────────────────────────────────────────────────────────
section('A1 \u2014 Required ids present in HTML');
for (const id of [...requiredIds].sort()) {
  if (JS_CREATED_IDS.has(id)) {
    pass(`${id}  [js-created \u2014 skipped]`);
    continue;
  }
  if (JS_PR_HELPER_STALE_IDS.has(id)) {
    warn(`#${id}  \u2014 KNOWN PR Helper stale id (§1.5A). Fix in J2.`);
    continue;
  }
  if (htmlIds.has(id)) {
    pass(`#${id}`);
  } else {
    fail(`#${id}  \u2014 referenced in dashboard.js but not found in dashboard.html`);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ASSERTION 2: No duplicate ids in dashboard.html
// ─────────────────────────────────────────────────────────────────────────────
section('A2 \u2014 No duplicate ids in dashboard.html');
let dupCount = 0;
for (const [id, count] of htmlIds) {
  if (count > 1) {
    fail(`#${id}  appears ${count} times (getElementById silently picks first)`);
    dupCount++;
  }
}
if (dupCount === 0) pass('No duplicate ids found');

// ─────────────────────────────────────────────────────────────────────────────
// ASSERTION 3: Classes from JS selectors exist in HTML (or JS_CREATED list)
// ─────────────────────────────────────────────────────────────────────────────
section('A3 \u2014 Selector classes reachable from HTML or emitted by JS');
for (const sel of selectorStrings) {
  const classMatches = [...sel.matchAll(/\.([a-zA-Z][a-zA-Z0-9_-]*)/g)].map(m => m[1]);
  for (const cls of classMatches) {
    if (JS_CREATED_CLASSES.has(cls)) {
      pass(`.${cls}  [js-created \u2014 skipped]`);
    } else if (htmlClasses.has(cls)) {
      pass(`.${cls}`);
    } else {
      warn(`.${cls}  \u2014 used in querySelector but not found in static HTML (may be CSS-only or JS-created)`);
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ASSERTION 4: Ordinal / positional assertions
//   4a. First .guide-code-copy carries onclick starting with copyCode(this,'git clone
//   4b. Second .guide-code .cmd is 'cd' with a bare text node after it (R2)
//   4c. First .guide-code .url is the <repo-url> placeholder (R3 — not a commit msg)
//   4d. .milestone-actions-row exists inside .milestone-modal (R-1494)
// ─────────────────────────────────────────────────────────────────────────────
section('A4 \u2014 Ordinal / structural assertions');

// 4a — first guide-code-copy must start with the git clone copy command
{
  const m = html.match(/class="guide-code-copy"[^>]*onclick="([^"]*?)"/s);
  if (!m) {
    fail('4a: No .guide-code-copy element found');
  } else {
    const val = m[1].replace(/\s+/g, ' ').trim();
    if (val.includes("copyCode(this, 'git clone") || val.includes('copyCode(this, "git clone')) {
      pass(`4a: first .guide-code-copy onclick starts with copyCode(this, 'git clone ...)`);
    } else {
      fail(`4a: first .guide-code-copy onclick unexpected: ${val.slice(0, 120)}`);
    }
  }
}

// 4b — second .guide-code .cmd should be 'cd' with bare text node
{
  const guideCodeBlocks = [...html.matchAll(/<div class="guide-code">([\s\S]*?)<\/div>/g)].map(m => m[1]);
  let cmdCount = 0;
  let secondCmdFound = false;
  outer:
  for (const block of guideCodeBlocks) {
    for (const cmdM of block.matchAll(/<span class="cmd">([^<]*)<\/span>([^<]*)/g)) {
      cmdCount++;
      if (cmdCount === 2) {
        const cmdText  = cmdM[1].trim();
        const textNode = cmdM[2];
        if (cmdText === 'cd') {
          pass(`4b: second .guide-code .cmd is 'cd' with text node: "${textNode.slice(0,40)}"`);
        } else {
          fail(`4b: second .guide-code .cmd is '${cmdText}', expected 'cd'`);
        }
        secondCmdFound = true;
        break outer;
      }
    }
  }
  if (!secondCmdFound) fail('4b: fewer than 2 .guide-code .cmd spans found');
}

// 4c — first .guide-code .url should be the <repo-url> placeholder
{
  const m = html.match(/<span class="url">([^<]*)<\/span>/);
  if (!m) {
    fail('4c: No .guide-code .url span found');
  } else {
    const text = m[1].trim();
    if (text.includes('repo-url') || text.startsWith('<repo') ||
        text === '&lt;repo-url&gt;' || text.includes('&lt;repo')) {
      pass(`4c: first .guide-code .url is repo-url placeholder: "${text.slice(0,60)}"`);
    } else {
      warn(`4c: first .guide-code .url is "${text.slice(0,60)}" \u2014 verify it is the repo-url placeholder`);
    }
  }
}

// 4d — .milestone-actions-row must exist somewhere after .milestone-modal-card opens
{
  const cardIdx = html.indexOf('class="milestone-modal-card"');
  const rowIdx  = html.indexOf('milestone-actions-row', cardIdx);
  // The modal card is large; the row sits within it. We verify it comes after
  // the card opener and before 10 000 chars later (generous but bounded).
  if (cardIdx === -1) {
    warn('4d: .milestone-modal-card not found \u2014 verify manually');
  } else if (rowIdx !== -1 && (rowIdx - cardIdx) < 10000) {
    pass(`4d: .milestone-actions-row found inside .milestone-modal-card (offset +${rowIdx - cardIdx})`);
  } else if (rowIdx === -1) {
    fail('4d: .milestone-actions-row NOT found in dashboard.html');
  } else {
    warn(`4d: .milestone-actions-row found but far from .milestone-modal-card (offset +${rowIdx - cardIdx}) \u2014 verify nesting`);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ASSERTION 5: Inline handler functions exist in dashboard.js (or KNOWN_FAILURES)
// ─────────────────────────────────────────────────────────────────────────────
section('A5 \u2014 Inline handler functions exist (pre-existing failures baselined)');

// Build the set of all callable function names from dashboard.js.
// Covers: window.X =, function X() {, const/let/var X = function/arrow,
// and module-scope async function X() { (for verifyGithubInvite etc.)
const globalFns = new Set([
  ...exposedFunctions,
  ...[...js.matchAll(/^(?:async\s+)?function\s+(\w+)\s*\(/gm)].map(m => m[1]),
  ...[...js.matchAll(/^(?:const|let|var)\s+(\w+)\s*=\s*(?:function|\(|async)/gm)].map(m => m[1]),
]);

// Keywords and browser built-ins that appear as "function calls" in inline
// handlers but are not app-defined.
const BROWSER_GLOBALS = new Set([
  'document','window','console','alert','confirm','setTimeout','clearTimeout',
  'setInterval','clearInterval','fetch','JSON','Object','Array','Math','String',
  'Number','Boolean','Date','Promise','Error','parseInt','parseFloat','isNaN',
  'isFinite','encodeURIComponent','decodeURIComponent','location','history',
  'navigator','performance','requestAnimationFrame','cancelAnimationFrame',
  // JS keywords that syntactically look like calls
  'function',  // appears in setTimeout(function(){...},ms) inside onclick values
  'if','else','return','var','let','const','new','typeof','instanceof',
  'void','delete','throw','catch','finally',
  // Truthy/falsy literals
  'true','false','null','undefined',
  // Third-party
  'Razorpay',
]);

for (const fnName of [...inlineCalls].sort()) {
  if (BROWSER_GLOBALS.has(fnName)) continue;
  if (KNOWN_FAILURES.has(fnName)) {
    warn(`${fnName}  \u2014 KNOWN pre-existing failure (baselined). Fix in J2.`);
    continue;
  }
  if (globalFns.has(fnName)) {
    pass(`${fnName}()`);
  } else {
    fail(`${fnName}()  \u2014 called from inline handler but not defined/exported in dashboard.js`);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ASSERTION 6: !important budget
//   Regression check: count must not increase from baseline (captured first run).
//   End-state progress: separately report distance to ≤15 (post-commit-3 target).
//   Both dashboard.html AND dashboard.css are tracked.
// ─────────────────────────────────────────────────────────────────────────────
section('A6 \u2014 !important budget (regression + end-state progress)');
{
  // ── dashboard.html ──
  const htmlImportants = [...html.matchAll(/!important/g)].length;
  const htmlBaselinePath = path.join(ROOT, 'tools', '.dash-important-baseline');

  if (!fs.existsSync(htmlBaselinePath)) {
    fs.writeFileSync(htmlBaselinePath, String(htmlImportants), 'utf8');
    console.log(`  \uD83D\uDCCC  dashboard.html baseline captured: ${htmlImportants}`);
  } else {
    const baseline = parseInt(fs.readFileSync(htmlBaselinePath, 'utf8').trim(), 10);
    if (htmlImportants > baseline) {
      fail(`dashboard.html: ${htmlImportants} !important \u2014 UP from baseline ${baseline}. No new !important allowed.`);
    } else {
      pass(`dashboard.html: ${htmlImportants} !important (baseline ${baseline} \u2014 no regression)`);
    }
  }

  // ── dashboard.css ──
  const dashCssPath = path.join(ROOT, 'dashboard.css');
  if (fs.existsSync(dashCssPath)) {
    const css = fs.readFileSync(dashCssPath, 'utf8');
    // Strip block comments before counting so R6 fence comment text doesn't inflate count
    const cssNoComments = css.replace(/\/\*[\s\S]*?\*\//g, '');
    const cssImportants = [...cssNoComments.matchAll(/!important/g)].length;
    const cssCssBaselinePath = path.join(ROOT, 'tools', '.dash-css-important-baseline');
    const END_STATE_TARGET = 15;

    // Regression check (baseline file)
    if (!fs.existsSync(cssCssBaselinePath)) {
      fs.writeFileSync(cssCssBaselinePath, String(cssImportants), 'utf8');
      console.log(`  \uD83D\uDCCC  dashboard.css baseline captured: ${cssImportants}`);
    } else {
      const cssBaseline = parseInt(fs.readFileSync(cssCssBaselinePath, 'utf8').trim(), 10);
      if (cssImportants > cssBaseline) {
        fail(`dashboard.css: ${cssImportants} !important \u2014 UP from baseline ${cssBaseline}. No new !important allowed.`);
      } else if (cssImportants <= END_STATE_TARGET) {
        pass(`dashboard.css: ${cssImportants} !important \u2014 \u2705 end-state target \u2264${END_STATE_TARGET} REACHED`);
      } else {
        pass(`dashboard.css: ${cssImportants} !important (baseline ${cssBaseline} \u2014 no regression)`);
        console.log(`  \uD83D\uDCCA  End-state progress: ${cssImportants} \u2192 target \u2264${END_STATE_TARGET} (need \u2212${cssImportants - END_STATE_TARGET} more reductions)`);
      }
    }
  } else {
    pass('dashboard.css: not yet present \u2014 skipping');
  }
}


// ─────────────────────────────────────────────────────────────────────────────
// ASSERTION 7: style.css must not have been modified (hash check)
// ─────────────────────────────────────────────────────────────────────────────
section('A7 \u2014 style.css untouched');
{
  const hashPath   = path.join(ROOT, 'tools', '.dash-style-hash');
  const stylePath  = path.join(ROOT, 'style.css');
  const styleBytes = fs.readFileSync(stylePath);
  const currentHash = createHash('sha256').update(styleBytes).digest('hex');

  if (!fs.existsSync(hashPath)) {
    fs.writeFileSync(hashPath, currentHash, 'utf8');
    console.log(`  \uD83D\uDCCC  style.css baseline hash captured: ${currentHash.slice(0, 16)}\u2026`);
  } else {
    const baselineHash = fs.readFileSync(hashPath, 'utf8').trim();
    if (currentHash === baselineHash) {
      pass(`style.css hash matches baseline (${currentHash.slice(0, 16)}\u2026)`);
    } else {
      fail(`style.css has been MODIFIED! baseline: ${baselineHash.slice(0, 16)}\u2026  current: ${currentHash.slice(0, 16)}\u2026`);
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Final summary
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n' + '\u2550'.repeat(60));
if (failures === 0 && warnings === 0) {
  console.log('\u2705  ALL ASSERTIONS PASSED \u2014 contract is green.');
} else if (failures === 0) {
  console.log(`\u26a0\ufe0f   CONTRACT GREEN with ${warnings} warning(s) (baselined pre-existing issues).`);
} else {
  console.log(`\u274c  ${failures} FAILURE(S), ${warnings} WARNING(S) \u2014 fix before committing.`);
}
console.log('\u2550'.repeat(60) + '\n');
if (failures > 0) process.exit(1);
