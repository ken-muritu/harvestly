# Harvestly hard-questions bank (2026-10-12)

Answers use the concept note v4.7 and the research files here. [V] = verified, [S] = secondary, [A] = our assumption, [?] = unknown, say so. Keep answers to 20 seconds.

## Science and validity
1. **The tables are for US yellow corn. Why trust them for Kenyan white maize?**
Not validated, and we say so. The Arkansas PDFs do not say "yellow"; a Bartosik and Maier follow-up says the standard corn curve is for yellow dent and white and waxy corn need their own [S]. Our moisture table reads about 0.6-0.7 points wetter than one set of measured maize points (two points only), so errors lean towards a false alarm, not missed damp grain. Only a meter or hygrometer can clear grain; the pilot calibrates against meter readings. Caveat: even that comparison used non-Kenyan points.

2. **Iodised salt: does the salt test still work?**
We do not know. The secondary descriptions we found ask for non-iodised salt; Kenyan table salt is normally iodised, so we planned a side-by-side test of salt versus meter on the same maize (10-11 Oct); no result yet. We have not verified the quantities, timing or salt type (the primary source was unreachable), so do not quote them [?]. Whatever the answer, the salt test never clears grain.

3. **How accurate is the salt test at all?**
It is a coarse line at about 15% moisture, a published rule of thumb that is unverified for Kenyan conditions, designed for "clearly wet or not" [S, Johnson 1992 not opened; details unverified]. We use it only to start a countdown (at an assumed 18% if sticky, 14.5% if not) and to trigger a meter check. 18% and 14.5% are our assumptions to calibrate.

4. **Your drift rate is 5% of the gap a day. Where from?**
It is an untested assumption, applied to drying as well as wetting. One Pakistani trial (12.5% to 15.6% over about 2 months in woven bags) is the same order of magnitude for wetting but cannot test it. To calibrate with meter spot checks. At 0% a day the demo reads 43 days, not 261. A different grain, bag or climate could change it.

5. **Grain temperature is not air temperature.**
Right; the engine uses daily air temperature as a stand-in and flags it. In small sacks indoors the difference is modest, but it is a known error.

6. **"1 ÷ storage days" is a US table for 0.5% dry-matter loss. Does that reflect mould or aflatoxin?**
It is a quality-loss proxy (0.5% dry-matter loss, a US grade-level statement), not an aflatoxin predictor. We call it "storage days left (estimate)", never "safe". Aflatoxin needs a lab test. The table's clock starts at harvest; ours starts at the first test.

7. **Insects cause most storage loss, but you model moisture. Isn't that the wrong problem?**
Partly. De Groote et al. 2023 measure losses to two insect pests only; moisture is not compared [S]. We do not say insects cause most weight lost. We treat insects with a dated reminder at week 7 (Makueni trial; the week-7 timing is our reading, not in the abstract) and a pointer to hermetic bags; moisture is what drives mould and aflatoxin and is what a farmer can act on this week. Do not quote the 36% loss figure; the authors say it looks high.

8. **Is 2.2 Mt "down 51%" right?**
We do not say that. The 51% is the cut against USDA's earlier 4.5 Mt forecast; against last year it is roughly a third lower (derived) [S]. Say "USDA cut its forecast by half to 2.2 Mt", with the base flagged. Base confirmed in the full report (read via the APEDA copy, 12 Oct); see verification.md.

## Product and channels
9. **Do farmers with feature phones actually use USSD? Where is your USSD?**
USSD is not built, and neither is SMS. What exists is a Telegram test bot (@HarvestlyBot, built 12 Oct with AI help) that runs the real engine on simulated weather, replies only when messaged, and has no farmers; plus the engine output on a website. A dedicated Safaricom USSD code costs KES 145,000 setup and KES 70,000 a month and takes 3-4 weeks [V, AT page of 27 May 2025]. A pilot could start on SMS and we would ask AT about a shared USSD code and shortcode (no price source found for a shared shortcode).

9b. **Is the Telegram bot live? Can I try it?**
There is a test bot, @HarvestlyBot, built on 12 Oct with AI help. It runs the real Python engine on a fixed simulated forecast (not a real forecast). /weather and the calculator chip show NASA POWER observed weather as context only, answers 24/7 from a Vercel webhook (Dublin) and keeps chat state in a Turso database in Ireland. It replies only when you message it; it sends no alerts unprompted, no farmer has been enrolled, and it is a prototype test, not a service. /demo walks through the seven example messages. The Oracle/ORDS version, SMS, USSD and the dashboard are not built. Telegram itself sees the conversation (docs/TELEGRAM.md, site /privacy).

