# Harvestly site

Plain HTML, CSS and vanilla JS modules. Eight pages (home, how-it-works, pilot, partners, sources, privacy, thanks, 404) and two serverless functions (Tally webhook, NASA recent weather), no framework, no inline code. Live: https://harvestly-roan.vercel.app (Vercel project `harvestly`, scope ken-muritus-projects).

## Architecture
- `tools/site-src/pages/*.mjs` are template modules (home, how, pilot, partners, sources, notfound). `tools/site-src/lib.mjs` holds the page shell, masthead and footer; `params.mjs` the 15 parameters; `refs.mjs` the 39 references; `parts.mjs` shared SVG and message parts.
- `tools/build-site.mjs` writes `site/*.html`, `sitemap.xml`, `robots.txt`.
- `site/assets/js`: `hero.js` (hero phone), `engine.js` (JS port of emc, ast_days, drift, days_left, risk level), `data.js` (generated), `dial.js` (the countdown dial, shared by build and browser), `chart.js`, `main.js`, `story.js` (scroll-driven week), `calc.js` (calculator).
- `site/vercel.json` sets the strict CSP (`script-src 'self'; style-src 'self'`) and cache headers.
- Logos: `tools/logo/optimise.mjs` shrinks the traced SVGs into `site/brand/` (each under 15 KB). Company lockup SVGs, if any remain in `site/brand/`, are not used: the site carries no endorsement line.

## Regenerate
```
python3 tools/gen_site_data.py        # data.js + templates from engine/vectors.json (asserts a match)
node tools/build-site.mjs             # HTML, sitemap, robots
node tools/make-brand-assets.mjs      # favicon, apple icon, og/*.png (Playwright renders HTML to PNG; sharp is not used)
node tools/serve.mjs 4173             # local server with the production CSP
cd site && vercel --prod --scope ken-muritus-projects
```

## Tests
- `node tools/test-engine-js.mjs`: 109 table values match vectors.json (worst 4.9e-7) and the 70-day dry_grain_rewets replay matches.
- `node tools/audit.mjs <url> [outDir] [sections] [scheme]`: Playwright (Brave), widths 360/390/768/1280/1920, light and dark. Sections: sweep, story, calc, whatif, print, kb, og. Checks h1, headings, tap targets, overflow, meta, og, console, axe, CTA, focus, CSP, text clipping.

## Audit results, 12 October 2026, live URL
- audit.mjs: all sections, both themes, 0 failures (12 Oct 2026). check-links.mjs: 44 external URLs, 0 broken, 11 blocked to bots (open by hand).
- Lighthouse (mobile default, Brave headless): performance 0.96, accessibility 0.97, best practices 1.00, SEO 1.00 (home page only).
- JS: about 112 KB raw in assets/v (content-hashed, immutable).
- Screenshots viewed by eye for home at 1280 (light and dark) and 360 (dark), story at four scroll positions, how-it-works at 360. Not every page at every width was viewed by eye; the automated checks cover the rest.

## Known gaps
- Lighthouse was run on the home page only.
- Sack illustration is serviceable, not refined.
- Large tables on /how-it-works scroll sideways at 360 px.
- References not re-opened on 12 October are labelled "Cited".


Regenerate: python3 tools/gen_site_data.py; node tools/build-site.mjs; node tools/make-brand-assets.mjs; node tools/serve.mjs 4173; node tools/check-links.mjs. Contact address: CONTACT_EMAIL in tools/site-src/config.mjs (harvestlyafrica@gmail.com).


