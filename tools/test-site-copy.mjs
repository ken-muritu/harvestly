// Copy and config checks on the built site (round 4): region wording, no commitment wording, one repeat rule, safe examples.
import fs from 'node:fs';
import assert from 'node:assert/strict';
const R = (f) => fs.readFileSync(new URL('../site/' + f, import.meta.url), 'utf8');
const T = (name, f) => { f(); console.log('ok', name); };
const priv = R('privacy.html'), how = R('how-it-works.html'), partners = R('partners.html'), home = R('index.html');
const vj = JSON.parse(R('vercel.json'));
T('P4-01 the function region is pinned and /privacy states it exactly', () => {
  assert.deepEqual(vj.regions, ['iad1']);
  assert.match(priv, /Washington, D\.C\. in the United States \(Vercel region iad1\)/);
  assert.ok(!/United States or India/.test(priv));
});
T('P4-02 no commitment wording on /privacy', () => {
  for (const bad of [/We will delete/i, /will change first/i, /we will (?:reply|message|send|alert)/i]) assert.ok(!bad.test(priv), String(bad));
  assert.match(priv, /Ask for your answers to be deleted/); assert.match(priv, /would change first/);
});
T('F4-02 the phone number has a stated purpose and the reply-to rule is accurate', () => {
  assert.match(priv, /phone number or email if you give one \(only so the team can reply to you\)/);
  assert.match(priv, /email box of the partner or team form/);
  assert.ok(!/If you gave an email address, it is set as the reply address/.test(priv));
});
T('S4-04 one repeat rule on how-it-works, naming the codes', () => {
  assert.match(how, /at most four times per test result/); assert.match(how, /The fourth says it is the last reminder/);
  assert.ok(!/at most twice per test result/.test(how)); assert.ok(!/repeats every 3 days \(sealed bags: 7\) and at most twice/.test(how));
  assert.match(how, /HIGH_ALERT_MAX/);
  assert.match(home, /at most four times, and the fourth says it is the last reminder/);
});
T('S4-06 partners h1 keeps co-operatives in one piece', () => assert.match(partners, /<h1>For <span class="nb">co-operatives<\/span>,/));
T('S4-08 the printed story says it shows day 0 only', () => assert.match(home, /class="print-only">The printed page shows the first day/));
T('E4-01/C4-01 site SMS texts: examples are above the limit and the Swahili join example is a Swahili batch', () => {
  const data = fs.readFileSync(new URL('../site/assets/js/data.js', import.meta.url), 'utf8');
  assert.ok(!/METER 13\.5|MITA 13\.5/.test(data));
  assert.match(data, /SAJILI KITALE MAGUNIA 12/); assert.ok(!/SAJILI KITALE SACK/.test(data));
  assert.match(data, /e\.g\. METER 14\.2 \(your own reading\)/);
});
T('D3-06 tools/audit.mjs does not contain the former company name', () => {
  const former = String.fromCharCode(100, 97, 101, 108, 117, 115);
  for (const f of ['audit.mjs', 'test-site-copy.mjs', 'test-webhook.mjs', 'test-chart.mjs']) assert.ok(!fs.readFileSync(new URL('./' + f, import.meta.url), 'utf8').toLowerCase().includes(former), f);
});

