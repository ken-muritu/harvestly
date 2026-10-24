-- Harvestly smoke test for ords_handlers.sql helpers (R1-25 / R2). *** NEVER RUN: written without an Oracle database ***
-- Run AFTER schema.sql, the package and ords_handlers.sql, and AFTER test_vectors.sql passes. Needs hv_config rows
-- hash_pepper, and a ward named Kitale. It writes test rows with phone 254700000001..3 and removes them at the end.
-- Prints "ok ..." or "FAIL ..." per check, then a summary. It does not call Open-Meteo, Africa's Talking or Telegram.
SET SERVEROUTPUT ON
SET DEFINE OFF
DECLARE
  v_fail PLS_INTEGER := 0;
  v_n    PLS_INTEGER := 0;
  v_hash VARCHAR2(64);
  v_reply VARCHAR2(1000);
  v_cmd  VARCHAR2(20);
  v_cnt  NUMBER;
  v_st   VARCHAR2(10);
  v_clob CLOB;
  PROCEDURE report(p_ok IN BOOLEAN, p_label IN VARCHAR2) IS
  BEGIN
    v_n := v_n + 1;
    IF p_ok THEN DBMS_OUTPUT.PUT_LINE('ok   ' || p_label); ELSE v_fail := v_fail + 1; DBMS_OUTPUT.PUT_LINE('FAIL ' || p_label); END IF;
  END;
