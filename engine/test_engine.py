"""Tests for the Harvestly v3 engine.  Run:  python3 -m unittest -v test_engine"""
import math
import os
import unittest
from datetime import date, timedelta

import harvestly_engine as H

D0 = date(2026, 10, 12)
T65 = (65 - 32) * 5 / 9          # 65 F in C (a table row)
PLACES = {"stockist": "SAMPLE Agrovet, Kitale (KES 300)",
          "warehouse": "SAMPLE certified store, Kitale",
          "checkpoint": "SAMPLE co-op depot, Kitale"}


def fc(today, n=7, t=18.0, rh=70.0, rain=0.0, prob=None):
    """Forecast starting tomorrow."""
    return [H.WeatherDay(today + timedelta(days=k + 1), t, rh, rain, prob) for k in range(n)]


def batch(storage="sack", since=D0, **kw):
    return H.Batch("B1", "Kitale", storage, since, **kw)


def ev(b, today=D0, rain24=None, meta=None, **kw):
    return H.evaluate(b, today, fc(today, **kw), PLACES, rain24, meta)


def reply(b, text, today=D0, **kw):
    return H.respond(b, text, today, fc(today, **kw), PLACES)[1]


def run_days(b, start, n, t=18.0, rh=70.0, rain24=None):
    """Advance + evaluate for days start+1 .. start+n; returns [(offset, code, level)]."""
    out = []
    for k in range(1, n + 1):
        day = start + timedelta(days=k)
        H.advance_day(b, H.WeatherDay(day, t, rh))
        a, d = ev(b, day, rain24, t=t, rh=rh)
        out.append((k, a.code if a else None, d["level"]))
    return out


