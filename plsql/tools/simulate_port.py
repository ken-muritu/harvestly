#!/usr/bin/env python3
"""Offline proof harness for the PL/SQL port (no Oracle database was available).

This file is a line-by-line Python mirror of the control flow in ../harvestly_engine.pkb:
  * same procedure / function split and the same order of rules and early RETURNs;
  * numbers are decimal.Decimal at 38 digits (Oracle NUMBER), ln/exp via Decimal, ROUND half away
    from zero (Oracle ROUND), TO_CHAR 'FM9999990.0' formatting;
  * NULL is None. Python raises TypeError when None is compared, so an unguarded NULL in the mirror
    shows up as a crash instead of Oracle's silent NULL-is-false;
  * strings are handled with the same character-by-character loops, TRANSLATE / TRIM / RTRIM
    semantics and the very same regular-expression strings (read out of the .pkb), with
    [[:space:]] mapped to \\s for Python;
  * the EMC / AST tables and the message templates are parsed back out of ../schema.sql, so the
    seed that Oracle will load is what is tested.

Checks (all must pass; exit status 1 otherwise):
  1. vectors.json: 49 EMC, 60 AST (1e-6), and every step of the 3 scenarios (replies first, then the
     evening run): code, level, days left (exact), the EXACT message text, the exact display strings
     (moisture_s, life_used_pct_s) and the exact values; plus the rounding, evidence, opt-out, normalise,
     address-hash and days_left sections.
  1b. Rounding fuzz: every x = 5.00 .. 40.00 step 0.01 through fmt0/1/2 in Python, this mirror and the
     JS port (node): all three must equal exact half-up integer arithmetic (0 divergences).
  2. render(): every template, both languages, equals the Python reference text for random
     states, places, rain values; plus the GSM-7 / 2-segment rule on the mirror's output.
  3. normalise / apply_reply: same command and same resulting state as the reference for a fixed
     corpus and for random farmer strings.
  4. Differential fuzz: random batches, weather and reply sequences run through mirror and
     reference side by side; every message code, level, days left must agree.

Usage:  python3 simulate_port.py [--fuzz N] [--seed S]
"""
import argparse
import json
import math
import os
import random
import re
import sys
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, getcontext

getcontext().prec = 38                      # Oracle NUMBER carries 38 significant digits

HERE = os.path.dirname(os.path.abspath(__file__))
PLSQL = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(PLSQL, "..", "engine"))
import harvestly_engine as H                # noqa: E402  (the Python reference)

D = Decimal


# ======================================================================================
# Oracle-ish primitives
# ======================================================================================
def d(x):
    """A literal as Oracle would read it: exact decimal, never a binary float."""
    if x is None or isinstance(x, Decimal):
        return x
    if isinstance(x, float):
        return Decimal(repr(x))
    return Decimal(x)


def ora_round(x, n=0):
    return x.quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP)      # half away from zero


def fmt0(x):                                 # TO_CHAR(ROUND(ROUND(x,10),0),'FM9999990')
    return format(ora_round(ora_round(x, 10), 0), "f")


def fmt1(x):                                 # TO_CHAR(ROUND(ROUND(x,10),1),'FM9999990.0')
    return format(ora_round(ora_round(x, 10), 1), "f")


def fmt2(x):                                 # TO_CHAR(ROUND(ROUND(x,10),2),'FM9999990.00')
    return format(ora_round(ora_round(x, 10), 2), "f")


def ln(x):
    return x.ln()


def exp(x):
    return x.exp()


# ======================================================================================
# parameters (mirror of the package spec constants; the labels live in the .pks)
# ======================================================================================
def read_constants():
    """Read the NUMBER constants from the .pks so spec and mirror cannot drift apart."""
    src = open(os.path.join(PLSQL, "harvestly_engine.pks")).read()
    out = {}
    for m in re.finditer(r"^\s*(c_\w+)\s+CONSTANT\s+(?:NUMBER|PLS_INTEGER)\s*:=\s*([0-9.]+);", src, re.M):
        out[m.group(1)] = D(m.group(2))
    for m in re.finditer(r"^\s*(c_place_\w+)\s+CONSTANT\s+VARCHAR2\(\d+\)\s*:=\s*'([^']*)';", src, re.M):
        out[m.group(1)] = m.group(2)
    return out


C = read_constants()
c_eas_max_mc, c_hermetic_max_mc, c_salt_line_mc = C["c_eas_max_mc"], C["c_hermetic_max_mc"], C["c_salt_line_mc"]
c_salt_sticky_mc, c_salt_flows_mc = C["c_salt_sticky_mc"], C["c_salt_flows_mc"]
c_sack_exchange_rate, c_max_ast_days = C["c_sack_exchange_rate"], C["c_max_ast_days"]
c_rain_prob_alert, c_rain_mm_alert = C["c_rain_prob_alert"], C["c_rain_mm_alert"]
c_high_life, c_high_days, c_medium_life, c_medium_days = (
    C["c_high_life"], C["c_high_days"], C["c_medium_life"], C["c_medium_days"])
c_remind_gap_days, c_sealed_gap_days, c_repeat_max = (
    C["c_remind_gap_days"], C["c_sealed_gap_days"], C["c_repeat_max"])
c_worse_factor, c_worse_within, c_retest_margin = C["c_worse_factor"], C["c_worse_within"], C["c_retest_margin"]
c_retest_per_30_days, c_test_reminders_max = C["c_retest_per_30_days"], C["c_test_reminders_max"]
c_rain_unacked_max, c_place_max_chars = C["c_rain_unacked_max"], int(C["c_place_max_chars"])
c_insect_reminder_days, c_horizon_days = C["c_insect_reminder_days"], int(C["c_horizon_days"])
c_sms_gsm7_single, c_sms_max_segments = int(C["c_sms_gsm7_single"]), int(C["c_sms_max_segments"])
c_high_alert_gap_days, c_high_alert_max = int(C["c_high_alert_gap_days"]), int(C["c_high_alert_max"])
c_weather_stale_hours, c_weeks_cap = C["c_weather_stale_hours"], int(C["c_weeks_cap"])
c_norm_store_chars, c_max_text_chars = int(C["c_norm_store_chars"]), int(C["c_max_text_chars"])
c_credit_open_meteo = re.search(r"c_credit_open_meteo\s+CONSTANT\s+VARCHAR2\(\d+\)\s*:=\s*'([^']*)';",
                                open(os.path.join(PLSQL, "harvestly_engine.pks")).read()).group(1)

# the regular expressions, straight from the package body
_pkb = open(os.path.join(PLSQL, "harvestly_engine.pkb")).read()


def _re(name):
    m = re.search(rf"{name}\s+CONSTANT VARCHAR2\(\d+\) := '(.*?)';\n", _pkb)
    return m.group(1).replace("''", "'").replace("[[:space:]]", r"\s")


RE_SALT_YES, RE_SALT_NO = _re("c_re_salt_yes"), _re("c_re_salt_no")
RE_METER, RE_HYGRO = _re("c_re_meter"), _re("c_re_hygro")
RE_METER_CMD, RE_HYGRO_CMD, RE_NEG = _re("c_re_meter_cmd"), _re("c_re_hygro_cmd"), _re("c_re_neg")


# ======================================================================================
# tables and templates, parsed back out of schema.sql (what Oracle will actually hold)
# ======================================================================================
_schema = open(os.path.join(PLSQL, "schema.sql")).read()
EMC_ROWS = [(D(a), D(b), D(c)) for a, b, c in
            re.findall(r"SELECT ([\d.]+) temp_f, ([\d.]+) rh, ([\d.]+) emc_pct FROM dual", _schema)]
AST_ROWS = [(D(a), D(b), D(c)) for a, b, c in
            re.findall(r"SELECT ([\d.]+) temp_f, ([\d.]+) mc, ([\d.]+) days FROM dual", _schema)]
TEMPLATES = {(c, l): b for c, l, b in
             re.findall(r"SELECT '(\w+)' c, '(en|sw)' l, q'~(.*?)~' b FROM dual", _schema)}

g_emc_t, g_emc_rh, g_emc_v = [], [], {}
g_ast_t, g_ast_mc, g_ast_ln = [], [], {}


