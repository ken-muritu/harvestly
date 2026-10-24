"""Harvestly bot core: transport-independent routing, formatting and per-chat state handling.

Shared by the local long-poller (tools/telegram_bot.py) and the Vercel webhook (bot/api/telegram.py). It talks to
Telegram only through an injected transport object (call/upload) and keeps per-chat state in store.data["chats"].
Nothing here logs message text, chat ids or the token. Copied verbatim into bot/lib/ by bot/sync-engine.sh.
"""
import collections
import dataclasses
import hashlib
import html as htmllib
import json
import logging
import os
import re
import time
import urllib.request

try:                         # tools/ and bot/lib/ both carry weather_providers.py; without it /forecast says "not available"
    import weather_providers as WP
except ImportError:
    WP = None
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
EAT = timezone(timedelta(hours=3))
RATE_MAX, RATE_WINDOW = 20, 60.0           # messages per chat per minute
MAX_INBOUND = 1000                          # same cut as the engine / ORDS handler (R1-07)
KEEP_SENT = 40                              # trim batch history kept in state
log = logging.getLogger("harvestly-bot")

class TelegramError(Exception):
    def __init__(self, msg, code=None, retry_after=None):
        super().__init__(msg)
        self.code, self.retry_after = code, retry_after



def find_asset(name):
    """name: 'logo' or 'dial-<n>'. Installed copy: assets/; repo: ../brand/. Returns a path or None."""
    if name == "logo":
        cands = [os.path.join(HERE, "assets", "logo.png"), os.path.join(HERE, "..", "brand", "telegram-profile-512.png")]
    elif re.fullmatch(r"dial-(?:sw-)?[0-9]{1,2}", name):
        cands = [os.path.join(HERE, "assets", "cards", name + ".png"),
                 os.path.join(HERE, "..", "brand", "telegram-cards", name + ".png")]
    else:
        return None
    return next((c for c in cands if os.path.isfile(c)), None)


# ---------------------------------------------------------------------------------------------- batch (de)serialisation
_DATE_FIELDS = ("stored_since", "last_test", "last_advanced", "last_alert", "last_run")


def batch_to_json(b):
    d = dataclasses.asdict(b)
    for k in _DATE_FIELDS:
        d[k] = d[k].isoformat() if d[k] else None
    d["sent"] = [[x.isoformat(), c] for x, c in b.sent[-KEEP_SENT:]]
    d["replies"] = []                                         # reply text is never persisted
    d["acks"] = [x.isoformat() for x in b.acks[-KEEP_SENT:]]
    return d


def batch_from_json(H, d):
    d = dict(d)
    for k in _DATE_FIELDS:
        d[k] = date.fromisoformat(d[k]) if d.get(k) else None
    d["sent"] = [(date.fromisoformat(x), c) for x, c in d.get("sent", [])]
    d["acks"] = [date.fromisoformat(x) for x in d.get("acks", [])]
    d["replies"] = []
    return H.Batch(**d)


# ---------------------------------------------------------------------------------------------- texts
esc = lambda t: htmllib.escape(t, quote=False)
# Language is EITHER/OR. The only message with both languages is NEUTRAL (first contact, before a choice); every other
# bot-side string below is a {en, sw} pair and a chat only ever sees its own language.
NEUTRAL = "<b>Harvestly</b>\nChoose a language.\nChagua lugha."
LANG_WORDS = {"english": "en", "kiswahili": "sw", "swahili": "sw"}
LANG_SET = {"en": "Language: English.", "sw": "Lugha: Kiswahili."}
# B6-11: the English chat is told the English register word (JOIN, which the engine reads as lang=en); the Kiswahili
# form (SAJILI, lang=sw) is shown only as the Kiswahili line, and a Kiswahili chat gets all of this in Kiswahili.
PREFIX = {"en": "<i>Prototype test, simulated weather.</i>\n\n",        # added once to a chat's first non-command reply
          "sw": "<i>Jaribio la mfano, hali ya hewa ya kuigwa.</i>\n\n"}
START_HTML = {"en": ("<b>Harvestly</b>\n"
                     "Maize-storage advice. A hackathon prototype test with simulated weather, not a live alert service.\n\n"
                     "To begin, send:\n<code>JOIN KITALE SACK 12</code>\n"
                     "(your ward, storage, bags)."),
              "sw": ("<b>Harvestly</b>\n"
                     "Ushauri wa kuhifadhi mahindi. Jaribio la mfano, hali ya hewa ni ya kuigwa, si huduma halisi ya tahadhari.\n\n"
                     "Kuanza, tuma:\n<code>SAJILI KITALE MAGUNIA 12</code>\n"
                     "(kata, hifadhi, magunia).")}
HELP_HTML = {"en": ("<b>Help</b>\n\n"
                    "Register: <code>JOIN KITALE SACK 12</code> (ward, storage, bags)\n"
                    "Then: <code>METER 14.2</code>, <code>SALT YES</code>, <code>SALT NO</code>, <code>DRYING</code>, <code>SEALED</code>\n"
                    "/demo sample week, /weather recent weather, /forecast next days, /lang change language\n"
                    "<code>STOP</code> stops messages, /reset deletes my test data"),
             "sw": ("<b>Msaada</b>\n\n"
                    "Kusajili: <code>SAJILI KITALE MAGUNIA 12</code> (kata, hifadhi, magunia)\n"
                    "Kisha: <code>MITA 14.2</code>, <code>CHUMVI NDIYO</code>, <code>CHUMVI HAPANA</code>, <code>ANIKA</code>, <code>NIMEFUNGA</code>\n"
                    "/demo wiki ya mfano, /weather hali ya hewa ya karibuni, /forecast siku zijazo, /lang badilisha lugha\n"
                    "<code>ACHA</code> inasimamisha ujumbe, /reset inafuta data yangu ya majaribio")}
