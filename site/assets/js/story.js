// Twelve days, replayed: a scroll-driven view of the engine's demo scenario (assets/js/data.js, generated from
// engine/vectors.json by tools/gen_site_data.py). Day k is chosen by scroll position, or by the controls.
// Everything printed here comes from the data: if the engine's scenario changes, regenerate data.js and rebuild.
import * as DATA from './data.js';
import * as E from './engine.js';
import { dialSvg } from './dial.js';
import { noDryingDays } from './whatif.js';

const S = DATA.SCENARIOS.find((s) => s.name === 'demo_pitch');
const N = S.days;
const calm = matchMedia('(prefers-reduced-motion: reduce)');
const $ = (id) => document.getElementById(id);
const el = { track: $('track'), day: $('st-day'), of: $('st-of'), date: $('st-date'), cap: $('st-cap'), dial: $('dial'), days: $('g-days'), unit: $('g-unit'),
  level: $('g-level'), moistLabel: $('g-moist-l'), moist: $('g-moist'), gate: $('g-gate'), note: $('g-note'), life: $('g-life'), bar: $('g-bar'), wx: $('wx'), ml: $('ml'), thread: $('thread'),
  prev: $('prev'), next: $('next'), scrub: $('scrub') };
const evening = Array.from({ length: N }, (_, k) => S.events.find((e) => e.kind === 'evening' && e.day === k));
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const fmt1 = (x) => (E.fmt ? E.fmt(x, 1) : x.toFixed(1));
const cap365 = (e) => e.capped || e.days_left >= ((E.P && E.P.HORIZON_DAYS) || 365);
const daysTxt = (e) => (cap365(e) ? '365+' : String(e.days_left));

el.of.textContent = `of ${N - 1}`;

// ---- what each day is about, found from the events (not hard-coded to day numbers) ------------------------
const firstDay = (pred) => { const e = S.events.find(pred); return e ? e.day : -1; };
const DAY = {
  salt: firstDay((e) => e.kind === 'reply' && /^SALT YES/.test(e.reply)),
  hook: firstDay((e) => e.kind === 'evening' && e.code === 'DRY_NOW'),
  drying: firstDay((e) => e.kind === 'reply' && /^DRYING/.test(e.reply)),
  rainWarn: firstDay((e) => e.kind === 'evening' && e.code === 'RAIN_COVER'),
  rain: S.weather.findIndex((w) => w.mm > 0),
  meter: firstDay((e) => e.kind === 'reply' && /^METER/.test(e.reply)),
};
const meterVal = (() => { const e = S.events.find((x) => x.kind === 'reply' && /^METER/.test(x.reply)); const m = e && e.reply.match(/[\d.]+/); return m ? m[0] : ''; })();
const QUIET = 'No message today. Harvestly sends at most one unprompted message a day, and only when something changes.';
const caption = (k) => {
  const e = evening[k], prev = evening[k - 1];
  if (k === DAY.salt) return 'The farmer’s salt test says the salt stuck: wetter than 15%. Harvestly counts from an assumed 18% and replies at once.';
  if (k === DAY.hook && prev) return `The forecast turns: ${Math.round(S.weather[k].fc[0].rh)}% humidity all week. The countdown falls from ${daysTxt(prev)} days to ${daysTxt(e)}, and Harvestly sends its first unprompted message.`;
  if (k === DAY.drying) return `The farmer starts drying and replies DRYING. Drying grain is held at its tested moisture until the next test, so the count recovers to ${daysTxt(e)} days.`;
  if (k === DAY.rainWarn) return 'Heavy rain is forecast for tomorrow and the grain is out drying. One message: cover it.';
  if (k === DAY.rain) return `The rain falls: ${Math.round(S.weather[k].mm)} mm. Nothing more is sent; the farmer already knows.`;
  if (k === DAY.meter) return `Salt test again: not yet proven dry. Then a meter at the co-op reads ${meterVal}%: dry enough to store. The farmer seals the bags. The count shows 365+, the longest the engine looks ahead. It is not a prediction.`;
  return QUIET;
};
// The small print under the caption: what the big number rests on.
const aside = (k) => {
  const e = evening[k];
  if (DAY.drying > -1 && k < DAY.drying && k !== DAY.hook) {
    const x = noDryingDays(S.weather, k);
    return `Illustration on simulated weather. The ${daysTxt(e)} assumes the sack dries toward the air’s moisture at 5% of the gap a day: our assumption, not tested in the field.${x != null ? ` With no drying at all, the same batch has about ${x} days.` : ''} The clock starts at the first test, not at harvest.`;
  }
  if (k === DAY.hook) {
    const x = noDryingDays(S.weather, k);
    return `Illustration on simulated weather. The drop is partly the model: the earlier ${prevDays(k)} assumed the sack dries at 5% of the gap a day, untested in the field.${x != null ? ` With no drying at all the count would already be about ${x} days.` : ''}`;
  }
  if (DAY.drying > -1 && k >= DAY.drying && k < DAY.meter) return 'The moisture estimate stays at the tested value while the grain dries. It only moves again at the next test.';
  return 'Illustration on simulated weather. The estimate steps down to the meter reading because the test replaces the estimate.';
};
const prevDays = (k) => daysTxt(evening[k - 1] || evening[k]);
const setCap = (k) => { el.cap.innerHTML = `${esc(caption(k))}<span class="st-aside">${esc(aside(k))}</span>`; };

