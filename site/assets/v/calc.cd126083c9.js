// "How long will your sacks last?" The engine's own physics, ported to JS (engine.js), run in the browser.
// Results lead with the verdict. Invalid or empty input clears the result (no stale pill, chart or flags).
import * as E from './engine.61e9735e7e.js';
import { dialSvg } from './dial.c090896001.js';
import { scales, linePath } from './chart.c6eda661bc.js';
import { daysLeftAt } from './whatif.1d5f71e6a9.js';

const { emc, astDays, drift, daysLeft, riskLevel, P } = E;
const f1 = (x) => E.fmt(x, 1);
const $ = (id) => document.getElementById(id);
const form = $('calc');
const how = () => form.elements.how.value;

const FLAG = {
  'AST moisture extrapolated': 'Below 15% moisture the storage-days figure is extended past the published table. Treat it as a rough guide.',
  'AST temperature extrapolated': 'Above 24 °C the storage-days table is extended past its last row.',
  'AST temperature clamped': 'Below 2 °C the storage-days figure is held at the table’s coldest row.',
  'AST moisture clamped': 'Above 30% moisture the figure is held at the table’s last column.',
  'EMC humidity clamped': 'Humidity outside 25–90% is treated as the nearest edge of the moisture table.',
  'EMC temperature clamped': 'Temperature outside 2–38 °C is treated as the nearest edge of the moisture table.',
};
const BASE_FLAGS = [
  'Assumes the air stays as you entered it. Damp weather shortens the countdown, and a long countdown does not clear wet grain for sale.',
  'An estimate, not a test. Only a meter or hygrometer reading can clear grain as dry.',
  'The salt test never clears grain.',
  'The storage clock here starts at the first reading, not at harvest.',
  'The tables are for US corn and have not been validated for Kenyan white maize.',
  '13.5% is the East African standard limit for sale. Arkansas guidance for keeping corn a full year is 12%.',
];

// ---- reading the fields ---------------------------------------------------------------------------------
const FIELDS = {
  mc: { name: 'Moisture', lo: 5, hi: 40, unit: '%', eg: '13.5' },
  temp: { name: 'Temperature', lo: -5, hi: 45, unit: ' °C', eg: '18' },
  rh: { name: 'Humidity', lo: 1, hi: 99, unit: '%', eg: '63' },
};
/** '13,5' and '13.5' both work. Returns {v} or {err}. Empty gives {empty:true}. */
function read(id) {
  const raw = $(id).value.trim().replace(',', '.');
  const F = FIELDS[id];
  if (raw === '') return { empty: true, err: `${F.name}: enter a number, for example ${F.eg}.` };
  if (!/^-?\d+(\.\d+)?$/.test(raw)) return { err: `${F.name}: use digits only, for example ${F.eg} (a comma or a point both work).` };
  const v = parseFloat(raw);
  if (v < F.lo || v > F.hi) return { err: `${F.name}: ${f1(v).replace(/\.0$/, '')}${F.unit.trim() ? F.unit : ''} is outside what this tool handles. Enter ${F.lo} to ${F.hi}${F.unit}.` };
  return { v };
}
const touched = new Set();
function showFieldErrors(res) {
  for (const id of Object.keys(FIELDS)) {
    const r = res[id], e = $('e-' + id);
    if (!r) { e.hidden = true; $(id).removeAttribute('aria-invalid'); continue; }
    const bad = r.err && touched.has(id) && !r.empty ? r.err : (r.empty && touched.has(id) ? r.err : '');
    e.textContent = bad; e.hidden = !bad;
    if (bad) $(id).setAttribute('aria-invalid', 'true'); else $(id).removeAttribute('aria-invalid');
  }
}