# ---------------------------------------------------------------- tables and physics
class Tables(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(len(H.EMC_TABLE), len(H.EMC_TEMPS_F))
        self.assertTrue(all(len(r) == len(H.EMC_RH) for r in H.EMC_TABLE))
        self.assertEqual(len(H.AST_TABLE), len(H.AST_TEMPS_F))
        self.assertTrue(all(len(r) == len(H.AST_MC) for r in H.AST_TABLE))

    def test_source_spot_cells(self):
        # corners and centre cells, FSA1074 Table A and FSA1058 Table 1
        self.assertEqual(H.EMC_TABLE[0][0], 9.3)
        self.assertEqual(H.EMC_TABLE[-1][-1], 17.9)
        self.assertEqual(H.EMC_TABLE[6][9], 15.3)     # 65 F, 70 %
        self.assertEqual(H.AST_TABLE[0][0], 2126)
        self.assertEqual(H.AST_TABLE[-1][-1], 3)
        self.assertEqual(H.AST_TABLE[6][4], 11)       # 65 F, 23 %

    def test_monotonic(self):
        for row in H.EMC_TABLE:
            self.assertTrue(all(a < b for a, b in zip(row, row[1:])))
        for j in range(len(H.EMC_RH)):
            col = [r[j] for r in H.EMC_TABLE]
            self.assertTrue(all(a >= b for a, b in zip(col, col[1:])))
        for row in H.AST_TABLE:
            self.assertTrue(all(a > b for a, b in zip(row, row[1:])))
        for j in range(len(H.AST_MC)):
            col = [r[j] for r in H.AST_TABLE]
            self.assertTrue(all(a >= b for a, b in zip(col, col[1:])))

    def test_grid_points_exact(self):
        self.assertAlmostEqual(H.emc(T65, 70)[0], 15.3, places=9)
        self.assertAlmostEqual(H.ast_days(T65, 23)[0], 11, places=9)
        self.assertAlmostEqual(H.ast_days((60 - 32) * 5 / 9, 15)[0], 275, places=9)

    def test_interpolation_inside_cell(self):
        self.assertTrue(22 < H.ast_days((67.5 - 32) * 5 / 9, 18)[0] < 66)
        self.assertTrue(15.0 < H.emc((67.5 - 32) * 5 / 9, 72.5)[0] < 16.3)

    def test_flags(self):
        d, w = H.ast_days(18.0, 13.0)
        self.assertIn("AST moisture extrapolated", w)
        self.assertGreater(d, H.ast_days(18.0, 15.0)[0])
        d, w = H.ast_days(27.0, 20.0)
        self.assertIn("AST temperature extrapolated", w)
        self.assertLess(d, H.ast_days(23.0, 20.0)[0])
        self.assertLessEqual(H.ast_days(10.0, 8.0)[0], H.MAX_AST_DAYS)
        v, w = H.emc(18, 97)
        self.assertIn("EMC humidity clamped", w)
        self.assertAlmostEqual(v, H.emc(18, 90)[0])

    def test_reference_values_quoted_in_concept_note(self):
        self.assertAlmostEqual(H.emc(18.3, 63)[0], 14.1, delta=0.05)    # Kitale October normal
        self.assertAlmostEqual(H.emc(18.3, 85)[0], 18.6, delta=0.05)
        self.assertAlmostEqual(H.ast_days(18, 15)[0], 213, delta=1)
        self.assertAlmostEqual(H.ast_days(18, 19)[0], 30, delta=1)
        self.assertAlmostEqual(H.ast_days(18, 23)[0], 11, delta=0.5)


class Simulation(unittest.TestCase):
    def test_sack_drifts_toward_emc(self):
        b = batch(); b.record_meter(D0, 14.0)
        target = H.emc(18, 88)[0]
        for k in range(30):
            H.advance_day(b, H.WeatherDay(D0 + timedelta(k), 18, 88))
        self.assertTrue(14.0 < b.moisture < target)

    def test_hermetic_and_drying_hold_moisture(self):
        for s in ("hermetic", "drying"):
            b = batch(s); b.record_meter(D0, 13.0)
            for k in range(30):
                H.advance_day(b, H.WeatherDay(D0 + timedelta(k), 18, 90))
            self.assertEqual(b.moisture, 13.0)

    def test_life_used_sums_reciprocals(self):
        b = batch("drying"); b.record_meter(D0, 23.0)
        for k in range(11):
            H.advance_day(b, H.WeatherDay(D0 + timedelta(k), T65, 80))
        self.assertAlmostEqual(b.life_used, 1.0, places=9)

    def test_advance_is_idempotent(self):
        b = batch("drying"); b.record_meter(D0, 23.0)
        w = H.WeatherDay(D0, T65, 80)
        H.advance_day(b, w); H.advance_day(b, w)
        self.assertAlmostEqual(b.life_used, 1 / 11, places=9)

    def test_untested_batch_is_not_simulated(self):
        b = batch()
        H.advance_day(b, H.WeatherDay(D0, 18, 90))
        self.assertEqual((b.moisture, b.life_used), (None, 0.0))
        self.assertIsNone(H.days_left(b, fc(D0)))

    def test_days_left(self):
        b = batch("drying"); b.record_meter(D0, 23.0)
        self.assertEqual(H.days_left(b, fc(D0, t=T65, rh=80)), 11)
        b.life_used = 1.2
        self.assertEqual(H.days_left(b, fc(D0)), 0)
        self.assertIsNone(H.days_left(b, []))

    def test_input_validation(self):
        b = batch()
        with self.assertRaises(ValueError):
            b.record_meter(D0, 55)
        with self.assertRaises(ValueError):
            b.record_hygro(D0, 104, 18)
        with self.assertRaises(ValueError):
            batch("bucket")
        with self.assertRaises(ValueError):
            batch(lang="fr")

    def test_hygrometer_uses_emc_and_offset(self):
        b = batch(); b.record_hygro(D0, 60, 18)
        self.assertAlmostEqual(b.moisture, H.emc(18, 60)[0])
        b.record_hygro(D0, 56, 18, offset=4)
        self.assertAlmostEqual(b.moisture, H.emc(18, 60)[0])
        self.assertEqual(b.source, "hygro")

    def test_first_test_starts_the_clock(self):
        b = batch(); b.record_salt(D0, sticky=True)
        self.assertEqual(b.last_advanced, D0 - timedelta(1))

    def test_weaker_test_does_not_overwrite_recent_reading(self):
        b = batch(); b.record_meter(D0, 13.1)
        self.assertFalse(b.record_salt(D0 + timedelta(2), sticky=False))
        self.assertEqual((b.source, b.test_value), ("meter", 13.1))
        self.assertTrue(b.record_salt(D0 + timedelta(2), sticky=True))     # conservative result wins
        self.assertEqual(b.source, "salt_sticky")
        b = batch(); b.record_meter(D0, 13.1)
        self.assertTrue(b.record_salt(D0 + timedelta(8), sticky=False))    # old reading: accept


# ---------------------------------------------------------------- the advice function
class Advice(unittest.TestCase):
    def test_table(self):
        cases = [
            ("sack", None, None, 0.0, "TEST_FIRST"),
            ("sack", "salt_sticky", None, 0.0, "DRY_NOW"),
            ("drying", "salt_flows", None, 0.0, "NEARLY_DRY"),
            ("sack", "meter", 14.2, 0.0, "NEARLY_DRY"),
            ("sack", "meter", 13.5, 0.0, "READY_TO_STORE"),
            ("hermetic", "meter", 13.8, 0.0, None),
            ("hermetic", "meter", 14.0, 0.0, "OPEN_AND_DRY"),
            ("hermetic", "salt_sticky", None, 0.0, "OPEN_AND_DRY"),
            ("hermetic", "salt_flows", None, 0.0, "CONFIRM_DRY"),
            ("sack", "meter", 13.0, 0.85, "SORT_AND_SELL"),
            ("hermetic", "salt_sticky", None, 0.9, "SORT_AND_SELL"),
        ]
        for storage, src, val, life, want in cases:
            b = batch(storage, life_used=life)
            if src == "meter":
                b.record_meter(D0, val)
            elif src:
                b.record_salt(D0, sticky=(src == "salt_sticky"))
            self.assertEqual(H.advice(b), want, (storage, src, val, life))

    def test_drift_means_retest_not_dry_now(self):
        b = batch(); b.record_meter(D0, 13.0)
        b.moisture = 15.6                       # within the 1-point margin: no re-test yet
        self.assertEqual(H.advice(b), "NEARLY_DRY")
        b.moisture = 16.2                       # estimate well past the salt line, test said dry
        self.assertEqual(H.advice(b), "RETEST")
        b = batch(); b.record_salt(D0, sticky=True)
        b.moisture = 13.8                       # wet by test, estimate has dried well below 15 %
        self.assertEqual(H.advice(b), "RETEST")

    def test_rewetted_then_sealed_needs_confirmation(self):
        b = batch(); b.record_meter(D0, 13.0)
        b.moisture = 14.6
        b.set_storage(D0 + timedelta(30), "hermetic")
        self.assertEqual(H.advice(b), "CONFIRM_DRY")   # not "open the bags" on an estimate


# ---------------------------------------------------------------- evening decisions
class Evening(unittest.TestCase):
    def test_forecast_must_start_tomorrow(self):
        with self.assertRaises(ValueError):
            H.evaluate(batch(), D0, [H.WeatherDay(D0, 18, 70)])
        with self.assertRaises(ValueError):
            H.evaluate(batch(), D0, [])

    def test_untested_spacing_and_cap(self):
        b = batch()
        codes = [ev(b, D0 + timedelta(k))[0] for k in range(20)]
        codes = [a.code if a else None for a in codes]
        self.assertEqual(codes.count("TEST_FIRST"), H.TEST_REMINDERS_MAX)
        self.assertEqual(codes[:4], ["TEST_FIRST", None, None, "TEST_FIRST"])

    def test_rain_alert_needs_drying_and_wet_grain(self):
        b = batch("drying"); b.record_salt(D0, sticky=True)
        a, _ = ev(b, rain24=(8.0, 80.0))
        self.assertEqual(a.code, "RAIN_COVER")
        self.assertIn("80% chance", a.text)
        b = batch("drying"); b.record_meter(D0, 13.0)          # dry grain: no rain nagging
        self.assertIsNone(ev(b, rain24=(9.0, 90.0))[0])
        b = batch("sack"); b.record_meter(D0, 13.0)
        self.assertIsNone(ev(b, rain24=(20.0, 95.0))[0])

    def test_rain_alert_only_once_farmer_is_drying(self):
        b = batch()
        self.assertEqual(reply(b, "SALT YES").code, "DRY_NOW")
        self.assertIsNone(ev(b, rain24=(10.0, 85.0))[0])               # never said they are drying
        self.assertEqual(reply(b, "DRYING", D0 + timedelta(1)).code, "THANKS")
        a, _ = ev(b, D0 + timedelta(1), rain24=(10.0, 85.0))
        self.assertEqual(a.code, "RAIN_COVER")
        self.assertIn("next 24 hours", a.text)
        a, _ = ev(batch("drying"), rain24=(10.0, 85.0))                 # untested but out drying
        self.assertEqual(a.code, "RAIN_COVER")

    def test_rain_alerts_pause_without_replies(self):
        b = batch("drying"); reply(b, "SALT NO")
        codes = [c for _, c, _ in run_days(b, D0, 30, rain24=(15.0, 90.0))]
        self.assertEqual(codes.count("RAIN_COVER"), H.RAIN_UNACKED_MAX)
        reply(b, "1", D0 + timedelta(30))
        a, _ = ev(b, D0 + timedelta(31), rain24=(15.0, 90.0))
        self.assertEqual(a.code, "RAIN_COVER")

    def test_rain_without_window_says_tomorrow(self):
        b = batch("drying"); b.record_salt(D0, sticky=True)
        a, _ = ev(b, rain=9.0, prob=None)
        self.assertIn("tomorrow (9 mm expected)", a.text)

    def test_morning_reply_does_not_block_evening_rain_alert(self):
        b = batch("drying")
        self.assertEqual(reply(b, "SALT YES").code, "DRY_NOW")
        self.assertEqual(ev(b, rain24=(12.0, 90.0))[0].code, "RAIN_COVER")

    def test_dry_now_escalation_and_capped_repeats(self):
        b = batch()
        reply(b, "SALT YES")
        res = run_days(b, D0, 40, t=20, rh=92)
        sent = [k for k, c, _ in res if c == "DRY_NOW"]
        self.assertTrue(sent)
        self.assertLessEqual(len(sent), H.REPEAT_MAX + 2)     # escalations + capped repeats
        self.assertTrue(all(b2 - b1 >= H.REMIND_GAP_DAYS for b1, b2 in zip(sent, sent[1:])), sent)

    def test_estimate_never_declares_grain_dry(self):
        b = batch(); reply(b, "METER 14.2", rh=60)
        run_days(b, D0, 40, t=21, rh=50)
        self.assertLess(b.moisture, 13.5)
        self.assertEqual(H.advice(b), "NEARLY_DRY")                     # not READY_TO_STORE
        b = batch(); reply(b, "METER 13.0", rh=60)
        run_days(b, D0, 30, t=19, rh=92)
        run_days(b, D0 + timedelta(30), 30, t=21, rh=45)
        self.assertEqual(reply(b, "SEALED", D0 + timedelta(61)).code, "CONFIRM_DRY")

    def test_honest_salt_farmer_in_wet_season_is_not_looped(self):
        b = batch(); reply(b, "SALT NO")
        retests = 0
        for k in range(1, 61):
            day = D0 + timedelta(k)
            H.advance_day(b, H.WeatherDay(day, 19, 92))
            a, _ = ev(b, day, t=19, rh=92)
            if a and a.code == "RETEST":
                retests += 1
                reply(b, "SALT NO", day + timedelta(1), t=19, rh=92)
        self.assertGreaterEqual(retests, 1)
        self.assertLessEqual(retests, 2 * H.RETEST_PER_30_DAYS)

    def test_salt_no_is_accepted_when_we_asked_for_it(self):
        b = batch(); reply(b, "METER 14.0")
        run_days(b, D0, 6, t=19, rh=92)
        self.assertGreater(b.moisture, 15.0)          # estimate past the salt line within 7 days
        cmd, _ = H.respond(b, "SALT NO", D0 + timedelta(6), fc(D0 + timedelta(6)))
        self.assertEqual(cmd, "SALT_NO")

    def test_escalation_after_a_reply_is_not_lost(self):
        b = batch(); reply(b, "SALT YES", rh=63)
        self.assertEqual(b.told_level, "LOW")
        res = run_days(b, D0, 8, rh=90)
        first = next((k, c, lv) for k, c, lv in res if c)
        self.assertEqual(first[1:], ("DRY_NOW", "MEDIUM"))

    def test_no_message_when_nothing_changed(self):
        b = batch(); reply(b, "METER 13.0", rh=60)
        res = run_days(b, D0, 10, rh=60)
        self.assertTrue(all(c is None for _, c, _ in res), res)

    def test_drifting_dry_grain_gets_retest_once_then_capped(self):
        b = batch(); reply(b, "METER 13.0", rh=60)
        res = run_days(b, D0, 60, t=19, rh=92)
        codes = [c for _, c, _ in res if c]
        self.assertEqual(codes[0], "RETEST")
        self.assertNotIn("DRY_NOW", codes)                      # never orders drying on an estimate
        self.assertLessEqual(codes.count("RETEST"), H.REPEAT_MAX + 2)

    def test_retest_text_never_claims_a_reading(self):
        b = batch(); reply(b, "METER 13.0", rh=60)
        res = run_days(b, D0, 60, t=19, rh=92)
        k = next(k for k, c, _ in res if c == "RETEST")
        b2 = batch(); reply(b2, "METER 13.0", rh=60)
        run_days(b2, D0, k - 1, t=19, rh=92)
        day = D0 + timedelta(k)
        H.advance_day(b2, H.WeatherDay(day, 19, 92))
        a, _ = ev(b2, day, t=19, rh=92)
        self.assertEqual(a.code, "RETEST")
        self.assertIn("estimate", a.text)
        self.assertNotIn("meter 13.0", a.text)

    def test_hermetic_wet_and_salt_only_are_not_silenced(self):
        b = batch("hermetic"); reply(b, "SALT YES")
        res = run_days(b, D0, 120, t=20, rh=70)
        codes = [c for _, c, _ in res if c]
        self.assertIn("OPEN_AND_DRY", codes)                     # reminders after the reply
        self.assertIn("SORT_AND_SELL", codes)                    # still reachable
        b = batch("hermetic"); reply(b, "SALT NO")
        codes = [c for _, c, _ in run_days(b, D0, 30) if c]
        self.assertEqual(codes.count("CONFIRM_DRY"), H.REPEAT_MAX)

    def test_sort_and_sell_once(self):
        b = batch("hermetic", life_used=0.85); b.record_meter(D0 - timedelta(5), 13.0)
        a, d = ev(b, rh=60)
        self.assertEqual((a.code, d["level"]), ("SORT_AND_SELL", "HIGH"))
        codes = [c for _, c, _ in run_days(b, D0, 10, rh=60)]
        self.assertEqual(codes[:6], [None] * 6)                  # nothing for a week ...
        self.assertEqual(codes[6], "HIGH_ALERT")                  # ... then the spaced, escalated reminder

    def test_insect_reminder_only_for_dry_grain_in_open_storage(self):
        b = batch("sack", since=D0 - timedelta(50)); b.record_meter(D0 - timedelta(10), 13.0)
        b.last_advice = "READY_TO_STORE"
        self.assertEqual(ev(b, rh=55)[0].code, "INSECT_REMINDER")
        self.assertIsNone(ev(b, D0 + timedelta(1), rh=55)[0])
        for storage, val in (("sack", 16.0), ("hermetic", 13.0)):
            b = batch(storage, since=D0 - timedelta(80)); b.record_meter(D0 - timedelta(10), val)
            b.last_advice = H.advice(b)
            a, _ = ev(b, rh=55)
            self.assertTrue(a is None or a.code != "INSECT_REMINDER", (storage, val))

    def test_one_proactive_message_per_day(self):
        b = batch(); b.record_salt(D0, sticky=True)
        self.assertIsNotNone(ev(b)[0])
        self.assertIsNone(ev(b)[0])

    def test_closed_and_stopped_batches_are_silent(self):
        for word in ("SOLD", "STOP", "NIMEUZA", "SIMAMISHA"):
            b = batch(); b.record_salt(D0, sticky=True)
            reply(b, word)
            self.assertIsNone(ev(b)[0])

    def test_kiswahili_farmer_gets_kiswahili(self):
        b = batch(lang="sw")
        a = reply(b, "CHUMVI NDIYO")
        self.assertTrue(a.text.startswith("Harvestly: Mahindi yako"))
        self.assertTrue(a.other.startswith("Harvestly: Your maize"))


# ---------------------------------------------------------------- replies
class Replies(unittest.TestCase):
    def test_parsing(self):
        b = batch()
        cases = [("salt yes", "SALT_YES"), ("  Chumvi   ndiyo ", "SALT_YES"), ("CHUMVI NDIO", "SALT_YES"),
                 ("SALT YES.", "SALT_YES"), ("SALT NO", "SALT_NO"), ("chumvi hapana", "SALT_NO"),
                 ("METER 13,4", "METER"), ("mita 14.0%", "METER"), ("METER 13.5 %", "METER"),
                 ("HYGRO 62 18", "HYGRO"), ("hygro 62% 18c", "HYGRO"), ("HYGRO 60 20°C", "HYGRO"),
                 ("SEALED", "STORAGE"), ("magunia", "STORAGE"), ("1", "ACK"), ("hello", "UNKNOWN"),
                 ("SALT MAYBE", "UNKNOWN"), ("METER 135", "INVALID"), ("METER 4", "INVALID"),
                 ("HYGRO 100 20", "INVALID")]
        for text, want in cases:
            self.assertEqual(H.apply_reply(b, text, D0, temp_hint=18), want, text)
        self.assertEqual(H.apply_reply(b, "HYGRO 60", D0), "INVALID")    # no temperature at all

    def test_e5_01_ranges_and_negatives_never_record_a_reading(self):
        """E5-01: 'METER 13-15', 'meter 13 / 15' and 'METER -13' used to record 13 (dry). One number only."""
        for text in ("METER 13-15", "meter 13 / 15", "METER -13", "METER \u221213", "MITA 13\u201415", "METER 13 15",
                     "METER 13.5 and 14", "METER", "METER .5", "METER ,5", "MITA .5", "HYGRO .5 20", "HYGRO 62 -5", "HYGRO 62 18 20", "hygro 60-70 20"):
            b = batch("drying")
            before = (b.moisture, b.source)
            self.assertEqual(H.apply_reply(b, text, D0, temp_hint=18), "INVALID", text)
            self.assertEqual((b.moisture, b.source), before, text)
            self.assertEqual(reply(batch("drying"), text).code, "HELP", text)
        for text, mc in (("METER 13.2", 13.2), ("meter 13,5%", 13.5), ("Meter13.2%", 13.2), ("MITA 14", 14.0)):
            b = batch("drying")
            self.assertEqual(H.apply_reply(b, text, D0), "METER", text)
            self.assertAlmostEqual(b.moisture, mc)
        self.assertEqual(H.apply_reply(batch(), "METERS 13", D0), "UNKNOWN")

    def test_invalid_and_unknown_get_help_not_a_crash(self):
        b = batch()
        for text in ("METER 135", "hello", "HYGRO 100 20"):
            self.assertEqual(reply(b, text).code, "HELP")

    def test_reply_to_a_test_answers_the_test_even_when_raining(self):
        b = batch("drying")
        a = reply(b, "SALT NO", rain=20.0, prob=95.0)
        self.assertEqual(a.code, "NEARLY_DRY")
        a = reply(b, "METER 13.2", rain=20.0, prob=95.0)
        self.assertEqual(a.code, "READY_TO_STORE")
        self.assertIn("meter 13.2%", a.text)

    def test_status_only_when_safe(self):
        b = batch("hermetic"); b.record_meter(D0, 17.0)
        self.assertEqual(reply(b, "SEALED").code, "OPEN_AND_DRY")
        b = batch("hermetic"); b.record_meter(D0, 13.2)
        a = reply(b, "SEALED")
        self.assertEqual(a.code, "STATUS")
        self.assertIn("meter 13.2%", a.text)                     # hermetic: no drift, still the reading
        self.assertEqual(reply(b, "1").code, "THANKS")

    def test_no_forecast_no_false_countdown(self):
        b = batch()
        _, a = H.respond(b, "SALT YES", D0, [])
        self.assertIn("not available today", a.text)
        b = batch("hermetic")
        _, a = H.respond(b, "METER 13.0", D0, [])
        self.assertIn("not available today", a.text)
        self.assertNotIn("safe", a.text.lower())

    def test_closed_batch_replies_closed_until_restarted(self):
        b = batch(); reply(b, "SALT YES")
        self.assertEqual(reply(b, "SOLD").code, "CLOSED")
        self.assertEqual(reply(b, "SALT YES").code, "CLOSED")
        self.assertEqual(reply(b, "START").code, "DRY_NOW")

    def test_duplicate_reply_gets_thanks(self):
        b = batch()
        self.assertEqual(reply(b, "salt no").code, "NEARLY_DRY")
        self.assertEqual(reply(b, "Salt No!").code, "THANKS")

    def test_loose_spelling(self):
        b = batch()
        for text, want in [("SALTYES", "SALT_YES"), ("Salt-yes", "SALT_YES"), ("meter13.2", "METER"),
                           ("drying now", "STORAGE"), ("Sealed bags", "STORAGE"), ("ok", "ACK"),
                           ("Asante", "ACK"), ("METER 13.2 thanks", "INVALID")]:   # E5-01: one number, nothing else
            self.assertEqual(H.apply_reply(b, text, D0, 18), want, text)

    def test_loaded_batch_state(self):
        b = batch(moisture=16.0, source="meter")
        self.assertEqual(b.test_value, 16.0)
        with self.assertRaises(ValueError):
            batch(moisture=16.0)

    def test_stop_start(self):
        b = batch(); b.record_salt(D0, sticky=True)
        self.assertEqual(reply(b, "STOP").code, "STOPPED")
        self.assertIsNone(H.respond(b, "SALT YES", D0, fc(D0))[1])
        self.assertEqual(reply(b, "ANZA").code, "DRY_NOW")

    def test_storage_change_resets_storage_date(self):
        b = batch("drying", since=D0 - timedelta(5))
        H.apply_reply(b, "SACKS", D0)
        self.assertEqual((b.storage, b.stored_since), ("sack", D0))

    def test_same_day_weaker_test_keeps_reading(self):
        b = batch()
        self.assertEqual(reply(b, "METER 13.1").code, "READY_TO_STORE")
        cmd, a = H.respond(b, "SALT NO", D0, fc(D0), PLACES)
        self.assertEqual((cmd, a.code), ("SALT_NO_IGNORED", "READY_TO_STORE"))


# ---------------------------------------------------------------- SMS limits
GSM7 = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡"
           "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
GSM7_EXT = set("^{}\\[~]|€")


def sms_segments(text):
    if any(c not in GSM7 and c not in GSM7_EXT for c in text):
        return "UCS-2", math.ceil(len(text) / (70 if len(text) <= 70 else 67))
    n = sum(2 if c in GSM7_EXT else 1 for c in text)
    return "GSM-7", 1 if n <= 160 else math.ceil(n / 153)


class SmsLimits(unittest.TestCase):
    def test_every_template_both_languages_worst_case(self):
        places = {"stockist": "X" * 32, "warehouse": "Y" * 30, "checkpoint": "Z" * 26}
        b = batch()
        for code in H.TEMPLATES:
            for src in ("meter", "hygro", "salt_flows", "salt_sticky"):
                for drift in (0.0, 1.0):
                    b.source, b.test_value, b.moisture = src, 29.9, 29.9 + drift
                    for left in (0, 1, 2, 89, 90, 365):
                        for pl in (places, None):
                            a = H.render(code, b, "HIGH", left, D0, pl, (120.0, 100.0))
                            for text in (a.text, a.other):
                                enc, seg = sms_segments(text)
                                self.assertEqual(enc, "GSM-7", (code, text))
                                self.assertLessEqual(seg, 2, (code, len(text), text))
                                self.assertFalse(set("{}") & set(text), (code, text))
                                self.assertNotIn("  ", text, (code, text))
                                self.assertNotIn(" .", text, (code, text))

    def test_directory_names_are_sanitised(self):
        b = batch(); b.record_meter(D0, 13.0)
        a = H.render("READY_TO_STORE", b, "LOW", 365, D0,
                     {"stockist": "Mama\u2019s Agrovet \u2013 Kitale town branch, Moi Avenue", "warehouse": "\u00e7\u20ac"})
        self.assertEqual(sms_segments(a.text)[0], "GSM-7")
        self.assertIn("Mama's Agrovet - Kitale town bra", a.text)
        self.assertIn("a certified warehouse", a.text)                 # unusable name -> default

    def test_generic_places_when_directory_missing(self):
        b = batch(); b.record_meter(D0, 13.0)
        a = H.render("READY_TO_STORE", b, "LOW", 365, D0, None)
        self.assertIn("an agro-dealer near you", a.text)
        self.assertIn("ghala lililoidhinishwa", a.other)


# ---------------------------------------------------------------- weather adapter + daily job
class Weather(unittest.TestCase):
    def payload(self):
        times, t, rh, p, pp = [], [], [], [], []
        for d in range(-2, 8):                  # 2 past days, today, 7 future days
            day = D0 + timedelta(d)
            for hr in range(24):
                times.append(f"{day.isoformat()}T{hr:02d}:00")
                t.append(15.0 if hr < 12 else 21.0)
                rh.append(90 if d >= 3 else 60)
                p.append(0.5 if (d == 1 and hr < 10) or (d == 0 and hr >= 20) else 0.0)
                pp.append(None if d >= 6 else (85 if (d == 1 and hr == 23) else 20))
        times.append(f"{(D0 + timedelta(8)).isoformat()}T00:00")   # partial trailing day
        for arr, v in ((t, 18.0), (rh, 70), (p, 0.0), (pp, None)):
            arr.append(v)
        return {"hourly": {"time": times, "temperature_2m": t, "relative_humidity_2m": rh,
                           "precipitation": p, "precipitation_probability": pp}}

    def test_daily_aggregation(self):
        days = H.daily_from_open_meteo(self.payload())
        self.assertEqual(len(days), 10)                       # partial day dropped
        tomorrow = [d for d in days if d.day == D0 + timedelta(1)][0]
        self.assertAlmostEqual(tomorrow.temp_c, 18.0)
        self.assertAlmostEqual(tomorrow.rain_mm, 5.0)
        self.assertEqual(tomorrow.rain_prob, 85)
        self.assertIsNone(days[-1].rain_prob)                 # no ensemble data -> None, not 0

    def test_missing_precipitation_is_unknown_not_zero(self):
        pl = self.payload()
        del pl["hourly"]["precipitation"]
        self.assertTrue(all(d.rain_mm is None for d in H.daily_from_open_meteo(pl)))

    def test_missing_rain_is_flagged(self):
        b = batch("drying"); b.record_salt(D0, sticky=True)
        a, d = ev(b, rain24=(None, None), rain=None)
        self.assertIn("rain data missing", d["flags"])

    def test_rain_window_includes_tonight(self):
        pl = self.payload()
        mm, prob = H.rain_next_hours(pl, f"{D0.isoformat()}T17:00", 24)
        self.assertAlmostEqual(mm, 4 * 0.5 + 10 * 0.5)       # 20:00-23:00 today + 00:00-09:00 tomorrow
        self.assertEqual(prob, 20)                            # the 85 % hour (23:00 tomorrow) is outside
        self.assertEqual(H.rain_next_hours(pl, "1999-01-01T00:00"), (None, None))

    def test_split_is_today_vs_future(self):
        past, forecast = H.split_weather(H.daily_from_open_meteo(self.payload()), D0)
        self.assertEqual(max(past), D0)
        self.assertEqual(forecast[0].day, D0 + timedelta(1))
        self.assertEqual(len(forecast), 7)

    def test_url(self):
        u = H.open_meteo_url(1.0157, 35.0062)
        self.assertTrue(u.startswith("https://api.open-meteo.com/v1/forecast?"))
        self.assertIn("past_days=2", u)
        self.assertIn("forecast_days=8", u)

    def test_daily_run_catches_up_and_reports_gaps(self):
        pl = self.payload()
        days = H.daily_from_open_meteo(pl)
        b = batch("drying"); b.record_salt(D0 - timedelta(4), sticky=True)
        a, d = H.daily_run(b, D0, days, PLACES, H.rain_next_hours(pl, f"{D0.isoformat()}T17:00"))
        self.assertEqual(b.last_advanced, D0)
        self.assertEqual(d["missing_days"], [D0 - timedelta(4), D0 - timedelta(3)])
        self.assertEqual(a.code, "RAIN_COVER")                # 7 mm in the next 24 h while drying
        life = b.life_used
        H.daily_run(b, D0, days, PLACES)                      # re-run the same evening
        self.assertEqual(b.life_used, life)

    def test_daily_run_handles_batch_loaded_without_clock(self):
        days = H.daily_from_open_meteo(self.payload())
        b = batch(moisture=18.0, source="salt_sticky", test_value=18.0, last_test=D0 - timedelta(2))
        H.daily_run(b, D0, days, PLACES)
        self.assertGreater(b.life_used, 0)
        self.assertEqual(b.last_advanced, D0)

    def test_daily_run_needs_tomorrow(self):
        days = [d for d in H.daily_from_open_meteo(self.payload()) if d.day != D0 + timedelta(1)]
        with self.assertRaises(ValueError):
            H.daily_run(batch(), D0, days)


# ---------------------------------------------------------------- the pitch demo, end to end
class DemoScript(unittest.TestCase):
    def test_pitch_walkthrough(self):
        b = H.Batch("DEMO", "Kitale", "sack", D0, lang="en", bags=10)
        self.assertEqual(ev(b, rh=63)[0].code, "TEST_FIRST")              # 1. registered: test first
        a = reply(b, "SALT YES", rh=63)
        self.assertEqual(a.code, "DRY_NOW")                                # 2. too wet
        self.assertIn("3 months or more", a.text)                                   #    normal weather: low risk
        res = run_days(b, D0, 7, rh=88)                                    # 3. simulated El Nino week
        alert = [(k, c, lv) for k, c, lv in res if c]
        self.assertEqual(alert[0][1:], ("DRY_NOW", "MEDIUM"))               #    countdown alert fires
        day = D0 + timedelta(8)
        self.assertEqual(reply(b, "DRYING", day, rh=88).code, "THANKS")   #    farmer starts drying
        a, _ = ev(b, day, rain24=(12.0, 80.0), rh=88)
        self.assertEqual(a.code, "RAIN_COVER")                             # 4. rain tonight: cover it
        day += timedelta(2)
        self.assertEqual(reply(b, "SALT NO", day, rh=60).code, "NEARLY_DRY")   # 5. salt passes
        a = reply(b, "METER 13.1", day, rh=60)
        self.assertEqual(a.code, "READY_TO_STORE")                         # 6. confirmed: seal/deposit
        self.assertIn("SAMPLE Agrovet", a.text)
        self.assertEqual(reply(b, "SEALED", day).code, "STATUS")           # 7. sealed below 14 %: quiet


# ---------------------------------------------------------------- review R1 fixes
class Rounding(unittest.TestCase):
    """One rule everywhere: half-up on the decimal value. Checked against integer arithmetic, not against H.fmt."""

    def test_ties_that_used_to_diverge(self):
        for x, one in ((5.05, "5.1"), (13.25, "13.3"), (13.35, "13.4"), (13.45, "13.5"), (0.05, "0.1")):
            self.assertEqual(H.fmt1(x), one, x)
        for x, zero in ((0.5, "1"), (2.5, "3"), (6.5, "7"), (59.5, "60"), (1.5, "2")):
            self.assertEqual(H.fmt0(x), zero, x)

    def test_every_meter_reading_5_to_40(self):
        for h in range(500, 4001):                                    # hundredths, exact integers
            x = h / 100
            tenths = (h + 5) // 10                                     # half-up in integer arithmetic
            self.assertEqual(H.fmt1(x), f"{tenths // 10}.{tenths % 10}", x)
            self.assertEqual(H.fmt2(x), f"{h // 100}.{h % 100:02d}", x)

    def test_diag_uses_the_same_rule(self):
        b = batch("hermetic"); b.record_meter(D0, 13.25)
        _, d = ev(b)
        self.assertEqual(d["moisture"], 13.3)

    def test_two_decimals_next_to_a_limit(self):
        b = batch(); b.record_meter(D0, 13.54)
        self.assertEqual(H._evidence(b, "en"), "meter 13.54%")        # not 'meter 13.5%' beside 'the limit is 13.5%'
        b.record_meter(D0, 13.5); self.assertEqual(H._evidence(b, "en"), "meter 13.5%")
        b.record_meter(D0, 13.3); self.assertEqual(H._evidence(b, "en"), "meter 13.3%")
        b.record_meter(D0, 13.96); self.assertEqual(H._evidence(b, "sw"), "mita 13.96%")


class OptOut(unittest.TestCase):
    def test_vocabulary_case_insensitive(self):
        for t in ("STOP", "stop", "Stop.", "UNSUBSCRIBE", "cancel", "End", "QUIT", "acha", "SITISHA", "simamisha",
                  "PLEASE STOP", "please stop!", "Tafadhali acha", "STOP ALL", "stop\u00a0now"):
            self.assertTrue(H.is_optout(H.normalise(t)), t)
            self.assertEqual(H.apply_reply(batch(), t, D0), "STOP", t)
        for t in ("METER 13.5", "ENDING", "hello", "", "PLEASE", "SALT YES"):
            self.assertFalse(H.is_optout(H.normalise(t)), t)

    def test_r1_04_stop_anywhere_in_a_short_message(self):
        for t in ("I WANT TO STOP", "NO MORE", "no more please", "STOPP", "please stop sending", "OPT OUT",
                  "nisitishie", "sitaki tena", "I said stop!"):
            self.assertTrue(H.is_optout(H.normalise(t)), t)
            self.assertEqual(H.apply_reply(batch(), t, D0), "STOP", t)
        # a long message is never read as an opt-out, and commands that start a message keep their meaning
        long_text = "the rain came and the maize is wet so what should I do now and when can I stop"
        self.assertFalse(H.is_optout(H.normalise(long_text)))
        for t in ("METER 13.5", "SALT YES", "SALT NO", "HYGRO 62 18"):
            self.assertNotEqual(H.apply_reply(batch(), t, D0), "STOP", t)
        self.assertEqual(H.apply_reply(batch(), "SEALED STOP", D0), "STOP")   # opt-out wins over a storage word

    def test_c14_ascii_only_digits_and_boundaries(self):
        b = batch()
        self.assertEqual(H.apply_reply(b, "METER \u0661\u0663.\u0665", D0), "INVALID")      # Arabic-Indic digits
        self.assertEqual(H.apply_reply(batch(), "SALT YES\u00c9", D0), "SALT_YES")          # same as Oracle's [^A-Z0-9_]
        self.assertEqual(H.normalise_address("0712\u0663\u0664\u0665678"), "0712678")      # no unicode digits kept as digits

    def test_stop_applies_to_every_batch_of_the_phone_and_cancels_the_queue(self):
        bs = [batch(), batch("hermetic"), batch("drying")]
        bs[2].status = "closed"
        queue = [{"status": "QUEUED"}, {"status": "SENT"}, {"status": "QUEUED"}]
        self.assertEqual(H.stop_phone(bs, queue), 2)
        self.assertEqual([b.status for b in bs], ["stopped", "stopped", "closed"])
        self.assertEqual([m["status"] for m in queue], ["CANCELLED", "SENT", "CANCELLED"])
        self.assertEqual(H.start_phone(bs), 2)
        self.assertEqual([b.status for b in bs], ["active", "active", "closed"])

    def test_a_stopped_phone_is_not_sent_to(self):
        out = {H.address_hash("0712 345 678", "p")}
        self.assertFalse(H.may_send("+254712345678", out, "p"))
        self.assertFalse(H.may_send("254712345678", out, "p"))
        self.assertTrue(H.may_send("+254700000000", out, "p"))
        self.assertTrue(H.may_send("+254712345678", out, "other-pepper"))

    def test_hash_is_not_the_number(self):
        h = H.address_hash("+254712345678", "p")
        self.assertEqual(len(h), 64)
        self.assertNotIn("254712345678", h)

    def test_start_after_stop_charges_the_paused_days(self):
        b = batch(); b.record_meter(D0, 14.0)
        for k in range(1, 3):
            H.advance_day(b, H.WeatherDay(D0 + timedelta(k), 18.0, 70.0))
        life = b.life_used
        H.apply_reply(b, "STOP", D0 + timedelta(2))
        self.assertEqual(H.apply_reply(b, "START", D0 + timedelta(92)), "START")
        wl = [H.WeatherDay(D0 + timedelta(92 + k), 18.0, 70.0) for k in range(-2, 8)]
        a, d = H.daily_run(b, D0 + timedelta(92), wl, PLACES)
        self.assertGreater(b.life_used, life + 80 * 0.0005)            # 90 paused days were charged
        self.assertGreater(len(d["missing_days"]), 80)                  # and reported as nearest-weather days


class HighIsNeverSilent(unittest.TestCase):
    def test_dry_grain_rewets_never_goes_quiet_while_high(self):
        b = batch(); b.record_meter(D0, 13.0)
        sent, quiet = [], 0
        worst_quiet = 0
        for k in range(1, 71):
            day = D0 + timedelta(k)
            H.advance_day(b, H.WeatherDay(day, 19.0, 92.0))
            a, d = ev(b, day, t=19.0, rh=92.0)
            if a: sent.append((k, a.code)); quiet = 0
            elif d["level"] == "HIGH" and b.count_sent("HIGH_ALERT") < H.HIGH_ALERT_MAX: quiet += 1; worst_quiet = max(worst_quiet, quiet)
        self.assertLessEqual(worst_quiet, 6)                            # at most weekly
        self.assertLessEqual(b.count_sent("HIGH_ALERT"), H.HIGH_ALERT_MAX)  # and capped
        self.assertIn("SORT_AND_SELL", [c for _, c in sent])
        self.assertTrue(any(c == "HIGH_ALERT" for _, c in sent))
        self.assertLess(sum(c == "RETEST" for _, c in sent), 3)          # the per-code cap still holds

    def test_c12_closing_state_after_the_last_high_alert(self):
        """R2 C-12: 4th HIGH_ALERT is the last-chance message, then silence ON PURPOSE, flagged, until a new test."""
        b = batch(); b.record_meter(D0, 13.0); b.life_used = 1.3
        texts, last_k = [], None
        for k in range(1, 61):
            day = D0 + timedelta(k)
            H.advance_day(b, H.WeatherDay(day, 19.0, 92.0))
            al, d = ev(b, day, t=19.0, rh=92.0)
            if al and al.code == "HIGH_ALERT":
                texts.append(al.text); last_k = k
            elif last_k and k > last_k:
                self.assertIsNone(al)                                     # nothing more is sent ...
        self.assertEqual(len(texts), H.HIGH_ALERT_MAX)
        self.assertNotIn("last reminder", texts[-2])
        self.assertIn("last reminder", texts[-1])
        self.assertIn("Retest", texts[-1])                           # tells the farmer how to restart
        self.assertLess(last_k, 55)
        day = D0 + timedelta(59)
        a, d = ev(b, day + timedelta(1), t=19.0, rh=92.0)
        self.assertIn("high alerts used up", d["flags"])                  # ... and the state is explicit
        b.record_meter(day + timedelta(1), 15.0)                          # a new test restarts the count
        self.assertEqual(b.count_sent("HIGH_ALERT", b.last_test), 0)

    def test_c12_last_reminder_fits_two_segments_in_the_worst_case(self):
        b = batch(); b.record_meter(D0, 13.0)
        b.sent = [(D0, "HIGH_ALERT")] * 3
        for left in (None, 0, 1, 14, 30, 89, 90, 365):
            for lang in ("en", "sw"):
                b.lang = lang
                a = H.render("HIGH_ALERT", b, "HIGH", left, D0, None)
                self.assertIn("MITA" if lang == "sw" else "METER", a.text)
                self.assertLessEqual(sms_segments(a.text)[1], 2, (left, lang, len(a.text)))
                self.assertLessEqual(sms_segments(a.other)[1], 2, (left, lang, len(a.other)))

    def test_k01_first_message_has_no_salt_protocol_quantities(self):
        for lang in (0, 1):
            t = H.TEMPLATES["TEST_FIRST"][lang].lower()
            for banned in ("teaspoon", "vijiko", "6 hours", "saa 6", "5-10", "2-3", "glass", "kioo", "bottle", "chupa", "pan-dried"):
                self.assertNotIn(banned, t, banned)
            self.assertIn("draft", t) if lang == 0 else self.assertIn("rasimu", t)

    def test_c11_no_unverified_week_7_claim_to_farmers(self):
        for lang in (0, 1):
            t = H.TEMPLATES["INSECT_REMINDER"][lang].lower()
            self.assertNotIn("week 7", t); self.assertNotIn("wiki 7", t); self.assertNotIn("trial", t)

    def test_last_reminder_says_so_and_nothing_follows(self):
        b = batch(); b.record_meter(D0, 13.0); b.life_used = 1.3
        codes = [c for _, c, _ in run_days(b, D0, 60, t=19.0, rh=92.0) if c]
        self.assertLessEqual(codes.count("HIGH_ALERT"), H.HIGH_ALERT_MAX)
        b2 = batch(); b2.record_meter(D0, 13.0); b2.life_used = 1.3
        b2.sent = [(D0 - timedelta(30 - 7 * i), "HIGH_ALERT") for i in range(3)]; b2.last_alert = D0 - timedelta(8); b2.last_advice = "SORT_AND_SELL"; b2.last_test = D0 - timedelta(40)
        a, _ = ev(b2, D0, t=19.0, rh=92.0)
        self.assertEqual(a.code, "HIGH_ALERT")
        self.assertIn("last reminder", a.text)

    def test_demo_numbers_unchanged(self):
        import json, os
        v = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectors.json")))
        demo = next(s for s in v["scenarios"] if s["name"] == "demo_pitch")
        left = {t["day"]: t["days_left"] for t in demo["trace"] if t["event"] == "evening"}
        self.assertEqual((left["2026-10-14"], left["2026-10-15"]), (261, 34))


class Undelivered(unittest.TestCase):
    def test_skipped_evening_message_is_taken_back(self):
        b = batch("drying"); b.record_salt(D0, sticky=True)
        before = (b.last_alert, b.last_advice, b.told_level, b.told_left, list(b.sent))
        a, _ = ev(b)
        self.assertEqual(a.code, "DRY_NOW")
        self.assertEqual(b.count_sent("DRY_NOW"), 1)
        H.revert_undelivered(b, a)
        self.assertEqual((b.last_alert, b.last_advice, b.told_level, b.told_left, b.sent), before)
        a2, _ = ev(b)                                                    # so the farmer is told next time
        self.assertEqual(a2.code, "DRY_NOW")

    def test_failed_test_requests_do_not_use_up_the_cap(self):
        b = batch()
        for k in range(10):
            a, _ = ev(b, D0 + timedelta(3 * k))
            self.assertEqual(a.code, "TEST_FIRST")
            H.revert_undelivered(b, a)

    def test_skipped_reply_is_taken_back(self):
        b = batch(); _, a = H.respond(b, "SALT YES", D0, fc(D0), PLACES)
        self.assertEqual(b.last_advice, "DRY_NOW")
        H.revert_undelivered(b, a)
        self.assertIsNone(b.last_advice); self.assertEqual(b.sent, [])


class StaleWeather(unittest.TestCase):
    def test_stale_weather_is_flagged_and_never_triggers_rain(self):
        b = batch("drying"); b.record_salt(D0, sticky=True)
        fresh = H.WeatherMeta(D0, 5.0)
        old = H.WeatherMeta(D0 - timedelta(3), 72.0)
        a, d = ev(b, rain24=(12.0, 90.0), meta=fresh)
        self.assertEqual(a.code, "RAIN_COVER"); self.assertFalse(d["weather_stale"])
        b = batch("drying"); b.record_salt(D0, sticky=True)
        a, d = ev(b, rain24=(12.0, 90.0), meta=old)
        self.assertNotEqual(a.code if a else None, "RAIN_COVER")
        self.assertTrue(d["weather_stale"]); self.assertIn("weather stale", d["flags"])
        self.assertIn(f"{(D0 - timedelta(3)).strftime('%d/%m')}", a.text)   # shows the date of the DATA
        self.assertFalse(H.WeatherMeta(D0, 24.0).stale); self.assertTrue(H.WeatherMeta(D0, 24.1).stale)

    def test_demo_credit_says_simulated(self):
        b = batch("drying"); b.record_salt(D0, sticky=True)
        a, _ = ev(b, meta=H.WeatherMeta(D0, 0, "Simulated weather"))
        self.assertIn("Simulated weather", a.text); self.assertNotIn("Open-Meteo", a.text)


class InputHandling(unittest.TestCase):
    def test_long_input_is_cut_and_never_raises(self):
        for t in ("METER 13.5 " + "x" * 5000, "\U0001F600" * 3000, "A" * 100000, None, 12345, "\x00\x01\ufffe"):
            n = H.normalise(t)
            self.assertLessEqual(len(n), H.MAX_TEXT_CHARS)
            b = batch()
            _, a = H.respond(b, t, D0, fc(D0), PLACES)
            self.assertIsNotNone(a)
        self.assertEqual(H.apply_reply(batch(), "METER 13.5" + " " * 5000, D0), "METER")

    def test_unicode_spaces_are_spaces(self):
        self.assertEqual(H.normalise("METER\u00a013.5"), "METER 13.5")
        self.assertEqual(H.apply_reply(batch(), "METER\u202f13.5", D0), "METER")

    def test_places_cannot_override_template_fields(self):
        b = batch(); b.record_meter(D0, 14.0)
        a = H.render("DRY_NOW", b, "LOW", 40, D0, {"date": "XXX", "risk": "YYY", "evidence": "ZZZ"})
        self.assertNotIn("XXX", a.text); self.assertNotIn("YYY", a.text); self.assertNotIn("ZZZ", a.text)

    def test_weeks_are_capped_at_two_digits(self):
        b = batch(since=D0 - timedelta(5000)); b.record_meter(D0, 13.0)
        a = H.render("INSECT_REMINDER", b, "LOW", 200, D0)
        self.assertIn("for 99 weeks", a.text)
        for lang_text in (a.text, a.other):
            self.assertLessEqual(sms_segments(lang_text)[1], 2)

    def test_rain24_without_data_falls_back_to_tomorrow(self):
        b = batch("drying"); b.record_salt(D0, sticky=True)
        a, _ = ev(b, rain24=(None, None), rain=12.0, prob=90.0)
        self.assertEqual(a.code, "RAIN_COVER")
        self.assertIn("tomorrow", a.text)


class Idempotent(unittest.TestCase):
    def test_second_daily_run_same_day_does_nothing(self):
        b = batch(); b.record_meter(D0, 15.5)
        wl = [H.WeatherDay(D0 + timedelta(k), 18.0, 70.0) for k in range(-2, 8)]
        a1, _ = H.daily_run(b, D0, wl, PLACES)
        life, sent = b.life_used, list(b.sent)
        a2, d2 = H.daily_run(b, D0, wl, PLACES)
        self.assertIsNotNone(a1); self.assertIsNone(a2)
        self.assertEqual((b.life_used, b.sent), (life, sent))
        self.assertIn("already run today", d2["flags"])
        b.last_alert = None; H.revert_undelivered(b, a1)
        a3, _ = H.daily_run(b, D0, wl, PLACES)                           # still once per day, even after an undo
        self.assertIsNone(a3)


class WordingAndLabels(unittest.TestCase):
    def test_no_message_says_safe_or_promises(self):
        import re
        for code, pair in H.TEMPLATES.items():
            for t in pair:
                self.assertNotRegex(t.lower(), r"\bsafe\b|salama", code)
                self.assertNotRegex(t.lower(), r"we will|tutakutumia|tutakukumbusha|always|never fails", code)
        for left in (None, 0, 1, 40, 365):
            for lang in ("en", "sw"):
                self.assertNotRegex(H._risk(left, lang).lower(), r"safe|salama")

    def test_status_says_what_was_measured_and_when(self):
        b = batch("hermetic"); b.record_meter(D0, 13.1)
        _, a = H.respond(b, "SEALED", D0, fc(D0), PLACES)
        self.assertEqual(a.code, "STATUS")
        self.assertIn("meter 13.1% on 12/10", a.text)
        self.assertIn("estimate", a.text)
        self.assertIn("meter 13.1% on 12/10", a.other.replace("mita", "meter").replace("tarehe", "on"))

    def test_welcome_carries_the_credit_and_the_opt_out(self):
        a = H.welcome(batch(), D0)
        self.assertIn("Open-Meteo.com", a.text); self.assertIn("CC BY 4.0", a.text); self.assertIn("STOP", a.text)
        self.assertIn("SIMAMISHA", a.other)
        self.assertIn("Open-Meteo.com", H.ATTRIBUTION); self.assertIn("https://open-meteo.com", H.ATTRIBUTION)

    def test_worst_case_lengths_with_the_demo_credit(self):
        b = batch(); b.source, b.test_value, b.moisture = "meter", 29.9, 30.9
        for code in H.TEMPLATES:
            for left in (0, 1, 89, 365):
                a = H.render(code, b, "HIGH", left, D0, None, (120.0, 100.0), True, H.WeatherMeta(D0, 0, "Simulated weather"))
                for text in (a.text, a.other):
                    self.assertLessEqual(sms_segments(text)[1], 2, (code, len(text), text))

    def test_n5_09_every_template_in_both_languages_fits_two_segments_with_room_to_spare(self):
        """N5-09: the raw template, each placeholder filled with 12 characters, is GSM-7 and at most 2 segments
        (306 characters); and no template is within 6 characters of the limit before the placeholders are filled."""
        import string
        for code, pair in H.TEMPLATES.items():
            for lang, tpl in zip(("en", "sw"), pair):
                names = [f for _, f, _, _ in string.Formatter().parse(tpl) if f]
                filled = tpl.format(**{n: "x" * 12 for n in names}) if names else tpl
                enc, seg = sms_segments(filled)
                self.assertEqual(enc, "GSM-7", (code, lang))
                self.assertLessEqual(seg, 2, (code, lang, len(filled)))
                bare = tpl.format(**{n: "" for n in names}) if names else tpl
                self.assertLessEqual(len(bare), 306 - 6, (code, lang, len(bare)))

    def test_n5_08_open_meteo_drops_nan_infinity_and_absurd_values(self):
        hours = [f"2026-10-12T{h:02d}:00" for h in range(24)]
        def payload(t):
            return {"hourly": {"time": hours, "temperature_2m": t, "relative_humidity_2m": [60.0] * 24,
                               "precipitation": [0.0] * 24, "precipitation_probability": [10] * 24}}
        for bad in (float("nan"), float("inf"), 1e9, -1e9, "hot"):
            t = [20.0] * 24; t[5] = bad
            days = H.daily_from_open_meteo(payload(t))
            self.assertEqual(len(days), 1, bad)
            self.assertAlmostEqual(days[0].temp_c, 20.0)
            b = batch("sack"); H.advance_day(b, days[0])        # must not raise
        t = [float("nan")] * 24
        self.assertEqual(H.daily_from_open_meteo(payload(t)), [])      # a day with no usable temperatures is dropped

    def test_assumptions_are_all_labelled(self):
        self.assertEqual([a[0] for a in H.ASSUMPTIONS], list(range(1, 16)))
        self.assertTrue(all(a[1] in ("SOURCE", "CALIBRATION", "PROGRAMME", "UNVALIDATED") and a[2] for a in H.ASSUMPTIONS))

    def test_horizon_cap_is_flagged_not_predicted(self):
        b = batch("hermetic"); b.record_meter(D0, 12.0)
        _, d = ev(b)
        self.assertEqual(d["days_left"], H.HORIZON_DAYS); self.assertTrue(d["days_left_capped"])
        b = batch(); b.record_salt(D0, sticky=True)
        self.assertFalse(ev(b)[1]["days_left_capped"])

    def test_retention_cutoffs(self):
        c = H.retention_cutoffs(D0)
        self.assertEqual(c["inbound_text"], D0 - timedelta(30)); self.assertEqual(c["messages"], D0 - timedelta(180))
        self.assertEqual(c["ended_batch_phone"], D0 - timedelta(90))


class GoldenVectors(unittest.TestCase):
    def test_vectors_file_matches_engine(self):
        import json, os, subprocess, sys, tempfile
        here = os.path.dirname(os.path.abspath(__file__))
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, os.path.join(here, "make_vectors.py")], cwd=tmp, check=True,
                           capture_output=True, env=dict(os.environ, PYTHONPATH=here))
            fresh = json.load(open(os.path.join(tmp, "vectors.json")))
        self.assertEqual(fresh, json.load(open(os.path.join(here, "vectors.json"))))

    def test_demo_story_through_the_production_path(self):
        import json, os
        v = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectors.json")))
        demo = next(s for s in v["scenarios"] if s["name"] == "demo_pitch")
        codes = [(t["day"][-2:], t["code"]) for t in demo["trace"] if t["code"]]
        self.assertEqual([c for _, c in codes], ["DRY_NOW", "DRY_NOW", "THANKS", "RAIN_COVER",
                                                 "NEARLY_DRY", "READY_TO_STORE", "STATUS"])


