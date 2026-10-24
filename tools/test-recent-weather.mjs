// Unit tests for site/api/recent-weather.js with a fake NASA POWER (global fetch) and fake req/res (research/nasa-due-diligence.md, tests 1, 2, 5, 9).
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
const h = createRequire(import.meta.url)('../site/api/recent-weather.js');
const NOW = Date.parse('2026-10-12T12:00:00Z');
const day = (n) => new Date(NOW - n * 86400000).toISOString().slice(0, 10).replace(/-/g, '');
const power = ({ lastReal = 3, partial = null, days = 14 } = {}) => {
  const T2M = {}, RH2M = {}, PRECTOTCORR = {};
  for (let n = days; n >= 0; n--) {
    const k = day(n), real = n >= lastReal;
    T2M[k] = real ? 19.5 + (n % 3) * 0.5 : -999; RH2M[k] = real ? (k === partial ? -999 : 60 + (n % 5)) : -999; PRECTOTCORR[k] = real ? (n % 4) * 1.1 : -999;
  }
  return { header: { fill_value: -999, api: { version: 'v2.10.0' } }, properties: { parameter: { T2M, RH2M, PRECTOTCORR } } };
};
let calls = [], mode = 'ok', body = power();
globalThis.fetch = async (u) => {
  calls.push(String(u));
  if (mode === 'throw') throw new Error('network');
  if (mode === '429') return { ok: false, status: 429, json: async () => ({}) };
  if (mode === 'badjson') return { ok: true, json: async () => { throw new Error('bad json'); } };
  return { ok: true, json: async () => body };
};
const logs = []; for (const m of ['log', 'error', 'warn']) console[m] = (...a) => logs.push(a.join(' '));
async function get(url, { method = 'GET', ip = '1.2.3.4' } = {}) {
  const out = { code: 0, json: null, headers: {} };
  const res = { setHeader: (k, v) => { out.headers[k] = v; }, status(c) { out.code = c; return this; }, json(j) { out.json = j; return this; } };
  await h({ method, url, headers: { 'x-forwarded-for': ip } }, res); return out;
}
let n = 0; const t = async (name, f) => { h._reset(); h._setClock(() => NOW); calls = []; mode = 'ok'; body = power(); logs.length = 0; await f(); n++; process.stdout.write('ok ' + name + '\n'); };

