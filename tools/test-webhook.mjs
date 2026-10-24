// Unit tests for site/api/tally-webhook.js with a mocked Brevo (global fetch) and fake req/res.
import { createRequire } from 'node:module';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import { Readable } from 'node:stream';
const h = createRequire(import.meta.url)('../site/api/tally-webhook.js');
process.env.TALLY_SIGNING_SECRET = 'unit-secret'; process.env.BREVO_API_KEY = 'k'; process.env.BREVO_SENDER_EMAIL = 's@example.org';
process.env.VERCEL_ENV = 'production';
const sent = []; let brevoOk = true;
let rejectReplyTo = false;
globalThis.fetch = async (u, o) => { const b = JSON.parse(o.body); sent.push(b); return { ok: brevoOk && !(rejectReplyTo && b.replyTo) }; };
const logs = []; console.error = (...a) => logs.push(a.join(' '));
const sign = (b) => crypto.createHmac('sha256', 'unit-secret').update(b).digest('base64');
async function call(bodyObj, { sig, method = 'POST', raw } = {}) {
  const body = raw ?? JSON.stringify(bodyObj);
  const req = Object.assign(Readable.from([Buffer.from(body)]), { method, headers: { 'tally-signature': sig === undefined ? sign(body) : sig } });
  const out = { code: 0, json: null, headers: {} };
  const res = { setHeader: (k, v) => { out.headers[k] = v; }, status(c) { out.code = c; return this; }, json(j) { out.json = j; return this; } };
  await h(req, res); return out;
}
const evt = (over = {}, fields) => ({ eventId: 'e' + Math.random(), eventType: 'FORM_RESPONSE', createdAt: new Date().toISOString(),
  data: { formId: 'F1', formName: 'Talk "x"\r\nBcc: a@b.c', fields: fields || [
    { label: 'Email', type: 'INPUT_EMAIL', value: 'tester@example.com' },
    { label: 'Message', type: 'TEXTAREA', value: '<img src=x onerror=1> & "q"\r\nBcc: evil@x.y' },
    { label: 'Agree to this', type: 'CHECKBOXES', value: ['o1'], options: [{ id: 'o1', text: 'I agree' }] },
    { label: 'Agree to this (I agree)', type: 'CHECKBOX', value: true }] }, ...over });
let n = 0; const t = async (name, f) => { h._reset(); sent.length = 0; logs.length = 0; brevoOk = true; rejectReplyTo = false; await f(); n++; console.log('ok', name); };

await t('405 on GET', async () => assert.equal((await call({}, { method: 'GET' })).code, 405));
await t('401 bad/missing signature', async () => { assert.equal((await call(evt(), { sig: 'AAAA' })).code, 401); assert.equal((await call(evt(), { sig: '' })).code, 401); assert.equal(sent.length, 0); });
await t('signed null body is 400 not 500', async () => assert.equal((await call(null, { raw: 'null' })).code, 400));
await t('exactly one email, to the team, reply-to respondent, nothing to respondent', async () => {
  const r = await call(evt()); assert.equal(r.code, 200); assert.equal(sent.length, 1);
  const m = sent[0]; assert.deepEqual(m.to, [{ email: 'harvestlyafrica@gmail.com' }]); assert.equal(m.replyTo.email, 'tester@example.com');
  assert.ok(!m.htmlContent.includes('<img')); assert.ok(m.htmlContent.includes('&lt;img')); assert.ok(!/\r|\n/.test(m.subject));
  assert.equal((m.textContent.match(/Agree to this/g) || []).length, 1);
  assert.ok(!JSON.stringify(m).includes('tester@example.com') || m.replyTo.email); });
await t('no reply-to without email', async () => { await call(evt({}, [{ label: 'Msg', type: 'TEXTAREA', value: 'hi' }])); assert.equal(sent[0].replyTo, undefined); });
await t('dedupe, including concurrent', async () => { const e = evt(); const [a, b] = await Promise.all([call(e), call(e)]); assert.equal(sent.length, 1); assert.ok([a, b].some((x) => x.json.duplicate)); });
await t('failed send is released for retry', async () => { const e = evt(); brevoOk = false; assert.equal((await call(e)).code, 502); brevoOk = true; assert.equal((await call(e)).code, 200); assert.equal(sent.length, 3); /* failed try with Reply-To, failed retry without, then the Tally retry */ });
await t('per-form per-minute cap', async () => { const codes = []; for (let i = 0; i < 8; i++) codes.push((await call(evt())).code); assert.deepEqual(codes, [200, 200, 200, 200, 200, 200, 429, 429]); });
await t('other form not blocked by one form cap', async () => { for (let i = 0; i < 6; i++) await call(evt()); assert.equal((await call(evt({ data: { ...evt().data, formId: 'F2' } }))).code, 200); });
await t('daily cap', async () => { let last; for (let i = 0; i < 101; i++) { last = await call(evt({ data: { ...evt().data, formId: 'f' + i } })); } assert.equal(last.code, 429); });
await t('stale signed body is not sent', async () => { const r = await call(evt({ createdAt: '2020-01-01T00:00:00Z' })); assert.equal(r.json.stale, true); assert.equal(sent.length, 0); });
await t('preview does not send', async () => { process.env.VERCEL_ENV = 'preview'; const r = await call(evt()); process.env.VERCEL_ENV = 'production'; assert.equal(sent.length, 0); assert.equal(r.code, 200); });
await t('logs carry no PII', async () => { brevoOk = false; await call(evt()); assert.ok(logs.length && !logs.join().match(/tester@example|img|Bcc/)); });
await t('W4-01 reply-to only from INPUT_EMAIL, never from a text field', async () => {
  await call(evt({}, [{ label: 'Name', type: 'INPUT_TEXT', value: 'a@b.co' }, { label: 'Msg', type: 'TEXTAREA', value: 'x@y.org' }]));
  assert.equal(sent[0].replyTo, undefined); });
