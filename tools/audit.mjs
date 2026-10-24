// Full audit of a deployed or local Harvestly site.
//   node tools/audit.mjs <baseUrl> [outDir]          (default http://localhost:4173, /tmp/hv-audit)
// Sweep: every page x 360/390/768/1280/1920 x light/dark: status, h1, heading order, tap targets, overflow, meta, axe,
//        console, minimum text size, chart-label collisions and clipping, heading-to-next-element spacing.
// Then: story (every day, EN and SW, 360/390/1280: clipping, control stability), calculator edge cases, whatif vs engine,
//        print stylesheet, keyboard, reduced motion, OG images, assets, banned words. The link checker is tools/check-links.mjs.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const axeSrc = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const base = (process.argv[2] || 'http://localhost:4173').replace(/\/$/, '');
const out = process.argv[3] || '/tmp/hv-audit';
fs.mkdirSync(out, { recursive: true });
const exe = ['/usr/bin/brave-browser', '/opt/brave.com/brave-nightly/brave'].find(fs.existsSync);
const pages = ['/', '/how-it-works', '/pilot', '/partners', '/sources', '/privacy', '/thanks', '/nope-404'];
const widths = [[360, 740], [390, 844], [768, 1024], [1280, 800], [1920, 1080]];
const schemeArg = process.argv[5];
const pageSel = (process.argv[6] || '').split(',').filter(Boolean);
const widthSel = (process.argv[7] || '').split(',').filter(Boolean).map(Number);
const only = (process.argv[4] || 'sweep,story,calc,whatif,print,kb,cta,og').split(',');
const on = (k) => only.includes(k);
// The former company name is built at run time so this file never contains it.
const FORMER = String.fromCharCode(100, 97, 101, 108, 117, 115), FORMER_RE = new RegExp(FORMER, 'i');
const fails = [];
const note = (m) => { fails.push(m); console.log('FAIL', m); };
const browser = await chromium.launch({ executablePath: exe, args: ['--no-sandbox'] });
const open = async (w, h, scheme = 'light', extra = {}) => { const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, ...extra }); const page = await ctx.newPage(); page._errs = []; page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) page._errs.push(m.text()); }); page.on('pageerror', (e) => page._errs.push(String(e))); return { ctx, page }; };