# the engine's SMS wording, mapped to this chat (N6-02)
# B7-01: the engine's SMS WELCOME credits Open-Meteo (the designed live version). This test bot calls Open-Meteo only for /forecast (context), never for the engine or the welcome,
# so the credit is replaced by the honest line for this chat. The long form must come before the short one.
_CHAT_WORDS = (("Weather data by Open-Meteo.com (CC BY 4.0).", "Weather in this test is simulated. /weather shows recent NASA POWER estimates."),
               ("Data ya hali ya hewa: Open-Meteo.com (CC BY 4.0).", "Hali ya hewa katika jaribio hili ni ya kuigwa. /weather inaonyesha makadirio ya karibuni ya NASA POWER."),
               ("by SMS", "here"), ("kwa SMS", "hapa"), ("on this number", "in this chat"),
               ("kwenye namba hii", "kwenye mazungumzo haya"), ("kwa namba hii", "kwa mazungumzo haya"),
               ("SIMAMISHA", "ACHA"))  # N8-04: one stop word in the SW chat (keyboard and /help use ACHA; SIMAMISHA still works when typed)
TITLES = {"en": {"register": "Registered", "reading": "Reading recorded", "warn": "Warning", "stopped": "Stopped",
                 "started": "Messages on", "noted": "Noted", "step": "Step"},
          "sw": {"register": "Umesajiliwa", "reading": "Kipimo kimerekodiwa", "warn": "Onyo", "stopped": "Umesimamisha",
                 "started": "Ujumbe umewashwa", "noted": "Imerekodiwa", "step": "Hatua"}}
READING_CMDS = frozenset({"METER", "HYGRO", "SALT_YES", "SALT_NO", "SALT_NO_IGNORED"})
_FMT = re.compile(r"(?P<c>(?:METER|MITA|HYGRO) [0-9]+(?:[.,][0-9]+)?(?: [0-9]+)?|SALT (?:YES|NO)\b|CHUMVI (?:NDIYO|HAPANA)\b"
                  r"|\bDRYING\b|\bANIKA\b|\bSEALED\b|\bNIMEFUNGA\b)"
                  r"|(?P<b>about [0-9]+ days?|siku [0-9]+|3 months or more|miezi 3 au zaidi|used up|umeisha)")


def fmt_engine(text, title=None):
    """Engine wording unchanged: escape everything, then <code> the commands to tap-copy and <b> the time left."""
    for a, b in _CHAT_WORDS:
        text = text.replace(a, b)
    body = _FMT.sub(lambda m: f"<code>{m.group('c')}</code>" if m.group("c") else f"<b>{m.group('b')}</b>", esc(text))
    return f"<b>{esc(title)}</b>\n\n{body}" if title else body


def plain(html_text):
    return htmllib.unescape(re.sub(r"<[^>]+>", "", html_text))


UNKNOWN_TEXT = {"en": "Not sure what you meant. Send /help.", "sw": "Sijaelewa. Tuma /help."}
METER_HINT = {"en": "Type <code>METER</code> and your reading, e.g. <code>METER 14.2</code>",
              "sw": "Andika <code>MITA</code> na namba, mf. <code>MITA 14.2</code>"}
LABELS = {"en": {"salt_yes": "SALT YES", "salt_no": "SALT NO", "meter": "Meter reading", "dry": "DRYING",
                 "stop": "STOP", "start": "START"},
          "sw": {"salt_yes": "CHUMVI NDIYO", "salt_no": "CHUMVI HAPANA", "meter": "Kipimo cha mita", "dry": "ANIKA",
                 "stop": "ACHA", "start": "ANZA"}}
WARN_CODES = frozenset({"DRY_NOW", "OPEN_AND_DRY", "RAIN_COVER", "HIGH_ALERT", "SORT_AND_SELL", "CONFIRM_DRY"})
MAIN_CODES = frozenset({"TEST_FIRST", "NEARLY_DRY"})


def keyboard(kind, lang):
    """Small reply keyboard: a tap sends the button text as an ordinary message."""
    L = LABELS[lang]
    if kind == "choose":                                   # first contact: the one bilingual keyboard
        return {"keyboard": [[{"text": "English"}, {"text": "Kiswahili"}]], "resize_keyboard": True, "one_time_keyboard": True}
    rows = {"main": [[L["salt_yes"], L["salt_no"]], [L["meter"], "/lang"]],
            "idle": [["/help", "/demo"], ["/weather", "/forecast"], ["/lang"]],
            "warn": [[L["dry"], L["stop"]], [L["meter"], "/lang"]],
            "start": [[L["start"]]]}[kind]
    return {"keyboard": [[{"text": t} for t in r] for r in rows], "resize_keyboard": True}


NON_TEXT = {"en": "I can only read text. Send /help.", "sw": "Ninasoma maandishi tu. Tuma /help."}
SLOW_DOWN = {"en": "Too many messages in a minute; pausing a bit.", "sw": "Ujumbe mwingi kwa dakika moja; ninapumzika kidogo."}
SLOW_DOWN[None] = SLOW_DOWN["en"] + "\n" + SLOW_DOWN["sw"]          # N7-02: before a language is chosen, both (like NEUTRAL)
ERROR_TEXT = {"en": "Something went wrong in this test. Try /help.", "sw": "Hitilafu imetokea kwenye jaribio hili. Jaribu /help."}
ERROR_TEXT[None] = ERROR_TEXT["en"] + "\n" + ERROR_TEXT["sw"]
RESET_TEXT = {"en": "Your test data is deleted. Send /start to begin again.",
              "sw": "Data yako ya majaribio imefutwa. Tuma /start kuanza tena."}
