import { page, mark, ref, esc, formLink } from '../lib.mjs';
import { TEMPLATES } from '../../../site/assets/js/data.js';
import { SC, bi, bubble, phone, langToggle, SACK_DEFS, sackUse, heroDial, fmtDate } from '../parts.mjs';
import { astDays } from '../../../site/assets/js/engine.js';

// ---- data from the engine's own scenarios (site/assets/js/data.js, generated) -----------------------------
const need = (x, what) => { if (!x) throw new Error(`home: scenario data is missing ${what}; regenerate with tools/gen_site_data.py`); return x; };
const find = (sc, pred, what) => need(SC[sc]?.events.find(pred), `${sc}: ${what}`);
const hookMsg = find('demo_pitch', (e) => e.kind === 'evening' && e.code === 'DRY_NOW', 'the DRY_NOW evening message');
const DAY3 = hookMsg.day;
const dayEv = (d) => need(SC.demo_pitch.events.find((e) => e.day === d && e.kind === 'evening'), `demo_pitch day ${d}`);
const BEFORE = dayEv(DAY3 - 1).days_left, AFTER = hookMsg.days_left;
const r1 = find('salt_pass_then_seal', (e) => e.reply === 'SALT NO', 'a SALT NO reply');
const r1b = find('dry_grain_rewets', (e) => e.kind === 'reply', 'the first reply');
const r2 = find('dry_grain_rewets', (e) => e.code === 'RETEST', 'a RETEST message');
const r3sell = find('dry_grain_rewets', (e) => e.code === 'SORT_AND_SELL', 'a SORT_AND_SELL message');
const sent70 = SC.dry_grain_rewets.events.filter((e) => e.kind === 'evening' && e.code).map((e) => e.day);
const seal = SC.demo_pitch.events.find((e) => e.code === 'READY_TO_STORE');
const w70 = SC.dry_grain_rewets.weather[0];
const ast = (m) => Math.round(astDays(18, m).value);

// ---- the ledger of days -----------------------------------------------------------------------------------
const ledgerRows = [15, 19, 23].map((m) => ({ m, d: ast(m) }));
const maxD = ledgerRows[0].d;
const ledger = ledgerRows.map(({ m, d }) => `<li class="led-row">
  <span class="led-m"><b>${m}%</b> moisture</span>
  <span class="led-d"><b>${d}</b> storage days</span>
  <svg class="tape" viewBox="0 0 ${d} 12" preserveAspectRatio="none" width="${((d / maxD) * 100).toFixed(2)}%" height="14" aria-hidden="true" focusable="false"><line x1="0" y1="6" x2="${d}" y2="6" stroke-dasharray="0.42 0.58" stroke-width="12"/></svg>
</li>`).join('');

// ---- rule 3 tape: days counted from 0, labels staggered so neighbours never touch --------------------------
const tape70 = (() => {
  const w = 700, n = w / 70, X = (i) => (i * n + n / 2).toFixed(1);
  let s = `<svg class="tape70" viewBox="0 0 ${w} 104" role="img" aria-label="Seventy days as seventy ticks, counted from day 0. Messages were sent on days ${sent70.join(', ')}." focusable="false">`;
  for (let i = 0; i < 70; i++) {
    const hit = sent70.includes(i);
    s += `<line class="${hit ? 'tk hit' : 'tk'}" x1="${X(i)}" x2="${X(i)}" y1="${hit ? 4 : 20}" y2="${hit ? 40 : 36}" stroke-width="${(n * 0.5).toFixed(1)}"/>`;
  }
  const labs = [...new Set([0, ...sent70, 69])];
  let last = -999, row = 0;
  for (const i of labs) {
    row = (i * n - last < 62) ? 1 - row : 0; last = i * n;
    const y = row ? 96 : 62;
    const anchor = i === 0 ? 'start' : i >= 62 ? 'end' : 'middle';
    if (row) s += `<line class="tl-lead" x1="${X(i)}" x2="${X(i)}" y1="42" y2="${y - 28}"/>`;
    s += `<text class="tl" x="${X(i)}" y="${y}" text-anchor="${anchor}">${i === 0 ? 'Day 0' : i}</text>`;
  }
  return s + '</svg>';
})();