// Reserve the height of the longest caption so nothing below it moves from day to day.
let reserved = 0;
function reserveCaption() {
  el.cap.style.minHeight = '0px';
  let max = 0;
  for (let k = 0; k < N; k++) { setCap(k); max = Math.max(max, el.cap.offsetHeight); }
  el.cap.style.minHeight = `${max}px`;
  reserved = max;
  if (shown >= 0) setCap(shown);
}

// ---- weather strip ---------------------------------------------------------------------------------------
const WX = { w: 520, colW: 520 / N, base: 62, scale: 54 / 60 };
const colX = (i) => WX.colW * i + WX.colW / 2;
const rhH = (rh) => Math.max(4, (rh - 40) * WX.scale);
let wxHtml = '';
for (let i = 0; i < N; i++) {
  wxHtml += `<rect id="wb${i}" x="${colX(i) - 11}" width="22" y="${WX.base}" height="0"/><circle id="wr${i}" cx="${colX(i)}" cy="9" r="0"/>`;
  if (i % 3 === 0 || i === N - 1) wxHtml += `<text class="c-axis" x="${i === 0 ? 2 : i === N - 1 ? 518 : colX(i)}" y="86" text-anchor="${i === 0 ? 'start' : i === N - 1 ? 'end' : 'middle'}">${i === 0 ? 'Day 0' : i}</text>`;
}
el.wx.innerHTML = wxHtml + '<rect id="wnow" class="wx-now" y="2" height="64" width="34" rx="3"/>' +
  `<line class="c-grid" x1="0" x2="520" y1="${WX.base}" y2="${WX.base}"/>`;
const drawWx = (k) => {
  for (let i = 0; i < N; i++) {
    const b = $('wb' + i), r = $('wr' + i);
    let rh = null, mm = 0, cls = '';
    if (i <= k) { rh = S.weather[i].rh; mm = S.weather[i].mm; cls = 'wx-a'; }
    else if (i <= k + 7 && S.weather[k].fc) { const f = S.weather[k].fc[i - k - 1]; rh = f.rh; mm = f.mm; cls = 'wx-f'; }
    if (rh === null) { b.setAttribute('height', 0); r.setAttribute('r', 0); continue; }
    const h = rhH(rh);
    b.setAttribute('class', cls); b.setAttribute('y', WX.base - h); b.setAttribute('height', h);
    r.setAttribute('class', mm > 0 ? (i <= k ? 'wx-r' : 'wx-f') : ''); r.setAttribute('r', mm > 0 ? 5.5 : 0);
  }
  $('wnow').setAttribute('x', colX(k) - 17);
};

// ---- moisture line ----------------------------------------------------------------------------------------
const ML = { l: 40, r: 508, t: 8, b: 70, y0: 12, y1: 19 };
const mlX = (i) => ML.l + (i / (N - 1)) * (ML.r - ML.l);
const mlY = (v) => ML.b - ((v - ML.y0) / (ML.y1 - ML.y0)) * (ML.b - ML.t);
el.ml.innerHTML = [12, 15, 18].map((v) => `<line class="c-grid" x1="${ML.l}" x2="${ML.r}" y1="${mlY(v)}" y2="${mlY(v)}"/><text class="c-axis" x="${ML.l - 6}" y="${mlY(v) + 4}" text-anchor="end">${v}</text>`).join('') +
  `<line class="ml-limit" x1="${ML.l}" x2="${ML.r}" y1="${mlY(13.5)}" y2="${mlY(13.5)}"/>` +
  [0, 4, 8, 12].filter((i) => i < N).map((i) => `<text class="c-axis" x="${mlX(i)}" y="98" text-anchor="${i === N - 1 || i === 12 ? 'end' : i === 0 ? 'start' : 'middle'}">${i === 0 ? 'Day 0' : i}</text>`).join('') +
  '<path id="mline" class="ml-line" d=""/><circle id="mdot" class="ml-dot" r="5" cx="-10" cy="-10"/>';