BEGIN
  -- body parsing (C-03, R1-12): form, percent-decoding, '+', JSON fallback
  v_clob := 'from=%2B254700000001&to=22384&text=SALT+YES&date=2026-10-12&id=ATXid_1&linkId=abc';
  report(hv_body_value(v_clob, 'from') = '+254700000001', 'form: from percent-decoded');
  report(hv_body_value(v_clob, 'text') = 'SALT YES', 'form: + is a space');
  report(hv_body_value(v_clob, 'id') = 'ATXid_1' AND hv_body_value(v_clob, 'linkId') = 'abc', 'form: id is not linkId');
  report(hv_body_value('{"from":"+254700000001","text":"STOP"}', 'text') = 'STOP', 'json fallback');
  report(hv_body_value(NULL, 'text') IS NULL, 'empty body -> NULL');
  -- R3 R1-12: malformed bodies are detected (the handlers answer 400), well-formed ones of either format pass
  report(hv_body_ok(v_clob) = 1, 'body_ok: good form body');
  report(hv_body_ok('from=%ZZ&text=hi') = 0, 'body_ok: a % not followed by two hex digits is malformed');
  report(hv_body_ok('from=%2B25470&text=hi%') = 0, 'body_ok: a trailing % is malformed');
  report(hv_body_ok('from=%FF%FE&text=x') = 0, 'body_ok: invalid UTF-8 is malformed');
  report(hv_body_ok('from=%C3%A9&text=caf%C3%A9') = 1, 'body_ok: well-formed UTF-8 (C4-02)');
  report(hv_body_ok('from=1&text=%C3') = 0, 'body_ok: truncated UTF-8 sequence is malformed (C4-02, no reliance on UNESCAPE raising)');
  report(hv_body_ok('from=1&text=%D0%96%D8%B9') = 1, 'body_ok: valid D0-DF lead (Cyrillic, Arabic) is accepted (C5-01)');
  report(hv_body_ok('from=1&text=%E2%82%AC%F0%9F%98%80') = 1, 'body_ok: valid 3 and 4 byte sequences are accepted (C5-01)');
  report(hv_body_ok('from=1&text=%E0%80%80') = 0, 'body_ok: overlong 3-byte sequence is malformed (C5-01)');
  report(hv_body_ok('from=1&text=%ED%A0%80') = 0, 'body_ok: surrogate is malformed (C5-01)');
  report(hv_body_ok('from=1&text=%C0%80') = 0, 'body_ok: overlong 2-byte sequence is malformed (C5-01)');
  report(hv_body_ok('from=1&text=%F4%90%80%80') = 0, 'body_ok: above U+10FFFF is malformed (C5-01)');
  report(hv_body_ok('{"from":"+254700000001","text":"STOP"}') = 1, 'body_ok: good JSON');
  report(hv_body_ok('{"from":"+254700000001",') = 0, 'body_ok: broken JSON is malformed');
  report(hv_body_ok(NULL) = 1, 'body_ok: empty body is not malformed');
  v_clob := '{"from":"+254700000001","text":"' || RPAD('a', 5000, 'a') || '"}';
  report(LENGTH(hv_body_value(v_clob, 'text')) = 4000 AND hv_body_value(v_clob, 'from') = '+254700000001',
         'JSON value over 4000 bytes is cut to 4000, not dropped');

  -- R3 C3-10: a secret under 16 characters is refused, whatever it matches
  DELETE FROM hv_config WHERE cfg_key = 'smoke_secret';
  INSERT INTO hv_config (cfg_key, cfg_value) VALUES ('smoke_secret', 'short');
  report(NOT hv_check_secret('smoke_secret', 'short'), 'secret under 16 characters is refused');
  UPDATE hv_config SET cfg_value = 'aaaaaaaaaaaaaaaaaaaaaa1' WHERE cfg_key = 'smoke_secret';
  report(hv_check_secret('smoke_secret', 'aaaaaaaaaaaaaaaaaaaaaa1') AND NOT hv_check_secret('smoke_secret', 'aaaaaaaaaaaaaaaaaaaaaa2'),
         'secret compare: equal accepted, one character off refused');
  DELETE FROM hv_config WHERE cfg_key = 'smoke_secret';

  -- replay protection (C-05)
  DELETE FROM hv_inbound_seen WHERE channel = 'sms' AND provider_id = 'SMOKE-1';
  report(hv_seen_once('sms', 'SMOKE-1') = 1, 'first id accepted');
  report(hv_seen_once('sms', 'SMOKE-1') = 0, 'repeated id refused');
  report(hv_seen_once('sms', NULL) = 1, 'no id is never deduplicated');

  -- rate limit (C-05): the 13th message in an hour is over the default cap of 12
  v_hash := harvestly_engine.address_hash('254700000002');
  DELETE FROM hv_rate WHERE addr_hash = v_hash; COMMIT;
  FOR i IN 1 .. 13 LOOP v_cnt := hv_rate_hit(v_hash); END LOOP;
  report(v_cnt = 13 AND v_cnt > hv_limit('max_in_per_hour', 12), 'hourly inbound cap trips on message 13');

  -- STOP from a stranger is confirmed exactly once, then silence (C-01); START brings the number back (C-06)
  v_hash := harvestly_engine.address_hash('254700000003');
  DELETE FROM hv_optout WHERE addr_hash = v_hash; DELETE FROM hv_messages WHERE to_hash = v_hash; COMMIT;
  hv_handle_inbound('sms', '254700000003', 'I want to stop', v_reply, v_cmd);
  report(v_cmd = 'STOP' AND v_reply LIKE '%no more messages%', 'stranger STOP is confirmed (R1-04 phrase)');
  SELECT status INTO v_st FROM hv_messages WHERE to_hash = v_hash AND code = 'STOPPED';
  report(v_st = 'QUEUED', 'STOPPED confirmation is QUEUED although the number is opted out');
  hv_handle_inbound('sms', '254700000003', 'STOP', v_reply, v_cmd);
  SELECT COUNT(*) INTO v_cnt FROM hv_messages WHERE to_hash = v_hash AND code = 'STOPPED';
  report(v_cnt = 1 AND v_reply IS NULL, 'a second STOP is silent');
  hv_handle_inbound('sms', '254700000003', 'hello', v_reply, v_cmd);
  report(v_reply IS NULL, 'opted-out number gets no answer');
  hv_handle_inbound('sms', '254700000003', 'START', v_reply, v_cmd);
  SELECT COUNT(*) INTO v_cnt FROM hv_optout WHERE addr_hash = v_hash;
  report(v_cmd = 'START' AND v_cnt = 0, 'START clears the opt-out of an unknown sender');
  -- C5-02: a Kiswahili stranger who mistypes gets Kiswahili guidance with a SAJILI example
  hv_handle_inbound('sms', '254700000003', 'SAJILI KITALE MAHINDI 12', v_reply, v_cmd);
  report(v_reply LIKE '%Kusajili%SAJILI KITALE MAGUNIA 12%', 'mistyped SAJILI gets the Kiswahili how-to (C5-02)');
  hv_handle_inbound('sms', '254700000003', 'SAJILI KITALE', v_reply, v_cmd);
  report(v_reply LIKE '%Kusajili%', 'SAJILI with no number gets the Kiswahili how-to (C5-02)');
  hv_handle_inbound('sms', '254700000003', 'JOIN KITALE', v_reply, v_cmd);
  report(v_reply LIKE '%To join%', 'JOIN with no number still gets the English how-to');

  -- reply status is a VARCHAR2 and never needs BOOLEAN in SQL (C-02)
  report(hv_reply_status(v_hash, 'HOWTO') = 'QUEUED', 'reply status QUEUED for a normal number');

  -- USSD status wording (C-07 / K-04): measured + date + estimate, never "safe"
  hv_handle_inbound('sms', '254700000001', 'JOIN KITALE SACK 5', v_reply, v_cmd);
  hv_handle_inbound('sms', '254700000001', 'METER 13.1', v_reply, v_cmd);
  FOR r IN (SELECT 'METER 13-15' t FROM dual UNION ALL SELECT 'meter 13 / 15' FROM dual UNION ALL SELECT 'METER -13' FROM dual UNION ALL SELECT 'METER .5' FROM dual) LOOP
    hv_handle_inbound('sms', '254700000001', r.t, v_reply, v_cmd);       -- E5-01: a range or a negative is never a reading
    report(v_reply LIKE '%did not understand%', 'E5-01: ' || r.t || ' is answered with help, not recorded');
  END LOOP;
  v_reply := hv_ussd_menu('254700000001', '2', 'smoke-session');
  DBMS_OUTPUT.PUT_LINE('     USSD: ' || v_reply);
  -- C3-09: a correct build says "3 months or more" here (the 365 cap), which has no word "estimate"
  report(LENGTH(v_reply) <= 160 AND INSTR(LOWER(v_reply), 'safe') = 0
         AND INSTR(v_reply, 'meter 13.1%') > 0, 'USSD status: <=160, no "safe", names the reading');

  -- R3 C3-06: typing STOP at the USSD meter prompt must not opt the farmer out
  v_hash := harvestly_engine.address_hash('254700000001');
  v_reply := hv_ussd_menu('254700000001', '3*3*STOP', 'smoke-session-2');
  SELECT COUNT(*) INTO v_cnt FROM hv_optout WHERE addr_hash = v_hash;
  report(v_cnt = 0 AND v_reply LIKE 'END%', 'USSD: STOP at the meter prompt is not an opt-out');

  -- R3 C3-01: a known sender's repeated STOP is confirmed once
  hv_handle_inbound('sms', '254700000001', 'STOP', v_reply, v_cmd);
  hv_handle_inbound('sms', '254700000001', 'please stop', v_reply, v_cmd);
  SELECT COUNT(*) INTO v_cnt FROM hv_messages WHERE to_hash = v_hash AND code = 'STOPPED';
  report(v_cnt = 1 AND v_reply IS NULL, 'known sender: second STOP gets no second confirmation');

  ROLLBACK;
  DBMS_OUTPUT.PUT_LINE(v_n || ' checks, ' || v_fail || ' failed');
END;
/
