# Verification of the "not verified" items in CHANGES.md (checked 2026-10-12, updated after review R1)

Labels: **primary** = read at the publisher or its official record; **secondary** = read via a mirror, news report or search-result summary; **unreachable** = could not be opened from this machine.

## 1. De Groote et al. 2023 (CIMMYT repository 10883/22998)
- Real title: "On-farm storage loss estimates of maize in Kenya using community survey methods" (De Groote, Muteti, Bruce, 2023).
- Source read: the Mexican national repository mirror of the CIMMYT record, https://recca.secihti.mx/recurso/oai:hdl.handle.net/10883/22998 (secondary: a mirror of the primary record's metadata). The CIMMYT repository itself (https://repository.cimmyt.org/handle/10883/22998) returned an Anubis "Access Denied" bot wall (unreachable).
- **Confirmed:** focus groups in 121 communities, 1,439 farmers, 6 maize zones. Pesticides 49%, **hermetic bags 16%**, botanicals 15%. So "about one in six" is right, but it is a focus-group estimate of farmers, not a household survey count.
- **Needs rewording:** the study only measures losses to two insects (maize weevil 21% a year, larger grain borer 18%), total 36% (671,000 t a year). It does not compare insects against moisture or mould, so "insects cause most of the weight lost" is the study's framing, not a tested ranking. The authors themselves say the 36% is higher than other studies and its accuracy needs checking. Do not quote 36% on stage.
- The note's reference [2] title ("storage losses, their causes and hermetic bag use") is a paraphrase. Use the real title.

## 2. Bartosik & Maier 2005 (ASAE Paper 056081)
- Exists: ASAE Annual International Meeting, Tampa, 17-20 July 2005; compares equilibrium moisture/humidity of yellow dent, white and waxy corn (2003 harvest, 0-25 C, 12-20% moisture). Finding: each type needs its own Modified Chung-Pfost fit; the standard ASAE corn parameters predicted white and waxy poorly. Source: search-result summaries of the abstract (secondary). Follow-up: Transactions of the ASABE 2007, "Study of Adsorption and Desorption Equilibrium Relationships for Yellow Dent, White, and Waxy Corn Types Using the Modified Chung-Pfost Equation"; errors 1.9-2.6 (MRD) vs 4.3 for the ASAE standard data (secondary).
- Supports the note's risk row. Caveat to say aloud: these are US white corn samples, not Kenyan white maize, and the tested range is 12-20% moisture, 0-25 C. The 2005 paper's numeric parameters were not seen. Hence the pilot calibration is the real answer.

## 3. USDA GAIN KE2026-0017 (28 Aug 2026): full report read via the APEDA copy on 12 Oct; usda.gov original unreachable
- The usda.gov page returns 403/Access Denied from here (original host unreachable; the full report was later read via the APEDA copy, see below): https://www.fas.usda.gov/data/gain/2026/08/kenya-dry-weather-decimates-kenyan-harvest
- Search-result summary of that page (secondary): "downgrades Kenya's MY2026/27 corn production forecast **by 51 percent to 2.2 million MT** after a severe mid-year dry period... will force Kenya to import a record 2.3 million MT." Also in Nation, https://nation.africa/kenya/business/kenya-maize-wheat-import-demand-rises-on-failed-crop-5582824 (secondary, 403 on fetch).
- **CORRECTION APPLIED in concept note v4 (kept in v4.2) and the deck (wording).** Review R1 (reading the GAIN text via the APEDA mirror) confirms the 51% is against the 4.5 Mt projection. The same summaries say the March 2026 GAIN report forecast **4.5 Mt (+32.4%)** and the July Feed Outlook cut it to 3 Mt. 2.2 / 4.5 = -51%. So the 51% is a cut **against the earlier forecast**, not a fall against last year. Implied last-year crop is about 3.4 Mt (4.5 / 1.324), so year-on-year the fall is about -35% (derived, not published by me). Note v3 said "forecasts ... 2.2 Mt, down 51%"; v4 and the deck say "cut its forecast by half to 2.2 Mt" and flag the base. Safer, if more detail is wanted: "cut by 51% from its earlier forecast to 2.2 Mt, potentially the smallest crop since 2000/01" (the last clause is from a secondary report of the September WASDE). Base confirmed 12 Oct: the full USDA GAIN report was read through the APEDA copy (agriexchange.apeda.gov.in): 2.2 Mt, 51% below the earlier 4.5 Mt. The usda.gov original is still unreachable from here.
- Not verified: "failure concentrated in Uasin Gishu, Trans Nzoia and Nakuru". Nation says nearly half of grain fields in western/North Rift destroyed; county list not confirmed.
- 25 million bags import (Daily Nation) x 90 kg = 2.25 Mt, consistent with the 2.3 Mt import figure.

