# Telegram prototype bot (@HarvestlyBot)

A hackathon prototype test of the Python reference engine over Telegram. It is not a live alert service: the
weather is a fixed SIMULATED forecast (18 C, 63 % RH, no rain) and there are no proactive alerts. Since 2026-10-12 it
runs 24/7 as a Telegram WEBHOOK on Vercel (`bot/`, project `harvestly-bot`, https://harvestly-bot.vercel.app); the
laptop long-poller (`tools/telegram_bot.py`) is kept as a documented fallback. The Oracle/ORDS webhook version (`plsql/ords_handlers.sql`,
`POST /hv/telegram`) is written but not yet built or run on Oracle.

Files: `tools/harvestly_bot_core.py` (routing/formatting, transport-independent, shared), `tools/telegram_bot.py`
(stdlib long-polling front end), `tools/test_telegram_bot.py`
(offline tests with a fake transport: `cd tools && python3 -m unittest test_telegram_bot`; the webhook has its own in `bot/test_webhook.py`: `cd bot && python3 -m unittest test_webhook`).

## Behaviour
- Private text messages only; one message per turn (the demo sends 7). The first non-command reply of a chat starts
  with an italic "Prototype test, simulated weather." line (Kiswahili chats: "Jaribio la mfano, hali ya hewa ya kuigwa."). Typing indicator before replies.
- Language is EITHER/OR. First contact (no language chosen: `/start`, any command, any text that is not a register word) gets ONE
  neutral message, "Choose a language. / Chagua lugha.", with two reply-keyboard buttons `English` and `Kiswahili` (a tap sends
  the word; the webhook only receives messages). It is the only bilingual message. A register word also chooses: `JOIN` or
  `REGISTER` = English, `SAJILI` = Kiswahili (as the engine reads them). After that EVERY bot string is in that language only:
  welcome, help, buttons, hints, errors, /reset, /stop, the prototype line, card captions and the card images, and /demo. English
  chats are told `JOIN KITALE SACK 12`; Kiswahili chats `SAJILI KITALE MAGUNIA 12`, `MITA 14.2`, `CHUMVI NDIYO`. `/lang` (or tapping
  a language word) switches the whole chat in one step, including the registration's language and the keyboard labels; with no
  registration yet it also shows the welcome in the new language. The engine's "by SMS" / "on this number" are shown as "here" /
  "in this chat", and its welcome's Open-Meteo weather credit is replaced by "Weather in this test is simulated. /weather shows recent NASA POWER estimates." (Kiswahili twin); the welcome and the engine replies never name Open-Meteo (the bot calls it only for the context command `/forecast`, see below), and a test checks that no welcome, card or profile text names it. The /demo week is the engine's vectors with the credit "Simulated weather". Kiswahili chats are taught `KIHENGE` (crib) and `SAKAFU` (floor) next to `ANIKA`, `MAGUNIA`, `NIMEFUNGA` (the English `CRIB`, `FLOOR` still parse; the two words need a native check). Kiswahili engine text comes from the engine's own templates.
- /demo in Kiswahili: `engine/demo_sw.json`, written by `tools/gen_site_data.py` (the same `demo_pitch` scenario run through the
  engine in Kiswahili; asserted to have the same steps as `vectors.json`). The English demo reads `vectors.json`.
- Dial cards: `dial-0..90.png` (English: "days left (estimate)", "Harvestly example, simulated weather") and `dial-sw-0..90.png`
  ("siku zilizobaki (makadirio)", "Harvestly mfano, hali ya hewa ya kuigwa"), rendered by `node tools/telegram_cards.mjs`; the chat
  language picks the set.
- Profile: `setup_profile` sets one English profile (default) and one Kiswahili profile (`language_code=sw`, shown to people whose
  Telegram is in Swahili), each single-language: name, description, short description, commands.
- `/start` (logo + 3 short paragraphs; deep link params ignored), `/help` (4 lines), `/weather` (recent weather, see below), `/lang` (toggles English/Kiswahili,
  or `/lang en|sw`), `/stop` (engine opt-out), `/reset` (delete my data), `/demo` (7 steps from `engine/vectors.json`,
  `demo_pitch`, each with a dial card, ends "simulated, not a live alert").
- Formatting: Telegram HTML. Engine wording is untouched; it is escaped (`html.escape`), commands become `<code>`
  (tap to copy), the time left is bold, and a short bold title is added by type (Registered, Reading recorded, Warning,
  Stopped). If Telegram rejects the markup the bot resends plain text.
- Buttons (reply keyboard, a tap sends its text): after registering `SALT YES | SALT NO`, `Meter reading | /lang`;
  after a warning `DRYING | STOP`; after STOP `START`. Kiswahili labels when the chat is Kiswahili. "Meter reading"
  answers with the `METER 14.2` hint.
- Images: `/start` sends the symbol (`brand/telegram-profile-512.png`, as supplied). Warnings and demo steps send a dial
  card (`brand/telegram-cards/dial-0..90.png` and `dial-sw-0..90.png`, 90 means 90+, labelled "example, simulated weather" in the chat's language) with the text as
  caption (max 1024; longer text is sent as a plain message). Cards are pre-rendered once, not at runtime
  (`node tools/telegram_cards.mjs`, Brave headless over CDP); Telegram file_ids are cached in state.json.
- Free text follows the ORDS contract: unknown chat gets the how-to; `JOIN|REGISTER|SAJILI <ward> <storage> <bags> [SW]`
  registers (example wards: Kitale, Eldoret, Webuye, Bungoma, Kapsabet, Kakamega; unknown ward gets the ward list);
  a registered chat goes to `respond()`. Unrecognised text gets a one-line "send /help" (engine HELP template not shown).
  Deviation for testing: JOIN works again after a registration unless the chat has opted out.
- `/weather` (added 2026-10-12, per `research/nasa-due-diligence.md`): the last 3 observed days for the chat's example ward (Kitale if not registered), from NASA POWER daily point data (T2M, RH2M, PRECTOTCORR, community AG), in the chat's language only. The message carries the due-diligence sentence ("Recent weather near Kitale (NASA satellite/model estimate, to <date>): about <T> C, humidity <RH>%, <R> mm rain. This is an area estimate, not a measurement at your store."), the as-of date (data are about 3 days old), the credit line ("Weather estimates: NASA POWER (NASA Langley Research Center, funded by the NASA Earth Science Division). Not endorsed by NASA.") and a note that the advice in this test still uses simulated weather. The call is server side with a rounded 1-decimal ward centroid only (`WARD_CENTROID` in the core; no chat id or text is sent, nothing about chats is logged), -999 days dropped (a day missing any of the three values is missing), an in-memory cache (one request per POWER grid cell per 6 hours, wards in one cell share it, a failure is not retried for 15 minutes, a stale copy up to 7 days old is shown with its date), a 6 s timeout, and a plain fallback line when NASA is down or the data are older than 7 days. The cache is per function instance. It is context only: no engine run on observed days. Kiswahili wording is a draft that needs a native check. The command is in both profiles' `setMyCommands` and the idle keyboard (`/weather | /lang`).
- `/forecast` (added 2026-10-13, per `docs/WEATHER_PROVIDERS.md`): the next 7 days for the chat's example ward (Kitale if not registered) from a real weather-model forecast, in the chat's language only. Providers are tried in order (`tools/weather_providers.py`): Open-Meteo (no key), WeatherAPI.com, OpenWeather (keys in the function's environment: `WEATHERAPI_KEY`, `OPENWEATHER_API_KEY`); the first that returns tomorrow first with no gap in the days wins, and its credit line is shown (Open-Meteo: "Weather data by Open-Meteo.com (CC BY 4.0)."; WeatherAPI: "Powered by WeatherAPI.com."; OpenWeather: "Weather data provided by OpenWeather."). The message says it is an area forecast, not a measurement at the store, lists date, temperature, humidity, rain and chance of rain, and notes that the advice in this test still uses simulated weather. The call is server side with the same rounded ward centroid as `/weather` (no chat id or text sent, nothing about chats logged), an in-memory cache (one provider-chain run per ward per 3 hours; a failure is not retried for 10 minutes; a stale copy under a day old is shown if every provider fails), a 15 s timeout, and a plain fallback line when all are down. Context only: it never feeds the engine (a test asserts the engine forecast stays the simulated day). The Open-Meteo free tier is non-commercial, which fits this prototype; a pilot needs WeatherAPI.com's commercial-use free plan (3-day forecast) or a paid Open-Meteo plan. Kiswahili wording is a draft that needs a native check.
- Future work (not built): the due diligence allows an opt-in catch-up only from a MEASURED test (meter, hygrometer or salt-test result on a stated date) run over observed days since that test, capped at 21 days, worded "Since your test on <date> (<M>%), using area weather from NASA, the estimate is about <X>%. Weather is estimated, so test again to be sure.", never "safe", and nothing from a batch with no measurement. `daily_run` also needs a forecast starting tomorrow, so it would be fed POWER days plus the existing simulated forecast. It also needs the weather bias discussed in the file (section 3 and 6) checked against a measured test first.
- Rate limit 20 messages/min/chat; input cut to 1000 chars; non-text gets a polite note; handler errors are caught.
- State: `~/.local/share/harvestly-bot/state.json` (mode 600): update offset, salt, Telegram file_ids, per chat a salted
  hash of the chat id plus the batch state. No names, usernames or message text. Logs: update ids and command classes
  only; the token is never logged. The only outside calls that depend on a chat are `/weather`'s NASA POWER request and `/forecast`'s weather-provider request, which carries a
  rounded ward centroid and nothing else (the request leaves from the Vercel function in Dublin, not from the user's phone).

## Run
Installed copy (survives edits of the repo): `~/.local/share/harvestly-bot/app/` (bot + engine + vectors.json).
Refresh after changing the repo:
```
cp tools/telegram_bot.py ~/.local/share/harvestly-bot/app/ && mkdir -p ~/.local/share/harvestly-bot/app/assets/cards && cp brand/telegram-profile-512.png ~/.local/share/harvestly-bot/app/assets/logo.png && cp brand/telegram-cards/*.png ~/.local/share/harvestly-bot/app/assets/cards/ && cp engine/harvestly_engine.py engine/vectors.json ~/.local/share/harvestly-bot/app/engine/
systemctl --user restart harvestly-bot
```
Unit: `~/.config/systemd/user/harvestly-bot.service` (token via EnvironmentFile=~/.config/harvestly/secrets.env,
Restart=on-failure, MemoryMax=100M, Nice=10, about 16 MB in use).
```
systemctl --user start|stop|restart|status harvestly-bot
journalctl --user -u harvestly-bot -f
systemctl --user enable harvestly-bot        # start at login (not enabled by default)
python3 tools/telegram_bot.py --check        # getMe only
python3 tools/telegram_bot.py --setup-profile  # name, descriptions, commands
python3 tools/telegram_bot.py --drain        # skip waiting messages without replying
```
Do not set a webhook while polling (getUpdates then returns 409). The unit is currently stopped and disabled: the webhook is live.

## BotFather steps for Ken (cannot be done through the API)
`/setuserpic` with `brand/telegram-profile-512.png`; `/setjoingroups` -> Disable.

## Webhook on Vercel (live)
- Layout: `bot/api/telegram.py` (Vercel Python function, stdlib only), `bot/lib/webhook.py` (request handling, Turso
  backend, injected transport), `bot/lib/` also holds copies of `harvestly_bot_core.py`, `harvestly_engine.py`,
  `vectors.json`, `demo_sw.json`; `bot/public/` has `index.html` (noindex), `logo.png`, `cards/dial-0..90.png` and `cards/dial-sw-0..90.png`. `bot/vercel.json` pins
  region `dub1` (Dublin, next to Turso `aws-eu-west-1`). One source of truth: edit `tools/` and `engine/`, then run
  `bot/sync-engine.sh` before deploying; `bot/test_webhook.py` fails if a copy is stale.
- Deploy: `cd bot && ./sync-engine.sh && python3 -m unittest test_webhook && vercel deploy --prod --scope ken-muritus-projects`.
- Security: Telegram sends `X-Telegram-Bot-Api-Secret-Token`; checked in constant time, else 401. Valid updates always
  get 200 (Telegram retries otherwise); only a state-store outage returns 503 so Telegram retries. `update_id` is
  claimed in Turso before processing (dedupe). `allowed_updates` is `["message"]` (no inline buttons are used).
  Logs carry only update ids and command classes.
- Env (Vercel Sensitive, production): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `CRON_SECRET`, `TURSO_URL`, `TURSO_TOKEN`
  (permissions: data read/add/update/delete only, no schema), `STATE_SALT`. Local copies in
  `~/.config/harvestly/secrets.env` (mode 600). Turso DB `harvestly-bot` (tables `chats`, `updates`; schema created once
  with a short-lived admin token: `bot/scripts/schema.sql`).
- Photos are sent by URL (`https://harvestly-bot.vercel.app/logo.png`, `/cards/dial-N.png`); if Telegram rejects the
  photo the text is sent alone. No file_id cache.
- Set / check webhook (token from secrets.env, never printed):
  `curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" --data-urlencode "url=https://harvestly-bot.vercel.app/api/telegram" --data-urlencode "secret_token=$TELEGRAM_WEBHOOK_SECRET" --data-urlencode 'allowed_updates=["message"]'`
  and `.../getWebhookInfo` (look at `pending_update_count`, `last_error_message`).
- Rate limit: 20 messages/min/chat kept in the chat's stored state (read-modify-write, fixed window: a burst of up to 40
  across a window edge, and two simultaneous updates of one chat could both pass; Telegram delivers a chat's updates one at a time).
- Delete after 30 days (B6-01): a Vercel Cron (`bot/vercel.json` `crons`, daily 03:17 UTC, Hobby plan allows one run a day)
  calls `GET /api/prune` (`bot/api/prune.py`) with `Authorization: Bearer $CRON_SECRET` (Vercel sets this header when the
  `CRON_SECRET` env var exists; anything else gets 401). It deletes chat rows idle for 30 days and update ids older than 2 days.
  The old 1-in-25 prune on incoming requests stays as a second path. /reset keeps the hashed row, language and counter
  (the rate limit must survive a reset) and restarts the 30-day clock; /privacy says so.
- Failure handling: `chats` is saved BEFORE the first reply is sent, so a registration is never lost after "Registered";
  if that save fails nothing is sent, the update-id claim is released and the webhook returns 503 so Telegram retries. A
  bug inside the handler is logged by class only and answered 200 (no retry storm, no stack trace). The secret is checked
  before the configuration (an unauthenticated call always gets 401).
- The webhook state starts empty (new salt, new database); the old laptop `state.json` was not migrated.

## Switch back to the laptop poller
```
set -a; . ~/.config/harvestly/secrets.env; set +a
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/deleteWebhook"      # without drop_pending_updates, so nothing is lost
cp tools/telegram_bot.py tools/harvestly_bot_core.py ~/.local/share/harvestly-bot/app/
systemctl --user start harvestly-bot
```
(getUpdates is rejected while a webhook is set, and the reverse.) The unit is stopped and disabled since the cutover.
To go back to the webhook: stop the unit, then run the setWebhook command above.
