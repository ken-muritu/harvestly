# Harvestly risk engine v4 (Python reference)

Python 3.9+, standard library only.

```
python3 -m unittest -v test_engine     # 98 tests
python3 make_vectors.py                # regenerates vectors.json (the port contract)
```

## Files

| File | What it is |
|---|---|
| `harvestly_engine.py` | The engine: data tables, moisture drift, storage-life accounting, advice, send rules, reply parsing, weather adapter. |
| `test_engine.py` | Unit tests: tables, physics, advice, evening decisions, replies, SMS limits, weather adapter, the pitch demo, and a check that `vectors.json` is up to date. |
| `make_vectors.py` | Generates `vectors.json` by driving the engine through `respond()` and `daily_run()`, the same entry points production uses. |
| `vectors.json` | Reference results: 49 EMC values, 60 storage-time values, 3 day-by-day scenarios (the pitch demo, salt pass then seal, dry grain re-wetting) with the exact message text, the displayed strings and the exact values, plus rounding, evidence, opt-out, normalise, address-hash and days-left sections. The PL/SQL and JS ports must reproduce them exactly. |

## How it decides

- `advice(batch)` gives the one current recommendation, from state alone.
- `daily_run()` is the 17:00 job. It catches up un-simulated days, then sends at most one proactive message, in this order of priority:
  1. rain in the next 24 h while the farmer is drying;
  2. a changed recommendation;
  3. a worse countdown (risk level up, or days left halved and 60 or fewer);
  4. a spaced, capped reminder;
  5. the one-off insect reminder;
  6. a HIGH_ALERT fallback: a HIGH batch whose normal messages are capped still hears weekly, at most 4 per test result, the last one saying so.
- `respond()` answers a farmer's reply straight away. Replies never use up the evening slot.

Four rules:

1. Only a meter or hygrometer reading clears grain as dry. A salt test or the model's estimate never does.
2. An estimate that moves a full point past the salt-test line (16 % up, or 14 % down) triggers a re-test. The engine never orders drying on an estimate alone.
3. Every repeat has a spacing and a cap. A HIGH batch whose normal messages are capped gets a weekly HIGH_ALERT, at most 4 per test result; the 4th is a last-chance message ("Our last reminder. Retest: reply e.g. METER 14.2 (your own reading) or SALT YES/NO to restart"), after which the engine is silent on purpose (diagnostics flag `high alerts used up`) until a new test result arrives (review R2 C-12).
4. A message that did not reach the farmer (SKIPPED, CANCELLED, finally FAILED) burns no cap: `revert_undelivered` takes it back out of the history and restores `last_alert`, `last_advice`, `told_*` and `rain_unacked`.

## Changes after review R1

- **Wording.** No message says "safe" or promises a future message. The STATUS text says what was measured and when,
  labels the time left an estimate (`Storage time left: about 12 days (estimate)`), and a result of 90 days or more is shown as
  "3 months or more". The clause ", falling fast in damp weather" is added only for grain in permeable storage with a countdown
  of 90 to 364 days; a sealed bag (it does not follow the air) or a countdown at the 365 cap (`days_left_capped`, "365 or more",
  not a prediction) never gets it (review R3 S3-01). The closing HIGH alert names only commands the parser accepts:
  "reply e.g. METER 14.2 (your own reading) or SALT YES/NO" (R3 E3-01, R4 E4-01).
  **Example numbers (R4 E4-01, decision).** Every example reading in a message (TEST_FIRST, HELP, the closing text) is 14.2, above the 13.5 limit. A farmer who copies an example literally records a 14.2% reading: the verdict is NOT_PROVEN, never DRY, and the reply echoes "meter 14.2%", so a copy can neither clear grain nor go unnoticed. A reading of exactly 13.5 is NOT rejected: it is a legitimate meter value (test_e4_01_*). Closing texts are shortened so every worst case stays within 2 SMS segments. Accepted design cap (R3 E3-04, R1-31): 7 of the 10 message codes can take 2 SMS segments.
- **Rounding** is decided once: `fmt(x, n)` rounds half up on the decimal value after correcting binary noise to 10
  decimals (`Decimal(f"{x:.10f}").quantize(ROUND_HALF_UP)`). The PL/SQL and JS ports do the same, and the vectors compare
  exact display strings (5.00..40.00 step 0.01 fuzzed across all ports: 0 divergences). Near a limit a second decimal is
  shown so that 13.54 never reads "13.5, the limit is 13.5".
- **Consent per phone.** `is_optout` (R1-04) recognises STOP, STOPP, UNSUBSCRIBE, CANCEL, END, QUIT, ACHA, SITISHA, SIMAMISHA, NISITISHIE and the phrases NO MORE / OPT OUT / SITAKI TENA anywhere in a message of at most 6 words ("I WANT TO STOP"); longer messages are never read as opt-outs. An opt-out word beats a storage word ("SEALED STOP" stops). Digits and word boundaries are ASCII-only (R2 C-14). `stop_phone` / `start_phone` / `cancel_queued` apply it to every batch of a
  number and to the queued messages. START after a pause does not reset the countdown (the paused days are charged);
  START after a sale restarts it.