## 4. Other claims checked in passing
| Claim in note | Result |
|---|---|
| Oracle Always Free: 2 databases, 20 GB each, 3-6 APEX/ORDS users, stops after 7 days idle | **Verified at primary** https://docs.oracle.com/iaas/autonomous-database-shared/doc/autonomous-always-free.html. Also: max 30 simultaneous sessions; stopped 90 days cumulative = may be reclaimed and deleted; Always Free only in the tenancy home region; 5 min wake-up wait for APEX/ORDS after restart. Add the 90-day reclaim and the 5-minute cold start (demo risk!). |
| ODPC registration exemption: needs BOTH turnover under KES 5M AND fewer than 10 staff | **Verified at primary** https://www.odpc.go.ke/faqs/ (Q6). **But** Q8 lists purposes that must register regardless: direct marketing, insurance, financial services, telecommunications, public sector bodies and others. Agriculture is not listed. Risk: stockist listings could be called direct marketing, and a county-funded service is arguably public-sector. Fee if required: KES 4,000 (micro/small). Legal Notice "265 of 2021": text unreachable (HTTP 403), number not confirmed. Retention, cross-border and DPIA duties not yet researched; get the wording reviewed by someone qualified. Do not state an exemption as fact. |
| Africa's Talking sandbox/USSD | see unit-economics.md |

## 5. Added after review R1 (12 Oct)
- **Salt test (Johnson 1992).** The PDF could not be opened (SSL error, retried). The quantities, 6-hour time, 5-10 grains and 15% threshold are therefore UNVERIFIED. The quantities, time and grain count are not stated in the note, deck, site or engine messages (fixed after review R2). The 15% line IS still stated, in the note (section 3), deck slides 6 and A1 and the engine, but only labelled as a published rule of thumb, unverified for Kenyan conditions, and as the engine's assumption (corrected after review R3, K3-03; an earlier version of this ledger wrongly said it was no longer stated). Secondary web descriptions (a search on 12 Oct, round 2) give a teaspoon of non-iodised salt, 2-3 minutes of shaking and a 15% line, with other sources giving other quantities; no primary FAO page with the wording was found (the FAO grain-drying chapter fetched has no salt test). Treat the whole protocol as PENDING VERIFICATION. Review R3 confirms the site and the engine's TEST_FIRST message no longer carry the quantities: the first message asks for a meter reading and offers the salt test only as a draft (K-01 closed). Iodised salt: unresolved. A web search on 12 Oct only confirmed that Johnson's note says FAO proposed the method in 1985.
- **Moisture limits.** FSA1074 Table 1 puts safe corn moisture at 12% for a year; 13.5% is the East African standard limit (draft), not a one-year storage guarantee.
- **Arkansas tables.** The two PDFs do not say "yellow"; the yellow-dent statement comes from the Bartosik and Maier follow-up (snippet). "0.5% dry-matter loss = one US grade" is a US-grade statement. The table clock starts at harvest; the engine's clock starts at the first test.
- **5%-a-day drift.** Untested, and used for drying as well as wetting. Afzal 2017 (12.5% to 15.64% over 2 months, Kotli, Pakistan) is a wetting final reading and cannot test it. Engine sensitivity, days left on 14 Oct / 15 Oct: 0% a day 43/42; 1% 70/39; 2% 143/38; 5% 261/34; 10% 302/31. Grain at +3 C: 205 days on day 0.
- **Ng'ang'a 2016b.** 41.2% is WEIGHT loss in woven bags (grain damage 77.6% and 82.3%); the week-7 timing is not in the abstracts (unverified).
- **WRI.** 20-36% confirmed; the "storage at least 70%" share only appears in press snippets, so it is no longer used. KES 72 bn is for all food.
- **Ndegwa trial.** Benefit-cost 1.6 / 4.8 are the authors' figures (secondary summaries; see section 6). Abstract only: county (Nakuru), 12.4/3.9 and the bag price are not verified in the primary source.
- **Tubbs 2017.** Cheap hygrometer equilibrium takes 30-45 minutes (15 only for the logger); the 0.6-0.7 point gap is confirmed at two points only.
- **NCPB 13.5%.** Depots without driers only; depots with driers (Kitale, Eldoret, Mois Bridge) accept 13.5-18% and dry it.
- **Bag price.** KES 250-300 is the one source found (ordinary bags); an older article gave Sh200-250 for a hermetic sack. Needs a current retailer quote.
- **Open-Meteo.** Licence needs a visible link ("Weather data by Open-Meteo.com") and CC BY 4.0; free tier non-commercial.
- **USSD.** Safaricom times out after about 30 s of user silence (Airtel 60 s); "160 characters" is not in the cited article. Shared shortcode price KES 5,000/2,000 has no source.
- **Competitors.** MoA-INFO users range 550,000 to 754,063 by source; KAOP 250,000 a month not found; SmartSilo US$800-1,200 is a production cost.
- **People Daily 7.5M bags** (27 Sep 2025) is stale; 2026 snippets put the county forecast at 6.34M cut to 3.62M bags.
- **Fabregas 2025.** Kenya and Rwanda confirmed; the 2-point effect comes from an appendix summary of six programmes (128,000 farmers), not the headline abstract.
- **DryCard.** A cobalt-chloride card at 65% ERH; no maize validation found. Do not imply it is validated.
- **Oracle platform.** The 90-day reclaim is cumulative stopped time and the database "may be" reclaimed. Snippets say the free oracleapex.com workspace is demonstration only (no production or sensitive data); unverified, but a pilot with farmers' phone numbers should not sit on it.