// Runs inside the page: returns problems with chart text and heading spacing.
const inPage = () => {
  const q = (s) => [...document.querySelectorAll(s)];
  const vis = (e) => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const hs = q('h1,h2,h3,h4,h5,h6').filter(vis).map((e) => +e.tagName[1]);
  let skip = false; for (let i = 1; i < hs.length; i++) if (hs[i] - hs[i - 1] > 1) skip = true;
  const small = q('a,button,input,select,summary,[tabindex="0"]').filter((e) => {
    const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
    if (!r.width || cs.visibility === 'hidden' || e.closest('.vh,.skip')) return false;
    if (e.tagName === 'A' && cs.display === 'inline' && e.closest('p,li,figcaption,td,dd')) return false;
    if (e.closest('.refs')) return false;
    return r.width < 24 || r.height < 24;
  }).map((e) => e.outerHTML.slice(0, 70));
  // text smaller than 11 px (rendered), HTML or SVG
  const tiny = [];
  for (const e of q('main *, footer *')) {
    if (!e.childNodes.length || ![...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
    if (!vis(e) || e.closest('.vh,.defs,[aria-hidden=true] svg')) continue;
    let px = parseFloat(getComputedStyle(e).fontSize);
    if (e instanceof SVGElement) { const svg = e.ownerSVGElement; const k = svg.getBoundingClientRect().width / (svg.viewBox.baseVal.width || svg.getBoundingClientRect().width); px *= k; }
    if (px < 10.95) tiny.push(`${e.tagName.toLowerCase()}.${e.getAttribute('class') || ''} ${px.toFixed(1)}px "${e.textContent.trim().slice(0, 18)}"`);
  }
  // chart text: overlaps and clipping
  const coll = [];
  for (const svg of q('main svg')) {
    if (!vis(svg)) continue;
    const sr = svg.getBoundingClientRect();
    const ts = [...svg.querySelectorAll('text')].filter(vis).map((t) => ({ t: t.textContent.trim(), r: t.getBoundingClientRect() }));
    for (const a of ts) if (a.r.left < sr.left - 1 || a.r.right > sr.right + 1 || a.r.top < sr.top - 1 || a.r.bottom > sr.bottom + 1) coll.push(`clipped "${a.t}"`);
    for (let i = 0; i < ts.length; i++) for (let j = i + 1; j < ts.length; j++) {
      const a = ts[i].r, b = ts[j].r;
      if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) coll.push(`"${ts[i].t}" overlaps "${ts[j].t}"`);
    }
  }
  // heading to next element: no collision with a rule or the next block
  const gap = [];
  for (const h of q('main h2, main h3')) {
    if (!vis(h)) continue;
    const n = h.nextElementSibling; if (!n || !vis(n)) continue;
    const hr = h.getBoundingClientRect(), nr = n.getBoundingClientRect(), hb = hr.bottom, nt = nr.top;
    if (nr.left >= hr.right - 1 || hr.left >= nr.right - 1 || nr.top < hr.top) continue;   // side by side, not stacked
    const ruled = getComputedStyle(n).borderTopWidth !== '0px' || /^(TABLE|HR|OL|UL|DL|FIGURE|SVG)$/.test(n.tagName) || n.matches('.table-wrap,.chart-fig,.steps,.measures');
    if (nt - hb < (ruled ? 10 : 4)) gap.push(`${h.textContent.trim().slice(0, 28)} -> ${n.tagName.toLowerCase()}.${n.className} ${(nt - hb).toFixed(1)}px`);
    // descenders versus the heading's own bottom rule
    const bb = parseFloat(getComputedStyle(h).borderBottomWidth); if (bb > 0 && parseFloat(getComputedStyle(h).paddingBottom) < 6) gap.push(`${h.textContent.trim().slice(0, 28)} touches own rule`);
  }
  const hdr = document.querySelector('header')?.getBoundingClientRect().height || 0;
  const cta = document.querySelector('.hero .btn, main .btn, .btn');
  return {
    h1: q('h1').length, skip, small, tiny: [...new Set(tiny)], coll, gap, hdr, ctaTop: cta ? cta.getBoundingClientRect().bottom : null,
    ow: document.documentElement.scrollWidth - innerWidth,
    desc: document.querySelector('meta[name=description]')?.content.length || 0,
    og: document.querySelector('meta[property="og:image"]')?.content || '', title: document.title,
    text: document.body.innerText,
  };
};

const BANNED = /\b(revolutioni[sz]e[sd]?|leverag(e|es|ed|ing)|seamless(ly)?|unlock(s|ed|ing)?|empower(s|ed|ing)?|cutting[- ]edge|game[- ]chang\w*|world[- ]class|ai[- ]powered|delve|synerg\w+|disrupt\w*)\b/i;
let n = 0;
if (on('sweep')) for (const scheme of (schemeArg ? [schemeArg] : ['light', 'dark'])) for (const [w, h] of widths.filter(([w]) => !widthSel.length || widthSel.includes(w))) {
  const { ctx, page } = await open(w, h, scheme);
  for (const p of pages.filter((p) => !pageSel.length || pageSel.includes(p))) {
    const tag = `${p === '/' ? 'home' : p.slice(1)}@${w}-${scheme}`;
    page._errs.length = 0;
    const r = await page.goto(base + p, { waitUntil: 'networkidle' });
    if (p !== '/nope-404' && r.status() !== 200) note(`${tag} status ${r.status()}`);
    if (p === '/nope-404' && r.status() !== 404) note(`${tag} expected 404 got ${r.status()}`);
    await page.waitForTimeout(500);
    const m = await page.evaluate(inPage);
    if (m.h1 !== 1) note(`${tag} h1 count ${m.h1}`);
    if (m.skip) note(`${tag} skipped heading level`);
    if (m.small.length) note(`${tag} small tap targets ${JSON.stringify(m.small.slice(0, 3))}`);
    if (m.tiny.length) note(`${tag} text under 11px: ${m.tiny.slice(0, 3).join(' | ')}`);
    if (m.coll.length) note(`${tag} chart text: ${m.coll.slice(0, 3).join(' | ')}`);
    if (m.gap.length) note(`${tag} heading spacing: ${m.gap.slice(0, 3).join(' | ')}`);
    if (m.ow > 0) note(`${tag} horizontal overflow ${m.ow}px`);
    if (!m.desc || m.desc > 160) note(`${tag} meta description length ${m.desc}`);
    if (!m.og) note(`${tag} og:image missing`);
    if (m.title.length > 60) note(`${tag} title ${m.title.length} chars`);
    if (p === '/' && m.hdr / h > 0.15) note(`${tag} header ${(100 * m.hdr / h).toFixed(1)}% of viewport`);
    if (p === '/' && w !== 768 && (m.ctaTop == null || m.ctaTop > h)) note(`${tag} main CTA below fold (${m.ctaTop})`);
    if (p === '/nope-404' && w >= 1280 && (await page.evaluate(() => document.documentElement.scrollHeight)) > h + 60) note(`${tag} 404 taller than the screen`);
    if (page._errs.length && p !== '/nope-404') note(`${tag} console: ${page._errs.slice(0, 2).join(' | ')}`);
    if (scheme === 'light' && w === 1280) {
      const body = m.text.replace(/\n/g, ' ');
      const ban = body.match(BANNED); if (ban) { const i = body.indexOf(ban[0]); const ctxt = body.slice(Math.max(0, i - 60), i + 40); if (!/Innovative hermetic bags revolutionize grain storage/i.test(ctxt)) note(`${tag} banned word "${ban[0]}": ...${ctxt}...`); }
      if (FORMER_RE.test(body)) note(`${tag} mentions the former company name`);
      if (/\bwill message you\b/i.test(body)) note(`${tag} commitment wording "will message you"`);
    }
    await page.evaluate(axeSrc);
    const ax = await page.evaluate(() => axe.run(document, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa', 'best-practice'] }).then((r) => r.violations.map((v) => `${v.id}(${v.nodes.length}): ${v.nodes[0].target.join(' ')}`)));
    if (ax.length) note(`${tag} axe ${ax.slice(0, 3).join('; ')}`);
    await page.screenshot({ path: `${out}/${tag.replace('/', '_')}.png`, fullPage: true });
    n++;
  }
  await ctx.close();
}

// ---- story: every day, both languages, three widths --------------------------------------------------------------
if (on('story')) for (const [w, h] of [[360, 740], [390, 844], [1280, 800]]) for (const lang of ['en', 'sw']) {
  const { ctx, page } = await open(w, h, schemeArg || 'light');
  await page.goto(base + '/', { waitUntil: 'networkidle' });
  await page.evaluate(() => document.getElementById('story').scrollIntoView());
  if (lang === 'sw') await page.click('#story [data-sms=sw]');
  const total = +(await page.getAttribute('#scrub', 'max'));
  const ys = new Set(); const tag = `story@${w}-${lang}-${schemeArg || 'light'}`;
  const geo = await page.evaluate(() => { const t = document.getElementById('track'); return { top: t.getBoundingClientRect().top + scrollY, h: t.offsetHeight, vh: innerHeight }; });
  const dayNow = () => page.evaluate(() => +document.getElementById('st-day').textContent.replace(/\D/g, ''));
  for (let d = 0; d <= total; d++) {
    // scroll so the pinned stage shows day d (the mapping a reader uses); step with the buttons if the mapping lands elsewhere
    const y = geo.top + (d / total) * (geo.h - geo.vh) + (d === 0 ? 4 : d === total ? -4 : 0);
    await page.evaluate((y) => scrollTo(0, y), y); await page.waitForTimeout(260);
    let got = await dayNow();
    for (let k = 0; got !== d && k < 14; k++) { await page.click(got < d ? '#next' : '#prev'); await page.waitForTimeout(120); got = await dayNow(); }
    const r = await page.evaluate(() => {
      const R = (s) => document.querySelector(s)?.getBoundingClientRect();
      const th = R('#thread'), hd = R('header'), stage = R('#stage');
      const lis = [...document.querySelectorAll('#thread > li')].map((li) => li.getBoundingClientRect());
      const cut = lis.filter((b) => b.height && (b.top < th.top - 1 || b.bottom > th.bottom + 1)).length;
      const more = document.getElementById('sms-more').dataset.on === '1';
      return { dayTop: R('#st-day').top, hdrBottom: hd.bottom, ctlTop: R('#controls').top, thBottom: th.bottom, vh: innerHeight, cut, more, nb: lis.length, stageBottom: stage.bottom, stageTop: stage.top, day: document.getElementById('st-day').textContent };
    });
    ys.add(Math.round(r.ctlTop));
    if (r.dayTop < Math.min(r.hdrBottom, 0) - 1 || r.dayTop < 0) note(`${tag} day ${d}: heading clipped at top (${r.dayTop.toFixed(0)})`);
    if (r.thBottom > r.vh + 1) note(`${tag} day ${d}: messages below the viewport (${r.thBottom.toFixed(0)} > ${r.vh})`);
    if (r.cut && !r.more) note(`${tag} day ${d}: ${r.cut} bubble(s) cut without an "earlier messages" cue`);
    if (r.cut > 0 && r.more === false) { /* reported above */ }
    if (r.nb === 0 && d > 0) note(`${tag} day ${d}: empty thread`);
    if (d === 0 || d === total) await page.screenshot({ path: `${out}/${tag}-d${d}.png` });
  }
  if (ys.size > 1 && w >= 1000) note(`${tag}: controls move vertically between days (${[...ys].join(',')})`);
  await ctx.close();
}

// ---- calculator edge cases -------------------------------------------------------------------------------------------
if (on('calc')) {
  const { ctx, page } = await open(1280, 900, schemeArg || 'light');
  await page.goto(base + '/', { waitUntil: 'networkidle' });
  await page.waitForSelector('html[data-calc-ready="1"]', { state: 'attached', timeout: 20000 });   // T7-01: calc.js binds after a dynamic import
  const set = async (id, v) => { await page.fill('#' + id, v); await page.dispatchEvent('#' + id, 'blur'); await page.waitForTimeout(80); };
  const st = () => page.evaluate(() => ({ state: document.getElementById('out').dataset.state, pill: document.getElementById('c-level').offsetParent !== null, chart: document.getElementById('c-chart').getBoundingClientRect().height > 0, days: document.getElementById('c-days').textContent, title: document.getElementById('c-title').textContent, msg: document.getElementById('c-msg').textContent, notes: document.getElementById('c-notes').textContent, err: [...document.querySelectorAll('.err:not([hidden])')].map((e) => e.textContent), inv: [...document.querySelectorAll('[aria-invalid=true]')].map((e) => e.id), lead: document.getElementById('c-lead').textContent }));
  let s = await st();
  if (s.state !== 'ok' || /^2\d\d$/.test(s.days) || s.days === '288') note(`calc default: state ${s.state}, headline ${s.days} (must lead with safe days for wet grain)`);
  if (!/Too wet/i.test(s.title)) note(`calc default title "${s.title}"`);
  for (const [id, v, label] of [['mc', '13,5', 'comma decimal'], ['mc', '13.5', 'point decimal']]) {
    await set(id, v); s = await st(); if (s.state !== 'ok' || s.err.length) note(`calc ${label} "${v}" rejected: ${s.err.join('/')}`);
  }
  for (const [id, v] of [['mc', 'abc'], ['mc', ''], ['mc', '0'], ['mc', '4.9'], ['mc', '40.5'], ['mc', '-3'], ['mc', '1e1'], ['rh', '0'], ['rh', '100'], ['temp', '-10'], ['temp', '60'], ['temp', '']]) {
    await set('mc', '17'); await set('temp', '18.3'); await set('rh', '63');
    await set(id, v); s = await st();
    if (!['invalid', 'empty'].includes(s.state)) { note(`calc ${id}="${v}" not rejected (state ${s.state})`); continue; }
    if (s.pill || s.chart) note(`calc ${id}="${v}": stale pill/chart still visible`);
    if (!s.err.length && !s.msg) note(`calc ${id}="${v}": no message`);
    if (v !== '' && !s.inv.includes(id)) note(`calc ${id}="${v}": field not marked aria-invalid`);
  }
  await set('mc', '17'); await set('temp', '18.3'); await set('rh', '63'); s = await st(); if (s.state !== 'ok') note('calc does not recover after invalid input');
  // 13.5 in sacks in Kitale air: must say it drifts back above the limit
  await set('mc', '13.5'); s = await st(); if (!/(settle|drift|again|heading)/i.test(s.lead + s.notes + s.title)) note('calc 13.5% sack: no note about re-wetting'); 
  await page.selectOption('#storage', 'hermetic'); await set('mc', '13.8'); s = await st();
  if (/Not yet dry enough to seal or sell/i.test(s.notes + s.title)) note('calc hermetic 13.8%: says "not yet dry enough to seal" though the engine gives no advice below 14%');
  await page.selectOption('#storage', 'sack'); await page.click('input[value=sticks]'); await page.waitForTimeout(100); s = await st();
  if (!/Not proven|Above|Too wet/i.test(s.title + (await page.textContent('#c-level')))) note('calc salt sticks: verdict does not warn');
  await page.screenshot({ path: `${out}/calc-sticks.png` });
  await ctx.close();
}

if (on('whatif')) {
  const W = await import('../site/assets/js/whatif.js'); const E = await import('../site/assets/js/engine.js');
  let bad = 0;
  for (const m of [13, 14.5, 17, 18, 22]) for (const st of ['sack', 'hermetic', 'drying']) for (const [t, rh] of [[18, 63], [19, 92], [24, 40]]) {
    const fc = Array.from({ length: 7 }, () => ({ t, rh }));
    if (W.daysLeftAt(0.05, m, st, fc, 0) !== E.daysLeft(m, st, fc, 0)) bad++;
  }
  if (bad) note(`whatif.daysLeftAt(0.05) differs from engine daysLeft in ${bad} cases`); else console.log('whatif matches the engine in 45 cases');
}

if (on('print')) {
  const { ctx, page } = await open(1280, 900);
  for (const p of ['/', '/how-it-works', '/pilot', '/partners', '/sources', '/privacy', '/thanks']) {
    await page.goto(base + p, { waitUntil: 'networkidle' }); await page.emulateMedia({ media: 'print' });
    const r = await page.evaluate(() => ({ h: document.documentElement.scrollHeight, ow: document.documentElement.scrollWidth - innerWidth, nav: !!document.querySelector('.masthead') && getComputedStyle(document.querySelector('.masthead')).display !== 'none', bg: getComputedStyle(document.body).backgroundColor }));
    const pagesA4 = r.h / 1123; console.log(`print ${p}: ~${pagesA4.toFixed(1)} A4-equivalent pages`);
    if (r.nav) note(`print ${p}: masthead still shown`);
    if (pagesA4 > (p === '/' ? 14 : 12)) note(`print ${p}: ${pagesA4.toFixed(1)} pages`);
    if (r.ow > 0) note(`print ${p}: horizontal overflow`);
    await page.pdf({ path: `${out}/print-${p === '/' ? 'home' : p.slice(1)}.pdf`, format: 'A4' });
  }
  await ctx.close();
}

if (on('kb')) {
  const { ctx, page } = await open(1280, 800);
  await page.goto(base + '/', { waitUntil: 'networkidle' });
  const seen = new Set(); let bad = 0;
  for (let i = 0; i < 200; i++) {
    await page.keyboard.press('Tab');
    const d = await page.evaluate(() => { const e = document.activeElement; if (!e || e === document.body) return null; const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return { k: e.tagName + (e.id || e.className || e.textContent.slice(0, 20)), vis: r.width > 0 && r.height > 0, ring: cs.outlineStyle !== 'none' || cs.boxShadow !== 'none' }; });
    if (d) { seen.add(d.k); if (!d.vis || !d.ring) bad++; }
  }
  console.log('keyboard: distinct stops', seen.size, 'without ring/hidden', bad);
  if (bad) note(`keyboard: ${bad} stops without visible focus`);
  await ctx.close();
  const rc = await browser.newContext({ viewport: { width: 1280, height: 800 }, reducedMotion: 'reduce' });
  const rp = await rc.newPage(); await rp.goto(base + '/', { waitUntil: 'networkidle' });
  if (!(await rp.evaluate(() => !!document.querySelector('#story button')))) note('reduced motion: no stepper');
  if (!(await rp.evaluate(() => getComputedStyle(document.querySelector('.hero-ring .hand')).opacity === '1'))) note('reduced motion: hero hand not shown');
  await rc.close();
}


// ---- Tally calls to action, thanks/privacy, phone mockup, story reading checks ---------------------------------------------
if (on('cta')) {
  const { ctx, page } = await open(1280, 900);
  const forms = new Set();
  for (const p of ['/', '/how-it-works', '/pilot', '/partners', '/sources', '/privacy', '/thanks']) {
    await page.goto(base + p, { waitUntil: 'networkidle' });
    const links = await page.evaluate(() => [...document.querySelectorAll('a[href*="tally.so"]')].map((a) => ({ href: a.href, target: a.target, rel: a.rel, vh: !!a.querySelector('.vh') && /opens in a new tab/i.test(a.querySelector('.vh').textContent), icon: !!a.querySelector('svg.ext'), text: a.textContent.trim().slice(0, 40) })));
    for (const l of links) {
      forms.add(l.href);
      if (l.target !== '_blank' || !/noopener/.test(l.rel) || !/noreferrer/.test(l.rel)) note(`cta ${p}: ${l.href} target/rel wrong (${l.target} ${l.rel})`);
      if (!l.vh) note(`cta ${p}: ${l.href} lacks the hidden "opens in a new tab" text`);
      if (!l.icon) note(`cta ${p}: ${l.href} lacks the external icon`);
    }
    if (p === '/') { const cnt = links.length; if (cnt < 2) note(`cta /: only ${cnt} form links`); }
    console.log(`cta ${p}: ${links.length} form link(s)`);
    const fm = await page.evaluate(() => document.querySelectorAll('form:not(#calc)').length + document.querySelectorAll('iframe').length);
    if (fm) note(`cta ${p}: ${fm} unexpected form or iframe`);
  }
  if (forms.size !== 3) note(`cta: expected 3 distinct Tally forms, found ${forms.size}: ${[...forms].join(' ')}`);
  // keyboard: the first form link on home can be reached and shows a focus ring
  await page.goto(base + '/', { waitUntil: 'networkidle' }); await page.focus('a[href*="tally.so"]');
  if (!(await page.evaluate(() => { const cs = getComputedStyle(document.activeElement); return cs.outlineStyle !== 'none' || cs.boxShadow !== 'none'; }))) note('cta: no focus ring on the form link');
  // phone mockup
  const ph = await page.evaluate(() => [...document.querySelectorAll('.phone')].filter((p) => p.offsetParent).map((p) => { const r = p.getBoundingClientRect(), t = p.querySelector('.thread'); const crop = !!p.closest('.sms-wrap') && matchMedia('(max-width:979px)').matches; const fs = Math.min(...[...p.querySelectorAll('.msg p')].map((m) => parseFloat(getComputedStyle(m).fontSize))); return { w: Math.round(r.width), h: Math.round(r.height), crop, ratio: +(r.height / r.width).toFixed(2), over: p.querySelector('.phone-screen').scrollWidth > p.querySelector('.phone-screen').clientWidth + 1, tover: !p.closest('.sms-wrap') && t.scrollHeight > t.clientHeight + 2 && !p.closest('#hero-phone'), fs, thread: !!p.querySelector('.thread li') }; }));
  console.log('phone mockups', JSON.stringify(ph));
  if (!ph.length) note('phone mockup missing on home');
  for (const x of ph) { if (x.over) note('phone: content overflows its screen'); if (x.tover) note('phone: message text overflows the thread'); if (!x.thread && !x.crop) note('phone: empty thread'); if (!x.crop && Math.abs(x.ratio - 2.16) > 0.03) note(`phone ratio ${x.ratio} is not 2.16`); if (x.fs < 11.9) note(`phone text ${x.fs}px under 12`); }
  await ctx.close();
}

// ---- OG images, assets, headers ---------------------------------------------------------------------------------------
if (on('og')) for (const p of ['/', '/how-it-works', '/pilot', '/partners', '/sources']) {
  const html = await (await fetch(base + p)).text();
  const og = html.match(/property="og:image" content="([^"]+)"/)?.[1]; if (!og) { note(`og ${p}: none`); continue; }
  const url = base + new URL(og).pathname; const r = await fetch(url); const buf = Buffer.from(await r.arrayBuffer());
  const wpx = buf.readUInt32BE(16), hpx = buf.readUInt32BE(20);
  if (!r.ok || r.headers.get('content-type') !== 'image/png' || wpx !== 1200 || hpx !== 630) note(`og ${p}: ${r.status} ${r.headers.get('content-type')} ${wpx}x${hpx}`);
  if (!/property="og:image:alt"/.test(html)) note(`og ${p}: no alt`);
  fs.writeFileSync(`${out}/og-${p === '/' ? 'home' : p.slice(1)}.png`, buf);
}
for (const f of ['/sitemap.xml', '/robots.txt', '/favicon.svg', '/favicon-32.png', '/apple-touch-icon.png']) { const r = await fetch(base + f); if (!r.ok) note(`asset ${f} ${r.status}`); }
for (const f of [`/brand/${FORMER}-lockup.svg`, `/brand/${FORMER}-lockup-reversed.svg`]) { const r = await fetch(base + f); if (r.ok && !(r.headers.get('content-type') || '').includes('html')) note(`${f} still served`); }
const sm = await (await fetch(base + '/sitemap.xml')).text(); if (FORMER_RE.test(sm)) note('sitemap mentions the former company name');
const home = await fetch(base + '/'); const csp = home.headers.get('content-security-policy'); if (!csp || /unsafe-inline/.test(csp)) note('CSP missing or unsafe');
const js = (await home.text()).match(/\/assets\/v\/[^"]+\.(js|css)/g) || []; for (const a of new Set(js)) { const cc = (await fetch(base + a)).headers.get('cache-control') || ''; if (!/immutable/.test(cc) && base.startsWith('https')) note(`${a} cache-control "${cc}"`); }
await browser.close();
console.log(`\n${n} page-views checked, ${fails.length} failures`);
process.exit(fails.length ? 1 : 0);
