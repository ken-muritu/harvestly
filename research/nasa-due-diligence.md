# NASA data in Harvestly: due diligence (checked 2026-10-12)

Labels as in verification.md: **verified** = read at the publisher or measured by me today with a live call; **secondary** = read via a search-result summary or a third-party page; **unverified** = not opened or not testable from here.
Scope: (1) NASA POWER daily point data (T2M, RH2M, PRECTOTCORR) as "real recent weather"; (2) a NASA satellite image of Trans Nzoia as a site visual. About 18 network calls were made. The NASA_API_KEY was never used or printed (POWER and GIBS need no key).

## 0. Decision summary
| Use | Verdict | One line |
|---|---|---|
| (1) POWER as "recent weather, NASA satellite/model estimate", shown only | **GO, conditional** | Server-side, cached, labelled as a ward-scale estimate. Show it as context. |
| (1b) POWER observed days feeding the engine | **GO for a labelled catch-up only; NO-GO for any claim about a specific sack** | Only T and RH drive the engine. Rain does not. Gap-fill needed. |
| (2) Image of Trans Nzoia from GIBS (MODIS true colour), self-hosted | **GO, conditional** | One honest, dated, cloud-checked snapshot, stored as a static file. |
| (2b) EPIC | **NO-GO** | Whole-Earth disc images; Trans Nzoia would be a few pixels. Not called (unverified detail). |