class R3Fixes(unittest.TestCase):
    """Review R3 engine findings: S3-01, E3-01, E3-03, C3-14 (template)."""

    def test_s3_01_a_sealed_bag_never_says_falling_fast(self):
        for left in (90, 120, 200, 364, 365):
            for lang in ("en", "sw"):
                self.assertNotIn("falling", H._risk(left, lang, tracks_air=False))
                self.assertNotIn("hupungua", H._risk(left, lang, tracks_air=False))
        # through render(): a hermetic batch, any countdown >= 90
        b = batch("hermetic"); b.record_meter(D0, 13.1)
        for left in (90, 200, 365):
            for lang in ("en", "sw"):
                b.lang = lang
                a = H.render("STATUS", b, "LOW", left, D0, PLACES)
                self.assertNotIn("falling fast", a.text + a.other)
                self.assertNotIn("hupungua haraka", a.text + a.other)

    def test_s3_01_story_day_12_sealed_bag_text(self):
        import json, os
        v = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectors.json")))
        demo = next(s for s in v["scenarios"] if s["name"] == "demo_pitch")
        last = [t for t in demo["trace"] if t.get("message") and t["day"].endswith("-24")][-1]
        self.assertIn("3 months or more", last["message"])
        self.assertNotIn("falling fast", last["message"])

    def test_s3_01_a_capped_countdown_is_not_a_prediction_either(self):
        b = batch("sack"); b.record_meter(D0, 13.1)
        a = H.render("STATUS", b, "LOW", H.HORIZON_DAYS, D0, PLACES)
        self.assertNotIn("falling fast", a.text)
        a = H.render("STATUS", b, "LOW", 120, D0, PLACES)         # an uncapped long countdown in sacks still follows the air
        self.assertIn("falling fast in damp weather", a.text)
        self.assertIn("hupungua haraka", a.other)

    def test_e3_01_every_command_a_message_names_is_one_the_parser_accepts(self):
        import re
        bare = re.compile(r"\b(METER|SALT|MITA|CHUMVI|HYGRO)\b(?! ?[0-9]| (YES|NO|NDIYO|NDIO|HAPANA)\b"
                          r"| and the number| with the number| na namba)")
        b = batch(); b.record_meter(D0, 14.0); b.sent = [(D0, "HIGH_ALERT")] * 3
        for code in H.TEMPLATES:
            for lang in (0, 1):
                self.assertIsNone(bare.search(H.TEMPLATES[code][lang]), (code, lang, H.TEMPLATES[code][lang]))
        for left in (None, 0, 30, 365):
            for lang in ("en", "sw"):
                b.lang = lang
                a = H.render("HIGH_ALERT", b, "HIGH", left, D0, PLACES)
                for text in (a.text, a.other):
                    self.assertIsNone(bare.search(text), text)

    def test_e3_01_the_closing_text_commands_really_work(self):
        b0 = batch(); b0.record_meter(D0, 13.0); b0.sent = [(D0, "HIGH_ALERT")] * 3
        a = H.render("HIGH_ALERT", b0, "HIGH", 0, D0, PLACES)
        self.assertIn("e.g. METER 14.2 (your own reading) or SALT YES/NO to restart", a.text)
        self.assertIn("mf. MITA 14.2 au CHUMVI NDIYO/HAPANA", a.other)
        for cmd in ("METER 13.5", "SALT YES", "SALT NO", "MITA 13.5", "CHUMVI NDIYO", "CHUMVI HAPANA"):
            b = batch(); b.record_meter(D0, 17.0)
            got = H.apply_reply(b, cmd, D0 + timedelta(1))
            self.assertIn(got, ("METER", "SALT_YES", "SALT_NO", "SALT_NO_IGNORED"), cmd)
        # and the restart really restarts the count
        b = batch(); b.record_meter(D0, 19.0); b.sent = [(D0, "HIGH_ALERT")] * 4
        H.apply_reply(b, "METER 17", D0 + timedelta(1))
        self.assertEqual(b.count_sent("HIGH_ALERT", b.last_test), 0)

    def test_e3_01_the_last_reminder_still_restarts_with_the_documented_wording_in_both_languages(self):
        b = batch(); b.record_meter(D0, 13.0); b.sent = [(D0, "HIGH_ALERT")] * 3
        for lang, word in (("en", "restart"), ("sw", "kuziwasha")):
            b.lang = lang
            a = H.render("HIGH_ALERT", b, "HIGH", 0, D0, PLACES)
            self.assertIn(word, a.text)

    def test_e3_03_no_comment_claims_a_high_batch_is_never_silent(self):
        import os
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "harvestly_engine.py")).read()
        self.assertNotIn("never silent", src.replace("HighIsNeverSilent", ""))

    def test_c3_14_the_start_confirmation_is_a_template_in_both_languages(self):
        en, sw = H.TEMPLATES["START_OK"]
        self.assertIn("JOIN", en); self.assertIn("STOP", en)
        self.assertIn("SAJILI", sw); self.assertIn("SIMAMISHA", sw)
        self.assertLessEqual(len(en), 160 * 2); self.assertLessEqual(len(sw), 160 * 2)


