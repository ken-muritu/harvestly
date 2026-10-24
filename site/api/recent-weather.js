'use strict';
const crypto = require('node:crypto');
// Recent weather for ONE example ward, from NASA POWER daily point data (T2M, RH2M, PRECTOTCORR, community AG, local solar time).
// Per research/nasa-due-diligence.md: server-side only (the page CSP stays connect-src 'self'), a fixed allowlist of example
// wards with centroids rounded to 1 decimal (no free coordinates, nothing about the visitor is forwarded or stored), -999 days
// dropped, cached, one upstream request per grid cell per few hours, stale data kept for a week, never an exception.
// The values are an area estimate (a POWER cell is about 55 km by 70 km), 3 or more days old, and never a measurement.
// No dependencies beyond node:crypto, no API key (POWER needs none). Caches and caps live in memory, so they are per function instance.
// The caller's IP address is never stored or logged: it is turned into a short hash with a random per-instance salt (kept only in
// memory, lost when the instance ends) and only that hash is used as the rate-limit key, for at most one minute.

// Example wards, not the pilot directory. [lat, lon] rounded to 1 decimal.
const WARDS = {
  kitale: ['Kitale', 1.0, 35.0], eldoret: ['Eldoret', 0.5, 35.3], webuye: ['Webuye', 0.6, 34.8],
  bungoma: ['Bungoma', 0.6, 34.6], kapsabet: ['Kapsabet', 0.2, 35.1], kakamega: ['Kakamega', 0.3, 34.8],
};
const POWER = 'https://power.larc.nasa.gov/api/temporal/daily/point';
const FRESH_MS = 6 * 3600 * 1000;          // one upstream request per cell per 6 hours
const RETRY_MS = 15 * 60 * 1000;           // after a failure, do not ask again for 15 minutes
const STALE_DAYS = 7;                      // newest observed day older than this: hide, never show
const TIMEOUT_MS = 6000;
const WINDOW_DAYS = 14;
const KEEP = 7;                            // observed days returned
const PER_IP_PER_MIN = 12, TOTAL_PER_MIN = 120;

const cache = new Map();                   // cell key -> { at, days, version } | { failedAt }
const inflight = new Map();                // cell key -> Promise (concurrent callers share one request)
const SALT = crypto.randomBytes(16);       // per instance, memory only: the hash below cannot be linked across instances or restarts
const hits = new Map();                    // salted-hash caller -> timestamps within the last minute (memory only, never logged)
const who = (ip) => crypto.createHash('sha256').update(SALT).update(String(ip)).digest('hex').slice(0, 16);
let total = [];
let clock = () => Date.now();

const cellKey = (lat, lon) => `${Math.round(lat / 0.5)}:${Math.round(lon / 0.625)}`;   // POWER grid: 0.5 deg by 0.625 deg
const ymd = (ms) => new Date(ms).toISOString().slice(0, 10);
const compact = (s) => s.replace(/-/g, '');

/** POWER JSON -> [{date,t,rh,rain}] oldest first. A day missing ANY of the three values (-999, null, absurd) is dropped. */
function parse(json) {
  const p = json && json.properties && json.properties.parameter;
  if (!p || !p.T2M || !p.RH2M || !p.PRECTOTCORR) return null;
  const fill = Number(json.header && json.header.fill_value);
  const bad = (v) => typeof v !== 'number' || !Number.isFinite(v) || v === -999 || (Number.isFinite(fill) && v === fill);
  const out = [];
  for (const d of Object.keys(p.T2M).sort()) {
    const t = p.T2M[d], rh = p.RH2M[d], rain = p.PRECTOTCORR[d];
    if (!/^\d{8}$/.test(d) || bad(t) || bad(rh) || bad(rain)) continue;
    if (t < -60 || t > 60 || rh < 0 || rh > 100 || rain < 0 || rain > 1000) continue;
    out.push({ date: `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6)}`, t: Math.round(t * 10) / 10, rh: Math.round(rh), rain: Math.round(rain * 10) / 10 });
  }
  return out;
}

