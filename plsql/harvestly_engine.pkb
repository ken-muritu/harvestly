CREATE OR REPLACE PACKAGE BODY harvestly_engine AS

  c_max_attempts CONSTANT PLS_INTEGER := 3;      -- a message is tried this many times before it is FAILED
  /* Port of engine/harvestly_engine.py. Section numbers follow the Python module.
     tools/simulate_port.py is a line-by-line Python mirror of this control flow. */

  -- ====================================================================================
  -- 1. Lookup tables, loaded once per session from hv_emc / hv_ast (rows, not code)
  -- ====================================================================================
  TYPE t_num_tab IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
  TYPE t_str_tab IS TABLE OF VARCHAR2(2000) INDEX BY VARCHAR2(80);

  g_emc_t    t_num_tab;     -- air temperature axis (F), 1..g_emc_nt
  g_emc_rh   t_num_tab;     -- RH axis (%), 1..g_emc_nrh
  g_emc_v    t_num_tab;     -- value at (i, j) stored under key i*100 + j
  g_emc_nt   PLS_INTEGER := 0;
  g_emc_nrh  PLS_INTEGER := 0;

  g_ast_t    t_num_tab;     -- grain temperature axis (F)
  g_ast_mc   t_num_tab;     -- moisture axis (% w.b.)
  g_ast_ln   t_num_tab;     -- LN(days) at (i, j), key i*100 + j
  g_ast_nt   PLS_INTEGER := 0;
  g_ast_nmc  PLS_INTEGER := 0;
  g_ln_max   NUMBER;

  g_tpl      t_str_tab;     -- template cache, key code|lang

  -- Patterns are POSIX ERE as used by Oracle REGEXP_*; tools/simulate_port.py runs the same strings.
  c_re_salt_yes CONSTANT VARCHAR2(100) := '^(SALT|CHUMVI) ?(YES|NDIYO|NDIO)($|[^A-Z0-9_])';
  c_re_salt_no  CONSTANT VARCHAR2(100) := '^(SALT|CHUMVI) ?(NO|HAPANA)($|[^A-Z0-9_])';
  -- E5-01: strict readings. The command word claims the message; anything but exactly the expected numbers is INVALID.
  c_re_meter_cmd CONSTANT VARCHAR2(100) := '^(METER|METRE|MITA)($|[^A-Z])';
  c_re_hygro_cmd CONSTANT VARCHAR2(100) := '^HYGRO($|[^A-Z])';
  c_re_meter    CONSTANT VARCHAR2(200) := '^(METER|METRE|MITA) ?([0-9]+([.,][0-9]+)?)%?$';
  c_re_hygro    CONSTANT VARCHAR2(200) := '^HYGRO ?([0-9]+([.,][0-9]+)?)%?( ([0-9]+([.,][0-9]+)?) ?C?)?$';
  -- N6-01: a minus or dash in front of a digit, or a leading '.5' / ',5' (no digit before the point), tested on the raw text (normalise turns every '-' into a space)
  c_re_neg      CONSTANT VARCHAR2(100) := '-[[:space:]]?[0-9]|(^|[^0-9])[.,][0-9]';

  PROCEDURE init_tables IS
    i    PLS_INTEGER := 0;
    j    PLS_INTEGER := 0;
    v_last NUMBER;
    n    PLS_INTEGER := 0;
  BEGIN
    g_emc_t.DELETE; g_emc_rh.DELETE; g_emc_v.DELETE;
    FOR r IN (SELECT temp_f, rh, emc_pct FROM hv_emc ORDER BY temp_f, rh) LOOP
      IF v_last IS NULL OR r.temp_f <> v_last THEN
        i := i + 1; j := 0; g_emc_t(i) := r.temp_f; v_last := r.temp_f;
      END IF;
      j := j + 1;
      g_emc_rh(j) := r.rh;
      g_emc_v(i * 100 + j) := r.emc_pct;
      n := n + 1;
    END LOOP;
    g_emc_nt := i; g_emc_nrh := j;
    IF n = 0 OR n <> g_emc_nt * g_emc_nrh THEN
      RAISE_APPLICATION_ERROR(-20001, 'hv_emc is empty or not a full grid (run schema.sql)');
    END IF;

    i := 0; j := 0; v_last := NULL; n := 0;
    g_ast_t.DELETE; g_ast_mc.DELETE; g_ast_ln.DELETE;
    FOR r IN (SELECT temp_f, mc, days FROM hv_ast ORDER BY temp_f, mc) LOOP
      IF v_last IS NULL OR r.temp_f <> v_last THEN
        i := i + 1; j := 0; g_ast_t(i) := r.temp_f; v_last := r.temp_f;
      END IF;
      j := j + 1;
      g_ast_mc(j) := r.mc;
      g_ast_ln(i * 100 + j) := LN(r.days);
      n := n + 1;
    END LOOP;
    g_ast_nt := i; g_ast_nmc := j;
    IF n = 0 OR n <> g_ast_nt * g_ast_nmc THEN
      RAISE_APPLICATION_ERROR(-20001, 'hv_ast is empty or not a full grid (run schema.sql)');
    END IF;
    g_ln_max := LN(c_max_ast_days);
  END init_tables;

  -- ====================================================================================
  -- small helpers
  -- ====================================================================================
  FUNCTION is_permeable(p_storage IN VARCHAR2) RETURN BOOLEAN IS
  BEGIN
    RETURN p_storage IN ('sack', 'crib', 'floor');
  END;

  FUNCTION is_measured(p_source IN VARCHAR2) RETURN BOOLEAN IS
  BEGIN
    RETURN p_source IN ('meter', 'hygro');
  END;

  FUNCTION level_ord(p_level IN VARCHAR2) RETURN PLS_INTEGER IS
  BEGIN
    RETURN CASE p_level WHEN 'LOW' THEN 0 WHEN 'MEDIUM' THEN 1 WHEN 'HIGH' THEN 2 ELSE -1 END;
  END;

  FUNCTION needs_drying(p_adv IN VARCHAR2) RETURN BOOLEAN IS
  BEGIN
    RETURN p_adv IS NOT NULL AND p_adv IN ('TEST_FIRST', 'DRY_NOW', 'NEARLY_DRY', 'OPEN_AND_DRY');
  END;

  -- PUSHED_ON_CHANGE: pushed when the recommendation changes. NEARLY_DRY / READY_TO_STORE are
  -- answers to a test and go out only as replies, so an estimate hovering around 13.5 % never
  -- causes flip-flop messages.
  FUNCTION pushed_on_change(p_adv IN VARCHAR2) RETURN BOOLEAN IS
  BEGIN
    RETURN p_adv IS NOT NULL AND p_adv IN ('DRY_NOW', 'RETEST', 'SORT_AND_SELL', 'OPEN_AND_DRY', 'CONFIRM_DRY');
  END;

  FUNCTION is_advice_code(p_code IN VARCHAR2) RETURN BOOLEAN IS
  BEGIN
    RETURN pushed_on_change(p_code) OR p_code IN ('TEST_FIRST', 'NEARLY_DRY', 'READY_TO_STORE', 'STATUS');
  END;

  FUNCTION c_to_f(p_c IN NUMBER) RETURN NUMBER IS
  BEGIN
    RETURN p_c * 9 / 5 + 32;
  END;

  -- The ONE rounding rule (Python fmt()): correct the binary noise to 10 decimals, then round half up on the
  -- decimal value. Oracle ROUND is half away from zero, i.e. half up for the non-negative values shown.
  FUNCTION fmt0(p_x IN NUMBER) RETURN VARCHAR2 IS
  BEGIN
    RETURN TO_CHAR(ROUND(ROUND(p_x, 10), 0), 'FM9999990');
  END;

  FUNCTION fmt1(p_x IN NUMBER) RETURN VARCHAR2 IS
  BEGIN
    RETURN TO_CHAR(ROUND(ROUND(p_x, 10), 1), 'FM9999990.0');
  END;

  FUNCTION fmt2(p_x IN NUMBER) RETURN VARCHAR2 IS
  BEGIN
    RETURN TO_CHAR(ROUND(ROUND(p_x, 10), 2), 'FM9999990.00');
  END;

  FUNCTION no_meta RETURN t_weather_meta IS
    m t_weather_meta;
  BEGIN
    RETURN m;
  END no_meta;

  -- Tables and templates are cached per session. After editing hv_emc / hv_ast / hv_templates call this
  -- (a recompile of the package still raises ORA-04068 once per pooled session; retry the call).
  PROCEDURE reset_cache IS
  BEGIN
    g_tpl.DELETE;
    init_tables;
  END reset_cache;

  FUNCTION today_eat RETURN DATE IS
  BEGIN
    RETURN TRUNC(CAST(SYSTIMESTAMP AT TIME ZONE 'Africa/Nairobi' AS DATE));
  END;

  PROCEDURE add_sent(b IN OUT NOCOPY t_batch, p_date IN DATE, p_code IN VARCHAR2) IS
    n PLS_INTEGER := b.sent.COUNT + 1;
  BEGIN
    b.sent(n).sent_date := p_date;
    b.sent(n).code := p_code;
  END;

  FUNCTION make_undo(b IN t_batch) RETURN t_undo IS
    u t_undo;
  BEGIN
    u.present := TRUE;
    u.sent_len := b.sent.COUNT;
    u.last_alert := b.last_alert;
    u.last_advice := b.last_advice;
    u.told_level := b.told_level;
    u.told_left := b.told_left;
    u.rain_unacked := b.rain_unacked;
    RETURN u;
  END make_undo;

  PROCEDURE revert_undelivered(b IN OUT NOCOPY t_batch, p_undo IN t_undo) IS
  BEGIN
    IF NOT p_undo.present THEN
      RETURN;
    END IF;
    IF p_undo.sent_len < b.sent.COUNT THEN            -- take the entry out of the send history, close the gap
      FOR k IN p_undo.sent_len + 1 .. b.sent.COUNT - 1 LOOP
        b.sent(k) := b.sent(k + 1);
      END LOOP;
      b.sent.DELETE(b.sent.COUNT);
    END IF;
    b.last_alert := p_undo.last_alert;
    b.last_advice := p_undo.last_advice;
    b.told_level := p_undo.told_level;
    b.told_left := p_undo.told_left;
    b.rain_unacked := p_undo.rain_unacked;
  END revert_undelivered;

  -- ====================================================================================
  -- 3. Physics
  -- ====================================================================================
  -- Index i and fraction t so that x = axis(i) + t*(axis(i+1)-axis(i)); t<0 or >1 only at the edges.
  PROCEDURE bracket(p_axis IN t_num_tab, p_n IN PLS_INTEGER, p_x IN NUMBER,
                    p_i OUT PLS_INTEGER, p_t OUT NUMBER) IS
  BEGIN
    IF p_x <= p_axis(1) THEN
      p_i := 1;
    ELSIF p_x >= p_axis(p_n) THEN
      p_i := p_n - 1;
    ELSE
      p_i := 1;
      FOR k IN 1 .. p_n - 1 LOOP
        IF p_axis(k) <= p_x THEN p_i := k; END IF;      -- the largest k with axis(k) <= x
      END LOOP;
    END IF;
    p_t := (p_x - p_axis(p_i)) / (p_axis(p_i + 1) - p_axis(p_i));
  END bracket;

  FUNCTION emc(p_temp_c IN NUMBER, p_rh IN NUMBER, p_warn OUT VARCHAR2) RETURN NUMBER IS
    tf  NUMBER;
    rh  NUMBER := p_rh;
    i   PLS_INTEGER; j PLS_INTEGER;
    ti  NUMBER;      tj NUMBER;
    top NUMBER;      bot NUMBER;
  BEGIN
    p_warn := NULL;
    tf := c_to_f(p_temp_c);
    IF NOT (g_emc_t(1) <= tf AND tf <= g_emc_t(g_emc_nt)) THEN
      p_warn := p_warn || 'EMC temperature clamped;';
      tf := LEAST(GREATEST(tf, g_emc_t(1)), g_emc_t(g_emc_nt));
    END IF;
    IF NOT (g_emc_rh(1) <= rh AND rh <= g_emc_rh(g_emc_nrh)) THEN
      p_warn := p_warn || 'EMC humidity clamped;';
      rh := LEAST(GREATEST(rh, g_emc_rh(1)), g_emc_rh(g_emc_nrh));
    END IF;
    bracket(g_emc_t, g_emc_nt, tf, i, ti);
    bracket(g_emc_rh, g_emc_nrh, rh, j, tj);
    top := g_emc_v(i * 100 + j)       + tj * (g_emc_v(i * 100 + j + 1)       - g_emc_v(i * 100 + j));
    bot := g_emc_v((i + 1) * 100 + j) + tj * (g_emc_v((i + 1) * 100 + j + 1) - g_emc_v((i + 1) * 100 + j));
    RETURN top + ti * (bot - top);
  END emc;

  FUNCTION emc(p_temp_c IN NUMBER, p_rh IN NUMBER) RETURN NUMBER IS
    w VARCHAR2(200);
  BEGIN
    RETURN emc(p_temp_c, p_rh, w);
  END emc;

  FUNCTION ast_days(p_temp_c IN NUMBER, p_mc IN NUMBER, p_warn OUT VARCHAR2) RETURN NUMBER IS
    tf  NUMBER;
    m   NUMBER;
    i   PLS_INTEGER; j PLS_INTEGER;
    ti  NUMBER;      tj NUMBER;
    top NUMBER;      bot NUMBER;
    x   NUMBER;
  BEGIN
    p_warn := NULL;
    tf := c_to_f(p_temp_c);
    IF tf > g_ast_t(g_ast_nt) THEN
      p_warn := p_warn || 'AST temperature extrapolated;';
    END IF;
    IF tf < g_ast_t(1) THEN
      tf := g_ast_t(1);
      p_warn := p_warn || 'AST temperature clamped;';
    END IF;
    m := p_mc;
    IF m > g_ast_mc(g_ast_nmc) THEN
      m := g_ast_mc(g_ast_nmc);
      p_warn := p_warn || 'AST moisture clamped;';
    END IF;
    IF m < g_ast_mc(1) THEN
      p_warn := p_warn || 'AST moisture extrapolated;';
    END IF;
    bracket(g_ast_t, g_ast_nt, tf, i, ti);
    bracket(g_ast_mc, g_ast_nmc, m, j, tj);
    top := g_ast_ln(i * 100 + j)       + tj * (g_ast_ln(i * 100 + j + 1)       - g_ast_ln(i * 100 + j));
    bot := g_ast_ln((i + 1) * 100 + j) + tj * (g_ast_ln((i + 1) * 100 + j + 1) - g_ast_ln((i + 1) * 100 + j));
    x := top + ti * (bot - top);
    IF x >= g_ln_max THEN            -- min(exp(x), MAX_AST_DAYS), without risking EXP overflow
      RETURN c_max_ast_days;
    END IF;
    RETURN EXP(x);
  END ast_days;

  FUNCTION ast_days(p_temp_c IN NUMBER, p_mc IN NUMBER) RETURN NUMBER IS
    w VARCHAR2(200);
  BEGIN
    RETURN ast_days(p_temp_c, p_mc, w);
  END ast_days;

  -- ====================================================================================
  -- 4. State
  -- ====================================================================================
  FUNCTION new_batch(p_batch_id IN NUMBER, p_ward_id IN NUMBER, p_storage IN VARCHAR2,
                     p_stored_since IN DATE, p_lang IN VARCHAR2 DEFAULT 'en') RETURN t_batch IS
    b t_batch;
  BEGIN
    IF p_storage IS NULL OR p_storage NOT IN ('drying', 'sack', 'crib', 'floor', 'hermetic') THEN
      RAISE_APPLICATION_ERROR(-20001, 'unknown storage type ' || p_storage);
    END IF;
    IF p_lang IS NULL OR p_lang NOT IN ('en', 'sw') THEN
      RAISE_APPLICATION_ERROR(-20001, 'lang must be en or sw');
    END IF;
    b.batch_id := p_batch_id;
    b.ward_id := p_ward_id;
    b.storage := p_storage;
    b.stored_since := TRUNC(p_stored_since);
    b.lang := p_lang;
    RETURN b;
  END new_batch;

  -- True if the estimate has risen well past the salt line since the last (dry) test,
  -- so that test can no longer vouch for the grain.
  FUNCTION stale(b IN t_batch) RETURN BOOLEAN IS
  BEGIN
    RETURN b.peak_since_test IS NOT NULL AND b.peak_since_test > c_salt_line_mc + c_retest_margin;
  END stale;

  -- What the farmer's LAST TEST says (never the estimate): UNTESTED | WET | NOT_PROVEN | DRY.
  FUNCTION verdict(b IN t_batch) RETURN VARCHAR2 IS
  BEGIN
    IF b.moisture IS NULL THEN
      RETURN 'UNTESTED';
    END IF;
    IF b.source = 'salt_sticky' OR b.test_value > c_salt_line_mc THEN
      RETURN 'WET';
    END IF;
    IF is_measured(b.source) AND b.test_value <= c_eas_max_mc AND NOT stale(b) THEN
      RETURN 'DRY';
    END IF;
    RETURN 'NOT_PROVEN';        -- salt flows, a reading of 13.5-15 %, or a test since outdated
  END verdict;

  FUNCTION count_sent(b IN t_batch, p_code IN VARCHAR2, p_since IN DATE DEFAULT NULL) RETURN PLS_INTEGER IS
    n PLS_INTEGER := 0;
  BEGIN
    FOR k IN 1 .. b.sent.COUNT LOOP
      IF b.sent(k).code = p_code AND (p_since IS NULL OR b.sent(k).sent_date >= p_since) THEN
        n := n + 1;
      END IF;
    END LOOP;
    RETURN n;
  END count_sent;

  -- ---- moisture inputs -------------------------------------------------------------
  PROCEDURE set_moisture(b IN OUT NOCOPY t_batch, p_on IN DATE, p_mc IN NUMBER, p_source IN VARCHAR2) IS
  BEGIN
    IF b.last_advanced IS NULL THEN          -- start the clock on the first test
      b.last_advanced := p_on - 1;
    END IF;
    b.moisture := p_mc;
    b.source := p_source;
    b.last_test := p_on;
    b.test_value := p_mc;
    b.peak_since_test := p_mc;
  END set_moisture;

  -- Returns FALSE if 'salt flows' was ignored: a meter/hygrometer reading of 15 % or less in the
  -- last 7 days is more informative, unless the estimate has since risen past 15 %.
  -- 'Salt sticks' always counts: it is the conservative direction.
  FUNCTION record_salt(b IN OUT NOCOPY t_batch, p_on IN DATE, p_sticky IN BOOLEAN) RETURN BOOLEAN IS
  BEGIN
    IF (NOT p_sticky AND is_measured(b.source) AND b.test_value <= c_salt_line_mc
        AND b.moisture <= c_salt_line_mc AND (p_on - b.last_test) <= 7) THEN
      RETURN FALSE;
    END IF;
    IF p_sticky THEN
      set_moisture(b, p_on, c_salt_sticky_mc, 'salt_sticky');
    ELSE
      set_moisture(b, p_on, c_salt_flows_mc, 'salt_flows');
    END IF;
    RETURN TRUE;
  END record_salt;

  PROCEDURE record_meter(b IN OUT NOCOPY t_batch, p_on IN DATE, p_reading IN NUMBER) IS
  BEGIN
    IF NOT (5.0 <= p_reading AND p_reading <= 40.0) THEN
      RAISE_APPLICATION_ERROR(-20001, 'moisture meter reading must be between 5 and 40 %');
    END IF;
    set_moisture(b, p_on, p_reading, 'meter');
  END record_meter;

  -- Hygrometer sealed in a bag of grain until steady (Tubbs et al. 2017: 15-45 min).
  PROCEDURE record_hygro(b IN OUT NOCOPY t_batch, p_on IN DATE, p_rh IN NUMBER, p_temp_c IN NUMBER) IS
    rh_c NUMBER := p_rh + 0.0;       -- offset = calibration correction from the salt check (default 0)
  BEGIN
    IF NOT (0.0 < rh_c AND rh_c < 100.0) OR NOT (-5.0 <= p_temp_c AND p_temp_c <= 45.0) THEN
      RAISE_APPLICATION_ERROR(-20001, 'hygrometer reading out of range');
    END IF;
    set_moisture(b, p_on, emc(p_temp_c, rh_c), 'hygro');
  END record_hygro;

  PROCEDURE set_storage(b IN OUT NOCOPY t_batch, p_on IN DATE, p_storage IN VARCHAR2) IS
  BEGIN
    IF p_storage NOT IN ('drying', 'sack', 'crib', 'floor', 'hermetic') THEN
      RAISE_APPLICATION_ERROR(-20001, 'unknown storage type ' || p_storage);
    END IF;
    IF p_storage <> b.storage THEN
      b.storage := p_storage;
      b.stored_since := p_on;
    END IF;
  END set_storage;

  -- ====================================================================================
  -- 5. Daily simulation
  -- ====================================================================================
  -- Move the batch through day w.wx_date. Idempotent: a day is never counted twice.
  PROCEDURE advance_day(b IN OUT NOCOPY t_batch, w IN t_weather_day) IS
  BEGIN
    IF b.moisture IS NULL OR b.status <> 'active' THEN
      RETURN;
    END IF;
    IF b.last_advanced IS NOT NULL AND w.wx_date <= b.last_advanced THEN
      RETURN;
    END IF;
    IF is_permeable(b.storage) THEN
      b.moisture := b.moisture + c_sack_exchange_rate * (emc(w.temp_c, w.rh) - b.moisture);
      b.peak_since_test := GREATEST(b.peak_since_test, b.moisture);
    END IF;
    -- drying: moisture changes only with the next test (sun-drying is too variable to model;
    -- holding it constant is the conservative choice). hermetic: no exchange with outside air.
    b.life_used := b.life_used + 1 / ast_days(w.temp_c, b.moisture);
    b.last_advanced := w.wx_date;
  END advance_day;

  -- Days until life_used reaches 1: the forecast first, then the forecast mean repeated.
  -- NULL if the batch is untested or there is no forecast.
  FUNCTION days_left(b IN t_batch, p_forecast IN t_weather_tab) RETURN PLS_INTEGER IS
    n_fc   PLS_INTEGER := p_forecast.COUNT;
    sum_t  NUMBER := 0;
    sum_rh NUMBER := 0;
    mean_t NUMBER;
    mean_rh NUMBER;
    used   NUMBER;
    m      NUMBER;
    t      NUMBER;
    rh     NUMBER;
  BEGIN
    IF b.moisture IS NULL OR n_fc = 0 THEN
      RETURN NULL;
    END IF;
    IF b.life_used >= 1.0 THEN
      RETURN 0;
    END IF;
    FOR k IN 1 .. n_fc LOOP
      sum_t := sum_t + p_forecast(k).temp_c;
      sum_rh := sum_rh + p_forecast(k).rh;
    END LOOP;
    mean_t := sum_t / n_fc;
    mean_rh := sum_rh / n_fc;
    used := b.life_used;
    m := b.moisture;
    FOR n IN 0 .. c_horizon_days - 1 LOOP
      IF n < n_fc THEN
        t := p_forecast(n + 1).temp_c;
        rh := p_forecast(n + 1).rh;
      ELSE
        t := mean_t;
        rh := mean_rh;
      END IF;
      IF is_permeable(b.storage) THEN
        m := m + c_sack_exchange_rate * (emc(t, rh) - m);
      END IF;
      used := used + 1 / ast_days(t, m);
      IF used >= 1.0 THEN
        RETURN n + 1;
      END IF;
    END LOOP;
    RETURN c_horizon_days;
  END days_left;

  FUNCTION risk_level(p_life_used IN NUMBER, p_left IN PLS_INTEGER) RETURN VARCHAR2 IS
  BEGIN
    IF p_left IS NULL THEN
      RETURN 'UNKNOWN';
    END IF;
    IF p_life_used >= c_high_life OR p_left <= c_high_days THEN
      RETURN 'HIGH';
    END IF;
    IF p_life_used >= c_medium_life OR p_left <= c_medium_days THEN
      RETURN 'MEDIUM';
    END IF;
    RETURN 'LOW';
  END risk_level;

  -- ====================================================================================
  -- 6. The single current recommendation (NULL = nothing: grain measured safe in sealed bags)
  -- ====================================================================================
  FUNCTION advice(b IN t_batch) RETURN VARCHAR2 IS
    v     VARCHAR2(12) := verdict(b);
    fresh BOOLEAN;
  BEGIN
    IF v = 'UNTESTED' THEN
      RETURN 'TEST_FIRST';
    END IF;
    IF b.life_used >= c_high_life THEN
      RETURN 'SORT_AND_SELL';
    END IF;
    IF b.storage = 'hermetic' THEN
      fresh := is_measured(b.source) AND NOT stale(b);
      IF v = 'WET' OR (fresh AND b.test_value >= c_hermetic_max_mc) THEN
        RETURN 'OPEN_AND_DRY';           -- the last test said too wet to seal
      END IF;
      IF fresh AND b.moisture < c_hermetic_max_mc THEN
        RETURN NULL;                     -- measured below 14 % and not re-wetted before sealing
      END IF;
      RETURN 'CONFIRM_DRY';              -- salt test only, or re-wetted in sacks before sealing
    END IF;
    IF v = 'WET' THEN                    -- test says wet; in sacks it may have dried since
      IF is_permeable(b.storage) AND b.moisture < c_salt_line_mc - c_retest_margin THEN
        RETURN 'RETEST';
      END IF;
      RETURN 'DRY_NOW';
    END IF;
    IF is_permeable(b.storage) AND b.moisture > c_salt_line_mc + c_retest_margin THEN
      RETURN 'RETEST';                   -- test says dry, estimate says it has re-wetted: verify
    END IF;
    IF v = 'DRY' AND b.moisture <= c_eas_max_mc THEN
      RETURN 'READY_TO_STORE';
    END IF;
    RETURN 'NEARLY_DRY';
  END advice;

  -- ====================================================================================
  -- 7. Messages (GSM-7 only, max 2 SMS segments after filling)
  -- ====================================================================================
  -- Directory names: plain GSM-7 characters only, at most c_place_max_chars.
  FUNCTION sanitise_place(p_name IN VARCHAR2) RETURN VARCHAR2 IS
    s VARCHAR2(4000);
    r VARCHAR2(4000);
    c VARCHAR2(4);
    a PLS_INTEGER;
  BEGIN
    IF p_name IS NULL THEN
      RETURN NULL;
    END IF;
    -- curly quotes, en/em dash and no-break space -> plain ASCII  (the Python _TRANSLIT table)
    s := TRANSLATE(p_name, UNISTR('\2019\2018\201C\201D\2013\2014\00A0'),
                   CHR(39) || CHR(39) || CHR(34) || CHR(34) || '-- ');
    FOR k IN 1 .. LENGTH(s) LOOP
      c := SUBSTR(s, k, 1);
      a := ASCII(c);
      IF (a BETWEEN 65 AND 90) OR (a BETWEEN 97 AND 122) OR (a BETWEEN 48 AND 57)
         OR c IN (' ', '.', ',', ':', ';', '!', '?', CHR(39), '(', ')', CHR(38), '/', '+', '-', '%', '@',
                  CHR(34), '#', '*', '=', '<', '>') THEN
        r := r || c;
      END IF;
    END LOOP;
    r := TRIM(REGEXP_REPLACE(r, ' {2,}', ' '));
    r := SUBSTR(r, 1, c_place_max_chars);
    RETURN RTRIM(r, ' ,.-');
  END sanitise_place;

  FUNCTION get_template(p_code IN VARCHAR2, p_lang IN VARCHAR2) RETURN VARCHAR2 IS
    k VARCHAR2(80) := p_code || '|' || p_lang;
    v VARCHAR2(2000);
  BEGIN
    IF g_tpl.EXISTS(k) THEN
      RETURN g_tpl(k);
    END IF;
    BEGIN
      SELECT body INTO v FROM hv_templates WHERE code = p_code AND lang = p_lang;
    EXCEPTION WHEN NO_DATA_FOUND THEN
      RAISE_APPLICATION_ERROR(-20001, 'no template ' || k);
    END;
    g_tpl(k) := v;
    RETURN v;
  END get_template;

  -- A moisture for the farmer: one decimal, but two when one decimal would hide which side of a limit the
  -- number is on (13.54 shown as 13.5 next to "the limit is 13.5"). Decided on the rounded strings.
  FUNCTION pct_text(p_x IN NUMBER) RETURN VARCHAR2 IS
    v_one VARCHAR2(20) := fmt1(p_x);
  BEGIN
    IF v_one IN ('13.5', '14.0', '15.0') AND fmt2(p_x) <> v_one || '0' THEN
      RETURN fmt2(p_x);
    END IF;
    RETURN v_one;
  END pct_text;

  -- What the numbers rest on. p_tested = TRUE describes the farmer's last TEST, ignoring any drift since.
  FUNCTION evidence(b IN t_batch, p_en IN BOOLEAN, p_tested IN BOOLEAN DEFAULT FALSE) RETURN VARCHAR2 IS
    drifted BOOLEAN := NOT p_tested AND ABS(b.moisture - b.test_value) >= 0.05;
    word    VARCHAR2(20);
  BEGIN
    IF is_measured(b.source) THEN
      IF drifted THEN
        RETURN CASE WHEN p_en THEN 'estimate ' ELSE 'makadirio ' END || pct_text(b.moisture) || '%';
      END IF;
      IF b.source = 'meter' THEN
        word := CASE WHEN p_en THEN 'meter' ELSE 'mita' END;
      ELSE
        word := CASE WHEN p_en THEN 'hygrometer' ELSE 'haigromita' END;
      END IF;
      RETURN word || ' ' || pct_text(b.test_value) || '%';
    END IF;
    IF drifted THEN
      RETURN CASE WHEN p_en THEN 'estimate from salt test' ELSE 'makadirio ya kipimo cha chumvi' END;
    END IF;
    IF b.source = 'salt_flows' THEN
      RETURN CASE WHEN p_en THEN 'salt test: below about 15%' ELSE 'kipimo cha chumvi: chini ya 15% hivi' END;
    END IF;
    RETURN CASE WHEN p_en THEN 'salt test: above 15%' ELSE 'kipimo cha chumvi: zaidi ya 15%' END;
  END evidence;

  FUNCTION evidence_text(b IN t_batch, p_en IN BOOLEAN) RETURN VARCHAR2 IS
  BEGIN
    RETURN evidence(b, p_en, FALSE);
  END evidence_text;

  -- 'meter 13.1% on 12/10': what was measured and when.
  FUNCTION measured_text(b IN t_batch, p_en IN BOOLEAN) RETURN VARCHAR2 IS
    ev VARCHAR2(200) := evidence(b, p_en, TRUE);
  BEGIN
    IF b.last_test IS NULL THEN
      RETURN ev;
    END IF;
    RETURN ev || ' ' || CASE WHEN p_en THEN 'on' ELSE 'tarehe' END || ' ' || TO_CHAR(b.last_test, 'DD/MM');
  END measured_text;

  -- The estimated storage time left, always labelled an estimate. Never the word "safe".
  FUNCTION risk_text(p_left IN PLS_INTEGER, p_en IN BOOLEAN, p_tracks_air IN BOOLEAN DEFAULT TRUE) RETURN VARCHAR2 IS
  BEGIN
    IF p_left IS NULL THEN
      RETURN CASE WHEN p_en THEN 'not available today' ELSE 'haipatikani leo' END;
    END IF;
    IF p_left <= 0 THEN
      RETURN CASE WHEN p_en THEN 'used up (estimate)' ELSE 'umeisha (makadirio)' END;
    END IF;
    IF p_left >= 90 THEN
      -- S3-01: a sealed bag does not follow the air, and a countdown at the horizon cap is not a prediction
      IF NOT p_tracks_air OR p_left >= c_horizon_days THEN
        RETURN CASE WHEN p_en THEN '3 months or more' ELSE 'miezi 3 au zaidi' END;
      END IF;
      RETURN CASE WHEN p_en THEN '3 months or more, falling fast in damp weather'
                  ELSE 'miezi 3 au zaidi, hupungua haraka kukiwa na unyevu' END;
    END IF;
    IF p_en THEN
      RETURN 'about ' || p_left || ' day' || CASE WHEN p_left > 1 THEN 's' ELSE '' END || ' (estimate)';
    END IF;
    RETURN 'siku ' || p_left || ' hivi (makadirio)';
  END risk_text;

  FUNCTION rain_text(p_mm IN NUMBER, p_prob IN NUMBER, p_en IN BOOLEAN) RETURN VARCHAR2 IS
  BEGIN
    IF p_prob IS NOT NULL AND p_prob >= c_rain_prob_alert THEN
      RETURN CASE WHEN p_en THEN fmt0(p_prob) || '% chance' ELSE 'uwezekano ' || fmt0(p_prob) || '%' END;
    END IF;
    RETURN CASE WHEN p_en THEN fmt0(NVL(p_mm, 0)) || ' mm expected'
                ELSE 'mm ' || fmt0(NVL(p_mm, 0)) || ' zinatarajiwa' END;
  END rain_text;

  FUNCTION render(p_code IN VARCHAR2, b IN t_batch, p_risk IN VARCHAR2, p_left IN PLS_INTEGER,
                  p_today IN DATE, p_places IN t_places, p_rain_mm IN NUMBER DEFAULT NULL,
                  p_rain_prob IN NUMBER DEFAULT NULL, p_rain_window IN BOOLEAN DEFAULT TRUE,
                  p_meta IN t_weather_meta DEFAULT no_meta) RETURN t_alert IS
    v_stockist   VARCHAR2(100) := sanitise_place(p_places.stockist);
    v_warehouse  VARCHAR2(100) := sanitise_place(p_places.warehouse);
    v_checkpoint VARCHAR2(100) := sanitise_place(p_places.checkpoint);
    v_wdate  DATE := NVL(CASE WHEN p_meta.given THEN p_meta.fetched_on END, p_today);
    v_credit VARCHAR2(40) := CASE WHEN p_meta.given THEN p_meta.credit ELSE c_credit_open_meteo END;
    v_nth    PLS_INTEGER := count_sent(b, 'HIGH_ALERT', NVL(b.last_test, DATE '0001-01-01')) + 1;
    v_en  VARCHAR2(2000);
    v_sw  VARCHAR2(2000);
    v_dried BOOLEAN;
    a     t_alert;

    FUNCTION fill(p_lang IN VARCHAR2) RETURN VARCHAR2 IS
      en BOOLEAN := (p_lang = 'en');
      t  VARCHAR2(2000) := get_template(p_code, p_lang);
    BEGIN
      t := REPLACE(t, '{stockist}', NVL(v_stockist, CASE WHEN en THEN c_place_stockist_en ELSE c_place_stockist_sw END));
      t := REPLACE(t, '{warehouse}', NVL(v_warehouse, CASE WHEN en THEN c_place_warehouse_en ELSE c_place_warehouse_sw END));
      t := REPLACE(t, '{checkpoint}', NVL(v_checkpoint, CASE WHEN en THEN c_place_checkpoint_en ELSE c_place_checkpoint_sw END));
      t := REPLACE(t, '{date}', TO_CHAR(v_wdate, 'DD/MM'));
      t := REPLACE(t, '{credit}', v_credit);
      t := REPLACE(t, '{rain}', rain_text(p_rain_mm, p_rain_prob, en));
      t := REPLACE(t, '{rain_when}', CASE WHEN p_rain_window THEN CASE WHEN en THEN 'in the next 24 hours' ELSE 'ndani ya saa 24' END
                                          ELSE CASE WHEN en THEN 'tomorrow' ELSE 'kesho' END END);
      t := REPLACE(t, '{risk}', risk_text(p_left, en, b.storage <> 'hermetic'));
      t := REPLACE(t, '{weeks}', TO_CHAR(LEAST(FLOOR((p_today - b.stored_since) / 7), c_weeks_cap)));
      t := REPLACE(t, '{closing}', CASE WHEN v_nth >= c_high_alert_max
                                        THEN CASE WHEN en THEN 'Our last reminder. Retest: reply e.g. METER 14.2 (your own reading) or SALT YES/NO to restart.'
                                                  ELSE 'Ukumbusho wa mwisho. Pima tena: mf. MITA 14.2 au CHUMVI NDIYO/HAPANA kuziwasha.' END
                                        ELSE CASE WHEN en THEN 'Reminders are weekly, at most 4.' ELSE 'Ukumbusho: kila wiki, hadi mara 4.' END END);
      t := REPLACE(t, '{reply_drying}', CASE WHEN b.storage = 'drying' THEN ''
                                             ELSE CASE WHEN en THEN ' and reply DRYING' ELSE ' na ujibu ANIKA' END END);
      IF b.moisture IS NOT NULL THEN
        t := REPLACE(t, '{evidence}', evidence(b, en));
        t := REPLACE(t, '{measured}', measured_text(b, en));
        IF en THEN
          t := REPLACE(t, '{why}', CASE WHEN v_dried THEN 'Your stored maize may have dried out'
                                        ELSE 'Damp air has probably re-wetted your stored maize' END);
        ELSE
          t := REPLACE(t, '{why}', CASE WHEN v_dried THEN 'Huenda mahindi yako ghalani yamekauka'
                                        ELSE 'Hewa yenye unyevu huenda imeongeza unyevu wa mahindi yako ghalani' END);
        END IF;
      END IF;
      RETURN t;
    END fill;
  BEGIN
    IF b.moisture IS NOT NULL THEN
      v_dried := (verdict(b) = 'WET');
    END IF;
    v_en := fill('en');
    v_sw := fill('sw');
    a.code := p_code;
    a.risk := p_risk;
    IF b.lang = 'en' THEN
      a.msg := v_en;  a.other := v_sw;
    ELSE
      a.msg := v_sw;  a.other := v_en;
    END IF;
    RETURN a;
  END render;

  -- The first message after registration: what this is, the weather credit, how to stop.
  FUNCTION welcome(b IN t_batch, p_today IN DATE) RETURN t_alert IS
    v_places t_places;
  BEGIN
    RETURN render('WELCOME', b, 'UNKNOWN', NULL, p_today, v_places);
  END welcome;

  -- GSM 03.38: number of SMS segments, or 0 if any character forces UCS-2.
  FUNCTION sms_segments(p_text IN VARCHAR2) RETURN PLS_INTEGER IS
    c_basic CONSTANT VARCHAR2(400) :=
      '@$_ !"#%' || CHR(38) || '''()*+,-./0123456789:;<=>?ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz' ||
      CHR(10) || CHR(13) ||
      UNISTR('\00A3\00A5\00E8\00E9\00F9\00EC\00F2\00C7\00D8\00F8\00C5\00E5\0394\03A6\0393\039B\03A9\03A0\03A8\03A3\0398\039E\00C6\00E6\00DF\00C9\00A4\00A1\00C4\00D6\00D1\00DC\00A7\00BF\00E4\00F6\00F1\00FC\00E0');
    c_ext   CONSTANT VARCHAR2(40) := '^{}\[~]|' || UNISTR('\20AC');
    n  PLS_INTEGER := 0;
    ch VARCHAR2(4);
  BEGIN
    FOR k IN 1 .. NVL(LENGTH(p_text), 0) LOOP
      ch := SUBSTR(p_text, k, 1);
      IF INSTR(c_basic, ch) > 0 THEN
        n := n + 1;
      ELSIF INSTR(c_ext, ch) > 0 THEN
        n := n + 2;
      ELSE
        RETURN 0;
      END IF;
    END LOOP;
    RETURN CASE WHEN n <= c_sms_gsm7_single THEN 1 ELSE CEIL(n / 153) END;
  END sms_segments;

  -- ====================================================================================
  -- 8. When to send: the evening job's decision
  -- ====================================================================================
  -- True if `code` was not sent in the last `gap` days.
  FUNCTION quiet_for(b IN t_batch, p_code IN VARCHAR2, p_today IN DATE, p_gap IN NUMBER) RETURN BOOLEAN IS
  BEGIN
    RETURN count_sent(b, p_code, p_today - (p_gap - 1)) = 0;
  END quiet_for;

  -- Repeats of a warning: spaced by `gap` days, at most c_repeat_max after the first, per test result.
  FUNCTION repeat_ok(b IN t_batch, p_code IN VARCHAR2, p_today IN DATE, p_gap IN NUMBER) RETURN BOOLEAN IS
  BEGIN
    RETURN quiet_for(b, p_code, p_today, p_gap)
       AND count_sent(b, p_code, NVL(b.last_test, DATE '0001-01-01')) <= c_repeat_max;
  END repeat_ok;

  PROCEDURE add_flag(p_flags IN OUT VARCHAR2, p_warn IN VARCHAR2, p_token IN VARCHAR2) IS
  BEGIN
    IF INSTR(p_warn, p_token || ';') > 0 THEN
      p_flags := CASE WHEN p_flags IS NULL THEN p_token ELSE p_flags || '; ' || p_token END;
    END IF;
  END add_flag;

  FUNCTION build_diag(b IN t_batch, p_left IN PLS_INTEGER, p_risk IN VARCHAR2, p_adv IN VARCHAR2,
                      p_tomorrow IN t_weather_day) RETURN t_diag IS
    d  t_diag;
    w1 VARCHAR2(200);
    w2 VARCHAR2(200);
    w  VARCHAR2(400);
    e  NUMBER;
  BEGIN
    IF b.moisture IS NOT NULL THEN
      e := ast_days(p_tomorrow.temp_c, b.moisture, w1);
      e := emc(p_tomorrow.temp_c, p_tomorrow.rh, w2);
      w := w1 || w2;
      -- sorted(set(...)) in the Python: plain ASCII order of the flag texts
      add_flag(d.flags, w, 'AST moisture clamped');
      add_flag(d.flags, w, 'AST moisture extrapolated');
      add_flag(d.flags, w, 'AST temperature clamped');
      add_flag(d.flags, w, 'AST temperature extrapolated');
      add_flag(d.flags, w, 'EMC humidity clamped');
      add_flag(d.flags, w, 'EMC temperature clamped');
    END IF;
    d.moisture := ROUND(ROUND(b.moisture, 10), 1);          -- fmt1 as a number
    d.moisture_raw := b.moisture;
    d.life_used_raw := b.life_used;
    d.source := b.source;
    d.verdict := verdict(b);
    d.life_used_pct := ROUND(ROUND(100 * b.life_used, 10), 1);
    d.days_left := p_left;
    d.days_left_capped := p_left IS NOT NULL AND p_left >= c_horizon_days;
    d.weather_stale := FALSE;
    d.risk := p_risk;
    d.advice := p_adv;
    d.emc_tomorrow := ROUND(ROUND(emc(p_tomorrow.temp_c, p_tomorrow.rh), 10), 1);
    d.missing_days := 0;
    RETURN d;
  END build_diag;

  -- Evening decision. forecast(1) MUST be tomorrow. p_rain24 = rain in the 24 h after the run;
  -- if not given, tomorrow's values are used and the message says 'tomorrow'.
  PROCEDURE evaluate(b IN OUT NOCOPY t_batch, p_today IN DATE, p_forecast IN t_weather_tab,
                     p_places IN t_places, p_rain24 IN t_rain24, p_alert OUT t_alert, p_diag OUT t_diag,
                     p_meta IN t_weather_meta DEFAULT no_meta, p_send IN BOOLEAN DEFAULT TRUE) IS
    v_tomorrow  t_weather_day;
    v_mm        NUMBER;
    v_prob      NUMBER;
    v_left      PLS_INTEGER;
    v_risk      VARCHAR2(8);
    v_adv       VARCHAR2(20);
    v_escalated BOOLEAN;
    v_rain      BOOLEAN;
    v_retest_ok BOOLEAN;
    v_code      VARCHAR2(30);
    v_none      t_alert;
    v_use24     BOOLEAN;
    v_stale     BOOLEAN;
    v_undo      t_undo;
  BEGIN
    p_alert := v_none;
    IF p_forecast.COUNT = 0 THEN
      RAISE_APPLICATION_ERROR(-20001, 'forecast is empty');
    END IF;
    IF p_forecast(1).wx_date <> p_today + 1 THEN
      RAISE_APPLICATION_ERROR(-20001, 'forecast(1) must be tomorrow');
    END IF;
    v_tomorrow := p_forecast(1);
    -- rain24 with no data at all (None, None) falls back to tomorrow's values, like "not given"
    v_use24 := p_rain24.given AND NOT (p_rain24.mm IS NULL AND p_rain24.prob IS NULL);
    v_stale := p_meta.given AND p_meta.age_hours > c_weather_stale_hours;
    IF v_use24 THEN
      v_mm := p_rain24.mm;
      v_prob := p_rain24.prob;
    ELSE
      v_mm := v_tomorrow.rain_mm;
      v_prob := v_tomorrow.rain_prob;
    END IF;
    v_left := days_left(b, p_forecast);
    v_risk := risk_level(b.life_used, v_left);
    v_adv := advice(b);
    p_diag := build_diag(b, v_left, v_risk, v_adv, v_tomorrow);
    IF v_mm IS NULL AND v_prob IS NULL THEN
      p_diag.flags := CASE WHEN p_diag.flags IS NULL THEN 'rain data missing'
                           ELSE p_diag.flags || '; rain data missing' END;     -- shown on the dashboard
    END IF;
    IF v_stale THEN
      p_diag.flags := CASE WHEN p_diag.flags IS NULL THEN 'weather stale' ELSE p_diag.flags || '; weather stale' END;
      p_diag.weather_stale := TRUE;
    END IF;
    IF NOT p_send OR b.status <> 'active' OR (b.last_alert IS NOT NULL AND b.last_alert = p_today) THEN
      RETURN;
    END IF;

    v_escalated := level_ord(v_risk) > level_ord(b.told_level) AND level_ord(v_risk) >= 1;
    IF v_left IS NOT NULL AND b.told_left IS NOT NULL AND v_left <= c_worse_within
       AND v_left <= b.told_left * c_worse_factor THEN
      v_escalated := TRUE;                                     -- countdown at least halved
    END IF;
    v_rain := ((v_prob IS NOT NULL AND v_prob >= c_rain_prob_alert)
               OR (v_mm IS NOT NULL AND v_mm >= c_rain_mm_alert)) AND NOT v_stale;
    v_retest_ok := v_adv IS NULL OR v_adv <> 'RETEST'
                   OR count_sent(b, 'RETEST', p_today - 29) < c_retest_per_30_days;

    v_code := NULL;
    IF v_rain AND b.storage = 'drying' AND needs_drying(v_adv) AND b.rain_unacked < c_rain_unacked_max THEN
      v_code := 'RAIN_COVER';
    ELSIF v_adv = 'TEST_FIRST' THEN
      IF quiet_for(b, v_adv, p_today, c_remind_gap_days) AND count_sent(b, v_adv) < c_test_reminders_max THEN
        v_code := v_adv;
      END IF;
    ELSIF NOT v_retest_ok THEN
      NULL;
    ELSIF pushed_on_change(v_adv) AND (b.last_advice IS NULL OR v_adv <> b.last_advice) THEN
      v_code := v_adv;                                         -- the recommendation changed
    ELSIF v_adv IN ('DRY_NOW', 'RETEST', 'OPEN_AND_DRY') AND v_escalated
          AND quiet_for(b, v_adv, p_today, c_remind_gap_days) THEN
      v_code := v_adv;                                         -- same advice, countdown worse
    ELSIF v_adv IN ('DRY_NOW', 'RETEST') AND v_risk = 'HIGH'
          AND repeat_ok(b, v_adv, p_today, c_remind_gap_days) THEN
      v_code := v_adv;                                         -- unanswered HIGH warning
    ELSIF v_adv IN ('OPEN_AND_DRY', 'CONFIRM_DRY') AND repeat_ok(b, v_adv, p_today, c_sealed_gap_days) THEN
      v_code := v_adv;                                         -- unanswered sealed-bag warning
    ELSIF is_permeable(b.storage) AND verdict(b) = 'DRY' AND b.moisture < c_hermetic_max_mc
          AND b.life_used < c_medium_life AND (p_today - b.stored_since) >= c_insect_reminder_days
          AND count_sent(b, 'INSECT_REMINDER') = 0 THEN
      v_code := 'INSECT_REMINDER';
    END IF;

    -- capped HIGH_ALERT: weekly, at most c_high_alert_max per test result, then the closing state below (C-12)
    IF v_code IS NULL AND v_risk = 'HIGH'
       AND v_adv IN ('RETEST', 'DRY_NOW', 'SORT_AND_SELL', 'OPEN_AND_DRY', 'CONFIRM_DRY')
       AND (b.last_alert IS NULL OR (p_today - b.last_alert) >= c_high_alert_gap_days)
       AND count_sent(b, 'HIGH_ALERT', NVL(b.last_test, DATE '0001-01-01')) < c_high_alert_max THEN
      v_code := 'HIGH_ALERT';
    ELSIF v_code IS NULL AND v_risk = 'HIGH'
       AND v_adv IN ('RETEST', 'DRY_NOW', 'SORT_AND_SELL', 'OPEN_AND_DRY', 'CONFIRM_DRY')
       AND count_sent(b, 'HIGH_ALERT', NVL(b.last_test, DATE '0001-01-01')) >= c_high_alert_max THEN
      -- C-12 closing state: the last-chance message has gone; silent ON PURPOSE until a new test (new count), flagged
      p_diag.flags := CASE WHEN p_diag.flags IS NULL THEN 'high alerts used up'
                           ELSE p_diag.flags || '; high alerts used up' END;
    END IF;

    IF v_code IS NULL THEN
      RETURN;
    END IF;
    v_undo := make_undo(b);
    p_alert := render(v_code, b, v_risk, v_left, p_today, p_places, v_mm, v_prob, v_use24, p_meta);
    p_alert.undo := v_undo;
    b.last_alert := p_today;
    add_sent(b, p_today, v_code);
    IF v_code = 'RAIN_COVER' THEN
      b.rain_unacked := b.rain_unacked + 1;
    ELSIF is_advice_code(v_code) THEN
      b.last_advice := v_code;
      b.told_level := v_risk;
      b.told_left := v_left;
    END IF;
  END evaluate;

  -- ====================================================================================
  -- 9. Farmer replies (English or Kiswahili keywords; case, spacing and punctuation tolerant)
  -- ====================================================================================
  -- Cuts the input to c_max_text_chars characters first; never raises. Unicode spaces become plain spaces
  -- explicitly (Oracle's [[:space:]] would not match them): NBSP, en/em space, figure space, thin/hair space,
  -- zero-width space, narrow NBSP, ideographic space.
  FUNCTION normalise(p_text IN VARCHAR2) RETURN VARCHAR2 IS
    t    VARCHAR2(8000);
    r    VARCHAR2(8000);
    c    VARCHAR2(4);
    prev VARCHAR2(4);
    nxt  VARCHAR2(4);
    FUNCTION is_digit(p_c IN VARCHAR2) RETURN BOOLEAN IS
    BEGIN
      RETURN p_c IS NOT NULL AND ASCII(p_c) BETWEEN 48 AND 57;
    END;
  BEGIN
    IF p_text IS NULL THEN
      RETURN NULL;
    END IF;
    t := REPLACE(UPPER(SUBSTR(p_text, 1, c_max_text_chars)), UNISTR('\00B0'), ' ');
    t := TRANSLATE(t, UNISTR('\00A0\2002\2003\2007\2009\200A\200B\202F\3000'), '         ');
    -- [!?;:'"()\-_/*#] -> space
    t := REGEXP_REPLACE(t, '[!?;:''"()_/*#-]', ' ');
    -- keep a '.' or ',' only when it sits between two digits (decimal point / comma inside a number)
    FOR k IN 1 .. LENGTH(t) LOOP
      c := SUBSTR(t, k, 1);
      IF c IN ('.', ',') THEN
        prev := CASE WHEN k > 1 THEN SUBSTR(t, k - 1, 1) END;
        nxt := SUBSTR(t, k + 1, 1);
        IF NOT (is_digit(prev) AND is_digit(nxt)) THEN
          c := ' ';
        END IF;
      END IF;
      r := r || c;
    END LOOP;
    r := TRIM(REGEXP_REPLACE(r, '[[:space:]]+', ' '));
    RETURN REGEXP_REPLACE(r, ' +%', '%');
  END normalise;

  -- R1-04: a short message (at most c_optout_max_tokens words) that contains an opt-out word anywhere, or a phrase such
  -- as NO MORE, is an opt-out: STOP, PLEASE STOP, I WANT TO STOP, NO MORE, STOPP. A false positive only stops messages
  -- (START undoes it); a missed STOP is the worse error. p_norm is a normalised text.
  FUNCTION is_optout(p_norm IN VARCHAR2) RETURN BOOLEAN IS
    v_pad VARCHAR2(4000);
  BEGIN
    IF p_norm IS NULL THEN
      RETURN FALSE;
    END IF;
    IF REGEXP_COUNT(p_norm, ' ') + 1 > c_optout_max_tokens THEN
      RETURN FALSE;
    END IF;
    v_pad := ' ' || p_norm || ' ';
    RETURN INSTR(v_pad, ' STOP ') > 0 OR INSTR(v_pad, ' STOPP ') > 0 OR INSTR(v_pad, ' STOPPED ') > 0
        OR INSTR(v_pad, ' UNSUBSCRIBE ') > 0 OR INSTR(v_pad, ' CANCEL ') > 0 OR INSTR(v_pad, ' END ') > 0
        OR INSTR(v_pad, ' QUIT ') > 0 OR INSTR(v_pad, ' ACHA ') > 0 OR INSTR(v_pad, ' SITISHA ') > 0
        OR INSTR(v_pad, ' SIMAMISHA ') > 0 OR INSTR(v_pad, ' NISITISHIE ') > 0
        OR INSTR(v_pad, ' NO MORE ') > 0 OR INSTR(v_pad, ' OPT OUT ') > 0 OR INSTR(v_pad, ' SITAKI TENA ') > 0;
  END is_optout;

  -- Phone numbers and chat ids in one canonical form, so +254712345678, 0712 345 678 and 254712345678 are one
  -- person: lower-case, only digits, '+', letters and ':' kept; 00 -> +; 0xxxxxxxxx and 254xxxxxxxxx -> +254xxxxxxxxx.
  FUNCTION normalise_address(p_addr IN VARCHAR2) RETURN VARCHAR2 IS
    a VARCHAR2(400) := REGEXP_REPLACE(LOWER(NVL(p_addr, '')), '[^0-9a-z+:]', '');
  BEGIN
    IF SUBSTR(a, 1, 2) = '00' THEN
      a := '+' || SUBSTR(a, 3);
    END IF;
    IF REGEXP_LIKE(a, '^0[0-9]{9}$') THEN
      a := '+254' || SUBSTR(a, 2);
    ELSIF REGEXP_LIKE(a, '^254[0-9]{9}$') THEN
      a := '+' || a;
    END IF;
    RETURN a;
  END normalise_address;

  -- HMAC-SHA256 (lower-case hex) of the canonical address with a secret pepper. Stored instead of the number
  -- wherever the number itself is not needed (opt-outs, inbound log). Needs EXECUTE on DBMS_CRYPTO.
  FUNCTION address_hash(p_addr IN VARCHAR2, p_pepper IN VARCHAR2) RETURN VARCHAR2 IS
  BEGIN
    RETURN LOWER(RAWTOHEX(DBMS_CRYPTO.MAC(UTL_I18N.STRING_TO_RAW(normalise_address(p_addr), 'AL32UTF8'),
                                          DBMS_CRYPTO.HMAC_SH256,
                                          UTL_I18N.STRING_TO_RAW(p_pepper, 'AL32UTF8'))));
  END address_hash;

  FUNCTION address_hash(p_addr IN VARCHAR2) RETURN VARCHAR2 IS
    v_pepper hv_config.cfg_value%TYPE;
  BEGIN
    BEGIN
      SELECT cfg_value INTO v_pepper FROM hv_config WHERE cfg_key = 'hash_pepper';
    EXCEPTION WHEN NO_DATA_FOUND THEN
      RAISE_APPLICATION_ERROR(-20004, 'hv_config hash_pepper is not set');
    END;
    RETURN address_hash(p_addr, v_pepper);
  END address_hash;

  -- Update the batch from a reply. Never raises on farmer input. Returns one of:
  -- SALT_YES, SALT_NO, SALT_NO_IGNORED, METER, HYGRO, STORAGE, CLOSED, ACK, STOP, START,
  -- INVALID (recognised command, unusable value) or UNKNOWN.
  FUNCTION apply_reply(b IN OUT NOCOPY t_batch, p_text IN VARCHAR2, p_today IN DATE,
                       p_temp_hint IN NUMBER DEFAULT NULL) RETURN VARCHAR2 IS
    t     VARCHAR2(8000) := normalise(p_text);
    v_first VARCHAR2(8000);
    v_neg BOOLEAN;
    v_num VARCHAR2(100);
    v_tmp VARCHAR2(100);
    v_rh  NUMBER;
    v_temp NUMBER;
    v_val NUMBER;
    v_was VARCHAR2(8);

    FUNCTION to_num(p_s IN VARCHAR2) RETURN NUMBER IS      -- float(s.replace(",", "."))
    BEGIN
      -- more than 15 decimals are cut (Oracle's format model allows 20 integer + 15 decimal digits)
      RETURN TO_NUMBER(REGEXP_REPLACE(REPLACE(p_s, ',', '.'), '(\.[0-9]{15})[0-9]+', '\1'),
                       '99999999999999999999.999999999999999', 'NLS_NUMERIC_CHARACTERS=''.,''');
    END;
  BEGIN
    IF t IS NULL THEN
      RETURN 'UNKNOWN';
    END IF;
    v_first := SUBSTR(t, 1, INSTR(t || ' ', ' ') - 1);
    IF REGEXP_LIKE(t, c_re_salt_yes) THEN
      IF record_salt(b, p_today, TRUE) THEN NULL; END IF;
      RETURN 'SALT_YES';
    END IF;
    IF REGEXP_LIKE(t, c_re_salt_no) THEN
      RETURN CASE WHEN record_salt(b, p_today, FALSE) THEN 'SALT_NO' ELSE 'SALT_NO_IGNORED' END;
    END IF;
    v_neg := REGEXP_LIKE(TRANSLATE(UPPER(SUBSTR(p_text, 1, c_max_text_chars)), UNISTR('\2212\2013\2014'), '---'), c_re_neg);
    IF REGEXP_LIKE(t, c_re_meter_cmd) THEN
      IF v_neg OR NOT REGEXP_LIKE(t, c_re_meter) THEN
        RETURN 'INVALID';
      END IF;
      v_num := REGEXP_SUBSTR(t, c_re_meter, 1, 1, NULL, 2);
      BEGIN
        v_val := to_num(v_num);
        record_meter(b, p_today, v_val);
      EXCEPTION WHEN OTHERS THEN               -- unparsable number, or outside 5..40 %
        RETURN 'INVALID';
      END;
      RETURN 'METER';
    END IF;
    IF REGEXP_LIKE(t, c_re_hygro_cmd) THEN
      IF v_neg OR NOT REGEXP_LIKE(t, c_re_hygro) THEN
        RETURN 'INVALID';
      END IF;
      v_num := REGEXP_SUBSTR(t, c_re_hygro, 1, 1, NULL, 1);
      v_tmp := REGEXP_SUBSTR(t, c_re_hygro, 1, 1, NULL, 4);
      BEGIN
        IF v_tmp IS NOT NULL THEN
          v_temp := to_num(v_tmp);
        ELSE
          v_temp := p_temp_hint;
        END IF;
        IF v_temp IS NULL THEN
          RAISE_APPLICATION_ERROR(-20001, 'no temperature');
        END IF;
        v_rh := to_num(v_num);
        record_hygro(b, p_today, v_rh, v_temp);
      EXCEPTION WHEN OTHERS THEN
        RETURN 'INVALID';
      END;
      RETURN 'HYGRO';
    END IF;
    IF is_optout(t) THEN
      b.status := 'stopped';
      RETURN 'STOP';
    END IF;
    IF v_first IN ('DRYING', 'ANIKA') THEN
      set_storage(b, p_today, 'drying');
      RETURN 'STORAGE';
    END IF;
    IF v_first IN ('SACKS', 'SACK', 'MAGUNIA') THEN
      set_storage(b, p_today, 'sack');
      RETURN 'STORAGE';
    END IF;
    IF v_first IN ('SEALED', 'NIMEFUNGA') THEN
      set_storage(b, p_today, 'hermetic');
      RETURN 'STORAGE';
    END IF;
    IF v_first IN ('SOLD', 'NIMEUZA', 'DEPOSITED', 'GHALANI') THEN
      b.status := 'closed';
      RETURN 'CLOSED';
    END IF;
    IF v_first IN ('START', 'ANZA') THEN
      IF b.status <> 'active' THEN
        v_was := b.status;
        b.status := 'active';
        -- A sold batch restarts from today. An opted-out pause is NOT free: the paused days are charged (with
        -- the nearest known weather) by the next daily run, so a pause never resets the countdown.
        IF v_was = 'closed' AND b.moisture IS NOT NULL THEN
          b.last_advanced := p_today - 1;
        END IF;
      END IF;
      RETURN 'START';
    END IF;
    IF t IN ('1', 'OK', 'OKAY', 'SAWA', 'ASANTE', 'THANKS', 'DONE', 'THANK YOU') THEN
      RETURN 'ACK';
    END IF;
    RETURN 'UNKNOWN';
  END apply_reply;

  -- Answer a farmer's reply at once. Never uses the evening slot.
  -- p_forecast should start tomorrow; if it is empty, messages say the countdown is not available.
  PROCEDURE respond(b IN OUT NOCOPY t_batch, p_text IN VARCHAR2, p_today IN DATE,
                    p_forecast IN t_weather_tab, p_places IN t_places, p_temp_hint IN NUMBER,
                    p_cmd OUT VARCHAR2, p_alert OUT t_alert, p_meta IN t_weather_meta DEFAULT no_meta) IS
    v_hint      NUMBER := p_temp_hint;
    v_norm      VARCHAR2(4000);
    v_duplicate BOOLEAN := FALSE;
    v_was       VARCHAR2(8);
    v_left      PLS_INTEGER;
    v_risk      VARCHAR2(8);
    v_adv       VARCHAR2(20);
    v_code      VARCHAR2(30);
    v_none      t_alert;
    v_undo      t_undo;
    n           PLS_INTEGER;
  BEGIN
    p_alert := v_none;
    IF v_hint IS NULL AND p_forecast.COUNT > 0 THEN
      v_hint := p_forecast(1).temp_c;
    END IF;
    v_norm := SUBSTR(normalise(p_text), 1, c_norm_store_chars);
    FOR k IN 1 .. b.replies.COUNT LOOP
      IF b.replies(k).rcv_date = p_today
         AND (b.replies(k).norm = v_norm OR (b.replies(k).norm IS NULL AND v_norm IS NULL)) THEN
        v_duplicate := TRUE;
      END IF;
    END LOOP;
    v_was := b.status;
    p_cmd := apply_reply(b, p_text, p_today, v_hint);
    n := b.replies.COUNT + 1;
    b.replies(n).rcv_date := p_today;
    b.replies(n).norm := v_norm;
    b.rain_unacked := 0;
    IF b.status = 'stopped' AND p_cmd <> 'STOP' THEN
      RETURN;                                  -- opted out: stay silent
    END IF;
    v_left := days_left(b, p_forecast);
    v_risk := risk_level(b.life_used, v_left);
    v_adv := advice(b);
    IF v_was = 'closed' AND b.status = 'closed' AND p_cmd <> 'CLOSED' THEN
      v_code := 'CLOSED';                      -- reply START to reopen
    ELSIF p_cmd IN ('UNKNOWN', 'INVALID') THEN
      v_code := 'HELP';
    ELSIF p_cmd IN ('ACK', 'SALT_NO_IGNORED') OR v_duplicate THEN
      IF p_cmd = 'ACK' OR v_duplicate THEN
        v_code := 'THANKS';
      ELSE
        v_code := NVL(v_adv, 'STATUS');
      END IF;
    ELSIF p_cmd IN ('CLOSED', 'STOP') THEN
      v_code := CASE p_cmd WHEN 'CLOSED' THEN 'CLOSED' ELSE 'STOPPED' END;
    ELSIF p_cmd = 'STORAGE' AND b.storage = 'drying' AND needs_drying(v_adv) THEN
      v_code := 'THANKS';                      -- started drying, as advised
    ELSE
      v_code := NVL(v_adv, 'STATUS');
    END IF;
    v_undo := make_undo(b);
    IF is_advice_code(v_code) THEN
      b.last_advice := v_code;
      b.told_level := v_risk;
      b.told_left := v_left;
    END IF;
    p_alert := render(v_code, b, v_risk, v_left, p_today, p_places, NULL, NULL, TRUE, p_meta);
    p_alert.undo := v_undo;
    add_sent(b, p_today, v_code);
  END respond;

  -- ====================================================================================
  -- 10. The evening job for one batch: catch up on un-simulated days, then evaluate.
  --     p_days = ascending weather from (about) today-2 to today+7; diag.missing_days counts gaps.
  -- ====================================================================================
  PROCEDURE daily_run(b IN OUT NOCOPY t_batch, p_today IN DATE, p_days IN t_weather_tab,
                      p_places IN t_places, p_rain24 IN t_rain24, p_alert OUT t_alert, p_diag OUT t_diag,
                      p_meta IN t_weather_meta DEFAULT no_meta) IS
    v_again    BOOLEAN := (b.last_run IS NOT NULL AND b.last_run = p_today);
    v_past     t_weather_tab;        -- days up to and including today
    v_forecast t_weather_tab;        -- days after today
    v_missing  PLS_INTEGER := 0;
    v_d        DATE;
    v_w        t_weather_day;
    v_found    BOOLEAN;
    v_src      t_weather_day;
    v_have_src BOOLEAN;
    v_empty    t_weather_day;
  BEGIN
    FOR k IN 1 .. p_days.COUNT LOOP                           -- split_weather
      IF p_days(k).wx_date <= p_today THEN
        v_past(v_past.COUNT + 1) := p_days(k);
      ELSE
        v_forecast(v_forecast.COUNT + 1) := p_days(k);
      END IF;
    END LOOP;
    IF v_forecast.COUNT = 0 THEN
      RAISE_APPLICATION_ERROR(-20002, 'weather must include tomorrow');
    END IF;
    IF v_forecast(1).wx_date <> p_today + 1 THEN
      RAISE_APPLICATION_ERROR(-20002, 'weather must include tomorrow');
    END IF;
    IF b.moisture IS NOT NULL AND b.last_advanced IS NULL THEN        -- e.g. a batch loaded from storage
      b.last_advanced := NVL(b.last_test, p_today) - 1;
    END IF;
    IF b.moisture IS NOT NULL AND b.status = 'active' THEN
      v_d := b.last_advanced + 1;
      WHILE v_d <= p_today LOOP
        v_found := FALSE;
        FOR k IN 1 .. v_past.COUNT LOOP
          IF v_past(k).wx_date = v_d THEN
            v_w := v_past(k);
            v_found := TRUE;
          END IF;
        END LOOP;
        IF NOT v_found THEN
          -- gap in the data: reuse the nearest earlier day (or tomorrow) and report it
          v_missing := v_missing + 1;
          v_have_src := FALSE;
          FOR k IN 1 .. v_past.COUNT LOOP
            IF v_past(k).wx_date < v_d AND (NOT v_have_src OR v_past(k).wx_date > v_src.wx_date) THEN
              v_src := v_past(k);
              v_have_src := TRUE;
            END IF;
          END LOOP;
          IF NOT v_have_src THEN
            v_src := v_forecast(1);
          END IF;
          v_w := v_empty;
          v_w.wx_date := v_d;
          v_w.temp_c := v_src.temp_c;
          v_w.rh := v_src.rh;
          v_w.rain_mm := 0;
        END IF;
        advance_day(b, v_w);
        v_d := v_d + 1;
      END LOOP;
    END IF;
    evaluate(b, p_today, v_forecast, p_places, p_rain24, p_alert, p_diag, p_meta, NOT v_again);
    IF v_again THEN       -- idempotent per batch per day: a second call never sends again
      p_diag.flags := CASE WHEN p_diag.flags IS NULL THEN 'already run today' ELSE p_diag.flags || '; already run today' END;
    ELSE
      b.last_run := p_today;
    END IF;
    p_diag.missing_days := v_missing;
  END daily_run;

  -- ====================================================================================
  -- Database wrappers (not covered by vectors.json; see README "Known gaps")
  -- ====================================================================================

  -- Loads AND LOCKS the batch row (SELECT ... FOR UPDATE): every read-modify-write of a batch (a reply, the
  -- evening run) goes through here, so a STOP can never be lost to the 17:00 run (R1-05).
  PROCEDURE load_batch(p_batch_id IN NUMBER, b OUT NOCOPY t_batch) IS
    r hv_batches%ROWTYPE;
    n PLS_INTEGER;
  BEGIN
    BEGIN
      SELECT * INTO r FROM hv_batches WHERE batch_id = p_batch_id FOR UPDATE WAIT 30;
    EXCEPTION WHEN NO_DATA_FOUND THEN
      RAISE_APPLICATION_ERROR(-20003, 'no such batch ' || p_batch_id);
    END;
    b := new_batch(r.batch_id, r.ward_id, r.storage, r.stored_since, r.lang);
    b.bags := r.bags;
    b.moisture := r.moisture;
    b.source := r.source;
    b.last_test := r.last_test;
    b.test_value := r.test_value;
    b.peak_since_test := r.peak_since_test;
    b.life_used := r.life_used;
    b.last_advanced := r.last_advanced;
    b.last_alert := r.last_alert;
    b.last_advice := r.last_advice;
    b.told_level := r.told_level;
    b.told_left := r.told_left;
    b.rain_unacked := r.rain_unacked;
    b.status := r.status;
    b.last_run := r.last_run;
    IF b.moisture IS NOT NULL THEN                    -- Python __post_init__
      IF b.test_value IS NULL THEN b.test_value := b.moisture; END IF;
      IF b.peak_since_test IS NULL THEN b.peak_since_test := GREATEST(b.moisture, b.test_value); END IF;
    END IF;
    -- Only messages that were or will be delivered count as sent: a SKIPPED, CANCELLED or finally FAILED
    -- message burns no cap (R1-08).
    FOR m IN (SELECT msg_date, code FROM hv_messages
               WHERE batch_id = p_batch_id AND status IN ('QUEUED', 'SENDING', 'SENT') ORDER BY msg_id) LOOP
      n := b.sent.COUNT + 1;
      b.sent(n).sent_date := m.msg_date;
      b.sent(n).code := m.code;
    END LOOP;
    FOR i IN (SELECT rcv_date, norm_text FROM hv_inbound WHERE batch_id = p_batch_id ORDER BY in_id) LOOP
      n := b.replies.COUNT + 1;
      b.replies(n).rcv_date := i.rcv_date;
      b.replies(n).norm := i.norm_text;
    END LOOP;
  END load_batch;

  PROCEDURE save_batch(b IN t_batch) IS
  BEGIN
    UPDATE hv_batches
       SET storage = b.storage, stored_since = b.stored_since, lang = b.lang, bags = b.bags,
           moisture = b.moisture, source = b.source, last_test = b.last_test,
           test_value = b.test_value, peak_since_test = b.peak_since_test,
           life_used = b.life_used, last_advanced = b.last_advanced, last_alert = b.last_alert,
           last_advice = b.last_advice, told_level = b.told_level, told_left = b.told_left,
           rain_unacked = b.rain_unacked, status = b.status, last_run = b.last_run,
           ended_at = CASE WHEN b.status IN ('closed', 'stopped') THEN NVL(ended_at, today_eat) ELSE NULL END
     WHERE batch_id = b.batch_id;
  END save_batch;

  FUNCTION load_places(p_ward_id IN NUMBER) RETURN t_places IS
    p t_places;
  BEGIN
    FOR r IN (SELECT kind, name FROM hv_places WHERE ward_id = p_ward_id AND active = 1 ORDER BY place_id) LOOP
      IF r.kind = 'stockist' AND p.stockist IS NULL THEN p.stockist := r.name;
      ELSIF r.kind = 'warehouse' AND p.warehouse IS NULL THEN p.warehouse := r.name;
      ELSIF r.kind = 'checkpoint' AND p.checkpoint IS NULL THEN p.checkpoint := r.name;
      END IF;
    END LOOP;
    RETURN p;
  END load_places;

  PROCEDURE load_weather(p_ward_id IN NUMBER, p_today IN DATE, p_days OUT NOCOPY t_weather_tab) IS
    n PLS_INTEGER := 0;
  BEGIN
    FOR r IN (SELECT wx_date, temp_c, rh, rain_mm, rain_prob FROM hv_weather
               WHERE ward_id = p_ward_id AND wx_date BETWEEN p_today - 2 AND p_today + 7
               ORDER BY wx_date) LOOP
      n := n + 1;
      p_days(n).wx_date := r.wx_date;
      p_days(n).temp_c := r.temp_c;
      p_days(n).rh := r.rh;
      p_days(n).rain_mm := r.rain_mm;
      p_days(n).rain_prob := r.rain_prob;
    END LOOP;
  END load_weather;

  FUNCTION load_rain24(p_ward_id IN NUMBER, p_today IN DATE) RETURN t_rain24 IS
    r t_rain24;
  BEGIN
    SELECT rain_mm, rain_prob INTO r.mm, r.prob FROM hv_weather_rain24
     WHERE ward_id = p_ward_id AND run_date = p_today;
    r.given := TRUE;
    RETURN r;
  EXCEPTION WHEN NO_DATA_FOUND THEN
    r.given := FALSE;
    RETURN r;
  END load_rain24;

  -- A failed refresh is recorded (in its own transaction, so a caller's ROLLBACK cannot erase it) and the
  -- cached forecast ages: after c_weather_stale_hours advice is flagged stale (R1-09).
  PROCEDURE record_weather_fetch(p_ward_id IN NUMBER, p_ok IN BOOLEAN, p_error IN VARCHAR2) IS
    PRAGMA AUTONOMOUS_TRANSACTION;
    v_ok NUMBER := CASE WHEN p_ok THEN 1 ELSE 0 END;
  BEGIN
    MERGE INTO hv_weather_fetch f
    USING (SELECT p_ward_id AS ward_id FROM dual) s ON (f.ward_id = s.ward_id)
    WHEN MATCHED THEN UPDATE SET
         f.last_attempt_at = SYSTIMESTAMP,
         f.last_ok_at = CASE WHEN v_ok = 1 THEN SYSTIMESTAMP ELSE f.last_ok_at END,
         f.last_error = CASE WHEN v_ok = 1 THEN NULL ELSE SUBSTR(p_error, 1, 500) END
    WHEN NOT MATCHED THEN INSERT (ward_id, last_attempt_at, last_ok_at, last_error)
         VALUES (p_ward_id, SYSTIMESTAMP, CASE WHEN v_ok = 1 THEN SYSTIMESTAMP END,
                 CASE WHEN v_ok = 1 THEN NULL ELSE SUBSTR(p_error, 1, 500) END);
    COMMIT;
  END record_weather_fetch;

  -- How old is the cached forecast? No fetch record at all counts as stale (age 9999 h): never silently
  -- use data of unknown age.
  FUNCTION load_weather_meta(p_ward_id IN NUMBER) RETURN t_weather_meta IS
    m      t_weather_meta;
    v_ok   TIMESTAMP WITH TIME ZONE;
    v_iv   INTERVAL DAY(9) TO SECOND;
  BEGIN
    m.given := TRUE;
    BEGIN
      SELECT last_ok_at INTO v_ok FROM hv_weather_fetch WHERE ward_id = p_ward_id;
    EXCEPTION WHEN NO_DATA_FOUND THEN
      v_ok := NULL;
    END;
    IF v_ok IS NULL THEN
      m.age_hours := 9999;
      RETURN m;
    END IF;
    v_iv := SYSTIMESTAMP - v_ok;
    m.age_hours := EXTRACT(DAY FROM v_iv) * 24 + EXTRACT(HOUR FROM v_iv) + EXTRACT(MINUTE FROM v_iv) / 60;
    m.fetched_on := TRUNC(CAST(v_ok AT TIME ZONE 'Africa/Nairobi' AS DATE));
    RETURN m;
  END load_weather_meta;

  -- Numeric hv_config value with a default (a missing or non-numeric value gives the default).
  FUNCTION cfg_num(p_key IN VARCHAR2, p_default IN NUMBER) RETURN NUMBER IS
    v hv_config.cfg_value%TYPE;
  BEGIN
    SELECT cfg_value INTO v FROM hv_config WHERE cfg_key = p_key;
    RETURN NVL(TO_NUMBER(TRIM(v)), p_default);
  EXCEPTION WHEN OTHERS THEN
    RETURN p_default;
  END cfg_num;

  -- R3 C3-02 (moved here from ords_handlers.sql so that queue_message budgets EVERY reply: known senders, the welcome,
  -- the how-to). Returns a VARCHAR2 so no BOOLEAN ever appears inside SQL (C-02).
  FUNCTION reply_status(p_hash IN VARCHAR2, p_code IN VARCHAR2) RETURN VARCHAR2 IS
    n_opt NUMBER;
    n_h   NUMBER;
    n_d   NUMBER;
    n_g   NUMBER;
    n_how NUMBER;
  BEGIN
    IF p_code = 'STOPPED' THEN RETURN 'QUEUED'; END IF;           -- C-01: the opt-out confirmation, sent once
    SELECT COUNT(*) INTO n_opt FROM hv_optout WHERE addr_hash = p_hash;
    IF n_opt > 0 THEN RETURN 'CANCELLED'; END IF;
    SELECT COUNT(*) INTO n_h FROM hv_messages
     WHERE to_hash = p_hash AND kind = 'REPLY' AND status IN ('QUEUED', 'SENDING', 'SENT')
       AND created_at > SYSTIMESTAMP - INTERVAL '1' HOUR;
    SELECT COUNT(*) INTO n_d FROM hv_messages
     WHERE to_hash = p_hash AND kind = 'REPLY' AND status IN ('QUEUED', 'SENDING', 'SENT')
       AND created_at > SYSTIMESTAMP - INTERVAL '1' DAY;
    IF n_h >= cfg_num('max_reply_per_hour', 6) OR n_d >= cfg_num('max_reply_per_day', 20) THEN RETURN 'SKIPPED'; END IF;
    -- forged senders rotate past any per-phone limit, so there is also a system-wide daily ceiling on replies
    SELECT COUNT(*) INTO n_g FROM hv_messages
     WHERE kind = 'REPLY' AND status IN ('QUEUED', 'SENDING', 'SENT') AND created_at > SYSTIMESTAMP - INTERVAL '1' DAY;
    IF n_g >= cfg_num('max_reply_global_per_day', 3000) THEN RETURN 'SKIPPED'; END IF;
    IF p_code = 'HOWTO' THEN
      SELECT COUNT(*) INTO n_how FROM hv_messages
       WHERE code = 'HOWTO' AND status IN ('QUEUED', 'SENDING', 'SENT') AND created_at > SYSTIMESTAMP - INTERVAL '1' DAY;
      IF n_how >= cfg_num('max_howto_per_day', 300) THEN RETURN 'SKIPPED'; END IF;
    END IF;
    RETURN 'QUEUED';
  END reply_status;

  -- Queue one message. Opted-out phones get CANCELLED rows (except the STOPPED confirmation); a message that
  -- would go out as UCS-2 or take more than 2 SMS is SKIPPED. Neither burns a cap: what the message changed
  -- on the batch is taken back (the caller saves the batch afterwards).
  PROCEDURE queue_message(b IN OUT NOCOPY t_batch, p_alert IN t_alert, p_kind IN VARCHAR2, p_today IN DATE,
                          p_ignore_optout IN BOOLEAN DEFAULT FALSE) IS
    v_ref    hv_batches.farmer_ref%TYPE;
    v_hash   hv_batches.farmer_hash%TYPE;
    v_chan   hv_batches.channel%TYPE;
    v_status VARCHAR2(10);
    v_opt    NUMBER;
  BEGIN
    SELECT farmer_ref, farmer_hash, channel INTO v_ref, v_hash, v_chan FROM hv_batches WHERE batch_id = b.batch_id;
    SELECT COUNT(*) INTO v_opt FROM hv_optout WHERE addr_hash = v_hash;
    IF v_opt > 0 AND NOT p_ignore_optout THEN
      v_status := 'CANCELLED';
    ELSIF sms_segments(p_alert.msg) BETWEEN 1 AND c_sms_max_segments THEN
      v_status := 'QUEUED';
      IF p_kind = 'REPLY' AND NOT p_ignore_optout THEN      -- R3 C3-02: the reply budget (proactive rows have their own caps)
        v_status := reply_status(v_hash, p_alert.code);
        IF v_status = 'CANCELLED' THEN v_status := 'SKIPPED'; END IF;   -- cannot happen here (opt-out checked above)
      END IF;
    ELSE
      v_status := 'SKIPPED';
    END IF;
    INSERT INTO hv_messages (batch_id, msg_date, code, kind, lang, body, body_other, channel, to_addr, to_hash, status,
                             undo_last_alert, undo_last_advice, undo_told_level, undo_told_left, undo_rain_unacked)
    VALUES (b.batch_id, p_today, p_alert.code, p_kind, b.lang, p_alert.msg, p_alert.other, v_chan, v_ref, v_hash, v_status,
            p_alert.undo.last_alert, p_alert.undo.last_advice, p_alert.undo.told_level, p_alert.undo.told_left,
            p_alert.undo.rain_unacked);
    IF v_status <> 'QUEUED' THEN
      revert_undelivered(b, p_alert.undo);
    END IF;
  END queue_message;

  -- The first message after registration: what this is, the weather credit, how to stop.
  PROCEDURE queue_welcome(p_batch_id IN NUMBER, p_today IN DATE DEFAULT NULL) IS
    v_today DATE := TRUNC(NVL(p_today, today_eat));
    b       t_batch;
    a       t_alert;
  BEGIN
    load_batch(p_batch_id, b);
    a := welcome(b, v_today);
    queue_message(b, a, 'REPLY', v_today);
  END queue_welcome;

  -- Sender protocol (R1-05): rows are claimed with FOR UPDATE SKIP LOCKED and flipped to SENDING in a
  -- committed transaction BEFORE any HTTP call, so two senders (the 5-minute job and a manual run) can never
  -- pick the same row. A row stuck in SENDING for 15 minutes (crashed sender) goes back to QUEUED: delivery is
  -- at-least-once in that rare case. Opted-out phones are skipped here too.
  PROCEDURE claim_queued(p_limit IN NUMBER, p_ids OUT SYS.ODCINUMBERLIST) IS
    CURSOR c IS SELECT msg_id, to_hash, code FROM hv_messages WHERE status = 'QUEUED'
                 ORDER BY msg_id FOR UPDATE SKIP LOCKED;
    v_n   PLS_INTEGER := 0;
    v_opt NUMBER;
  BEGIN
    p_ids := SYS.ODCINUMBERLIST();
    UPDATE hv_messages SET status = 'QUEUED'
     WHERE status = 'SENDING' AND sent_at < SYSTIMESTAMP - INTERVAL '15' MINUTE;
    FOR r IN c LOOP
      EXIT WHEN v_n >= p_limit;
      SELECT COUNT(*) INTO v_opt FROM hv_optout WHERE addr_hash = r.to_hash;
      -- C-01: the one STOP confirmation is queued WITH the opt-out in place and must still go out (exactly once per STOP)
      IF v_opt > 0 AND r.code <> 'STOPPED' THEN
        UPDATE hv_messages SET status = 'CANCELLED' WHERE msg_id = r.msg_id;
      ELSE
        UPDATE hv_messages SET status = 'SENDING', sent_at = SYSTIMESTAMP WHERE msg_id = r.msg_id;
        v_n := v_n + 1;
        p_ids.EXTEND;
        p_ids(v_n) := r.msg_id;
      END IF;
    END LOOP;
    COMMIT;
  END claim_queued;

  PROCEDURE mark_sent(p_msg_id IN NUMBER, p_provider_ref IN VARCHAR2) IS
  BEGIN
    UPDATE hv_messages SET status = 'SENT', sent_at = SYSTIMESTAMP, provider_ref = SUBSTR(p_provider_ref, 1, 100),
           error_text = NULL, to_addr = NULL            -- the number is not needed any more
     WHERE msg_id = p_msg_id;
    COMMIT;
  END mark_sent;

  -- A failed send is retried (back to QUEUED) up to c_max_attempts times; the last failure is final: the
  -- message never reached the farmer, so what it changed on the batch is taken back.
  PROCEDURE mark_failed(p_msg_id IN NUMBER, p_error IN VARCHAR2) IS
    r hv_messages%ROWTYPE;
  BEGIN
    SELECT * INTO r FROM hv_messages WHERE msg_id = p_msg_id FOR UPDATE;
    IF r.attempts + 1 < c_max_attempts THEN
      UPDATE hv_messages SET status = 'QUEUED', attempts = attempts + 1, error_text = SUBSTR(p_error, 1, 500)
       WHERE msg_id = p_msg_id;
    ELSE
      UPDATE hv_messages SET status = 'FAILED', attempts = attempts + 1, error_text = SUBSTR(p_error, 1, 500),
             to_addr = NULL
       WHERE msg_id = p_msg_id;
      IF r.batch_id IS NOT NULL THEN
        IF is_advice_code(r.code) THEN
          UPDATE hv_batches SET last_advice = r.undo_last_advice, told_level = NVL(r.undo_told_level, 'UNKNOWN'),
                 told_left = r.undo_told_left
           WHERE batch_id = r.batch_id AND last_advice = r.code;
        END IF;
        IF r.kind = 'PROACTIVE' THEN
          UPDATE hv_batches SET last_alert = r.undo_last_alert
           WHERE batch_id = r.batch_id AND last_alert = r.msg_date;
        END IF;
        IF r.code = 'RAIN_COVER' THEN
          UPDATE hv_batches SET rain_unacked = NVL(r.undo_rain_unacked, 0) WHERE batch_id = r.batch_id;
        END IF;
      END IF;
    END IF;
    COMMIT;
  END mark_failed;

  -- Handle one inbound farmer message. Known sender: lock the batch, run the engine, apply STOP / START to the
  -- whole PHONE (every batch, queued messages cancelled), store only the hash of the number plus a short
  -- normalised text. Unknown sender: store nothing but the hash and the command (R1-03, R1-07, R1-11).
  PROCEDURE process_reply(p_channel IN VARCHAR2, p_from IN VARCHAR2, p_text IN VARCHAR2,
                          p_today IN DATE, p_batch_id OUT NUMBER, p_cmd OUT VARCHAR2,
                          p_reply OUT VARCHAR2) IS
    v_today  DATE := TRUNC(NVL(p_today, today_eat));
    v_text   VARCHAR2(4000) := SUBSTR(p_text, 1, c_max_text_chars);
    v_norm   VARCHAR2(4000) := normalise(v_text);
    v_hash   VARCHAR2(64) := address_hash(p_from);
    b        t_batch;
    v_days   t_weather_tab;
    v_fc     t_weather_tab;
    v_alert  t_alert;
    v_places t_places;
    v_meta   t_weather_meta;
    v_was_out NUMBER;
  BEGIN
    p_reply := NULL;
    p_batch_id := NULL;
    SELECT COUNT(*) INTO v_was_out FROM hv_optout WHERE addr_hash = v_hash;   -- R3 C3-01: was it already opted out?
    BEGIN
      -- the latest ACTIVE batch of this phone, else its latest batch
      SELECT batch_id INTO p_batch_id FROM (
        SELECT batch_id FROM hv_batches WHERE channel = p_channel AND farmer_hash = v_hash
         ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, created_at DESC, batch_id DESC)
       WHERE ROWNUM = 1;
    EXCEPTION WHEN NO_DATA_FOUND THEN
      INSERT INTO hv_inbound (batch_id, channel, from_hash, rcv_date, raw_text, norm_text, cmd)
      VALUES (NULL, p_channel, v_hash, v_today, NULL, NULL, 'UNKNOWN_SENDER');      -- C-09: nothing of the text is kept
      p_cmd := 'UNKNOWN_SENDER';
      IF is_optout(v_norm) THEN                         -- an unknown number can opt out too
        MERGE INTO hv_optout o USING (SELECT v_hash AS h FROM dual) s ON (o.addr_hash = s.h)
        WHEN NOT MATCHED THEN INSERT (addr_hash) VALUES (s.h);
        UPDATE hv_messages SET status = 'CANCELLED' WHERE to_hash = v_hash AND status = 'QUEUED';
        p_cmd := 'STOP';
      END IF;
      RETURN;
    END;
    load_batch(p_batch_id, b);                          -- locks the batch row
    v_places := load_places(b.ward_id);
    load_weather(b.ward_id, v_today, v_days);
    v_meta := load_weather_meta(b.ward_id);
    FOR k IN 1 .. v_days.COUNT LOOP                    -- forecast = days after today
      IF v_days(k).wx_date > v_today THEN
        v_fc(v_fc.COUNT + 1) := v_days(k);
      END IF;
    END LOOP;
    respond(b, v_text, v_today, v_fc, v_places, NULL, p_cmd, v_alert, v_meta);
    INSERT INTO hv_inbound (batch_id, channel, from_hash, rcv_date, raw_text, norm_text, cmd)
    VALUES (p_batch_id, p_channel, v_hash, v_today, SUBSTR(v_text, 1, c_norm_store_chars),
            SUBSTR(v_norm, 1, c_norm_store_chars), p_cmd);
    IF p_cmd = 'STOP' THEN
      MERGE INTO hv_optout o USING (SELECT v_hash AS h FROM dual) s ON (o.addr_hash = s.h)
      WHEN NOT MATCHED THEN INSERT (addr_hash) VALUES (s.h);
      UPDATE hv_batches SET status = 'stopped', ended_at = NVL(ended_at, v_today)
       WHERE channel = p_channel AND farmer_hash = v_hash AND status = 'active' AND batch_id <> p_batch_id;
      UPDATE hv_messages SET status = 'CANCELLED' WHERE to_hash = v_hash AND status = 'QUEUED';
    ELSIF p_cmd = 'START' THEN
      DELETE FROM hv_optout WHERE addr_hash = v_hash;
      UPDATE hv_batches SET status = 'active', ended_at = NULL, farmer_ref = NVL(farmer_ref, p_from)
       WHERE channel = p_channel AND farmer_hash = v_hash AND status = 'stopped' AND batch_id <> p_batch_id;
      UPDATE hv_batches SET farmer_ref = NVL(farmer_ref, p_from) WHERE batch_id = p_batch_id;
    END IF;
    -- R3 C3-01: the STOPPED confirmation goes out ONCE, on the transition into opt-out. A repeated STOP (new day,
    -- different wording) from a number that is already opted out is processed but gets no second confirmation.
    IF v_alert.code IS NOT NULL AND NOT (p_cmd = 'STOP' AND v_was_out > 0) THEN
      queue_message(b, v_alert, 'REPLY', v_today, p_cmd = 'STOP');
      p_reply := v_alert.msg;
    END IF;
    save_batch(b);
  END process_reply;

  -- flags: '; '-separated, never starting with a separator (R1-30)
  PROCEDURE log_run(p_batch_id IN NUMBER, p_today IN DATE, p_alert IN t_alert, p_diag IN t_diag, p_err IN VARCHAR2) IS
    v_flags VARCHAR2(600) := p_diag.flags;
  BEGIN
    IF p_diag.missing_days > 0 THEN
      v_flags := CASE WHEN v_flags IS NULL THEN '' ELSE v_flags || '; ' END
                 || 'missing weather days: ' || p_diag.missing_days;
    END IF;
    DELETE FROM hv_run_log WHERE batch_id = p_batch_id AND run_date = p_today;
    INSERT INTO hv_run_log (batch_id, run_date, risk, days_left, moisture, life_used_pct, advice, code, flags, error_text)
    VALUES (p_batch_id, p_today, p_diag.risk, p_diag.days_left, p_diag.moisture, p_diag.life_used_pct,
            p_diag.advice, p_alert.code, SUBSTR(v_flags, 1, 500), SUBSTR(p_err, 1, 500));
  END log_run;

  -- Run one already-loaded ward context for one batch. Isolated: an error rolls this batch back.
  -- Idempotent per batch per day (hv_batches.last_run): a second run the same day changes and sends nothing.
  PROCEDURE run_loaded(p_batch_id IN NUMBER, p_today IN DATE, p_days IN t_weather_tab,
                       p_places IN t_places, p_rain24 IN t_rain24, p_meta IN t_weather_meta) IS
    b       t_batch;
    v_alert t_alert;
    v_diag  t_diag;
  BEGIN
    load_batch(p_batch_id, b);                          -- locks the batch row
    daily_run(b, p_today, p_days, p_places, p_rain24, v_alert, v_diag, p_meta);
    IF v_alert.code IS NOT NULL THEN
      queue_message(b, v_alert, 'PROACTIVE', p_today);
    END IF;
    save_batch(b);
    IF INSTR(v_diag.flags, 'already run today') = 0 OR v_diag.flags IS NULL THEN
      log_run(p_batch_id, p_today, v_alert, v_diag, NULL);
    END IF;
  END run_loaded;

  PROCEDURE daily_run_batch(p_batch_id IN NUMBER, p_today IN DATE DEFAULT NULL) IS
    v_today  DATE := TRUNC(NVL(p_today, today_eat));
    v_ward   NUMBER;
    v_days   t_weather_tab;
  BEGIN
    BEGIN
      SELECT ward_id INTO v_ward FROM hv_batches WHERE batch_id = p_batch_id;
    EXCEPTION WHEN NO_DATA_FOUND THEN
      RAISE_APPLICATION_ERROR(-20003, 'no such batch ' || p_batch_id);
    END;
    load_weather(v_ward, v_today, v_days);
    run_loaded(p_batch_id, v_today, v_days, load_places(v_ward), load_rain24(v_ward, v_today), load_weather_meta(v_ward));
  END daily_run_batch;

  -- Weather, places and rain24 are loaded once per ward, not per batch.
  PROCEDURE daily_run_ward(p_ward_id IN NUMBER, p_today IN DATE DEFAULT NULL) IS
    v_today  DATE := TRUNC(NVL(p_today, today_eat));
    v_days   t_weather_tab;
    v_places t_places;
    v_rain   t_rain24;
    v_meta   t_weather_meta;
    v_err    VARCHAR2(500);
    v_none_a t_alert;
    v_none_d t_diag;
  BEGIN
    load_weather(p_ward_id, v_today, v_days);
    v_places := load_places(p_ward_id);
    v_rain := load_rain24(p_ward_id, v_today);
    v_meta := load_weather_meta(p_ward_id);
    FOR r IN (SELECT batch_id FROM hv_batches
               WHERE ward_id = p_ward_id AND status = 'active' AND (last_run IS NULL OR last_run < v_today)
               ORDER BY batch_id) LOOP
      BEGIN
        run_loaded(r.batch_id, v_today, v_days, v_places, v_rain, v_meta);
        COMMIT;                                        -- one batch failing never blocks the others
      EXCEPTION WHEN OTHERS THEN
        v_err := SQLERRM;
        ROLLBACK;
        v_none_d.missing_days := 0;
        log_run(r.batch_id, v_today, v_none_a, v_none_d, v_err);
        COMMIT;
      END;
    END LOOP;
  END daily_run_ward;

  PROCEDURE daily_run_all(p_today IN DATE DEFAULT NULL) IS
    v_today DATE := TRUNC(NVL(p_today, today_eat));
  BEGIN
    FOR w IN (SELECT DISTINCT ward_id FROM hv_batches WHERE status = 'active' ORDER BY ward_id) LOOP
      daily_run_ward(w.ward_id, v_today);
    END LOOP;
  END daily_run_all;

  -- ====================================================================================
  -- Privacy (R1-11). Run purge_retention daily; erase_by_phone on a person's request.
  -- ====================================================================================
  PROCEDURE purge_retention(p_today IN DATE DEFAULT NULL) IS
    v_today DATE := TRUNC(NVL(p_today, today_eat));
  BEGIN
    UPDATE hv_inbound SET raw_text = NULL
     WHERE raw_text IS NOT NULL AND rcv_date < v_today - c_retain_inbound_text;
    -- C-09: the normalised text of any sender (unknown senders included) is blanked with the raw text at 30 days
    UPDATE hv_inbound SET norm_text = NULL
     WHERE norm_text IS NOT NULL AND rcv_date < v_today - c_retain_inbound_text;
    DELETE FROM hv_inbound WHERE rcv_date < v_today - c_retain_message;
    -- dedupe and rate-limit bookkeeping is only needed for days
    DELETE FROM hv_inbound_seen WHERE seen_at < SYSTIMESTAMP - INTERVAL '7' DAY;
    DELETE FROM hv_rate WHERE bucket_hour < SYSDATE - 2;
    UPDATE hv_messages SET to_addr = NULL
     WHERE to_addr IS NOT NULL AND status IN ('SENT', 'FAILED', 'SKIPPED', 'CANCELLED')
       AND msg_date < v_today - c_retain_sent_address;
    -- C-10 / R3 C3-03: the caps are rebuilt from message rows (count_sent), so while a batch is ACTIVE its cap rows are kept
    -- past 180 days: TEST_FIRST and INSECT_REMINDER (counted over the batch's whole life) and every row dated on or after
    -- its last test (HIGH_ALERT, DRY_NOW, RETEST ... are counted per test result). Their text is blanked at 180 days; only
    -- the code and the date stay. Everything else, and every row of an ended batch, is deleted at 180 days.
    UPDATE hv_messages m SET body = '[purged]', body_other = NULL
     WHERE m.msg_date < v_today - c_retain_message AND m.body <> '[purged]'
       AND EXISTS (SELECT 1 FROM hv_batches b WHERE b.batch_id = m.batch_id AND b.status = 'active'
                    AND (m.code IN ('TEST_FIRST', 'INSECT_REMINDER') OR m.msg_date >= NVL(b.last_test, DATE '0001-01-01')));
    DELETE FROM hv_messages m WHERE m.msg_date < v_today - c_retain_message
       AND NOT EXISTS (SELECT 1 FROM hv_batches b WHERE b.batch_id = m.batch_id AND b.status = 'active'
                        AND (m.code IN ('TEST_FIRST', 'INSECT_REMINDER') OR m.msg_date >= NVL(b.last_test, DATE '0001-01-01')));
    DELETE FROM hv_run_log WHERE run_date < v_today - c_retain_runlog;
    UPDATE hv_batches SET farmer_ref = NULL
     WHERE farmer_ref IS NOT NULL AND status IN ('closed', 'stopped') AND ended_at < v_today - c_retain_ended_batch;
    UPDATE hv_weather_fetch SET last_error = NULL WHERE last_error IS NOT NULL AND last_attempt_at < SYSTIMESTAMP - c_retain_runlog;
    COMMIT;
  END purge_retention;

  -- Erase one person: every batch of the phone, its messages, inbound log and run log. The opt-out row (a
  -- hash, not a number) is KEPT so an erased person who had said STOP is never messaged again.
  PROCEDURE erase_by_phone(p_channel IN VARCHAR2, p_addr IN VARCHAR2, p_deleted OUT NUMBER) IS
    v_hash VARCHAR2(64) := address_hash(p_addr);
    v_n    NUMBER;
  BEGIN
    p_deleted := 0;
    DELETE FROM hv_run_log WHERE batch_id IN
      (SELECT batch_id FROM hv_batches WHERE farmer_hash = v_hash AND (p_channel IS NULL OR channel = p_channel));
    p_deleted := p_deleted + SQL%ROWCOUNT;
    DELETE FROM hv_messages WHERE to_hash = v_hash OR batch_id IN
      (SELECT batch_id FROM hv_batches WHERE farmer_hash = v_hash AND (p_channel IS NULL OR channel = p_channel));
    p_deleted := p_deleted + SQL%ROWCOUNT;
    DELETE FROM hv_inbound WHERE from_hash = v_hash OR batch_id IN
      (SELECT batch_id FROM hv_batches WHERE farmer_hash = v_hash AND (p_channel IS NULL OR channel = p_channel));
    p_deleted := p_deleted + SQL%ROWCOUNT;
    DELETE FROM hv_batches WHERE farmer_hash = v_hash AND (p_channel IS NULL OR channel = p_channel);
    v_n := SQL%ROWCOUNT;
    p_deleted := p_deleted + v_n;
    COMMIT;
  END erase_by_phone;

BEGIN
  init_tables;
END harvestly_engine;
/
