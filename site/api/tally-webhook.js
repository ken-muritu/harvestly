'use strict';
// Receives Tally FORM_RESPONSE webhooks, verifies the signature, and sends ONE email through Brevo:
// the team notification to the project inbox. Nothing is ever sent to the respondent.
// If the respondent gave an address in the form's email field (type INPUT_EMAIL, never a free-text field), it becomes
// the Reply-To, so the team can answer. If Brevo rejects the message with that Reply-To, it is sent again without it.
// Secrets come only from environment variables. Answers and addresses are never logged.
// Caps and dedupe live in memory, so they are per function instance (best effort, not a global limit).
const crypto = require('node:crypto');

const INBOX = 'harvestlyafrica@gmail.com';
const seen = new Map(); // eventId -> time (claimed before sending, released if sending fails)
const MAX_AGE_MS = 2 * 24 * 3600 * 1000; // older than this is treated as a replay (Tally's last retry is about a day after the first try)
const MAX_FUTURE_MS = 10 * 60 * 1000; // clock skew allowed between Tally and this function
const PER_FORM_PER_MINUTE = 6;
const PER_DAY = 100;
const hits = new Map(); // form key -> timestamps within the last minute
let day = { key: '', n: 0 };

/** Returns null when the request may go on (and a token for its cap slot), or true when a cap is reached. */
function overCap(form, now) {
  const dk = new Date(now).toISOString().slice(0, 10);
  if (day.key !== dk) day = { key: dk, n: 0 };
  if (day.n >= PER_DAY) return true;
  const recent = (hits.get(form) || []).filter((t) => now - t < 60000);
  if (recent.length >= PER_FORM_PER_MINUTE) { hits.set(form, recent); return true; }
  recent.push(now); hits.set(form, recent); day.n += 1;
  return { form, now, dk };
}
/** Gives back the cap slot of a send that did not go out, so a failed send does not use up the daily cap (W4-02).
 *  N5-10: it gives back THIS request's timestamp (not whichever is last), and the daily count only if the day has not
 *  rolled over since the slot was taken. */
function uncap(slot) {
  if (!slot || slot === true) return;
  const r = hits.get(slot.form);
  if (r) { const i = r.indexOf(slot.now); if (i >= 0) r.splice(i, 1); }
  if (day.key === slot.dk && day.n > 0) day.n -= 1;
}

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const oneLine = (s) => String(s).replace(/[\u0000-\u001f\u007f]+/g, ' ').slice(0, 200);
const clip = (s) => (String(s).length > 4000 ? String(s).slice(0, 4000) + ' [cut]' : String(s));