async function fetchCell(lat, lon, now) {
  const url = `${POWER}?parameters=T2M,RH2M,PRECTOTCORR&community=AG&latitude=${lat.toFixed(1)}&longitude=${lon.toFixed(1)}` +
    `&start=${compact(ymd(now - WINDOW_DAYS * 86400000))}&end=${compact(ymd(now))}&format=JSON&time-standard=LST`;
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TIMEOUT_MS);
  try {
    const r = await globalThis.fetch(url, { signal: ctl.signal, headers: { accept: 'application/json', 'user-agent': 'harvestly-site (+https://harvestly-roan.vercel.app)' } });
    if (!r || !r.ok) return null;                       // 429, 5xx: the stale copy (if any) is used by the caller
    const json = await r.json();
    const days = parse(json);
    if (!days) return null;
    return { at: now, days, version: String(json.header && json.header.api && json.header.api.version || '') };
  } catch { return null; } finally { clearTimeout(timer); }
}

/** Newest data for a cell: fresh cache, else one upstream request, else the stale copy, else null. */
async function getCell(lat, lon) {
  const key = cellKey(lat, lon), now = clock(), c = cache.get(key);
  if (c && c.days && now - c.at < FRESH_MS) return c;
  if (c && c.failedAt && now - c.failedAt < RETRY_MS) return c.days ? c : null;
  if (!inflight.has(key)) {
    inflight.set(key, fetchCell(lat, lon, now).then((fresh) => {
      if (fresh && fresh.days.length) cache.set(key, fresh);
      else cache.set(key, { ...(c && c.days ? c : {}), failedAt: now });
      return fresh && fresh.days.length ? fresh : (c && c.days ? c : null);
    }).finally(() => inflight.delete(key)));
  }
  return inflight.get(key);
}

function limited(key, now) {
  total = total.filter((t) => now - t < 60000);
  if (total.length >= TOTAL_PER_MIN) return true;
  const h = (hits.get(key) || []).filter((t) => now - t < 60000);
  if (h.length >= PER_IP_PER_MIN) { hits.set(key, h); return true; }
  h.push(now); hits.set(key, h); total.push(now);
  if (hits.size > 500) hits.delete(hits.keys().next().value);
  return false;
}

const fail = (res, code, error, extra = {}) => {
  res.setHeader('Cache-Control', 'no-store');
  return res.status(code).json({ error, ...extra });
};
// NASA down, throttled or stale: an ordinary 200 with an error field (the control is optional, so the browser logs nothing
// and the calculator simply keeps its manual inputs). Cached for a minute at the edge so a bad spell does not hit NASA.
const unavailable = (res) => { res.setHeader('Cache-Control', 'public, s-maxage=60'); return res.status(200).json({ error: 'unavailable' }); };

module.exports = async function handler(req, res) {
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  if (req.method !== 'GET' && req.method !== 'HEAD') { res.setHeader('Allow', 'GET, HEAD'); return fail(res, 405, 'method'); }
  const now = clock();
  const ip = String((req.headers && (req.headers['x-forwarded-for'] || req.headers['x-real-ip'])) || '').split(',')[0].trim().slice(0, 64);
  if (limited(who(ip || 'none'), now)) { res.setHeader('Retry-After', '60'); return fail(res, 429, 'rate'); }

  let ward = '';
  try { ward = new URL(req.url || '/', 'http://x').searchParams.get('ward') || ''; } catch { ward = ''; }
  const k = ward.trim().toLowerCase();
  const w = ward.length <= 20 && Object.hasOwn(WARDS, k) ? WARDS[k] : null;     // own keys only: 'constructor', '__proto__' are unknown wards
  if (!w) return fail(res, 400, 'unknown_ward', { wards: Object.values(WARDS).map((x) => x[0]) });

  try {
    const data = await getCell(w[1], w[2]);
    const days = data ? data.days.slice(-KEEP) : [];
    const newest = days.length ? days[days.length - 1].date : null;
    if (!newest || now - Date.parse(newest + 'T00:00:00Z') > STALE_DAYS * 86400000) return unavailable(res);
    res.setHeader('Cache-Control', 'public, s-maxage=21600, stale-while-revalidate=86400');
    return res.status(200).json({ ward: w[0], days, asOf: newest, source: 'NASA POWER', version: data.version });
  } catch { return unavailable(res); }
};
module.exports._parse = parse;
module.exports._cellKey = cellKey;
module.exports._WARDS = WARDS;
module.exports._hitKeys = () => [...hits.keys()];
module.exports._setClock = (f) => { clock = f || (() => Date.now()); };
module.exports._reset = () => { cache.clear(); inflight.clear(); hits.clear(); total = []; clock = () => Date.now(); };
