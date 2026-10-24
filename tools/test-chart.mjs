// Calculator chart geometry test (S4-01/02/03): many moisture, temperature, humidity and storage inputs at phone and desktop
// widths, in light and dark. Fails if any chart text leaves the SVG, overlaps another text, sits on the curve, the 13.5% line,
// the air line or the now-line, or if y-axis ticks collide.   node tools/test-chart.mjs [baseUrl]
import { chromium } from 'playwright-core';
import fs from 'node:fs';
const base = (process.argv[2] || 'http://localhost:4173').replace(/\/$/, '');
const exe = ['/usr/bin/brave-browser', '/opt/brave.com/brave-nightly/brave'].find(fs.existsSync);
const browser = await chromium.launch({ executablePath: exe, args: ['--no-sandbox'] });
const MC = [15, 18, 20, 23, 25, 30], TEMP = [5, 10, 15, 20, 25, 30, 35], RH = [40, 63, 80, 90], STORE = ['sack', 'crib', 'floor', 'hermetic', 'drying'];
const EXT = { MC: [5, 13.5, 40], TEMP: [-5, 0, 45], RH: [1, 25, 99], STORE };   // the edges of what the calculator accepts
const VIEWS = [[320, 640, 'light'], [360, 740, 'light'], [360, 740, 'dark'], [390, 844, 'light'], [390, 844, 'dark'], [768, 1024, 'light'], [1280, 800, 'light'], [1920, 1080, 'dark']];
const check = ({ MC, TEMP, RH, STORE }) => {
  const $ = (id) => document.getElementById(id);
  const svg = $('c-chart'); const bad = []; let n = 0;
  const set = (id, v) => { $(id).value = String(v); };
  document.querySelector('input[name=how][value=meter]')?.click();
  for (const st of STORE) for (const mc of MC) for (const t of TEMP) for (const rh of RH) {
    $('storage').value = st; set('mc', mc); set('temp', t); set('rh', rh); $('mc').dispatchEvent(new Event('input', { bubbles: true }));
    if ($('out').dataset.state !== 'ok') { bad.push(`${st} ${mc}/${t}/${rh}: state ${$('out').dataset.state}`); continue; }
    n++;
    const tag = `${st} ${mc}%/${t}C/${rh}%`;
    const vb = svg.viewBox.baseVal;
    const texts = [...svg.querySelectorAll('text')].map((e) => { const b = e.getBBox(); return { t: e.textContent, x0: b.x, x1: b.x + b.width, y0: b.y, y1: b.y + b.height, cls: e.getAttribute('class') }; });
    const sh = 1.5; // shrink the glyph box a little: the line box is taller than the ink
    for (const a of texts) {
      if (a.x0 < -0.5 || a.x1 > vb.width + 0.5 || a.y0 < -0.5 || a.y1 > vb.height + 0.5) bad.push(`${tag}: "${a.t}" leaves the svg (${a.x0.toFixed(0)}..${a.x1.toFixed(0)})`);
    }
    for (let i = 0; i < texts.length; i++) for (let j = i + 1; j < texts.length; j++) {
      const a = texts[i], b = texts[j];
      if (a.x0 < b.x1 && b.x0 < a.x1 && a.y0 + sh < b.y1 - sh && b.y0 + sh < a.y1 - sh) bad.push(`${tag}: "${a.t}" overlaps "${b.t}"`);
    }
    const labels = texts.filter((a) => !/^(\d+%|Today|Day \d+)$/.test(a.t));
    const hl = [...svg.querySelectorAll('.c-limit,.ml-limit')].filter((l) => l.getAttribute('x2') - l.getAttribute('x1') > 200).map((l) => +l.getAttribute('y1'));
    const now = svg.querySelector('.wx-now'); const nx = now ? +now.getAttribute('x1') : null;
    const path = svg.querySelector('.c-line'); const L = path.getTotalLength();
    for (const a of labels) {
      for (const y of hl) if (y > a.y0 + sh && y < a.y1 - sh && a.x1 > 60 && a.x0 < 508) bad.push(`${tag}: "${a.t}" sits on a horizontal line`);
      if (nx !== null && nx > a.x0 + 0.5 && nx < a.x1 - 0.5 && now && +now.getAttribute('y1') < a.y1 && +now.getAttribute('y2') > a.y0) bad.push(`${tag}: "${a.t}" is crossed by the now-line`);
      for (let d = 0; d <= L; d += 1.5) { const p = path.getPointAtLength(d); if (p.x > a.x0 && p.x < a.x1 && p.y > a.y0 + sh && p.y < a.y1 - sh) { bad.push(`${tag}: "${a.t}" sits on the curve`); break; } }
    }
    const ticks = texts.filter((a) => /^\d+%$/.test(a.t));
    if (ticks.length < 2) bad.push(`${tag}: fewer than 2 y ticks`);
    const fs = parseFloat(getComputedStyle(svg.querySelector('.c-axis')).fontSize);
    if (fs * svg.getBoundingClientRect().width / vb.width < 10.9) bad.push(`${tag}: axis text under 11px`);
  }
  return { n, bad };
};
let total = 0, failed = 0;
for (const [w, h, scheme] of VIEWS) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme });
  const page = await ctx.newPage();
  await page.goto(base + '/', { waitUntil: 'load' });
  await page.waitForSelector('html[data-calc-ready="1"]', { state: 'attached', timeout: 20000 });   // T7-01: calc.js binds after a dynamic import
  await page.waitForFunction(() => document.getElementById('out')?.dataset.state === 'ok', null, { timeout: 20000 });
  await page.evaluate(() => document.fonts.ready);
  const r = await page.evaluate(check, { MC, TEMP, RH, STORE });
  const r2 = w <= 390 || w === 1280 ? await page.evaluate(check, EXT) : { n: 0, bad: [] };
  r.n += r2.n; r.bad.push(...r2.bad);
  total += r.n; failed += r.bad.length;
  console.log(`${w}x${h} ${scheme}: ${r.n} inputs, ${r.bad.length} problems`);
  for (const b of r.bad.slice(0, 12)) console.log('  FAIL', b);
  await ctx.close();
}
await browser.close();
console.log(failed ? `FAILED: ${failed} problems in ${total} inputs` : `chart ok: ${total} inputs, 0 problems`);
process.exit(failed ? 1 : 0);
