-- Harvestly golden-vector runner (no utPLSQL needed).
--
-- Order:  schema.sql  ->  harvestly_engine.pks / .pkb  ->  vectors_data.sql  ->  this file.
-- Replays engine/vectors.json (loaded into hv_vec_* by vectors_data.sql):
--   1. 49 EMC values and 60 AST values  (must match to 1e-6)
--   2. each scenario day by day: farmer replies first, then the 17:00 evening run; compares the
--      reply command and the EXACT message text, then at every evening step the message code and
--      text, risk level, days left (exact), the displayed moisture / life-used strings (fmt1) and
--      the exact values
--   3. the SMS rule: every template, both languages, worst-case fill, is GSM-7 and <= 2 segments
--   4. rounding (fmt0/1/2 half-up), evidence strings, opt-out words, normalise length cap,
--      address canonical form + HMAC hash, days_left cases (incl. the 365 horizon)
--   5. rules that need no vector file: HIGH_ALERT is weekly and capped, SKIPPED/FAILED never count as sent,
--      stale weather suppresses rain alerts and is flagged, the daily run is idempotent, the STATUS text
--      never says "safe", a long reply never raises.
-- Prints PASS/FAIL per step and a summary; raises ORA-20999 if anything failed.
SET SERVEROUTPUT ON SIZE UNLIMITED
SET DEFINE OFF

