"""
Harvestly risk engine v3 - reference implementation (Python 3.9+, standard library only).

What it does
  Tracks one farmer's batch of shelled maize and answers two questions every evening:
    1. Is this grain dry enough for its storage method?
    2. If not, roughly how many days before mould starts to cost grade, and what is the ONE thing to do?

How
  * Moisture comes only from the farmer's own test: salt test (free), hygrometer reading
    (cheap, optional) or moisture-meter reading (co-op / depot / agro-dealer).
    Untested grain gets no countdown - only a request to test.
  * Grain in permeable storage (woven sacks, cribs, floor) drifts toward the equilibrium
    moisture content (EMC) of the surrounding air. Hermetic bags do not exchange moisture.
  * Each day uses 1/AST of the grain's allowable storage time (AST = days to 0.5 % dry-matter
    loss). When the fractions add up to 1, the grain has reached the grade-loss point.

Every number below is tagged:
  SOURCE        - taken from a published table/standard (reference in the concept note)
  CALIBRATION   - a stated pilot value, to be replaced by meter data from the pilot
  PROGRAMME     - a design rule we chose (alert thresholds, reminder spacing)

Three rules keep the advice honest
  1. Only a farmer's TEST can say grain is dry. The model's estimate never does.
  2. When the estimate moves well past the salt-test line, the farmer is asked to RE-TEST;
     the engine never orders drying on an estimate alone.
  3. Every repeated message has a spacing and a cap (see PROGRAMME parameters).

Structure
  advice()     - the ONE current recommendation for a batch, from its state alone.
  daily_run()  - the evening job (17:00 EAT): advance the batch through any un-simulated days,
                 then decide whether to SEND something (at most one proactive message per day):
                 rain in the next 24 h while the farmer is drying > a changed recommendation >
                 a worsening countdown > a capped reminder > the one-off insect reminder.
  respond()    - answers a farmer's reply at once. Replies never use up the evening slot.
  forecast[0] is always tomorrow; rain is judged on the 24 h after the run.

Safety rules added after review R1 (see README "Changes after review R1")
  * STOP and its synonyms apply to the phone number, not one batch (stop_phone / start_phone).
  * A HIGH batch is not left unwarned: if the normal rules are capped, a spaced HIGH_ALERT goes out weekly, at
    most HIGH_ALERT_MAX (4) times per test result; the 4th is a "last reminder, test again to restart" message.
    After that the engine is silent ON PURPOSE (diagnostics flag "high alerts used up") until the farmer sends a
    new test result, a STOP/SOLD, or the grain is sold. This is the closing state (review R2 C-12).
  * A message that was SKIPPED or FAILED never counts as sent (undo / revert_undelivered).
  * Weather older than WEATHER_STALE_HOURS is flagged, never used to judge rain, and the message
    carries the date of the data, not today's date.
  * Every displayed number is rounded ONCE, half-up on the decimal value (fmt0 / fmt1 / fmt2).
  * Messages never say "safe": they say what was measured, when, and that the countdown is an estimate.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

# ======================================================================================
# 1. Lookup tables (SOURCE; both verified cell-by-cell against the publications)
# ======================================================================================
# University of Arkansas Extension FSA1074, Table A "Corn Equilibrium Moisture Content"
# (% wet basis). Rows = air temperature (F), columns = relative humidity (%).
# Note: against measured maize points (Tubbs et al. 2017, Table 3: 14.0 % at 67.6 % RH / 20 C and
# 72.2 % RH / 30 C) this table gives 14.74 and 14.64, i.e. reads about 0.6-0.7 points WETTER - a safety
# margin we keep deliberately.
EMC_TEMPS_F = [35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100]
EMC_RH = [25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90]
EMC_TABLE = [
    [9.3, 10.3, 11.2, 12.1, 13.0, 13.9, 14.8, 15.7, 16.6, 17.6, 18.7, 19.8, 21.2, 22.9],
    [9.1, 10.0, 10.9, 11.8, 12.7, 13.5, 14.4, 15.3, 16.2, 17.1, 18.2, 19.3, 20.7, 22.3],
    [8.8, 9.8, 10.6, 11.5, 12.3, 13.2, 14.0, 14.9, 15.8, 16.7, 17.7, 18.9, 20.2, 21.8],
    [8.6, 9.5, 10.4, 11.2, 12.0, 12.9, 13.7, 14.5, 15.4, 16.3, 17.3, 18.5, 19.8, 21.4],
    [8.4, 9.3, 10.1, 11.0, 11.8, 12.6, 13.4, 14.2, 15.1, 16.0, 17.0, 18.1, 19.3, 20.9],
    [8.2, 9.1, 9.9, 10.7, 11.5, 12.3, 13.1, 13.9, 14.8, 15.7, 16.6, 17.7, 18.9, 20.5],
    [8.0, 8.9, 9.7, 10.5, 11.3, 12.0, 12.8, 13.6, 14.5, 15.3, 16.3, 17.4, 18.6, 20.1],
    [7.9, 8.7, 9.5, 10.3, 11.0, 11.8, 12.6, 13.4, 14.2, 15.0, 16.0, 17.0, 18.2, 19.8],
    [7.7, 8.5, 9.3, 10.1, 10.8, 11.6, 12.3, 13.1, 13.9, 14.8, 15.7, 16.7, 17.9, 19.4],
    [7.6, 8.4, 9.1, 9.9, 10.6, 11.4, 12.1, 12.9, 13.7, 14.5, 15.4, 16.4, 17.6, 19.1],
    [7.4, 8.2, 9.0, 9.7, 10.4, 11.2, 11.9, 12.6, 13.4, 14.3, 15.2, 16.2, 17.3, 18.8],
    [7.3, 8.1, 8.8, 9.5, 10.3, 11.0, 11.7, 12.4, 13.2, 14.0, 14.9, 15.9, 17.0, 18.5],
    [7.2, 7.9, 8.7, 9.4, 10.1, 10.8, 11.5, 12.2, 13.0, 13.8, 14.7, 15.6, 16.8, 18.2],
    [7.1, 7.8, 8.5, 9.2, 9.9, 10.6, 11.3, 12.0, 12.8, 13.6, 14.5, 15.4, 16.5, 17.9],
]

# University of Arkansas Extension FSA1058, Table 1 "Safe Storage Period for Corn (Days)",
# about 0.5 % dry-matter loss. Rows = GRAIN temperature (F) (source lists them descending),
# columns = moisture (% wet basis). The table covers 15-30 % moisture. The source states its 0.5 %
# dry-matter loss as the loss of one US grade level, so "grade" in our text is a US-grade statement.
# Neither Arkansas PDF says "yellow" corn; the ASAE parameters behind them are for yellow dent corn, and
# nobody has validated them for Kenyan white maize (ASSUMPTIONS 6).
AST_TEMPS_F = [35, 40, 45, 50, 55, 60, 65, 70, 75]
AST_MC = [15, 17, 19, 21, 23, 25, 30]
AST_TABLE = [
    [2126, 671, 295, 161, 102, 72, 41],   # 35 F
    [1413, 448, 197, 107, 68, 48, 27],    # 40 F
    [931, 299, 131, 72, 45, 32, 18],      # 45 F
    [621, 199, 88, 48, 30, 21, 12],       # 50 F
    [414, 133, 58, 32, 21, 14, 8],        # 55 F
    [275, 88, 39, 22, 14, 10, 6],         # 60 F
    [206, 66, 29, 16, 11, 8, 5],          # 65 F
    [154, 49, 22, 12, 8, 6, 4],           # 70 F
    [115, 37, 16, 9, 6, 5, 3],            # 75 F
]

# ======================================================================================
# 2. Thresholds and parameters
# ======================================================================================
EAS_MAX_MC = 13.5            # SOURCE: EAS 2 maize grain standard (DEAS 2:2024) - storage/sale/NCPB/WRS gate
HERMETIC_MAX_MC = 14.0       # SOURCE: Ng'ang'a et al. 2016 (J. Stored Prod. Res. 69) - hermetic bags stop
                             #         aflatoxin build-up only if grain is below 14 %
SALT_LINE_MC = 15.0          # SECONDARY, UNVERIFIED: rule of thumb attributed to Johnson 1992 (CSIR-FRI Ghana); the paper was never opened
SALT_STICKY_MC = 18.0        # CALIBRATION: point value used for the countdown when salt sticks (true value >15 %)
SALT_FLOWS_MC = 14.5         # CALIBRATION: salt flows = at most ~15 %; never treated as proof of <=13.5 %
SACK_EXCHANGE_RATE = 0.05    # CALIBRATION: share of the gap to EMC closed per day in woven sacks. Same order of
                             #   magnitude as Afzal et al. 2017 (12.5 -> 15.6 % over 2 months in woven polypropylene bags,
                             #   one final reading, wetting not drying): NOT a validation. Replace with pilot data.
                             #   The headline demo depends on it (see ASSUMPTIONS 3).
MAX_AST_DAYS = 3650.0        # cap for very dry grain (table edge is 15 %; below that we extrapolate and flag)

RAIN_PROB_ALERT = 60.0       # PROGRAMME: % chance of rain in the next 24 h that triggers "cover it"
RAIN_MM_ALERT = 5.0          # PROGRAMME: mm of rain in the next 24 h that triggers "cover it"
HIGH_LIFE, HIGH_DAYS = 0.8, 14     # PROGRAMME: HIGH if >=80 % of safe life used or <=14 days left
MEDIUM_LIFE, MEDIUM_DAYS = 0.5, 30  # PROGRAMME: MEDIUM if >=50 % used or <=30 days left
                                    #   (lead time: sun-drying needs several dry days in a wet season)
REMIND_GAP_DAYS = 3          # PROGRAMME: an unanswered HIGH warning repeats at most every 3 days
SEALED_GAP_DAYS = 7          # PROGRAMME: an unanswered sealed-bag warning repeats at most every 7 days
REPEAT_MAX = 2               # PROGRAMME: at most 2 repeats of the same warning per test result
WORSE_FACTOR, WORSE_WITHIN = 0.5, 60  # PROGRAMME: also warn again when the countdown has at least halved
                             #   since the farmer was last told, and is now 60 days or less
RETEST_MARGIN = 1.0          # PROGRAMME: the estimate must pass the salt line by 1 point (16 % up, 14 % down)
RETEST_PER_30_DAYS = 2       # PROGRAMME: at most 2 re-test requests in any 30 days (no test-loops)
TEST_REMINDERS_MAX = 3       # PROGRAMME: an untested farmer is asked to test at most 3 times
RAIN_UNACKED_MAX = 3         # PROGRAMME: rain alerts pause after 3 in a row with no reply; any reply resumes
PLACE_MAX_CHARS = 32         # PROGRAMME: directory names are cut to this length (SMS length is tested with it)
INSECT_REMINDER_DAYS = 49    # SOURCE-BASED (week 7 is not stated in the abstracts; unverified): Ng'ang'a et al. 2016
                             #   (Food Security 8) - WEIGHT LOSS in woven sacks well above hermetic; clocked from
                             #   stored_since, not from harvest
HORIZON_DAYS = 365           # longest countdown computed. A result of 365 means "365 or more": the tool stops looking.
HIGH_ALERT_GAP_DAYS = 7      # PROGRAMME: a HIGH batch whose normal messages are capped still hears from us weekly ...
HIGH_ALERT_MAX = 4           # PROGRAMME: ... at most 4 times per test result; the 4th says it is the last
WEATHER_STALE_HOURS = 24     # PROGRAMME: weather fetched more than 24 h ago is flagged stale and not used for rain alerts
WEEKS_CAP = 99               # PROGRAMME: "{weeks}" never exceeds 2 digits, so INSECT_REMINDER keeps its 2-SMS budget
NORM_STORE_CHARS = 250       # PROGRAMME: only this much of a normalised reply is stored / compared for duplicates
MAX_TEXT_CHARS = 1000        # PROGRAMME: inbound text is cut to this many characters before parsing; never raises
CREDIT_OPEN_METEO = "Open-Meteo.com"    # short credit inside alerts; the full attribution is in WELCOME and the README
ATTRIBUTION = ("Weather data by Open-Meteo.com (https://open-meteo.com), licensed CC BY 4.0 "
               "(https://creativecommons.org/licenses/by/4.0/). Values are averaged by Harvestly and drive an estimate.")
# Retention (days), see README "Privacy". Python is the contract; the PL/SQL purge job uses the same numbers.
RETAIN_INBOUND_TEXT_DAYS = 30    # raw inbound text is blanked after this
RETAIN_SENT_ADDRESS_DAYS = 30    # a recipient address is blanked from a message this long after it is sent/failed
RETAIN_MESSAGE_DAYS = 180        # message rows are deleted after this
RETAIN_RUNLOG_DAYS = 90          # run-log rows (and their error text) are deleted after this
RETAIN_ENDED_BATCH_DAYS = 90     # a closed or stopped batch loses its phone number this long after it ended
OPTOUT_WORDS = frozenset({"STOP", "STOPP", "STOPPED", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "ACHA", "SITISHA",
                          "SIMAMISHA", "NISITISHIE"})
OPTOUT_PHRASES = frozenset({"NO MORE", "OPT OUT", "SITAKI TENA"})
OPTOUT_MAX_TOKENS = 6        # PROGRAMME: an opt-out word counts anywhere in a message of at most 6 words
LIMIT_STRINGS = ("13.5", "14.0", "15.0")             # numbers the text compares against: show 2 decimals near them

# Assumptions the advice rests on. Every one is shown to the reader in the README and in the site data.
# label: SOURCE (published) | CALIBRATION (pilot value) | PROGRAMME (design rule) | UNVALIDATED (modelling choice, no source)
ASSUMPTIONS = (
    (1, "CALIBRATION", "Salt that sticks is treated as 18 % moisture (the true value is anything above 15 %)."),
    (2, "CALIBRATION", "Salt that flows is treated as 14.5 % and never counts as proof of 13.5 % or less."),
    (3, "CALIBRATION", "A woven sack closes 5 % of the gap to the air's equilibrium moisture per day. The headline demo "
                       "(261 days, then 34) depends on it: with 0 %/day it reads 45, 43, 42 days; with 2 %/day 145, 143, 38."),
    (4, "CALIBRATION", "Grain temperature equals the daily mean air temperature (the storage-time table is for grain temperature)."),
    (5, "PROGRAMME", "Alert thresholds (80 % / 50 % of life, 14 / 30 days), spacing and caps are design rules, not findings."),
    (6, "UNVALIDATED", "The Arkansas tables were built for US corn and have not been validated for Kenyan white maize."),
    (7, "UNVALIDATED", "Outdoor regional weather stands in for the conditions inside the sack."),
    (8, "UNVALIDATED", "Daily means of temperature and humidity are used although the moisture table is not linear."),
    (9, "UNVALIDATED", "The storage-life clock starts at the farmer's first test, not at harvest (the source clocks from harvest)."),
    (10, "UNVALIDATED", "Drying grain keeps its tested moisture and still uses up storage life at that moisture."),
    (11, "UNVALIDATED", "Hermetic bags are perfectly sealed: moisture stays constant."),
    (12, "UNVALIDATED", "Weather beyond the 7-day forecast equals the 7-day mean."),
    (13, "PROGRAMME", "A countdown is capped at 365 days (HORIZON_DAYS) and storage time at 3650 days (MAX_AST_DAYS); a 365 means 365 or more."),
    (14, "UNVALIDATED", "Sacks, cribs and floors all drift at the same rate."),
    (15, "UNVALIDATED", "Relative humidity above 90 % is treated as 90 % (the table ends there), and below 25 % as 25 %."),
)

PERMEABLE = frozenset({"sack", "crib", "floor"})
HERMETIC = frozenset({"hermetic"})
DRYING = frozenset({"drying"})
STORAGE_TYPES = PERMEABLE | HERMETIC | DRYING
MEASURED = frozenset({"meter", "hygro"})       # sources that give an actual number
LEVEL_ORDER = {"UNKNOWN": -1, "LOW": 0, "MEDIUM": 1, "HIGH": 2}


# ======================================================================================
# 3. Physics
# ======================================================================================
def c_to_f(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


def fmt(x: float, places: int) -> str:
    """The ONE rounding rule for every number shown to a farmer or compared across ports:
    first correct the binary noise (round to 10 decimals), then round HALF UP on the decimal value.
    13.25 -> '13.3', 5.05 -> '5.1', 0.5 mm -> '1'. PL/SQL: ROUND(ROUND(x, 10), places); JS: fmt() in engine.js."""
    q = Decimal(f"{x:.10f}").quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return f"{q:.{places}f}"


def fmt0(x: float) -> str:
    return fmt(x, 0)


def fmt1(x: float) -> str:
    return fmt(x, 1)


def fmt2(x: float) -> str:
    return fmt(x, 2)


def rnd1(x: float) -> float:
    """fmt1 as a number (diagnostics, vectors)."""
    return float(fmt1(x))


def _bracket(axis: list, x: float) -> tuple:
    """Index i and fraction t so that x = axis[i] + t*(axis[i+1]-axis[i]); t<0 or >1 only at the edges."""
    if x <= axis[0]:
        i = 0
    elif x >= axis[-1]:
        i = len(axis) - 2
    else:
        i = max(j for j in range(len(axis) - 1) if axis[j] <= x)
    return i, (x - axis[i]) / (axis[i + 1] - axis[i])


def emc(temp_c: float, rh: float) -> tuple:
    """Equilibrium moisture content (% w.b.) of maize at air temp (C) and RH (%).
    Bilinear interpolation, clamped to the table range. Returns (value, warnings)."""
    warnings = []
    tf = c_to_f(temp_c)
    if not EMC_TEMPS_F[0] <= tf <= EMC_TEMPS_F[-1]:
        warnings.append("EMC temperature clamped")
        tf = min(max(tf, EMC_TEMPS_F[0]), EMC_TEMPS_F[-1])
    if not EMC_RH[0] <= rh <= EMC_RH[-1]:
        warnings.append("EMC humidity clamped")
        rh = min(max(rh, EMC_RH[0]), EMC_RH[-1])
    i, ti = _bracket(EMC_TEMPS_F, tf)
    j, tj = _bracket(EMC_RH, rh)
    top = EMC_TABLE[i][j] + tj * (EMC_TABLE[i][j + 1] - EMC_TABLE[i][j])
    bot = EMC_TABLE[i + 1][j] + tj * (EMC_TABLE[i + 1][j + 1] - EMC_TABLE[i + 1][j])
    return top + ti * (bot - top), warnings


def ast_days(temp_c: float, mc: float) -> tuple:
    """Allowable storage time (days) at grain temp (C) and moisture (% w.b.).
    Bilinear interpolation of ln(days). Below 15 % moisture or above 75 F it extrapolates
    log-linearly from the table edge (flagged). Capped at MAX_AST_DAYS. Returns (days, warnings)."""
    warnings = []
    tf = c_to_f(temp_c)
    if tf > AST_TEMPS_F[-1]:
        warnings.append("AST temperature extrapolated")
    if tf < AST_TEMPS_F[0]:
        tf = AST_TEMPS_F[0]
        warnings.append("AST temperature clamped")
    m = mc
    if m > AST_MC[-1]:
        m = AST_MC[-1]
        warnings.append("AST moisture clamped")
    if m < AST_MC[0]:
        warnings.append("AST moisture extrapolated")
    i, ti = _bracket(AST_TEMPS_F, tf)
    j, tj = _bracket(AST_MC, m)
    ln = [[math.log(AST_TABLE[r][c]) for c in (j, j + 1)] for r in (i, i + 1)]
    top = ln[0][0] + tj * (ln[0][1] - ln[0][0])
    bot = ln[1][0] + tj * (ln[1][1] - ln[1][0])
    return min(math.exp(top + ti * (bot - top)), MAX_AST_DAYS), warnings



# ======================================================================================
# 4. State
# ======================================================================================
@dataclass
class WeatherDay:
    day: date
    temp_c: float                      # daily mean air temperature (used as grain temperature: CALIBRATION)
    rh: float                          # daily mean relative humidity, %
    rain_mm: Optional[float] = 0.0     # daily total; None = not available
    rain_prob: Optional[float] = None  # daily max probability of precipitation, %; None = not available


@dataclass
class Batch:
    batch_id: str
    ward: str                          # forecast is fetched once per ward, not per farmer
    storage: str                       # drying | sack | crib | floor | hermetic
    stored_since: date                 # date the grain entered its current storage
    lang: str = "en"                   # en | sw
    bags: int = 1                      # 90 kg bags (reporting only)
    moisture: Optional[float] = None   # current ESTIMATE (% w.b.); None = untested
    source: str = "none"               # none | salt_sticky | salt_flows | hygro | meter
    last_test: Optional[date] = None
    test_value: Optional[float] = None # value set by the last test, before any drift
    peak_since_test: Optional[float] = None  # highest estimate since the last test
    life_used: float = 0.0             # share of allowable storage time used (never decreases)
    last_advanced: Optional[date] = None
    last_alert: Optional[date] = None  # last PROACTIVE message (replies do not count)
    last_advice: Optional[str] = None  # last recommendation the farmer was given (alert or reply)
    told_level: str = "UNKNOWN"        # risk level when the farmer was last given advice
    told_left: Optional[int] = None    # days left when the farmer was last given advice
    rain_unacked: int = 0              # rain alerts sent since the farmer last replied
    status: str = "active"             # active | closed (sold/deposited) | stopped (opted out)
    last_run: Optional[date] = None    # day the evening job last completed for this batch (idempotency)
    sent: list = field(default_factory=list)     # [(date, code)] every outgoing message
    replies: list = field(default_factory=list)  # [(date, normalised text)] every incoming reply
    acks: list = field(default_factory=list)     # [date] "1"/OK replies, for alert-to-action metrics

    def __post_init__(self):
        if self.storage not in STORAGE_TYPES:
            raise ValueError(f"unknown storage type {self.storage!r}")
        if self.lang not in ("en", "sw"):
            raise ValueError("lang must be 'en' or 'sw'")
        if self.moisture is not None:      # e.g. loaded from the database
            if self.source == "none":
                raise ValueError("a moisture value needs its source")
            if self.test_value is None:
                self.test_value = self.moisture
            if self.peak_since_test is None:
                self.peak_since_test = max(self.moisture, self.test_value)

    def stale(self) -> bool:
        """True if the estimate has risen well past the salt line since the last (dry) test,
        so that test can no longer vouch for the grain."""
        return self.peak_since_test is not None and self.peak_since_test > SALT_LINE_MC + RETEST_MARGIN

    def verdict(self) -> str:
        """What the farmer's LAST TEST says (never the estimate): UNTESTED | WET | NOT_PROVEN | DRY."""
        if self.moisture is None:
            return "UNTESTED"
        if self.source == "salt_sticky" or self.test_value > SALT_LINE_MC:
            return "WET"
        if self.source in MEASURED and self.test_value <= EAS_MAX_MC and not self.stale():
            return "DRY"
        return "NOT_PROVEN"                 # salt flows, a reading of 13.5-15 %, or a test since outdated

    # ---- moisture inputs -------------------------------------------------------------
    def _set_moisture(self, on: date, mc: float, source: str) -> None:
        if self.last_advanced is None:      # start the clock on the first test
            self.last_advanced = on - timedelta(days=1)
        self.moisture, self.source, self.last_test, self.test_value = mc, source, on, mc
        self.peak_since_test = mc

    def record_salt(self, on: date, sticky: bool) -> bool:
        """Returns False if 'salt flows' was ignored: a meter/hygrometer reading of 15 % or less
        in the last 7 days is more informative, unless the estimate has since risen past 15 %.
        'Salt sticks' always counts: it is the conservative direction."""
        if (not sticky and self.source in MEASURED and self.test_value <= SALT_LINE_MC
                and self.moisture <= SALT_LINE_MC and (on - self.last_test).days <= 7):
            return False
        self._set_moisture(on, SALT_STICKY_MC if sticky else SALT_FLOWS_MC,
                           "salt_sticky" if sticky else "salt_flows")
        return True

    def record_meter(self, on: date, reading: float) -> None:
        if not 5.0 <= reading <= 40.0:
            raise ValueError("moisture meter reading must be between 5 and 40 %")
        self._set_moisture(on, reading, "meter")

    def record_hygro(self, on: date, rh: float, temp_c: float, offset: float = 0.0) -> None:
        """Hygrometer sealed in a bag of grain until steady (Tubbs et al. 2017: 30-45 min for cheap devices).
        offset = calibration correction from the salt check (saturated salt reads ~75 %)."""
        rh_c = rh + offset
        if not 0.0 < rh_c < 100.0 or not -5.0 <= temp_c <= 45.0:
            raise ValueError("hygrometer reading out of range")
        self._set_moisture(on, emc(temp_c, rh_c)[0], "hygro")

    def set_storage(self, on: date, storage: str) -> None:
        if storage not in STORAGE_TYPES:
            raise ValueError(f"unknown storage type {storage!r}")
        if storage != self.storage:
            self.storage, self.stored_since = storage, on

    def count_sent(self, code: str, since: Optional[date] = None) -> int:
        return sum(c == code and (since is None or d >= since) for d, c in self.sent)

    def snapshot(self) -> dict:
        """State a message changes when it is generated; kept so an undelivered message can be undone."""
        return {"last_alert": self.last_alert, "last_advice": self.last_advice, "told_level": self.told_level,
                "told_left": self.told_left, "rain_unacked": self.rain_unacked, "sent_len": len(self.sent)}


