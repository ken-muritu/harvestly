// Proves the browser port (site/assets/js/engine.js) matches the Python engine's reference results.
//   node tools/test-engine-js.mjs
// 0. The single rounding rule: golden ties from vectors.json plus every reading 5.00..40.00 step 0.01 against integer arithmetic.
// 3. daysLeft over varying forecasts, every storage type, thresholds, empty forecast (vectors.json days_left_cases).
// 1. EMC (49 values) and allowable storage time (60 values) from engine/vectors.json to 1e-6.
// 2. The dry_grain_rewets scenario (70 days, a measured 13.0% batch in damp air) replayed day by day with the
//    port's drift(), astDays() and daysLeft(): moisture, life used, days left and risk level must equal the
//    trace the Python engine wrote.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import { emc, astDays, drift, daysLeft, riskLevel, fmt } from '../site/assets/js/engine.js';

const V = JSON.parse(fs.readFileSync(new URL('../engine/vectors.json', import.meta.url)));
let n = 0, worst = 0;
for (const r of V.emc) { const d = Math.abs(emc(r.temp_c, r.rh).value - r.emc); worst = Math.max(worst, d); assert(d <= 1e-6, `EMC ${r.temp_c} C ${r.rh}%: ${emc(r.temp_c, r.rh).value} vs ${r.emc}`); n++; }
for (const r of V.ast) { const d = Math.abs(astDays(r.temp_c, r.mc).value - r.days); worst = Math.max(worst, d); assert(d <= 1e-6, `AST ${r.temp_c} C ${r.mc}%: ${astDays(r.temp_c, r.mc).value} vs ${r.days}`); n++; }
console.log(`ok  ${n} table values match vectors.json (worst difference ${worst.toExponential(1)})`);

// Scenario replay. Weather in this scenario is constant: 19 C, 92% RH, sack storage, meter 13.0% on day 0.
const sc = V.scenarios.find((s) => s.name === 'dry_grain_rewets');
const evening = sc.trace.filter((t) => t.event === 'evening');
const fc = Array.from({ length: 7 }, () => ({ t: 19, rh: 92 }));
let m = 13.0, life = 0, checked = 0;
for (const day of evening) {
  m = drift(m, 'sack', 19, 92);
  life += 1 / astDays(19, m).value;
  const left = daysLeft(m, 'sack', fc, life);
  assert.equal(left, day.days_left, `days_left on ${day.day}`);
  assert(Math.abs(m - day.moisture_exact) <= 1e-8 && fmt(m, 1) === day.moisture_s, `moisture on ${day.day}: ${m} vs ${day.moisture}`);
  assert(Math.abs(life - day.life_used_exact) <= 1e-8 && fmt(100 * life, 1) === day.life_used_pct_s, `life used on ${day.day}: ${100 * life} vs ${day.life_used_pct}`);
  assert.equal(riskLevel(life, left), day.level, `level on ${day.day}`);
  checked++;
}
console.log(`ok  ${checked} days of the dry_grain_rewets scenario: moisture, life used, days left, level`);

// ---- rounding: golden ties, then a fuzz of 3501 readings against exact integer arithmetic (0 divergences allowed)
let rn = 0;
for (const r of V.rounding) {
  for (const [k, p] of [['fmt0', 0], ['fmt1', 1], ['fmt2', 2]]) if (k in r) { assert.equal(fmt(r.x, p), r[k], `${k}(${r.x})`); rn++; }
}
let div = 0;
for (let h = 500; h <= 4000; h++) {
  const x = h / 100, t = Math.floor((h + 5) / 10);
  if (fmt(x, 1) !== `${Math.floor(t / 10)}.${t % 10}`) div++;
  if (fmt(x, 2) !== `${Math.floor(h / 100)}.${String(h % 100).padStart(2, '0')}`) div++;
  if (fmt(x, 0) !== String(Math.floor((h + 50) / 100))) div++;
  rn++;
}
assert.equal(div, 0, `${div} rounding divergences`);
for (const [x, w] of [[0.5, '1'], [2.5, '3'], [6.5, '7'], [99.5, '100']]) assert.equal(fmt(x, 0), w);
console.log(`ok  ${rn} rounding checks (golden ties + 3501 readings 5.00..40.00), 0 divergences`);

// ---- daysLeft: varying forecasts, all storage types, near thresholds, and the empty forecast
let dl = 0;
for (const c of V.days_left_cases) {
  const fcs = c.forecast.map(([t, rh]) => ({ t, rh }));
  const left = daysLeft(c.moisture, c.storage, fcs, c.life);
  assert.equal(left, c.left, `daysLeft ${JSON.stringify(c)} -> ${left}`);
  assert.equal(riskLevel(c.life, left), c.level, `riskLevel ${JSON.stringify(c)}`);
  dl++;
}
assert.equal(daysLeft(14, 'sack', []), null);
assert.equal(daysLeft(14, 'sack', undefined), null);
assert.equal(riskLevel(0, daysLeft(14, 'sack', [])), 'UNKNOWN');
console.log(`ok  ${dl} daysLeft cases (4 storage types, varying forecasts, thresholds, empty forecast = null)`);

// ---- R3 wording checks on the generated site data (S3-01, E3-01): the SMS text the pages show
import { SCENARIOS, TEMPLATES } from '../site/assets/js/data.js';
const texts = [];
for (const sc of SCENARIOS) JSON.stringify(sc, (k, v) => { if (typeof v === 'string' && v.startsWith('Harvestly:')) texts.push(v); return v; });
assert(texts.length > 0, 'no SMS text found in data.js');
const seal = SCENARIOS.find((sc) => sc.name === 'demo_pitch').events.filter((e) => e.reply === 'SEALED').pop();
assert(seal && /3 months or more/.test(seal.text) && !/falling fast/.test(seal.text) && !/hupungua haraka/.test(seal.text_sw), 'story day 12 sealed text');
for (const t of texts) {
  if (/Recorded \(meter .*3 months or more/.test(t)) assert(!/falling fast/.test(t), `sealed/capped text says falling fast: ${t}`);
  assert(!/METER or SALT|MITA au CHUMVI\./.test(t), `bare command in a message: ${t}`);
}
for (const [code, t] of Object.entries(TEMPLATES)) for (const s of [t.en, t.sw]) assert(!/METER or SALT|MITA au CHUMVI\./.test(s), `bare command in template ${code}`);
console.log(`ok  ${texts.length} site SMS texts: no "falling fast" on a recorded sealed/capped result, no bare METER/SALT instruction`);
