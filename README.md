# Harvestly

Early-warning service for maize in woven sacks: a farmer's salt test or meter reading plus the 7-day forecast gives an estimated "days left" countdown and one action. It is designed to work by SMS, USSD or Telegram. Today there is a Python risk engine, a public demo website (https://harvestly-roan.vercel.app), a Telegram TEST bot (@HarvestlyBot, answers 24/7 from a Vercel webhook with the real engine on simulated weather, no unprompted alerts, state in Turso Ireland; see `docs/TELEGRAM.md`) and an Oracle PL/SQL port that has been written but never compiled. Not built: the Oracle/ORDS version of the bot, SMS, USSD, the dashboard, a real weather forecast for the engine (the bot's forecast is simulated). NASA POWER observed weather (a satellite/model estimate for one grid cell of about 55 by 70 km, with a data lag of up to a few days, not measured on the farm and not a forecast) is offered as an optional "Show recent weather near Kitale" button in the calculator, which shows recent NASA estimates as one line of text and changes no calculator values, and as a /weather bot command. The forecast the engine needs is still simulated in the test bot. A MODIS image of Trans Nzoia (20 December 2025, with scattered cloud) is on the /pilot page. Catch-up over observed days is future work. Nothing here is a commitment, and no pilot has run.

**Built as a team project** for the Green Tech Hackathon 2026 (iLabAfrica, Strathmore University × Oracle). This repository is published by one of the team members, Kennedy Muritu. Pitch decks, scripts, internal review notes and earlier drafts are not included.

- `docs/Harvestly_Concept_Note_v4.7.*` - current concept note (v4.7), plus `docs/SITE.md`, `docs/TELEGRAM.md` and `docs/WEATHER_PROVIDERS.md`
- `engine/` - Python reference risk engine (stdlib only); `vectors.json` is the contract the Oracle PL/SQL port must match. See `engine/README.md`
- `plsql/` - Oracle PL/SQL port, written by the team with AI help on 12 Oct, never compiled or checked against `vectors.json`
- `research/` - verification notes, hard-question bank, unit economics, landscape
- `bot/` - Telegram test bot (Vercel webhook, Turso state). `site/` - the demo website and its API routes. `tools/` - site build, link check, chart and webhook tests. `brand/` - logo brief and Telegram cards
- `CHANGES.md` - what changed between versions, and what is still unverified at a primary source

Alert limits: a batch at high risk gets at most four weekly high-risk alerts per test result; the fourth says it is the last reminder, and after it the engine stays silent until the farmer sends a new test. The first message to an untested batch asks for a meter reading and offers the salt test only as a draft. The 15% salt-test line is a published rule of thumb, unverified for Kenyan conditions; the engine treats it as an assumption.

The headline demo ("261 days becomes 34") is illustrative: it uses simulated weather and an untested 5%-a-day drying assumption, and the clock starts at the first test, not at harvest. The 365 shown after a meter reading is the longest the tool looks ahead, not a prediction.

Designed forecast source: Open-Meteo.com (https://open-meteo.com), CC BY 4.0; the free tier is non-commercial, and the test bot calls it only for the context command /forecast (Open-Meteo first, then WeatherAPI.com, then OpenWeather); the advice itself still uses simulated weather. Recent observed weather and the Trans Nzoia image: NASA POWER and NASA Worldview / GIBS (MODIS Terra), used as context; not endorsed by NASA.

## Tests

```
cd engine && python3 test_engine.py     # risk engine (119 tests)
cd bot && python3 test_webhook.py       # Telegram webhook (29 tests)
node tools/test-webhook.mjs              # site form webhook (24 tests)
```

## Licence

Copyright © 2026 Kennedy Muritu. All rights reserved. The code is public to read, not to reuse. See [LICENSE](LICENSE). Weather and imagery credits are listed above and on the site's sources page.