DEMO_NOTE = {"en": "<i>Demo: a pretend farmer, 10 bags in sacks, a simulated wet week.</i>\n\n",
             "sw": "<i>Mfano: mkulima wa kuigwa, magunia 10, wiki ya mvua ya kuigwa.</i>\n\n"}
DEMO_MISSING = {"en": "Demo data not found on this machine.", "sw": "Data ya mfano haipatikani."}
DEMO_END = {"en": "<i>This demo is simulated, not a live alert.</i>", "sw": "<i>Mfano huu ni wa kuigwa, si tahadhari halisi.</i>"}
HOWTO = {"en": "Harvestly: To join, reply JOIN <ward> <storage> <bags>, e.g. JOIN KITALE SACK 12. "
               "Storage: DRYING, SACK, CRIB, FLOOR or SEALED.",
         "sw": "Harvestly: Kusajili, jibu SAJILI <kata> <hifadhi> <magunia>, mf. SAJILI KITALE MAGUNIA 12. "
               "Hifadhi: ANIKA, MAGUNIA, KIHENGE, SAKAFU au NIMEFUNGA."}
EXAMPLE_WARDS = ["BUNGOMA", "ELDORET", "KAKAMEGA", "KAPSABET", "KITALE", "WEBUYE"]   # EXAMPLE list, not the pilot directory
STORAGE_WORD = {"DRYING": "drying", "SACK": "sack", "SACKS": "sack", "MAGUNIA": "sack", "ANIKA": "drying",
                "NIMEFUNGA": "hermetic", "CRIB": "crib", "FLOOR": "floor", "KIHENGE": "crib", "SAKAFU": "floor",   # KIHENGE/SAKAFU: Kiswahili crib/floor, native check pending
                "SEALED": "hermetic", "HERMETIC": "hermetic"}
RE_JOIN = re.compile(r"^(JOIN|REGISTER|SAJILI) [A-Z][A-Z ]* [0-9]+( SW)?$")


# ---------------------------------------------------------------------------------------------- recent weather (NASA POWER)
# /weather shows the last observed days for the chat's example ward, from NASA POWER daily point data (T2M, RH2M, PRECTOTCORR,
# community AG, local solar time), as research/nasa-due-diligence.md allows: a server-side call with a cache, a rounded ward
# centroid only (no chat id, no text, nothing about the chat), -999 days dropped, an "as of" date, an attribution line, and a plain
# fallback when NASA is down. It is shown as context only: it never feeds the engine, never says a sack is safe. A catch-up from a
# measured test over observed days is documented future work (docs/TELEGRAM.md), not built.
# Example-ward centroids, rounded to 1 decimal (a POWER value covers a cell of about 55 km by 70 km anyway). EXAMPLE list, not the pilot directory.
WARD_CENTROID = {"BUNGOMA": (0.6, 34.6), "ELDORET": (0.5, 35.3), "KAKAMEGA": (0.3, 34.8), "KAPSABET": (0.2, 35.1),
                 "KITALE": (1.0, 35.0), "WEBUYE": (0.6, 34.8)}
POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_FRESH_S, POWER_RETRY_S, POWER_STALE_DAYS, POWER_TIMEOUT = 6 * 3600, 15 * 60, 7, 6
_POWER_CACHE = {}            # grid cell -> {"at": epoch seconds, "days": [...]} and/or {"failed": epoch seconds}; per process
MONTHS = {"en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
          "sw": ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ago", "Sep", "Okt", "Nov", "Des"]}
# the due-diligence sentence (section 10), once per message; the Kiswahili needs a native check (listed in the review notes)
WEATHER_LINE = {"en": "Recent weather near {ward} (NASA satellite/model estimate, to {date}): about {t} C, humidity {rh}%, {rain} mm rain. "
                      "This is an area estimate, not a measurement at your store.",
                "sw": "Hali ya hewa ya karibuni karibu na {ward} (makadirio ya satelaiti/modeli ya NASA, hadi {date}): takriban {t} C, unyevu {rh}%, mvua {rain} mm. "
                      "Ni makadirio ya eneo, si kipimo cha ghala lako."}
WEATHER_TITLE = {"en": "Recent weather", "sw": "Hali ya hewa ya karibuni"}
WEATHER_DAYS = {"en": "Last days:", "sw": "Siku za mwisho:"}
WEATHER_CREDIT = {"en": "Weather estimates: NASA POWER (NASA Langley Research Center, funded by the NASA Earth Science Division). Not endorsed by NASA.",
                  "sw": "Makadirio ya hali ya hewa: NASA POWER (NASA Langley Research Center, inayofadhiliwa na NASA Earth Science Division). Haijaidhinishwa na NASA."}
WEATHER_NOTE = {"en": "The advice in this test still uses simulated weather.",
                "sw": "Ushauri katika jaribio hili bado unatumia hali ya hewa ya kuigwa."}
WEATHER_DOWN = {"en": "Recent weather is not available right now. Try again later.",
                "sw": "Hali ya hewa ya karibuni haipatikani kwa sasa. Jaribu tena baadaye."}


def power_cell(lat, lon):
    """The POWER grid cell (0.5 deg latitude by 0.625 deg longitude) of a point: wards in one cell share one request."""
    return (round(lat / 0.5), round(lon / 0.625))


def parse_power(data):
    """POWER JSON -> [(date, t, rh, rain)], oldest first. A day missing ANY of the three values (-999, null, absurd) is dropped.
    Returns None if the response is not shaped like POWER output."""
    try:
        p = data["properties"]["parameter"]
        t_, rh_, rn_ = p["T2M"], p["RH2M"], p["PRECTOTCORR"]
    except (KeyError, TypeError):
        return None
    out = []
    for d in sorted(t_):
        try:
            t, rh, rn = float(t_[d]), float(rh_[d]), float(rn_[d])
            day = datetime.strptime(d, "%Y%m%d").date()
        except (KeyError, TypeError, ValueError):
            continue
        if -999.0 in (t, rh, rn) or not (-60 <= t <= 60 and 0 <= rh <= 100 and 0 <= rn <= 1000):
            continue
        out.append((day, round(t, 1), round(rh), round(rn, 1)))
    return out


def _power_http(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "harvestly-bot (+https://harvestly-bot.vercel.app)"})
    with urllib.request.urlopen(req, timeout=POWER_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def recent_weather(ward_key, today, now_s, fetch=None):
    """[(date, t, rh, rain)] for the last observed days at an example ward, or None when there is nothing fresh enough to show.
    Fresh cache first; otherwise ONE request for the whole grid cell; on failure the stale copy (at most POWER_STALE_DAYS old)."""
    if ward_key not in WARD_CENTROID:
        return None
    lat, lon = WARD_CENTROID[ward_key]
    cell = power_cell(lat, lon)
    c = _POWER_CACHE.get(cell) or {}
    if c.get("days") and now_s - c["at"] < POWER_FRESH_S:
        days = c["days"]
    elif c.get("failed") and now_s - c["failed"] < POWER_RETRY_S:
        days = c.get("days")
    else:
        days = None
        try:
            start, end = today - timedelta(days=14), today
            url = (f"{POWER_URL}?parameters=T2M,RH2M,PRECTOTCORR&community=AG&latitude={lat:.1f}&longitude={lon:.1f}"
                   f"&start={start:%Y%m%d}&end={end:%Y%m%d}&format=JSON&time-standard=LST")
            days = parse_power((fetch or _power_http)(url))
        except Exception:
            days = None              # 429, timeout, bad JSON: fall back to the stale copy; nothing is logged
        if days:
            _POWER_CACHE[cell] = {"at": now_s, "days": days}
        else:
            c["failed"] = now_s
            _POWER_CACHE[cell] = c
            days = c.get("days")
    if not days or (today - days[-1][0]).days > POWER_STALE_DAYS:
        return None
    return days[-3:]


def weather_text(lang, ward, days):
    """The /weather message: the due-diligence sentence for the newest day, the last days, the credit, the simulated-weather note."""
    d = lambda x: f"{x.day} {MONTHS[lang][x.month - 1]}"
    last = days[-1]
    num = lambda v: f"{v:.1f}"
    line = WEATHER_LINE[lang].format(ward=esc(ward), date=f"{d(last[0])} {last[0].year}", t=num(last[1]), rh=last[2], rain=num(last[3]))
    rows = "\n".join(f"{d(x[0])}: {num(x[1])} C, {x[2]}%, {num(x[3])} mm" for x in days)
    return (f"<b>{WEATHER_TITLE[lang]}</b>\n\n{line}\n\n{WEATHER_DAYS[lang]}\n{rows}\n\n<i>{WEATHER_CREDIT[lang]}</i>\n{WEATHER_NOTE[lang]}")


# ---------------------------------------------------------------------------------------------- forecast (live model forecast)
# /forecast shows the next days for the chat's example ward from a real weather-model forecast (tools/weather_providers.py:
# Open-Meteo first, then WeatherAPI.com, then OpenWeather; compared for Kitale in docs/WEATHER_PROVIDERS.md). Same rules as
# /weather: a server-side call, a ward centroid only (nothing about the chat), a cache, an attribution line per provider, a plain
# fallback when every provider is down. CONTEXT ONLY: it never feeds the engine and never says a sack is safe.
FORECAST_FRESH_S, FORECAST_RETRY_S = 3 * 3600, 10 * 60
_FC_CACHE = {}               # ward -> {"at": epoch seconds, "name": provider, "days": [...]} and/or {"failed": epoch seconds}; per process
FORECAST_TITLE = {"en": "Forecast", "sw": "Utabiri"}
FORECAST_LINE = {"en": "Forecast near {ward} from {name} (a weather-model forecast for the area, not a measurement at your store). Expect about {t} C, humidity {rh}%, {rain} mm rain in the next {n} days.",
                 "sw": "Utabiri karibu na {ward} kutoka {name} (utabiri wa modeli kwa eneo, si kipimo cha ghala lako). Tarajia takriban {t} C, unyevu {rh}%, mvua {rain} mm katika siku {n} zijazo."}
FORECAST_DAYS = {"en": "Next days (temperature, humidity, rain, chance of rain):", "sw": "Siku zijazo (joto, unyevu, mvua, uwezekano wa mvua):"}
FORECAST_CREDIT = {
    "open-meteo": ("Weather data by Open-Meteo.com (CC BY 4.0).", "Data ya hali ya hewa: Open-Meteo.com (CC BY 4.0)."),
    "weatherapi": ("Powered by WeatherAPI.com.", "Inatumia WeatherAPI.com."),
    "openweather": ("Weather data provided by OpenWeather.", "Data ya hali ya hewa kutoka OpenWeather.")}
FORECAST_DOWN = {"en": "The forecast is not available right now. Try again later.",
                 "sw": "Utabiri haupatikani kwa sasa. Jaribu tena baadaye."}
FORECAST_NAMES = {"open-meteo": "Open-Meteo", "weatherapi": "WeatherAPI.com", "openweather": "OpenWeather"}


def live_forecast(ward_key, today, now_s, providers=None):
    """(provider, [day dicts]) for an example ward, or None. Fresh cache first; one provider chain run otherwise; the stale copy
    (under a day old) when every provider fails. `providers` lets tests inject [(name, fn(lat, lon, today))]."""
    if ward_key not in WARD_CENTROID or WP is None:
        return None
    lat, lon = WARD_CENTROID[ward_key]
    c = _FC_CACHE.get(ward_key) or {}
    if c.get("days") and c["days"][0]["day"] > today and now_s - c["at"] < FORECAST_FRESH_S:
        return c["name"], c["days"]
    if not (c.get("failed") and now_s - c["failed"] < FORECAST_RETRY_S):
        name, days = WP.best_forecast(lat, lon, today, os.environ, providers)
        if days:
            _FC_CACHE[ward_key] = {"at": now_s, "name": name, "days": days}
            return name, days
        c["failed"] = now_s
        _FC_CACHE[ward_key] = c
    if c.get("days") and c["days"][0]["day"] > today and now_s - c["at"] < 86400:
        return c["name"], c["days"]
    return None


def forecast_text(lang, ward, name, days):
    """The /forecast message: area summary, the days, the provider credit, the simulated-advice note."""
    i = 1 if lang == "sw" else 0
    d = lambda x: f"{x.day} {MONTHS[lang][x.month - 1]}"
    n = len(days)
    mean = lambda k: sum(x[k] for x in days) / n
    rain = sum(x["rain_mm"] or 0.0 for x in days)
    line = FORECAST_LINE[lang].format(ward=esc(ward), name=FORECAST_NAMES[name], t=f"{mean('temp_c'):.0f}", rh=f"{mean('rh'):.0f}", rain=f"{rain:.0f}", n=n)
    rows = "\n".join(f"{d(x['day'])}: {x['temp_c']:.0f} C, {x['rh']:.0f}%, {(x['rain_mm'] or 0.0):.1f} mm"
                     + (f", {x['rain_prob']:.0f}%" if x.get("rain_prob") is not None else "") for x in days)
    return (f"<b>{FORECAST_TITLE[lang]}</b>\n\n{line}\n\n{FORECAST_DAYS[lang]}\n{rows}\n\n<i>{FORECAST_CREDIT[name][i]}</i>\n{WEATHER_NOTE[lang]}")


# ---------------------------------------------------------------------------------------------- the bot logic
class BotCore:
    def __init__(self, transport, store, H, engine_dir="", now=None, sleep=time.sleep, clock=time.monotonic):
        self.tx, self.store, self.H = transport, store, H
        self.now = now or (lambda: datetime.now(EAT))
        self.sleep, self.clock = sleep, clock
        self.stop = False
        self.kb, self.no_prefix = None, False
        self.in_poll = False
        self.live = {}                  # chat key -> Batch (in memory, with reply history for duplicate detection)
        self.rate = {}                  # chat key -> deque of monotonic times
        self.rate_warned = {}           # chat key -> window start when we last warned
        self.demo_wait = 1.0            # seconds between demo messages (Telegram: ~1 msg/s per chat)
        self._demo_cache = None
        self.engine_dir = engine_dir
        self.photo_base = None          # set to an https base URL to send photos by URL instead of uploading
        self.forecast_providers = None  # tests inject [(name, fn)]; None means the real providers
        self.power_fetch = None         # tests inject a fake POWER fetcher (url -> parsed JSON); None means a real call

    # ---- helpers
    def today(self):
        return self.now().date()

    def meta(self, lang="en"):
        return self.H.WeatherMeta(fetched_on=self.today(), age_hours=0.0,
                                  credit="Hali ya hewa ya kuigwa" if lang == "sw" else "Simulated weather")

    def forecast(self):
        """A fixed, clearly SIMULATED forecast: the engine's normal-weather demo day (18 C, 63 % RH, no rain)."""
        t = self.today()
        return [self.H.WeatherDay(t + timedelta(days=k), 18.0, 63.0, 0.0, 10.0) for k in range(1, 8)]

    def chat(self, key):
        return self.store.data["chats"].setdefault(key, {"lang": None, "banner": False, "optout": False, "batch": None})

    def get_batch(self, key, st):
        b = self.live.get(key)
        if b is None and st.get("batch"):
            try:
                b = batch_from_json(self.H, st["batch"])
            except Exception:
                log.warning("dropping unreadable batch")
                st["batch"] = None
                return None
            self.live[key] = b
        return b

    def put_batch(self, key, st, b):
        self.live[key] = b
        st["batch"] = batch_to_json(b)

    def catch_up(self, b):
        """Simulated days since the last test (the real job does this at 17:00 with real weather)."""
        if b.moisture is None or b.status != "active" or b.last_advanced is None:
            return
        t = self.today()
        d = b.last_advanced + timedelta(days=1)
        n = 0
        while d < t and n < 400:
            self.H.advance_day(b, self.H.WeatherDay(d, 18.0, 63.0, 0.0, 10.0))
            d += timedelta(days=1)
            n += 1

    def send(self, chat_id, html, markup=None):
        """HTML message; if Telegram rejects the markup, resend as plain text. Never raises."""
        html = (html or "")[:4000]
        params = {"chat_id": chat_id, "text": html, "parse_mode": "HTML", "disable_web_page_preview": True}
        if markup:
            params["reply_markup"] = markup
        for attempt in range(3):
            try:
                self.tx.call("sendMessage", params, timeout=20)
                return True
            except TelegramError as e:
                if e.retry_after and attempt < 2:
                    self.sleep(min(e.retry_after, 30))
                elif e.code == 400 and params.get("parse_mode"):
                    params = dict(params, text=plain(html)[:4000])
                    params.pop("parse_mode")
                else:
                    log.warning("sendMessage failed: %s", e)
                    return False
        return False

    def send_photo(self, chat_id, html, name, markup=None):
        """Photo with the formatted text as caption (<=1024). file_id is cached in state after the first upload.
        Returns False (caller falls back to a plain message) if anything fails."""
        files = self.store.data.setdefault("files", {})
        params = {"chat_id": chat_id, "caption": html, "parse_mode": "HTML"}
        if markup:
            params["reply_markup"] = markup
        if self.photo_base:                                    # webhook: Telegram fetches the static file by HTTPS URL
            rel = "logo.png" if name == "logo" else f"cards/{name}.png" if re.fullmatch(r"dial-(?:sw-)?[0-9]{1,2}", name) else None
            if not rel:
                return False
            try:
                self.tx.call("sendPhoto", dict(params, photo=f"{self.photo_base.rstrip('/')}/{rel}"), timeout=20)
                return True
            except Exception as e:
                log.warning("sendPhoto(url) failed: %s", type(e).__name__)
                return False
        try:
            if name in files:
                try:
                    self.tx.call("sendPhoto", dict(params, photo=files[name]), timeout=20)
                    return True
                except TelegramError as e:
                    if e.code != 400:
                        raise
                    files.pop(name, None)                      # stale file_id: upload again
            path = find_asset(name)
            if not path:
                return False
            res = self.tx.upload("sendPhoto", {k: (v if isinstance(v, str) else json.dumps(v)) for k, v in params.items()},
                                 "photo", path, timeout=40)
            try:
                files[name] = res["photo"][-1]["file_id"]
            except (KeyError, IndexError, TypeError):
                pass
            return True
        except Exception as e:
            log.warning("sendPhoto failed: %s", type(e).__name__)
            return False

    @staticmethod
    def L(st):
        """The chat's language; English until a choice is made (only the neutral message is shown before that)."""
        return "sw" if (st or {}).get("lang") == "sw" else "en"

    def lang_of(self, key):
        try:
            lg = self.store.data["chats"].get(key, {}).get("lang")
            return lg if lg in ("en", "sw") else None       # None = no choice yet: SLOW_DOWN / ERROR_TEXT are then bilingual
        except Exception:
            return None

    def rate_ok(self, key):
        now = self.clock()
        q = self.rate.setdefault(key, collections.deque())
        while q and now - q[0] > RATE_WINDOW:
            q.popleft()
        if len(q) >= RATE_MAX:
            return False
        q.append(now)
        return True

    def warn_once(self, key):
        """True the first time a rate-limited window is seen (so the 'slow down' note is sent once per window)."""
        q = self.rate[key]
        if self.rate_warned.get(key) != q[0]:
            self.rate_warned[key] = q[0]
            return True
        return False

    # ---- update handling
    def handle_update(self, upd):
        """Never raises. Returns a short class label for the log."""
        try:
            msg = upd.get("message") if isinstance(upd, dict) else None
            if not isinstance(msg, dict):
                return "ignored"
            chat = msg.get("chat") or {}
            chat_id = chat.get("id")
            if not isinstance(chat_id, int) or chat.get("type") != "private":
                return "ignored"
            key = self.store.chat_key(chat_id)
            if not self.rate_ok(key):
                if self.warn_once(key):
                    self.send(chat_id, SLOW_DOWN[self.lang_of(key)])
                return "rate-limited"
            st = self.chat(key)
            self.kb, self.no_prefix = None, False
            text = msg.get("text")
            if not isinstance(text, str):
                self.deliver(chat_id, st, [NEUTRAL if st.get("lang") is None else NON_TEXT[self.L(st)]])
                return "non-text"
            out, label = self.route(key, st, text[:MAX_INBOUND])
            self.deliver(chat_id, st, out)
            return label
        except Exception as e:      # never crash on bad input; log the class only (no text, no ids)
            log.error("handler error: %s", type(e).__name__)
            try:
                cid = upd["message"]["chat"]["id"]
                if isinstance(cid, int):
                    self.send(cid, ERROR_TEXT[self.lang_of(self.store.chat_key(cid))])
            except Exception:
                pass
            return "error"

    def deliver(self, chat_id, st, out):
        """out: items, each an HTML string or (HTML, photo_name). One Telegram message per item."""
        if not out:
            return
        out = [o if isinstance(o, tuple) else (o, None) for o in out]
        if not st.get("banner"):
            st["banner"] = True
            if not self.no_prefix:                      # first reply says it is a prototype, in the same message
                out[0] = (PREFIX[self.L(st)] + out[0][0], out[0][1])
        try:
            self.tx.call("sendChatAction", {"chat_id": chat_id, "action": "typing"}, timeout=10)
        except TelegramError:
            pass
        for i, (html, photo) in enumerate(out):
            last = i + 1 == len(out)
            mk = self.kb if last else None
            if not (photo and len(html) <= 1024 and self.send_photo(chat_id, html, photo, mk)):
                self.send(chat_id, html, mk)
            if not last:
                self.sleep(self.demo_wait)

    def choose(self, with_logo=False):
        """First contact: the one neutral, bilingual message with the two language buttons."""
        self.kb = keyboard("choose", "en")
        self.no_prefix = True
        return [(NEUTRAL, "logo")] if with_logo else [NEUTRAL]

    def set_lang(self, key, st, new, first):
        """Switch the whole chat to one language: state, the registration, the keyboard and the reply."""
        st["lang"] = new
        b = self.get_batch(key, st)
        if b:
            b.lang = new
            self.put_batch(key, st, b)
            self.kb = keyboard("start" if b.status == "stopped" else "main", new)
        else:
            self.kb = keyboard("idle", new)
        self.no_prefix = True
        if first or not b:                               # a fresh choice (or no registration yet): the welcome, in that language
            return [START_HTML[new] if first else LANG_SET[new] + "\n\n" + START_HTML[new]], "lang:" + new
        return [LANG_SET[new]], "lang:" + new

    def route(self, key, st, text):
        """Returns ([messages], label)."""
        H = self.H
        chosen = st.get("lang") is not None
        lang = self.L(st)
        stripped = text.strip()
        word = LANG_WORDS.get(stripped.lower())
        if word:                                          # a tap on a language button (or the word typed)
            return self.set_lang(key, st, word, first=not chosen)
        if stripped.startswith("/"):
            self.no_prefix = True
            cmd, _, arg = stripped.partition(" ")
            cmd = cmd.split("@")[0].lower()
            arg = arg.strip()
            if cmd == "/lang":
                new = LANG_WORDS.get(arg.lower()) or (arg.lower() if arg.lower() in ("en", "sw") else None)
                if new is None:
                    if not chosen:
                        return self.choose(), "cmd:lang"
                    new = "sw" if lang == "en" else "en"          # no argument: toggle
                return self.set_lang(key, st, new, first=not chosen)
            if cmd == "/stop":
                return self.engine_text(key, st, "STOP")
            if not chosen and cmd != "/reset" and not (cmd == "/start" and st.get("optout")):
                return self.choose(with_logo=cmd == "/start"), "choose"        # nothing else is shown before a choice
            if cmd == "/start":
                b = self.get_batch(key, st)
                if st.get("optout") or (b and b.status == "stopped"):
                    return self.engine_text(key, st, "START")          # an explicit /start is a restart
                return [(START_HTML[lang], "logo")], "cmd:start"
            if cmd == "/help":
                return [HELP_HTML[lang]], "cmd:help"
            if cmd == "/reset":
                self.live.pop(key, None)
                st.update({"batch": None, "optout": False})
                self.kb = {"remove_keyboard": True}
                return [RESET_TEXT[lang]], "cmd:reset"
            if cmd == "/demo":
                return self.demo(lang), "cmd:demo"
            if cmd == "/weather":
                return self.weather(key, st, lang), "cmd:weather"
            if cmd == "/forecast":
                return self.forecast_cmd(key, st, lang), "cmd:forecast"
            return [UNKNOWN_TEXT[lang]], "cmd:unknown"
        return self.engine_text(key, st, stripped)

    def engine_text(self, key, st, text):
        H = self.H
        lang = self.L(st)
        norm = H.normalise(text).upper()
        b = self.get_batch(key, st)
        today = self.today()
        if norm in ("METER READING", "KIPIMO CHA MITA"):
            return [METER_HINT[lang]], "meter-hint"

        # registration (an explicit prototype deviation: allowed even with a batch, so Ken can re-test)
        if RE_JOIN.match(norm) and not (b and b.status == "stopped"):
            return self.register(key, st, norm)
        if b is None:
            # a stranger: STOP is confirmed once, START un-stops, anything else gets the how-to
            if H.is_optout(norm):
                if st.get("optout"):
                    return [], "optout-silent"
                st["optout"] = True
                code_lang = "sw" if re.search(r"(^| )(SIMAMISHA|ACHA|SITISHA|SITAKI)( |$)", norm) else lang
                self.kb = keyboard("start", code_lang)
                st["lang"] = code_lang
                return [fmt_engine(self.stopped_text(code_lang), TITLES[code_lang]["stopped"])], "stop"
            if st.get("optout"):
                if re.match(r"^(START|ANZA)( |$)", norm):
                    st["optout"] = False
                    sw = norm.startswith("ANZA") if st.get("lang") is None else lang == "sw"
                    st["lang"] = "sw" if sw else "en"
                    self.kb = keyboard("start", "sw" if sw else "en")
                    return [fmt_engine(H.TEMPLATES["START_OK"][1 if sw else 0], TITLES["sw" if sw else "en"]["started"])], "start"
                return [], "optout-silent"
            if re.match(r"^SAJILI( |$)", norm) or re.match(r"^(JOIN|REGISTER) .* SW$", norm):
                st["lang"] = lang = "sw"                   # the register word is the choice
            elif re.match(r"^(JOIN|REGISTER)( |$)", norm):
                st["lang"] = lang = "en"
            elif st.get("lang") is None:
                return self.choose(), "choose"             # no language yet: the one neutral message
            return [fmt_engine(HOWTO[lang])], "howto"

        self.catch_up(b)
        cmd, alert = H.respond(b, text, today, self.forecast(), None, None, self.meta(b.lang))
        self.put_batch(key, st, b)
        if alert is None:
            return [], f"engine:{cmd}:silent"
        if cmd == "STOP":
            self.kb = keyboard("start", b.lang)
        elif cmd == "START" or alert.code in MAIN_CODES:
            self.kb = keyboard("main", b.lang)
        elif alert.code in WARN_CODES:
            self.kb = keyboard("warn", b.lang)
        if cmd in ("UNKNOWN", "INVALID"):                  # friendly one-liner instead of the long HELP template
            return [UNKNOWN_TEXT[b.lang]], f"engine:{cmd}"
        T_ = TITLES[b.lang]
        title = (T_["warn"] if alert.code in WARN_CODES else T_["reading"] if cmd in READING_CMDS else
                 T_["stopped"] if cmd == "STOP" else T_["started"] if cmd == "START" else
                 T_["noted"] if cmd == "STORAGE" else None)
        html = fmt_engine(alert.text, title)
        photo = None
        if alert.code in WARN_CODES:
            left = H.days_left(b, self.forecast())
            if left is not None:
                photo = f"dial-{'sw-' if b.lang == 'sw' else ''}{0 if left <= 0 else min(left, 90)}"
        return [(html, photo)], f"engine:{cmd}:{alert.code}"

    def weather(self, key, st, lang):
        """/weather: recent observed days at the chat's example ward (Kitale if none). Context only; no engine run on these days."""
        b = self.get_batch(key, st)
        ward = (b.ward if b and b.ward else "Kitale").upper()
        ward = ward if ward in WARD_CENTROID else "KITALE"
        days = recent_weather(ward, self.today(), self.now().timestamp(), self.power_fetch)
        if not days:
            return [WEATHER_DOWN[lang]]
        return [weather_text(lang, ward.title(), days)]

    def forecast_cmd(self, key, st, lang):
        """/forecast: the next days at the chat's example ward (Kitale if none), from a live forecast. Context only; never feeds the engine."""
        b = self.get_batch(key, st)
        ward = (b.ward if b and b.ward else "Kitale").upper()
        ward = ward if ward in WARD_CENTROID else "KITALE"
        got = live_forecast(ward, self.today(), self.now().timestamp(), self.forecast_providers)
        if not got:
            return [FORECAST_DOWN[lang]]
        return [forecast_text(lang, ward.title(), got[0], got[1])]

    def stopped_text(self, lang):
        return self.H.TEMPLATES["STOPPED"][1 if lang == "sw" else 0]

    def register(self, key, st, norm):
        H = self.H
        lang = "en"
        rest = re.sub(r"^(JOIN|REGISTER|SAJILI) ", "", norm)
        if norm.startswith("SAJILI "):
            lang = "sw"
        if rest.endswith(" SW"):
            lang, rest = "sw", rest[:-3]
        m = re.match(r"^(.*?) *([0-9]+)$", rest)
        bags_t, rest = m.group(2), m.group(1).rstrip()
        parts = rest.rsplit(" ", 1)
        storage_t = parts[-1]
        ward_t = parts[0].strip() if len(parts) == 2 else ""
        store = STORAGE_WORD.get(storage_t)
        howto = HOWTO[lang]
        if not (store and ward_t and re.fullmatch(r"[A-Z ]+", ward_t)):
            return [fmt_engine(howto)], "howto"
        bags = 9999 if len(bags_t.lstrip("0")) > 4 else min(9999, max(1, int(bags_t or 1)))
        ids = [w for w in EXAMPLE_WARDS if w == ward_t] or [w for w in EXAMPLE_WARDS if w.startswith(ward_t)]
        if len(ids) != 1:
            wl = ", ".join(w.title() for w in EXAMPLE_WARDS)
            q = (f"Harvestly: Kata gani? Jibu SAJILI <kata> <hifadhi> <magunia> na mojawapo ya: {wl}." if lang == "sw"
                 else f"Harvestly: Which ward? Reply JOIN <ward> <storage> <bags> with one of: {wl}.")
            return [fmt_engine(q)], "howto-ward"
        today = self.today()
        b = H.Batch(batch_id="tg", ward=ids[0].title(), storage=store, stored_since=today, lang=lang, bags=bags)
        st["lang"], st["optout"] = lang, False
        self.live[key] = b
        body = H.welcome(b, today, self.meta(lang)).text + "\n\n" + H.render("TEST_FIRST", b, "UNKNOWN", None, today, None).text
        out = [fmt_engine(body, TITLES[lang]["register"])]
        self.put_batch(key, st, b)
        self.kb = keyboard("main", lang)
        return out, "register"

    # ---- /demo: the engine's pitch-demo week, using the real vector messages
    def _find(self, name):
        for d in (self.engine_dir, os.path.join(HERE, "..", "engine"), HERE, os.path.expanduser("~/harvestly/engine")):
            p = os.path.join(d or ".", name)
            if os.path.exists(p):
                return p
        return None

    def demo_steps(self, lang="en"):
        """(day, what the farmer sent or None, message, days left or None). English: the engine's vectors.json demo_pitch.
        Kiswahili: demo_sw.json, the same scenario run through the engine's Kiswahili templates (tools/gen_site_data.py)."""
        cache = self._demo_cache if isinstance(self._demo_cache, dict) else {}
        self._demo_cache = cache
        if lang not in cache:
            steps = []
            if lang == "sw":
                path = self._find("demo_sw.json")
                if path:
                    with open(path, encoding="utf-8") as f:
                        steps = [(x["day"], x["said"], x["text"], x["left"]) for x in json.load(f)["steps"]]
            else:
                path = self._find("vectors.json")
                if path:
                    with open(path, encoding="utf-8") as f:
                        sc = next(s for s in json.load(f)["scenarios"] if s["name"] == "demo_pitch")
                    d0 = date.fromisoformat(sc["start"])
                    left = {t["day"]: t.get("days_left") for t in sc["trace"] if t["event"] == "evening"}
                    for t in sc["trace"]:
                        if t.get("message"):
                            n = (date.fromisoformat(t["day"]) - d0).days
                            # B7-01: the contract vectors carry the live design's credit; this bot's demo is simulated weather
                            steps.append((n, t.get("text") if t["event"] == "reply" else None,
                                          t["message"].replace(self.H.CREDIT_OPEN_METEO, "Simulated weather"), left.get(t["day"])))
            cache[lang] = steps
        return cache[lang]

    def demo(self, lang="en"):
        steps = self.demo_steps(lang)
        if not steps:
            return [DEMO_MISSING[lang]]
        n = len(steps)
        out = []
        for i, (day, said, msg, left) in enumerate(steps, 1):
            who = f"farmer sends <code>{esc(said)}</code>" if said else "evening alert"
            if lang == "sw":
                who = f"mkulima anatuma <code>{esc(said)}</code>" if said else "tahadhari ya jioni"
                head = f"<b>Hatua {i}/{n}</b>  siku {day}, {who}"
            else:
                head = f"<b>Step {i}/{n}</b>  day {day}, {who}"
            if i == 1:
                head = DEMO_NOTE[lang] + head
            html = f"{head}\n\n{fmt_engine(msg)}"
            if i == n:
                html += "\n\n" + DEMO_END[lang]
            photo = f"dial-{'sw-' if lang == 'sw' else ''}{0 if left <= 0 else min(int(left), 90)}" if isinstance(left, (int, float)) else None
            out.append((html, photo))
        return out

