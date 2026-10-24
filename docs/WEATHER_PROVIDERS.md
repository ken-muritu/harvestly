# Weather providers: due diligence (13 Oct 2026)

Tested live from this machine for Kitale (1.0157 N, 35.0062 E) on 13 Oct 2026 with the keys Ken supplied (stored in `~/.config/harvestly/secrets.env`, never in the repo). Terms are from the providers' own plan and pricing pages as pasted by Ken, not from the legal texts: read the full terms before a paid pilot.

## What each provider gave

| Provider | Endpoint tested | Result for Kitale | Free-tier limits that matter | Commercial use |
|---|---|---|---|---|
| Open-Meteo | `/v1/forecast` | 7 days (up to 16), daily mean temperature, mean humidity, rain, chance of rain; no key | 10,000 calls a day; credit required (CC BY 4.0) | Free tier is **non-commercial**; paid plan needed for a pilot |
| WeatherAPI.com | `/v1/forecast.json` | Worked. The key returned **14 days** because new keys start on a 14-day Business trial and then drop to **Free: 3-day forecast, history last 1 day** | 100,000 calls a month | Allowed on the free plan; a link back is asked for |
| OpenWeather (key 1) | `/data/2.5/weather`, `/data/2.5/forecast` | Worked: current weather, **5-day / 3-hour** forecast. **One Call 3.0 returned 401** (needs a separate subscription) | 60 calls a minute, 1 million a month | Free plan allows use with attribution |
| AgroMonitoring (OpenWeather's agro API) | polygons, `/weather/forecast`, `/weather`, `/soil`, `/image/search` | Worked on a 19.8 ha demo polygon at Kitale: current weather, the same 5-day / 3-hour forecast, soil temperature and moisture (current), satellite image search (Landsat 8). **Historical weather and accumulated precipitation returned 401** (paid) | Free tier | Check its own terms of sale before a pilot |

The account already held one sample polygon ("Iowa Demo Field"). I created one more, "Harvestly Kitale pilot ward (demo)" (id saved in `~/.config/harvestly/agro_polygon_id`). It can be deleted from the Agro dashboard.

## Do they agree? (forecast for 14 to 17 Oct, Kitale)

Run `cd tools && python3 weather_providers.py` to repeat it.

| Day | Open-Meteo | WeatherAPI | OpenWeather |
|---|---|---|---|
| 14 Oct | 18.8 C, 75 %, 1.7 mm | 18.3 C, 80 %, 5.5 mm | 18.6 C, 71 %, 4.2 mm |
| 15 Oct | 18.9 C, 76 %, 4.3 mm | 18.3 C, 79 %, 16.1 mm | 18.8 C, 69 %, 2.8 mm |
| 16 Oct | 17.2 C, 89 %, 20.8 mm | 18.1 C, 81 %, 8.2 mm | 18.6 C, 72 %, 3.8 mm |

- **Temperature agrees** within about 1.5 C and **humidity** within about 10 points. These two drive the engine's moisture and mould clock, so a provider switch moves the answer little.
- **Rain amounts disagree a lot** (16 mm against 3 mm on one day). Rain is a poor basis for a single number; the engine treats it as a hint for the next 24 hours and the bot shows it as context only. One more reason not to quote rain amounts as facts.
- Both are model forecasts for an area, not measurements at a farmer's store.

## Decision

1. **Primary: Open-Meteo.** Longest forecast (the engine wants 7 days), no key, fine for a non-commercial hackathon prototype. Credit shown with every use.
2. **Fallbacks, in order: WeatherAPI.com, then OpenWeather.** WeatherAPI is the one with a free commercial-use plan, so it is the route for a pilot (but only a 3-day forecast; do not rely on the 14 days, they end with the trial). OpenWeather's 5-day / 3-hour forecast is folded into local days and only complete days are used.
3. **A provider is accepted only if it returns tomorrow first and no day is missing.** Otherwise the next provider is tried; if all fail the bot says the forecast is unavailable. The engine is never fed a partial or shifted forecast.
4. **AgroMonitoring is not used for the forecast** (it is the same OpenWeather 5-day data). It is kept for field context that the other providers do not offer: satellite imagery and soil moisture for a pilot-ward polygon. That is a pre-harvest and field signal, not a storage signal, so it is not wired into the engine. Candidate for the pilot page as a dated image, labelled like the NASA MODIS image. Not built.
5. **Scope today:** `/forecast` in the Telegram test bot (context only). The engine's advice still runs on the simulated forecast, because feeding live weather into the advice changes every "simulated" claim in the note, the decks and the site and needs the review rounds that backed those claims. See "Next step".

## Credits and privacy

- Open-Meteo: "Weather data by Open-Meteo.com (CC BY 4.0)." WeatherAPI.com: "Powered by WeatherAPI.com." OpenWeather: "Weather data provided by OpenWeather."
- Only a rounded ward centre (one decimal of latitude and longitude) is sent to a provider: no chat id, text or farmer data. The key never leaves the server.

## Keys

Three keys were pasted into the chat. They are now in the secrets file and, for the two fallbacks, in the bot's Vercel environment. Rotate them when the hackathon is over (WeatherAPI, OpenWeather and Agro keys can be regenerated in each dashboard).

## Next step (needs a decision)

Feed the live forecast to the engine for real (non-demo) chats, keeping `/demo` simulated. It would touch: the bot's "simulated weather" prefix and credits, the site footers, the note, both decks, the Q&A bank and the prior-work statement. Do this only if time allows after Thursday's submission, or before it if the team wants the stronger claim and accepts the re-review.