## 1. What a POWER point value is (spatial)
- Sources page (https://power.larc.nasa.gov/docs/methodology/data/sources/, **verified**): meteorology comes from MERRA-2 and GEOS-IT on a 1/2 degree latitude by 5/8 degree longitude grid ("GEOS-IT has the same grid resolution as MERRA-2"; GEOS-IT is appended after MERRA-2 for recent days). Precipitation is described as derived from IMERG on a 0.1 degree (about 10 km) grid. The page does not say which parameter comes from which source.
- **Measured today:** the daily point response header says `sources: GEOSIT, POWER`, `time_standard: LST`, `fill_value: -999.0`, v2.10.0. Kitale (1.0157 N, 35.0062 E) and a point 20 km away (1.2 N, 35.3 E) returned **identical** values for 1-9 Oct (T2M, RH2M, precipitation all equal) and the same elevation 2097.62 m. Eldoret (0.52 N, 35.27 E) differed (elevation 1809.96 m, different values). So one value = one grid cell, about 55 km by 70 km (0.5 deg x 0.625 deg at the equator). **Verified.**
- Consequence: one number for every farmer in a cell. Trans Nzoia (about 2,500 km2, sloping from Kitale at about 1,900 m up to Cherangany and down to Mt Elgon) spans roughly 2 to 3 cells. A ward is far smaller than a cell, so a point value is "the weather of the surrounding roughly 50 km box", not "your ward". The cell elevation (2,098 m) is about 200 m above Kitale town (Open-Meteo reports its own 1,898 m for the same spot), so a cold bias from elevation is plausible; I did not find POWER documentation of an elevation correction (the sources page does not mention one). **Verified (measurement), the cause is unverified.**

## 2. Latency (measured)
- Request on 2026-10-12 12:21 UTC for 15 Sep to 12 Oct: real values through **9 Oct**; 10, 11 and 12 Oct returned `-999` for all three parameters. So the newest usable day was **today minus 3**. **Verified.** The docs say GEOS-IT is "generally ready within about two days" (**verified**, sources page); IMERG Late is 14 hours but IMERG Final 3.5 months (verified, same page), so late-arriving revisions to precipitation are possible and **unverified** here.
- Rule for the code: treat -999 as missing, never as a number (the engine has a plausibility filter, `_plausible`, but -999 for RH would be rejected only because it is below 0; T2M -999 is below -60. Both rejected, good, but test it).
- Time standard is **LST** (local solar time) by default: for 35 deg E that is UTC+2.33 h, not Nairobi's UTC+3. A "day" is shifted about 40 minutes against a calendar day in Kenya. Harmless for daily means; do not call it "yesterday's weather in Kitale". `time-standard=UTC` exists (verified, daily API page). Pick one and say nothing about hours.

## 3. Does it match the ground? Comparison and literature
**My own comparison (Kitale point, 1-9 Oct 2026, POWER vs Open-Meteo archive, which is another model product, not a station):** verified measurement, but neither is ground truth.
| | POWER T2M | Open-Meteo T mean | POWER RH2M | OM RH mean | POWER rain | OM rain |
|---|---|---|---|---|---|---|
| range | 19.7-21.4 | 18.9-20.6 | 43.6-68.3 | 49-77 | 0-5.2 | 0-9.4 |
- POWER was **warmer by about 0.5 to 1.5 degrees C** on most days (opposite sign to what the higher cell elevation would suggest), RH differed by **-5 to -10 points on wet days** and rain differed by up to 4 mm/day (6 Oct: 5.2 vs 9.4). Two products on the same day disagree by more than the engine's sensitivity (section 6). Neither can be called right.
- **Literature (searched; no Kenya-specific POWER validation found):**
  - No study validating NASA POWER T2M, RH2M or PRECTOTCORR against Kenyan stations was found. A 2026 EGUsphere preprint (Shibabaw and Mersha, doi 10.5194/egusphere-2025-6425) evaluates POWER T2M and irradiance over East Africa for 2021-2024; I did not open it and do not know if it uses stations (**unverified**, secondary).
  - Outside Africa: Oman station comparison found 2 m temperature reliable, RH "mild inaccuracy", precipitation "largely unreliable" (arXiv 2210.16111, secondary); a 21-station multi-country study found Tmin underestimated in tropical climates (secondary summary only). Sri Lanka (high elevation) recommended local bias correction (secondary). These are analogues, not evidence for Kenya.
  - IMERG in East Africa: Ageet et al., J. Hydrometeorology (doi 10.1175/JHM-D-21-0145.1), 36 stations in equatorial East Africa 2001-2018: IMERG best at short time scales; **all products missed most daily extremes, the share missed ranging from 79% (IMERG-NRT) to 98% (CHIRPS)** (secondary, search summary). Dezfuli et al. 2017 (TAHMO gauges): IMERG agrees better in East Africa than in the Sahel, largest product differences over mountains (secondary). A University of Twente dataset assessed CHIRPS, CMORPH, MSWEP and RFE vs 20 Kenyan gauges 2012-2018; findings not seen (unverified).
  - POWER's own precipitation page (https://power.larc.nasa.gov/docs/methodology/meteorology/precipitation/) validates against NCEI stations globally; not Kenya (secondary). NASA says MERRA-2 uses a coarser gauge-and-satellite product over Africa (secondary).
- Conclusion: expect errors of the order of 1 to 2 degrees C and 5 to 10 RH points on a given day, larger for rain in the highlands, **no validation number to quote**. Say "estimate". Never "accurate".

## 4. What the variables mean for stored grain
- **RH2M** is the model's relative humidity of **outdoor air at 2 m**, daily mean (the docs name it "Relative Humidity at 2 Meters", verified in the response). It is not store air and not grain moisture. Indoors, air is usually warmer by day and the store buffers swings; the grain tracks the mean RH and temperature inside the store, not outside. A sack in a house, a crib and a bare floor differ (the engine already models "sack/crib/floor/hermetic" with one 5%-a-day exchange rate, a CALIBRATION constant).
- **T2M** is outdoor air temperature (daily mean), used by the engine as grain temperature (already flagged as CALIBRATION in the engine). Store temperature can differ by several degrees (sun on roof, thick walls, floor contact): unmeasured here, so do not claim.
- **PRECTOTCORR** (mm/day) is rainfall on the ~10 km (IMERG) or 50 km cell. Rain does not wet maize in a sack indoors; it matters through roof leaks, wet floors, carrying grain across and harvest or drying timing. Indoors, the grain follows humidity, not rain. The engine uses rain only for the "cover it" alert from **forecast** values (`evaluate`, line 758) and never in `advance_day`. So **observed rain cannot change the engine's drift or days-left**. Show it as "rain recorded by satellite estimate", nothing more.

## 5. Terms, attribution, limits
- **POWER acknowledgement (verified, https://power.larc.nasa.gov/docs/referencing/):** "The data was obtained from National Aeronautics and Space Administration (NASA) Langley Research Center's Prediction Of Worldwide Energy Resources (POWER) project funded through the NASA Earth Science Division." Data reference form: "The data was obtained from the POWER Project's Daily 2.x.x version on YYYY/MM/DD" (the page gives the Hourly form; Daily is my substitution). That page has no licence text and no disclaimer (**verified: none found there**). I did not find a separate POWER terms-of-use page (**unverified**).
- **NASA general rule (verified, https://www.nasa.gov/nasa-brand-center/images-and-media/):** NASA content is generally not subject to copyright in the US; NASA should be acknowledged as source; content must not suggest NASA endorses a product or service; the NASA insignia and logotype are not public domain, so **do not use the NASA meatball logo**. Plain text credit only.
- **Rate and use limits (verified, daily API doc page):** no numeric limit published; "If your application persists in requesting the same relative location, it will potentially be blocked"; request each 0.5 degree cell once; up to 20 parameters per point request; the API returns HTTP 429 when throttled with no retry guidance. So: one request per cell per day from our server, never per user. Our need is 2 to 3 cells x 1 per day.
- **Robots:** power.larc.nasa.gov/robots.txt has `Disallow: /api/` for crawlers (verified). It targets crawlers, but it signals the API is not meant for page-load traffic by the public. Another reason for server-side, cached.
- **CORS (verified):** a GET returned `access-control-allow-origin: *`, so a browser could call POWER directly. Both are not advisable: (a) our CSP is `connect-src 'self'` and `img-src 'self' data:` (site/vercel.json), so a browser call needs `connect-src https://power.larc.nasa.gov`, loosening a strict CSP; (b) the visitor's IP and a ward coordinate go to NASA from each visitor; (c) a burst of visitors hits NASA, risking a block; (d) no cache. **Use a server (or build-time) proxy; keep the CSP unchanged.** The OPTIONS preflight returned 404, which is fine for simple GETs (verified), and irrelevant when proxied.
- **GIBS acknowledgement (verified, https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api):** "We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS)." No rate limits or quotas stated there. Support: earthdata-support@nasa.gov. The official page lists WMTS, WMS and TWMS and **no snapshot endpoint**.
- **Worldview Snapshots (`wvs.earthdata.nasa.gov/api/v1/snapshot`):** worked today (HTTP 200, image/jpeg, `access-control-allow-origin: *`; **verified**), but it is not on the official GIBS API page, so treat it as a convenience tool with no stated guarantee (**unverified status**). Fetch once at build time; do not call it at runtime.
- **api.nasa.gov key:** not needed for POWER or GIBS; I did not test api.nasa.gov or EPIC (**unverified**). Its published limits are not confirmed here.

## 6. How it fits the engine (read from engine/harvestly_engine.py)
- `WeatherDay(day, temp_c, rh, rain_mm=0.0, rain_prob=None)`: T and RH are **daily means**; rain_mm daily total; rain_prob optional.
- `daily_run(b, today, days, places, rain24, meta)`: `days` is a list of WeatherDay. `split_weather` makes `past` (day <= today) and `forecast` (day > today). **It raises ValueError unless the forecast starts tomorrow**, so POWER alone (no future) can never drive `daily_run`. For each day from `last_advanced + 1` to today it calls `advance_day` with `past[d]`; a missing day **reuses the nearest earlier day** and is listed in `diag['missing_days']`.
- `advance_day` is idempotent (a day is never counted twice) and uses only `temp_c` and `rh`: for sack/crib/floor `moisture += 0.05 x (EMC(T,RH) - moisture)`; `life_used += 1 / ast_days(T, moisture)`. Hermetic and drying batches do not exchange moisture. Rain is not used.
- `respond(b, text, today, forecast, ...)` needs a forecast (tomorrow onward); only `forecast[0].temp_c` is used as a hint. No change needed for observed days.
- **How observed days can be fed:** (a) keep Open-Meteo for the forecast (tomorrow onward, as now); (b) fetch POWER for [last_advanced+1, today-3]; (c) append WeatherDay(day, T2M, RH2M, PRECTOTCORR) for those days to `days`; for the last 3 days (-999) either drop them (the engine then repeats the last real day, flagged in missing_days) or use Open-Meteo's `past_days` values as now. Do not mix without recording which days came from where. Rows with -999 must be dropped before building WeatherDay.
- **Sensitivity (computed with the real engine on the POWER Kitale 1-9 Oct series, sack, 16.0% start from a meter reading):** end moisture 14.96% and life used 6.2% with POWER as is; 15.45% / 6.4% with the Open-Meteo-like offsets (-1.2 C, +7 RH); 15.61% / 7.6% with RH +10. For a 13.0% start: 13.07% (1.6% life) or 13.72% (2.0%) with RH +10. Moisture after 9 days moved up to 0.65 points just from a 10-point RH difference. The EMC table is steep (about 1.6 points of EMC per 10 RH points: EMC 11.8% at 50% RH, 13.4% at 60%, 15.1% at 70%, all at 20.5 C), so a 5-10 point RH error is the same size as the 13.5% safety line margin.
- **Is a catch-up meaningful?** Only as a rough, labelled estimate from a **measured** starting point (a meter, hygrometer or salt-test result on a stated date), run over observed days since that test. It is then "estimated drift since your last test, using ward-area weather", consistent with the engine's own rule that the table clock starts at the first test. Not meaningful from a harvest or registration date with no measurement (moisture is None, `advance_day` returns without doing anything). Longer than a few weeks it compounds the unvalidated 5%-a-day rate and the weather bias; cap and say so. The result must never replace a re-test.
- What would be **wrong to claim:** that this is the weather in your store or on your farm; that it is a measurement; that it is a forecast; that the grain moisture "is" the output; that rain on the roof/ground caused the number; that results hold for Kenyan white maize (tables are US yellow dent, Bartosik and Maier caveat in verification.md section 2); that POWER is accurate or validated for Kenya.

## 7. Reliability and fallback
- No SLA or status page found (**unverified**). Measured today: 9 successful responses, each about 0.15 s server time; one 404 only on the OPTIONS probe. Latency at CloudFront Nairobi POP (verified `x-amz-cf-pop: NBO50`).
- Plan: a daily server job fetches the 2-3 Trans Nzoia cells once, stores the daily rows (date, T2M, RH2M, rain, fetched_at) and serves from there. If POWER is down or throttled: serve the last stored data with "as of <date>", never an error; after more than 7 days stale, hide the block silently and let the engine fall back to the existing Open-Meteo path (`WEATHER_STALE_HOURS`-style flag). Open-Meteo remains the forecast source, and its free tier is for non-commercial use (engine comment, line 1040; not rechecked).
- If -999 appears for older days than 5 days (late or failed reprocessing), log and skip. A day with 3 parameters partly -999 should be treated as missing.

## 8. Data protection
- Bot check: `bot/lib/harvestly_bot_core.py` has only `EXAMPLE_WARDS = BUNGOMA, ELDORET, KAKAMEGA, KAPSABET, KITALE, WEBUYE` ("EXAMPLE list, not the pilot directory"), no coordinates, and its weather is simulated today (**verified**: grep for lat/lon in bot code found nothing). The bot never holds a farmer location.
- Send NASA only a **ward or cell centroid**, rounded to the 0.5 degree grid (POWER is the same value anyway, as shown in section 1). Never a farmer's address, phone, or Telegram id. The request carries our server's IP, not the farmer's. Round the centroid to 1 decimal; with that, no coordinate can identify a farm.
- The website calculator has no network calls today (`connect-src 'self'`); keep it that way: a fixed server-built JSON per ward, no browser contact with NASA, no change to privacy.html needed beyond adding NASA as a data source in the sources page.

## 9. Imagery: what I got, honestly
- Request: Worldview snapshot, layer `MODIS_Terra_CorrectedReflectance_TrueColor`, bbox 0.6 to 1.4 N, 34.4 to 35.2 E (about 88 km square, Kitale/Trans Nzoia and part of Uasin Gishu), 800 x 800 px. MODIS true colour is a coarse product (250 m native; look at pixels, not fields; 800 px over 88 km is about 110 m per pixel, so it is enlarged and soft). It cannot show farms, stores or crops. **Verified (visual).**
- **9 Oct 2026:** about 25% cloud, scattered cumulus and thin haze over the west and south; the north-east is clear. Usable but not clean.
- **27 Sep 2026:** milky haze/smoke over the south and middle; worse.
- Both dates are the rainy-season start: cloud and haze are normal here, so a clear image is chance. Choose by looking at several dates (compare 3-5), pick the clearest one, and label the date. Do not present any single day as "typical" or "this week". A composite or longer window is unverified here.
- Do **not** claim the image shows crop failure, drought or maize condition (USDA GAIN said the harvest was cut 51%, but this image proves nothing about it).
- GIBS WMTS (official) is the supported way for a mapped view; for a still, store a snapshot file, which keeps `img-src 'self'` and removes a runtime dependency. Cost: one JPEG, roughly 80 KB at 800 px (measured 83 KB, 39 KB).

## 10. Go/no-go with wording
### Use (1): recent weather (GO, conditional)
Conditions: server-side cached fetch; ward centroid rounded; -999 dropped; shows "as of" date (data are 3 days old); never sits next to a verdict or a countdown as if causing it.
- Bot, optional one line in the daily message and in `/status` (not in the SMS-length templates; keep Telegram only):
  - EN: "Recent weather near Kitale (NASA satellite/model estimate, to <date>): about <T> C, humidity <RH>%, <R> mm rain. This is an area estimate, not a measurement at your store."
  - SW: "Hali ya hewa ya karibuni karibu na Kitale (makadirio ya satelaiti ya NASA, hadi <tarehe>): takriban <T> C, unyevu <RH>%, mvua <R> mm. Ni makadirio ya eneo, si kipimo cha ghala lako." (Kiswahili needs a native check, **unverified**.)
  - Credit line in the welcome/about text, not in every message: "Weather estimates: NASA POWER (NASA Langley Research Center, funded by the NASA Earth Science Division). Not endorsed by NASA."
- Website: no live widget on the calculator page. One quiet text line under the calculator result, same wording as above, with the full credit on `sources.html` (not the footer). The calculator itself should remain a user-input tool; a prefilled "typical Kitale week" would again look like measurement.
- Engine catch-up (1b): GO as an **opt-in**, bot only, sentence: "Since your test on <date> (<M>%), using area weather from NASA, the estimate is about <X>%. Weather is estimated, so test again to be sure." Cap at 21 days, then "test again". Never use it to say "safe".
- Words to avoid: accurate, precise, real-time, live, measured, your weather, forecast, "NASA says", "NASA data shows your grain".

### Use (2): image of Trans Nzoia (GO, conditional)
- One static JPEG, self-hosted in `site/assets`, alt text and caption together: "Satellite view of the Trans Nzoia area, NASA MODIS Terra true colour, <date>. About 88 km across; individual farms are not visible. Cloud and haze are normal at this time of year." Credit under the caption: "Imagery: NASA Worldview / GIBS (MODIS Terra)." Footer or sources page: the full acknowledgement quoted in section 5.
- Placement: `pilot.html` (where the area is the point) as a small figure beside the pilot description, or the About/Sources page. Not the hero or the calculator. A decorative use is fine only if the caption says it is decorative-scale and dated.
- Fallback: if no clear image is found, no image (the page works without it). If the snapshot service is down at build time, keep the existing file.
- No NASA logo. No claim of partnership or endorsement.

## 11. Tests needed
1. Parser: POWER JSON with -999 in any of the 3 parameters, in the last 1-3 days: those days dropped, `missing_days` reported; partial -999 treated as missing; malformed JSON or 429 returns the stale cache, not an exception.
2. Cell mapping: rounding of ward centroid; two wards in the same cell make one request (assert request count).
3. Engine: `daily_run` with POWER past days plus Open-Meteo forecast gives the same result as before when POWER is absent; idempotent on repeat; `daily_run` with no forecast still raises (documented).
4. Observed catch-up: starting from a meter reading on a date, N observed days; untested batch returns nothing; cap at 21 days; output text never says "safe".
5. Staleness: data older than 7 days hides the block; the "as of" date is rendered.
6. Copy tests: the 3 sentences above contain the words "estimate" and "not a measurement"; none of the banned words appear (accurate, live, real-time, measured, forecast, NASA says).
7. CSP: a test or `curl -I` check that the response header remains `connect-src 'self'; img-src 'self' data:` after the image is added, and that the page loads no request to nasa.gov host at runtime.
8. Attribution present on sources.html, exact GIBS and POWER strings; no NASA logo file in the repo.
9. Privacy: grep that no request log or payload contains a phone, Telegram id, or a coordinate with more than 1 decimal.
10. Live canary (CI optional, weekly): one POWER call for Kitale, assert the latest real date is within 7 days; one Worldview snapshot returns image/jpeg > 10 KB.

## 12. Open items (not resolved)
- No Kenya station validation of POWER found; if wanted, request KMD or TAHMO station data for Kitale and compare 30 days.
- POWER terms of use / licence page not found; GIBS terms only via the developer page; ask earthdata-support if the commercial status of Harvestly matters.
- EPIC and api.nasa.gov limits not tested. Kiswahili wording not reviewed by a native speaker.