9c. **Is the weather real? I saw NASA data.**
Two different things. The advice runs on a simulated forecast; the real forecast is the designed source (Open-Meteo); the test bot shows it as context in /forecast (with WeatherAPI.com and OpenWeather as fallbacks) but does not feed it to the engine. Separately, the website calculator's optional button "Show recent weather near Kitale" (one line of text; it changes no calculator values) and the bot's /weather show NASA POWER recent observed weather: a satellite and model estimate for one grid cell of about 55 by 70 km, with a data lag of up to a few days (on 12 Oct the newest day was 9 Oct), not measured on the farm and not a forecast [V: research/nasa-due-diligence.md]. It is context, not input: the calculator inputs are never filled from it, and the page says so. Catch-up over observed days since a farmer's test is future work. The /pilot page also has one dated MODIS image of Trans Nzoia (20 December 2025, scattered cloud); farms are not visible. Not endorsed by NASA.

10. **Safaricom approval for the USSD code?**
Lead time is 3-4 weeks after payment per Africa's Talking [V]. We found no public Safaricom approval criteria. Not a hackathon-week deliverable.

11. **Sandbox SMS only reaches a simulator. So nothing real has been sent?**
Correct; say it before they do. Real SMS needs a live AT account with a top-up. Cost of SMS for 200 farmers: about KES 6,400 on our assumptions.

12. **Why not hardware sensors?**
Because the farmer owning a sack cannot afford them: a SmartSilo is reported to cost US$800-1,200 to build, which is a production cost, not a price [S]. A low-cost hygrometer (US$4 is an unsourced figure) or the free salt test plus a forecast is a cheaper way into the decision for most farmers; we have not measured how much of the decision value it captures. Hardware is complementary: Silo-type customers are a different, richer segment.

13. **Literacy, language, trust: will farmers do the salt test and reply with codes?**
Unknown, which is why a pilot would measure test completion rate first. Messages are in English and Kiswahili and are short. Extension officers and co-ops can enter readings on a farmer's behalf via the dashboard.

14. **Alert fatigue or false alarms?**
One unprompted message a day maximum (replies are answered at once), spaced and capped repeats, STOP at any time. A batch at high risk gets at most four weekly alerts per test result; the fourth says it is the last reminder, then the engine stays silent until a new test. We track false-alarm and opt-out rates as pilot metrics, not as claims.

15. **What if the phone has no forecast coverage or the data source fails?**
Forecast cached per ward; missing days are flagged and rain is never recorded as 0 mm when missing.

## Money
16. **Who pays?**
Not decided. The pilot design does not charge farmers for alerts. Hypotheses: a county, co-op or donor funds a pilot; later per-tonne fees from warehouse operators and bag stockists. No signed interest, no talks held; the unit-economics file marks the prices as assumptions.

17. **Cost per farmer per month?**
SMS: about KES 32 per farmer per 4-month season at KES 0.8 per SMS and 40 SMS (about KES 8 a month) [A on volume; rate from AT, S]. A shared shortcode is excluded (no price source found). Dedicated USSD would add KES 145,000 setup plus KES 70,000 a month, which only makes sense at roughly 10,000 farmers or more.

18. **Doesn't "farmers never pay" break when they reply by SMS? (We do not say it.)**
Possibly: inbound SMS to a shortcode is normally charged at the farmer's standard rate (about KES 1, unchecked). Fix: ask AT for a toll-free or reverse-billed keyword, or say "alerts are free; replies cost an ordinary SMS".

19. **What is your moat if Safaricom or MoA-INFO copies it?**
Honestly small: the engine is simple. Defensibility is the ward-level farm-gate moisture dataset, calibrated parameters from the pilot, and being a module partners can license. We position as a module for MoA-INFO/KAOP, not a rival.

20. **How do you make money from warehouses if few farmers deliver there?**
We do not know the conversion rate; that is a pilot metric (share meter-tested at 13.5% or below before delivery). The break-even per-tonne fee is about KES 40 for a 0.9 t farmer [A].