## Forms and email (added 12 October 2026)
- Three Tally forms, linked as plain links that open in a new tab (no embeds, CSP unchanged). URLs live in one constant, `FORMS` in `tools/site-src/config.mjs`; `formLink()` in `lib.mjs` renders every call to action (visible text, visually hidden "(opens in a new tab)", icon, `target="_blank" rel="noopener noreferrer"`). Forms: farmer interest list (`D4rAxR`), partner (`lboKYk`), team contact (`RGXvb9`).
- Each form redirects on completion to `/thanks` (a static page with no promises). The Tally API cannot create a native thank-you page, so the redirect stands in for it.
- `/privacy` is the privacy note (Kenya Data Protection Act basics; open points stated; not legal advice). Linked from the footer, `/thanks` and each form.
- `/privacy` also has a section on the Telegram test bot @HarvestlyBot: what is stored (a salted hash of the chat id, language, test registration and readings, a message counter, update numbers for 2 days; no message text, names or usernames), Telegram itself sees the conversation, hosting in Dublin (Vercel `dub1`) and Turso in Ireland (aws-eu-west-1), 30-day deletion of idle chats (daily Vercel cron), what /reset keeps, simulated weather, no alerts sent unprompted. Source: `privacy.mjs` in `tools/site-src`; facts in `docs/TELEGRAM.md`.
- The bot is a separate Vercel project, `harvestly-bot` (https://harvestly-bot.vercel.app, source in `bot/`, not part of `site/`); its deploy steps and environment are in `docs/TELEGRAM.md`.
- `site/api/tally-webhook.js` (Node, CommonJS, no dependencies). Tally POSTs FORM_RESPONSE; the function checks `Tally-Signature` (base64 HMAC-SHA256 of the raw body, constant-time compare; 401 if wrong), then sends ONE email through the Brevo transactional API: the team notification to the project inbox with the answers (Reply-To only from the form's INPUT_EMAIL field, one plain validated address; if Brevo rejects the message with it, the function sends it again without Reply-To so the notification is never lost). The function is pinned to Vercel region iad1 (`regions` in `site/vercel.json`; `vercel project inspect` shows iad1) and /privacy says exactly that. A body with no `createdAt`, or older than 2 days, is refused or ignored as a replay; a failed send gives its cap slot back. No acknowledgement is sent to respondents. Answers and addresses are never logged. Caps: 6 per form per minute and 100 per day (per instance, best effort); non-production deployments never send. Repeats of the same Tally `eventId` are ignored (best effort: the memory lives as long as one function instance). Brevo failure on the notification returns 502 so Tally retries; 
- Environment variables (Vercel project `harvestly`, production and preview, all hidden): `TALLY_SIGNING_SECRET`, `BREVO_API_KEY`, `BREVO_SENDER_NAME`, `BREVO_SENDER_EMAIL`. Local copies live outside the repo in `~/.config/harvestly/secrets.env` (also `TALLY_API_KEY`, used only for setup and tests). Nothing secret is in the repo or in client files.
- Brevo setting for Ken: verify harvestlyafrica@gmail.com as the sender (or use a Harvestly-only account). The site and forms make no tracking claim about Brevo.

### Rotating keys
1. New signing secret: generate one (`openssl rand -hex 32`), update `TALLY_SIGNING_SECRET` in `secrets.env`, run `vercel env add TALLY_SIGNING_SECRET production --sensitive --force` (value on stdin), update each Tally webhook (`PATCH https://api.tally.so/webhooks/<id>` with `signingSecret`), then redeploy.
2. Brevo key: create a new key in Brevo, replace `BREVO_API_KEY` the same way, redeploy, delete the old key.
3. Tally API key: replace it in `secrets.env` and revoke the old one in Tally settings. The site does not use it at run time.

### Testing the email path
- Unit-style: call the exported handler with a mock `fetch` (bad signature gives 401, unsigned 401, malformed 400, repeated `eventId` is ignored, Brevo down gives 502).
- End to end: Tally cannot submit through its API. Fill each real form in headless Brave with clearly labelled TEST data and your own address, then check `GET https://api.tally.so/webhooks/<id>/events` (deliveryStatus SUCCEEDED) and Brevo `GET /v3/smtp/statistics/events` (requests, delivered). Delete the test submissions with `DELETE /forms/<id>/submissions/<subId>`.
- Preview deployments are behind Vercel protection; a webhook aimed at one needs a protection-bypass query parameter. Point webhooks back at the production URL afterwards.

## Phone mockup
One shared `phone()` in `tools/site-src/parts.mjs` and one `.phone` block in `style.css` draw every phone on the site (hero, story, the three rules). Real Android proportion: body 1 : 2.16 (about 72 x 155 mm), height = 2.16 x `--pw`, bezel 2.6% of the width, punch-hole camera, side keys, status bar, Android messages header (back, avatar, call, menu), thread, compose bar with plus and send, gesture bar. One variable, `--pw`, sets every size; message text never falls under 12 px. In the story, small screens show the top of the same phone, open at the bottom (same width and type, never squat); wide screens show the full phone beside the gauges.

## Hero simulation
`site/assets/js/hero.js` plays the hero phone: the farmer sends `JOIN KITALE SACK 12` (`SAJILI KITALE MAGUNIA 12` in Kiswahili; the format the SMS handler accepts), Harvestly sends its WELCOME template, a typing indicator, the demo scenario's DRY_NOW warning of 15 October (the 34), the farmer replies DRYING, Harvestly answers THANKS. All text comes from `data.js`. The HTML holds the final state (the first two bubbles carry `.pre` and show only while playing), so with no JavaScript or under prefers-reduced-motion nothing moves. It loops with a 6 s pause at the end, pauses when the tab is hidden or the phone is off screen, has a Pause/Play button, and while playing the phone is `aria-hidden` and a visually hidden caption carries the whole conversation. The phone size is fixed, so there is no layout shift.


## NASA data (added 12 October 2026, per `research/nasa-due-diligence.md`)
- `site/api/recent-weather.js` (Node, no dependencies, no key): GET `?ward=<name>` for one of six example wards (fixed allowlist, centroids rounded to 1 decimal; any other ward or parameter is refused or ignored, nothing about the visitor is forwarded). It asks NASA POWER daily point data (T2M, RH2M, PRECTOTCORR, community AG, local solar time) for the last 14 days, drops -999 (a day missing any of the three values is missing), returns the last 7 observed days `{ward, days:[{date,t,rh,rain}], asOf, source, version}`, caches in memory (6 h, one request per POWER cell, failures not retried for 15 min, stale copy kept up to 7 days) plus `Cache-Control: s-maxage=21600`, times out after 6 s, and rate-limits (12 per minute per caller, 120 per instance; the caller's IP is never stored or logged: the key is a salted hash with a random per-instance salt, kept in memory for one minute). `ward` is matched against the allowlist's own keys only, so `constructor` or `__proto__` give 400 like any unknown ward. NASA down or data older than 7 days gives `200 {"error":"unavailable"}`. The CSP stays `connect-src 'self'`; `vercel.json` no longer sets `no-store` on all of `/api/*` (only the Tally webhook) so the proxy can set its own cache header. `tools/serve.mjs` routes the path to the same handler locally. Tests: `node tools/test-recent-weather.mjs` and the N7 checks in `tools/test-site-copy.mjs`.
- Calculator: an optional button "Show recent weather near Kitale" under the calculator. Nothing is requested when the page loads; only a tap calls `/api/recent-weather?ward=Kitale`. The answer is one text line under the result, the due-diligence wording ("Recent weather near Kitale (NASA satellite/model estimate, to <date>): about <T> C, humidity <RH>%, <R> mm rain. This is an area estimate, not a measurement at your store.", with the Kiswahili twin; English and Kiswahili follow the message-language toggle). It never fills the calculator inputs. If NASA is unavailable the line says so. `html[data-calc-ready]` is set once the calculator has bound (tests wait for it).
- `/pilot` has one MODIS Terra true-colour snapshot of Trans Nzoia (20 December 2025, 800 x 800, 76 KB, `site/assets/img/`), fetched once through the Worldview snapshot tool (bbox 0.6 to 1.4 N, 34.4 to 35.2 E; layer `MODIS_Terra_CorrectedReflectance_TrueColor`). Re-fetch only by hand; do not call it at run time. `/sources` references 38 and 39 carry the POWER and GIBS acknowledgements word for word. No NASA logo is used.

## Drive copy
