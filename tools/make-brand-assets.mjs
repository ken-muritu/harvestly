// Favicon (from the logo symbol), PNG icons, favicon.ico and one 1200x630 OG image per page, rendered with Playwright.
//   node tools/make-brand-assets.mjs     (needs playwright-core and a Chromium-family browser: BRAVE=/path/to/brave)
import fs from 'node:fs';
import { chromium } from 'playwright-core';
import { dialSvg } from '../site/assets/js/dial.js';
import { SCENARIOS } from '../site/assets/js/data.js';

const SITE = new URL('../site/', import.meta.url).pathname;
const BROWSER = process.env.BRAVE || '/usr/bin/brave-browser';
const symbol = fs.readFileSync(SITE + 'brand/harvestly-symbol.svg', 'utf8');
const inner = symbol.replace(/^<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '');

// favicon.svg: the traced symbol, unchanged, on a paper tile (square viewBox).
const tile = (rx) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="-40 -12 316 316"><rect x="-40" y="-12" width="316" height="316" rx="${rx}" fill="#FDFBF8"/>${inner}</svg>`;
fs.writeFileSync(SITE + 'favicon.svg', tile(56));
fs.writeFileSync(SITE + 'icon-square.tmp.svg', tile(0));   // full-bleed square for the PNG and ICO icons (no transparent corners)

const day3 = SCENARIOS.find((x) => x.name === 'demo_pitch')?.events.find((e) => e.kind === 'evening' && e.code === 'DRY_NOW')?.days_left;
if (!day3) throw new Error('make-brand-assets: demo_pitch DRY_NOW days_left missing; regenerate site data first');
// id, big figure, label under it, heading, lit ticks (only the home card is a countdown)
const PAGES = [
  ['home', String(day3), 'days left (example)', 'The sack doesn’t tell you.', Math.round((day3 / 60) * 36), 'Example, simulated weather'],
  ['how-it-works', '17:00', 'every evening', 'How the countdown works.', 0, ''],
  ['pilot', '200', 'farmers, proposed', 'A proposal, not a pledge.', 0, ''],
  ['partners', '13.5%', 'the limit for sale', 'For co\u2011operatives, counties and warehouses.', 0, ''],
  ['privacy', '0', 'cookies or trackers', 'What we collect, and why.', 0, ''],
  ['sources', '39', 'references', 'Where every number comes from.', 0, ''],
];
const css = `@font-face{font-family:"DM Sans";font-weight:400;src:url(${SITE}assets/fonts/dm-sans-latin-400-normal.woff2)}
@font-face{font-family:"DM Sans";font-weight:500;src:url(${SITE}assets/fonts/dm-sans-latin-500-normal.woff2)}
@font-face{font-family:"DM Sans";font-weight:700;src:url(${SITE}assets/fonts/dm-sans-latin-700-normal.woff2)}
*{box-sizing:border-box;margin:0}body{width:1200px;height:630px;background:#09342B;color:#EFE8CF;font-family:"DM Sans";position:relative;overflow:hidden}
.logo{position:absolute;left:72px;top:60px;height:64px}
.tag{position:absolute;left:72px;top:146px;font-size:26px;color:#BCC8B7;font-weight:500;width:600px}
.h{position:absolute;left:72px;bottom:72px;width:560px;max-height:300px;font-size:76px;line-height:1.03;font-weight:700;letter-spacing:-.04em;text-wrap:balance;overflow-wrap:normal}
.ring{position:absolute;right:56px;top:80px;width:470px;height:470px}
.ring svg{width:100%;height:100%}.ring .t{stroke:#1F5144;fill:none}.ring .t.on{stroke:#D9A441}.ring .hand{stroke:#EFE8CF;stroke-linecap:round}
.c{position:absolute;left:50%;top:50%;width:290px;height:230px;transform:translate(-50%,-50%);display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
.c b{display:block;white-space:nowrap;font-size:150px;line-height:.9;letter-spacing:-.06em;color:#EFE8CF}
.c span{display:block;font-size:30px;line-height:1.15;font-weight:500;margin-top:12px;color:#EFE8CF;text-wrap:balance}
.note{position:absolute;right:56px;bottom:30px;width:470px;text-align:center;font-size:22px;color:#BCC8B7;font-weight:500}`;
const logo = 'file://' + SITE + 'brand/harvestly-horizontal-reversed.svg';

const b = await chromium.launch({ executablePath: BROWSER, args: ['--no-sandbox'] });
const ctx = await b.newContext({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
fs.mkdirSync(SITE + 'og', { recursive: true });
const p = await ctx.newPage();
const tmp = new URL('./og-tmp.html', import.meta.url).pathname;
for (const [id, big, small, head, on, note] of PAGES) {
  fs.writeFileSync(tmp, `<!doctype html><meta charset="utf-8"><style>${css}</style>
<img class="logo" src="${logo}" alt=""><p class="tag">A prototype countdown for stored maize</p>
<div class="h" id="h">${head}</div>
<div class="ring">${dialSvg({ ticks: 36, on, hand: on ? on / 36 : null, handIn: 60, handOut: 74, level: 'low', cls: 'dial' })}<div class="c"><b id="big">${big}</b><span>${small}</span></div></div>${note ? `<p class="note">${note}</p>` : ''}`);
  await p.goto('file://' + tmp); await p.evaluate(() => document.fonts.ready);
  // auto-fit: shrink until the heading fits its box and the figure fits the inner ring
  await p.evaluate(() => {
    const fit = (el, w, h) => { let f = parseFloat(getComputedStyle(el).fontSize); while ((el.scrollWidth > w || el.scrollHeight > h) && f > 20) { f -= 2; el.style.fontSize = f + 'px'; } };
    fit(document.getElementById('h'), 560, 300); fit(document.getElementById('big'), 290, 150);
  });
  await p.waitForTimeout(150);
  await p.screenshot({ path: `${SITE}og/${id}.png` });
}
// icons
const icon = async (size, out) => {
  fs.writeFileSync(tmp, `<!doctype html><body style="margin:0;background:transparent"><img src="file://${SITE}icon-square.tmp.svg" width="${size}" height="${size}">`);
  for (let attempt = 1; ; attempt++) {   // the headless browser occasionally stalls on a screenshot of a tiny page: retry with a fresh page
    const q = await b.newPage(); await q.setViewportSize({ width: size, height: size });
    try { await q.goto('file://' + tmp); await q.waitForTimeout(100); await q.screenshot({ path: out, omitBackground: true, timeout: 6000 }); await q.close(); return; }
    catch (e) { await q.close().catch(() => {}); if (attempt >= 5) throw e; }
  }
};
await icon(32, SITE + 'favicon-32.png'); await icon(48, SITE + 'favicon-48.png'); await icon(180, SITE + 'apple-touch-icon.png');
await b.close(); fs.unlinkSync(tmp); fs.unlinkSync(SITE + 'icon-square.tmp.svg');
// favicon.ico: one 48x48 PNG image inside an ICO container
const png = fs.readFileSync(SITE + 'favicon-48.png'); fs.unlinkSync(SITE + 'favicon-48.png');
const hdr = Buffer.alloc(22); hdr.writeUInt16LE(0, 0); hdr.writeUInt16LE(1, 2); hdr.writeUInt16LE(1, 4);
hdr[6] = 48; hdr[7] = 48; hdr.writeUInt16LE(1, 10); hdr.writeUInt16LE(32, 12); hdr.writeUInt32LE(png.length, 14); hdr.writeUInt32LE(22, 18);
fs.writeFileSync(SITE + 'favicon.ico', Buffer.concat([hdr, png]));
console.log('assets written');
