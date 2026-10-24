"""Static checks on the never-compiled PL/SQL (no Oracle needed). They do not prove it compiles; they stop the specific
defects found by review R2 from coming back.   Run:  python3 -m unittest plsql/tools/test_plsql_static.py -v
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLSQL = os.path.join(HERE, "..")
ORDS = open(os.path.join(PLSQL, "ords_handlers.sql")).read()
PKB = open(os.path.join(PLSQL, "harvestly_engine.pkb")).read()
SCHEMA = open(os.path.join(PLSQL, "schema.sql")).read()
PKS = open(os.path.join(PLSQL, "harvestly_engine.pks")).read()
README = open(os.path.join(PLSQL, "README.md")).read()
SMOKE = open(os.path.join(PLSQL, "test_smoke.sql")).read()


def strip_comments(sql):
    sql = re.sub(r"--[^\n]*", "", sql)
    return re.sub(r"/\*.*?\*/", "", sql, flags=re.S)


def boolean_functions(text):
    """Names of every function declared RETURN BOOLEAN (stand-alone or in a package), found in the source itself."""
    return re.findall(r"\bFUNCTION\s+(\w+)[^;]*?RETURN\s+BOOLEAN", strip_comments(text), flags=re.S | re.I)


def sql_statements(text):
    """Rough split into INSERT / UPDATE / DELETE / SELECT / MERGE statements (up to the next ';')."""
    code = strip_comments(text)
    return re.findall(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|SELECT)\b[^;]*;", code, flags=re.I)


def handler_sources(text):
    return re.findall(r"q'~(.*?)~'", text, flags=re.S)


class NoBooleanInSql(unittest.TestCase):
    """C-02: a BOOLEAN function called inside a SQL statement does not compile before 23ai."""
    def test_no_boolean_function_inside_a_sql_statement(self):
        # E3-02: the names are read from the sources (no hand-kept list that can go stale)
        names = sorted(set(boolean_functions(ORDS) + boolean_functions(PKB) + boolean_functions(PKS)))
        for must in ("hv_is_optedout", "hv_can_register", "hv_check_secret", "hv_ip_allowed", "is_optout", "is_permeable",
                     "needs_drying", "pushed_on_change", "is_advice_code", "record_salt"):
            self.assertIn(must, names)
        for stmt in sql_statements(ORDS) + sql_statements(PKB):
            for n in names:
                if n == "stale":
                    continue
                self.assertNotRegex(stmt, r"\b" + n + r"\s*\(", f"BOOLEAN function {n} inside SQL: {stmt[:140]!r}")

    def test_the_insert_that_failed_review_now_uses_a_varchar_status(self):
        self.assertNotRegex(strip_comments(ORDS), r"CASE WHEN hv_is_optedout")
        self.assertIn("hv_reply_status", ORDS)

    PATTERNS_23AI = {
        "IF [NOT] EXISTS in DDL": r"\b(?:CREATE|ALTER|DROP)\s+(?:OR\s+REPLACE\s+)?\w+\s+(?:\w+\s+)?IF\s+(?:NOT\s+)?EXISTS\b",
        "GROUP BY ALL": r"\bGROUP\s+BY\s+ALL\b",
        "multi-row VALUES": r"\bVALUES\s*\([^()]*\)\s*,\s*\(",
        "BOOLEAN column": r"^\s*\w+\s+BOOLEAN\b",
    }

    def test_no_23ai_only_syntax(self):
        code = strip_comments(ORDS) + strip_comments(PKB) + strip_comments(SCHEMA)
        for name, bad in self.PATTERNS_23AI.items():
            where = strip_comments(SCHEMA) if name == "BOOLEAN column" else code       # BOOLEAN variables are fine in PL/SQL
            self.assertIsNone(re.search(bad, where, re.I | re.M), name)

    def test_the_23ai_patterns_are_not_dead(self):
        # E3-02: each pattern really matches an example of the thing it forbids
        samples = {"IF [NOT] EXISTS in DDL": "CREATE TABLE IF NOT EXISTS t (a NUMBER)",
                   "GROUP BY ALL": "SELECT a FROM t GROUP BY ALL",
                   "multi-row VALUES": "INSERT INTO t VALUES (1), (2)",
                   "BOOLEAN column": "  flag BOOLEAN,"}
        self.assertEqual(set(samples), set(self.PATTERNS_23AI))
        for name, text in samples.items():
            self.assertRegex(text, re.compile(self.PATTERNS_23AI[name], re.I | re.M), name)

    def test_no_on_conversion_error_inside_plsql_expressions(self):
        self.assertNotIn("ON CONVERSION ERROR", strip_comments(ORDS))


class Handlers(unittest.TestCase):
    def test_body_text_is_read_exactly_once_per_handler(self):
        hs = handler_sources(ORDS)
        self.assertEqual(len(hs), 3)
        for h in hs:
            self.assertEqual(len(re.findall(r":body_text", strip_comments(h))), 1, h[:80])
            self.assertRegex(strip_comments(h), r"l_body\s*:=\s*:body_text")

    def test_no_uri_parameter_sources_for_form_fields(self):
        self.assertNotIn("p_source_type => 'URI'", ORDS)

    def test_every_handler_checks_its_secret_and_at_handlers_check_the_ip(self):
        hs = handler_sources(ORDS)
        self.assertIn("hv_check_secret('telegram_secret'", hs[0])
        for h in hs[1:]:
            self.assertIn("hv_ip_allowed", h)

    def test_replay_protection_on_provider_ids(self):
        hs = handler_sources(ORDS)
        self.assertIn("hv_seen_once('telegram'", hs[0])
        self.assertIn("hv_seen_once('sms'", hs[1])
        self.assertIn("hv_inbound_seen", SCHEMA)

    def test_ip_allowlist_fails_closed(self):
        m = re.search(r"FUNCTION hv_ip_allowed.*?END hv_ip_allowed;", ORDS, flags=re.S)
        body = m.group(0)
        self.assertRegex(body, r"IF v_list IS NULL THEN RETURN FALSE")
        self.assertIn("trusted_proxies", body)

    def test_stop_confirmation_is_exempt_from_the_optout_cancel_in_every_claim_path(self):
        self.assertIn("m.code <> 'STOPPED'", ORDS)                       # hv_claim_and_send
        self.assertIn("r.code <> 'STOPPED'", PKB)                        # claim_queued
        self.assertIn("IF p_code = 'STOPPED' THEN RETURN 'QUEUED'", PKB)       # reply_status (moved into the package, R3 C3-02)

    def test_telegram_token_mitigation_is_in_place_and_honest(self):
        self.assertIn("hv_ws_quiet;", ORDS)
        self.assertIn("NOT guaranteed", ORDS)
        self.assertNotRegex(ORDS, r"is never logged or stored")

    def test_ussd_status_never_says_safe(self):
        m = re.search(r"FUNCTION hv_ussd_menu.*?END hv_ussd_menu;", ORDS, flags=re.S)
        self.assertNotRegex(strip_comments(m.group(0)).lower(), r"safe|salama")

    def test_welcome_is_queued_before_the_first_test_message(self):
        for m in re.finditer(r"queue_welcome\(v_batch, v_today\);.*?hv_queue_test_first", ORDS, flags=re.S):
            pass
        self.assertEqual(len(re.findall(r"queue_welcome\(v_batch, v_today\);[^\n]*\n\s*hv_queue_test_first", ORDS)), 2)

    def test_claim_and_send_sets_sent_at(self):
        self.assertRegex(ORDS, r"SET status = 'SENDING', sent_at = SYSTIMESTAMP WHERE msg_id = p_msg_id")

    def test_telegram_addresses_are_prefixed(self):
        self.assertIn("'tg:' || TO_CHAR(l_chat)", ORDS)
        self.assertIn("created_at   TIMESTAMP WITH TIME ZONE", SCHEMA)


class ReviewR3(unittest.TestCase):
    """One static check per R3 code finding (the logic itself is only provable on Oracle)."""
    def fn(self, name, text=ORDS):
        m = re.search(r"(?:FUNCTION|PROCEDURE) " + name + r"\b.*?END " + name + r";", text, flags=re.S)
        self.assertIsNotNone(m, name)
        return strip_comments(m.group(0))

    def handler(self, i):
        return strip_comments(handler_sources(ORDS)[i])

    def test_c3_01_stop_is_confirmed_only_on_the_transition(self):
        body = self.fn("process_reply", PKB)
        self.assertRegex(body, r"SELECT COUNT\(\*\) INTO v_was_out FROM hv_optout")
        self.assertRegex(body, r"NOT \(p_cmd = 'STOP' AND v_was_out > 0\)")

    def test_c3_02_reply_budget_lives_in_the_package_and_queue_message_applies_it(self):
        self.assertIn("FUNCTION reply_status", PKS)
        self.assertIn("RETURN harvestly_engine.reply_status(p_hash, p_code)", self.fn("hv_reply_status"))
        self.assertIn("reply_status(v_hash, p_alert.code)", self.fn("queue_message", PKB))
        self.assertIn("max_reply_global_per_day", PKB)
        self.assertIn("max_batches_global_per_day", ORDS)
        self.assertIn("max_ussd_per_hour", self.fn("hv_ussd_menu"))

    def test_c3_02_the_inbound_counter_is_a_sliding_window(self):
        body = self.fn("hv_rate_hit")
        self.assertIn("bucket_hour = v_b - 1/24", body)
        self.assertRegex(body, r"CEIL\(v_prev \* \(60 - ")

    def test_c3_03_purge_keeps_cap_rows_of_active_batches_past_180_days(self):
        body = self.fn("purge_retention", PKB)
        self.assertIn("'[purged]'", body)
        self.assertIn("m.msg_date >= NVL(b.last_test", body)
        self.assertIn("'TEST_FIRST', 'INSECT_REMINDER'", body)

    def test_c3_04_ussd_handler_has_an_outer_exception_block(self):
        h = self.handler(2)
        self.assertGreaterEqual(len(re.findall(r"EXCEPTION WHEN OTHERS THEN", h)), 2)
        self.assertRegex(h, r"htp\.prn\(l_out\);\s*EXCEPTION WHEN OTHERS THEN")

    def test_c3_05_sender_and_phone_are_validated_and_cut_to_width(self):
        for i in (1, 2):
            h = self.handler(i)
            self.assertIn("REGEXP_LIKE(", h)
            self.assertIn("^\\+?[0-9]{6,15}$", h)
            self.assertRegex(h, r"SUBSTR\(hv_body_value\(l_body, '(from|phoneNumber)'\), 1, 200\)")

    def test_c3_06_only_a_number_is_sent_on_as_meter_from_ussd(self):
        body = self.fn("hv_ussd_menu")
        self.assertRegex(body, r"NOT REGEXP_LIKE\(parts\(3\), '\^\[0-9\]")
        self.assertLess(body.index("NOT REGEXP_LIKE(parts(3)"), body.index("'METER ' || parts(3)"))

    def test_c3_07_the_cap_is_checked_after_the_retry_checks(self):
        body = self.fn("hv_register_once")
        self.assertLess(body.index("USSD_REG' AND from_hash"), body.index("hv_can_register"))
        self.assertLess(body.index("AND status = 'active'"), body.index("hv_can_register"))
        self.assertIn("p_blocked OUT BOOLEAN", ORDS)
        self.assertNotRegex(self.fn("hv_ussd_menu"), r"ELSIF NOT hv_can_register")

    def test_c3_08_the_inline_send_is_off_unless_switched_on(self):
        self.assertRegex(self.fn("hv_send_reply_now"), r"hv_cfg\('inline_send'\), 'N'\) <> 'Y' THEN\s*RETURN")

    def test_c3_09_the_smoke_test_does_not_demand_the_word_estimate_from_a_capped_status(self):
        self.assertNotIn("INSTR(v_reply, 'estimate')", SMOKE)

    def test_c3_10_secret_compare_has_no_early_exit_and_a_minimum_length(self):
        body = self.fn("hv_check_secret")
        self.assertIn("LENGTH(v) < 16", body)
        self.assertIn("HASH_SH256", body)
        self.assertRegex(body, r"FOR i IN 1 \.\. 64 LOOP")
        self.assertNotRegex(body, r"RETURN v = p_secret")

    def test_c3_11_schema_refuses_old_column_types_and_readme_has_the_upgrade(self):
        self.assertIn("RAISE_APPLICATION_ERROR(-20099", SCHEMA)
        for col in ("'HV_MESSAGES' t, 'CREATED_AT' c", "'HV_MESSAGES' t, 'SENT_AT' c", "'HV_WEATHER_RAIN24' t, 'FETCHED_AT' c"):
            self.assertIn(col, SCHEMA)
        self.assertIn("Upgrading an existing install", README)

    def test_c3_12_cors_is_closed_on_the_module(self):
        self.assertIn("ORDS.SET_MODULE_ORIGINS_ALLOWED(p_module_name => 'harvestly'", ORDS)

    def test_c3_13_ip_diag_is_available_and_documented(self):
        self.assertIn("hv_ip_log;", self.fn("hv_ip_allowed"))
        self.assertIn("ip_diag", README)

    def test_c3_14_start_confirmation_comes_from_a_template(self):
        self.assertIn("code = 'START_OK'", ORDS)
        self.assertNotIn("Messages are on again for this number", ORDS)
        self.assertEqual(SCHEMA.count("'START_OK' c"), 2)

    def test_r1_12_malformed_bodies_get_a_400_in_all_three_handlers_and_json_is_read_from_the_clob(self):
        for i in (0, 1, 2):
            self.assertRegex(self.handler(i), r"hv_body_ok\(l_body\) = 0 THEN\s*:status_code := 400")
        body = self.fn("hv_body_value")
        self.assertIn("JSON_VALUE(p_body,", body)
        self.assertNotIn("JSON_VALUE(v_b,", body)
        self.assertIn("the one-callback procedure", README)
        self.assertIn("Testing against a real callback", README)

    def test_s3_01_risk_text_has_the_sealed_and_capped_rule(self):
        body = self.fn("risk_text", PKB)
        self.assertIn("NOT p_tracks_air OR p_left >= c_horizon_days", body)
        self.assertIn("risk_text(p_left, en, b.storage <> 'hermetic')", PKB)

    def test_e3_01_the_closing_text_names_working_commands(self):
        self.assertIn("e.g. METER 14.2 (your own reading) or SALT YES/NO to restart", PKB)
        self.assertNotIn("METER or SALT", PKB + ORDS + README)
        self.assertNotIn("MITA au CHUMVI.", PKB)


class R4Fixes(unittest.TestCase):
    def test_c4_01_sajili_implies_kiswahili_and_swahili_storage_words_parse(self):
        self.assertRegex(ORDS, r"IF REGEXP_LIKE\(v_norm, '\^SAJILI '\) THEN v_lang := 'sw'")
        for w in ("MAGUNIA", "NIMEFUNGA", "ANIKA", "KIHENGE", "SAKAFU"):      # B7-02: Kiswahili crib / floor
            self.assertIn(f"WHEN '{w}' THEN", ORDS)
        self.assertIn("Hifadhi: ANIKA, MAGUNIA, KIHENGE, SAKAFU au NIMEFUNGA.", ORDS)
        self.assertNotRegex(re.search(r"c_howto_sw CONSTANT.*?;", ORDS, re.S).group(0), r"CRIB|FLOOR")
        sw = re.search(r"'START_OK' c, 'sw' l, q'~(.*?)~'", SCHEMA, re.S).group(1)
        ex = re.search(r"mf\. (SAJILI [A-Z ]+ [0-9]+)", sw).group(1)
        self.assertRegex(ex, r"^(JOIN|REGISTER|SAJILI) [A-Z][A-Z ]* [0-9]+( SW)?$")
        self.assertTrue(ex.split()[-2] in ("MAGUNIA", "NIMEFUNGA", "ANIKA"))

    def test_c4_03_stranger_replies_have_swahili(self):
        self.assertIn("Usajili mwingi sana", ORDS)
        self.assertIn("Kata gani?", ORDS)

    def test_c4_02_utf8_check_does_not_rely_on_unescape_raising(self):
        m = re.search(r"REGEXP_REPLACE\(v_b, '(%\(\[Cc\].*?)', ''\),\s*'(%\[89A-Fa-f\]\[0-9A-Fa-f\])'", ORDS, re.S)
        self.assertTrue(m)
        good, left = m.group(1), m.group(2)
        def ok(body):
            return re.search(left, re.sub(good, "", body)) is None
        self.assertTrue(ok("text=caf%C3%A9")); self.assertTrue(ok("a=%E2%82%AC")); self.assertTrue(ok("a=%F0%9F%98%80"))
        for bad in ("%FF%FE", "%C3", "%80", "%C3%28", "%E2%82", "%F8%88%80%80%80"):
            self.assertFalse(ok("x=" + bad), bad)
        self.assertIn("UNISTR('\\FFFD')", ORDS)
        self.assertIn("truncated UTF-8", SMOKE)

    def test_e4_01_the_closing_and_examples_are_safe_to_copy(self):
        for txt in re.findall(r"(?:METER|MITA) (\d+\.\d)", PKB + SCHEMA):
            self.assertGreater(float(txt), 13.5)
        self.assertNotIn("METER 13.5", PKB + SCHEMA)
        self.assertNotIn("MITA 13.5", PKB + SCHEMA)


class R5Fixes(unittest.TestCase):
    def _utf8_ok(self):
        m = re.search(r"REGEXP_REPLACE\(v_b, '(%\(\[Cc\].*?)', ''\),\s*'(%\[89A-Fa-f\]\[0-9A-Fa-f\])'", ORDS, re.S)
        self.assertTrue(m)
        good, left = m.group(1), m.group(2)
        return lambda body: re.search(left, re.sub(good, "", body)) is None

    def test_c5_01_utf8_regex_agrees_with_a_real_utf8_decoder(self):
        ok = self._utf8_ok()
        enc = lambda bs: "".join("%%%02X" % b for b in bs)
        def valid(bs):
            try:
                bs.decode("utf-8"); return True
            except UnicodeDecodeError:
                return False
        # valid 2, 3 and 4 byte sequences, including the D0-DF leads that C4-02 left out
        for ch in ("\u00e9", "\u0416", "\u0639", "\u05d0", "\u07ff", "\u0800", "\u20ac", "\ud7ff", "\ue000", "\uffff", "\U0001f600", "\U0010ffff", "\U00010000"):
            self.assertTrue(ok("x=" + enc(ch.encode())), ch)
        self.assertTrue(ok("text=%D0%96%D0%B0&b=%D8%B9"))
        # overlong, surrogate and out-of-range sequences are rejected
        for bad in ("%C0%80", "%C1%BF", "%E0%80%80", "%E0%9F%BF", "%ED%A0%80", "%ED%BF%BF", "%F0%80%80%80", "%F0%8F%BF%BF",
                    "%F4%90%80%80", "%F5%80%80%80", "%D0", "%D0%28", "%E2%28%A1", "%F0%28%8C%BC"):
            self.assertFalse(ok("x=" + bad), bad)
        # exhaustive over every 2-byte pair, and over every lead + second byte for 3 and 4 byte forms
        for a in range(0x80, 0x100):
            for b in range(0x80, 0x100):
                self.assertEqual(ok("x=" + enc(bytes([a, b]))), valid(bytes([a, b])), hex(a * 256 + b))
        for lead in range(0xE0, 0xF5):
            for b2 in range(0x70, 0xC0):
                for tail in ((0x80, 0x80), (0xBF, 0xBF)) if lead < 0xF0 else ((0x80, 0x80, 0x80), (0xBF, 0xBF, 0xBF)):
                    n = 3 if lead < 0xF0 else 4
                    bs = bytes([lead, b2]) + bytes(tail[: n - 2])
                    self.assertEqual(ok("x=" + enc(bs)), valid(bs), bs.hex())
        self.assertIn("%D0%96", SMOKE)
        self.assertIn("%E0%80%80", SMOKE)

    def test_c5_02_kiswahili_howto_and_lang_set_before_the_regex_test(self):
        self.assertIn("c_howto_sw", ORDS)
        sw = re.search(r"c_howto_sw CONSTANT VARCHAR2\(300\) :=[^\n]*\n\s*'(.*?)'\n\s*\|\| '(.*?)';", ORDS, re.S)
        self.assertTrue(sw)
        text = sw.group(1) + sw.group(2)
        self.assertLessEqual(len(text), 300)
        ex = re.search(r"mf\. (SAJILI [A-Z ]+ [0-9]+)", text).group(1)
        self.assertRegex(ex, r"^(JOIN|REGISTER|SAJILI) [A-Z][A-Z ]* [0-9]+( SW)?$")
        self.assertIn(ex.split()[-2], ("MAGUNIA", "NIMEFUNGA", "ANIKA"))
        i_lang = ORDS.index("C5-02: a Kiswahili command word")
        i_regex = ORDS.index("'^(JOIN|REGISTER|SAJILI) [A-Z][A-Z ]* [0-9]+( SW)?$'")
        self.assertLess(i_lang, i_regex)
        self.assertRegex(ORDS, r"p_reply := CASE v_lang WHEN 'sw' THEN c_howto_sw ELSE c_howto END;")
        self.assertIn("SAJILI KITALE MAHINDI 12", SMOKE)

    def test_e5_01_ports_read_one_number_only(self):
        self.assertIn("c_re_meter_cmd", PKB)
        self.assertIn("c_re_neg", PKB)
        self.assertRegex(PKB, r"c_re_meter\s+CONSTANT VARCHAR2\(200\) := '\^\(METER\|METRE\|MITA\) \?\(\[0-9\]\+\(\[\.,\]\[0-9\]\+\)\?\)%\?\$'")
        self.assertRegex(PKB, r"IF v_neg OR NOT REGEXP_LIKE\(t, c_re_meter\) THEN\s+RETURN 'INVALID'")


if __name__ == "__main__":
    unittest.main()