// ---- verdict ---------------------------------------------------------------------------------------------
const SEV = { low: 0, medium: 1, high: 2 };
function verdict({ mode, m, storage, E: eq, left, shown }) {
  const gate = P.EAS_MAX_MC, permeable = ['sack', 'crib', 'floor'].includes(storage);
  const here = `${f1(m).replace(/\.0$/, '')}%`;
  let v;
  if (mode !== 'meter') {
    v = { sev: mode === 'sticks' ? 'high' : 'medium', pill: 'Not proven dry', title: mode === 'sticks' ? 'Too wet to store' : 'Not proven dry',
      note: 'The salt test never clears grain. Confirm with a meter reading before you seal or sell.' };
    if (mode === 'sticks') v.pill = 'Above the 13.5% limit';
  } else if (storage === 'hermetic') {
    if (m >= P.HERMETIC_MAX_MC) v = { sev: 'high', pill: 'Too wet to seal', title: 'Open the bags and dry it', note: 'Sealed at 14% or more, grain can still go mouldy. Open the bags, dry the grain, and seal again only after a meter reads 13.5% or less.' };
    else if (m > gate) v = { sev: 'medium', pill: 'Above the 13.5% limit', title: 'Under the sealed-bag limit, over the sale limit', note: `At ${here} sealed bags hold it, but a warehouse or buyer applying the 13.5% limit would not take it. Dry it a little more first.` };
    else v = { sev: 'low', pill: 'At or under 13.5%', title: 'Dry enough to store', note: `A meter reading at or below 13.5% counts as dry. Sealed bags hold the grain at ${here}, whatever the air does.` };
  } else if (m > P.SALT_LINE_MC) {
    v = { sev: 'high', pill: 'Above the 13.5% limit', title: 'Too wet to store', note: `Dry it in full sun, then read it again. The limit is 13.5%; ${here} is above it.` };
  } else if (m > gate) {
    v = { sev: 'medium', pill: 'Above the 13.5% limit', title: 'Not yet dry enough', note: `Not yet dry enough to seal or sell. The limit is 13.5%; ${here} is above it. Dry it more, then read it again.` };
  } else if (permeable && eq > gate) {
    v = { sev: 'medium', pill: 'Dry today, not for long', title: 'Dry now, but this air will wet it again', note: `In this air sacks drift back above 13.5% (they settle near ${f1(eq)}%). Seal in hermetic bags or deliver soon.` };
  } else {
    v = { sev: 'low', pill: 'At or under 13.5%', title: 'Dry enough to store', note: 'A meter reading at or below 13.5% counts as dry: it meets the warehouse and standard limit.' };
  }
  // Time can make it worse than the moisture does.
  const risk = riskLevel(0, shown).toLowerCase();
  if (SEV[risk] > SEV[v.sev]) { v.sev = risk; v.pill = risk === 'high' ? '14 days or fewer' : '30 days or fewer'; }
  return v;
}

// ---- render ----------------------------------------------------------------------------------------------
let statusTimer = 0;
function setState(state, msg = '') {
  $('out').dataset.state = state;
  $('c-msg').textContent = msg;
  const bar = $('c-bar');
  bar.dataset.state = state;
  if (state !== 'ok') { bar.textContent = msg; bar.querySelector?.('.pill'); }
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => { $('c-status').textContent = state === 'ok' ? $('c-barsr').textContent : msg; }, 500);
}