DECLARE
  g_pass PLS_INTEGER := 0;
  g_fail PLS_INTEGER := 0;

  PROCEDURE report(p_ok IN BOOLEAN, p_label IN VARCHAR2, p_detail IN VARCHAR2 DEFAULT NULL) IS
  BEGIN
    IF p_ok THEN
      g_pass := g_pass + 1;
      DBMS_OUTPUT.PUT_LINE('PASS ' || p_label);
    ELSE
      g_fail := g_fail + 1;
      DBMS_OUTPUT.PUT_LINE('FAIL ' || p_label || ' ' || p_detail);
    END IF;
  END report;

  FUNCTION same_s(a IN VARCHAR2, b IN VARCHAR2) RETURN BOOLEAN IS
  BEGIN
    RETURN (a = b) OR (a IS NULL AND b IS NULL);
  END;

  FUNCTION same_n(a IN NUMBER, b IN NUMBER, p_tol IN NUMBER) RETURN BOOLEAN IS
  BEGIN
    RETURN (ABS(a - b) <= p_tol) OR (a IS NULL AND b IS NULL);
  END;

  -- ------------------------------------------------------------------ 1. EMC and AST
  PROCEDURE test_tables IS
    got NUMBER;
    bad PLS_INTEGER := 0;
    n   PLS_INTEGER := 0;
  BEGIN
    FOR r IN (SELECT * FROM hv_vec_emc ORDER BY temp_c, rh) LOOP
      n := n + 1;
      got := harvestly_engine.emc(r.temp_c, r.rh);
      IF NOT same_n(got, r.emc, 0.000001) THEN
        bad := bad + 1;
        report(FALSE, 'emc(' || r.temp_c || 'C, ' || r.rh || '%)', 'got ' || got || ' want ' || r.emc);
      END IF;
    END LOOP;
    report(bad = 0 AND n = 49, 'EMC table: ' || n || ' values, ' || bad || ' mismatches', 'expected 49 values, 0 mismatches');
    bad := 0; n := 0;
    FOR r IN (SELECT * FROM hv_vec_ast ORDER BY temp_c, mc) LOOP
      n := n + 1;
      got := harvestly_engine.ast_days(r.temp_c, r.mc);
      IF NOT same_n(got, r.days, 0.000001) THEN
        bad := bad + 1;
        report(FALSE, 'ast_days(' || r.temp_c || 'C, ' || r.mc || '%)', 'got ' || got || ' want ' || r.days);
      END IF;
    END LOOP;
    report(bad = 0 AND n = 60, 'AST table: ' || n || ' values, ' || bad || ' mismatches', 'expected 60 values, 0 mismatches');
  END test_tables;

  -- ------------------------------------------------------------------ 2. scenarios
  PROCEDURE load_wx(p_scn IN VARCHAR2, p_issued IN NUMBER, p_start IN DATE,
                    p_days OUT NOCOPY harvestly_engine.t_weather_tab) IS
    n PLS_INTEGER := 0;
  BEGIN
    FOR r IN (SELECT day_off, temp_c, rh, rain_mm, rain_prob FROM hv_vec_wx
               WHERE scn = p_scn AND issued_off = p_issued ORDER BY day_off) LOOP
      n := n + 1;
      p_days(n).wx_date := p_start + r.day_off;
      p_days(n).temp_c := r.temp_c;
      p_days(n).rh := r.rh;
      p_days(n).rain_mm := r.rain_mm;
      p_days(n).rain_prob := r.rain_prob;
    END LOOP;
  END load_wx;

  PROCEDURE test_scenario(p_scn IN VARCHAR2, p_storage IN VARCHAR2, p_start IN DATE) IS
    b        harvestly_engine.t_batch;
    days     harvestly_engine.t_weather_tab;
    fc       harvestly_engine.t_weather_tab;
    places   harvestly_engine.t_places;
    rain24   harvestly_engine.t_rain24;
    alert    harvestly_engine.t_alert;
    diag     harvestly_engine.t_diag;
    v_cmd    VARCHAR2(20);
    v_today  DATE;
    ok       BOOLEAN;
    v_label  VARCHAR2(200);
    v_detail VARCHAR2(500);
  BEGIN
    b := harvestly_engine.new_batch(0, 1, p_storage, p_start);
    rain24.given := FALSE;
    FOR t IN (SELECT * FROM hv_vec_trace WHERE scn = p_scn ORDER BY seq) LOOP
      v_today := p_start + t.day_off;
      load_wx(p_scn, t.day_off, p_start, days);
      IF t.event = 'reply' THEN
        fc.DELETE;
        FOR k IN 1 .. days.COUNT LOOP
          IF days(k).wx_date > v_today THEN
            fc(fc.COUNT + 1) := days(k);
          END IF;
        END LOOP;
        harvestly_engine.respond(b, t.txt, v_today, fc, places, NULL, v_cmd, alert);
        ok := same_s(v_cmd, t.cmd) AND same_s(alert.code, t.code) AND same_s(alert.msg, t.msg);
        v_label := p_scn || ' d' || t.day_off || ' reply "' || t.txt || '"';
        v_detail := 'cmd ' || v_cmd || '/' || t.cmd || ' code ' || alert.code || '/' || t.code
                 || ' msg [' || alert.msg || '] want [' || t.msg || ']';
        report(ok, v_label || ' -> ' || v_cmd || ' ' || NVL(alert.code, '-'), v_detail || ' (got/want)');
      ELSE
        harvestly_engine.daily_run(b, v_today, days, places, rain24, alert, diag);
        ok := same_s(alert.code, t.code)
          AND same_s(diag.risk, t.risk)
          AND same_n(diag.days_left, t.days_left, 0)
          AND same_s(alert.msg, t.msg)
          AND same_s(harvestly_engine.fmt1(diag.moisture_raw), t.moisture_s)
          AND same_s(harvestly_engine.fmt1(100 * diag.life_used_raw), t.life_s)
          AND same_n(diag.moisture_raw, t.moisture_exact, 0.0001)
          AND same_n(diag.life_used_raw, t.life_exact, 0.000001);
        v_label := p_scn || ' d' || t.day_off || ' evening';
        v_detail := 'code ' || alert.code || '/' || t.code || ' risk ' || diag.risk || '/' || t.risk
                 || ' left ' || diag.days_left || '/' || t.days_left
                 || ' moist ' || diag.moisture || '/' || t.moisture
                 || ' life% ' || diag.life_used_pct || '/' || t.life_pct
                 || ' msg [' || alert.msg || '] want [' || t.msg || ']';
        report(ok, v_label || ' ' || NVL(alert.code, '-') || ' ' || diag.risk || ' left=' || diag.days_left
                   || ' m=' || diag.moisture || ' life=' || diag.life_used_pct || '%',
               v_detail || ' (got/want)');
      END IF;
    END LOOP;
  END test_scenario;

  -- ------------------------------------------------------------------ 3. SMS limits
  PROCEDURE test_sms_limits IS
    b       harvestly_engine.t_batch;
    places  harvestly_engine.t_places;
    no_places harvestly_engine.t_places;
    use_pl  harvestly_engine.t_places;
    a       harvestly_engine.t_alert;
    bad     PLS_INTEGER;
    n       PLS_INTEGER;
    v_left  PLS_INTEGER;
    TYPE t_lefts IS VARRAY(6) OF PLS_INTEGER;
    lefts   t_lefts := t_lefts(0, 1, 2, 89, 90, 365);
    srcs    SYS.ODCIVARCHAR2LIST := SYS.ODCIVARCHAR2LIST('meter', 'hygro', 'salt_flows', 'salt_sticky');

    FUNCTION text_ok(p_text IN VARCHAR2) RETURN BOOLEAN IS
      s PLS_INTEGER := harvestly_engine.sms_segments(p_text);
    BEGIN
      RETURN s BETWEEN 1 AND harvestly_engine.c_sms_max_segments
         AND INSTR(p_text, '{') = 0 AND INSTR(p_text, '}') = 0
         AND INSTR(p_text, '  ') = 0 AND INSTR(p_text, ' .') = 0;
    END;
  BEGIN
    places.stockist := RPAD('X', 32, 'X');
    places.warehouse := RPAD('Y', 30, 'Y');
    places.checkpoint := RPAD('Z', 26, 'Z');
    FOR tpl IN (SELECT DISTINCT code FROM hv_templates ORDER BY code) LOOP
      bad := 0; n := 0;
      FOR si IN 1 .. srcs.COUNT LOOP
        FOR drift IN 0 .. 1 LOOP
          FOR li IN 1 .. lefts.COUNT LOOP
            FOR pl IN 1 .. 2 LOOP
              b := harvestly_engine.new_batch(0, 1, 'sack', DATE '2026-10-12');
              b.source := srcs(si);
              b.test_value := 29.9;
              b.moisture := 29.9 + drift;
              v_left := lefts(li);
              IF pl = 1 THEN use_pl := places; ELSE use_pl := no_places; END IF;
              a := harvestly_engine.render(tpl.code, b, 'HIGH', v_left, DATE '2026-10-12',
                                           use_pl, 120, 100);
              n := n + 1;
              IF NOT (text_ok(a.msg) AND text_ok(a.other)) THEN
                bad := bad + 1;
                IF bad <= 2 THEN
                  DBMS_OUTPUT.PUT_LINE('  bad text (' || tpl.code || '): ' || a.msg);
                END IF;
              END IF;
            END LOOP;
          END LOOP;
        END LOOP;
      END LOOP;
      report(bad = 0, 'sms ' || tpl.code || ': ' || n || ' worst-case fills, GSM-7, <= 2 segments',
             bad || ' of ' || n || ' too long or not GSM-7');
    END LOOP;
  END test_sms_limits;
  -- ------------------------------------------------------------------ 4. vector sections
  PROCEDURE test_sections IS
    bad PLS_INTEGER;
    n   PLS_INTEGER;
    b   harvestly_engine.t_batch;
    fc  harvestly_engine.t_weather_tab;
    v_pepper VARCHAR2(200);
    v_left PLS_INTEGER;
  BEGIN
    bad := 0; n := 0;
    FOR r IN (SELECT * FROM hv_vec_round) LOOP
      n := n + 1;
      IF (r.f0 IS NOT NULL AND harvestly_engine.fmt0(r.x) <> r.f0)
         OR (r.f1 IS NOT NULL AND harvestly_engine.fmt1(r.x) <> r.f1)
         OR (r.f2 IS NOT NULL AND harvestly_engine.fmt2(r.x) <> r.f2) THEN
        bad := bad + 1;
        DBMS_OUTPUT.PUT_LINE('  rounding ' || r.x || ': ' || harvestly_engine.fmt1(r.x) || ' want ' || r.f1);
      END IF;
    END LOOP;
    report(bad = 0 AND n > 0, 'rounding vectors: ' || n || ', ' || bad || ' mismatches');
    -- the whole 5.00 .. 40.00 range, step 0.01, against exact integer arithmetic
    bad := 0;
    FOR h IN 500 .. 4000 LOOP
      IF harvestly_engine.fmt1(h / 100) <> TO_CHAR(FLOOR((h + 5) / 10) / 10, 'FM9999990.0')
         OR harvestly_engine.fmt2(h / 100) <> TO_CHAR(h / 100, 'FM9999990.00')
         OR harvestly_engine.fmt0(h / 100) <> TO_CHAR(FLOOR((h + 50) / 100), 'FM9999990') THEN
        bad := bad + 1;
      END IF;
    END LOOP;
    report(bad = 0, 'rounding fuzz 5.00..40.00 step 0.01: ' || bad || ' divergences');

    bad := 0; n := 0;
    FOR r IN (SELECT * FROM hv_vec_evid) LOOP
      n := n + 1;
      b := harvestly_engine.new_batch(0, 1, 'sack', DATE '2026-10-01');
      b.source := 'meter'; b.moisture := r.reading; b.test_value := r.reading; b.peak_since_test := r.reading;
      IF harvestly_engine.evidence_text(b, TRUE) <> r.en OR harvestly_engine.evidence_text(b, FALSE) <> r.sw THEN
        bad := bad + 1;
        DBMS_OUTPUT.PUT_LINE('  evidence ' || r.reading || ': ' || harvestly_engine.evidence_text(b, TRUE) || ' want ' || r.en);
      END IF;
    END LOOP;
    report(bad = 0 AND n > 0, 'evidence vectors: ' || n || ', ' || bad || ' mismatches');

    bad := 0; n := 0;
    FOR r IN (SELECT * FROM hv_vec_optout ORDER BY seq) LOOP
      n := n + 1;
      IF NVL(harvestly_engine.normalise(r.txt), '~') <> NVL(r.norm, '~')
         OR (CASE WHEN harvestly_engine.is_optout(harvestly_engine.normalise(r.txt)) THEN 1 ELSE 0 END) <> r.optout THEN
        bad := bad + 1;
        DBMS_OUTPUT.PUT_LINE('  optout [' || r.txt || '] norm [' || harvestly_engine.normalise(r.txt) || '] want [' || r.norm || ']');
      END IF;
    END LOOP;
    report(bad = 0 AND n > 0, 'opt-out / normalise vectors: ' || n || ', ' || bad || ' mismatches');

    bad := 0;
    FOR r IN (SELECT * FROM hv_vec_norm) LOOP
      IF LENGTH(NVL(harvestly_engine.normalise(RPAD('A', r.text_len, 'A')), '')) <> r.norm_len THEN
        bad := bad + 1;
      END IF;
    END LOOP;
    report(bad = 0, 'normalise cuts long input to 1000 characters, never raises');

    SELECT v INTO v_pepper FROM hv_vec_cfg WHERE k = 'pepper';
    bad := 0; n := 0;
    FOR r IN (SELECT * FROM hv_vec_addr) LOOP
      n := n + 1;
      IF harvestly_engine.normalise_address(r.addr) <> r.canonical
         OR harvestly_engine.address_hash(r.addr, v_pepper) <> r.hash THEN
        bad := bad + 1;
        DBMS_OUTPUT.PUT_LINE('  address [' || r.addr || '] ' || harvestly_engine.address_hash(r.addr, v_pepper) || ' want ' || r.hash);
      END IF;
    END LOOP;
    report(bad = 0 AND n > 0, 'address canonical form + HMAC-SHA256 hash: ' || n || ', ' || bad || ' mismatches');

    bad := 0; n := 0;
    FOR c IN (SELECT * FROM hv_vec_dl ORDER BY id) LOOP
      n := n + 1;
      b := harvestly_engine.new_batch(0, 1, c.storage, DATE '2026-10-01');
      b.source := 'meter'; b.moisture := c.moisture; b.test_value := c.moisture; b.peak_since_test := c.moisture;
      b.life_used := c.life;
      fc.DELETE;
      FOR f IN (SELECT * FROM hv_vec_dlf WHERE id = c.id ORDER BY seq) LOOP
        fc(f.seq).wx_date := DATE '2026-10-01' + f.seq;
        fc(f.seq).temp_c := f.temp_c;
        fc(f.seq).rh := f.rh;
      END LOOP;
      v_left := harvestly_engine.days_left(b, fc);
      IF v_left <> c.left_days OR harvestly_engine.risk_level(b.life_used, v_left) <> c.lvl THEN
        bad := bad + 1;
        DBMS_OUTPUT.PUT_LINE('  days_left case ' || c.id || ': ' || v_left || ' want ' || c.left_days);
      END IF;
    END LOOP;
    report(bad = 0 AND n > 0, 'days_left cases (incl. 365 horizon): ' || n || ', ' || bad || ' mismatches');
  END test_sections;

  -- ------------------------------------------------------------------ 5. rules without a vector file
  PROCEDURE test_rules IS
    b       harvestly_engine.t_batch;
    days    harvestly_engine.t_weather_tab;
    places  harvestly_engine.t_places;
    rain24  harvestly_engine.t_rain24;
    meta    harvestly_engine.t_weather_meta;
    alert   harvestly_engine.t_alert;
    diag    harvestly_engine.t_diag;
    v_cmd   VARCHAR2(20);
    v_start DATE := DATE '2026-10-12';
    v_n     PLS_INTEGER;
    v_high  PLS_INTEGER := 0;
    v_ok    BOOLEAN;
    v_long  VARCHAR2(4000) := RPAD('x', 4000, 'x');

    PROCEDURE wx(p_today IN DATE, p_t IN NUMBER, p_rh IN NUMBER) IS
    BEGIN
      days.DELETE;
      FOR k IN 1 .. 10 LOOP
        days(k).wx_date := p_today - 3 + k;
        days(k).temp_c := p_t;
        days(k).rh := p_rh;
        days(k).rain_mm := 0;
        days(k).rain_prob := 10;
      END LOOP;
    END wx;
  BEGIN
    -- a long reply never raises (R1-07)
    b := harvestly_engine.new_batch(0, 1, 'sack', v_start);
    harvestly_engine.respond(b, v_long, v_start, days, places, NULL, v_cmd, alert);
    report(v_cmd = 'UNKNOWN' AND alert.code = 'HELP' AND LENGTH(alert.msg) <= 320, 'a 4000-character reply is answered with HELP, no error');

    -- STATUS never says "safe", and says what was measured and when (R1-24)
    b := harvestly_engine.new_batch(0, 1, 'sack', v_start);
    harvestly_engine.respond(b, 'METER 13.1', v_start, days, places, NULL, v_cmd, alert);
    alert := harvestly_engine.render('STATUS', b, 'LOW', 120, v_start, places);
    report(INSTR(LOWER(alert.msg), 'safe') = 0 AND INSTR(alert.msg, 'meter 13.1%') > 0 AND INSTR(alert.msg, '12/10') > 0
           AND INSTR(LOWER(alert.msg), 'will message') = 0,
           'STATUS: no "safe", no promise; names the reading and its date');

    -- HIGH_ALERT: a HIGH batch past its limit is never silent: weekly, at most 4 per test result (R1-08)
    b := harvestly_engine.new_batch(0, 1, 'sack', v_start - 30);
    harvestly_engine.respond(b, 'METER 18', v_start - 30, days, places, NULL, v_cmd, alert);
    b.life_used := 1.2;
    FOR k IN 0 .. 80 LOOP
      wx(v_start + k, 20, 80);
      harvestly_engine.daily_run(b, v_start + k, days, places, rain24, alert, diag);
      IF alert.code = 'HIGH_ALERT' THEN v_high := v_high + 1; END IF;
    END LOOP;
    report(v_high = 4, 'HIGH_ALERT: weekly and capped at 4 (got ' || v_high || ')');

    -- idempotent per day (R1-05): a second run changes and sends nothing
    b := harvestly_engine.new_batch(0, 1, 'drying', v_start);
    wx(v_start, 18, 63);
    harvestly_engine.daily_run(b, v_start, days, places, rain24, alert, diag);
    v_n := b.sent.COUNT;
    harvestly_engine.daily_run(b, v_start, days, places, rain24, alert, diag);
    report(alert.code IS NULL AND b.sent.COUNT = v_n AND INSTR(diag.flags, 'already run today') > 0,
           'daily_run twice on the same day sends once');

    -- stale weather is flagged and suppresses the rain alert (R1-09)
    b := harvestly_engine.new_batch(0, 1, 'drying', v_start);
    harvestly_engine.respond(b, 'SALT YES', v_start, days, places, NULL, v_cmd, alert);
    wx(v_start + 1, 18, 63);
    FOR k IN 1 .. days.COUNT LOOP days(k).rain_prob := 90; END LOOP;
    meta.given := TRUE; meta.fetched_on := v_start - 2; meta.age_hours := 60;
    harvestly_engine.daily_run(b, v_start + 1, days, places, rain24, alert, diag, meta);
    report(diag.weather_stale AND INSTR(diag.flags, 'weather stale') > 0 AND NVL(alert.code, '-') <> 'RAIN_COVER',
           'stale weather: flagged, no rain alert');

    -- the opt-out words (R1-03)
    v_ok := harvestly_engine.is_optout(harvestly_engine.normalise('Please STOP')) AND harvestly_engine.is_optout('ACHA')
        AND harvestly_engine.is_optout('UNSUBSCRIBE') AND NOT harvestly_engine.is_optout('STOPPED');
    report(v_ok, 'opt-out words recognised');
  END test_rules;
BEGIN
  DBMS_OUTPUT.PUT_LINE('=== Harvestly PL/SQL port: golden vectors ===');
  test_tables;
  FOR s IN (SELECT * FROM hv_vec_scn ORDER BY ord) LOOP
    DBMS_OUTPUT.PUT_LINE('--- scenario ' || s.scn || ' (' || s.storage || ', ' || s.n_days || ' days)');
    test_scenario(s.scn, s.storage, s.start_date);
  END LOOP;
  DBMS_OUTPUT.PUT_LINE('--- SMS limits');
  test_sms_limits;
  DBMS_OUTPUT.PUT_LINE('--- vector sections');
  test_sections;
  DBMS_OUTPUT.PUT_LINE('--- rules');
  test_rules;
  DBMS_OUTPUT.PUT_LINE('=== ' || g_pass || ' passed, ' || g_fail || ' failed ===');
  IF g_fail > 0 THEN
    RAISE_APPLICATION_ERROR(-20999, g_fail || ' vector check(s) failed');
  END IF;
END;
/