const drawMl = (k) => {
  const pts = evening.slice(0, k + 1).filter((e) => e && e.moisture != null).map((e) => [mlX(e.day), mlY(e.moisture)]);
  $('mline').setAttribute('d', pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(''));
  const last = pts[pts.length - 1];
  $('mdot').setAttribute('cx', last ? last[0] : -10); $('mdot').setAttribute('cy', last ? last[1] : -10);
};

// ---- messages: whole bubbles only, newest at the bottom ----------------------------------------------------
const bubble = (dir, en, sw, meta) => `<li class="msg msg-${dir}"><p><span data-l="en">${esc(en)}</span><span data-l="sw" lang="sw">${esc(sw)}</span></p><span class="msg-meta">${esc(meta)}</span></li>`;
const drawThread = (k) => {
  let html = '';
  for (const e of S.events) {
    if (e.day > k) break;
    if (e.kind === 'reply') {
      html += bubble('out', e.reply, e.reply_sw, `Day ${e.day} · farmer`);
      if (e.text) html += bubble('in', e.text, e.text_sw, `Day ${e.day} · Harvestly, replying to ${e.reply}`);
    } else if (e.code) html += bubble('in', e.text, e.text_sw, `Day ${e.day} · 17:00`);
  }
  el.thread.innerHTML = html ? `<li class="sms-more-li"><button type="button" class="sms-more" id="sms-more" hidden></button></li>${html}` : '<li class="sms-empty">Nothing sent yet.</li>';
  revealed = false;
  snapThread();
};
// Show the newest messages that fit completely, packed from the top. Earlier bubbles that would not fit are taken out of the
// flow (never a half bubble, never an empty gap), and a button above the newest one brings them back. Reading them by hand
// (wheel, touch, keys, the button) also shows them all.
let revealed = false;
const msgs = () => [...el.thread.children].filter((li) => li.classList.contains('msg'));
const narrow = matchMedia('(max-width: 979px)');
// The panel's height must not depend on what is in it (or hiding bubbles would shrink it and hide more). On a phone it is the
// space left in the pinned stage; on a wide screen the CSS height applies.
function sizePanel() {
  el.thread.style.height = ''; el.thread.style.flex = '';
  if (!narrow.matches || calm.matches) return;
  const stage = $('stage').getBoundingClientRect(), t = el.thread.getBoundingClientRect();
  const room = Math.max(100, Math.floor(stage.bottom - t.top));   // the open-bottomed phone runs to the stage edge
  el.thread.style.flex = 'none'; el.thread.style.height = `${room}px`;
}
function snapThread() {
  sizePanel();
  const items = msgs(), cue = el.thread.querySelector('.sms-more');
  items.forEach((li) => li.classList.remove('early'));
  let hidden = 0;
  if (!revealed && items.length) {
    const cs = getComputedStyle(el.thread), room = el.thread.clientHeight - (parseFloat(cs.paddingTop) || 0) - (parseFloat(cs.paddingBottom) || 0), last = items[items.length - 1];
    const fit = (r) => items.filter((li) => last.offsetTop + last.offsetHeight - li.offsetTop > r + 0.5);
    hidden = fit(room).length;
    if (hidden) {
      const cueH = 34;                          // the cue takes a row above the newest bubbles
      const cut = fit(room - cueH); hidden = Math.max(hidden, cut.length);
      hidden = Math.min(hidden, items.length - 1);
      items.slice(0, hidden).forEach((li) => li.classList.add('early'));
    }
  }
  el.thread.scrollTop = revealed ? el.thread.scrollHeight : 0;
  if (cue) {
    cue.hidden = !hidden;
    cue.textContent = hidden ? `Show ${hidden} earlier ${hidden === 1 ? 'message' : 'messages'}` : '';
  }
}
const reveal = () => { if (revealed) return; revealed = true; snapThread(); };
if (window.ResizeObserver) new ResizeObserver(() => requestAnimationFrame(snapThread)).observe($('stage'));
el.thread.addEventListener('click', (ev) => { if (ev.target.closest('.sms-more')) { reveal(); el.thread.focus(); } });
['wheel', 'touchstart', 'keydown', 'pointerdown'].forEach((t) => el.thread.addEventListener(t, reveal, { passive: true }));
new MutationObserver(() => requestAnimationFrame(snapThread)).observe(document.documentElement, { attributes: true, attributeFilter: ['data-sms'] });

