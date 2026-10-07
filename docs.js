/**
 * SkillMe — shared helpers for the credential documents
 * (certificate.html, lor.html, offer.html).
 *
 *  - SkillMeDocs.domainLabel(raw) / toSlug(raw): stored domains are a mix of slugs
 *    ('web-dev') and form labels ('Data Science'); normalise them for display.
 *  - SkillMeDocs.downloadPDF(el, opts): renders the document at a fixed desktop width
 *    and saves a real PDF file. Unlike window.print() this gives the same output on
 *    phones and desktops and also works inside in-app browsers (WhatsApp, LinkedIn,
 *    Instagram) where the print dialog doesn't exist. Falls back to window.print().
 */
(function () {
  const DOMAIN_LABELS = {
    'web-dev': 'Full Stack Engineer', 'python': 'Python', 'ml': 'Machine Learning',
    'react': 'Frontend Engineer', 'node': 'Backend Engineer', 'java': 'Java / Spring Boot',
    'datascience': 'Data Science', 'data-science': 'Data Science', 'flutter': 'App Developer',
    'devops': 'DevOps / CI-CD', 'cpp': 'C/C++ / DSA', 'cloud': 'Cloud / AWS', 'cyber': 'Cybersecurity',
    'uiux': 'UI/UX Design', 'genai': 'Generative AI', 'sql': 'SQL / Databases',
    'ai-engineer': 'AI Engineer', 'fde': 'Forward Deployed Engineer', 'sde': 'SDE / SWE',
    'ai-pm': 'AI Product Management', 'qa': 'Software Quality', 'android': 'Android / Kotlin',
  };
  // Legacy slugs / old form labels that don't match a current label exactly.
  const ALIASES = {
    'ui-ux': 'uiux', 'nodejs': 'node', 'cybersecurity': 'cyber', 'mobile': 'flutter', 'swe': 'sde',
    'web development': 'web-dev', 'react / next.js': 'react', 'node.js / express': 'node',
    'devops / cloud': 'devops', 'flutter / mobile': 'flutter', 'mobile development': 'flutter',
    'machine learning': 'ml', 'sdet': 'qa',
  };

  function toSlug(raw) {
    const v = String(raw || '').trim();
    if (!v) return '';
    const lower = v.toLowerCase();
    if (DOMAIN_LABELS[lower]) return lower;
    if (ALIASES[lower]) return ALIASES[lower];
    const byLabel = Object.keys(DOMAIN_LABELS).find(k => DOMAIN_LABELS[k].toLowerCase() === lower);
    return byLabel || lower;
  }

  function domainLabel(raw, fallback) {
    const v = String(raw || '').trim();
    if (!v) return fallback || '';
    const label = DOMAIN_LABELS[toSlug(v)];
    if (label) return label;
    // Unknown value: keep a typed label as-is, title-case a slug.
    return /[A-Z\s]/.test(v) ? v : v.replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  function esc(v) {
    return String(v == null ? '' : v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // SQLite timestamps look like "YYYY-MM-DD HH:MM:SS"; Safari can't parse the space form.
  function parseDate(raw) {
    const d = raw ? new Date(String(raw).replace(' ', 'T')) : new Date();
    return isNaN(d) ? new Date() : d;
  }

  // ── PDF export ────────────────────────────────────────────────────────────
  const LIBS = [
    'https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js',
    'https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js',
  ];
  let libsPromise = null;

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = src;
      s.onload = resolve;
      s.onerror = () => reject(new Error('Failed to load ' + src));
      document.head.appendChild(s);
    });
  }

  function loadLibs() {
    if (window.html2canvas && window.jspdf) return Promise.resolve();
    if (!libsPromise) {
      libsPromise = Promise.all(LIBS.map(loadScript)).catch(e => { libsPromise = null; throw e; });
    }
    return libsPromise;
  }

  function waitForImages(root) {
    return Promise.all([...root.querySelectorAll('img')].map(img =>
      img.complete ? null : new Promise(r => { img.onload = img.onerror = r; })));
  }

  function setBusy(btn, busy) {
    if (!btn) return;
    if (busy) {
      btn.dataset.label = btn.innerHTML;
      btn.disabled = true;
      btn.setAttribute('aria-busy', 'true');
      btn.innerHTML = 'Preparing PDF…';
    } else {
      btn.disabled = false;
      btn.removeAttribute('aria-busy');
      if (btn.dataset.label) btn.innerHTML = btn.dataset.label;
    }
  }

  function saveBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  /**
   * opts:
   *   filename     'SkillMe-LOR-Name.pdf'
   *   orientation  'portrait' | 'landscape'
   *   width        CSS px the document is laid out at in the PDF (default 860)
   *   singlePage   true → scale the whole document onto one page
   *   breakAvoid   selector for blocks a page break must not cut through (multi-page)
   *   keepWithNext selector for headings kept on the same page as the block after them
   *   margin       page margin in mm (multi-page, default 10)
   *   prepare      fn(snapshotDoc, snapshotEl) for page-specific tweaks before capture
   *   button       the clicked button (shows a busy state)
   */
  // Snapshot the page into an offscreen, desktop-width iframe (scripts stripped, so the
  // page logic doesn't re-run). Measuring and capturing inside that iframe means the
  // layout is identical on every device, and nothing visibly changes on the real page.
  function snapshotFrame(frameWidth) {
    return new Promise((resolve, reject) => {
      const html = document.documentElement.cloneNode(true);
      html.querySelectorAll('script').forEach(s => s.remove());
      const frame = document.createElement('iframe');
      frame.setAttribute('aria-hidden', 'true');
      frame.tabIndex = -1;
      frame.style.cssText = `position:absolute;left:-30000px;top:0;width:${frameWidth}px;height:1600px;border:0;`;
      frame.onload = () => resolve(frame);
      frame.onerror = reject;
      frame.srcdoc = '<!DOCTYPE html>' + html.outerHTML;
      document.body.appendChild(frame);
    });
  }

  async function downloadPDF(el, opts) {
    opts = opts || {};
    const btn = opts.button;
    setBusy(btn, true);
    let frame = null;
    try {
      await loadLibs();
      if (document.fonts && document.fonts.ready) await document.fonts.ready;

      const width = opts.width || 860;
      const frameWidth = Math.max(width + 80, 1200);
      frame = await snapshotFrame(frameWidth);
      const fdoc = frame.contentDocument;

      // <canvas> pixels (QR codes) aren't serialised — copy them across.
      const srcCanvases = document.querySelectorAll('canvas');
      fdoc.querySelectorAll('canvas').forEach((c, i) => {
        const src = srcCanvases[i];
        if (!src || !src.width) return;
        c.width = src.width; c.height = src.height;
        c.getContext('2d').drawImage(src, 0, 0);
      });

      const target = fdoc.getElementById(el.id);
      if (!target) throw new Error('Document element not found in snapshot');
      Object.assign(target.style, {
        width: width + 'px', maxWidth: 'none', margin: '0', boxShadow: 'none',
        borderRadius: '0', transform: 'none',
      });
      // html2canvas can't draw auto-hyphenation: it splits words with a gap and no hyphen.
      const fix = fdoc.createElement('style');
      fix.textContent = '*{-webkit-hyphens:manual!important;hyphens:manual!important}';
      fdoc.head.appendChild(fix);
      if (opts.prepare) opts.prepare(fdoc, target);

      if (fdoc.fonts && fdoc.fonts.ready) await fdoc.fonts.ready;
      await waitForImages(target);

      // [top, bottom] (CSS px) of each block a page break must not cut through.
      const top0 = target.getBoundingClientRect().top;
      const blocks = opts.singlePage ? [] :
        [...target.querySelectorAll(opts.breakAvoid || 'p, li, tr, h1, h2, h3, .section-head, .signature-row')]
          .map(n => { const r = n.getBoundingClientRect(); return [r.top - top0, r.bottom - top0]; });
      // Keep headings with the start of what follows (no heading stranded at a page bottom).
      if (!opts.singlePage) {
        target.querySelectorAll(opts.keepWithNext || '.section-head, h1, h2, h3').forEach(n => {
          const next = n.nextElementSibling;
          if (!next) return;
          const r = n.getBoundingClientRect(), nr = next.getBoundingClientRect();
          blocks.push([r.top - top0, Math.min(nr.bottom, nr.top + 90) - top0]);
        });
      }

      const canvas = await window.html2canvas(target, {
        scale: 2,
        useCORS: true,
        backgroundColor: '#ffffff',
        logging: false,
        windowWidth: frameWidth,
        windowHeight: 1600,
        scrollX: 0,
        scrollY: 0,
      });

      const { jsPDF } = window.jspdf;
      const orientation = opts.orientation || 'portrait';
      const pdf = new jsPDF({ orientation, unit: 'mm', format: 'a4', compress: true });
      const pageW = pdf.internal.pageSize.getWidth();
      const pageH = pdf.internal.pageSize.getHeight();

      if (opts.singlePage) {
        const ratio = Math.min(pageW / canvas.width, pageH / canvas.height);
        const w = canvas.width * ratio, h = canvas.height * ratio;
        pdf.addImage(canvas.toDataURL('image/jpeg', 0.95), 'JPEG', (pageW - w) / 2, (pageH - h) / 2, w, h);
      } else {
        const margin = opts.margin == null ? 10 : opts.margin;
        const contentW = pageW - margin * 2;
        const pxPerMm = canvas.width / contentW;            // canvas px per mm
        const pagePx = Math.floor((pageH - margin * 2) * pxPerMm);
        const cssToPx = canvas.width / width;               // html2canvas scale
        // A cut at y is bad if it falls strictly inside a block.
        const blocksPx = blocks.map(([t, b]) => [t * cssToPx, b * cssToPx]);
        const safeCut = (y) => {
          let cut = y;
          for (const [t, b] of blocksPx) {
            if (t < cut && cut < b && b - t < pagePx) cut = Math.min(cut, t);
          }
          return Math.max(Math.floor(cut), 1);
        };

        let y = 0, first = true;
        while (y < canvas.height - 2) {
          let end = Math.min(y + pagePx, canvas.height);
          if (end < canvas.height) {
            const cut = safeCut(end);
            if (cut > y + pagePx * 0.5) end = cut;            // never leave a mostly-empty page
          }
          const slice = document.createElement('canvas');
          slice.width = canvas.width;
          slice.height = end - y;
          const ctx = slice.getContext('2d');
          ctx.fillStyle = '#ffffff';
          ctx.fillRect(0, 0, slice.width, slice.height);
          ctx.drawImage(canvas, 0, y, canvas.width, end - y, 0, 0, canvas.width, end - y);
          if (!first) pdf.addPage();
          pdf.addImage(slice.toDataURL('image/jpeg', 0.95), 'JPEG', margin, margin, contentW, (end - y) / pxPerMm);
          first = false;
          y = end;
        }
      }

      saveBlob(pdf.output('blob'), opts.filename || 'SkillMe-Document.pdf');
      return true;
    } catch (err) {
      console.error('PDF export failed, falling back to print:', err);
      window.print();
      return false;
    } finally {
      if (frame) frame.remove();
      setBusy(btn, false);
    }
  }

  function safeFilePart(s) {
    return String(s || '').trim().replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-+|-+$/g, '') || 'Document';
  }

  window.SkillMeDocs = { DOMAIN_LABELS, toSlug, domainLabel, esc, parseDate, downloadPDF, safeFilePart };
})();