function readRaw(req) {
  return new Promise((resolve, reject) => {
    const chunks = []; let n = 0;
    // N5-10: on an oversized body stop collecting but do not destroy the socket here, so the 413 can still be sent;
    // the handler closes the request after the response has finished.
    let big = false;
    req.on('data', (c) => { if (big) return; n += c.length; if (n > 256 * 1024) { big = true; chunks.length = 0; reject(new Error('too large')); } else chunks.push(c); });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

function validSignature(raw, header, secret) {
  if (!header || !secret) return false;
  const expected = crypto.createHmac('sha256', secret).update(raw).digest();
  let given;
  try { given = Buffer.from(String(header), 'base64'); } catch { return false; }
  return given.length === expected.length && crypto.timingSafeEqual(given, expected);
}

const show = (v) => {
  if (v == null || v === '') return '(blank)';
  if (Array.isArray(v)) return v.map(show).join(', ');
  return String(v);
};

/** Turns one Tally field into readable text (choice fields carry ids; the options list maps them to text). */
function fieldValue(f) {
  const v = f.value;
  if (Array.isArray(v) && Array.isArray(f.options)) {
    return v.map((id) => (f.options.find((o) => o.id === id) || {}).text || id).join(', ');
  }
  return show(v);
}

// The Reply-To comes only from the form's designated email field (type INPUT_EMAIL), first one only, and must be exactly
// one plain address: no list, no display name, no brackets, no quotes, no spaces (W4-01).
const EMAIL_RE = /^[A-Za-z0-9.!#$%&'*+\/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$/;
function findEmail(fields) {
  const f = fields.find((x) => x && x.type === 'INPUT_EMAIL' && typeof x.value === 'string' && x.value.trim() !== '');
  if (!f) return null;
  const v = f.value.trim();
  return v.length <= 200 && EMAIL_RE.test(v) && !v.includes('..') && !v.startsWith('.') && !v.split('@')[0].endsWith('.') ? v : null;
}

async function brevo(payload) {
  const r = await fetch('https://api.brevo.com/v3/smtp/email', {
    method: 'POST',
    headers: { 'api-key': process.env.BREVO_API_KEY, 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(8000),
  });
  return r.ok;
}

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'POST') { res.setHeader('Allow', 'POST'); return res.status(405).json({ ok: false }); }
  let raw;
  try { raw = await readRaw(req); } catch {
    res.setHeader('Connection', 'close');
    if (typeof res.once === 'function') res.once('finish', () => { try { req.destroy(); } catch { /* already closed */ } });
    return res.status(413).json({ ok: false });
  }
  if (!validSignature(raw, req.headers['tally-signature'], process.env.TALLY_SIGNING_SECRET)) return res.status(401).json({ ok: false });

  let evt;
  try { evt = JSON.parse(raw.toString('utf8')); } catch { return res.status(400).json({ ok: false }); }
  const data = evt && typeof evt === 'object' ? evt.data : null;
  const fields = data && Array.isArray(data.fields) ? data.fields : null;
  if (!evt || evt.eventType !== 'FORM_RESPONSE' || !fields) return res.status(400).json({ ok: false });

  const now = Date.now();
  const created = Date.parse(evt.createdAt || data.createdAt || '');
  if (!Number.isFinite(created)) return res.status(400).json({ ok: false }); // no timestamp, no replay window: refuse (W4-02)
  if (created - now > MAX_FUTURE_MS) return res.status(400).json({ ok: false }); // N5-10: a timestamp from the future is not a replay window either
  if (now - created > MAX_AGE_MS) return res.status(200).json({ ok: true, stale: true });

  // Previews carry the same variables as production; only production may send real mail.
  if (process.env.VERCEL_ENV && process.env.VERCEL_ENV !== 'production') return res.status(200).json({ ok: true, skipped: 'not production' });

  const id = String(evt.eventId || data.responseId || '');
  if (id && seen.has(id)) return res.status(200).json({ ok: true, duplicate: true });

  const sender = { name: process.env.BREVO_SENDER_NAME || 'Harvestly', email: process.env.BREVO_SENDER_EMAIL };
  if (!process.env.BREVO_API_KEY || !sender.email) { console.error('tally-webhook: mail not configured'); return res.status(500).json({ ok: false }); }

  const slot = overCap(String(data.formId || data.formName || 'form'), now);
  if (slot === true) { res.setHeader('Retry-After', '3600'); return res.status(429).json({ ok: false }); }
  if (id) { seen.set(id, now); if (seen.size > 500) seen.delete(seen.keys().next().value); } // claim before the await so concurrent duplicates do not both send

  const formName = oneLine(data.formName || 'Harvestly form');
  // The consent tick-boxes carry no information for the team; skip the per-option CHECKBOX rows.
  const rows = fields.filter((f) => f && f.label && f.type !== 'CHECKBOX').map((f) => [oneLine(f.label), clip(fieldValue(f))]);
  const text = `New answer to "${formName}"\n\n` + rows.map(([k, v]) => `${k}\n${v}\n`).join('\n');
  const html = `<p>New answer to <b>${esc(formName)}</b></p>` + rows.map(([k, v]) => `<p><b>${esc(k)}</b><br>${esc(v).replace(/\n/g, '<br>')}</p>`).join('');
  const replyTo = findEmail(fields);

  const mail = { sender, to: [{ email: INBOX }], subject: `Harvestly form: ${formName}`, textContent: text, htmlContent: html };
  let ok;
  try { ok = await brevo(replyTo ? { ...mail, replyTo: { email: replyTo } } : mail); } catch { ok = false; }
  if (!ok && replyTo) {
    // W4-01: a rejected Reply-To must never lose the notification. Send once more without it.
    console.error('tally-webhook: retrying without Reply-To');
    try { ok = await brevo(mail); } catch { ok = false; }
  }
  if (!ok) { if (id) seen.delete(id); uncap(slot); console.error('tally-webhook: notification not accepted by Brevo'); return res.status(502).json({ ok: false }); }
  return res.status(200).json({ ok: true });
};
module.exports._findEmail = findEmail;
module.exports._cap = { overCap, uncap, day: () => ({ ...day }) };
module.exports._reset = () => { seen.clear(); hits.clear(); day = { key: '', n: 0 }; };