// ---- the day ------------------------------------------------------------------------------------------------
let shown = -1;
function setDay(k) {
  k = Math.max(0, Math.min(N - 1, k));
  if (k === shown) return;
  shown = k;
  const e = evening[k];
  const left = e.days_left, frac = Math.min(1, left / 60), lvl = e.level.toLowerCase();
  el.day.textContent = `Day ${k}`;
  el.date.textContent = new Date(Date.parse(S.start + 'T12:00:00Z') + k * 864e5).toLocaleDateString('en-GB', { timeZone: 'UTC', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  setCap(k);
  el.dial.innerHTML = dialSvg({ ticks: 36, on: Math.round(frac * 36), hand: frac, level: lvl });
  el.days.textContent = daysTxt(e);
  el.days.classList.toggle('long', daysTxt(e).length > 3);
  el.unit.textContent = cap365(e) ? 'days, max' : 'days left';
  el.note.textContent = cap365(e) ? '365+ is the longest the tool looks ahead. It is not a prediction.' : '';
  el.note.hidden = !cap365(e);
  // The level is the engine's name for the countdown (LOW, MEDIUM, HIGH). It says nothing about moisture, so moisture gets its own status.
  el.level.textContent = e.level.charAt(0) + e.level.slice(1).toLowerCase();
  el.level.className = `pill pill-${lvl}`;
  const measured = k >= DAY.meter && DAY.meter > -1;
  el.moistLabel.textContent = measured ? 'Moisture (meter)' : 'Moisture estimate';
  el.moist.textContent = `${fmt1(e.moisture)}%`;
  const wet = e.moisture > (E.P && E.P.SALT_LINE_MC ? E.P.SALT_LINE_MC : 15), over = e.moisture > 13.5;
  el.gate.textContent = narrow.matches ? (wet ? 'Too wet' : over ? 'Not dry yet' : '13.5% or less') : (wet ? 'Too wet to store' : over ? 'Not yet dry enough' : 'At or under 13.5%');
  el.gate.className = `pill pill-sm pill-${wet ? 'high' : over ? 'medium' : 'low'}`;
  el.life.textContent = `${Math.round(e.life)}%`;
  el.bar.style.width = `${Math.min(100, e.life)}%`;
  el.scrub.value = k;
  el.scrub.setAttribute('aria-valuetext', `Day ${k} of ${N - 1}, ${el.date.textContent}`);
  drawWx(k); drawMl(k); drawThread(k);
}

// ---- scroll mapping (motion allowed) or plain stepper (reduced motion) ---------------------------------------------
const metrics = () => {
  const top = el.track.getBoundingClientRect().top + scrollY;
  return { top, span: Math.max(1, el.track.offsetHeight - innerHeight) };
};
const dayFromScroll = () => { const { top, span } = metrics(); return Math.min(N - 1, Math.max(0, Math.floor(((scrollY - top) / span) * N))); };
const posOfDay = (k) => { const { top, span } = metrics(); return top + ((k + 0.5) / N) * span; };
let ticking = false;
const onScroll = () => { if (calm.matches || ticking) return; ticking = true; requestAnimationFrame(() => { ticking = false; setDay(dayFromScroll()); }); };
function goTo(k) {
  k = Math.max(0, Math.min(N - 1, k));
  if (calm.matches) { setDay(k); return; }
  scrollTo({ top: posOfDay(k), behavior: 'instant' });
  setDay(k);
}
el.prev.addEventListener('click', () => goTo(shown - 1));
el.next.addEventListener('click', () => goTo(shown + 1));
el.scrub.addEventListener('input', () => goTo(Number(el.scrub.value)));
addEventListener('scroll', onScroll, { passive: true });
// A resize changes the scroll length: keep the same day on screen (only when the width changes, not for the
// address bar sliding away on phones).
let lastW = innerWidth, rt = 0;
addEventListener('resize', () => {
  clearTimeout(rt);
  rt = setTimeout(() => {
    reserveCaption(); snapThread();
    if (calm.matches) return;
    if (innerWidth !== lastW && shown >= 0) scrollTo({ top: posOfDay(shown), behavior: 'auto' });
    lastW = innerWidth;
    onScroll();
  }, 120);
});
narrow.addEventListener?.('change', () => { const k = shown; shown = -1; setDay(k); });
calm.addEventListener?.('change', () => setDay(calm.matches ? shown : dayFromScroll()));
setDay(calm.matches ? 0 : dayFromScroll());
reserveCaption();
document.fonts?.ready.then(() => { reserveCaption(); snapThread(); });