# ======================================================================================
# 5. Daily simulation
# ======================================================================================
def advance_day(b: Batch, w: WeatherDay) -> None:
    """Move the batch through day w.day. Idempotent: a day is never counted twice."""
    if b.moisture is None or b.status != "active":
        return
    if b.last_advanced is not None and w.day <= b.last_advanced:
        return
    if b.storage in PERMEABLE:
        b.moisture += SACK_EXCHANGE_RATE * (emc(w.temp_c, w.rh)[0] - b.moisture)
        b.peak_since_test = max(b.peak_since_test, b.moisture)
    # drying: moisture changes only with the next test (sun-drying is too variable to model;
    # holding it constant is the conservative choice). hermetic: no exchange with outside air.
    b.life_used += 1.0 / ast_days(w.temp_c, b.moisture)[0]
    b.last_advanced = w.day


def days_left(b: Batch, forecast: list) -> Optional[int]:
    """Days until life_used reaches 1: the forecast first, then the forecast mean repeated.
    None if the batch is untested or there is no forecast."""
    if b.moisture is None or not forecast:
        return None
    if b.life_used >= 1.0:
        return 0
    mean_t = sum(d.temp_c for d in forecast) / len(forecast)
    mean_rh = sum(d.rh for d in forecast) / len(forecast)
    used, m = b.life_used, b.moisture
    for n in range(HORIZON_DAYS):
        t, rh = (forecast[n].temp_c, forecast[n].rh) if n < len(forecast) else (mean_t, mean_rh)
        if b.storage in PERMEABLE:
            m += SACK_EXCHANGE_RATE * (emc(t, rh)[0] - m)
        used += 1.0 / ast_days(t, m)[0]
        if used >= 1.0:
            return n + 1
    return HORIZON_DAYS