function render() {
  const mode = how();
  $('f-mc').hidden = mode !== 'meter';
  $('salt-hint').hidden = mode === 'meter';
  const res = { temp: read('temp'), rh: read('rh') };
  if (mode === 'meter') res.mc = read('mc');
  showFieldErrors(res);
  const T = res.temp.v, RH = res.rh.v, storage = $('storage').value;
  document.querySelectorAll('.presets .chip').forEach((c) => c.setAttribute('aria-pressed', String(Number(c.dataset.t) === T && Number(c.dataset.rh) === RH)));
  const bad = Object.values(res).filter((r) => r.err && !r.empty);
  const empty = Object.values(res).filter((r) => r.empty);
  if (bad.length) return setState('invalid', bad.map((r) => r.err).join(' '));
  if (empty.length) return setState('empty', 'Enter ' + Object.entries(res).filter(([, r]) => r.empty).map(([k]) => FIELDS[k].name.toLowerCase()).join(', ') + ' to see the result.');
  const m = mode === 'meter' ? res.mc.v : mode === 'sticks' ? P.SALT_STICKY_MC : P.SALT_FLOWS_MC;

  const Eq = emc(T, RH), A = astDays(T, m);
  const fc = Array.from({ length: 7 }, () => ({ t: T, rh: RH }));
  const left = daysLeft(m, storage, fc);
  const astNow = Math.round(A.value);
  // The headline never relies on the drying assumption: the smaller of "the engine's countdown" and "storage days at today's moisture".
  const useNow = left > astNow;
  const shown = useNow ? Math.min(astNow, P.MAX_AST_DAYS) : left;
  const capped = !useNow && left >= P.HORIZON_DAYS;
  const v = verdict({ mode, m, storage, E: Eq.value, left, shown });

  const frac = Math.min(1, shown / 60);
  const dialLvl = SEV[riskLevel(0, shown).toLowerCase()] ? riskLevel(0, shown).toLowerCase() : 'low';
  $('c-dial').innerHTML = dialSvg({ ticks: 36, on: Math.round(frac * 36), hand: frac, level: dialLvl });
  $('c-days').textContent = capped ? '365+' : shown >= P.MAX_AST_DAYS ? '3,650+' : shown.toLocaleString('en-GB');
  $('c-days').classList.toggle('long', $('c-days').textContent.length > 3);
  $('c-unit').textContent = useNow ? (shown === 1 ? 'day now' : 'days now') : capped ? 'days, max' : (shown === 1 ? 'day left' : 'days left');
  $('c-scale').textContent = (useNow ? 'Days of storage at today’s moisture if it stays this wet, not the engine’s countdown. ' : capped ? '365+ is the longest the tool looks ahead, not a prediction. ' : '') + 'A full ring is 60 days or more.';
  $('c-level').textContent = v.pill; $('c-level').className = `pill pill-${v.sev}`;
  $('c-title').textContent = v.title;

  const here = `${f1(m).replace(/\.0$/, '')}%`;
  const eqs = `${f1(Eq.value)}%`;
  $('c-lead').textContent = storage === 'hermetic' ? `Sealed bags hold the grain at ${here}, whatever the air does.`
    : storage === 'drying' ? `Grain being dried is held at ${here} until you test it again.`
    : `In this air the grain is heading for ${eqs}, from ${here} today.`;
  $('c-emc').textContent = eqs; $('c-emc-row').hidden = storage === 'hermetic' || storage === 'drying';
  $('c-ast').textContent = A.value >= P.MAX_AST_DAYS ? '3,650+ days' : `${astNow.toLocaleString('en-GB')} days`;
  $('c-eng').textContent = left >= P.HORIZON_DAYS ? '365+ days' : `${left} days`;

  const notes = [v.note];
  const permeable = ['sack', 'crib', 'floor'].includes(storage);
  if (permeable && m > P.EAS_MAX_MC && Eq.value > P.EAS_MAX_MC) notes.push(`Even if the sack dries as far as this air allows, ${eqs} is still above the 13.5% limit.`);
  if (useNow && permeable) notes.push(`If it dries toward ${eqs} as the engine assumes, the count stretches to ${left >= P.HORIZON_DAYS ? '365 or more' : left} days. That drying rate (5% of the gap a day) is our assumption and has not been tested in the field.`);
  $('c-notes').innerHTML = notes.map((n) => `<p class="out-note">${n.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</p>`).join('');

  const flags = [...new Set([...Eq.warnings, ...A.warnings])].map((w) => FLAG[w]).filter(Boolean);
  if (mode !== 'meter') flags.unshift(`The engine assumes ${f1(m).replace(/\.0$/, '')}% when salt ${mode === 'sticks' ? 'sticks' : 'flows'}. That is our assumption, to be replaced by meter readings.`);
  $('c-flags').innerHTML = flags.map((f) => `<li class="on">${f}</li>`).join('') + BASE_FLAGS.map((f) => `<li>${f}</li>`).join('');

  $('out').dataset.state = 'ok';                   // the chart is measured, so it must be laid out (not display:none) while it draws
  drawChart(m, T, RH, storage, Eq.value, left);

  const barText = `${v.title}: ${capped ? '365+' : shown.toLocaleString('en-GB')} ${useNow ? 'storage days now' : 'days'}`;
  $('c-bar').innerHTML = `<span class="pill pill-${v.sev}">${v.pill}</span><span></span>`;
  $('c-bar').lastChild.textContent = barText;
  $('c-barsr').textContent = `${barText}.`;
  $('out').dataset.state = 'ok'; $('c-bar').dataset.state = 'ok'; $('c-msg').textContent = '';
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => { $('c-status').textContent = $('c-barsr').textContent; }, 500);
}