class R4Fixes(unittest.TestCase):
    """Round 4: examples in messages must be safe to copy; the Kiswahili join example must work."""

    def _texts(self):
        out = []
        for code, pair in H.TEMPLATES.items():
            out += [(code, "en", pair[0]), (code, "sw", pair[1])]
        b = batch(); b.record_meter(D0, 13.0); b.sent = [(D0, "HIGH_ALERT")] * 3
        for lang in ("en", "sw"):
            b.lang = lang
            a = H.render("HIGH_ALERT", b, "HIGH", 0, D0, PLACES)
            out += [("HIGH_ALERT closing", lang, a.text), ("HIGH_ALERT closing", "other", a.other)]
        return out

    def test_e4_01_every_meter_example_is_labelled_an_example_and_copies_as_wet(self):
        import re
        seen = 0
        for code, lang, text in self._texts():
            for m in re.finditer(r"(METER|MITA) (\d+(?:\.\d+)?)", text):
                seen += 1
                self.assertGreater(float(m.group(2)), H.EAS_MAX_MC, (code, lang, text))   # a literal copy is never a dry reading
                before = text[:m.start()]
                self.assertTrue(before.rstrip().endswith(("e.g.", "mf.")) or "reply" in before.lower() or "jibu" in before.lower(), (code, text))
                if code == "HIGH_ALERT closing" and lang == "en":
                    self.assertIn("e.g. METER", text); self.assertIn("your own reading", text)
        self.assertGreaterEqual(seen, 5)

    def test_e4_01_copying_the_example_literally_keeps_the_batch_wet_and_warns(self):
        b = batch(); b.record_meter(D0, 17.0); b.sent = [(D0, "HIGH_ALERT")] * 4
        cmd, a = H.respond(b, "METER 14.2", D0 + timedelta(1), [], PLACES and None)
        self.assertEqual(cmd, "METER")
        self.assertEqual(b.verdict(), "NOT_PROVEN")          # never DRY: the example sits above the 13.5 limit, so a literal copy cannot clear grain
        self.assertIn("not yet proven dry", a.text.lower()); self.assertIn("14.2", a.text)   # the reply echoes the reading, so a copy is never silent

    def test_e4_02_status_does_not_claim_a_weather_basis_and_swahili_object_agrees(self):
        en, sw = H.TEMPLATES["STATUS"]
        self.assertNotIn("current weather", en); self.assertNotIn("hali ya hewa", sw)
        b = batch(); b.record_meter(D0, 13.0); b.sent = [(D0, "HIGH_ALERT")] * 3; b.lang = "sw"
        self.assertIn("kuziwasha", H.render("HIGH_ALERT", b, "HIGH", 0, D0, PLACES).text)

    def test_c4_01_swahili_start_example_is_a_registration_the_parser_takes_as_swahili(self):
        import re
        ords = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plsql", "ords_handlers.sql")).read()
        sw = H.TEMPLATES["START_OK"][1]
        ex = re.search(r"mf\. (SAJILI [A-Z ]+ [0-9]+)", sw).group(1)
        self.assertRegex(ex, r"^(JOIN|REGISTER|SAJILI) [A-Z][A-Z ]* [0-9]+( SW)?$")
        self.assertIn("MAGUNIA", ex); self.assertNotIn("SACK", ex)
        # the handler: SAJILI implies Kiswahili, and MAGUNIA is a storage word
        self.assertRegex(ords, r"IF REGEXP_LIKE\(v_norm, '\^SAJILI '\) THEN v_lang := 'sw'")
        self.assertIn("WHEN 'MAGUNIA' THEN 'sack'", ords)


if __name__ == "__main__":
    unittest.main(verbosity=1)
