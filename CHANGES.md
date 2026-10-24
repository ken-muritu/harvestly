# Harvestly v2 → v3: what was wrong and what changed

> The review reports (`review/`), pitch materials (`pitch/`) and superseded drafts (`docs/_superseded/`) referred to below are not included in the public repository.

Checked 9 October 2026 against primary sources wherever they could be reached. Reviewed by three independent reviewers: two on the engine, one on the note.

## Concept note: factual errors fixed

| v2 said | Problem | v3 |
|---|---|---|
| "Kenya grows about 4 million tonnes" (2023/24–2024/25) | Out of date. USDA (28 Aug 2026) cut its forecast for 2026/27 to 2.2 Mt after the drought (v3 wrongly said "down 51%"; see v3 to v4). | Uses the 2026 drought figures. |
| Purdue: "dry grain below 13% before storage" | That line is about seed, not grain for storage. | Removed. The 13.5% (EAS 2) and 14% (hermetic, Ng'ang'a 2016a) limits are used instead. |
| PICS trial: under 1% vs 41.2% | Correct, but the trial was in Makueni, not the North Rift. | Cited with its location, and used for the week-7 insect reminder. |
| "Very strong El Niño" attributed to KMD | KMD says "currently strong". "Very strong" is from the NCOF-13 statement. | Quotes KMD exactly, including its advisory on drying, hermetic storage and aflatoxin. |
| KES 72 bn, cited to People Daily | The figure originates in the WRI report and covers all value chains. | Dropped as a headline. The note uses WRI's maize-specific figures. |
| Uptake "floor" of 2% | Fabregas et al. report an average effect, not a floor. | "Base case (trial average)". |
| Impact: 14% baseline loss, 2% after acting | Neither figure came from a trial. | Uses a Kenyan randomised trial (Ndegwa): 12.4% vs 3.9% loss over 4 months. |
| Impact per 1,000 farmers × 10 bags | The 10 bags per farmer was an assumption. | Reported per 10,000 bags stored, plus how it scales. |
| Phones: The Star infographic | A secondary source. | Cites the Communications Authority report directly. |
| One Acre Fund 11.5% / 30% (in v1) | Misattributed: the trial was Mumias Sugar / IPA, and the 30% figure does not exist. | Removed (v2 had already dropped it). |

## Concept note: gaps closed

- The edge is now on page 1.
- The note was inconsistent about what causes the loss. v3 said insects cause most weight loss (not supported; corrected in v4), moisture drives mould and aflatoxin, and the impact estimate counts only the switch to hermetic bags.
- Oracle limits are now stated:
  - about 3–6 simultaneous users on Always Free;
  - the database stops after 7 days without activity;
  - 1,000 outbound calls per day by default.
- Channel limits are now stated:
  - a farmer must message the Telegram bot before it can alert them;
  - Safaricom USSD menus are limited to 160 characters and sessions to 180 seconds;
  - Africa's Talking sandbox SMS only reaches the simulator;
  - the free Open-Meteo tier is for non-commercial use only.
- Risks added:
  - the tables are not validated for Kenyan white maize;
  - salt-test errors, including Kenyan table salt being iodised;
  - data protection (ODPC registration rules).
- All five official tracks were checked. The two tracks the note claims are named exactly as on the official list.
- References are numbered in order of first use, and every reference is cited.

## Engine: bugs fixed

1. **Dead end.** Salt test passed, then grain sealed: the farmer got "too wet to seal" every day, forever.
2. **Weather adapter.** It asked for 7 past days and then treated the oldest one as "tomorrow".
3. **Wrong wording:**
   - "~365 safe days left" in a rain alert;
   - "0% chance" when the alert was triggered by millimetres of rain;
   - "about 0 days".
4. **Invented countdown.** Untested grain got a countdown based on a made-up 20% moisture.
5. **Silence.** After the first alert, a HIGH batch was never warned again, even after it passed its safe limit.
6. **Replies ignored.** SALT, SEALED and "1" did not change the engine's state.
7. **Estimate shown as a reading.** A drifted estimate was labelled "meter 18.0%".
8. **Estimate declared grain dry.** An estimate could say "dry enough to store", and the farmer could then be told to open the bags seconds later.
9. **Loops and floods:**
   - a RETEST ↔ SALT NO loop, with about 12 messages a month;
   - up to 60 rain alerts in 60 days;
   - a reply used up the evening rain alert.