def risk_level(life_used: float, left: Optional[int]) -> str:
    if left is None:
        return "UNKNOWN"
    if life_used >= HIGH_LIFE or left <= HIGH_DAYS:
        return "HIGH"
    if life_used >= MEDIUM_LIFE or left <= MEDIUM_DAYS:
        return "MEDIUM"
    return "LOW"


# ======================================================================================
# 6. The single current recommendation
# ======================================================================================
def advice(b: Batch) -> Optional[str]:
    """What should this farmer do now? None = nothing (grain measured safe in sealed bags)."""
    v = b.verdict()
    if v == "UNTESTED":
        return "TEST_FIRST"
    if b.life_used >= HIGH_LIFE:
        return "SORT_AND_SELL"
    if b.storage in HERMETIC:
        fresh_reading = b.source in MEASURED and not b.stale()
        if v == "WET" or (fresh_reading and b.test_value >= HERMETIC_MAX_MC):
            return "OPEN_AND_DRY"           # the last test said too wet to seal
        if fresh_reading and b.moisture < HERMETIC_MAX_MC:
            return None                     # measured below 14 % and not re-wetted before sealing
        return "CONFIRM_DRY"                # salt test only, or re-wetted in sacks before sealing
    if v == "WET":                          # test says wet; in sacks it may have dried since
        return "RETEST" if b.storage in PERMEABLE and b.moisture < SALT_LINE_MC - RETEST_MARGIN else "DRY_NOW"
    if b.storage in PERMEABLE and b.moisture > SALT_LINE_MC + RETEST_MARGIN:
        return "RETEST"                     # test says dry, estimate says it has re-wetted: verify
    return "READY_TO_STORE" if v == "DRY" and b.moisture <= EAS_MAX_MC else "NEARLY_DRY"