// ---- the hero conversation: real engine formats and templates; hero.js plays it, and the HTML is its final state --------
// JOIN/SAJILI with a ward, a storage word and a bag count is the registration the SMS handler accepts; WELCOME is the engine's template
// for it. The warning is the demo scenario's DRY_NOW (the 34), the farmer's DRYING is the scenario's own reply and THANKS its answer.
const drying = need(SC.demo_pitch.events.find((e) => e.kind === 'reply' && e.cmd === 'STORAGE' && e.code === 'THANKS'), 'demo_pitch: the DRYING reply');
const heroSteps = [
  { pre: true, dir: 'out', en: 'JOIN KITALE SACK 12', sw: 'SAJILI KITALE MAGUNIA 12', meta: '' },
  { pre: true, dir: 'in', en: TEMPLATES.WELCOME.en, sw: TEMPLATES.WELCOME.sw, meta: '' },
  { dir: 'in', en: hookMsg.text, sw: hookMsg.text_sw, meta: [`SMS · ${fmtDate(hookMsg.date)}, 17:00`, `SMS · ${fmtDate(hookMsg.date).replace('Oct', 'Okt')}, 17:00`] },
  { dir: 'out', en: drying.reply, sw: drying.reply_sw, meta: [fmtDate(drying.date), fmtDate(drying.date).replace('Oct', 'Okt')] },
  { dir: 'in', en: drying.text, sw: drying.text_sw, meta: '' },
];
const heroThread = heroSteps.map((m) => bubble(m.dir, m.en, m.sw, m.meta).replace('<li class="msg', `<li${m.pre ? ' data-pre' : ''} class="msg${m.pre ? ' pre' : ''}`)).join('');
const heroAlt = `Example text conversation, simulated weather. The farmer registers with ${heroSteps[0].en}. Harvestly welcomes them. On ${fmtDate(hookMsg.date)} at 17:00 Harvestly warns: ${hookMsg.text} The farmer replies ${drying.reply}. Harvestly answers: ${drying.text}`;
// S6-01: the caption is the only text a screen reader gets while the phone plays, so it follows the Kiswahili toggle too
const heroAltSw = `Mfano wa mazungumzo ya ujumbe, hali ya hewa ya kuigwa. Mkulima anasajili kwa ${heroSteps[0].sw}. Harvestly inamkaribisha. Tarehe ${fmtDate(hookMsg.date).replace('Oct', 'Okt')} saa 17:00 Harvestly inaonya: ${hookMsg.text_sw} Mkulima anajibu ${drying.reply_sw}. Harvestly inajibu: ${drying.text_sw}`;

const fullDate = fmtDate(hookMsg.date, { day: 'numeric', month: 'long', year: 'numeric' });