def init_tables():                           # same one-pass loop as the PL/SQL init_tables
    i = j = 0
    v_last = None
    for tf, rh, v in sorted(EMC_ROWS):
        if v_last is None or tf != v_last:
            i += 1
            j = 0
            g_emc_t.append(tf)
            v_last = tf
        j += 1
        if i == 1:
            g_emc_rh.append(rh)
        g_emc_v[i * 100 + j] = v
    assert len(EMC_ROWS) == len(g_emc_t) * len(g_emc_rh)
    i = j = 0
    v_last = None
    for tf, mc, days in sorted(AST_ROWS):
        if v_last is None or tf != v_last:
            i += 1
            j = 0
            g_ast_t.append(tf)
            v_last = tf
        j += 1
        if i == 1:
            g_ast_mc.append(mc)
        g_ast_ln[i * 100 + j] = ln(days)
    assert len(AST_ROWS) == len(g_ast_t) * len(g_ast_mc)


init_tables()
g_ln_max = ln(c_max_ast_days)


# ======================================================================================
# records
# ======================================================================================
class Rec:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def W(wx_date, temp_c, rh, rain_mm=None, rain_prob=None):
    return Rec(wx_date=wx_date, temp_c=d(temp_c), rh=d(rh), rain_mm=d(rain_mm), rain_prob=d(rain_prob))


def new_batch_rec(batch_id, ward_id, storage, stored_since, lang="en"):
    if storage is None or storage not in ("drying", "sack", "crib", "floor", "hermetic"):
        raise ValueError("unknown storage type")
    if lang is None or lang not in ("en", "sw"):
        raise ValueError("lang")
    return Rec(batch_id=batch_id, ward_id=ward_id, storage=storage, stored_since=stored_since, lang=lang,
               bags=1, moisture=None, source="none", last_test=None, test_value=None,
               peak_since_test=None, life_used=D(0), last_advanced=None, last_alert=None,
               last_advice=None, told_level="UNKNOWN", told_left=None, rain_unacked=0,
               status="active", last_run=None, sent=[], replies=[])


def new_places(stockist=None, warehouse=None, checkpoint=None):
    return Rec(stockist=stockist, warehouse=warehouse, checkpoint=checkpoint)


def new_rain24(given=False, mm=None, prob=None):
    return Rec(given=given, mm=d(mm), prob=d(prob))


def new_meta(given=False, fetched_on=None, age_hours=0, credit=None):      # no_meta / t_weather_meta
    return Rec(given=given, fetched_on=fetched_on, age_hours=d(age_hours),
               credit=credit if credit is not None else c_credit_open_meteo)


NO_META = new_meta()


# ======================================================================================
# helpers
# ======================================================================================
def is_permeable(s):
    return s in ("sack", "crib", "floor")


def is_measured(s):
    return s in ("meter", "hygro")


def level_ord(lv):
    return {"LOW": 0, "MEDIUM": 1, "HIGH": 2}.get(lv, -1)


def needs_drying(adv):
    return adv is not None and adv in ("TEST_FIRST", "DRY_NOW", "NEARLY_DRY", "OPEN_AND_DRY")


def pushed_on_change(adv):
    return adv is not None and adv in ("DRY_NOW", "RETEST", "SORT_AND_SELL", "OPEN_AND_DRY", "CONFIRM_DRY")


def is_advice_code(code):
    return pushed_on_change(code) or code in ("TEST_FIRST", "NEARLY_DRY", "READY_TO_STORE", "STATUS")


def c_to_f(c):
    return c * 9 / 5 + 32


def add_sent(b, on, code):
    b.sent.append((on, code))


def make_undo(b):
    return Rec(present=True, sent_len=len(b.sent), last_alert=b.last_alert, last_advice=b.last_advice,
               told_level=b.told_level, told_left=b.told_left, rain_unacked=b.rain_unacked)


def revert_undelivered(b, u):
    if u is None or not u.present:
        return
    if u.sent_len < len(b.sent):
        del b.sent[u.sent_len]
    b.last_alert, b.last_advice = u.last_alert, u.last_advice
    b.told_level, b.told_left, b.rain_unacked = u.told_level, u.told_left, u.rain_unacked


# ======================================================================================
# 3. physics
# ======================================================================================
def bracket(axis, n, x):                     # axis is 0-based here; n = COUNT; returns 1-based i like the .pkb
    if x <= axis[0]:
        i = 1
    elif x >= axis[n - 1]:
        i = n - 1
    else:
        i = 1
        for k in range(1, n):
            if axis[k - 1] <= x:
                i = k
    t = (x - axis[i - 1]) / (axis[i] - axis[i - 1])
    return i, t


def emc_w(temp_c, rh):
    warn = ""
    tf = c_to_f(temp_c)
    nt, nrh = len(g_emc_t), len(g_emc_rh)
    if not (g_emc_t[0] <= tf and tf <= g_emc_t[nt - 1]):
        warn += "EMC temperature clamped;"
        tf = min(max(tf, g_emc_t[0]), g_emc_t[nt - 1])
    if not (g_emc_rh[0] <= rh and rh <= g_emc_rh[nrh - 1]):
        warn += "EMC humidity clamped;"
        rh = min(max(rh, g_emc_rh[0]), g_emc_rh[nrh - 1])
    i, ti = bracket(g_emc_t, nt, tf)
    j, tj = bracket(g_emc_rh, nrh, rh)
    top = g_emc_v[i * 100 + j] + tj * (g_emc_v[i * 100 + j + 1] - g_emc_v[i * 100 + j])
    bot = g_emc_v[(i + 1) * 100 + j] + tj * (g_emc_v[(i + 1) * 100 + j + 1] - g_emc_v[(i + 1) * 100 + j])
    return top + ti * (bot - top), warn


def emc(temp_c, rh):
    return emc_w(temp_c, rh)[0]


def ast_w(temp_c, mc):
    warn = ""
    tf = c_to_f(temp_c)
    nt, nmc = len(g_ast_t), len(g_ast_mc)
    if tf > g_ast_t[nt - 1]:
        warn += "AST temperature extrapolated;"
    if tf < g_ast_t[0]:
        tf = g_ast_t[0]
        warn += "AST temperature clamped;"
    m = mc
    if m > g_ast_mc[nmc - 1]:
        m = g_ast_mc[nmc - 1]
        warn += "AST moisture clamped;"
    if m < g_ast_mc[0]:
        warn += "AST moisture extrapolated;"
    i, ti = bracket(g_ast_t, nt, tf)
    j, tj = bracket(g_ast_mc, nmc, m)
    top = g_ast_ln[i * 100 + j] + tj * (g_ast_ln[i * 100 + j + 1] - g_ast_ln[i * 100 + j])
    bot = g_ast_ln[(i + 1) * 100 + j] + tj * (g_ast_ln[(i + 1) * 100 + j + 1] - g_ast_ln[(i + 1) * 100 + j])
    x = top + ti * (bot - top)
    if x >= g_ln_max:
        return c_max_ast_days, warn
    return exp(x), warn


def ast_days(temp_c, mc):
    return ast_w(temp_c, mc)[0]


# ======================================================================================
# 4. state
# ======================================================================================
def stale(b):
    return b.peak_since_test is not None and b.peak_since_test > c_salt_line_mc + c_retest_margin


def verdict(b):
    if b.moisture is None:
        return "UNTESTED"
    if b.source == "salt_sticky" or b.test_value > c_salt_line_mc:
        return "WET"
    if is_measured(b.source) and b.test_value <= c_eas_max_mc and not stale(b):
        return "DRY"
    return "NOT_PROVEN"


def count_sent(b, code, since=None):
    n = 0
    for (sd, sc) in b.sent:
        if sc == code and (since is None or sd >= since):
            n += 1
    return n


def set_moisture(b, on, mc, source):
    if b.last_advanced is None:
        b.last_advanced = on - timedelta(days=1)
    b.moisture = mc
    b.source = source
    b.last_test = on
    b.test_value = mc
    b.peak_since_test = mc


def record_salt(b, on, sticky):
    if (not sticky and is_measured(b.source) and b.test_value <= c_salt_line_mc
            and b.moisture <= c_salt_line_mc and (on - b.last_test).days <= 7):
        return False
    if sticky:
        set_moisture(b, on, c_salt_sticky_mc, "salt_sticky")
    else:
        set_moisture(b, on, c_salt_flows_mc, "salt_flows")
    return True


class OraError(Exception):
    pass


def record_meter(b, on, reading):
    if not (D("5.0") <= reading and reading <= D("40.0")):
        raise OraError("moisture meter reading must be between 5 and 40 %")
    set_moisture(b, on, reading, "meter")