# ======================================================================================
# 7. Messages (GSM-7 only, max 2 SMS segments after filling - checked by tests)
# ======================================================================================
TEMPLATES = {
    "RAIN_COVER": (
        "Harvestly: Rain likely {rain_when} ({rain}). Cover your drying maize or bring it indoors now. "
        "Reply 1 when covered. {credit} {date}.",
        "Harvestly: Mvua inatarajiwa {rain_when} ({rain}). Funika mahindi unayoanika au uyaingize ndani "
        "sasa. Jibu 1 ukishafunika. {credit} {date}."),
    "TEST_FIRST": (
        "Harvestly: We do not know how wet your maize is yet. Test it before you store it: use a "
        "moisture meter at your co-op or NCPB depot and reply METER and the number, e.g. METER 14.2. "
        "Salt test (draft, unconfirmed): reply SALT YES if salt sticks, SALT NO if it stays loose.",
        "Harvestly: Hatujui bado mahindi yako yana unyevu kiasi gani. Yapime kabla ya kuhifadhi: tumia "
        "mita ya unyevu kwenye chama chako au bohari ya NCPB kisha jibu MITA na namba, mf. MITA 14.2. "
        "Kipimo cha chumvi (rasimu, bado hakijathibitishwa): jibu CHUMVI NDIYO chumvi ikinata, "
        "CHUMVI HAPANA ikibaki huru."),
    "OPEN_AND_DRY": (
        "Harvestly: Maize sealed at 14% moisture or more can still go mouldy ({evidence}). Storage time "
        "left: {risk}. Open the bags, dry the maize in full sun and reply DRYING. Reseal only after a "
        "test shows it is dry.",
        "Harvestly: Mahindi yaliyofungwa yakiwa na unyevu wa 14% au zaidi bado yanaweza kuota kuvu "
        "({evidence}). Muda uliobaki: {risk}. Fungua mifuko, anika juani kisha jibu ANIKA. "
        "Usifunge tena mpaka kipimo kionyeshe yamekauka."),
    "CONFIRM_DRY": (
        "Harvestly: Sealed bags protect maize only below 14% moisture, and this is not yet confirmed "
        "({evidence}). Within a week, get a meter check at {checkpoint} and reply METER with the number.",
        "Harvestly: Mifuko isiyopitisha hewa hulinda mahindi yenye unyevu chini ya 14% tu, na hili "
        "bado halijathibitishwa ({evidence}). Ndani ya wiki moja, pima kwa mita katika {checkpoint} "
        "kisha tuma MITA na namba."),
    "SORT_AND_SELL": (
        "Harvestly: This batch has used most of its estimated storage time. Check it today: remove "
        "mouldy or discoloured grain (do not eat it or feed it to animals), then sell or use this batch first.",
        "Harvestly: Mahindi haya yametumia sehemu kubwa ya muda wa uhifadhi uliokadiriwa. Yakague leo: "
        "ondoa punje zenye kuvu au zilizobadilika rangi (usizile wala usiwalishe mifugo), kisha yauze au "
        "uyatumie kwanza."),
    "HIGH_ALERT": (
        "Harvestly: URGENT. Storage time left: {risk}. Check this maize today: remove mouldy or "
        "discoloured grain (do not eat it or feed it to animals), then sell or use it first. {closing}",
        "Harvestly: HARAKA. Muda uliobaki: {risk}. Kagua mahindi haya leo: ondoa punje "
        "zenye kuvu au zilizobadilika rangi (usizile wala usiwalishe mifugo), kisha yauze au uyatumie "
        "kwanza. {closing}"),
    "DRY_NOW": (
        "Harvestly: Your maize is too wet to store ({evidence}). Storage time left: {risk}. Dry it on a "
        "tarpaulin in full sun{reply_drying}, then test again. {credit} {date}.",
        "Harvestly: Mahindi yako yana unyevu mwingi mno kuhifadhiwa ({evidence}). Muda uliobaki: "
        "{risk}. Yaanike juu ya turubai juani{reply_drying}, kisha pima tena. {credit} {date}."),
    "RETEST": (
        "Harvestly: {why} ({evidence}). Storage time left: {risk}. Do the salt test today and reply "
        "SALT YES or SALT NO. {credit} {date}.",
        "Harvestly: {why} ({evidence}). Muda uliobaki: {risk}. Fanya kipimo cha chumvi leo "
        "kisha jibu CHUMVI NDIYO au CHUMVI HAPANA. {credit} {date}."),
    "NEARLY_DRY": (
        "Harvestly: Not yet proven dry enough to seal or sell ({evidence}); the limit is 13.5%. Dry "
        "more in full sun if needed, then confirm with a meter at {checkpoint}. Reply METER and the number.",
        "Harvestly: Bado haijathibitishwa kuwa mahindi yamekauka vya kutosha kufungwa au kuuzwa "
        "({evidence}); kiwango ni 13.5%. Anika zaidi juani ikihitajika, kisha thibitisha kwa mita katika "
        "{checkpoint}. Jibu MITA na namba."),
    "READY_TO_STORE": (
        "Harvestly: Dry enough to store ({evidence}). Seal it in hermetic bags ({stockist}) or deposit "
        "it at {warehouse} for a warehouse receipt. Reply SEALED, SOLD or DEPOSITED when done.",
        "Harvestly: Mahindi yamekauka vya kutosha ({evidence}). Yafunge kwenye mifuko isiyopitisha hewa "
        "({stockist}) au yaweke kwenye {warehouse} upate stakabadhi ya ghala. Ukimaliza jibu NIMEFUNGA, "
        "NIMEUZA au GHALANI."),
    "INSECT_REMINDER": (
        "Harvestly: Your maize has been in sacks or open storage for {weeks} weeks. Weevil damage "
        "grows the longer maize stays in sacks. It tested dry, so consider moving it into hermetic bags "
        "({stockist}) or selling soon.",
        "Harvestly: Mahindi yako yamekaa kwenye magunia au hifadhi ya wazi wiki {weeks}. Uharibifu "
        "wa fukusi huongezeka mahindi yakikaa muda mrefu kwenye magunia. Kipimo kilionyesha "
        "yamekauka, kwa hiyo fikiria kuyahamishia kwenye mifuko isiyopitisha hewa ({stockist}) au kuyauza mapema."),
    "STATUS": (
        "Harvestly: Recorded ({measured}). Storage time left: {risk}. This is an "
        "estimate, not a guarantee.",
        "Harvestly: Tumepokea ({measured}). Muda wa kuhifadhi uliobaki: {risk}. "
        "Ni makadirio, si hakikisho."),
    "WELCOME": (
        "Harvestly: Welcome. These messages give storage advice for your maize by SMS. It is an estimate. Weather "
        "data by Open-Meteo.com (CC BY 4.0). Reply STOP at any time to stop all messages.",
        "Harvestly: Karibu. Ujumbe huu unatoa ushauri wa kuhifadhi mahindi yako kwa SMS. Ni makadirio. Data ya "
        "hali ya hewa: Open-Meteo.com (CC BY 4.0). Jibu SIMAMISHA wakati wowote kusimamisha ujumbe wote."),
    "HELP": (
        "Harvestly: Sorry, we did not understand. Reply SALT YES, SALT NO, METER 14.2, HYGRO 62 18, "
        "DRYING, SACKS, SEALED, SOLD, DEPOSITED or STOP.",
        "Harvestly: Samahani, hatukuelewa. Jibu CHUMVI NDIYO, CHUMVI HAPANA, MITA 14.2, HYGRO 62 18, "
        "ANIKA, MAGUNIA, NIMEFUNGA, NIMEUZA, GHALANI au SIMAMISHA."),
    "THANKS": ("Harvestly: Thank you, noted.", "Harvestly: Asante, tumepokea."),
    # C3-14: sent by the SMS handler when a number with no batch says START after STOP (a template, so it has Kiswahili)
    "START_OK": (
        "Harvestly: Messages are on again for this number. To register grain reply JOIN <ward> <storage> <bags>, "
        "e.g. JOIN KITALE SACK 12. Reply STOP to stop.",
        "Harvestly: Ujumbe umewashwa tena kwa namba hii. Kusajili mahindi jibu SAJILI <kata> <hifadhi> <magunia>, "
        "mf. SAJILI KITALE MAGUNIA 12. Jibu SIMAMISHA kusimamisha."),
    "CLOSED": (
        "Harvestly: Noted. Alerts for this batch have ended. Reply START to restart them.",
        "Harvestly: Tumepokea. Arifa za mahindi haya zimekoma. Jibu ANZA kuziwasha tena."),
    "STOPPED": (
        "Harvestly: You will get no more messages on this number, for any batch. Reply START to restart.",
        "Harvestly: Hutapokea ujumbe zaidi kwenye namba hii, kwa mahindi yoyote. Jibu ANZA kuanza tena."),
}

