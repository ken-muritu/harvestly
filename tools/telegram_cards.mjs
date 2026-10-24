// Renders the Telegram countdown-dial cards (brand/telegram-cards/dial-0..90.png English, dial-sw-0..90.png Kiswahili) offline with Brave headless over CDP.
// Run: node tools/telegram_cards.mjs   (Brave must be started by this script's wrapper: see docs/TELEGRAM.md)
// Dial shape = site/assets/v/dial.js (36 ticks, 270 degree arc, amber lit ticks, short green hand). Example art only.
import fs from 'fs';
import { spawn } from 'child_process';
import os from 'os';
import path from 'path';

const out = process.argv[2] || new URL('../brand/telegram-cards', import.meta.url).pathname;
fs.mkdirSync(out, { recursive: true });
const port = 9344;
const prof = fs.mkdtempSync(path.join(os.tmpdir(), 'hv-cards-'));
const brave = spawn('brave-browser', ['--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--no-first-run',
  `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`, 'about:blank'], { stdio: 'ignore', env: { ...process.env, DBUS_SESSION_BUS_ADDRESS: 'disabled:' } });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let target;
for (let i = 0; i < 40 && !target; i++) { await sleep(500); try { target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json(); } catch {} }
const ws = new WebSocket(target.webSocketDebuggerUrl);
let id = 0; const pend = {};
ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && pend[m.id]) pend[m.id](m); };
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pend[i] = r; ws.send(JSON.stringify({ id: i, method, params })); });
await new Promise((r) => (ws.onopen = r));
await send('Emulation.setDeviceMetricsOverride', { width: 560, height: 360, deviceScaleFactor: 1, mobile: false });

const G = '#09342B', A = '#CC9033', C = '#F6F0DC';
function dial(n) {
  const ticks = 36, on = Math.round(ticks * n / 90), start = -135, step = 270 / (ticks - 1);
  const pt = (r, a) => [100 + r * Math.sin(a * Math.PI / 180), 100 - r * Math.cos(a * Math.PI / 180)].map((v) => Math.round(v * 10) / 10);
  let s = '';
  for (let i = 0; i < ticks; i++) {
    const a = start + i * step, [x1, y1] = pt(74, a), [x2, y2] = pt(94, a);
    s += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${i < on ? A : G}" stroke-opacity="${i < on ? 1 : 0.16}" stroke-width="6" stroke-linecap="round"/>`;
  }
  const a = start + (n / 90) * 270, [x1, y1] = pt(57, a), [x2, y2] = pt(68, a);
  s += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${G}" stroke-width="7.5" stroke-linecap="round"/>`;
  return s;
}
const TXT = { en: ['days left (estimate)', 'Harvestly example, simulated weather'], sw: ['siku zilizobaki (makadirio)', 'Harvestly mfano, hali ya hewa ya kuigwa'] };
const html = (n, lang) => `<body style="margin:0;background:${C};width:560px;height:360px;position:relative;font-family:'DM Sans',sans-serif;color:${G}">
<svg viewBox="0 0 200 200" width="290" height="290" style="position:absolute;left:135px;top:6px">${dial(n)}</svg>
<div id="num" style="position:absolute;left:0;width:560px;top:115px;text-align:center;font-weight:700;font-size:${n >= 90 ? 62 : 72}px;line-height:1">${n >= 90 ? '90+' : n}</div>
<div id="lab" style="position:absolute;left:0;width:560px;top:264px;text-align:center;font-size:22px;font-weight:500">${TXT[lang][0]}</div>
<div id="foot" style="position:absolute;left:0;width:560px;top:320px;text-align:center;font-size:19px;opacity:.7">${TXT[lang][1]}</div></body>`;
// Overlap check: every dial line (stroke included) must stay clear of the number, label and footer text boxes, and the three texts clear of each other and inside the card.
const CHECK = `(() => {
  const box = (id) => { const e = document.getElementById(id), r = document.createRange(); r.selectNodeContents(e); const b = r.getBoundingClientRect(); return { l: b.left, t: b.top, r: b.right, b: b.bottom }; };
  const T = { num: box('num'), lab: box('lab'), foot: box('foot') }, bad = [];
  const dist = (p, q, b) => { let best = 1e9; for (let i = 0; i <= 40; i++) { const x = p[0] + (q[0] - p[0]) * i / 40, y = p[1] + (q[1] - p[1]) * i / 40; const dx = Math.max(b.l - x, 0, x - b.r), dy = Math.max(b.t - y, 0, y - b.b); best = Math.min(best, Math.hypot(dx, dy)); } return best; };
  for (const ln of document.querySelectorAll('svg line')) {
    const m = ln.getScreenCTM(), pt = (x, y) => [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f];
    const p = pt(+ln.getAttribute('x1'), +ln.getAttribute('y1')), q = pt(+ln.getAttribute('x2'), +ln.getAttribute('y2'));
    const half = (+ln.getAttribute('stroke-width')) * m.a / 2;
    for (const k in T) if (dist(p, q, T[k]) < half + 4) bad.push('line near ' + k);
  }
  const ks = Object.keys(T);
  for (let i = 0; i < 3; i++) { const a = T[ks[i]]; if (a.l < 8 || a.r > 552 || a.t < 4 || a.b > 356) bad.push(ks[i] + ' outside card'); for (let j = i + 1; j < 3; j++) { const b = T[ks[j]]; if (a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b) bad.push(ks[i] + ' overlaps ' + ks[j]); } }
  return JSON.stringify(bad);
})()`;
let problems = 0;
for (const lang of ['en', 'sw']) for (let n = 0; n <= 90; n++) {
  await send('Runtime.evaluate', { expression: `document.open();document.write(${JSON.stringify(html(n, lang))});document.close();document.fonts.ready.then(()=>1)`, awaitPromise: true });
  await sleep(120);
  const bad = JSON.parse((await send('Runtime.evaluate', { expression: CHECK, returnByValue: true })).result.result.value);
  const r = await send('Page.captureScreenshot', { format: 'png' });
  const f = path.join(out, (lang === 'sw' ? `dial-sw-${n}.png` : `dial-${n}.png`)), buf = Buffer.from(r.result.data, 'base64');
  fs.writeFileSync(f, buf);
  if (bad.length) { problems++; console.error(`OVERLAP ${lang} ${n}: ${bad.join('; ')}`); }
  if (buf.length >= 100000) { problems++; console.error(`TOO BIG ${lang} ${n}: ${buf.length}`); }
}
console.log(problems ? `${problems} problems` : 'all 182 cards: no overlaps, each under 100 KB');
brave.kill(); process.exit(problems ? 1 : 0);
