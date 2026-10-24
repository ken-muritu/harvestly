import { page, mark, ref, esc } from '../lib.mjs';
import { PARAMS, ALSO_IN_CODE } from '../params.mjs';
import { bi, langToggle } from '../parts.mjs';
import { TEMPLATES, ASSUMPTIONS } from '../../../site/assets/js/data.js';
import { EMC_TEMPS_F, EMC_RH, EMC_TABLE, AST_TEMPS_F, AST_MC, AST_TABLE, emc, astDays, drift } from '../../../site/assets/js/engine.js';
import { scales, linePath } from '../../../site/assets/js/chart.js';

// ---- worked example ------------------------------------------------------------------------------
const E0 = emc(18.3, 63).value;
const m1 = drift(18, 'sack', 18.3, 63);
const a1 = astDays(18.3, m1).value;

// ---- drift chart (built here, no script needed). Labels are two letters on the curves; the key sits under the chart ----
const EMC_DRY = emc(18.3, 63).value, EMC_WET = emc(18, 85).value;
const drift2 = (() => {
  const area = [44, 18, 508, 206], { X, Y } = scales(area, [0, 60], [12, 20]);
  const run = (m, t, rh) => Array.from({ length: 61 }, (_, d) => { const p = [d, m]; m = drift(m, 'sack', t, rh); return p; });
  const dry = run(18, 18.3, 63), wet = run(13, 18, 85);
  let s = `<svg class="chart-svg" viewBox="0 0 520 240" role="img" aria-label="Two sacks over 60 days. Sack A starts at 18 percent in air at 63 percent humidity and falls toward ${EMC_DRY.toFixed(1)} percent. Sack B starts at 13 percent in air at 85 percent humidity and rises toward ${EMC_WET.toFixed(1)} percent, crossing the 13.5 percent limit within days." focusable="false">`;
  for (const v of [12, 14, 16, 18]) s += `<line class="c-grid" x1="${area[0]}" x2="${area[2]}" y1="${Y(v)}" y2="${Y(v)}"/><text class="c-axis" x="${area[0] - 8}" y="${Y(v) + 4}" text-anchor="end">${v}%</text>`;
  for (const d of [0, 15, 30, 45, 60]) s += `<text class="c-axis" x="${X(d)}" y="230" text-anchor="${d === 0 ? 'start' : d === 60 ? 'end' : 'middle'}">${d === 0 ? 'Day 0' : d}</text>`;
  s += `<line class="c-limit" x1="${area[0]}" x2="${area[2]}" y1="${Y(13.5)}" y2="${Y(13.5)}"/>`;
  s += `<path class="c-line c-a" d="${linePath(dry, X, Y)}"/><path class="c-line c-b" d="${linePath(wet, X, Y)}"/>`;
  s += `<text class="c-end" x="${X(60) - 2}" y="${Y(dry[60][1]) - 10}" text-anchor="end">A</text><text class="c-end" x="${X(60) - 2}" y="${Y(wet[60][1]) - 10}" text-anchor="end">B</text>`;
  return s + '</svg>';
})();