DEFAULT_PLACES = {   # used when the pilot directory has no entry, so no placeholder ever reaches a farmer
    "en": {"stockist": "an agro-dealer near you", "warehouse": "a certified warehouse",
           "checkpoint": "your co-op or NCPB depot"},
    "sw": {"stockist": "duka la pembejeo karibu nawe", "warehouse": "ghala lililoidhinishwa",
           "checkpoint": "chama chako au bohari ya NCPB"},
}
PLACE_KEYS = ("stockist", "warehouse", "checkpoint")   # the only keys a directory entry may set

_GSM_SAFE = re.compile(r"[^A-Za-z0-9 .,:;!?'()&/+\-%@\"#*=<>]")
_TRANSLIT = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"',
                           "–": "-", "—": "-", "\u00a0": " "})


def _place(s: str) -> str:
    """Directory names: plain GSM-7 characters only, at most PLACE_MAX_CHARS."""
    s = _GSM_SAFE.sub("", s.translate(_TRANSLIT))
    return " ".join(s.split())[:PLACE_MAX_CHARS].rstrip(" ,.-")


@dataclass
class Alert:
    code: str
    level: str
    text: str            # in the farmer's language
    other: str           # the same message in the other language (dashboard / audit)
    undo: Optional[dict] = None   # Batch.snapshot() taken before this message changed the batch


def revert_undelivered(b: Batch, alert: Alert) -> None:
    """The message was SKIPPED (too long / not GSM-7) or FAILED for good: it never reached the farmer.
    Take it back out of the send history and restore what it changed, so it burns no cap and the next run
    tells the farmer again."""
    u = alert.undo
    if not u:
        return
    if u["sent_len"] < len(b.sent):
        del b.sent[u["sent_len"]]
    b.last_alert, b.last_advice = u["last_alert"], u["last_advice"]
    b.told_level, b.told_left, b.rain_unacked = u["told_level"], u["told_left"], u["rain_unacked"]


@dataclass
class WeatherMeta:
    """Where the weather came from. fetched_on = date of the fetch; age_hours = how old it is now."""
    fetched_on: Optional[date] = None
    age_hours: float = 0.0
    credit: str = CREDIT_OPEN_METEO     # demos pass "Simulated weather"

    @property
    def stale(self) -> bool:
        return self.age_hours > WEATHER_STALE_HOURS


def _pct(x: float) -> str:
    """A moisture for the farmer. One decimal, but two when one decimal would hide which side of a limit
    the number is on (13.54 shown as '13.5' next to 'the limit is 13.5')."""
    one = fmt1(x)
    if one in LIMIT_STRINGS and fmt2(x) != one + "0":      # decided on the rounded strings, so every port agrees
        return fmt2(x)
    return one


def _evidence(b: Batch, lang: str, tested: bool = False) -> str:
    """What the numbers rest on. tested=True describes the farmer's last TEST, ignoring any drift since."""
    en = lang == "en"
    drifted = not tested and abs(b.moisture - b.test_value) >= 0.05
    if b.source in MEASURED:
        if drifted:
            return f"estimate {_pct(b.moisture)}%" if en else f"makadirio {_pct(b.moisture)}%"
        word = {"meter": ("meter", "mita"), "hygro": ("hygrometer", "haigromita")}[b.source]
        return f"{word[0 if en else 1]} {_pct(b.test_value)}%"
    if drifted:
        return "estimate from salt test" if en else "makadirio ya kipimo cha chumvi"
    if b.source == "salt_flows":
        return "salt test: below about 15%" if en else "kipimo cha chumvi: chini ya 15% hivi"
    return "salt test: above 15%" if en else "kipimo cha chumvi: zaidi ya 15%"


def _measured(b: Batch, lang: str) -> str:
    """'meter 13.1% on 12/10': what was measured and when."""
    ev = _evidence(b, lang, tested=True)
    if b.last_test is None:
        return ev
    return f"{ev} {'on' if lang == 'en' else 'tarehe'} {b.last_test.strftime('%d/%m')}"


def _risk(left: Optional[int], lang: str, tracks_air: bool = True) -> str:
    """The estimated storage time left, always labelled an estimate. Never the word 'safe'.
    tracks_air=False (S3-01: sealed bag) or a countdown at the horizon cap never says 'falling fast in damp
    weather': hermetic storage does not follow the air, and a capped result is not a prediction."""
    en = lang == "en"
    if left is None:
        return "not available today" if en else "haipatikani leo"
    if left <= 0:
        return "used up (estimate)" if en else "umeisha (makadirio)"
    if left >= 90:
        if not tracks_air or left >= HORIZON_DAYS:
            return "3 months or more" if en else "miezi 3 au zaidi"
        return ("3 months or more, falling fast in damp weather" if en
                else "miezi 3 au zaidi, hupungua haraka kukiwa na unyevu")
    return f"about {left} day{'s' if left > 1 else ''} (estimate)" if en else f"siku {left} hivi (makadirio)"