// ---- round 5 ----
const src = fs.readFileSync(new URL('./site-src/refs.mjs', import.meta.url), 'utf8'), prm = fs.readFileSync(new URL('./site-src/params.mjs', import.meta.url), 'utf8');
const css = R('assets/css/style.css'), calcjs = R('assets/js/calc.js'), sources = R('sources.html'), pilot = R('pilot.html');
T('S5-01 the limit legend swatch is dashed like the 13.5% line, and the air line is a different, dotted grey line', () => {
  assert.match(css, /\.lg-l\{[^}]*border-top:2px dashed var\(--amber\)/);
  assert.match(css, /\.c-limit,\.ml-limit\{[^}]*stroke-dasharray:5 4/);
  assert.match(css, /\.c-air\{stroke:var\(--ink2\)/);
  assert.ok(!/class="ml-limit"/.test(calcjs), 'air line must not reuse the limit class');
  assert.equal((calcjs.match(/class="c-air"/g) || []).length, 2);
});
T('K5-02 the salt line is not labelled SOURCE and says it is unverified', () => {
  assert.match(prm, /name: 'Salt test line'[^\n]*tag: 'UNVALIDATED'[^\n]*Secondary, unverified/);
  assert.ok(!/glass/.test(prm + home + how + sources));
  assert.match(fs.readFileSync(new URL('../engine/harvestly_engine.py', import.meta.url), 'utf8'), /SALT_LINE_MC = 15\.0\s+# SECONDARY, UNVERIFIED/);
  assert.match(sources, /unverified rule of thumb/);
});
T('K5-03 ref 8 says the full report was read via the APEDA copy', () => {
  assert.match(sources, /Read in full via the APEDA copy; the usda\.gov original was unreachable/);
  assert.ok(!/The USDA site returned/.test(sources));
});
T('K5-04 ref 31 title does not name the county', () => {
  assert.ok(!/randomised trial, Nakuru County/.test(sources));
  assert.match(sources, /\(randomised trial\)\. AgEcon/);
});
T('K5-05 ref 37 separates the verified FAQ from the unconfirmed Notice number', () => {
  assert.ok(!/Legal Notice 265 of 2021\./.test(sources));
  assert.match(sources, /Notice number is unconfirmed|Legal Notice number is unconfirmed/);
  assert.match(sources, /Not confirmed: the Regulations/);
});
T('N5-01/N5-03/N5-06 consistent example, no unsupported privacy claims, hedged drought line', () => {
  assert.ok(!/METER 13\.2/.test(partners));
  assert.ok(!/hosted in the EU|France, EU|sections 48 to 50|kept only as long as needed/.test(priv));
  assert.match(priv, /not yet written retention rules/);
  assert.match(pilot, /so each sack is likely to be worth more/);
});

// ---- round 7: NASA data (research/nasa-due-diligence.md, tests 6 to 9) ----
const nasaRoot = new URL('../site/', import.meta.url).pathname;
const priv7 = R('privacy.html'), pilot7 = R('pilot.html'), src7 = R('sources.html'), home7 = R('index.html');
const calc7 = R('assets/js/calc.js'), hero7 = R('assets/js/hero.js'), api7 = R('api/recent-weather.js');
const BANNED7 = /\b(accurate|real-time|measured|forecast|NASA says)\b|\blive\b/i;
T('N7-01 CSP stays connect-src self / img-src self data:, and no page or script loads a nasa.gov host at runtime', () => {
  const csp = vj.headers[0].headers.find((h) => h.key === 'Content-Security-Policy').value;
  assert.match(csp, /img-src 'self' data:;/); assert.match(csp, /connect-src 'self';/); assert.ok(!/nasa/i.test(csp));
  for (const f of ['index.html', 'pilot.html', 'sources.html', 'privacy.html', 'assets/js/calc.js', 'assets/js/main.js', 'assets/js/hero.js']) {
    const txt = R(f);
    assert.ok(!/(src|action)=["']https?:\/\/[^"']*nasa\.gov/i.test(txt), f);
    if (f.endsWith('.js')) assert.ok(!/nasa\.gov/i.test(txt), f);
  }
  assert.match(calc7, /fetch\('\/api\/recent-weather\?ward=Kitale'/);
  assert.ok(vj.functions['api/recent-weather.js'] && vj.regions.length === 1);
  assert.ok(!vj.headers.some((h) => h.source === '/api/(.*)'), 'the proxy must be able to set its own Cache-Control');
});
T('N7-02 the calculator control is optional, fires only on a tap, labelled as an estimate with its date, in both languages, fills nothing, and uses no banned word', () => {
  assert.match(home7, /id="wx-btn"[^>]*><span data-l="en">Show recent weather near Kitale<\/span><span data-l="sw" lang="sw">Onyesha hali ya hewa ya karibuni karibu na Kitale<\/span>/);
  assert.match(calc7, /Recent weather near Kitale \(NASA satellite\/model estimate, to \$\{d\}\): about \$\{t\} C, humidity \$\{rh\}%, \$\{rain\} mm rain\. This is an area estimate, not a measurement at your store\./);
  assert.match(calc7, /Hali ya hewa ya karibuni karibu na Kitale \(makadirio ya satelaiti\/modeli ya NASA, hadi \$\{d\}\): takriban \$\{t\} C, unyevu \$\{rh\}%, mvua \$\{rain\} mm\. Ni makadirio ya eneo, si kipimo cha ghala lako\./);
  const note = calc7.slice(calc7.indexOf('const WX_NOTE'), calc7.indexOf('async function showRecentWeather'));
  assert.ok(!BANNED7.test(note), 'banned word in the note');
  assert.ok(!/forecast|on your farm|your weather/i.test(note));
  const fn = calc7.slice(calc7.indexOf('async function showRecentWeather'));
  assert.equal((calc7.match(/fetch\(/g) || []).length, 1); assert.ok(fn.includes("fetch('/api/recent-weather?ward=Kitale'"), 'the only fetch sits inside the tap handler');
  assert.match(calc7, /\$\('wx-btn'\)\?\.addEventListener\('click', showRecentWeather\)/);
  assert.ok(!/\$\('(temp|rh|mc)'\)\.value\s*=/.test(fn), 'the recent weather never fills the calculator inputs');
  assert.ok(!/id="wx-use" hidden/.test(home7));                                  // the button is always there; nothing is requested until it is tapped
  assert.match(calc7, /catch \{ \/\* offline/);
});
T('N7-03 the proxy: allowlist, rounded centroids, timeout, no key, no dependencies', () => {
  assert.match(api7, /AbortController/); assert.ok(!/require\((?!'node:crypto')/.test(api7)); assert.ok(!/NASA_API_KEY|api_key|process\.env/.test(api7));
  assert.match(api7, /WARDS = \{/);
});
T('N7-04 /sources carries both NASA acknowledgements word for word, labelled verified, and no NASA logo file exists', () => {
  assert.match(src7, /The data was obtained from National Aeronautics and Space Administration \(NASA\) Langley Research Center's Prediction Of Worldwide Energy Resources \(POWER\) project funded through the NASA Earth Science Division\./);
  assert.match(src7, /We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services \(GIBS\), part of NASA's Earth Science Data and Information System \(ESDIS\)\./);
  assert.match(src7, /id="r38"[\s\S]*?tag-verified[\s\S]*?id="r39"[\s\S]*?tag-verified/);
  assert.match(src7, /Not endorsed by NASA/);
  const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => e.isDirectory() ? (e.name === 'node_modules' || e.name === '.vercel' ? [] : walk(d + e.name + '/')) : [d + e.name]);
  for (const f of [...walk(nasaRoot), ...walk(new URL('../brand/', import.meta.url).pathname)]) assert.ok(!/nasa|meatball/i.test(f.split('/').pop()), f);
});
T('N7-05 /pilot has one dated MODIS image with alt text, size, honest caption and the credit', () => {
  assert.equal((pilot7.match(/<figure class="sat">/g) || []).length, 1);
  assert.match(pilot7, /<img src="\/assets\/img\/trans-nzoia-modis-2025-12-20\.jpg" width="800" height="800"[^>]* alt="Satellite view of the Trans Nzoia area from NASA MODIS Terra, true colour, 20 December 2025\./);
  assert.match(pilot7, /Satellite view of the Trans Nzoia area, NASA MODIS Terra true colour, 20 December 2025\. About 88 km across; individual farms are not visible\./);
  assert.match(pilot7, /not a picture of crop conditions/); assert.match(pilot7, /Imagery: NASA Worldview \/ GIBS \(MODIS Terra\)\./);
  const img = fs.readFileSync(nasaRoot + 'assets/img/trans-nzoia-modis-2025-12-20.jpg');
  assert.ok(img.length < 150 * 1024 && img.length > 10 * 1024); assert.equal(img[0], 0xff); assert.equal(img[1], 0xd8);
  assert.ok(!BANNED7.test(pilot7.match(/<figure class="sat">[\s\S]*?<\/figure>/)[0]));
});
T('N7-06 /privacy says only a rounded ward centre goes to NASA, from the site function and from the bot', () => {
  assert.match(priv7, /NASA POWER for the weather at a rounded ward centre/); assert.match(priv7, /sends NASA nothing about you/);
  assert.match(priv7, /Nothing about weather is requested when a page loads/); assert.match(priv7, /Only if you tap the optional/); assert.match(priv7, /salted hash of the caller&rsquo;s address/); assert.match(priv7, /does not store or log the address itself/);
  assert.match(priv7, /\/weather asks NASA POWER, from our server/); assert.match(priv7, /no chat id, message or other chat data/);
  assert.ok(!/will never|guarantee/i.test(priv7));
});
T('E7-01 the Kiswahili hero follows the toggle: the dial unit and the Pause/Play label', () => {
  assert.match(home7, /<span class="unit"><span data-l="en">days left<\/span><span data-l="sw" lang="sw">siku zilizobaki<\/span><\/span>/);
  assert.match(hero7, /Simamisha/); assert.match(hero7, /Cheza/); assert.ok(!/textContent = paused/.test(hero7));
});