def record_hygro(b, on, rh, temp_c):
    rh_c = rh + D("0.0")
    if not (D("0.0") < rh_c and rh_c < D("100.0")) or not (D("-5.0") <= temp_c and temp_c <= D("45.0")):
        raise OraError("hygrometer reading out of range")
    set_moisture(b, on, emc(temp_c, rh_c), "hygro")


def set_storage(b, on, storage):
    if storage not in ("drying", "sack", "crib", "floor", "hermetic"):
        raise OraError("unknown storage type")
    if storage != b.storage:
        b.storage = storage
        b.stored_since = on


# ======================================================================================
# 5. daily simulation
# ======================================================================================
def advance_day(b, w):
    if b.moisture is None or b.status != "active":
        return
    if b.last_advanced is not None and w.wx_date <= b.last_advanced:
        return
    if is_permeable(b.storage):
        b.moisture = b.moisture + c_sack_exchange_rate * (emc(w.temp_c, w.rh) - b.moisture)
        b.peak_since_test = max(b.peak_since_test, b.moisture)
    b.life_used = b.life_used + 1 / ast_days(w.temp_c, b.moisture)
    b.last_advanced = w.wx_date


def days_left(b, forecast):
    n_fc = len(forecast)
    if b.moisture is None or n_fc == 0:
        return None
    if b.life_used >= 1:
        return 0
    sum_t = D(0)
    sum_rh = D(0)
    for k in range(n_fc):
        sum_t = sum_t + forecast[k].temp_c
        sum_rh = sum_rh + forecast[k].rh
    mean_t = sum_t / n_fc
    mean_rh = sum_rh / n_fc
    used = b.life_used
    m = b.moisture
    for n in range(0, c_horizon_days):
        if n < n_fc:
            t = forecast[n].temp_c
            rh = forecast[n].rh
        else:
            t = mean_t
            rh = mean_rh
        if is_permeable(b.storage):
            m = m + c_sack_exchange_rate * (emc(t, rh) - m)
        used = used + 1 / ast_days(t, m)
        if used >= 1:
            return n + 1
    return c_horizon_days


def risk_level(life_used, left):
    if left is None:
        return "UNKNOWN"
    if life_used >= c_high_life or left <= c_high_days:
        return "HIGH"
    if life_used >= c_medium_life or left <= c_medium_days:
        return "MEDIUM"
    return "LOW"


# ======================================================================================
# 6. advice
# ======================================================================================
def advice(b):
    v = verdict(b)
    if v == "UNTESTED":
        return "TEST_FIRST"
    if b.life_used >= c_high_life:
        return "SORT_AND_SELL"
    if b.storage == "hermetic":
        fresh = is_measured(b.source) and not stale(b)
        if v == "WET" or (fresh and b.test_value >= c_hermetic_max_mc):
            return "OPEN_AND_DRY"
        if fresh and b.moisture < c_hermetic_max_mc:
            return None
        return "CONFIRM_DRY"
    if v == "WET":
        if is_permeable(b.storage) and b.moisture < c_salt_line_mc - c_retest_margin:
            return "RETEST"
        return "DRY_NOW"
    if is_permeable(b.storage) and b.moisture > c_salt_line_mc + c_retest_margin:
        return "RETEST"
    if v == "DRY" and b.moisture <= c_eas_max_mc:
        return "READY_TO_STORE"
    return "NEARLY_DRY"


# ======================================================================================
# 7. messages
# ======================================================================================
def sanitise_place(p_name):
    if p_name is None:
        return None
    table = {0x2019: "'", 0x2018: "'", 0x201C: '"', 0x201D: '"', 0x2013: "-", 0x2014: "-", 0x00A0: " "}
    s = "".join(table.get(ord(ch), ch) for ch in p_name)             # TRANSLATE
    r = ""
    for c in s:
        a = ord(c) if ord(c) < 128 else 256
        if (65 <= a <= 90) or (97 <= a <= 122) or (48 <= a <= 57) or c in (
                " ", ".", ",", ":", ";", "!", "?", "'", "(", ")", "&", "/", "+", "-", "%", "@",
                '"', "#", "*", "=", "<", ">"):
            r += c
    r = re.sub(" {2,}", " ", r).strip(" ")                           # TRIM(REGEXP_REPLACE(...))
    r = r[:c_place_max_chars]
    r = r.rstrip(" ,.-")                                              # RTRIM(r, ' ,.-')
    return r if r != "" else None                                     # '' is NULL in Oracle


def get_template(code, lang):
    return TEMPLATES[(code, lang)]


def pct_text(x):
    one = fmt1(x)
    if one in ("13.5", "14.0", "15.0") and fmt2(x) != one + "0":
        return fmt2(x)
    return one


def evidence(b, en, tested=False):
    drifted = (not tested) and abs(b.moisture - b.test_value) >= D("0.05")
    if is_measured(b.source):
        if drifted:
            return ("estimate " if en else "makadirio ") + pct_text(b.moisture) + "%"
        if b.source == "meter":
            word = "meter" if en else "mita"
        else:
            word = "hygrometer" if en else "haigromita"
        return word + " " + pct_text(b.test_value) + "%"
    if drifted:
        return "estimate from salt test" if en else "makadirio ya kipimo cha chumvi"
    if b.source == "salt_flows":
        return "salt test: below about 15%" if en else "kipimo cha chumvi: chini ya 15% hivi"
    return "salt test: above 15%" if en else "kipimo cha chumvi: zaidi ya 15%"


def measured_text(b, en):
    ev = evidence(b, en, True)
    if b.last_test is None:
        return ev
    return ev + " " + ("on" if en else "tarehe") + " " + b.last_test.strftime("%d/%m")


def risk_text(left, en, tracks_air=True):
    if left is None:
        return "not available today" if en else "haipatikani leo"
    if left <= 0:
        return "used up (estimate)" if en else "umeisha (makadirio)"
    if left >= 90:
        if not tracks_air or left >= c_horizon_days:
            return "3 months or more" if en else "miezi 3 au zaidi"
        return ("3 months or more, falling fast in damp weather" if en
                else "miezi 3 au zaidi, hupungua haraka kukiwa na unyevu")
    if en:
        return "about " + str(left) + " day" + ("s" if left > 1 else "") + " (estimate)"
    return "siku " + str(left) + " hivi (makadirio)"


def rain_text(mm, prob, en):
    if prob is not None and prob >= c_rain_prob_alert:
        return (fmt0(prob) + "% chance") if en else ("uwezekano " + fmt0(prob) + "%")
    mmv = mm if mm is not None else D(0)
    return (fmt0(mmv) + " mm expected") if en else ("mm " + fmt0(mmv) + " zinatarajiwa")


