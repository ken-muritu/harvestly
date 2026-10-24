// Link checker for every external reference on the site.
//   node tools/check-links.mjs [--json out.json]
// Reads the built site/*.html (so run tools/build-site.mjs first), collects every http(s) href that leaves the site,
// requests each once (GET, browser user agent, redirects followed, 20 s timeout) and prints a status per URL:
//   ok        2xx (final URL shown when it redirected)
//   blocked   401/403/429/5xx or a TLS/connection error: the publisher refuses bots or is unreachable from here.
//             These are NOT counted as broken, and are listed so a person can open them in a browser.
//   BROKEN    404/410 or a DNS failure: exits 1.
// Also checks that every /sources#rN anchor used on a page exists on /sources.
import fs from 'node:fs';
import https from 'node:https';

const SITE = new URL('../site/', import.meta.url).pathname;
const UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36';
const files = fs.readdirSync(SITE).filter((f) => f.endsWith('.html'));
const urls = new Map();   // url -> pages that use it
for (const f of files) {
  const html = fs.readFileSync(SITE + f, 'utf8');
  for (const m of html.matchAll(/href="(https?:\/\/[^"]+)"/g)) {
    const u = m[1].replace(/&amp;/g, '&');
    if (!urls.has(u)) urls.set(u, new Set());
    urls.get(u).add(f);
  }
}
// Internal anchors to /sources#rN
const srcHtml = fs.readFileSync(SITE + 'sources.html', 'utf8');
const ids = new Set([...srcHtml.matchAll(/ id="(r\d+)"/g)].map((m) => m[1]));
let badAnchors = 0;
for (const f of files) {
  for (const m of fs.readFileSync(SITE + f, 'utf8').matchAll(/href="\/sources#(r\d+)"/g)) {
    if (!ids.has(m[1])) { console.log(`BROKEN anchor /sources#${m[1]} used on ${f}`); badAnchors++; }
  }
}

const agent = new https.Agent({ keepAlive: false });
async function probe(url) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 20000);
  try {
    const r = await fetch(url, { redirect: 'follow', signal: ctl.signal, headers: { 'user-agent': UA, accept: 'text/html,application/pdf,*/*' } });
    clearTimeout(t);
    try { await r.body?.cancel(); } catch { /* ignore */ }
    const moved = r.url !== url ? ` -> ${r.url}` : '';
    if (r.ok) return ['ok', r.status, moved];
    if ([404, 410].includes(r.status)) return ['BROKEN', r.status, moved];
    return ['blocked', r.status, moved];
  } catch (e) {
    clearTimeout(t);
    const code = e.cause?.code || e.name;
    if (['ENOTFOUND', 'EAI_AGAIN'].includes(code)) return ['BROKEN', code, ''];
    return ['blocked', code, ''];
  }
}

const list = [...urls.keys()];
const results = [];
const queue = [...list];
await Promise.all(Array.from({ length: 6 }, async () => {
  while (queue.length) {
    const u = queue.shift();
    const [cls, code, moved] = await probe(u);
    results.push({ url: u, cls, code, moved, pages: [...urls.get(u)] });
  }
}));
results.sort((a, b) => list.indexOf(a.url) - list.indexOf(b.url));
for (const r of results) console.log(`${r.cls.padEnd(7)} ${String(r.code).padEnd(12)} ${r.url}${r.moved}`);
const n = (c) => results.filter((r) => r.cls === c).length;
console.log(`\n${results.length} external URLs: ${n('ok')} ok, ${n('blocked')} blocked or unreachable from this machine (open by hand), ${n('BROKEN')} broken; ${badAnchors} broken internal anchors`);
const j = process.argv.indexOf('--json');
if (j > -1) fs.writeFileSync(process.argv[j + 1], JSON.stringify(results, null, 1));
process.exit(n('BROKEN') + badAnchors ? 1 : 0);