## Data protection and ethics
21. **ODPC registration?**
The exemption applies only with turnover under KES 5M AND fewer than 10 staff [V, ODPC FAQ]. But ODPC lists purposes that must register regardless, including direct marketing, insurance, financial services and public-sector bodies. Stockist listings could be read as direct marketing; a county-funded service may count as public. Plan to register (KES 4,000 for micro/small; one source says certificates last two years) if either applies, and keep consent, minimal data (no ID numbers), and a STOP command. Agriculture is not on the list. The exemption needs BOTH turnover under KES 5M and fewer than 10 staff; do not say we are exempt. Get the wording reviewed by someone qualified.

22. **What personal data do you hold? Location?**
Phone number, ward, harvest date, bag count, storage method, test results. Ward-level location only. Retention and deletion rules need writing before the pilot [?].

23. **Is the stockist listing paid placement that biases advice?**
Payment never changes the advice; listings are labelled. Every dry-grain message points to hermetic bags in general, not a brand.

24. **Safety: what if the advice is wrong and a farmer eats mouldy grain?**
Messages say remove mouldy grain and not to eat it or feed it to animals, and claim only "not proven dry" or an estimate, never "safe". Check the engine templates say so before 16 Oct. Aflatoxin cannot be seen or tested by us.

## Impact honesty
25. **Is your impact estimate real?**
It is an illustration, not a measurement. It multiplies a trial effect (12.4% vs 3.9% weight loss; abstract only, county and bag price unverified) by a 2-point adoption effect that SMS-advice trials found for recommended practices in general, applied here to bag switching [abstract-level]. Gross of bag cost: an illustrative upper bound. At 2% switching, per 10,000 bags saved: 17 bags, KES 68,000. We count only hermetic switching. No trial shows Harvestly itself reduces loss.

26. **Why did your concept note previously cite Makueni and now Nakuru?**
The PICS-style under-1% versus 41.2% WEIGHT-loss result is Makueni (reference [22]; grain damage there was 77-82%); the 12.4 vs 3.9% trial is [31] (Nakuru is unverified: the abstract does not confirm the county). Both are cited with their locations. Make sure you can say which is which.

**26b. Where does the benefit-cost 1.6 to 4.8 come from?** The note quotes 1.6 (one season) and 4.8 (three seasons) as the trial authors' own figures, on their prices, seen in secondary summaries of the abstract; we did not read the full paper and the ratios are not ours. Our KES 340 per bag-season is our own arithmetic, and the authors' figure is about KES 307. Not on the deck.

27. **"Water embodied in saved maize" is a global average. Is that a green claim?**
It is a stewardship framing using Mekonnen and Hoekstra's global average [33], not a measured saving for Trans Nzoia. Only quote it as "about", if at all.

## Oracle and scaling
28. **Always Free limits?**
Verified at Oracle docs (the 90 days is cumulative stopped time and the database may be reclaimed): 2 instances of 20 GB, 30 sessions, about 3-6 simultaneous APEX/ORDS users, auto-stop after 7 idle days, reclaimable after 90 stopped days, 5-minute cold start after a restart, home region only. Fine for a demo. The ledger (verification.md section 5) says farmer phone data should not sit on a free workspace, so a real pilot with farmers' numbers needs a paid or otherwise approved setup; to decide. Keep it warm before the pitch.

29. **Outbound call limit?**
APEX default 1,000 web-service calls a day per workspace (raisable) [per note]; one forecast call per ward, so Trans Nzoia needs a few dozen.

30. **Scaling beyond Trans Nzoia?**
Engine is crop-agnostic only in structure: other crops need their own tables. Ward-level forecast caching scales linearly with wards, SMS linearly with farmers. Open-Meteo free tier is non-commercial and needs a visible link-back credit, so production needs a KMD/KAOP agreement or a paid plan.

31. **What did you build before the hackathon versus during?**
Be ready: the Python reference engine (with tests) was built before 9 Oct, and the PL/SQL was written on 12 Oct, the first onboarding day, with AI help, never compiled. The Telegram test bot (Vercel webhook, simulated weather) was also built on 12 Oct, with AI help. The Oracle/ORDS handlers (written, not run), SMS, USSD and the dashboard are not built. The hackathon rules on pre-existing work could not be found; disclose rather than wait to be asked.

32. **How will you know it worked?**
Primary metrics: test completion, alert-to-action, share meter-tested before sealing, false alarms, opt-outs, self-reported loss against non-users. We found no randomised trial of SMS storage advice, so the pilot is a staggered roll-out.