await t('W4-01 malformed addresses are never a reply-to', async () => {
  for (const bad of ['a,b@x.co', '(x)@a.b', 'a b@x.co', 'Bob <a@b.co>', '"a"@b.co', 'a@b', 'a@@b.co', '.a@b.co', 'a.@b.co', 'a..b@x.co', 'a@b..co', 'a@-b.co', 'x'.repeat(65) + '@b.co', 'a@b.co\r\nBcc: z@z.zz', 'a@b.co;c@d.ee'])
    assert.equal(h._findEmail([{ type: 'INPUT_EMAIL', value: bad }]), null, bad);
  for (const good of ['tester@example.com', 'a+tag@sub.example.co.ke', " o'neil@x.org "]) assert.ok(h._findEmail([{ type: 'INPUT_EMAIL', value: good }]), good); });
await t('W4-01 Brevo rejects the Reply-To: sent again without it, notification not lost', async () => {
  rejectReplyTo = true; const r = await call(evt()); assert.equal(r.code, 200); assert.equal(sent.length, 2);
  assert.ok(sent[0].replyTo); assert.equal(sent[1].replyTo, undefined); assert.deepEqual(sent[1].to, [{ email: 'harvestlyafrica@gmail.com' }]);
  assert.ok(!logs.join().includes('tester@example')); });
await t('W4-01 a retry without Reply-To that also fails is a 502 and Tally can retry', async () => {
  rejectReplyTo = true; brevoOk = false; const e = evt(); assert.equal((await call(e)).code, 502); brevoOk = true; assert.equal((await call(e)).code, 200); });
await t('W4-02 a body with no timestamp is refused (no replay window without one)', async () => {
  const e = evt(); delete e.createdAt; assert.equal((await call(e)).code, 400); assert.equal(sent.length, 0); });
await t('W4-02 a failed send does not use up the daily or per-minute cap', async () => {
  brevoOk = false; for (let i = 0; i < 8; i++) assert.equal((await call(evt())).code, 502); brevoOk = true;
  const codes = []; for (let i = 0; i < 6; i++) codes.push((await call(evt())).code); assert.deepEqual(codes, [200, 200, 200, 200, 200, 200]); });
await t('W4-02 a body older than two days is stale', async () => { const r = await call(evt({ createdAt: new Date(Date.now() - 2.1 * 864e5).toISOString() })); assert.equal(r.json.stale, true); });
await t('N5-10 a failed send gives back its own cap slot, not another request\'s timestamp', async () => {
  const c = h._cap, t0 = Date.parse('2026-10-12T10:00:00Z');
  const a = c.overCap('F', t0), b = c.overCap('F', t0 + 1000), d = c.overCap('F', t0 + 2000);
  c.uncap(b); assert.equal(c.day().n, 2);
  // two more fit in the minute only if exactly one slot was freed: slots are now t0 and t0+2000
  for (let i = 0; i < 4; i++) assert.notEqual(c.overCap('F', t0 + 3000 + i), true);
  assert.equal(c.overCap('F', t0 + 4000), true); void a; void d; });
await t('N5-10 a failure just after midnight does not take a slot from the new day', async () => {
  const c = h._cap, before = Date.parse('2026-10-12T23:59:59Z'), after = Date.parse('2026-10-13T00:00:01Z');
  const old = c.overCap('F', before); assert.equal(c.day().n, 1);
  c.overCap('G', after); assert.equal(c.day().n, 1); assert.equal(c.day().key, '2026-10-13');
  c.uncap(old); assert.equal(c.day().n, 1); });
await t('N5-10 a createdAt from the future is refused', async () => {
  const r = await call(evt({ createdAt: new Date(Date.now() + 3600e3).toISOString() })); assert.equal(r.code, 400); assert.equal(sent.length, 0);
  assert.equal((await call(evt({ createdAt: new Date(Date.now() + 60e3).toISOString() }))).code, 200); });
await t('N5-10 an oversized body gets a 413 without destroying the request first', async () => {
  const body = 'x'.repeat(300 * 1024); let destroyed = false, finishCb = null, destroyedBeforeSend = false;
  const req = Object.assign(Readable.from([Buffer.from(body)], { autoDestroy: false }), { method: 'POST', headers: {} });
  req.destroy = () => { destroyed = true; };
  const out = { code: 0, headers: {} };
  const res = { setHeader: (k, v) => { out.headers[k] = v; }, status(c) { destroyedBeforeSend = destroyed; out.code = c; return this; }, json() { return this; }, once(ev, cb) { if (ev === 'finish') finishCb = cb; } };
  await h(req, res);
  assert.equal(out.code, 413); assert.equal(destroyedBeforeSend, false); assert.equal(out.headers.Connection, 'close');
  finishCb(); assert.equal(destroyed, true); });
console.log(n, 'webhook tests passed');
