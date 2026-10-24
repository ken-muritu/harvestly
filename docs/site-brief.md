# Harvestly website brief (v3, 2026-10-12)

Ken's verdict on v1 and v2: generic, design mismatches, missing concept and story, many gaps. This brief replaces both. Hold the site to a full standard (voice, accessibility, documentation, audit).

## The idea the whole site is built on

**The sack doesn't tell you.** Maize in a woven sack looks the same on day 1 and on the day it is ruined. Moisture is invisible, the weather changes it every day, and a farmer finds out when it smells. Harvestly makes the invisible visible: a countdown, per batch, from a free test plus the forecast.

One visual motif carries everything: **the countdown dial from the logo** (the dashed amber arc and tick). Reuse it as the section marker, the progress device, the loader, the days-left gauge and the favicon story. Do not add other decorative motifs.

## The story (the home page is one scroll told in this order)

Use a plain, specific narrator voice ("we"), short sentences, Kenyan English. No invented farmer quotes or fake testimonials. If a person appears, label them "An example farmer (illustrative)". The data is real: it comes from the engine's own scenarios.

1. **Hook.** "34 days left." Big number on a designed phone screen. Line: "That is what Harvestly told the owner of one batch of maize on the day the forecast turned." Under it, the example label.
2. **The problem, felt.** Day 0: the harvest comes in, looks fine. Show two identical sacks; one is at 13%, one at 18%. You cannot tell. Then the numbers: 213 storage days at 15% moisture, 30 days at 19%, 11 days at 23% (Arkansas FSA1058, 18 °C). The East African standard limit is 13.5%.
3. **Why now.** Trans Nzoia, Oct 2026: the drought cut the crop and USDA cut its forecast by half to 2.2 Mt; KMD expects above-average rain, and says "drying capacity, safe/hermetic storage, aflatoxin surveillance". Say it once, with sources.
4. **What happens in a week.** The scrollytelling centrepiece: a scroll-driven replay of the engine's pitch-demo scenario from `vectors.json`. As the reader scrolls, a day counter advances; the weather strip (rain, humidity), a moisture line, the life-used bar and the days-left dial all move together; the SMS the farmer receives appears at the day it is sent (EN/SW toggle). It must be driven by the real data (`tools/gen_site_data.py` asserts it matches vectors.json). Respect prefers-reduced-motion (then show a stepper with buttons).
5. **Your turn: the calculator.** "How long will your sacks last?" Inputs: moisture % (or salt test yes/no), temperature, humidity, storage type. Output: where the moisture is heading (EMC) and storage days, with the honest flags the engine uses (below 15% is extrapolated; salt test never clears grain; US yellow corn tables, not validated for Kenyan white maize). Port `emc` and `ast_days` to JS from the engine and test it against vectors.json in `tools/`. This is the thing no generic site has.
6. **Three rules that keep it honest.** Only a meter or hygrometer reading clears grain as dry; estimates only trigger a re-test; every repeat is spaced and capped. Show each with one real message example.
7. **What we know and what we do not.** The 15-row SOURCE / CALIBRATION / PROGRAMME table, and the honest limits. Say the pilot has not run.
8. **Where it goes next.** The warehouse gate: 13.5% is the NCPB / warehouse-receipt line. Pilot plan for Trans Nzoia, Oct 2026 to Jan 2027, in one short section, and the data this builds.
9. **For co-operatives, extension officers, counties and warehouses.** What they get, how it fits MoA-INFO or KAOP as a module. One contact action.
10. **Footer.** Contact address harvestlyafrica@gmail.com (single constant), sources, "Hackathon prototype". No company endorsement line.

Secondary pages (real pages, shared header, each with its own h1, meta, OG): `/how-it-works` (the engine in detail, the data tables, the parameters), `/pilot`, `/partners`, `/sources` (numbered references with the verified / secondary label from `research/verification.md`), `/kiswahili` is NOT a page: language is a toggle on messages only, from the engine's templates.

## Hard content rules

- No commitments. Remove every promise to publish results, report metrics or deliver anything by a date. Describe the pilot as a plan, not a pledge.
- Every claim matches `research/verification.md` and `docs/concept-note-v4.5.txt`: USDA "cut its forecast by half to 2.2 Mt"; no 36% loss figure; insects not called a tested majority cause; do not say farmers never pay (alerts are free, a reply is an ordinary SMS, cost to confirm); pilot has not run; impact figures are estimates labelled ESTIMATE and shown per 10,000 bags.
- Voice: plain and concrete. Banned: cutting-edge, seamless, robust, empower, solutions. Absolute dates.
- No stock photos. Illustration is drawn in SVG from the logo's own shapes: sacks, kernels, the dial, phone screens.

## Look and feel

- The supplied logo only (see "Logo" below). Palette from the logo itself (sample it): deep green, grain amber, cream, on warm paper. Red only for the HIGH-risk state. DM Sans (with its licence file), self-hosted.
- Editorial and calm, not a SaaS template: large type, a strict grid, generous space, strong numerals, no card-grid-of-three-icons, no gradient hero, no emoji, no glassmorphism. Each section earns its layout from its content (a table where it is a table, a timeline where it is time).
- Dark mode is a real design, not an inversion: deep green ground, cream type, amber accent.
- Motion has a job (time passing), is subtle, and is off under prefers-reduced-motion.

## Quality standards (all must pass, measured on the live URL)

Centred hero and nav; compact header (<=15% of viewport at 360x740 and 1280x800); main CTA above the fold at both; one h1 per page, no skipped levels; tap targets >=24 px; no horizontal overflow at 360/768/1280; meta description <=160; og:image per page (generated, 1200x630, using the logo); favicon from the logo symbol; sitemap, robots, 404 page; strict CSP with no inline script or style; AA contrast in both themes; axe zero violations; no console errors; keyboard-complete; Lighthouse performance and accessibility >= 95 on mobile; total JS under ~100 KB gz. Screenshots at 3 widths x 2 themes x every page must be looked at by eye and fixed before reporting.

## Logo

`~/Downloads/Harvestly Grain Monitoring Logo.png` is the supplied logo. Use it as supplied: do not redraw, recolour away from the palette, crop or retype it. A vector trace of it (symbol, horizontal lockup, with tagline, reversed) is made in `~/harvestly/tools/logo/` and published to `site/brand/`. No company endorsement appears on the site.

## Docs

`docs/SITE.md` in the repo: architecture, how data and OG images are generated, how to regenerate and test, the audit results with dates.