10. **Lost or over-strict alerts:**
    - escalations were lost if a reply had just been sent;
    - hermetic batches went silent for good;
    - the insect reminder told farmers to seal wet grain.
11. **Crashes and bad reply handling:**
    - the engine crashed on typos such as METER 135 or HYGRO 100;
    - SALT NO overwrote a meter reading taken the same day;
    - a closed batch kept giving advice.
12. **Countdown halving missed.** A forecast that cut the countdown from 261 to 34 days sent nothing, because the risk level stayed LOW. This was the core pitch moment.

## Engine: structure

- One function, `advice()`, decides the current recommendation.
- `daily_run()` decides when to send.
- `respond()` answers replies.
- Three rules:
  - only a meter or hygrometer reading clears grain as dry;
  - estimates only trigger a re-test;
  - every repeat is spaced and capped.
- Every parameter is labelled as SOURCE, CALIBRATION or PROGRAMME.
- 68 tests.
- `vectors.json` holds reference results that the PL/SQL port must reproduce.

## Verified as correct

- Both data tables match their publications, all 196 + 63 cells:
  - Arkansas FSA1074 Table A;
  - Arkansas FSA1058 Table 1.
- Hackathon dates and track names: NOT verified at the official page (it was unreachable); they come from search summaries and the team poster. See v3 to v4 below.

## Not verified at a primary source

These figures come from secondary or abstract-level reading. Check them before quoting them on stage:

- De Groote et al. 2023 (CIMMYT): one in six farmers uses hermetic bags, and insects are the main cause of weight loss. (v4 correction: the insect-cause claim is not supported by the primary source and was removed; see v3 to v4 below.)
- Bartosik & Maier 2005: abstract only.
- USDA KE2026-0017: read as a search-result summary and via a mirror (the USDA site was not reachable). The PDF had not been read at v3; it was read in full via the APEDA copy on 12 Oct (see v4 to v4.1 below).

# Concept note v3 to v4 (12 October 2026, after review R1)

Source: `review/r1-claims.md`; per-finding status in `review/r1-claims-fixes.md`.