def _rain(mm: Optional[float], prob: Optional[float], lang: str) -> str:
    if prob is not None and prob >= RAIN_PROB_ALERT:
        return f"{fmt0(prob)}% chance" if lang == "en" else f"uwezekano {fmt0(prob)}%"
    return f"{fmt0(mm or 0)} mm expected" if lang == "en" else f"mm {fmt0(mm or 0)} zinatarajiwa"


def render(code: str, b: Batch, level: str, left: Optional[int], today: date,
           places: Optional[dict] = None, rain: tuple = (None, None), rain_window: bool = True,
           meta: Optional[WeatherMeta] = None) -> Alert:
    out = []
    wdate = (meta.fetched_on if meta and meta.fetched_on else today)
    credit = meta.credit if meta else CREDIT_OPEN_METEO
    nth = b.count_sent("HIGH_ALERT", b.last_test or date.min) + 1
    for lang in ("en", "sw"):
        en = lang == "en"
        # a directory entry can set the three place fields only, never a template field such as {date}
        p = dict(DEFAULT_PLACES[lang],
                 **{k: _place(v) for k, v in (places or {}).items() if k in PLACE_KEYS and v and _place(v)})
        fill = dict(
            p, date=wdate.strftime("%d/%m"), credit=credit, rain=_rain(rain[0], rain[1], lang),
            rain_when=("in the next 24 hours" if en else "ndani ya saa 24") if rain_window
            else ("tomorrow" if en else "kesho"),
            risk=_risk(left, lang, b.storage not in HERMETIC),
            weeks=min((today - b.stored_since).days // 7, WEEKS_CAP),
            closing=(("Our last reminder. Retest: reply e.g. METER 14.2 (your own reading) or SALT YES/NO to restart." if en
                      else "Ukumbusho wa mwisho. Pima tena: mf. MITA 14.2 au CHUMVI NDIYO/HAPANA kuziwasha.")
                     if nth >= HIGH_ALERT_MAX else
                     ("Reminders are weekly, at most 4." if en else "Ukumbusho: kila wiki, hadi mara 4.")),
            reply_drying="" if b.storage in DRYING else (" and reply DRYING" if en else " na ujibu ANIKA"))
        if b.moisture is not None:
            fill["evidence"] = _evidence(b, lang)
            fill["measured"] = _measured(b, lang)
            dried = b.verdict() == "WET"
            fill["why"] = (("Your stored maize may have dried out" if dried else
                            "Damp air has probably re-wetted your stored maize") if en else
                           ("Huenda mahindi yako ghalani yamekauka" if dried else
                            "Hewa yenye unyevu huenda imeongeza unyevu wa mahindi yako ghalani"))
        out.append(TEMPLATES[code][0 if en else 1].format(**fill))
    mine, other = (out[0], out[1]) if b.lang == "en" else (out[1], out[0])
    return Alert(code, level, mine, other)


# ======================================================================================
# 8. When to send: the evening job's decision
# ======================================================================================
NEEDS_DRYING = frozenset({"TEST_FIRST", "DRY_NOW", "NEARLY_DRY", "OPEN_AND_DRY"})
# Pushed when the recommendation changes. NEARLY_DRY / READY_TO_STORE are answers to a test and go
# out only as replies, so an estimate hovering around 13.5 % never causes flip-flop messages.
PUSHED_ON_CHANGE = frozenset({"DRY_NOW", "RETEST", "SORT_AND_SELL", "OPEN_AND_DRY", "CONFIRM_DRY"})
ADVICE_CODES = PUSHED_ON_CHANGE | {"TEST_FIRST", "NEARLY_DRY", "READY_TO_STORE", "STATUS"}


def _quiet_for(b: Batch, code: str, today: date, gap: int) -> bool:
    """True if `code` was not sent in the last `gap` days."""
    return b.count_sent(code, today - timedelta(days=gap - 1)) == 0


def _repeat_ok(b: Batch, code: str, today: date, gap: int) -> bool:
    """Repeats of a warning: spaced by `gap` days, at most REPEAT_MAX after the first, per test result."""
    return _quiet_for(b, code, today, gap) and b.count_sent(code, b.last_test or date.min) <= REPEAT_MAX


def _diag(b: Batch, left, level, adv, tomorrow: WeatherDay) -> dict:
    flags = []
    if b.moisture is not None:
        flags = sorted(set(ast_days(tomorrow.temp_c, b.moisture)[1] + emc(tomorrow.temp_c, tomorrow.rh)[1]))
    return {"moisture": None if b.moisture is None else rnd1(b.moisture), "source": b.source,
            "verdict": b.verdict(), "life_used_pct": rnd1(100 * b.life_used), "days_left": left,
            # days_left of HORIZON_DAYS means "that many or more": the tool stops looking, it is not a prediction
            "days_left_capped": left is not None and left >= HORIZON_DAYS,
            "level": level, "advice": adv, "emc_tomorrow": rnd1(emc(tomorrow.temp_c, tomorrow.rh)[0]),
            "moisture_raw": b.moisture, "life_used_raw": b.life_used,
            "weather_stale": False, "flags": flags}


HIGH_ALERT_ADVICE = frozenset({"RETEST", "DRY_NOW", "SORT_AND_SELL", "OPEN_AND_DRY", "CONFIRM_DRY"})


def evaluate(b: Batch, today: date, forecast: list, places: Optional[dict] = None,
             rain24: Optional[tuple] = None, meta: Optional[WeatherMeta] = None, send: bool = True) -> tuple:
    """Evening decision. Returns (Alert or None, diagnostics). forecast[0] MUST be tomorrow.
    rain24 = (mm, max probability %) for the 24 h after the run; if None or (None, None), tomorrow's
    values are used and the message says 'tomorrow'. meta describes the weather's age and credit; stale
    weather (older than WEATHER_STALE_HOURS) is flagged and never triggers a rain alert.
    send=False returns the diagnostics only."""
    if not forecast:
        raise ValueError("forecast is empty")
    if forecast[0].day != today + timedelta(days=1):
        raise ValueError("forecast[0] must be tomorrow")
    tomorrow = forecast[0]
    use24 = rain24 is not None and tuple(rain24) != (None, None)
    mm, prob = rain24 if use24 else (tomorrow.rain_mm, tomorrow.rain_prob)
    stale = meta is not None and meta.stale
    left = days_left(b, forecast)
    level = risk_level(b.life_used, left)
    adv = advice(b)
    diag = _diag(b, left, level, adv, tomorrow)
    if mm is None and prob is None:
        diag["flags"].append("rain data missing")                  # shown on the dashboard
    if stale:
        diag["flags"].append("weather stale")
        diag["weather_stale"] = True
    if not send or b.status != "active" or b.last_alert == today:
        return None, diag

    escalated = LEVEL_ORDER[level] > LEVEL_ORDER[b.told_level] and LEVEL_ORDER[level] >= 1
    if (left is not None and b.told_left is not None and left <= WORSE_WITHIN
            and left <= b.told_left * WORSE_FACTOR):
        escalated = True                                            # countdown at least halved
    rain = ((prob is not None and prob >= RAIN_PROB_ALERT) or (mm is not None and mm >= RAIN_MM_ALERT)) and not stale
    retest_ok = adv != "RETEST" or b.count_sent("RETEST", today - timedelta(days=29)) < RETEST_PER_30_DAYS

    code = None
    if rain and b.storage in DRYING and adv in NEEDS_DRYING and b.rain_unacked < RAIN_UNACKED_MAX:
        code = "RAIN_COVER"
    elif adv == "TEST_FIRST":
        if _quiet_for(b, adv, today, REMIND_GAP_DAYS) and b.count_sent(adv) < TEST_REMINDERS_MAX:
            code = adv
    elif not retest_ok:
        pass
    elif adv in PUSHED_ON_CHANGE and adv != b.last_advice:
        code = adv                                                  # the recommendation changed
    elif adv in ("DRY_NOW", "RETEST", "OPEN_AND_DRY") and escalated and _quiet_for(b, adv, today, REMIND_GAP_DAYS):
        code = adv                                                  # same advice, countdown worse
    elif adv in ("DRY_NOW", "RETEST") and level == "HIGH" and _repeat_ok(b, adv, today, REMIND_GAP_DAYS):
        code = adv                                                  # unanswered HIGH warning
    elif adv in ("OPEN_AND_DRY", "CONFIRM_DRY") and _repeat_ok(b, adv, today, SEALED_GAP_DAYS):
        code = adv                                                  # unanswered sealed-bag warning
    elif (b.storage in PERMEABLE and b.verdict() == "DRY" and b.moisture < HERMETIC_MAX_MC
          and b.life_used < MEDIUM_LIFE and (today - b.stored_since).days >= INSECT_REMINDER_DAYS
          and not b.count_sent("INSECT_REMINDER")):
        code = "INSECT_REMINDER"

    if (code is None and level == "HIGH" and adv in HIGH_ALERT_ADVICE
            and (b.last_alert is None or (today - b.last_alert).days >= HIGH_ALERT_GAP_DAYS)
            and b.count_sent("HIGH_ALERT", b.last_test or date.min) < HIGH_ALERT_MAX):
        code = "HIGH_ALERT"        # a HIGH batch is silent only after the capped last-chance message (C-12, see below)
    elif (code is None and level == "HIGH" and adv in HIGH_ALERT_ADVICE
            and b.count_sent("HIGH_ALERT", b.last_test or date.min) >= HIGH_ALERT_MAX):
        # C-12: the capped last-chance message has been sent. The engine now stays silent ON PURPOSE until the
        # farmer sends a new test result (which starts a new count) and says so in the diagnostics.
        diag["flags"].append("high alerts used up")

    if code is None:
        return None, diag
    snap = b.snapshot()
    alert = render(code, b, level, left, today, places, (mm, prob), use24, meta)
    alert.undo = snap
    b.last_alert = today
    b.sent.append((today, code))
    if code == "RAIN_COVER":
        b.rain_unacked += 1
    elif code in ADVICE_CODES:
        b.last_advice, b.told_level, b.told_left = code, level, left
    return alert, diag


def welcome(b: Batch, today: date, meta: Optional[WeatherMeta] = None) -> Alert:
    """The first message after registration: what this is, the weather credit, how to stop."""
    return render("WELCOME", b, "UNKNOWN", None, today, None, (None, None), True, meta)


# ======================================================================================
# 9. Farmer replies (English or Kiswahili keywords; case, spacing and punctuation tolerant)
# ======================================================================================
_NUM = r"([0-9]+(?:[.,][0-9]+)?)"
_RE_METER_CMD = r"(?:METER|METRE|MITA)(?![A-Z])"
_RE_HYGRO_CMD = r"HYGRO(?![A-Z])"
_RE_NEG = r"-\s?[0-9]|(?:^|[^0-9])[.,][0-9]"  # N6-01: a minus/dash, or a leading '.5' / ',5' (no digit before the point), in the raw text


def _raw_minus(text) -> str:
    """The raw message (cut like normalise, upper-cased) with the unicode minus and dashes as '-', so a negative
    reading can be told from a range after normalise() has turned every '-' into a space."""
    t = "" if text is None else text if isinstance(text, str) else str(text)
    return t[:MAX_TEXT_CHARS].upper().replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
_STORAGE_WORDS = {"DRYING": "drying", "ANIKA": "drying", "SACKS": "sack", "SACK": "sack",
                  "MAGUNIA": "sack", "SEALED": "hermetic", "NIMEFUNGA": "hermetic"}
_ACK_WORDS = {"1", "OK", "OKAY", "SAWA", "ASANTE", "THANKS", "DONE"}
# unicode spaces become a plain space explicitly (Oracle's [[:space:]] would not match them)
_SPACE_MAP = {ord(c): " " for c in "      ​ 　"}


def normalise(text) -> str:
    """Upper-case, punctuation and spacing tolerant. Cuts the input to MAX_TEXT_CHARS first; never raises."""
    if text is None:
        text = ""
    elif not isinstance(text, str):
        text = str(text)
    t = text[:MAX_TEXT_CHARS].upper().replace("°", " ").translate(_SPACE_MAP)
    t = re.sub(r"[!?;:'\"()\-_/*#]", " ", t)
    t = re.sub(r"(?<![0-9])[.,]|[.,](?![0-9])", " ", t)      # keep decimal points/commas inside numbers
    t = re.sub(r"[ \t\r\n\f\v]+", " ", t).strip(" ")
    return re.sub(r" +%", "%", t)


def is_optout(norm: str) -> bool:
    """R1-04: a short message (at most OPTOUT_MAX_TOKENS words) that contains an opt-out word anywhere, or a
    phrase such as NO MORE, is an opt-out: 'STOP', 'PLEASE STOP', 'I WANT TO STOP', 'NO MORE', 'STOPP'.
    A false positive only stops messages, which the farmer undoes with START; a missed STOP is the worse error.
    Long messages (more than OPTOUT_MAX_TOKENS words) are not read as opt-outs. `norm` is a normalised text."""
    tokens = norm.split(" ") if norm else []
    if not tokens or len(tokens) > OPTOUT_MAX_TOKENS:
        return False
    if any(t in OPTOUT_WORDS for t in tokens):
        return True
    return any(tokens[i] + " " + tokens[i + 1] in OPTOUT_PHRASES for i in range(len(tokens) - 1))


def apply_reply(b: Batch, text: str, today: date, temp_hint: Optional[float] = None) -> str:
    """Update the batch from a reply. Never raises on farmer input. Returns one of:
    SALT_YES, SALT_NO, SALT_NO_IGNORED, METER, HYGRO, STORAGE, CLOSED, ACK, STOP, START,
    INVALID (recognised command, unusable value) or UNKNOWN."""
    t = normalise(text)
    first = t.split(" ")[0] if t else ""
    num = lambda s: float(s.replace(",", "."))
    if re.match(r"(SALT|CHUMVI) ?(YES|NDIYO|NDIO)\b", t, re.ASCII):
        b.record_salt(today, sticky=True)
        return "SALT_YES"
    if re.match(r"(SALT|CHUMVI) ?(NO|HAPANA)\b", t, re.ASCII):
        return "SALT_NO" if b.record_salt(today, sticky=False) else "SALT_NO_IGNORED"
    # E5-01: strict readings. METER/HYGRO followed by anything but exactly the expected numbers is INVALID
    # (ask again), never a first-number guess: 'METER 13-15', 'meter 13 / 15' and 'METER -13' must not clear grain.
    neg = re.search(_RE_NEG, _raw_minus(text)) is not None
    if re.match(_RE_METER_CMD, t, re.ASCII):
        m = re.fullmatch(rf"(?:METER|METRE|MITA) ?{_NUM}%?", t, re.ASCII)
        if neg or not m:
            return "INVALID"
        try:
            b.record_meter(today, num(m.group(1)))
        except ValueError:
            return "INVALID"
        return "METER"
    if re.match(_RE_HYGRO_CMD, t, re.ASCII):
        m = re.fullmatch(rf"HYGRO ?{_NUM}%?(?: {_NUM} ?C?)?", t, re.ASCII)
        if neg or not m:
            return "INVALID"
        temp = num(m.group(2)) if m.group(2) else temp_hint
        try:
            if temp is None:
                raise ValueError("no temperature")
            b.record_hygro(today, num(m.group(1)), temp)
        except ValueError:
            return "INVALID"
        return "HYGRO"
    if is_optout(t):
        b.status = "stopped"
        return "STOP"
    if first in _STORAGE_WORDS:
        b.set_storage(today, _STORAGE_WORDS[first])
        return "STORAGE"
    if first in {"SOLD", "NIMEUZA", "DEPOSITED", "GHALANI"}:
        b.status = "closed"
        return "CLOSED"
    if first in {"START", "ANZA"}:
        if b.status != "active":
            was = b.status
            b.status = "active"
            # A sold batch restarts from today. An opted-out pause is NOT free: the paused days are charged
            # (with the nearest known weather) by the next daily run, so a pause never resets the countdown.
            if was == "closed" and b.moisture is not None:
                b.last_advanced = today - timedelta(days=1)
        return "START"
    if t in _ACK_WORDS or t == "THANK YOU":
        b.acks.append(today)
        return "ACK"
    return "UNKNOWN"


# ---- the phone number is the unit of consent ---------------------------------------------
def stop_phone(batches: list, queue: Optional[list] = None) -> int:
    """STOP applies to every batch of the phone number, and cancels what is still waiting to be sent.
    queue = list of message dicts with a 'status' key. Returns the number of batches stopped."""
    n = 0
    for b in batches:
        if b.status == "active":
            b.status = "stopped"
            n += 1
    cancel_queued(queue or [])
    return n


def start_phone(batches: list) -> int:
    """START reactivates every batch that STOP stopped (sold batches stay closed)."""
    n = 0
    for b in batches:
        if b.status == "stopped":
            b.status = "active"
            n += 1
    return n


def cancel_queued(queue: list) -> int:
    """QUEUED messages of an opted-out phone become CANCELLED and are never sent."""
    n = 0
    for m in queue:
        if m.get("status") == "QUEUED":
            m["status"] = "CANCELLED"
            n += 1
    return n


def normalise_address(addr: str) -> str:
    """Phone numbers and chat ids in one canonical form, so +254712345678, 0712 345 678 and 254712345678
    are one person: lower-case, only digits, '+', letters and ':' kept; 00 -> +; 0xxxxxxxxx and 254xxxxxxxxx -> +254xxxxxxxxx."""
    a = re.sub(r"[^0-9a-z+:]", "", (addr or "").lower())
    if a.startswith("00"):
        a = "+" + a[2:]
    if re.fullmatch(r"0[0-9]{9}", a):
        a = "+254" + a[1:]
    elif re.fullmatch(r"254[0-9]{9}", a):
        a = "+" + a
    return a


def address_hash(addr: str, pepper: str) -> str:
    """HMAC-SHA256 (hex, lower case) of the canonical address with a secret pepper. Stored instead of the
    number wherever the number itself is not needed (opt-outs, inbound log)."""
    return hmac.new(pepper.encode(), normalise_address(addr).encode(), hashlib.sha256).hexdigest()


def may_send(addr: str, opted_out: set, pepper: str) -> bool:
    """False if this phone has opted out (opted_out = set of address hashes)."""
    return address_hash(addr, pepper) not in opted_out


def retention_cutoffs(today: date) -> dict:
    """The dates before which each kind of personal data is purged. See README 'Privacy'."""
    d = lambda n: today - timedelta(days=n)
    return {"inbound_text": d(RETAIN_INBOUND_TEXT_DAYS), "sent_address": d(RETAIN_SENT_ADDRESS_DAYS),
            "messages": d(RETAIN_MESSAGE_DAYS), "run_log": d(RETAIN_RUNLOG_DAYS),
            "ended_batch_phone": d(RETAIN_ENDED_BATCH_DAYS)}


def respond(b: Batch, text: str, today: date, forecast: list, places: Optional[dict] = None,
            temp_hint: Optional[float] = None, meta: Optional[WeatherMeta] = None) -> tuple:
    """Answer a farmer's reply at once. Returns (command, Alert or None). Never uses the evening slot.
    forecast should start tomorrow; if it is missing, messages say the countdown is not available."""
    if temp_hint is None and forecast:
        temp_hint = forecast[0].temp_c
    norm = normalise(text)[:NORM_STORE_CHARS]
    duplicate = (today, norm) in b.replies
    was = b.status
    cmd = apply_reply(b, text, today, temp_hint)
    b.replies.append((today, norm))
    b.rain_unacked = 0
    if b.status == "stopped" and cmd != "STOP":
        return cmd, None                                  # opted out: stay silent
    left = days_left(b, forecast)
    level = risk_level(b.life_used, left)
    adv = advice(b)
    if was == "closed" and b.status == "closed" and cmd != "CLOSED":
        code = "CLOSED"                                    # reply START to reopen
    elif cmd in ("UNKNOWN", "INVALID"):
        code = "HELP"
    elif cmd in ("ACK", "SALT_NO_IGNORED") or duplicate:
        code = "THANKS" if cmd == "ACK" or duplicate else (adv or "STATUS")
    elif cmd in ("CLOSED", "STOP"):
        code = {"CLOSED": "CLOSED", "STOP": "STOPPED"}[cmd]
    elif cmd == "STORAGE" and b.storage in DRYING and adv in NEEDS_DRYING:
        code = "THANKS"                                    # started drying, as advised
    else:
        code = adv or "STATUS"
    snap = b.snapshot()
    if code in ADVICE_CODES:
        b.last_advice, b.told_level, b.told_left = code, level, left
    alert = render(code, b, level, left, today, places, meta=meta)
    alert.undo = snap
    b.sent.append((today, code))
    return cmd, alert


# ======================================================================================
# 10. Weather adapter (Open-Meteo; free tier is for non-commercial use, CC BY 4.0 attribution: see ATTRIBUTION)
# ======================================================================================
def open_meteo_url(lat: float, lon: float, past_days: int = 2, forecast_days: int = 8) -> str:
    """past_days lets the job catch up after a missed run; forecast_days=8 gives today + 7 days."""
    return (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,relative_humidity_2m,precipitation,precipitation_probability"
        f"&past_days={past_days}&forecast_days={forecast_days}&timezone=Africa%2FNairobi"
    )


def _col(h: dict, key: str) -> list:
    return h.get(key) or [None] * len(h["time"])


_PLAUSIBLE = {"t": (-60.0, 60.0), "rh": (0.0, 100.0), "p": (0.0, 1000.0), "pp": (0.0, 100.0)}


def _plausible(key: str, v) -> bool:
    """A weather value the model can use: a real number inside a physical range (None, NaN, inf, text and
    values like 1e9 are all rejected, so one bad hour can never crash the evening run)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    lo, hi = _PLAUSIBLE[key]
    return math.isfinite(v) and lo <= v <= hi


def daily_from_open_meteo(payload: dict) -> list:
    """Aggregate Open-Meteo hourly arrays (local time) into one WeatherDay per date.
    Days with fewer than 20 hourly temperature/humidity values are dropped (partial days)."""
    h = payload["hourly"]
    temps, rhs, rain, prob = (_col(h, k) for k in
                              ("temperature_2m", "relative_humidity_2m", "precipitation",
                               "precipitation_probability"))
    buckets: dict = {}
    for k, ts in enumerate(h["time"]):
        bk = buckets.setdefault(ts[:10], {"t": [], "rh": [], "p": [], "pp": []})
        for key, src in (("t", temps), ("rh", rhs), ("p", rain), ("pp", prob)):
            if _plausible(key, src[k]):                     # N5-08: NaN, infinity and absurd values are dropped
                bk[key].append(src[k])
    out = []
    for d, bk in sorted(buckets.items()):
        if len(bk["t"]) < 20 or len(bk["rh"]) < 20:
            continue
        out.append(WeatherDay(date.fromisoformat(d), sum(bk["t"]) / len(bk["t"]),
                              sum(bk["rh"]) / len(bk["rh"]),
                              sum(bk["p"]) if bk["p"] else None,
                              max(bk["pp"]) if bk["pp"] else None))
    return out


def rain_next_hours(payload: dict, start: str, hours: int = 24) -> tuple:
    """(total mm, max probability %) over `hours` hourly steps from local time `start`
    ('YYYY-MM-DDTHH:00'); None where the data is missing."""
    h = payload["hourly"]
    if start not in h["time"]:
        return None, None
    i = h["time"].index(start)
    mm = [v for v in _col(h, "precipitation")[i:i + hours] if v is not None]
    pp = [v for v in _col(h, "precipitation_probability")[i:i + hours] if v is not None]
    return (sum(mm) if mm else None), (max(pp) if pp else None)


def split_weather(days: list, today: date) -> tuple:
    """({date: WeatherDay} up to and including today, [forecast days after today])."""
    past = {d.day: d for d in days if d.day <= today}
    forecast = [d for d in sorted(days, key=lambda x: x.day) if d.day > today]
    return past, forecast


def daily_run(b: Batch, today: date, days: list, places: Optional[dict] = None,
              rain24: Optional[tuple] = None, meta: Optional[WeatherMeta] = None) -> tuple:
    """The evening job for one batch: catch up on un-simulated days, then evaluate.
    Returns (Alert or None, diagnostics); diagnostics['missing_days'] lists days with no weather.
    Idempotent per batch per day: a second call on the same day never sends again."""
    past, forecast = split_weather(days, today)
    if not forecast or forecast[0].day != today + timedelta(days=1):
        raise ValueError("weather must include tomorrow")
    if b.moisture is not None and b.last_advanced is None:      # e.g. a batch loaded from storage
        b.last_advanced = (b.last_test or today) - timedelta(days=1)
    missing = []
    again = b.last_run == today
    if b.moisture is not None and b.status == "active":
        d = b.last_advanced + timedelta(days=1)
        while d <= today:
            w = past.get(d)
            if w is None:   # gap in the data: reuse the nearest earlier day (or tomorrow) and report it
                missing.append(d)
                earlier = [x for x in past if x < d]
                src = past[max(earlier)] if earlier else forecast[0]
                w = WeatherDay(d, src.temp_c, src.rh)
            advance_day(b, w)
            d += timedelta(days=1)
    alert, diag = evaluate(b, today, forecast, places, rain24, meta, send=not again)
    if again:
        diag["flags"].append("already run today")
    else:
        b.last_run = today
    diag["missing_days"] = missing
    return alert, diag


def fetch_payload(lat: float, lon: float) -> dict:  # pragma: no cover - network
    import json
    import urllib.request
    with urllib.request.urlopen(open_meteo_url(lat, lon), timeout=20) as r:
        return json.load(r)