def render(code, b, risk, left, today, places, rain_mm=None, rain_prob=None, rain_window=True, meta=None):
    meta = meta or NO_META
    v_stockist = sanitise_place(places.stockist)
    v_warehouse = sanitise_place(places.warehouse)
    v_checkpoint = sanitise_place(places.checkpoint)
    v_wdate = meta.fetched_on if (meta.given and meta.fetched_on is not None) else today
    v_credit = meta.credit if meta.given else c_credit_open_meteo
    v_nth = count_sent(b, "HIGH_ALERT", b.last_test or date.min) + 1
    v_dried = None
    if b.moisture is not None:
        v_dried = (verdict(b) == "WET")

    def fill(lang):
        en = lang == "en"
        t = get_template(code, lang)
        t = t.replace("{stockist}", v_stockist if v_stockist is not None else (C["c_place_stockist_en"] if en else C["c_place_stockist_sw"]))
        t = t.replace("{warehouse}", v_warehouse if v_warehouse is not None else (C["c_place_warehouse_en"] if en else C["c_place_warehouse_sw"]))
        t = t.replace("{checkpoint}", v_checkpoint if v_checkpoint is not None else (C["c_place_checkpoint_en"] if en else C["c_place_checkpoint_sw"]))
        t = t.replace("{date}", v_wdate.strftime("%d/%m"))
        t = t.replace("{credit}", v_credit)
        t = t.replace("{rain}", rain_text(rain_mm, rain_prob, en))
        if rain_window:
            when = "in the next 24 hours" if en else "ndani ya saa 24"
        else:
            when = "tomorrow" if en else "kesho"
        t = t.replace("{rain_when}", when)
        t = t.replace("{risk}", risk_text(left, en, b.storage != "hermetic"))
        t = t.replace("{weeks}", str(min((today - b.stored_since).days // 7, c_weeks_cap)))      # LEAST(FLOOR(x/7), cap)
        if v_nth >= c_high_alert_max:
            cl = ("Our last reminder. Retest: reply e.g. METER 14.2 (your own reading) or SALT YES/NO to restart." if en
                  else "Ukumbusho wa mwisho. Pima tena: mf. MITA 14.2 au CHUMVI NDIYO/HAPANA kuziwasha.")
        else:
            cl = "Reminders are weekly, at most 4." if en else "Ukumbusho: kila wiki, hadi mara 4."
        t = t.replace("{closing}", cl)
        if b.storage == "drying":
            rd = ""
        else:
            rd = " and reply DRYING" if en else " na ujibu ANIKA"
        t = t.replace("{reply_drying}", rd)
        if b.moisture is not None:
            t = t.replace("{evidence}", evidence(b, en))
            t = t.replace("{measured}", measured_text(b, en))
            if en:
                t = t.replace("{why}", "Your stored maize may have dried out" if v_dried
                              else "Damp air has probably re-wetted your stored maize")
            else:
                t = t.replace("{why}", "Huenda mahindi yako ghalani yamekauka" if v_dried
                              else "Hewa yenye unyevu huenda imeongeza unyevu wa mahindi yako ghalani")
        return t

    v_en = fill("en")
    v_sw = fill("sw")
    if b.lang == "en":
        msg, other = v_en, v_sw
    else:
        msg, other = v_sw, v_en
    return Rec(code=code, risk=risk, msg=msg, other=other, undo=None)


def welcome(b, today):
    return render("WELCOME", b, "UNKNOWN", None, today, new_places())


_GSM_BASIC = ("@$_ !\"#%&'()*+,-./0123456789:;<=>?ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz\n\r"
              "£¥èéùìòÇØøÅåΔΦΓΛΩ"
              "ΠΨΣΘΞÆæßÉ¤¡ÄÖÑÜ§¿"
              "äöñüà")
_GSM_EXT = "^{}\\[~]|€"


def sms_segments(text):
    n = 0
    for ch in text or "":
        if ch in _GSM_BASIC:
            n += 1
        elif ch in _GSM_EXT:
            n += 2
        else:
            return 0
    return 1 if n <= c_sms_gsm7_single else math.ceil(n / 153)


# ======================================================================================
# 8. evening decision
# ======================================================================================
def quiet_for(b, code, today, gap):
    return count_sent(b, code, today - timedelta(days=int(gap) - 1)) == 0


def repeat_ok(b, code, today, gap):
    return quiet_for(b, code, today, gap) and count_sent(b, code, b.last_test or date.min) <= c_repeat_max


def add_flag(flags, warn, token):
    if (token + ";") in (warn or ""):
        return token if flags is None else flags + "; " + token
    return flags


def build_diag(b, left, risk, adv, tomorrow):
    flags = None
    if b.moisture is not None:
        _, w1 = ast_w(tomorrow.temp_c, b.moisture)
        _, w2 = emc_w(tomorrow.temp_c, tomorrow.rh)
        w = w1 + w2
        for tok in ("AST moisture clamped", "AST moisture extrapolated", "AST temperature clamped",
                    "AST temperature extrapolated", "EMC humidity clamped", "EMC temperature clamped"):
            flags = add_flag(flags, w, tok)
    return Rec(moisture=None if b.moisture is None else ora_round(ora_round(b.moisture, 10), 1),
               moisture_raw=b.moisture, life_used_raw=b.life_used, source=b.source,
               verdict=verdict(b), life_used_pct=ora_round(ora_round(100 * b.life_used, 10), 1), days_left=left,
               days_left_capped=left is not None and left >= c_horizon_days, weather_stale=False,
               risk=risk, advice=adv, emc_tomorrow=ora_round(ora_round(emc(tomorrow.temp_c, tomorrow.rh), 10), 1),
               flags=flags, missing_days=0)


def evaluate(b, today, forecast, places, rain24, meta=None, send=True):
    meta = meta or NO_META
    alert = Rec(code=None, risk=None, msg=None, other=None, undo=None)
    if len(forecast) == 0:
        raise OraError("forecast is empty")
    if forecast[0].wx_date != today + timedelta(days=1):
        raise OraError("forecast(1) must be tomorrow")
    tomorrow = forecast[0]
    use24 = rain24.given and not (rain24.mm is None and rain24.prob is None)
    v_stale = meta.given and meta.age_hours > c_weather_stale_hours
    if use24:
        mm, prob = rain24.mm, rain24.prob
    else:
        mm, prob = tomorrow.rain_mm, tomorrow.rain_prob
    left = days_left(b, forecast)
    risk = risk_level(b.life_used, left)
    adv = advice(b)
    diag = build_diag(b, left, risk, adv, tomorrow)
    if mm is None and prob is None:
        diag.flags = "rain data missing" if diag.flags is None else diag.flags + "; rain data missing"
    if v_stale:
        diag.flags = "weather stale" if diag.flags is None else diag.flags + "; weather stale"
        diag.weather_stale = True
    if (not send) or b.status != "active" or (b.last_alert is not None and b.last_alert == today):
        return alert, diag

    escalated = level_ord(risk) > level_ord(b.told_level) and level_ord(risk) >= 1
    if (left is not None and b.told_left is not None and left <= c_worse_within
            and left <= b.told_left * c_worse_factor):
        escalated = True
    rain = ((prob is not None and prob >= c_rain_prob_alert) or (mm is not None and mm >= c_rain_mm_alert)) and not v_stale
    retest_ok = adv is None or adv != "RETEST" or count_sent(b, "RETEST", today - timedelta(days=29)) < c_retest_per_30_days

    code = None
    if rain and b.storage == "drying" and needs_drying(adv) and b.rain_unacked < c_rain_unacked_max:
        code = "RAIN_COVER"
    elif adv == "TEST_FIRST":
        if quiet_for(b, adv, today, c_remind_gap_days) and count_sent(b, adv) < c_test_reminders_max:
            code = adv
    elif not retest_ok:
        pass
    elif pushed_on_change(adv) and (b.last_advice is None or adv != b.last_advice):
        code = adv
    elif adv in ("DRY_NOW", "RETEST", "OPEN_AND_DRY") and escalated and quiet_for(b, adv, today, c_remind_gap_days):
        code = adv
    elif adv in ("DRY_NOW", "RETEST") and risk == "HIGH" and repeat_ok(b, adv, today, c_remind_gap_days):
        code = adv
    elif adv in ("OPEN_AND_DRY", "CONFIRM_DRY") and repeat_ok(b, adv, today, c_sealed_gap_days):
        code = adv
    elif (is_permeable(b.storage) and verdict(b) == "DRY" and b.moisture < c_hermetic_max_mc
          and b.life_used < c_medium_life and (today - b.stored_since).days >= c_insect_reminder_days
          and count_sent(b, "INSECT_REMINDER") == 0):
        code = "INSECT_REMINDER"

    # capped HIGH_ALERT (C-12): weekly, c_high_alert_max per test result, then the closing state
    if (code is None and risk == "HIGH"
            and adv in ("RETEST", "DRY_NOW", "SORT_AND_SELL", "OPEN_AND_DRY", "CONFIRM_DRY")
            and (b.last_alert is None or (today - b.last_alert).days >= c_high_alert_gap_days)
            and count_sent(b, "HIGH_ALERT", b.last_test or date.min) < c_high_alert_max):
        code = "HIGH_ALERT"
    elif (code is None and risk == "HIGH"
            and adv in ("RETEST", "DRY_NOW", "SORT_AND_SELL", "OPEN_AND_DRY", "CONFIRM_DRY")
            and count_sent(b, "HIGH_ALERT", b.last_test or date.min) >= c_high_alert_max):
        diag.flags = "high alerts used up" if diag.flags is None else diag.flags + "; high alerts used up"

    if code is None:
        return alert, diag
    v_undo = make_undo(b)
    alert = render(code, b, risk, left, today, places, mm, prob, use24, meta)
    alert.undo = v_undo
    b.last_alert = today
    add_sent(b, today, code)
    if code == "RAIN_COVER":
        b.rain_unacked = b.rain_unacked + 1
    elif is_advice_code(code):
        b.last_advice = code
        b.told_level = risk
        b.told_left = left
    return alert, diag


# ======================================================================================
# 9. replies
# ======================================================================================
_UNI_SPACES = "\u00a0\u2002\u2003\u2007\u2009\u200a\u200b\u202f\u3000"


def normalise(p_text):
    if p_text is None:
        return None
    t = p_text[:c_max_text_chars].upper().replace("\u00b0", " ")
    t = "".join(" " if ch in _UNI_SPACES else ch for ch in t)             # TRANSLATE
    t = re.sub(r"[!?;:'\"()_/*#-]", " ", t)
    r = ""
    for k in range(len(t)):
        c = t[k]
        if c in (".", ","):
            prev = t[k - 1] if k > 0 else None
            nxt = t[k + 1] if k + 1 < len(t) else None
            is_d = lambda ch: ch is not None and 48 <= ord(ch) <= 57     # noqa: E731
            if not (is_d(prev) and is_d(nxt)):
                c = " "
        r += c
    r = re.sub(r"[ \t\r\n\f\v]+", " ", r).strip(" ")
    r = re.sub(" +%", "%", r)
    return r if r != "" else None                                        # '' is NULL in Oracle


OPTOUT_WORDS = ("STOP", "STOPP", "STOPPED", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "ACHA", "SITISHA", "SIMAMISHA",
                "NISITISHIE")
OPTOUT_PHRASES = ("NO MORE", "OPT OUT", "SITAKI TENA")
c_optout_max_tokens = 6


def is_optout(norm):
    if norm is None:
        return False
    if norm.count(" ") + 1 > c_optout_max_tokens:
        return False
    pad = " " + norm + " "
    return any((" " + w + " ") in pad for w in OPTOUT_WORDS + OPTOUT_PHRASES)


def normalise_address(addr):
    a = re.sub(r"[^0-9a-z+:]", "", (addr or "").lower())
    if a[:2] == "00":
        a = "+" + a[2:]
    if re.fullmatch(r"0[0-9]{9}", a):
        a = "+254" + a[1:]
    elif re.fullmatch(r"254[0-9]{9}", a):
        a = "+" + a
    return a


def address_hash(addr, pepper):
    import hashlib
    import hmac
    return hmac.new(pepper.encode(), normalise_address(addr).encode(), hashlib.sha256).hexdigest()


def to_num(s):
    s = s.replace(",", ".")
    s = re.sub(r"(\.[0-9]{15})[0-9]+", r"\1", s)                  # REGEXP_REPLACE(..., '\1')
    ip, _, fp = s.partition(".")
    if len(ip) > 20 or len(fp) > 15:
        raise OraError("ORA-01722/01426")
    return Decimal(s)


def apply_reply(b, p_text, today, temp_hint=None):
    t = normalise(p_text)
    if t is None:
        return "UNKNOWN"
    v_first = t[: (t + " ").index(" ")]
    if re.search(RE_SALT_YES, t):
        record_salt(b, today, True)
        return "SALT_YES"
    if re.search(RE_SALT_NO, t):
        return "SALT_NO" if record_salt(b, today, False) else "SALT_NO_IGNORED"
    v_neg = re.search(RE_NEG, (p_text or "")[:c_max_text_chars].upper().translate({0x2212: "-", 0x2013: "-", 0x2014: "-"})) is not None
    if re.search(RE_METER_CMD, t):
        m = re.search(RE_METER, t)
        if v_neg or not m:
            return "INVALID"
        try:
            v_val = to_num(m.group(2))
            record_meter(b, today, v_val)
        except Exception:
            return "INVALID"
        return "METER"
    if re.search(RE_HYGRO_CMD, t):
        m = re.search(RE_HYGRO, t)
        if v_neg or not m:
            return "INVALID"
        try:
            if m.group(4) is not None:
                v_temp = to_num(m.group(4))
            else:
                v_temp = temp_hint
            if v_temp is None:
                raise OraError("no temperature")
            v_rh = to_num(m.group(1))
            record_hygro(b, today, v_rh, v_temp)
        except Exception:
            return "INVALID"
        return "HYGRO"
    if is_optout(t):
        b.status = "stopped"
        return "STOP"
    if v_first in ("DRYING", "ANIKA"):
        set_storage(b, today, "drying")
        return "STORAGE"
    if v_first in ("SACKS", "SACK", "MAGUNIA"):
        set_storage(b, today, "sack")
        return "STORAGE"
    if v_first in ("SEALED", "NIMEFUNGA"):
        set_storage(b, today, "hermetic")
        return "STORAGE"
    if v_first in ("SOLD", "NIMEUZA", "DEPOSITED", "GHALANI"):
        b.status = "closed"
        return "CLOSED"
    if v_first in ("START", "ANZA"):
        if b.status != "active":
            v_was = b.status
            b.status = "active"
            if v_was == "closed" and b.moisture is not None:
                b.last_advanced = today - timedelta(days=1)
        return "START"
    if t in ("1", "OK", "OKAY", "SAWA", "ASANTE", "THANKS", "DONE", "THANK YOU"):
        return "ACK"
    return "UNKNOWN"


def respond(b, p_text, today, forecast, places, temp_hint=None, meta=None):
    alert = Rec(code=None, risk=None, msg=None, other=None, undo=None)
    hint = temp_hint
    if hint is None and len(forecast) > 0:
        hint = forecast[0].temp_c
    norm = normalise(p_text)
    if norm is not None:
        norm = norm[:c_norm_store_chars]
    duplicate = False
    for (rd, rn) in b.replies:
        if rd == today and (rn == norm or (rn is None and norm is None)):
            duplicate = True
    was = b.status
    cmd = apply_reply(b, p_text, today, hint)
    b.replies.append((today, norm))
    b.rain_unacked = 0
    if b.status == "stopped" and cmd != "STOP":
        return cmd, alert
    left = days_left(b, forecast)
    risk = risk_level(b.life_used, left)
    adv = advice(b)
    if was == "closed" and b.status == "closed" and cmd != "CLOSED":
        code = "CLOSED"
    elif cmd in ("UNKNOWN", "INVALID"):
        code = "HELP"
    elif cmd in ("ACK", "SALT_NO_IGNORED") or duplicate:
        if cmd == "ACK" or duplicate:
            code = "THANKS"
        else:
            code = adv if adv is not None else "STATUS"
    elif cmd in ("CLOSED", "STOP"):
        code = "CLOSED" if cmd == "CLOSED" else "STOPPED"
    elif cmd == "STORAGE" and b.storage == "drying" and needs_drying(adv):
        code = "THANKS"
    else:
        code = adv if adv is not None else "STATUS"
    v_undo = make_undo(b)
    if is_advice_code(code):
        b.last_advice = code
        b.told_level = risk
        b.told_left = left
    alert = render(code, b, risk, left, today, places, None, None, True, meta)
    alert.undo = v_undo
    add_sent(b, today, code)
    return cmd, alert


# ======================================================================================
# 10. daily_run
# ======================================================================================
def daily_run(b, today, days, places, rain24, meta=None):
    v_again = b.last_run is not None and b.last_run == today
    v_past, v_forecast = [], []
    for w in days:                                            # split_weather
        if w.wx_date <= today:
            v_past.append(w)
        else:
            v_forecast.append(w)
    if len(v_forecast) == 0:
        raise OraError("weather must include tomorrow")
    if v_forecast[0].wx_date != today + timedelta(days=1):
        raise OraError("weather must include tomorrow")
    if b.moisture is not None and b.last_advanced is None:
        b.last_advanced = (b.last_test or today) - timedelta(days=1)
    v_missing = 0
    if b.moisture is not None and b.status == "active":
        v_d = b.last_advanced + timedelta(days=1)
        while v_d <= today:
            v_found = False
            v_w = None
            for pw in v_past:
                if pw.wx_date == v_d:
                    v_w = pw
                    v_found = True
            if not v_found:
                v_missing += 1
                v_have_src = False
                v_src = None
                for pw in v_past:
                    if pw.wx_date < v_d and (not v_have_src or pw.wx_date > v_src.wx_date):
                        v_src = pw
                        v_have_src = True
                if not v_have_src:
                    v_src = v_forecast[0]
                v_w = W(v_d, v_src.temp_c, v_src.rh, D(0), None)
            advance_day(b, v_w)
            v_d = v_d + timedelta(days=1)
    alert, diag = evaluate(b, today, v_forecast, places, rain24, meta, not v_again)
    if v_again:
        diag.flags = "already run today" if diag.flags is None else diag.flags + "; already run today"
    else:
        b.last_run = today
    diag.missing_days = v_missing
    return alert, diag


# ======================================================================================
# test drivers
# ======================================================================================
FAILS = []
PASSES = [0]


def check(ok, label, detail=""):
    if ok:
        PASSES[0] += 1
    else:
        FAILS.append(f"{label} {detail}")
        print("FAIL", label, detail)


def same_n(a, b, tol):
    return (a is None and b is None) or (a is not None and b is not None and abs(D(a) - D(b)) <= D(tol))


def test_vectors():
    vec = json.load(open(os.path.join(PLSQL, "..", "engine", "vectors.json")))
    bad = 0
    for r in vec["emc"]:
        got = emc(d(r["temp_c"]), d(r["rh"]))
        if not same_n(got, d(r["emc"]), "0.000001"):
            bad += 1
            print("FAIL emc", r, got)
    check(bad == 0 and len(vec["emc"]) == 49, f"EMC vectors ({len(vec['emc'])}), mismatches {bad}")
    bad = 0
    for r in vec["ast"]:
        got = ast_days(d(r["temp_c"]), d(r["mc"]))
        if not same_n(got, d(r["days"]), "0.000001"):
            bad += 1
            print("FAIL ast", r, got)
    check(bad == 0 and len(vec["ast"]) == 60, f"AST vectors ({len(vec['ast'])}), mismatches {bad}")

    sys.path.insert(0, HERE)
    import gen_vectors_sql as G                               # the weather rules, verified against vectors
    d0 = G.D0
    for sc in vec["scenarios"]:
        wx = G.WX[sc["name"]]
        b = new_batch_rec(0, 1, sc["storage"], d0)
        rain24 = new_rain24(False)
        places = new_places()
        steps = 0
        for t in sc["trace"]:
            off = (date.fromisoformat(t["day"]) - d0).days
            today = d0 + timedelta(days=off)
            days = []
            for k in range(-2, 8):
                tt, rh, mm, pp = wx(off, off + k)
                days.append(W(d0 + timedelta(days=off + k), tt, rh, mm, pp))
            if t["event"] == "reply":
                fc = [w for w in days if w.wx_date > today]
                cmd, al = respond(b, t["text"], today, fc, places)
                ok = cmd == t["cmd"] and al.code == t["code"] and al.msg == t["message"]
                check(ok, f"{sc['name']} d{off} reply {t['text']!r}", f"got {cmd}/{al.code} want {t['cmd']}/{t['code']}")
            else:
                al, dg = daily_run(b, today, days, places, rain24)
                exact_m, exact_l = D(repr(t["moisture_exact"])), D(repr(t["life_used_exact"]))
                ok = (al.code == t["code"] and dg.risk == t["level"] and dg.days_left == t["days_left"]
                      and (al.msg == t["message"])
                      and fmt1(dg.moisture_raw) == t["moisture_s"] and fmt1(100 * dg.life_used_raw) == t["life_used_pct_s"]
                      and same_n(dg.moisture_raw, exact_m, "0.0001") and same_n(dg.life_used_raw, exact_l, "0.000001"))
                check(ok, f"{sc['name']} d{off} evening",
                      f"got {al.code} {dg.risk} {dg.days_left} {fmt1(dg.moisture_raw)} {fmt1(100 * dg.life_used_raw)} want {t}")
            steps += 1
        print(f"  scenario {sc['name']}: {steps} steps replayed (exact message text)")

    bad = 0
    for r in vec["rounding"]:
        x = D(repr(r["x"]))
        for k, f in (("fmt0", fmt0), ("fmt1", fmt1), ("fmt2", fmt2)):
            if k in r and f(x) != r[k]:
                bad += 1
                print("FAIL rounding", r, k, f(x))
    check(bad == 0, f"rounding vectors ({len(vec['rounding'])})", f"{bad} mismatches")
    bad = 0
    for r in vec["evidence"]:
        for lang, en in (("en", True), ("sw", False)):
            b = new_batch_rec(0, 1, "sack", date(2026, 10, 1))
            b.moisture = b.test_value = b.peak_since_test = D(repr(r["reading"]))
            b.source = "meter"
            if evidence(b, en) != r[lang]:
                bad += 1
                print("FAIL evidence", r, lang, evidence(b, en))
    check(bad == 0, f"evidence vectors ({len(vec['evidence'])})", f"{bad} mismatches")
    bad = 0
    for r in vec["optout"]:
        n = normalise(r["text"])
        if (n or "") != r["norm"] or is_optout(n) != r["optout"]:
            bad += 1
            print("FAIL optout", r, n)
    check(bad == 0, f"opt-out vectors ({len(vec['optout'])})", f"{bad} mismatches")
    bad = 0
    for r in vec["normalise"]:
        n = normalise("A" * r["text_len"]) or ""
        if len(n) != r["norm_len"]:
            bad += 1
    check(bad == 0, f"normalise length vectors ({len(vec['normalise'])})", f"{bad} mismatches")
    bad = 0
    for r in vec["addresses"]:
        if normalise_address(r["addr"]) != r["canonical"] or address_hash(r["addr"], vec["pepper"]) != r["hash"]:
            bad += 1
            print("FAIL address", r)
    check(bad == 0, f"address-hash vectors ({len(vec['addresses'])})", f"{bad} mismatches")
    bad = 0
    for r in vec["days_left_cases"]:
        b = new_batch_rec(0, 1, r["storage"], d0)
        b.moisture = b.test_value = b.peak_since_test = d(r["moisture"])
        b.source = "meter"
        b.life_used = d(r["life"])
        fc = [W(d0 + timedelta(days=i + 1), t, rh) for i, (t, rh) in enumerate(r["forecast"])]
        left = days_left(b, fc)
        if left != r["left"] or risk_level(b.life_used, left) != r["level"]:
            bad += 1
            print("FAIL days_left", r, left)
    check(bad == 0, f"days_left cases ({len(vec['days_left_cases'])})", f"{bad} mismatches")


def test_rounding_fuzz():
    """5.00 .. 40.00 step 0.01: Python reference, this mirror and the JS port against exact half-up integers."""
    import subprocess
    xs = [i / 100 for i in range(500, 4001)]
    js = ("import { fmt } from '%s';\nconst o=[];for(let i=500;i<=4000;i++){const x=i/100;"
          "o.push([fmt(x,0),fmt(x,1),fmt(x,2)].join(' '));}\nconsole.log(o.join('\\n'));"
          % os.path.join(PLSQL, '..', 'site', 'assets', 'js', 'engine.js'))
    jsout = None
    try:
        jsout = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True,
                               timeout=60, check=True).stdout.split("\n")
    except Exception as e:                                           # node missing: report, do not hide
        print("   node unavailable:", e)
    div = {"python": 0, "mirror": 0, "js": 0}
    for n, x in zip(range(500, 4001), xs):
        h = n                                                         # hundredths, exact
        exp0 = str((h + 50) // 100)
        t = (h + 5) // 10
        exp1 = f"{t // 10}.{t % 10}"
        exp2 = f"{h // 100}.{h % 100:02d}"
        want = (exp0, exp1, exp2)
        if (H.fmt0(x), H.fmt1(x), H.fmt2(x)) != want:
            div["python"] += 1
        dx = D(repr(x))
        if (fmt0(dx), fmt1(dx), fmt2(dx)) != want:
            div["mirror"] += 1
        if jsout is not None and tuple(jsout[n - 500].split(" ")) != want:
            div["js"] += 1
    if jsout is None:
        div.pop("js")
    print(f"   rounding fuzz 5.00..40.00 step 0.01 ({len(xs)} values): divergences {div}")
    check(all(v == 0 for v in div.values()) and jsout is not None, "rounding fuzz: 0 divergences across all ports", str(div))


# ---- conversion between the reference objects and the mirror
def to_mirror_batch(rb):
    b = new_batch_rec(0, 1, rb.storage, rb.stored_since, rb.lang)
    b.last_test = rb.last_test
    for f in ("source", "last_test", "last_advanced", "last_alert", "last_advice", "told_level",
              "rain_unacked", "status", "told_left", "last_run"):
        setattr(b, f, getattr(rb, f))
    for f in ("moisture", "test_value", "peak_since_test", "life_used"):
        setattr(b, f, d(getattr(rb, f)))
    b.sent = list(rb.sent)
    b.replies = list(rb.replies)
    return b


def rand_places(rnd):
    pool = ["SAMPLE Agrovet, Kitale (KES 300)", "Mama’s Agrovet – Kitale town branch, Moi Avenue",
            "ç€", "X" * 32, "Y" * 30, "  spaced   out  ", "Café “One”", "Co-op, ", None, "", "a.b-,"]
    return {k: rnd.choice(pool) for k in ("stockist", "warehouse", "checkpoint") if rnd.random() < 0.6}


def test_render(rnd, n):
    bad = 0
    for _ in range(n):
        rb = H.Batch("B", "w", rnd.choice(["drying", "sack", "crib", "floor", "hermetic"]),
                     date(2026, 10, 12) - timedelta(days=rnd.randint(0, 120)), rnd.choice(["en", "sw"]))
        if rnd.random() < 0.9:
            src = rnd.choice(["meter", "hygro", "salt_flows", "salt_sticky"])
            tv = round(rnd.uniform(6, 35), rnd.choice([1, 2]))
            rb.moisture = round(tv + rnd.choice([0, 0, 0.03, 0.06, 1.0, -2.0]), 3)
            rb.moisture = max(round(rb.moisture, 3), 0.5)
            rb.source, rb.test_value, rb.peak_since_test = src, tv, max(tv, rb.moisture)
        if rb.moisture is not None:
            rb.last_test = date(2026, 10, 12) - timedelta(days=rnd.randint(0, 30))
            for _k in range(rnd.choice([0, 0, 1, 3, 4])):
                rb.sent.append((rb.last_test, "HIGH_ALERT"))
        codes = [c for c, (en, sw) in H.TEMPLATES.items()
                 if rb.moisture is not None or not ("{evidence}" in en or "{why}" in en or "{measured}" in en)]
        code = rnd.choice(codes)
        left = rnd.choice([None, 0, 1, 2, 30, 89, 90, 365])
        today = date(2026, 10, 12)
        places = rand_places(rnd)
        mm = rnd.choice([None, 0.0, 3.0, 12.0, 120.0])
        prob = rnd.choice([None, 10.0, 59.0, 60.0, 80.0, 100.0])
        win = rnd.random() < 0.5
        wmeta = rnd.choice([None, None, H.WeatherMeta(today - timedelta(days=1), 30.0),
                            H.WeatherMeta(today, 2.0, "Simulated weather")])
        want = H.render(code, rb, "HIGH", left, today, places, (mm, prob), win, wmeta)
        mb = to_mirror_batch(rb)
        mmeta = None if wmeta is None else new_meta(True, wmeta.fetched_on, wmeta.age_hours, wmeta.credit)
        got = render(code, mb, "HIGH", None if left is None else left, today,
                     new_places(**places), d(mm), d(prob), win, mmeta)
        ok = want.text == got.msg and want.other == got.other
        if not ok:
            bad += 1
            if bad < 4:
                print("render mismatch", code, rb.source, places, "\n  ref:", want.text, "\n  got:", got.msg)
        for text in (got.msg, got.other):
            seg = sms_segments(text)
            if not (1 <= seg <= c_sms_max_segments):
                bad += 1
    check(bad == 0, f"render equals reference ({n} random fills, both languages, GSM-7, <=2 SMS)", f"{bad} mismatches")


REPLY_CORPUS = [
    "SALT YES", "salt no", "Salt  Yes!", "CHUMVI NDIYO", "chumvi ndio", "chumvi hapana", "saltyes", "SALT YESTERDAY",
    "SALT NOT", "METER 13.5", "meter 13,5", "Meter13.2%", "METER 13.5 %", "MITA 14", "metre 4", "METER 41", "METER 5",
    "METER 40", "METER .5", "METER 13.", "METER 1.2.3", "METER abc", "METER 13.5 and more", "METER 13-15", "meter 13 / 15", "METER -13", "METER \u221213", "MITA 13\u201415", "HYGRO 62 -5", "METER 13 15", "METERS 13", "METER 13.5 %", "HYGRO 62 18", "hygro 62",
    "HYGRO 62% 18C", "hygro 62,5 18,5 c", "HYGRO 100 18", "HYGRO 0 18", "HYGRO 62 60", "HYGRO 62 C", "HYGRO 62 18 5",
    "DRYING", "anika", "Sacks!", "magunia", "SEALED", "nimefunga", "SOLD", "nimeuza", "deposited", "ghalani", "STOP",
    "simamisha", "START", "anza", "1", "ok", "Okay.", "sawa", "Asante", "thanks", "THANK YOU", "thank  you!!", "done",
    "", "   ", "???", "hello", "13.5", "METER", "HYGRO", "dry", "sealed bags please", "stop now", "NO", "YES",
    "salt\tyes", "METER 13.5°", "please stop", "Tafadhali  ACHA", "unsubscribe", "Cancel!", "QUIT", "end", "sitisha",
    "STOPPED", "please", "stop\u00a0now", "METER\u00a013.5", "A" * 1500, "STOP" + " " * 2000 + "X", "METER 99999999999999999999999 ", "METER 13.0000000000000000001",
]


def same_state(rb, mb):
    for f in ("source", "last_test", "last_advanced", "last_alert", "last_advice", "told_level", "rain_unacked",
              "status", "storage", "stored_since", "last_run", "told_left"):
        if getattr(rb, f) != getattr(mb, f):
            return False, f
    for f in ("moisture", "test_value", "peak_since_test", "life_used"):
        a, c = getattr(rb, f), getattr(mb, f)
        if (a is None) != (c is None) or (a is not None and abs(D(repr(a)) - c) > D("1e-9")):
            return False, f
    return True, None


def seed_batch(rnd, storage=None):
    d0 = date(2026, 10, 12)
    rb = H.Batch("B", "w", storage or rnd.choice(["drying", "sack", "crib", "floor", "hermetic"]),
                 d0 - timedelta(days=rnd.randint(0, 80)), rnd.choice(["en", "sw"]))
    pick = rnd.random()
    if pick < 0.25:
        pass
    elif pick < 0.5:
        rb.record_meter(d0 - timedelta(days=rnd.randint(0, 9)), round(rnd.uniform(6, 25), 1))
    elif pick < 0.75:
        rb.record_salt(d0 - timedelta(days=rnd.randint(0, 9)), rnd.random() < 0.5)
    else:
        rb.record_hygro(d0 - timedelta(days=rnd.randint(0, 9)), round(rnd.uniform(40, 90)), 18.0)
    rb.status = rnd.choice(["active"] * 6 + ["closed", "stopped"])
    return rb


def test_replies(rnd, n):
    d0 = date(2026, 10, 12)
    bad = 0
    texts = list(REPLY_CORPUS)
    words = ["SALT", "YES", "NO", "METER", "HYGRO", "13.5", "62", "18", "%", ".", ",", "C", "SEALED", "STOP", "START",
             "ANIKA", "1", "ok", "-", "'", "°", "CHUMVI", "NDIYO", "HAPANA", "MITA", "x", "PLEASE", "TAFADHALI",
             "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "ACHA", "SITISHA", "\u00a0", "\u2009"]
    for _ in range(n):
        texts.append(" ".join(rnd.choice(words) for _ in range(rnd.randint(1, 4))))
    for text in texts:
        for _ in range(3):
            rb = seed_batch(rnd)
            mb = to_mirror_batch(rb)
            hint = rnd.choice([None, 18.0])
            want = H.apply_reply(rb, text, d0, hint)
            got = apply_reply(mb, text, d0, d(hint))
            ok, field = same_state(rb, mb)
            if want != got or not ok:
                bad += 1
                if bad < 6:
                    print("reply mismatch", repr(text), want, got, field)
        if H.normalise(text) != (normalise(text) or ""):
            bad += 1
            print("normalise mismatch", repr(text), repr(H.normalise(text)), repr(normalise(text)))
    check(bad == 0, f"apply_reply / normalise equal reference ({len(texts)} texts x 3 states)", f"{bad} mismatches")


def test_fuzz(rnd, n, days=45):
    d0 = date(2026, 10, 12)
    pool = ["SALT YES", "SALT NO", "METER 13.1", "METER 14.6", "METER 17", "HYGRO 62 18", "HYGRO 80 22", "DRYING",
            "SACKS", "SEALED", "1", "OK", "hello", "STOP", "START", "SOLD", "METER 99", "chumvi ndiyo", "mita 12.8", "please stop", "ACHA", "unsubscribe",
            "METER 13.54", "METER 13.45", "METER 15.05"]
    bad = 0
    steps = 0
    seen = {}
    for s in range(n):
        storage = rnd.choice(["drying", "sack", "crib", "floor", "hermetic"])
        rb = H.Batch("B", "w", storage, d0 - timedelta(days=rnd.randint(0, 60)), rnd.choice(["en", "sw"]))
        mb = new_batch_rec(0, 1, rb.storage, rb.stored_since, rb.lang)
        mode = rnd.choice(["dry", "wet", "mixed", "hot"])
        pr = rand_places(rnd)
        places = new_places(**pr)
        reply_days = {rnd.randrange(days): [rnd.choice(pool) for _ in range(rnd.randint(1, 2))]
                      for _ in range(rnd.randint(1, 7))}
        for off in range(days):
            today = d0 + timedelta(days=off)
            wl = []
            for k in range(-2, 8):
                if mode == "dry":
                    t, rh = rnd.choice([16, 18, 20]), rnd.choice([55, 60, 65, 70])
                elif mode == "wet":
                    t, rh = rnd.choice([14, 17, 19]), rnd.choice([80, 88, 92, 96])
                elif mode == "hot":
                    t, rh = rnd.choice([26, 30, 34]), rnd.choice([30, 50, 75])
                else:
                    t, rh = rnd.choice([10, 18, 24]), rnd.choice([40, 63, 85, 95])
                mm = rnd.choice([0.0, 0.0, 1.0, 12.0])
                pp = rnd.choice([None, 10.0, 30.0, 80.0])
                wl.append((today + timedelta(days=k), float(t), float(rh), mm, pp))
            if rnd.random() < 0.05:                                    # a missing past day
                wl = [w for w in wl if w[0] != today - timedelta(days=1)]
            rwl = [H.WeatherDay(*w) for w in wl]
            mwl = [W(*w) for w in wl]
            for text in reply_days.get(off, []):
                rfc = [w for w in rwl if w.day > today]
                mfc = [w for w in mwl if w.wx_date > today]
                rm_ = rnd.choice([None, H.WeatherMeta(today, 1.0)])
                mm2 = None if rm_ is None else new_meta(True, rm_.fetched_on, rm_.age_hours, rm_.credit)
                rc, ra = H.respond(rb, text, today, rfc, pr, meta=rm_)
                mc, ma = respond(mb, text, today, mfc, places, None, mm2)
                steps += 1
                seen['reply:' + str(ma.code)] = seen.get('reply:' + str(ma.code), 0) + 1
                if rc != mc or (ra.code if ra else None) != ma.code or (ra and ra.text != ma.msg):
                    bad += 1
                    print("respond mismatch", s, off, text, rc, mc, ra and ra.code, ma.code)
            rain24 = None if rnd.random() < 0.7 else (rnd.choice([0.0, 8.0, None]), rnd.choice([None, 20.0, 90.0]))
            wm = rnd.choice([None, None, H.WeatherMeta(today, 3.0), H.WeatherMeta(today - timedelta(days=2), 60.0, "Simulated weather")])
            mm_ = None if wm is None else new_meta(True, wm.fetched_on, wm.age_hours, wm.credit)
            ra, rd = H.daily_run(rb, today, rwl, pr, rain24, wm)
            ma, md = daily_run(mb, today, mwl, places,
                               new_rain24(False) if rain24 is None else new_rain24(True, *rain24), mm_)
            if rnd.random() < 0.3:                                    # a second run the same day changes and sends nothing
                before = (len(mb.sent), mb.last_alert, mb.life_used)
                ra2, rd2 = H.daily_run(rb, today, rwl, pr, rain24, wm)
                ma2, md2 = daily_run(mb, today, mwl, places,
                                     new_rain24(False) if rain24 is None else new_rain24(True, *rain24), mm_)
                if ra2 is not None or ma2.code is not None or before != (len(mb.sent), mb.last_alert, mb.life_used):
                    bad += 1
                    print("idempotency broken", s, off)
            steps += 1
            seen[ma.code] = seen.get(ma.code, 0) + 1
            same = ((ra.code if ra else None) == ma.code and rd["level"] == md.risk
                    and rd["days_left"] == md.days_left and rd["advice"] == md.advice
                    and rd["missing_days"].__len__() == md.missing_days
                    and (ra is None or ra.text == ma.msg) and list(rd["flags"]) == ((md.flags or "").split("; ") if md.flags else []))
            ok_state, field = same_state(rb, mb)
            if not same or not ok_state:
                bad += 1
                print("daily_run mismatch scenario", s, "day", off, storage, mode,
                      "\n  ref", ra.code if ra else None, rd["level"], rd["days_left"], rd["flags"],
                      "\n  got", ma.code, md.risk, md.days_left, md.flags, "state field", field)
                break
    print('   codes exercised:', ', '.join(f'{k}={v}' for k, v in sorted(seen.items(), key=lambda kv: str(kv[0]))))
    check(bad == 0, f"differential fuzz: {n} random scenarios x {days} days ({steps} steps)", f"{bad} mismatches")


def test_c12_scenario():
    """E3-02: the fuzz never reaches the C-12 closing state, so replay a fixed one in both ports: a measured 13.0 % batch in
    damp air with no replies. Four HIGH_ALERTs, the 4th is the last-chance text, then silence with the explicit flag (flags
    compared as an ordered list), and a new meter reading restarts the count. Texts must be identical in both ports."""
    d0 = date(2026, 10, 12)
    rb = H.Batch("B", "w", "sack", d0, "en")
    rb.record_meter(d0, 13.0)
    mb = new_batch_rec(0, 1, "sack", d0, "en")
    record_meter(mb, d0, D("13.0"))
    places = new_places()
    bad, highs, used_up_after, last_texts = 0, [], None, []
    for off in range(100):
        today = d0 + timedelta(days=off)
        if off == 80:                                                        # a new test result restarts the count
            rc, ra_ = H.respond(rb, "METER 15", today, [H.WeatherDay(today + timedelta(days=k), 19.0, 92.0, 0.0, None) for k in range(1, 8)])
            mc, ma_ = respond(mb, "METER 15", today, [W(today + timedelta(days=k), 19.0, 92.0, 0.0, None) for k in range(1, 8)], places, None, None)
            if rc != mc or (ra_.text if ra_ else None) != (ma_.msg if ma_ else None):
                bad += 1
        wl = [(today + timedelta(days=k), 19.0, 92.0, 0.0, None) for k in range(-2, 8)]
        ra, rd = H.daily_run(rb, today, [H.WeatherDay(*w) for w in wl], None, None, None)
        ma, md = daily_run(mb, today, [W(*w) for w in wl], places, new_rain24(False), None)
        flags = (md.flags or "").split("; ") if md.flags else []
        if (ra.code if ra else None) != ma.code or list(rd["flags"]) != flags or (ra and ra.text != ma.msg):
            bad += 1
            print("C-12 mismatch day", off, ra and ra.code, ma.code, rd["flags"], flags)
        if ma.code == "HIGH_ALERT" and off < 80:
            highs.append(off)
            last_texts.append(ma.msg)
        if off < 80 and "high alerts used up" in flags and used_up_after is None:
            used_up_after = off
    check(bad == 0, "C-12 scenario: both ports agree day by day, texts and ordered flags", f"{bad} mismatches")
    check(len(highs) == 4 and "Our last reminder" in last_texts[-1] and all("Our last reminder" not in t for t in last_texts[:-1]),
          "C-12 scenario: exactly four HIGH_ALERTs, only the 4th is the last-chance text", str(highs))
    check(used_up_after is not None and used_up_after > highs[-1], "C-12 scenario: the closing state is flagged after the 4th", str(used_up_after))
    check("e.g. METER 14.2 (your own reading) or SALT YES/NO" in last_texts[-1], "E3-01: the last-chance text names only commands the parser accepts")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fuzz", type=int, default=60)
    ap.add_argument("--seed", type=int, default=20261012)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    print("1. vectors.json replay")
    test_vectors()
    print("1b. rounding fuzz 5.00..40.00 step 0.01, all ports")
    test_rounding_fuzz()
    print("2. render vs reference")
    test_render(rnd, 1500)
    print("3. replies vs reference")
    test_replies(rnd, 400)
    print(f"4. differential fuzz ({a.fuzz} scenarios)")
    test_fuzz(rnd, a.fuzz)
    print("5. C-12 closing state (fixed scenario)")
    test_c12_scenario()
    print(f"\n{PASSES[0]} checks passed, {len(FAILS)} failed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