// ---- the drift chart ---------------------------------------------------------------------------------------
// Text keeps one size in screen pixels, so on a phone (viewBox 520 wide, drawn ~320 px) a label is ~1.6x wider in viewBox
// units than on a desktop. Nothing is therefore laid over the plot: the two labels sit in rows ABOVE it ("air settles at"
// on top, "storage time used up" next to the top of the now-line below it), measured in the browser and shortened when the
// room on either side of the now-line is too small. The plot holds only the curve, the lines and the axis, so no label can
// run over a line or off the left edge. Tick spacing is chosen from the pixel gap, not from a fixed number of ticks.
const SVGNS = 'http://www.w3.org/2000/svg';
const VB_W = 520, PLOT_H = 102;
let lastChart = null;
const chartU = () => { const w = $('c-chart').getBoundingClientRect().width; return w > 0 ? VB_W / w : 1; };

function drawChart(m0, T, RH, storage, eq, left) {
  lastChart = [m0, T, RH, storage, eq, left];
  const svg = $('c-chart'), u = chartU();
  svg.style.setProperty('--u', u.toFixed(3));
  const fa = 11.5 * u, fl = 12.5 * u;                                   // font sizes in viewBox units: axis text, label text
  const measure = (text, cls) => {
    const t = document.createElementNS(SVGNS, 'text'); t.setAttribute('class', cls); t.textContent = text; svg.appendChild(t);
    let w = 0; try { w = t.getBBox().width; } catch { w = 0; }
    t.remove(); return w || text.length * (cls === 'c-lab' ? fl : fa) * 0.6;
  };
  const H = left < P.HORIZON_DAYS ? Math.max(30, Math.min(120, Math.ceil(left * 1.15))) : 120;
  const pts = []; let m = m0;
  for (let d = 0; d <= H; d++) { pts.push([d, m]); m = drift(m, storage, T, RH); }
  const lo = Math.floor(Math.min(m0, eq, 13.5, ...pts.map((p) => p[1])) - 0.8), hi = Math.ceil(Math.max(m0, eq, 15, ...pts.map((p) => p[1])) + 0.8);
  const permeable = storage !== 'hermetic' && storage !== 'drying';
  const hasNow = left < H;
  const ROW = fl * 1.35;                                                // one label row
  const top = ((permeable ? 1 : 0) + (hasNow ? 1 : 0)) * ROW + fa * 0.7 + 8;                    // the top tick label hangs above the plot
  // y ticks: the smallest step from the list whose tick-to-tick gap is at least 1.5 text heights on screen (and always two or more)
  const perPct = PLOT_H / (hi - lo);
  const ticksFor = (st) => { const out = []; for (let v = Math.ceil(lo / st) * st; v <= hi; v += st) out.push(v); return out; };
  const steps = [1, 2, 4, 5, 10, 20].filter((st) => ticksFor(st).length >= 2);
  const step = steps.find((st) => st * perPct >= fa * 1.5) || steps[steps.length - 1] || 1;
  const ticks = ticksFor(step);
  const left0 = Math.max(44, Math.ceil(Math.max(...ticks.map((v) => measure(`${v}%`, 'c-axis'))) + 14));   // room for the widest tick label
  const area = [left0, top, 508, top + PLOT_H], { X, Y } = scales(area, [0, H], [lo, hi]);
  svg.setAttribute('viewBox', `0 0 ${VB_W} ${(area[3] + fa * 1.9 + 16).toFixed(1)}`);
  let s = ticks.map((v) => `<line class="c-grid" x1="${area[0]}" x2="${area[2]}" y1="${Y(v)}" y2="${Y(v)}"/><text class="c-axis" x="${area[0] - 6}" y="${Y(v) + fa * 0.35}" text-anchor="end">${v}%</text>`).join('');
  s += `<line class="c-limit" x1="${area[0]}" x2="${area[2]}" y1="${Y(13.5)}" y2="${Y(13.5)}"/>`;
  s += [0, 0.5, 1].map((f) => { const d = Math.round(f * H); return `<text class="c-axis" x="${X(d)}" y="${area[3] + fa + 12}" text-anchor="${f === 0 ? 'start' : f === 1 ? 'end' : 'middle'}">${f === 0 ? 'Today' : 'Day ' + d}</text>`; }).join('');
  s += `<path class="c-line c-a" d="${linePath(pts, X, Y)}"/>`;
  let row = 0;
  if (permeable) {                                                       // top row: the air line, with a sample of its dashes
    const airY = Y(eq), by = ROW * 0.85 + 2;
    const lab = [`air settles at ${f1(eq)}%`, `air ${f1(eq)}%`].find((t) => measure(t, 'c-axis') + 34 <= area[2] - 4) || `air ${f1(eq)}%`;
    const w = measure(lab, 'c-axis');
    s += `<line class="c-air" x1="${area[0]}" x2="${area[2]}" y1="${airY}" y2="${airY}"/>`;
    s += `<line class="c-air" x1="${area[2] - w - 30}" x2="${area[2] - w - 8}" y1="${by - fa * 0.3}" y2="${by - fa * 0.3}"/>`;
    s += `<text class="c-axis" x="${area[2]}" y="${by}" text-anchor="end">${lab}</text>`;
    row = 1;
  }
  if (hasNow) {                                                          // next row: beside the top of the now-line
    const lx = X(left), ly = row * ROW + ROW * 0.85 + 2;
    const room = [lx - 8 - 4, VB_W - 4 - (lx + 8)];                      // free width left and right of the line
    const lab = ['storage time used up', 'used up'].find((t) => measure(t, 'c-lab') <= Math.max(...room)) || 'used up';
    const w = measure(lab, 'c-lab');
    const onLeft = room[0] >= w || room[0] >= room[1];
    s += `<line class="wx-now" x1="${lx}" x2="${lx}" y1="${ly - fl * 0.9}" y2="${area[3]}"/>`;
    s += `<text class="c-lab c-halo" x="${(onLeft ? lx - 7 : lx + 7).toFixed(1)}" y="${ly}" text-anchor="${onLeft ? 'end' : 'start'}">${lab}</text>`;
  }
  svg.innerHTML = s;
}
// Redraw when the drawn width changes (rotation, resize) or the web font arrives: label widths depend on both.
if ('ResizeObserver' in window) {
  let lastW = 0;
  new ResizeObserver(() => { const w = Math.round($('c-chart').getBoundingClientRect().width); if (w && w !== lastW) { lastW = w; if (lastChart) drawChart(...lastChart); } }).observe($('c-chart'));
}
document.fonts?.ready.then(() => { if (lastChart) drawChart(...lastChart); });

