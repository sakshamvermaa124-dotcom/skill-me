/**
 * SkillMe — acquisition attribution (first touch + last touch).
 *
 * Loaded on the public pages. On every visit it reads utm_source / utm_medium / utm_campaign /
 * utm_content, a referral code (?referral_code= or ?ref_code=), document.referrer and the landing
 * page, and keeps two touches in localStorage:
 *   first touch : written once, never overwritten (the channel that discovered SkillMe)
 *   last touch  : updated whenever a visit arrives from a campaign, referral code or external site
 *                 (a plain direct visit never overwrites it)
 * Both are sent with the application (POST /api/students/apply) and the last touch rides along on
 * the payment order, so attribution survives the whole journey.
 *
 * `?ref=` is NOT read here: offer.html / verify.html already use it for signed offer-letter references.
 * Stored data is limited to marketing parameters and page paths; no personal data is collected.
 */
(function () {
  'use strict';
  var KEY = 'skillme_attribution_v1';
  var TTL_MS = 90 * 24 * 3600 * 1000;       // forget touches after 90 days
  var MAX = 150;

  var store = (function () {
    try { var k = '__sm_t'; localStorage.setItem(k, '1'); localStorage.removeItem(k); return localStorage; }
    catch (e) { try { return sessionStorage; } catch (e2) { return null; } }
  })();

  function clip(v, n) { v = (v == null ? '' : String(v)).trim(); return v ? v.slice(0, n || MAX) : null; }
  function lower(v, n) { v = clip(v, n); return v ? v.toLowerCase() : null; }

  function read() {
    if (!store) return {};
    try { return JSON.parse(store.getItem(KEY) || '{}') || {}; } catch (e) { return {}; }
  }
  function write(state) { if (store) { try { store.setItem(KEY, JSON.stringify(state)); } catch (e) { /* quota/private mode */ } } }

  // Referrer host -> a stable source name. Anything unknown keeps its hostname.
  var HOSTS = [
    [/(^|\.)google\./, 'google'], [/(^|\.)bing\.com$/, 'bing'], [/duckduckgo\.com$/, 'duckduckgo'],
    [/(^|\.)linkedin\.com$|(^|\.)lnkd\.in$/, 'linkedin'], [/(^|\.)instagram\.com$/, 'instagram'],
    [/(^|\.)facebook\.com$|(^|\.)fb\.me$/, 'facebook'], [/(^|\.)t\.co$|(^|\.)twitter\.com$|(^|\.)x\.com$/, 'twitter'],
    [/whatsapp\.com$|wa\.me$/, 'whatsapp'], [/youtube\.com$|youtu\.be$/, 'youtube'],
    [/reddit\.com$/, 'reddit'], [/(^|\.)t\.me$|telegram\.org$/, 'telegram'], [/github\.com$/, 'github'],
  ];

  function classifyReferrer(ref) {
    if (!ref) return { source: 'direct', external: false };
    var host;
    try { host = new URL(ref).hostname.toLowerCase().replace(/^www\./, ''); } catch (e) { return { source: 'direct', external: false }; }
    if (host === location.hostname.toLowerCase().replace(/^www\./, '')) return { source: null, external: false };   // internal navigation
    for (var i = 0; i < HOSTS.length; i++) if (HOSTS[i][0].test(host)) return { source: HOSTS[i][1], external: true };
    return { source: host.slice(0, MAX), external: true };
  }

  function currentVisit() {
    var q = new URLSearchParams(location.search);
    var utmSource = lower(q.get('utm_source')), utmMedium = lower(q.get('utm_medium'));
    var utmCampaign = lower(q.get('utm_campaign')), utmContent = lower(q.get('utm_content'));
    var code = clip(q.get('referral_code') || q.get('ref_code'), 40);
    var ref = classifyReferrer(document.referrer);
    var hasCampaign = !!(utmSource || utmCampaign || code);
    return {
      utm_source: utmSource,
      source: utmSource || (code ? 'referral' : ref.source),
      medium: utmMedium || (utmSource ? null : (code ? 'referral' : (ref.external ? 'referral' : null))),
      campaign: utmCampaign, content: utmContent, referral_code: code ? code.toUpperCase() : null,
      landing_page: clip(location.pathname + location.search.replace(/([?&])(email|token|ref)=[^&]*/gi, '$1'), 300),
      referrer: ref.external ? clip(document.referrer, 300) : null,
      at: new Date().toISOString(),
      meaningful: hasCampaign || ref.external,
    };
  }

  function capture() {
    var v = currentVisit(), s = read(), now = Date.now();
    if (s.first && s.first.ts && now - s.first.ts > TTL_MS) s = {};
    var touch = {
      utm_source: v.utm_source, source: v.source || 'direct', medium: v.medium, campaign: v.campaign, content: v.content,
      referral_code: v.referral_code, landing_page: v.landing_page, referrer: v.referrer, at: v.at, ts: now,
    };
    if (!s.first) s.first = touch;                                  // first touch: written once
    if (v.meaningful || !s.last) s.last = touch;                    // last touch: a direct visit never overwrites
    if (v.referral_code && !s.referral_code) s.referral_code = v.referral_code;
    write(s);
    return s;
  }

  var state = capture();

  window.SkillMeAttribution = {
    /** Payload for the `attribution` field of POST /api/students/apply. */
    payload: function () {
      var s = read(), f = s.first || state.first || {}, l = s.last || state.last || {};
      return {
        utm_source: clip(f.utm_source || l.utm_source),
        utm_medium: clip(f.medium || l.medium), utm_campaign: clip(f.campaign || l.campaign), utm_content: clip(f.content || l.content),
        referral_code: s.referral_code || f.referral_code || l.referral_code || null,
        landing_page: clip(f.landing_page, 300), referrer: clip(f.referrer, 300),
        first_touch_source: clip(f.source || 'direct'), first_touch_at: f.at || null,
        last_touch_source: clip(l.source || 'direct'), last_touch_campaign: clip(l.campaign), last_touch_at: l.at || null,
      };
    },
    /** Last touch only, for the payment order. */
    lastTouch: function () {
      var l = (read().last || state.last || {});
      return { last_touch_source: clip(l.source || 'direct'), last_touch_campaign: clip(l.campaign) };
    },
  };
})();