## 6. Added after review R3 (12 Oct): facts the note and deck state, and how far each is checked
| Fact in note or deck | Status |
|---|---|
| Communications Authority: 29.6 m of 78.3 m mobile connections are feature phones (end 2025) | Reported as confirmed in review R2 (CA report); per-row evidence not kept here, recheck before quoting; connections, not people |
| CDC 317 / 125 (the figures quoted in the note) | Reported as confirmed in review R2; per-row evidence not kept here, recheck before quoting on stage |
| Kitale 18.3 C, 63% humidity | A 1961-1990 average (not a forecast); labelled so in the note and deck |
| KMD "currently strong" (El Nino) | KMD wording as quoted; the phrase "very strong" belongs to the NCOF-13 statement only |
| Mekonnen and Hoekstra 1,222 m3 per tonne (maize water footprint) | Reported as confirmed in review R2; per-row evidence not kept here; a global average, not Kenya-specific |
| Oracle 1,000 outbound calls per 24 h (APEX web services) | The cited Oracle documentation page; a default that can change |
| USSD session 180 s; Safaricom times out after about 30 s of user silence | Both figures come from the pages cited in the note, not from the carrier; confirm with Africa's Talking |
| Benefit-cost 1.6 (one season) to 4.8 (three seasons) | The trial authors' own figures (Ndegwa, De Groote, Gitonga, Bruce, Crop Protection 90: 17-26, 2016), as reported in secondary summaries of the abstract (checked 12 Oct, round 4: web search; the ScienceDirect, ResearchGate, Academia and AgEcon pages all returned 403, so the full paper was not read). Not our arithmetic and not shown in the deck; the note (v4.3) states them as the authors' figures on the authors' prices. The same summaries give an abated loss of 8.5% valued at about KSh 307 per bag per season, damage 14% vs 4%, and say bags pay off if used 4 months per season for at least 4 seasons. They did not show 12.4% / 3.9% (the difference, 8.5 points, matches). Our KES 340 per bag-season is our own arithmetic (8.5 points x KES 4,000) |
| USDA 2.2 Mt, 51% below the earlier 4.5 Mt | Read in full via the APEDA copy; usda.gov original not opened (403) |
| Ndegwa 12.4% vs 3.9% loss | Abstract only (secondary summaries do not show these two figures; their 8.5-point difference matches the reported abated loss); county, the two figures and the bag price are unverified at the primary source, and the note's caveat now says so |
| Event name, tracks, "@iLabAfrica, Strathmore x Oracle" | From the organisers' poster and search summaries; the official page was never opened (note front page says so) |
| 15% salt-test line | Published rule of thumb, unverified for Kenyan conditions; engine assumption (see section 5) |
| Alert caps | Engine behaviour, not field-tested: at most four weekly HIGH alerts per test result, the fourth says it is the last, then silence until a new test |

## 7. Added after review R5 (12 Oct)
- **Ng'ang'a 2016a (note ref [4]).** "Hermetic bags stop aflatoxin building up below 14%" and "aflatoxin rose 5-8 times over 35 weeks in woven bags" come from the paper's record as cited; the paper was NOT re-opened here. Status: secondary/unverified. The note (v4.4) says so next to the figures. Do not quote the 5-8x figure on stage without opening the paper.
- **Johnson 1992 (salt test, 15% line).** Never opened; the 15% threshold and the protocol are UNVERIFIED. Any site label of "source" for it should read "secondary, unverified" (site wording is another workstream; see review r5 K5-02).
- **USDA GAIN KE2026-0017.** Read in full via the APEDA copy; the usda.gov original is unreachable. The right source label is "read in full via the APEDA copy" (K5-03).
- **Ndegwa trial county.** Not verified (abstract only); do not name the county in a title (K5-04).
- **Legal Notice 265 of 2021.** The Notice text was unreachable. Only the ODPC FAQ was read at the source (Q6, Q8). Mark the FAQ verified and the Notice number unconfirmed (K5-05; note ref [37] says so in v4.4).
- **Privacy-page specifics.** "Tally hosted in the EU", "Brevo France, EU" and the DPA section numbers (48-50) are NOT in this ledger: unverified. Retention rules are not yet written (note and /pilot say so). Do not repeat these as fact until checked.
- **"Drought cut the crop, so each sack is worth more."** An inference from the USDA forecast cut and local reports, not a measured price. Say "likely worth more" (note v4.4, slide 3 already hedges).
- **US$4 hygrometer.** Unsourced; do not quote it as a price.