- Removed "Farmers never pay". The pilot design does not charge farmers for alerts; the funding model is undecided and nobody has agreed to pay.
- USDA: "cut its forecast by half to 2.2 Mt". The 51% is against the earlier 4.5 Mt forecast, not last year, and was from summaries at the time (PDF unread; confirmed in v4.1). "Down 51%" removed.
- Removed "insects cause most of the weight lost in storage" and the "storage at least 70%" share (not in the primary source). The De Groote survey measured insect losses only.
- The 261-to-34 headline is labelled illustrative, with its sensitivity to the untested 5%-a-day drying assumption (0%: 43 then 42; 2%: 143 then 38; 5%: 261 then 34; 10%: 302 then 31) and the note that the clock starts at the first test, not harvest.
- A displayed 365 days is the look-ahead cap. Messages say "storage time left ... (estimate)", never "safe".
- SMS, USSD, Telegram, the bot and the dashboard are described as planned, not built. "Built on" became "Designed on".
- Oracle PL/SQL port: written by the team with AI help on 12 Oct (the first onboarding day; v4 said "before the bootcamp", corrected in v4.1), never compiled. It is not "bootcamp work".
- Salt test: quantities, 6-hour time and salt type removed as unverified (primary source unreachable); it only screens and never clears grain. Iodised-salt question stays open.
- Open-Meteo credited with link and CC BY 4.0; free tier is non-commercial.
- KES 250 to 300 is an ordinary-bag price in the one source found; hermetic prices unconfirmed. Impact table labelled an illustrative upper bound, gross of bag cost.
- ODPC: exemption needs BOTH turnover under KES 5M and fewer than 10 staff; direct marketing must register regardless.
- NCPB 13.5% applies at depots without driers; drier depots accept wetter grain.
- Competitor numbers hedged (MoA-INFO users vary by source; KAOP 250,000 a month not confirmed; Silo Africa US$800 to 1,200 is a build cost). Trans Nzoia 7.5M bags (Sept 2025) marked stale.
- USSD: Safaricom times out after about 30 s of silence; "160 characters" dropped (not in the cited source).
- Pilot, plan and asks are worded as proposals; no commitments. All company endorsement lines ("Built by ...") removed from the deck, briefs, docs and README. The one contact address is a single flagged constant (open-items #15).
- Corrections to earlier CHANGES text: hackathon dates, eligibility and tracks did not come from the official page (unreachable; search summaries); USDA was read from a search summary and a mirror, not an "Indian government mirror" alone.

# Concept note v4 to v4.1 (12 October 2026, after review R2)

Source: `review/r2-final.md`; per-finding status in `review/r2-claims-fixes.md`. v4 files are in `docs/_superseded/`.

- Reference [22]: the dead Purdue link is replaced by the DOI (https://doi.org/10.1007/s12571-016-0567-9). [29] now links the CC BY 4.0 licence.
- Salt test: the note, deck, Q&A and verification log say the protocol is pending verification. No quantities or times are stated anywhere in the docs or deck. The farmer-facing TEST_FIRST message in the engine and two site pages (`how-it-works`, `partners`) still carry the old quantities; that is outside this document pass and is a decision for Ken (open-items H2).
- USDA: the "PDF not read" caveat is closed (full report read via the APEDA copy; 2.2 Mt, 51% from the earlier 4.5 Mt).
- PL/SQL timing: "before the bootcamp" / "pre-dates the hackathon" replaced by "written on 12 Oct, the first onboarding day" (Ken to confirm).
- "Payment never changes the advice" now reads "is designed so that payment does not change the advice". Deck formula slide says "storage days", not "safe days". Farmer interviews are no longer in the future tense.
- Metadata: note author "Harvestly team"; deck subject set. README path for `plsql/` fixed. Slide 6 now marks 15% as the engine's assumption.

# Concept note v4.1 to v4.2 (12 October 2026, after review R3)

Source: `review/r3-final.md`; per-finding status in `review/r3-claims-fixes.md`. v4.1 files are in `docs/_superseded/` (and on Drive). Docs, deck and Drive only; the site, engine and PL/SQL were not touched in this pass.

- HIGH-alert silence (K3-01): the note no longer says a HIGH batch is "not left silent". It now says at most four weekly HIGH alerts per test result, the fourth says it is the last reminder, then silence until the farmer sends a new test. Same wording added to the deck notes (slide 5), README, pitch-prep and the Q&A bank (Q14).
- First message (K3-02): deck A3 row 1 and note sections 3 and 9 now say it asks for a meter reading first and offers the salt test only as a draft, unconfirmed. "Step-by-step SMS" removed.
- 15% salt line (K3-03, K-08): labelled a published rule of thumb, unverified for Kenyan conditions, and the engine's assumption, in note section 3 (step 2 and the engine table), the slide 6 notes and A1. `research/verification.md` section 5 corrected: it had said the line was no longer stated.
- Deck: slide 4 and A5 sources cite note v4.2 (K3-04); slide 9 transition reads "what we would propose next" (K3-05); slide 3 notes say "hermetic storage" outside the verbatim KMD quote (K3-06). Deck rebuilt (pptx and pdf), changed slides viewed.
- Note: the Ndegwa caveat now names the county and the 12.4% and 3.9% figures as unverified (K3-07); the front page says the event and track names come from the organisers' poster, and gives the contact address and demo URL (K3-08); the 10-11 Oct activities read "no results recorded as of 12 October" (K3-09, D-03; Ken to fill real results); BOM removed (K3-10).
- Docs: `verification.md` has ledger rows for the facts the note and deck state (D3-02) and its USDA heading is corrected (K3-10); open-items H2 and M2 closed, the company name scrubbed from open-items (D3-01, D3-05); `site-brief.md` says "storage days" (D3-03); Drive re-synced, `.pyc` files removed, README, CHANGES and brand added (D3-04, D-02).
- Still open and Ken's: see `pitch/open-items.md` ("Only Ken can do this"). Still not fixed here because they are site, engine or PL/SQL: F-01 to F-10, P-01 to P-06, S3-*, E3-*, C3-*, R1-12.

# Concept note v4.2 to v4.3 (12 October 2026, after review R4)

Source: `review/r4-final.md`; per-finding status in `review/r4-claims-fixes.md`. v4.2 files are in `docs/_superseded/` (and on Drive). Docs, deck, research and Drive only; the site, engine and PL/SQL were not touched here.

- Benefit-cost (K4-01): the 1.6 (one season) and 4.8 (three seasons) ratios are the trial authors' own figures (Ndegwa, De Groote, Gitonga and Bruce, Crop Protection 90: 17-26, 2016), seen in secondary summaries of the abstract; the full paper and the publisher pages could not be opened (403). The note now says so, and the ledger no longer calls them "our own arithmetic". Our KES 340 per bag-season is ours; the authors' is about KES 307. Reference [31] now cites the journal paper.
- Deck slide 5 (K4-02): the third rule reads "at most four weekly urgent alerts, the fourth says 'last reminder', then silence until a new test".
- Deck A7 (K4-04): the APEX dashboard box now has an arrow from the database.
- Note (K4-03): the "Test says wet" quote is the engine's words again; the rule-of-thumb caveat follows the quote. The first-message example reads "e.g. METER 14.2" (E4-01 was fixed in the engine by another worker).
- Drive (D4-01, D4-02): `docs/SITE.md` re-copied, the six `.pyc` files deleted, v4.3 uploaded, v4.2 archived under `docs/_superseded/` on Drive; every Drive file downloaded and searched.
- Open items: Brevo item rewritten (no acknowledgement, no tracking claim), test-email cleanup widened, new item 11 (squash the git history before the repo is shared).

# Concept note v4.3 to v4.4 (12 October 2026, after review R5)

Source: `review/r5-final.md`; per-finding status in `review/r5-claims-fixes.md`. v4.3 files are in `docs/_superseded/` (and on Drive). Docs, deck, research and Drive only.

- Note: example reading is "METER 14.2" everywhere (N5-01); "Less grain, likely worth more" (N5-06); reference [4] (Ng'ang'a 2016a) is flagged as not re-opened, next to the 5-8x figure (N5-07); reference [37] says the Notice text was unreachable and only the ODPC FAQ was read (K5-05).
- Deck (K5-01): slide 17 (A7) speaker note now says the PL/SQL files were written on 12 Oct, the first onboarding day (not before the hackathon), as in the note, pitch-prep, qa-bank and open-items. A8 and slide 5 notes say "storage total-loss percentage" (N5-04).
- Research (K5-06, N5-05): the week-7 reminder is marked "our reading" in qa-bank and pitch-prep; the Always Free answer no longer says it is fine for a 200-farmer pilot; the US$4 hygrometer claim is softened and marked unsourced. `verification.md` has section 7 (Ng'ang'a 2016a, Johnson, USDA label, Ndegwa county, Legal Notice 265, privacy-page specifics, drought wording).
- Docs (N5-02): pitch-prep "Updated" line no longer says "after R1".
- Drive (D5-01): `docs/SITE.md` and `pitch/build_deck.js` re-copied; v4.4 uploaded, v4.3 archived.

# Concept note v4.4 to v4.5 (12 October 2026, after review R6)

Source: `review/r6-final.md`; per-finding status in `review/r6-claims-fixes.md`. v4.4 files are in `docs/_superseded/` (and on Drive). Docs, deck, research and Drive only.

- Status (K6-01): the deck, note, qa-bank, open-items, pitch-prep and README now say what exists: a Telegram TEST bot (@HarvestlyBot) answers 24/7 from a Vercel webhook with the real engine on simulated weather, sends nothing unprompted, keeps state in Turso (Ireland); the Oracle/ORDS version, SMS, USSD, the dashboard and real weather are not built. No farmer has been enrolled and no alert has been sent.
- Deck: slides 5, 6 (notes), 7 and A7 reworded; slide 7 gets the bot under Built and the Oracle version under Not built.
- Pitch-prep: Plan A is now the live bot demo (/demo or JOIN and METER), with a fallback to Plan B if Telegram or the network fails and a checklist (BotFather picture, disable group joining, test /start and /demo before pitching). qa-bank has a new question 9b on the bot.
- Open items: item 3 (bot name) closed in substance, BotFather steps listed; item 13 status updated.
- Docs (K6-03): SITE.md covers the privacy bot section and the `harvestly-bot` project; TELEGRAM.md counts the poller and webhook tests (done by the bot worker).
- Drive (D6-03 to D6-05, N6-11): bot poller files, `bot/`, site sources and cards uploaded; `.gitignore` and `vectors.json` strays at the top level and the duplicate `engine/plsql` and `engine/python` removed after checking; `.vercel`, `review/`, `.pyc`, `node_modules` excluded.
- Not done here (other workers): K6-02 and S6 (site), B6 (bot), N6 (engine/bot).

# Concept note v4.5 to v4.6 (12 October 2026, after review R7)

Source: `review/r7-final.md`; per-finding status in `review/r7-claims-fixes.md`. v4.5 files are in `docs/_superseded/` (and on Drive). Docs, deck, research and Drive only.

- NASA (K7-01): note, README, both decks, speaker script, qa-bank (new 9c "Is the weather real?"), pitch-prep and open-items now say that NASA POWER observed weather (satellite/model estimate, one grid cell of about 55 by 70 km, about a day behind, not on-farm, not a forecast) is an optional calculator prefill and a /weather bot command; the engine's forecast in the test bot is still simulated; a dated MODIS image of Trans Nzoia (20 December 2025, scattered cloud) is on /pilot; catch-up over observed days is future work. The 18-slide deck no longer lists "Real weather" as not built; it lists the real forecast for the engine and the catch-up instead.
- Open-Meteo credit (B7-01, docs side): the note, README and slide A7 call Open-Meteo the designed forecast source that the test bot does not call; the code fix is another worker's.
- Open items (N7-07): "note (v4.4)" now reads v4.6; new item A15, a 20-second screen recording of the Telegram demo as a network fallback.
- 5-slide deck and 7-minute script: slide 3 and the script carry the same NASA lines; the team placeholders on slide 1 are unchanged.

# Concept note v4.6 to v4.7 (12 October 2026, after review R8, claims side)

- NASA wording (K8-01): the calculator button "Show recent weather near Kitale" shows one line of recent NASA POWER estimates as text and changes no calculator values (it is not a prefill since r7). The data lag is up to a few days (on 12 Oct the newest day was 9 Oct), not "about a day". Corrected in the note (v4.7), README, both decks and the speaker notes, the 7-minute script, qa-bank 9c, pitch-prep and open-items. The K7-01 entry above is left as history. v4.6 is archived in `docs/_superseded/`.
- Oracle (K8-02): slide 1 of the 5-slide deck now reads "Designed for Oracle", with PL/SQL written and not yet compiled or run on Oracle.
- Pitch eligibility (K8-04): open-items A1 and the email draft (still NOT sent) now say plainly that Harvestly was not among the ten names read out in Session 1, and ask whether Harvestly is a pitching team; pitch-prep says the pitch material is conditional on the answer. A2 corrected to the transcript quote.
- Script and deck (K8-03, K8-05, K8-06, N8-01, N8-02, N8-03): "Here is how it works" and "designed to combine ... every evening"; team size removed as a rule (unconfirmed); themes labelled as our reading; timings matched between script and speaker notes (slides 0:40, 0:50, 2:30, 1:20, 1:15, 0:25 spare); "co-ops" wrap removed; the PL/SQL parity claim now says a Python mirror matched the engine and the PL/SQL itself is not yet run.
- Docs (N8-05, N8-06): open-items intro, A9 quote, A13/A15 merged, README pitch line, Drive top-level file note in `docs/SITE.md`.

# After review R9 (12 October 2026, text side)
- K9-01: open-items A1 now starts with step 0 (search inboxes and spam for the organisers' selection email of about 6 Oct; Session 1 [~04:24] and [~08:55] say teams were already told) and says 30 shortlisted teams (transcript [~04:24], twice; the single "13" at [~10:24] is a mis-hearing). `email-to-leif-draft.md` is now a fallback and is still NOT sent.
- K9-02: research/hackathon-brief.md no longer says Harvestly is a finalist.
- K9-03: pitch-prep.md marked superseded by the 5-slide deck and the 7-minute script (7 + 3 minutes, 5 slides, Thu 15 Oct 4 pm); "not published" removed.
- K9-04: the ask no longer includes Oracle coaching (the winners' prize); it is now a co-operative and county introduction, two moisture meters and ward-level harvest and weather data. 5-slide and 18-slide decks, script and pitch-prep updated and rebuilt.
- N9-01, N9-02: 18-slide deck cites note v4.7; open-items title, NEW section and A-order fixed; README says R1 to R9. N9-03 and N9-04 (site and bot) and N9-05 (bootcamp notes) are outside this round.
- D9-01: Drive mirror re-synced.
