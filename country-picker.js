/*
 * Country + dialling-code picker for a phone field (apply page).
 *
 *   SkillMeCountryPicker.mount({ root, input, hidden, onChange })
 *
 * root   .cc-field wrapper holding the trigger button, the number <input> and the panel
 * input  the tel <input> the applicant types their local number into
 * hidden <input type="hidden"> that receives the ISO code (e.g. "IN")
 *
 * Returns { get country(), set(iso), fullNumber(), localDigits(), validate() }.
 * Data comes from country-data.js (generated from backend/services/countries.py).
 *
 * Desktop: opening the list focuses the search box, and typing on the closed trigger opens
 * it already filtered. Touch screens get a bottom sheet and no automatic keyboard.
 */
(function () {
  'use strict';

  var DATA = window.SKILLME_COUNTRIES || { list: [], primary: {}, prefixes: {} };
  var COUNTRIES = DATA.list.map(function (r) {
    return { iso: r[0], name: r[1], dial: r[2], aliases: r[3] || '' };
  });
  var BY_ISO = {};
  COUNTRIES.forEach(function (c) { BY_ISO[c.iso] = c; });

  // dial prefix -> iso; the longest prefix wins when reading a pasted number.
  var PREFIX = {};
  COUNTRIES.forEach(function (c) { if (!PREFIX[c.dial]) PREFIX[c.dial] = c.iso; });
  Object.keys(DATA.primary).forEach(function (d) { PREFIX[d] = DATA.primary[d]; });
  Object.keys(DATA.prefixes).forEach(function (iso) {
    DATA.prefixes[iso].forEach(function (p) { PREFIX[p] = iso; });
  });
  var MAX_PREFIX = Object.keys(PREFIX).reduce(function (m, p) { return Math.max(m, p.length); }, 0);

  function fold(s) {
    return String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }
  COUNTRIES.forEach(function (c) {
    c.key = fold(c.name);
    c.aliasKey = fold(c.aliases);
    c.aliasWords = c.aliasKey.split(/[^a-z0-9]+/).filter(Boolean);
    c.words = c.key.split(/[^a-z0-9]+/).filter(Boolean).concat(c.aliasWords);
    c.isPrimary = DATA.primary[c.dial] === c.iso;
  });

  // { iso, len } for the longest known prefix of `digits`, or null.
  function matchPrefix(digits) {
    for (var n = Math.min(MAX_PREFIX, digits.length); n > 0; n--) {
      var iso = PREFIX[digits.slice(0, n)];
      if (iso) return { iso: iso, len: n };
    }
    return null;
  }
  function isoFromDigits(digits) {
    var m = matchPrefix(digits);
    return m ? m.iso : null;
  }

  // Timezone -> country for the starting selection; India when unknown (most applicants).
  var TZ = {
    'Asia/Kolkata': 'IN', 'Asia/Calcutta': 'IN', 'Africa/Lagos': 'NG', 'Asia/Karachi': 'PK',
    'Asia/Kathmandu': 'NP', 'Asia/Katmandu': 'NP', 'Asia/Dhaka': 'BD', 'Africa/Cairo': 'EG',
    'Asia/Tashkent': 'UZ', 'Asia/Samarkand': 'UZ', 'Asia/Jakarta': 'ID', 'Africa/Kigali': 'RW',
    'Asia/Manila': 'PH', 'Africa/Casablanca': 'MA', 'Asia/Colombo': 'LK', 'Asia/Baku': 'AZ',
    'Africa/Nairobi': 'KE', 'Africa/Accra': 'GH', 'Asia/Riyadh': 'SA', 'Asia/Dubai': 'AE',
    'Asia/Kuala_Lumpur': 'MY', 'Asia/Kabul': 'AF', 'Asia/Yerevan': 'AM', 'Asia/Baghdad': 'IQ',
    'Africa/Dar_es_Salaam': 'TZ', 'Africa/Kampala': 'UG', 'Africa/Addis_Ababa': 'ET',
    'Africa/Johannesburg': 'ZA', 'Africa/Harare': 'ZW', 'Africa/Tunis': 'TN', 'Africa/Algiers': 'DZ',
    'Asia/Almaty': 'KZ', 'Asia/Singapore': 'SG', 'Asia/Bangkok': 'TH', 'Asia/Ho_Chi_Minh': 'VN',
    'Asia/Shanghai': 'CN', 'Asia/Tokyo': 'JP', 'Asia/Seoul': 'KR', 'Asia/Qatar': 'QA',
    'Asia/Kuwait': 'KW', 'Asia/Muscat': 'OM', 'Asia/Bahrain': 'BH', 'Asia/Amman': 'JO',
    'Asia/Tehran': 'IR', 'Europe/Istanbul': 'TR', 'Europe/London': 'GB', 'Europe/Berlin': 'DE',
    'Europe/Paris': 'FR', 'Europe/Madrid': 'ES', 'Europe/Rome': 'IT', 'Europe/Amsterdam': 'NL',
    'Europe/Moscow': 'RU', 'Europe/Kyiv': 'UA', 'Europe/Kiev': 'UA', 'Europe/Bucharest': 'RO',
    'Europe/Stockholm': 'SE', 'Europe/Warsaw': 'PL', 'Australia/Sydney': 'AU', 'Australia/Melbourne': 'AU',
    'America/Toronto': 'CA', 'America/Vancouver': 'CA', 'America/Sao_Paulo': 'BR', 'America/Lima': 'PE',
    'America/Mexico_City': 'MX', 'America/Bogota': 'CO', 'America/Argentina/Buenos_Aires': 'AR',
  };
  function guessCountry() {
    try {
      var tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (TZ[tz]) return TZ[tz];
      if (/^America\/(New_York|Chicago|Denver|Los_Angeles|Phoenix|Detroit|Anchorage)/.test(tz)) return 'US';
    } catch (e) { /* old browser */ }
    var langs = navigator.languages || [navigator.language || ''];
    for (var i = 0; i < langs.length; i++) {
      var m = /-([A-Z]{2})$/i.exec(langs[i] || '');
      if (m && BY_ISO[m[1].toUpperCase()] && m[1].toUpperCase() !== 'US') return m[1].toUpperCase();
    }
    return 'IN';
  }

  // Rank: name starts with query > a word starts with it > alias/contains > dial code / ISO.
  function search(query) {
    var q = fold(query).trim();
    if (!q) return COUNTRIES.slice();
    var digits = q.replace(/[^0-9]/g, '');
    var isDial = /^\+?[0-9\s]+$/.test(q);
    var scored = [];
    COUNTRIES.forEach(function (c) {
      var s = 0;
      if (isDial) {
        if (c.dial === digits) s = c.isPrimary ? 101 : 100;
        else if (c.dial.indexOf(digits) === 0) s = 60 - c.dial.length;
      } else {
        if (c.aliasWords.indexOf(q) !== -1 && q.length <= 3) s = 102; // 'uk', 'usa', 'uae'
        else if (c.key.indexOf(q) === 0) s = 100;
        else if (c.iso.toLowerCase() === q) s = 95;
        else if (c.words.some(function (w) { return w.indexOf(q) === 0; })) s = 80;
        else if (c.aliasKey.indexOf(q) !== -1) s = 60;
        else if (q.length > 2 && c.key.indexOf(q) !== -1) s = 40;
      }
      if (s) scored.push({ c: c, s: s });
    });
    scored.sort(function (a, b) { return b.s - a.s || (a.c.key < b.c.key ? -1 : 1); });
    return scored.map(function (x) { return x.c; });
  }

  function flagImg(iso, cls) {
    var img = document.createElement('img');
    var lower = iso.toLowerCase();
    img.className = cls;
    img.src = '/assets/flags/' + lower + '.png';
    img.srcset = '/assets/flags/' + lower + '.png 1x, /assets/flags/' + lower + '@2x.png 2x';
    img.alt = '';
    img.width = 20;
    img.height = 15;
    img.decoding = 'async';
    return img;
  }

  function mount(opts) {
    var root = opts.root;
    var input = opts.input;
    var hidden = opts.hidden;
    var trigger = root.querySelector('.cc-trigger');
    var panel = root.querySelector('.cc-panel');
    var searchInput = root.querySelector('.cc-search-input');
    var list = root.querySelector('.cc-list');
    var empty = root.querySelector('.cc-empty');
    var backdrop = root.querySelector('.cc-backdrop');
    var mq = function (q) { return !!(window.matchMedia && window.matchMedia(q).matches); };
    var uid = 'cc-' + Math.random().toString(36).slice(2, 8);

    var current = null;
    var results = [];
    var active = -1;

    // Build every option once; searching only reorders / hides them.
    var items = {};
    COUNTRIES.forEach(function (c) {
      var li = document.createElement('li');
      li.className = 'cc-option';
      li.id = uid + '-' + c.iso;
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', 'false');
      li.dataset.iso = c.iso;
      var flag = flagImg(c.iso, 'cc-flag');
      flag.loading = 'lazy';
      var name = document.createElement('span');
      name.className = 'cc-name';
      name.textContent = c.name;
      var dial = document.createElement('span');
      dial.className = 'cc-option-dial';
      dial.textContent = '+' + c.dial;
      var check = document.createElement('span');
      check.className = 'cc-check';
      check.setAttribute('aria-hidden', 'true');
      check.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';
      li.append(flag, name, dial, check);
      items[c.iso] = li;
    });

    function render(query) {
      results = search(query || '');
      var frag = document.createDocumentFragment();
      results.forEach(function (c) { frag.appendChild(items[c.iso]); });
      list.replaceChildren(frag);
      empty.hidden = results.length > 0;
      if (!results.length) empty.querySelector('b').textContent = query;
      setActive(results.length ? (query ? 0 : Math.max(0, results.indexOf(current))) : -1, !query);
    }

    function setActive(i, center) {
      if (active >= 0 && results[active]) items[results[active].iso].classList.remove('is-active');
      active = i;
      if (i < 0 || !results[i]) { searchInput.removeAttribute('aria-activedescendant'); return; }
      var li = items[results[i].iso];
      li.classList.add('is-active');
      searchInput.setAttribute('aria-activedescendant', li.id);
      // Keep the active row visible without moving the page.
      var top = li.offsetTop, bottom = top + li.offsetHeight;
      if (center) list.scrollTop = top - list.clientHeight / 2 + li.offsetHeight / 2;
      else if (top < list.scrollTop) list.scrollTop = top - 4;
      else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight + 4;
    }

    function select(iso, opts2) {
      var c = BY_ISO[iso];
      if (!c) return;
      if (current) items[current.iso].setAttribute('aria-selected', 'false');
      current = c;
      items[iso].setAttribute('aria-selected', 'true');
      hidden.value = iso;
      var flagSlot = trigger.querySelector('.cc-flag');
      flagSlot.replaceWith(flagImg(iso, 'cc-flag'));
      trigger.querySelector('.cc-dial').textContent = '+' + c.dial;
      trigger.setAttribute('aria-label', 'Country code: ' + c.name + ' +' + c.dial + '. Change country');
      input.placeholder = iso === 'IN' ? '98765 43210' : 'Phone number';
      if (!(opts2 && opts2.silent) && opts.onChange) opts.onChange(c);
    }

    function isOpen() { return !panel.hidden; }

    function open(seed) {
      if (isOpen()) return;
      panel.hidden = false;
      if (backdrop) backdrop.hidden = false;
      root.classList.add('is-open');
      trigger.setAttribute('aria-expanded', 'true');
      // Drop upward when there isn't room below (desktop popover only).
      root.classList.remove('cc-up');
      var coarse = mq('(pointer: coarse)');
      var sheet = coarse && mq('(max-width: 760px)'); // matches the bottom-sheet CSS
      if (!sheet) {
        var rect = root.getBoundingClientRect();
        if (window.innerHeight - rect.bottom < 360 && rect.top > window.innerHeight - rect.bottom) root.classList.add('cc-up');
      } else {
        document.documentElement.classList.add('cc-lock');
      }
      searchInput.value = seed || '';
      render(searchInput.value);
      if (!coarse || seed) searchInput.focus({ preventScroll: true });
    }

    function close(refocus) {
      if (!isOpen()) return;
      panel.hidden = true;
      if (backdrop) backdrop.hidden = true;
      root.classList.remove('is-open', 'cc-up');
      document.documentElement.classList.remove('cc-lock');
      trigger.setAttribute('aria-expanded', 'false');
      if (refocus) trigger.focus({ preventScroll: true });
    }

    function choose(iso) {
      select(iso);
      close(false);
      input.focus({ preventScroll: true });
    }

    trigger.addEventListener('click', function () { isOpen() ? close(true) : open(); });

    // Type-ahead on the closed trigger: the first letter opens the list already filtered.
    trigger.addEventListener('keydown', function (e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key.length === 1 && /\S/.test(e.key)) { e.preventDefault(); open(e.key); }
      else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); open(); }
    });

    searchInput.addEventListener('input', function () { render(searchInput.value); });
    searchInput.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); if (results.length) setActive(Math.min(results.length - 1, active + 1)); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); if (results.length) setActive(Math.max(0, active - 1)); }
      else if (e.key === 'PageDown') { e.preventDefault(); if (results.length) setActive(Math.min(results.length - 1, active + 8)); }
      else if (e.key === 'PageUp') { e.preventDefault(); if (results.length) setActive(Math.max(0, active - 8)); }
      else if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); if (results[active]) choose(results[active].iso); }
      else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(true); }
      else if (e.key === 'Tab') { close(false); }
    });

    list.addEventListener('mousedown', function (e) { e.preventDefault(); }); // keep focus in search
    list.addEventListener('click', function (e) {
      var li = e.target.closest('.cc-option');
      if (li) choose(li.dataset.iso);
    });
    list.addEventListener('mousemove', function (e) {
      var li = e.target.closest('.cc-option');
      if (!li) return;
      var i = results.indexOf(BY_ISO[li.dataset.iso]);
      if (i !== active) setActive(i);
    });
    if (backdrop) backdrop.addEventListener('click', function () { close(false); });
    root.querySelector('.cc-close') && root.querySelector('.cc-close').addEventListener('click', function () { close(true); });

    document.addEventListener('pointerdown', function (e) {
      if (isOpen() && !root.contains(e.target)) close(false);
    });

    // A pasted or typed international number (+44…, 0044…) switches the country and keeps
    // just the local part in the box.
    input.addEventListener('input', function () {
      var v = input.value;
      var m = /^\s*(?:\+|00)\s*([\d\s().-]{6,})$/.exec(v);
      if (!m) return;
      var digits = m[1].replace(/\D/g, '');
      var hit = matchPrefix(digits);
      if (!hit) return;
      var iso = hit.iso;
      // A bare shared code (+1, +7, +44…) keeps the picked country when it uses that code,
      // so a Canadian who picked Canada isn't flipped to the US.
      if (current && current.dial === BY_ISO[iso].dial && hit.len === current.dial.length) iso = current.iso;
      select(iso);
      input.value = digits.slice(BY_ISO[iso].dial.length);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });

    function localDigits() {
      var d = input.value.replace(/\D/g, '');
      // The trunk 0 (e.g. Nigeria 0813…, UK 07…) is dropped after a country code; Italy keeps it.
      if (d.length > 6 && d.charAt(0) === '0' && current && current.iso !== 'IT' && current.iso !== 'VA') d = d.replace(/^0+/, '');
      return d;
    }

    function validate() {
      var raw = input.value.trim();
      if (!current || !raw || !/^[\d\s().-]+$/.test(raw)) return false;
      var d = localDigits();
      if (current.iso === 'IN') {
        if (d.length === 12 && d.indexOf('91') === 0) d = d.slice(2);
        return /^[6-9]\d{9}$/.test(d);
      }
      return d.length >= 6 && d.length + current.dial.length <= 15;
    }

    function fullNumber() {
      var d = localDigits();
      if (current && current.iso === 'IN' && d.length === 12 && d.indexOf('91') === 0) d = d.slice(2);
      var parts = current.iso === 'IN' && d.length === 10 ? [d.slice(0, 5), d.slice(5)] : [d];
      return '+' + current.dial + ' ' + parts.join(' ');
    }

    // Starting value: a saved draft (ISO or a full +number), else a guess.
    var start = BY_ISO[(hidden.value || '').toUpperCase()] ? hidden.value.toUpperCase() : guessCountry();
    select(start, { silent: true });
    if (/^\s*(\+|00)/.test(input.value)) input.dispatchEvent(new Event('input'));

    return {
      get country() { return current ? current.iso : null; },
      set: function (iso) { select(iso); },
      fullNumber: fullNumber,
      localDigits: localDigits,
      validate: validate,
      close: close,
    };
  }

  window.SkillMeCountryPicker = { mount: mount, search: search, isoFromDigits: isoFromDigits };
})();