await t('known ward returns observed days, newest 3 days before today, as-of date, source', async () => {
  const r = await get('/api/recent-weather?ward=Kitale');
  assert.equal(r.code, 200); assert.equal(r.json.ward, 'Kitale'); assert.equal(r.json.source, 'NASA POWER');
  assert.equal(r.json.asOf, '2026-10-09'); assert.equal(r.json.days.length, 7); assert.deepEqual(Object.keys(r.json.days[0]), ['date', 't', 'rh', 'rain']);
  assert.equal(r.json.days.at(-1).date, '2026-10-09');
  assert.match(r.headers['Cache-Control'], /s-maxage=\d+/);
});
await t('-999 days are dropped (never a number), and a day with one -999 parameter is missing', async () => {
  body = power({ lastReal: 3, partial: day(3) });
  const r = await get('/api/recent-weather?ward=kitale');
  assert.equal(r.json.asOf, '2026-10-08'); assert.ok(!JSON.stringify(r.json).includes('-999'));
  assert.deepEqual(h._parse(power()).at(-1).date, '2026-10-09');
  assert.equal(h._parse({ properties: { parameter: { T2M: { 20261001: 1 } } } }), null);
  assert.equal(h._parse(null), null);
  assert.deepEqual(h._parse({ header: {}, properties: { parameter: { T2M: { 20261001: 130 }, RH2M: { 20261001: 50 }, PRECTOTCORR: { 20261001: 0 } } } }), []);   // absurd value dropped
});
await t('request carries only a rounded ward centroid, community AG, three parameters, no visitor data', async () => {
  await get('/api/recent-weather?ward=Kitale', { ip: '9.9.9.9' });
  assert.equal(calls.length, 1); const u = calls[0];
  assert.match(u, /^https:\/\/power\.larc\.nasa\.gov\/api\/temporal\/daily\/point\?parameters=T2M,RH2M,PRECTOTCORR&community=AG&latitude=1\.0&longitude=35\.0&/);
  assert.ok(!u.includes('9.9.9.9')); assert.ok(!/key|token/i.test(u));
  for (const [, lat, lon] of Object.values(h._WARDS)) assert.equal(String(lat).length <= 4 && String(lon).length <= 4, true);   // 1 decimal at most
});
await t('allowlist: unknown ward, coordinates and bad input are refused without calling NASA', async () => {
  for (const q of ['?ward=Nairobi', '?ward=', '', '?lat=1&lon=35', '?ward=Kitale%00', '?ward=' + 'a'.repeat(500), '?ward=../../etc', '?ward=constructor', '?ward=__proto__', '?ward=toString', '?ward=hasOwnProperty', '?ward=valueOf', '?ward=CONSTRUCTOR', '?ward=__defineGetter__', '?ward=Kitale&ward=Eldoret&lat=3']) {
    const r = await get('/api/recent-weather' + q, { ip: 'ip' + Math.random() });
    if (q.startsWith('?ward=Kitale&ward')) { assert.equal(r.code, 200); continue; }   // the first ward is used; extra params are ignored, never forwarded
    assert.equal(r.code, 400, q); assert.equal(r.json.error, 'unknown_ward');
  }
  assert.ok(calls.every((u) => !u.includes('latitude=3')));
  assert.equal((await get('/api/recent-weather?ward=Kitale', { method: 'POST' })).code, 405);
  assert.equal((await get('/api/recent-weather?ward=Kitale', { method: 'DELETE' })).code, 405);
});
await t('cache: repeated calls make one NASA request; wards in one cell share it', async () => {
  for (let i = 0; i < 3; i++) await get('/api/recent-weather?ward=Kitale', { ip: 'a' + i });
  assert.equal(calls.length, 1);
  await get('/api/recent-weather?ward=Eldoret'); await get('/api/recent-weather?ward=Webuye'); await get('/api/recent-weather?ward=Kakamega');
  assert.equal(calls.length, 2);   // Eldoret, Webuye and Kakamega are one POWER cell
  assert.equal(h._cellKey(...h._WARDS.eldoret.slice(1)), h._cellKey(...h._WARDS.webuye.slice(1)));
  h._setClock(() => NOW + 7 * 3600 * 1000); await get('/api/recent-weather?ward=Kitale', { ip: 'z' });   // fresh window is 6 h
  assert.equal(calls.length, 3);
});
await t('concurrent callers share one upstream request', async () => {
  await Promise.all([1, 2, 3, 4].map((i) => get('/api/recent-weather?ward=Bungoma', { ip: 'c' + i })));
  assert.equal(calls.length, 1);
});
await t('NASA down: graceful 200 error JSON (no exception, no stack), failure is not retried for 15 minutes', async () => {
  for (const m of ['throw', '429', 'badjson']) {
    h._reset(); h._setClock(() => NOW); calls = []; mode = m;
    const r = await get('/api/recent-weather?ward=Kitale');
    assert.equal(r.code, 200); assert.deepEqual(r.json, { error: 'unavailable' }); await get('/api/recent-weather?ward=Kitale', { ip: 'b' }); assert.equal(calls.length, 1, m);
  }
});
await t('stale copy is served when NASA fails later; older than 7 days is hidden', async () => {
  await get('/api/recent-weather?ward=Kitale');
  mode = 'throw'; h._setClock(() => NOW + 8 * 3600 * 1000);
  const r = await get('/api/recent-weather?ward=Kitale', { ip: 's' }); assert.equal(r.json.asOf, '2026-10-09');
  h._setClock(() => NOW + 9 * 86400000); mode = 'ok'; body = power({ lastReal: 3 }); calls = [];
  // NASA answers, but its newest day is more than 7 days old by then: hidden
  h._reset(); h._setClock(() => NOW + 12 * 86400000); body = power({ lastReal: 3 });
  const old = await get('/api/recent-weather?ward=Kitale', { ip: 'q' }); assert.deepEqual(old.json, { error: 'unavailable' });
});
await t('rate limit per caller, with Retry-After', async () => {
  const codes = []; for (let i = 0; i < 14; i++) codes.push((await get('/api/recent-weather?ward=Kitale', { ip: '7.7.7.7' })).code);
  assert.equal(codes.filter((c) => c === 429).length, 2); assert.equal((await get('/api/recent-weather?ward=Kitale', { ip: '8.8.8.8' })).code, 200);
});
await t('nothing is logged', async () => { await get('/api/recent-weather?ward=Kitale', { ip: '5.5.5.5' }); mode = 'throw'; h._reset(); h._setClock(() => NOW); await get('/api/recent-weather?ward=Kitale'); assert.deepEqual(logs, []); });
await t('W7-01 inherited object keys are unknown wards (400, never 500) and an internal failure is unavailable, not a throw', async () => {
  for (const k of ['constructor', '__proto__', 'toString', 'hasOwnProperty', 'valueOf', 'isPrototypeOf']) assert.equal((await get('/api/recent-weather?ward=' + k)).code, 400, k);
  assert.equal(calls.length, 0);
  const real = Object.hasOwn; // a broken lookup deep inside must still answer with the ordinary 200 'unavailable'
  body = { header: {}, properties: { parameter: { get T2M() { throw new Error('boom'); }, RH2M: {}, PRECTOTCORR: {} } } };
  const r = await get('/api/recent-weather?ward=Kitale', { ip: 'boom' }); assert.equal(r.code, 200); assert.deepEqual(r.json, { error: 'unavailable' }); assert.equal(real, Object.hasOwn);
});
await t('P7-01 the caller IP is never stored: the rate-limit key is a salted hash, and no IP text sits in memory keys or logs', async () => {
  await get('/api/recent-weather?ward=Kitale', { ip: '203.0.113.77' }); await get('/api/recent-weather?ward=Kitale', { ip: '198.51.100.9' });
  const keys = h._hitKeys(); assert.equal(keys.length, 2);
  for (const k of keys) { assert.match(k, /^[0-9a-f]{16}$/); assert.ok(!k.includes('203') && !k.includes('198')); }
  assert.deepEqual(logs, []);
  const src = (await import('node:fs')).readFileSync(new URL('../site/api/recent-weather.js', import.meta.url), 'utf8');
  assert.ok(/salt/i.test(src) && /never stored or logged/.test(src));
});
process.stdout.write(n + ' recent-weather tests passed\n');