- **Weather freshness.** `WeatherMeta(fetched_on, age_hours, credit)`: older than 24 hours is flagged stale, never
  triggers RAIN_COVER, and the message date is the date of the data. Demos pass `credit="Simulated weather"`.
- **Idempotent day.** `Batch.last_run`; a second `daily_run` the same day sends nothing and flags `already run today`.
- **Inbound text.** Cut to 1,000 characters before parsing, unicode spaces normalised, never raises; only 250 normalised
  characters are kept for duplicate detection.
- **Privacy.** `normalise_address`, `address_hash` (HMAC-SHA256 with a pepper), `retention_cutoffs` (30 / 30 / 180 / 90 / 90
  days). The database side is in `../plsql/README.md`.
- **Assumptions** are listed in `ASSUMPTIONS` (15 numbered, each CALIBRATION, PROGRAMME or UNVALIDATED) and exported to the
  site by `tools/gen_site_data.py`. The headline demo (261 days, then 34) depends on assumption 3 (5 %/day sack drift):
  0 %/day gives 45, 43, 42 days; 2 %/day gives 145, 143, 38; 5 %/day gives 263, 261, 34.

## Parameters

Each parameter is labelled in the code as one of these:

- **SOURCE**: from a publication.
  - EMC table: Arkansas FSA1074 Table A.
  - Storage-time table: Arkansas FSA1058 Table 1.
  - 13.5 % limit: EAS 2.
  - 14 % hermetic limit: Ng'ang'a et al. 2016a.
  - 15 % salt line: Johnson 1992.
  - Week-7 insect reminder: SOURCE-BASED, not verified: the week is not stated in the abstracts (Ng'ang'a et al. 2016b).
- **CALIBRATION**: an assumption the pilot will replace with meter data.
  - 18 % when salt sticks.
  - 14.5 % when salt flows.
  - 5 %/day drift in sacks.
  - Daily air temperature used as grain temperature.
- **PROGRAMME**: our own design rules: alert thresholds, spacing, caps.
- **UNVALIDATED**: a modelling assumption nobody has checked for Kenyan white maize (see `ASSUMPTIONS`).

Programme parameters not listed above, by name in the code: `HORIZON_DAYS` 365, `MAX_AST_DAYS` 3650, `RETEST_MARGIN` 1.0,
`REMIND_GAP_DAYS` 3, `SEALED_GAP_DAYS` 7, `REPEAT_MAX` 2, `TEST_REMINDERS_MAX` 3, `RAIN_UNACKED_MAX` 3, `PLACE_MAX_CHARS` 32,
`HIGH_ALERT_GAP_DAYS` 7, `HIGH_ALERT_MAX` 4, `WEATHER_STALE_HOURS` 24, `WEEKS_CAP` 99, `NORM_STORE_CHARS` 250,
`MAX_TEXT_CHARS` 1000, and the `RETAIN_*` windows.

## Porting to PL/SQL

- Store the two tables as rows.
- Port `emc`, `ast_days`, `advance_day`, `days_left`, `risk_level`, `advice`, `evaluate`, `apply_reply` and `respond`.
- Keep the message templates in a table keyed by code and language.
- Replay each scenario in `vectors.json` day by day: replies first, then the evening run. Compare the code, the exact message text, level, days left, the displayed moisture and life-used strings and the exact values at every step.
- EMC and AST values must match to 1e-6. Days left and message codes must match exactly.

## Known limits

- The tables are for US-grade yellow dent corn. They are not validated for Kenyan white maize.
- The EMC table reads about 0.6–0.7 points wetter than measured maize data, so it errs towards earlier warnings.
- Storage time below 15 % moisture is extrapolated, and the result is flagged.
- The free Open-Meteo tier is for non-commercial use only, and needs CC BY 4.0 credit. Attribution: "Weather data by
  Open-Meteo.com (https://open-meteo.com), licensed CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Values are
  averaged by Harvestly and drive an estimate." Alerts carry the short form `Open-Meteo.com <date>`; the WELCOME message and
  the site carry the full text.
- A hygrometer reading is trusted only after the instrument has equilibrated in the grain (30 to 45 minutes); the engine cannot check that.
- Afzal et al.: the 5 %/day sack drift is "consistent with" published sack-storage behaviour, not derived from it.
- Weight loss and the week-7 insect timing are unverified (see the SOURCE-BASED label above).
- `calc.js` on the site must format with the shared `fmt()` (rounding) and parse numbers with the same rules; that file is owned by the site workers.

## After review R2 (engine)

- `TEST_FIRST` no longer carries the salt quantities or the 6-hour wait (they were retracted as unverified, R1-006 / K-01): it asks
  for a meter reading first and offers the salt test as a "draft, unconfirmed" option, SALT YES / SALT NO unchanged.
- `INSECT_REMINDER` no longer states "weevil damage rose steeply after week 7" (C-11; the week-7 figure is unverified and is
  only the reminder's timing). `DRY_NOW` is shorter (R1-31).
- Opt-out matching, ASCII-only regexes, the HIGH_ALERT closing state and its diagnostics flag: see above. Tests:
  `OptOut.test_r1_04_*`, `test_c14_*`, `HighIsNeverSilent.test_c12_*`, `test_k01_*`, `test_c11_*`.