// ---- the two tables -------------------------------------------------------------------------------
const heatE = (v) => (v <= 13.5 ? 'h0' : v <= 15 ? 'h1' : v <= 17 ? 'h2' : 'h3');
const C = (f) => Math.round((f - 32) * 5 / 9);
const n0 = (v) => v.toLocaleString('en-GB');
const emcTable = `<table class="grid-table grid-table-emc"><caption>Equilibrium moisture of maize, % wet basis: where grain settles in air at a given temperature and humidity (Arkansas FSA1074, Table A ${ref(6)})</caption>
<thead><tr><th scope="col" class="corner">Temperature (rows), humidity % (columns)</th>${EMC_RH.map((r) => `<th scope="col">${r}</th>`).join('')}</tr></thead><tbody>${EMC_TABLE.map((row, i) => `<tr><th scope="row">${C(EMC_TEMPS_F[i])} °C <span class="alt">(${EMC_TEMPS_F[i]} °F)</span></th>${row.map((v) => `<td class="${heatE(v)}">${v.toFixed(1)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
const heatA = (v) => (v >= 100 ? 'h0' : v >= 30 ? 'h1' : v >= 14 ? 'h2' : 'h3');
const astTable = `<table class="grid-table grid-table-ast"><caption>Storage period for maize, days to about 0.5% dry-matter loss, by grain temperature and moisture (Arkansas FSA1058, Table 1 ${ref(7)})</caption>
<thead><tr><th scope="col" class="corner">Temperature (rows), moisture % (columns)</th>${AST_MC.map((m) => `<th scope="col">${m}</th>`).join('')}</tr></thead><tbody>${AST_TABLE.map((row, i) => `<tr><th scope="row">${C(AST_TEMPS_F[i])} °C <span class="alt">(${AST_TEMPS_F[i]} °F)</span></th>${row.map((v) => `<td class="${heatA(v)}">${n0(v)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;

// ---- message catalogue ------------------------------------------------------------------------------
const WHEN = {
  TEST_FIRST: ['Not yet tested', 'Asks for a meter reading first and offers the salt test as a draft, with no amounts or times. At most 3 requests.'],
  DRY_NOW: ['The test says wet', 'Sent again if the countdown halves or the risk level rises, and at most twice more while it stays HIGH.'],
  RAIN_COVER: ['Drying, and rain is due', 'Rain in the next 24 hours: 60% chance or 5 mm.'],
  RETEST: ['The estimate has moved past the test', 'A full point past the salt line, up or down.'],
  NEARLY_DRY: ['Salt test passed, or a reading of 13.6–15%', 'Answers a test. Never pushed on an estimate.'],
  READY_TO_STORE: ['Meter or hygrometer at 13.5% or below', 'The only message that says grain is dry.'],
  CONFIRM_DRY: ['Sealed in hermetic bags on a salt test only', 'Asks for a meter check within a week.'],
  OPEN_AND_DRY: ['Sealed, but the test said wet', 'Open the bags and dry the maize.'],
  SORT_AND_SELL: ['Most of the storage life used', '80% used.'],
  INSECT_REMINDER: ['Seven weeks or more in sacks, measured dry', 'One reminder that insects get more likely the longer grain stays in sacks, with a pointer to hermetic bags.'],
  STATUS: ['A reading or a storage change is recorded', 'Gives the last reading and when it was taken, then the estimate since, labelled as an estimate.'],
  HELP: ['A reply it does not understand', 'Lists the replies it knows.'],
  THANKS: ['An acknowledgement', ''],
  CLOSED: ['The batch is sold or deposited', 'Alerts for the batch end.'],
  STOPPED: ['The farmer replies STOP', 'No more messages until START.'],
  HIGH_ALERT: ['HIGH risk, repeated', 'An unanswered urgent warning, spaced and capped.'],
  WELCOME: ['At registration', 'Says what the messages are, credits the weather source, and explains STOP.'],
};
const when = (code) => WHEN[code] || ['Other message', ''];
const PHN = { weeks: 'number' };
const ph = (t) => esc(t).replace(/\{(\w+)\}/g, (_, k) => `<span class="ph">${PHN[k] || k.replace(/_/g, ' ')}</span>`);
const msgRows = Object.entries(TEMPLATES).map(([code, t]) => `<tr><th scope="row" data-label="Situation">${esc(when(code)[0])}${when(code)[1] ? `<span class="sub">${esc(when(code)[1])}</span>` : ''}</th><td data-label="Code"><code>${code}</code></td><td data-label="Message"><span data-l="en">${ph(t.en)}</span><span data-l="sw" lang="sw">${ph(t.sw)}</span></td></tr>`).join('');

const paramRows = PARAMS.map((p, i) => `<tr><th scope="row" data-label="Parameter"><span class="pn">${i + 1}</span>${esc(p.name)}</th><td data-label="Value">${esc(p.value)}</td><td data-label="Label"><span class="tag tag-${p.tag.toLowerCase()}">${p.tag}</span></td><td data-label="Where it comes from">${esc(p.from).replace(/\[(\d+)\]/g, (_, n) => ref(n))}</td><td data-label="In the code"><code>${esc(p.code)}</code></td></tr>`).join('');
const seen = new Set();
const assumeRows = ASSUMPTIONS.filter((a) => !seen.has(a.text) && seen.add(a.text)).map((a) => `<li><span class="tag tag-${a.label.toLowerCase()}">${esc(a.label)}</span> ${esc(a.text.replace(/ %/g, '%'))}</li>`).join('');
const alsoRows = ALSO_IN_CODE.map(([k, v]) => `<li><b>${esc(k)}.</b> ${esc(v)}</li>`).join('');
const WORDS = ['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen', 'Twenty'];
const NMSG = Object.keys(TEMPLATES).length;

const body = `
<section class="phero">
  <div class="wrap phero-in">
    <h1>How the countdown works.</h1>
    <p class="lede">One test, one forecast and two published tables give each batch of maize a number of storage days. Here is every step, with the numbers.</p>
    <p class="actions"><a class="btn" href="/#calculator">Try it on your own sacks</a><a class="textlink" href="#tables">Jump to the tables</a></p>
  </div>
</section>

<section class="sec" aria-labelledby="h-day">
  <div class="wrap">
    ${mark(1, 'A day in the engine', 6)}
    <h2 id="h-day">Every evening at 17:00, five steps.</h2>
    <ol class="steps">
      <li><h3>1. Starting moisture</h3><p>It comes only from the farmer&rsquo;s own test. Salt sticks: above 15%, and the countdown uses 18%. Salt flows: below about 15%, and it uses 14.5%, never as proof of 13.5%. A hygrometer reading is converted with the moisture table at the reading&rsquo;s temperature. A meter reading is used as read. Untested grain gets a request to test, never a countdown.</p></li>
      <li><h3>2. Drift</h3><p>Grain in woven sacks, cribs and floors takes on the moisture of the air around it. Each day it closes 5% of the gap to the moisture it would settle at in that air. Hermetic bags do not change. Drying grain is held until the next test.</p><p class="eg"><b>Example.</b> Kitale in a normal October, 18.3&nbsp;°C and 63% humidity ${ref(5)}, settles maize near <b>${E0.toFixed(1)}%</b> ${ref(6)}. A sack at 18% moves to ${m1.toFixed(2)}% after one day.</p></li>
      <li><h3>3. Storage life used</h3><p>Each day uses 1 divided by the storage days at that temperature and moisture ${ref(7)}. When the fractions add up to 1, the grain has lost about 0.5% of its dry weight, which the source puts at roughly one US grade level. The source counts from harvest; the engine counts from the first test.</p><p class="eg"><b>Example.</b> At ${m1.toFixed(2)}% and 18.3&nbsp;°C the table gives about ${a1.toFixed(0)} days, so that day uses ${(100 / a1).toFixed(1)}% of the batch&rsquo;s storage life.</p></li>
      <li><h3>4. Countdown and level</h3><p>The engine runs the days forward over the 7-day forecast, then repeats the forecast&rsquo;s average, and counts the days until the life is used up. HIGH: 80% used, or 14 days or fewer. MEDIUM: 50% used, or 30 days or fewer. These thresholds are ours, set for the lead time sun-drying needs in a wet season.</p></li>
      <li id="send"><h3>5. What is sent</h3><p>At most one unprompted message a day, in this order: rain in the next 24 hours while the farmer is drying; a changed recommendation; a worse countdown (risk up, or days left halved and 60 or fewer); a spaced and capped reminder; the one-off insect reminder. A reply is answered at once and never uses up the evening slot.</p>
        <details class="more"><summary>The repeat rules</summary>
          <p>An ordinary repeat is spaced at least 3 days apart and sent at most twice per test. Re-tests are asked at most twice in 30 days, and rain alerts pause after three go unanswered.</p>
          <p>Urgent warnings (HIGH) repeat weekly, at most four times per test result. The fourth says it is the last reminder on that result and asks for a new test; after it the engine stays quiet until a new test result restarts the count, so a batch can go silent while its countdown is at zero.</p>
        </details></li>
    </ol>
  </div>
</section>

<section class="sec panel" aria-labelledby="h-drift">
  <div class="wrap">
    ${mark(2, 'Drift', 6)}
    <h2 id="h-drift">Sixty days in a sack.</h2>
    <p class="prose-wide">The same rule, run forward. Wet grain in dry air dries slowly. Dry grain in damp air does not stay dry: at 85% humidity sack B heads for ${EMC_WET.toFixed(1)}% and passes the 13.5% line within days. That is the failure Harvestly watches for.</p>
    <figure class="chart-fig">${drift2}<ul class="chart-keys"><li><i class="lg lg-1"></i><span><b>A.</b> Starts at 18%, in dry air (18.3&nbsp;°C, 63% humidity). Falls toward ${EMC_DRY.toFixed(1)}%.</span></li><li><i class="lg lg-2"></i><span><b>B.</b> Starts at 13%, in damp air (18&nbsp;°C, 85% humidity). Rises toward ${EMC_WET.toFixed(1)}%.</span></li><li><i class="lg lg-l"></i><span>The 13.5% limit.</span></li></ul>
    <p class="fine">Engine rule: 5% of the gap closed each day, in woven sacks. The 5% rate is a calibration assumption, not a measurement.</p></figure>
  </div>
</section>

<section class="sec" id="tables" aria-labelledby="h-tables">
  <div class="wrap">
    ${mark(3, 'The tables', 6)}
    <h2 id="h-tables">The two published tables.</h2>
    <p class="prose-wide">Both are US corn tables from the University of Arkansas Extension, copied into the engine and checked cell by cell. Shading: in the first table, amber from 13.5% upward; in the second, amber as the days run short. Between the printed values the engine interpolates. The tables are in degrees Fahrenheit; the rows show both.</p>
    <p class="scroll-hint">Scroll the table sideways.</p>
    <div class="table-wrap" tabindex="0" role="region" aria-label="Moisture table, scrolls sideways">${emcTable}</div>
    <p class="scroll-hint">Scroll the table sideways.</p>
    <div class="table-wrap" tabindex="0" role="region" aria-label="Storage-period table, scrolls sideways">${astTable}</div>
  </div>
</section>

<section class="sec panel" aria-labelledby="h-msgs">
  <div class="wrap">
    ${mark(4, 'What the farmer is told', 6)}
    <h2 id="h-msgs">${WORDS[NMSG] || NMSG} messages, in two languages.</h2>
    <div class="rules-bar"><p>Plain characters only, two SMS at most. Fields in <span class="ph">this style</span> are filled in per batch. Draft wording.</p>${langToggle()}</div>
    <details class="more"><summary>Show all ${NMSG} messages</summary><div class="table-wrap"><table class="params msgs"><caption class="vh">The engine&rsquo;s message templates</caption><thead><tr><th scope="col">Situation</th><th scope="col">Code</th><th scope="col">Message</th></tr></thead><tbody>${msgRows}</tbody></table></div></details>
  </div>
</section>

<section class="sec" id="params" aria-labelledby="h-params">
  <div class="wrap">
    ${mark(5, 'The parameters', 6)}
    <h2 id="h-params">Fifteen parameters, each labelled.</h2>
    <p class="prose-wide">Labels: <span class="tag tag-source">SOURCE</span> from a publication, <span class="tag tag-source-based">SOURCE-BASED</span> our reading of one, <span class="tag tag-calibration">CALIBRATION</span> our assumption, <span class="tag tag-programme">PROGRAMME</span> a rule we chose, <span class="tag tag-unvalidated">UNVALIDATED</span> not checked against its source or against Kenyan data.</p>
    <div class="table-wrap"><table class="params p5"><caption class="vh">The 15 parameters with their names in the code</caption><colgroup><col class="c1"><col class="c2"><col class="c3"><col class="c4"><col class="c5"></colgroup><thead><tr><th scope="col">Parameter</th><th scope="col">Value</th><th scope="col">Label</th><th scope="col">Where it comes from</th><th scope="col">In the code</th></tr></thead><tbody>${paramRows}</tbody></table></div>
    <details class="more"><summary>Also in the code</summary><ul class="plain">${alsoRows}</ul></details>
    <details class="more"><summary>What the demos assume</summary><ul class="plain assume">${assumeRows}</ul></details>
  </div>
</section>

<section class="sec panel" aria-labelledby="h-check">
  <div class="wrap">
    ${mark(6, 'How it is checked', 6)}
    <h2 id="h-check">How it is checked.</h2>
    <div class="prose-wide">
      <p>The Python reference has automated tests. Its results are published as <code>vectors.json</code>: moisture values, storage-time values and day-by-day scenarios that any other version must reproduce. The JavaScript behind the calculator and the week replay on this site is checked against them by <code>tools/test-engine-js.mjs</code>, and a script asserts the replay equals <code>vectors.json</code> before the data is written.</p>
      <p>What is not validated, and the pilot status, are listed once on the <a href="/#know">home page</a>.</p>
    </div>
  </div>
</section>
`;

export default page({
  path: '/how-it-works',
  title: 'How Harvestly works: the engine, tables and numbers',
  desc: 'How a salt test, the forecast and two published tables become a countdown of storage days for a batch of maize: every step, table, message and parameter.',
  og: 'how-it-works',
  scripts: ['main.js'],
  body,
});