for (const id of Object.keys(FIELDS)) {
  $(id).addEventListener('blur', () => { touched.add(id); render(); });
}
form.addEventListener('input', render);
form.addEventListener('change', () => { for (const id of Object.keys(FIELDS)) if ($(id) === document.activeElement) touched.add(id); render(); });
form.addEventListener('submit', (e) => e.preventDefault());
document.querySelectorAll('.presets .chip').forEach((c) => c.addEventListener('click', () => { $('temp').value = c.dataset.t; $('rh').value = c.dataset.rh; render(); }));
render();
document.documentElement.dataset.calcReady = '1';   // T7-01: tests wait for this (calc.js is loaded by a dynamic import)

// ---- optional: recent weather for one example ward (NASA POWER, through our own /api/recent-weather) -------------------
// Per research/nasa-due-diligence.md section 10: nothing is requested until the visitor TAPS the button (no request on page load),
// the calculator inputs are never filled from it (it stays a user-input tool), and the result is one quiet text line with the
// "to <date>" end of the data and "an area estimate, not a measurement at your store", same wording as the bot's /weather.
const MON = { en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], sw: ['Jan', 'Feb', 'Mac', 'Apr', 'Mei', 'Jun', 'Jul', 'Ago', 'Sep', 'Okt', 'Nov', 'Des'] };
const wxDate = (iso, l) => { const [y, m, d] = iso.split('-').map(Number); return `${d} ${MON[l][m - 1]} ${y}`; };
const WX_NOTE = {
  en: (d, t, rh, rain) => `Recent weather near Kitale (NASA satellite/model estimate, to ${d}): about ${t} C, humidity ${rh}%, ${rain} mm rain. This is an area estimate, not a measurement at your store.`,
  sw: (d, t, rh, rain) => `Hali ya hewa ya karibuni karibu na Kitale (makadirio ya satelaiti/modeli ya NASA, hadi ${d}): takriban ${t} C, unyevu ${rh}%, mvua ${rain} mm. Ni makadirio ya eneo, si kipimo cha ghala lako.`,
};
const WX_DOWN = { en: 'Recent weather is not available right now. Try again later.', sw: 'Hali ya hewa ya karibuni haipatikani kwa sasa. Jaribu tena baadaye.' };
async function showRecentWeather() {
  const btn = $('wx-btn');
  btn.disabled = true;
  const say = (en, sw) => { $('wx-en').textContent = en; $('wx-sw').textContent = sw; $('wx-note').classList.add('on'); };
  try {
    const ctl = new AbortController(); const timer = setTimeout(() => ctl.abort(), 6000);
    const r = await fetch('/api/recent-weather?ward=Kitale', { signal: ctl.signal, headers: { accept: 'application/json' } });
    clearTimeout(timer);
    if (!r.ok) throw new Error('status');
    const j = await r.json();
    const days = (Array.isArray(j.days) ? j.days : []).filter((x) => x && Number.isFinite(x.t) && Number.isFinite(x.rh) && Number.isFinite(x.rain));
    const last = days[days.length - 1];
    if (!last || j.ward !== 'Kitale' || !/^\d{4}-\d{2}-\d{2}$/.test(last.date || '') || j.asOf !== last.date) throw new Error('shape');
    const a = [last.t.toFixed(1), String(Math.round(last.rh)), last.rain.toFixed(1)];
    say(WX_NOTE.en(wxDate(last.date, 'en'), ...a), WX_NOTE.sw(wxDate(last.date, 'sw'), ...a));
    $('wx-ref').hidden = false;
  } catch { /* offline, blocked, NASA down: say so, the calculator is unaffected */
    $('wx-ref').hidden = true; say(WX_DOWN.en, WX_DOWN.sw);
  } finally { btn.disabled = false; }
}
$('wx-btn')?.addEventListener('click', showRecentWeather);