const body = `
${SACK_DEFS}
<section class="hero" aria-labelledby="h1">
  <div class="wrap hero-in">
    <div class="hero-stage">
      ${heroDial(AFTER)}
      <h1 id="h1"><span class="num">${AFTER}</span><span class="unit">${bi('days left', 'siku zilizobaki')}</span></h1>
    </div>
    <p class="lede">That is the count for one example batch of maize on the day the forecast turned.</p>
    <p class="actions">${formLink('farmer')}<a class="textlink" href="#calculator">How long will your sacks last?</a><a class="textlink" href="#story">Watch that week unfold</a></p>
    <p class="form-note">A prototype. Joining the list is not a sign-up for alerts.</p>
    <p class="example"><span data-l="en"><strong>Example, simulated weather.</strong> The engine&rsquo;s own messages for one batch in woven sacks in Kitale. The warning is from its demo scenario, ${fullDate}, after the farmer&rsquo;s earlier SALT YES reply (not shown). The weather credit in the welcome is the designed live version&rsquo;s wording: this demo, and the Telegram test bot, use simulated weather. No real farmer has received them.</span><span data-l="sw" lang="sw"><strong>Mfano, hali ya hewa ya kuigwa.</strong> Ujumbe wenyewe wa mfumo kwa kundi la mahindi kwenye magunia ya kusokotwa huko Kitale. Onyo linatoka kwenye mfano wake wa majaribio, ${fullDate.replace('October', 'Oktoba')}, baada ya jibu la awali la mkulima CHUMVI NDIYO (halionyeshwi). Neno la sifa ya data ya hali ya hewa kwenye ujumbe wa kukaribisha ni la toleo lililobuniwa: onyesho hili na bot ya majaribio ya Telegram vinatumia hali ya hewa ya kuigwa. Hakuna mkulima halisi aliyeyapokea.</span></p>
    <figure class="hero-phone" id="hero-phone">${phone(heroThread, { sub: ['Harvestly (example)', 'Harvestly (mfano)'], label: 'Example text conversation', threadAttrs: ' id="hero-thread"' })}
      <figcaption class="vh" id="hero-alt" hidden>${bi(heroAlt, heroAltSw)}</figcaption></figure>
  </div>
</section>

<section class="sec problem" id="problem" aria-labelledby="h-problem">
  <div class="wrap">
    ${mark(2, 'The problem')}
    <h2 id="h-problem">The sack doesn&rsquo;t tell you.</h2>
    <div class="two">
      <div class="prose">
        <p><strong>Day 0.</strong> The harvest comes in. It looks fine.</p>
        <p>These two sacks hold maize from the same field. One is at 13% moisture. The other is at 18%. You cannot tell which is which by looking. Moisture is invisible, and the weather changes it every day.</p>
        <p class="reveal-wrap"><button class="btn btn-quiet" type="button" id="reveal" aria-pressed="false" aria-controls="sacks"><span class="when-off">Show me the moisture</span><span class="when-on">Hide the moisture</span></button></p>
      </div>
      <div class="sacks" id="sacks" data-state="hidden">
        <figure class="sk"><div class="sk-art">${sackUse()}<span class="sk-badge" aria-hidden="true">?</span></div><figcaption><b>Sack A</b><span class="sk-note"><span class="when-off">Looks fine.</span><span class="when-on"><b>13%</b> Under the 13.5% limit.</span></span></figcaption></figure>
        <figure class="sk"><div class="sk-art">${sackUse()}<span class="sk-badge" aria-hidden="true">?</span></div><figcaption><b>Sack B</b><span class="sk-note"><span class="when-off">Looks fine.</span><span class="when-on"><b>18%</b> About ${ast(18)} storage days at 18&nbsp;°C ${ref(7)}.</span></span></figcaption></figure>
      </div>
    </div>

    <div class="ledger-wrap">
      <h3>How long maize keeps, at 18&nbsp;°C</h3>
      <ol class="ledger">${ledger}</ol>
      <p class="fine">One tick is one day: storage period to about 0.5% dry-matter loss, University of Arkansas Extension FSA1058, Table 1 ${ref(7)}. The East African standard limit for maize is 13.5% moisture ${ref(3)}. These are US corn tables; see <a href="#know">the limits</a>.</p>
    </div>
  </div>
</section>

<section class="sec panel why" id="why-now" aria-labelledby="h-why">
  <div class="wrap">
    ${mark(3, 'Why now')}
    <p class="dateline">Trans Nzoia, October 2026</p>
    <h2 id="h-why">Less grain, coming in wet.</h2>
    <div class="why-grid">
      <div class="why-stat"><span class="big">2.2&nbsp;Mt</span><p>The US Department of Agriculture cut its forecast for Kenya&rsquo;s 2026/27 maize crop by half, to 2.2 million tonnes, after the drought hit the North Rift ${ref(8, 9)}.</p></div>
      <div class="why-stat"><span class="big big-text">Above&#8209;average rain</span><p>The Kenya Meteorological Department (KMD) expects it from October to December in Trans Nzoia and Uasin Gishu, continuing into January ${ref(12)}.</p></div>
    </div>
    <figure class="quote"><blockquote><p>&ldquo;drying capacity, safe/hermetic storage, aflatoxin surveillance&rdquo;</p></blockquote><figcaption>What the KMD seasonal advisory calls for, 31 August 2026 ${ref(12)}. Harvestly is designed to turn that advice into a prompt for each farmer&rsquo;s own grain.</figcaption></figure>
  </div>
</section>

<section class="sec night story" id="story" aria-labelledby="h-week" data-steps="${SC.demo_pitch.days}">
  <div class="wrap story-intro">
    ${mark(4, 'One week, replayed')}
    <h2 id="h-week">What happens in a week.</h2>
    <p class="story-lede">The engine&rsquo;s demo run on simulated weather, replayed one day at a time from its reference results. An illustration, not a result. Scroll, and the days pass.</p>
    <details class="more"><summary>What the replay assumes</summary>
      <p>The fall from ${BEFORE} days to ${AFTER} depends on our assumption that a sack closes 5% of the gap to the air&rsquo;s moisture each day. That rate has not been tested in the field. The count starts at the first test, not at harvest.</p>
      <p>Countdown level is the engine&rsquo;s own name (Low, Medium, High) for how soon the storage time runs out. It does not say the grain is dry: wet grain can have a long countdown, so moisture is shown on its own line.</p>
    </details>
    <noscript><p class="noscript">This panel needs JavaScript. In short: on day ${DAY3} the forecast turned damp and the countdown fell from ${BEFORE} days to ${AFTER}, on simulated weather${seal ? `; on day ${seal.day} a meter reading cleared the grain and it was sealed` : ''}.</p></noscript>
    <p class="print-only">The printed page shows the first day of the replay only. In short: on day ${DAY3} the forecast turned damp and the countdown fell from ${BEFORE} days to ${AFTER}, on simulated weather${seal ? `; on day ${seal.day} a meter reading cleared the grain and it was sealed` : ''}. The day-by-day replay needs the live page.</p>
  </div>
  <div class="track" id="track">
    <div class="stage" id="stage">
      <div class="wrap stage-in">
        <div class="st-left">
          <p class="st-day"><span id="st-day">Day 0</span> <span class="st-of" id="st-of">of ${SC.demo_pitch.days - 1}</span></p>
          <p class="st-date" id="st-date"></p>
          <p class="st-cap" id="st-cap"></p>
          <div class="controls" id="controls">
            <button type="button" class="ctl" id="prev" aria-label="Previous day">&larr;</button>
            <label class="scrub"><span class="vh">Day</span><input type="range" id="scrub" min="0" max="${SC.demo_pitch.days - 1}" value="0" step="1"></label>
            <button type="button" class="ctl" id="next" aria-label="Next day">&rarr;</button>
          </div>
        </div>
        <div class="st-right">
          <div class="st-main">
          <div class="gauges">
            <div class="gauge-col"><div class="gauge-dial"><div id="dial" class="dial-host"></div><div class="dial-read"><b id="g-days">&ndash;</b><span id="g-unit">days left</span></div></div><p class="dial-scale" id="g-note" hidden></p></div>
            <dl class="meters">
              <div><dt>Countdown level</dt><dd><span class="pill pill-low" id="g-level">Low</span></dd></div>
              <div><dt id="g-moist-l">Moisture estimate</dt><dd><span id="g-moist">&ndash;</span> <span class="pill pill-sm pill-high" id="g-gate"></span></dd></div>
              <div><dt>Storage life used</dt><dd><span id="g-life">&ndash;</span><span class="bar" aria-hidden="true"><i id="g-bar"></i></span></dd></div>
            </dl>
          </div>
          <figure class="chart wx"><figcaption>Weather, with the forecast issued that evening <span class="legend"><span><i class="lg lg-a"></i>happened</span> <span><i class="lg lg-f"></i>forecast</span> <span><i class="lg lg-r"></i>rain</span></span></figcaption><svg id="wx" viewBox="0 0 520 94" role="img" aria-label="Relative humidity for each day of the replay, with rain days marked" focusable="false"></svg></figure>
          <figure class="chart ml"><figcaption>Moisture estimate, % <span class="legend"><span><i class="lg lg-l"></i>13.5% limit</span></span></figcaption><svg id="ml" viewBox="0 0 520 104" role="img" aria-label="The moisture estimate day by day against the 13.5 percent limit" focusable="false"></svg><p class="chart-note">While grain is being dried the engine keeps its last tested moisture, so the line moves only when a new reading is recorded.</p></figure>
          </div>
          <div class="sms-wrap">
            <div class="sms-tools">${langToggle()}</div>
            ${phone('', { sub: 'The farmer\'s phone', time: '17:00', threadAttrs: ' id="thread" tabindex="0" aria-label="Messages so far"' })}
          </div>
        </div>
      </div>
    </div>
  </div>
  <p class="vh" role="status" id="st-status"></p>
</section>

<section class="sec calc" id="calculator" aria-labelledby="h-calc">
  <div class="wrap">
    ${mark(5, 'Your turn')}
    <h2 id="h-calc">How long will your sacks last?</h2>
    <p class="calc-lede">Enter what you know. This runs the engine&rsquo;s two tables and its drift rule in your browser. Nothing you type is sent anywhere.</p>
    <p class="noscript nojs-note">The calculator needs JavaScript. It runs the engine&rsquo;s two tables and its drift rule in your browser. The tables and the rule are on <a href="/how-it-works">How it works</a>.</p>
    <div class="calc-grid">
      <form class="calc-form" id="calc" autocomplete="off" novalidate>
        <fieldset>
          <legend>How did you check the grain?</legend>
          <div class="opts">
            <label class="opt"><input type="radio" name="how" value="meter" checked><span>Meter or hygrometer reading</span></label>
            <label class="opt"><input type="radio" name="how" value="sticks"><span>Salt test: salt stuck</span></label>
            <label class="opt"><input type="radio" name="how" value="flows"><span>Salt test: salt flowed</span></label>
          </div>
          <div class="field" id="f-mc"><label for="mc">Moisture reading, %</label><input id="mc" name="mc" type="text" inputmode="decimal" value="17" aria-describedby="e-mc"><p class="err" id="e-mc" hidden></p></div>
          <p class="hint" id="salt-hint" hidden>The engine uses 18% when salt sticks and 14.5% when it flows. Both are assumptions that a pilot would replace. A salt test only screens: it never clears grain as dry.</p>
        </fieldset>
        <fieldset>
          <legend>The air where the sacks are kept</legend>
          <div class="presets">
            <button type="button" class="chip" data-t="18.3" data-rh="63" aria-pressed="false">Kitale, a normal October</button>
            <button type="button" class="chip" data-t="18" data-rh="85" aria-pressed="false">After a damp spell</button>
          </div>
          <div class="field-row">
            <div class="field"><label for="temp">Temperature, °C</label><input id="temp" name="temp" type="text" inputmode="decimal" value="18.3" aria-describedby="e-temp"><p class="err" id="e-temp" hidden></p></div>
            <div class="field"><label for="rh">Humidity, %</label><input id="rh" name="rh" type="text" inputmode="decimal" value="63" aria-describedby="e-rh"><p class="err" id="e-rh" hidden></p></div>
          </div>
        </fieldset>
        <fieldset>
          <legend>Where is the grain?</legend>
          <div class="field"><label for="storage" class="vh">Storage</label>
            <select id="storage" name="storage"><option value="sack" selected>Woven sacks</option><option value="crib">Crib</option><option value="floor">On the floor</option><option value="hermetic">Hermetic bags, sealed</option><option value="drying">Drying outside</option></select></div>
        </fieldset>
      </form>
      <div class="calc-bar" id="c-bar" data-state="empty" aria-hidden="true"></div>
      <div class="calc-out" id="out" data-state="empty">
        <p class="out-msg" id="c-msg">Enter moisture, temperature and humidity to see the result.</p>
        <div class="out-top"><h3 class="out-title" id="c-title"></h3><span class="pill pill-low" id="c-level"></span></div>
        <div class="out-dial-wrap"><div class="out-dial"><div id="c-dial" class="dial-host"></div><div class="dial-read"><b id="c-days">&ndash;</b><span id="c-unit">days left</span></div></div><p class="dial-scale" id="c-scale">A full ring is 60 days or more.</p></div>
        <div class="out-body">
          <p class="out-lead" id="c-lead"></p>
          <dl class="out-nums">
            <div id="c-emc-row"><dt>Heading for</dt><dd id="c-emc">&ndash;</dd></div>
            <div><dt>Storage days at today&rsquo;s moisture</dt><dd id="c-ast">&ndash;</dd></div>
            <div><dt>Engine countdown</dt><dd id="c-eng">&ndash;</dd></div>
          </dl>
          <div id="c-notes"></div>
        </div>
        <figure class="chart drift"><figcaption>Moisture, day by day, if the air stays like this <span class="legend"><span><i class="lg lg-l"></i>13.5% limit</span></span></figcaption><svg id="c-chart" viewBox="0 0 520 172" role="img" aria-label="The projected moisture of the grain over the coming days" focusable="false"></svg></figure>
        <ul class="flags" id="c-flags"></ul>
      </div>
      <p class="vh" id="c-barsr"></p><p class="vh" role="status" id="c-status"></p>
    </div>
    <div class="wx-use" id="wx-use">
      <button type="button" class="chip" id="wx-btn" aria-describedby="wx-note"><span data-l="en">Show recent weather near Kitale</span><span data-l="sw" lang="sw">Onyesha hali ya hewa ya karibuni karibu na Kitale</span></button>
      <p class="hint" id="wx-note" role="status"><span data-l="en" id="wx-en"></span><span data-l="sw" lang="sw" id="wx-sw"></span> <span id="wx-ref" hidden>${ref(38)}</span></p>
    </div>
  </div>
</section>

<section class="sec rules" id="rules" aria-labelledby="h-rules">
  <div class="wrap">
    ${mark(6, 'Three rules')}
    <h2 id="h-rules">Three rules that keep it honest.</h2>
    <div class="rules-bar"><p>Messages below are the engine&rsquo;s own draft wording.</p>${langToggle()}</div>
    <ol class="rule-list">
      <li class="rule">
        <span class="rule-n" aria-hidden="true">1</span>
        <div class="rule-t"><h3>Only a meter or hygrometer reading clears grain as dry.</h3><p>A salt test that flows says &ldquo;about 15% or less&rdquo;. That is not 13.5%. So the answer is &ldquo;not yet proven&rdquo;, with a place to get a reading. A meter reading of 13.0% is different.</p></div>
        <div class="rule-ex">${phone(bubble('out', r1.reply, r1.reply_sw) + bubble('in', r1.text, r1.text_sw) + bubble('out', r1b.reply, r1b.reply_sw) + bubble('in', r1b.text, r1b.text_sw), { sub: 'Example, engine draft wording', label: 'Example text messages for rule 1' })}</div>
      </li>
      <li class="rule">
        <span class="rule-n" aria-hidden="true">2</span>
        <div class="rule-t"><h3>An estimate only triggers a re-test.</h3><p>If damp air moves the engine&rsquo;s estimate a full point past the salt-test line, the farmer is asked to test again. The engine never orders drying on an estimate alone.</p></div>
        <div class="rule-ex">${phone(bubble('in', r2.text, r2.text_sw, `Day ${r2.day} of a damp spell`), { sub: 'Example, engine draft wording', cls: 'ph-sm', label: 'Example text message for rule 2' })}</div>
      </li>
      <li class="rule">
        <span class="rule-n" aria-hidden="true">3</span>
        <div class="rule-t"><h3>Every repeat is spaced and capped.</h3><p>Seventy days of damp air at ${w70.t.toFixed(0)}&nbsp;°C and ${w70.rh.toFixed(0)}% humidity${w70.rh > 90 ? ' (the table ends at 90%, so the engine treats it as 90%)' : ''}, on grain that started at a measured 13.0%: ${sent70.length === 3 ? 'three' : sent70.length} messages in all. An unanswered urgent warning goes out weekly, at most four times, and the fourth says it is the last reminder. The other limits are on <a href="/how-it-works#send">How it works</a>.</p></div>
        <div class="rule-ex"><div class="tape-wrap">${tape70}<p class="fine">Each tick is a day from day 0. Tall amber ticks are days a message was sent; the last is shown below.</p></div>${phone(bubble('in', r3sell.text, r3sell.text_sw, `Day ${r3sell.day}`), { sub: 'Example, engine draft wording', cls: 'ph-sm', label: 'Example text message for rule 3' })}</div>
      </li>
    </ol>
  </div>
</section>

<section class="sec panel know" id="know" aria-labelledby="h-know">
  <div class="wrap">
    ${mark(7, 'What we know')}
    <h2 id="h-know">What we know, and what we do not.</h2>
    <p class="know-lede">Every number in the engine carries a label. They are listed on <a href="/how-it-works#params">How it works</a>, with their sources on <a href="/sources">Sources</a>. The limits, once:</p>
    <div class="limits">
      <ul>
        <li><strong>The pilot has not run.</strong> Nothing on this site is a result. No farmer has been enrolled; the test bot answers whoever messages it, on simulated weather.</li>
        <li><strong>13.5% is the limit for sale, not a year&rsquo;s guarantee.</strong> It is the East African standard limit ${ref(3)}. Arkansas guidance for keeping corn for a full year is 12% ${ref(6)}. A countdown of 365 days means 365 or more at the weather entered.</li>
        <li><strong>The storage clock starts at the first test, not at harvest.</strong> The source counts from harvest, so grain that sat wet before its first test has already used part of its life.</li>
        <li><strong>The tables are for US corn.</strong> Kenyan white maize has a different moisture curve ${ref(36)}, and we have not validated against it. The moisture table reads about 0.6&ndash;0.7 points wetter than measured maize points ${ref(19)}, which errs toward a false alarm. Below 15% moisture the storage-days figure is extended past its table and flagged.</li>
        <li><strong>The salt test is a coarse screen at about 15%</strong> ${ref(18)}. It asks for non-iodised salt, and Kenyan table salt is normally iodised. We do not know yet what that does.</li>
        <li><strong>Two simplifications.</strong> Daily air temperature stands in for grain temperature. Insects are not modelled: the engine sends one reminder at week 7 and points to hermetic bags.</li>
        <li><strong>Status, ${'12 October 2026'}.</strong> The engine exists as a tested Python reference. A Telegram test bot (@HarvestlyBot) answers with simulated weather; it replies only after you message it and sends no unprompted alerts. The Oracle version, SMS, USSD and the dashboard are planned, not built.</li>
      </ul>
    </div>
  </div>
</section>

<section class="sec next" id="gate-sec" aria-labelledby="h-next">
  <div class="wrap">
    ${mark(8, 'Where it goes next')}
    <h2 id="h-next">The warehouse gate.</h2>
    <div class="prose-wide">
      <p>13.5% is also the intake line used by the National Cereals and Produce Board (NCPB) and the warehouse receipt system ${ref(3, 17)}. Depots with driers may accept wetter grain and dry it, so the line matters most for grain that goes to a depot without one. Grain that leaves the farm already measured and dry meets it before it gets there.</p>
      <p>A pilot is proposed for Trans Nzoia, October 2026 to January 2027. It is a plan, not a pledge, and it has not started. <a class="textlink" href="/pilot">Read the pilot plan</a></p>
    </div>
  </div>
</section>

<section class="sec panel partners" id="partners" aria-labelledby="h-partners">
  <div class="wrap">
    ${mark(9, 'For partners')}
    <h2 id="h-partners">For co-operatives, extension officers, counties and warehouses.</h2>
    <p class="prose-wide">Harvestly is designed to run inside the services you already use, as a post-harvest module: a ward, a batch and a reading go in; a message code and the text, in English or Kiswahili, come out. What each of you would get is on the Partners page.</p>
    <p class="actions">${formLink('partner')}<a class="textlink" href="/partners">What a partnership could look like</a></p>
  </div>
</section>
`;

export default page({
  path: '/',
  title: 'Harvestly: the sack doesn’t tell you',
  desc: 'Maize in a sack looks the same dry or ruined. Harvestly is a prototype that turns a test and the forecast into a storage-day countdown, planned for SMS.',
  og: 'home',
  ogAlt: `Harvestly. An example countdown of ${AFTER} days left, on simulated weather.`,
  cls: 'home',
  scripts: ['main.js'],
  body,
});

