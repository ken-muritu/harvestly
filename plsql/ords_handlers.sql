-- Harvestly: ORDS endpoints, USSD menu, Open-Meteo weather cache, evening job, sender.   *** SKETCH: never run on Oracle ***
--
-- Order: schema.sql -> harvestly_engine.pks/.pkb -> this file.   Needs: ORDS (enabled on ADB / oracleapex.com
-- workspace schema), APEX (APEX_WEB_SERVICE, APEX_UTIL). Secrets go in hv_config (see schema_ddl.sql header for the
-- key list), never in this file. Prefer APEX Web Credentials where you can (R1-11).
--
-- Compile target: Oracle 19c AND 23ai (R2 C-02). Rule used throughout: no BOOLEAN-returning function is ever called
-- from inside a SQL statement (BOOLEAN in SQL is 23ai-only). Status/flags are computed into variables first, or by
-- functions that return VARCHAR2/NUMBER. Nothing here uses 23ai-only syntax.
--
-- Contents
--   1. helpers: hv_cfg, hv_scrub, hv_check_secret, hv_ip_allowed, hv_body_value, hv_body_ok, hv_is_optedout, hv_to_num, hv_limit,
--               hv_seen_once, hv_rate_hit, hv_reply_status, hv_can_register,
--               hv_register_batch, hv_register_once, hv_queue_test_first, hv_queue_reply, hv_handle_inbound
--   2. hv_ussd_menu          (every response <= 160 characters, English or Kiswahili)
--   3. hv_refresh_ward_weather / hv_refresh_all_weather (Open-Meteo JSON via APEX_WEB_SERVICE, one call per ward)
--   4. sender: hv_claim_and_send, hv_send_one, hv_send_reply_now, hv_send_queued (Africa's Talking SMS / Telegram)
--   5. hv_daily_job          (what the 17:00 APEX Automation calls; it never calls the sender)
--   6. ORDS module: POST /hv/telegram, POST /hv/sms/:secret, POST /hv/ussd/:secret
--   7. APEX Automation recipe and schedule (comment)
--
-- Findings handled here: R1-01 R1-02 R1-03 R1-05 R1-06 R1-07 R1-09 R1-10 R1-11 R1-12 R1-14 R1-16 R1-17 R1-18
-- R1-26 R1-27; R2: C-01 C-02 C-03 C-04 C-05 C-06 C-07 C-08 C-09 C-13 C-15 C-16 C-17 C-18, K-04;
-- R3: C3-01 .. C3-14 (see review/r3-code-fixes.md).
-- R1-12: the handlers no longer depend on ORDS binding form fields (they read the raw body once and parse it);
-- see the notes in section 6. Still never run against a real Africa's Talking callback.
SET DEFINE OFF

-- =====================================================================================
-- 1. helpers
-- =====================================================================================
CREATE OR REPLACE FUNCTION hv_cfg(p_key IN VARCHAR2, p_default IN VARCHAR2 DEFAULT NULL) RETURN VARCHAR2 IS
  v hv_config.cfg_value%TYPE;
BEGIN
  SELECT cfg_value INTO v FROM hv_config WHERE cfg_key = p_key;
  RETURN v;
EXCEPTION WHEN NO_DATA_FOUND THEN
  RETURN p_default;
END hv_cfg;
/

-- R1-01 / R1-11: remove every secret from a text before it can reach hv_messages.error_text or hv_run_log.
-- The Telegram bot token travels in the request path (Bot API design), so any HTTP error text may contain it.
CREATE OR REPLACE FUNCTION hv_scrub(p_text IN VARCHAR2) RETURN VARCHAR2 IS
  v VARCHAR2(4000) := SUBSTR(p_text, 1, 4000);
BEGIN
  IF v IS NULL THEN RETURN NULL; END IF;
  FOR k IN (SELECT cfg_value FROM hv_config
             WHERE cfg_key IN ('telegram_bot_token', 'at_api_key', 'telegram_secret', 'sms_secret', 'ussd_secret', 'hash_pepper')
               AND LENGTH(cfg_value) >= 4) LOOP
    v := REPLACE(v, k.cfg_value, '***');
  END LOOP;
  v := REGEXP_REPLACE(v, 'bot[0-9]+:[A-Za-z0-9_-]+', 'bot***');   -- token shape, in case the config value changed
  RETURN SUBSTR(v, 1, 500);
EXCEPTION WHEN OTHERS THEN
  RETURN 'error (details withheld)';
END hv_scrub;
/

-- R1-14: one secret per endpoint (telegram_secret, sms_secret, ussd_secret). A missing config value never matches.
-- R3 C3-10: a secret shorter than 16 characters is refused (fail closed), and the compare does not stop at the first
-- difference: both sides are hashed with SHA-256 (fixed length) and the 64 hex characters are compared in full.
CREATE OR REPLACE FUNCTION hv_check_secret(p_cfg_key IN VARCHAR2, p_secret IN VARCHAR2) RETURN BOOLEAN IS
  v      hv_config.cfg_value%TYPE := hv_cfg(p_cfg_key);
  v_a    VARCHAR2(64);
  v_b    VARCHAR2(64);
  v_diff PLS_INTEGER := 0;
BEGIN
  IF v IS NULL OR p_secret IS NULL OR LENGTH(v) < 16 THEN RETURN FALSE; END IF;
  v_a := RAWTOHEX(DBMS_CRYPTO.HASH(UTL_I18N.STRING_TO_RAW(v, 'AL32UTF8'), DBMS_CRYPTO.HASH_SH256));
  v_b := RAWTOHEX(DBMS_CRYPTO.HASH(UTL_I18N.STRING_TO_RAW(SUBSTR(p_secret, 1, 1000), 'AL32UTF8'), DBMS_CRYPTO.HASH_SH256));
  FOR i IN 1 .. 64 LOOP
    IF SUBSTR(v_a, i, 1) <> SUBSTR(v_b, i, 1) THEN v_diff := v_diff + 1; END IF;
  END LOOP;
  RETURN v_diff = 0;
EXCEPTION WHEN OTHERS THEN
  RETURN FALSE;
END hv_check_secret;
/

-- R3 C3-13 / R1-12: what the handler really sees. With hv_config 'ip_diag' = 'Y', every call of hv_ip_allowed records
-- "REMOTE_ADDR=... XFF=..." (autonomous, so a refused call is recorded too) in hv_inbound_seen with channel 'ipdiag'
-- (purged after 7 days). Used once, in the sandbox callback test (plsql/README.md "Testing against a real callback").
CREATE OR REPLACE PROCEDURE hv_ip_log IS
  PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
  IF NVL(hv_cfg('ip_diag'), 'N') = 'Y' THEN
    INSERT INTO hv_inbound_seen (channel, provider_id)
    VALUES ('ipdiag', SUBSTR('REMOTE_ADDR=' || OWA_UTIL.GET_CGI_ENV('REMOTE_ADDR')
                             || ' XFF=' || OWA_UTIL.GET_CGI_ENV('HTTP_X_FORWARDED_FOR'), 1, 100));
    COMMIT;
  END IF;
EXCEPTION WHEN OTHERS THEN
  ROLLBACK;                                          -- includes the duplicate-key case: the same address twice is fine
END hv_ip_log;
/

-- R1-14 / R2 C-05 / C-13: source-IP allowlist for the Africa's Talking callbacks, ON BY DEFAULT. AT does NOT sign
-- callbacks, so the secret in the URL path plus a source-IP check is the best available, and the path secret leaks to
-- ORDS/proxy access logs and the AT dashboard. hv_config 'at_ip_allowlist' = comma list of AT's callback source IPs
-- (get the current list from AT; it is NOT in this repo). Missing or empty = REFUSE everything (fail closed). The literal
-- value DISABLED switches the check off (sandbox testing only).
-- Trust: REMOTE_ADDR is the peer ORDS sees. X-Forwarded-For is believed ONLY when REMOTE_ADDR is listed in
-- hv_config 'trusted_proxies' (comma list), and then only its LAST entry, the one that proxy appended (C-13).
-- R3 C3-13: UNVERIFIED on the target: whether ORDS exposes the real REMOTE_ADDR and HTTP_X_FORWARDED_FOR to the handler, and
-- the match is exact-IP only (no CIDR ranges): list every address. hv_config 'ip_diag' = 'Y' records what the handler sees (hv_ip_log).
CREATE OR REPLACE FUNCTION hv_ip_allowed RETURN BOOLEAN IS
  v_list  VARCHAR2(1000);
  v_proxy VARCHAR2(1000);
  v_peer  VARCHAR2(100);
  v_xff   VARCHAR2(500);
  v_last  VARCHAR2(100);
BEGIN
  hv_ip_log;                                                     -- R3 C3-13: records the caller only when ip_diag = 'Y'
  v_list := REPLACE(hv_cfg('at_ip_allowlist'), ' ', '');
  IF v_list IS NULL THEN RETURN FALSE; END IF;                    -- fail closed
  IF UPPER(v_list) = 'DISABLED' THEN RETURN TRUE; END IF;
  v_peer := TRIM(OWA_UTIL.GET_CGI_ENV('REMOTE_ADDR'));
  IF v_peer IS NOT NULL AND INSTR(',' || v_list || ',', ',' || v_peer || ',') > 0 THEN RETURN TRUE; END IF;
  v_proxy := REPLACE(hv_cfg('trusted_proxies'), ' ', '');
  IF v_proxy IS NOT NULL AND v_peer IS NOT NULL AND INSTR(',' || v_proxy || ',', ',' || v_peer || ',') > 0 THEN
    v_xff  := OWA_UTIL.GET_CGI_ENV('HTTP_X_FORWARDED_FOR');
    v_last := TRIM(REGEXP_SUBSTR(v_xff, '[^,]+$'));
    IF v_last IS NOT NULL AND INSTR(',' || v_list || ',', ',' || v_last || ',') > 0 THEN RETURN TRUE; END IF;
  END IF;
  RETURN FALSE;
EXCEPTION WHEN OTHERS THEN
  RETURN FALSE;                                      -- cannot tell where it came from: refuse
END hv_ip_allowed;
/

-- R1-12 / R3: is the raw request body usable at all? 1 = yes, 0 = malformed (the handler answers 400, so Africa's Talking
-- sees a failure instead of the message being dropped with a 200). Malformed means: a JSON body that is not valid JSON
-- or is over 32000 characters; a form body over 8000 characters, with a '%' that is not followed by two hex digits, or
-- whose percent-decoding fails (invalid UTF-8). An empty body is "ok" (nothing to read; the handler drops it).
CREATE OR REPLACE FUNCTION hv_body_ok(p_body IN CLOB) RETURN NUMBER IS
  v_len NUMBER := NVL(DBMS_LOB.GETLENGTH(p_body), 0);
  v_b   VARCHAR2(32000);
  v_n   NUMBER;
  v_dec VARCHAR2(32000);
BEGIN
  IF v_len = 0 THEN RETURN 1; END IF;
  v_b := DBMS_LOB.SUBSTR(p_body, 100, 1);
  IF LTRIM(v_b) LIKE '{%' THEN
    IF v_len > 32000 THEN RETURN 0; END IF;
    SELECT CASE WHEN p_body IS JSON THEN 1 ELSE 0 END INTO v_n FROM dual;
    RETURN v_n;
  END IF;
  IF v_len > 8000 THEN RETURN 0; END IF;
  v_b := DBMS_LOB.SUBSTR(p_body, 8000, 1);
  IF REGEXP_LIKE(v_b, '%([^0-9A-Fa-f]|[0-9A-Fa-f]([^0-9A-Fa-f]|$)|$)') THEN RETURN 0; END IF;
  -- C5-01: valid sequences only: C2-DF leads (2 bytes), E0 A0-BF, E1-EC, ED 80-9F (no surrogates), EE-EF (3 bytes), F0 90-BF,
  -- F1-F3, F4 80-8F (4 bytes); overlongs (C0, C1, E0 80.., F0 80..) and > U+10FFFF are left over and rejected.
  -- C4-02: do not rely on UNESCAPE raising. Remove every well-formed UTF-8 byte sequence written as %XX; any %80-%FF byte
  -- left over is invalid UTF-8 (lone continuation, bad lead byte, truncated sequence) whatever the database does with it.
  IF REGEXP_LIKE(REGEXP_REPLACE(v_b, '%([Cc][2-9A-Fa-f]|[Dd][0-9A-Fa-f])%[89ABab][0-9A-Fa-f]|%[Ee]0%[ABab][0-9A-Fa-f]%[89ABab][0-9A-Fa-f]|%([Ee][1-9A-Ca-c]|[Ee][EeFf])(%[89ABab][0-9A-Fa-f]){2}|%[Ee][Dd]%8[0-9A-Fa-f]%[89ABab][0-9A-Fa-f]|%[Ee][Dd]%9[0-9A-Fa-f]%[89ABab][0-9A-Fa-f]|%[Ff]0%[9ABab][0-9A-Fa-f](%[89ABab][0-9A-Fa-f]){2}|%[Ff][1-3](%[89ABab][0-9A-Fa-f]){3}|%[Ff]4%8[0-9A-Fa-f](%[89ABab][0-9A-Fa-f]){2}', ''),
                 '%[89A-Fa-f][0-9A-Fa-f]') THEN RETURN 0; END IF;
  v_dec := UTL_URL.UNESCAPE(REPLACE(v_b, '+', ' '), 'UTF-8');          -- may raise on invalid UTF-8 (caught below)
  IF INSTR(v_dec, UNISTR('\FFFD')) > 0 THEN RETURN 0; END IF;           -- or substitute U+FFFD: also malformed
  RETURN 1;
EXCEPTION WHEN OTHERS THEN
  RETURN 0;
END hv_body_ok;
/

-- R1-12 / R2 C-03 / C-15 / R3: read one field from the raw request body, which the handler read ONCE from :body_text into a
-- local CLOB. Africa's Talking posts application/x-www-form-urlencoded (stated by secondary sources; AT's own docs
-- could not be fetched), so the main path decodes a form body. If the body starts with '{' it is read as JSON instead,
-- so a change of format on AT's side does not silently drop every message. p_name is always a literal from this file.
-- JSON is read straight from the CLOB (not from a VARCHAR2 copy: a VARCHAR2 bind in SQL is limited to 4000 bytes
-- without extended strings), each value cut to 4000 characters. A form body is cut to 8000 characters; the
-- percent-decoding is UTF-8; names are matched whole (id is not linkId). Callers call hv_body_ok first; this function
-- itself never raises and returns NULL for anything it cannot read.
CREATE OR REPLACE FUNCTION hv_body_value(p_body IN CLOB, p_name IN VARCHAR2) RETURN VARCHAR2 IS
  v_b VARCHAR2(32000) := DBMS_LOB.SUBSTR(p_body, 8000, 1);        -- 8000 characters, up to 32000 bytes
  v_v VARCHAR2(8000);
BEGIN
  IF v_b IS NULL THEN RETURN NULL; END IF;
  IF LTRIM(v_b) LIKE '{%' THEN                       -- JSON paths must be literals on 19c: one branch per name
    SELECT CASE p_name
             WHEN 'from'        THEN JSON_VALUE(p_body, '$.from' RETURNING VARCHAR2(4000) TRUNCATE)
             WHEN 'text'        THEN JSON_VALUE(p_body, '$.text' RETURNING VARCHAR2(4000) TRUNCATE)
             WHEN 'id'          THEN JSON_VALUE(p_body, '$.id' RETURNING VARCHAR2(4000) TRUNCATE)
             WHEN 'phoneNumber' THEN JSON_VALUE(p_body, '$.phoneNumber' RETURNING VARCHAR2(4000) TRUNCATE)
             WHEN 'sessionId'   THEN JSON_VALUE(p_body, '$.sessionId' RETURNING VARCHAR2(4000) TRUNCATE)
           END INTO v_v FROM dual;
    RETURN v_v;
  END IF;
  v_v := REGEXP_SUBSTR(v_b, '(^|&)' || p_name || '=([^&]*)', 1, 1, NULL, 2);
  IF v_v IS NULL THEN RETURN NULL; END IF;
  RETURN SUBSTR(UTL_URL.UNESCAPE(REPLACE(v_v, '+', ' '), 'UTF-8'), 1, 4000);
EXCEPTION WHEN OTHERS THEN
  RETURN NULL;
END hv_body_value;
/

-- R1-03: phone-wide opt-out lookup (hv_optout is written by harvestly_engine.process_reply).
CREATE OR REPLACE FUNCTION hv_is_optedout(p_hash IN VARCHAR2) RETURN BOOLEAN IS
  n PLS_INTEGER;
BEGIN
  IF p_hash IS NULL THEN RETURN FALSE; END IF;
  SELECT COUNT(*) INTO n FROM hv_optout WHERE addr_hash = p_hash;
  RETURN n > 0;
END hv_is_optedout;
/

-- Text to NUMBER, NULL when it is not a number. A plain PL/SQL function: 19c-safe, no ON CONVERSION ERROR in PL/SQL.
CREATE OR REPLACE FUNCTION hv_to_num(p_text IN VARCHAR2) RETURN NUMBER IS
BEGIN
  RETURN TO_NUMBER(TRIM(p_text));
EXCEPTION WHEN OTHERS THEN
  RETURN NULL;
END hv_to_num;
/

-- Numeric config value with a default (limits below).
CREATE OR REPLACE FUNCTION hv_limit(p_key IN VARCHAR2, p_default IN NUMBER) RETURN NUMBER IS
BEGIN
  RETURN NVL(hv_to_num(hv_cfg(p_key)), p_default);
END hv_limit;
/

-- R2 C-05 replay / duplicate protection: 1 = first time this provider message id is seen, 0 = duplicate.
-- Not autonomous on purpose: if the request fails and is rolled back, the provider's retry is processed.
-- A NULL id (provider sent none) is never deduplicated.
CREATE OR REPLACE FUNCTION hv_seen_once(p_channel IN VARCHAR2, p_id IN VARCHAR2) RETURN NUMBER IS
BEGIN
  IF p_id IS NULL THEN RETURN 1; END IF;
  INSERT INTO hv_inbound_seen (channel, provider_id) VALUES (p_channel, SUBSTR(p_id, 1, 100));
  RETURN 1;
EXCEPTION WHEN DUP_VAL_ON_INDEX THEN
  RETURN 0;
END hv_seen_once;
/

-- R2 C-05 per-key, per-hour counter of inbound messages; returns the count INCLUDING this one. Autonomous, so a
-- failing request still counts and a flood cannot hide behind rollbacks.
-- R3 C3-02: sliding window. Clock-hour buckets alone allow twice the limit across a boundary (12 at 10:59, 12 at 11:00), so
-- the previous bucket counts for the part of the hour that has not yet slid out: n_now + CEIL(n_previous * (60 - min) / 60).
CREATE OR REPLACE FUNCTION hv_rate_hit(p_hash IN VARCHAR2) RETURN NUMBER IS
  PRAGMA AUTONOMOUS_TRANSACTION;
  v_b    DATE := TRUNC(SYSDATE, 'HH24');
  v_n    NUMBER;
  v_prev NUMBER := 0;
BEGIN
  UPDATE hv_rate SET n = n + 1 WHERE addr_hash = p_hash AND bucket_hour = v_b RETURNING n INTO v_n;
  IF SQL%ROWCOUNT = 0 THEN
    BEGIN
      INSERT INTO hv_rate (addr_hash, bucket_hour, n) VALUES (p_hash, v_b, 1);
      v_n := 1;
    EXCEPTION WHEN DUP_VAL_ON_INDEX THEN
      UPDATE hv_rate SET n = n + 1 WHERE addr_hash = p_hash AND bucket_hour = v_b RETURNING n INTO v_n;
    END;
  END IF;
  BEGIN
    SELECT n INTO v_prev FROM hv_rate WHERE addr_hash = p_hash AND bucket_hour = v_b - 1/24;
  EXCEPTION WHEN NO_DATA_FOUND THEN
    v_prev := 0;
  END;
  COMMIT;
  RETURN v_n + CEIL(v_prev * (60 - TO_NUMBER(TO_CHAR(SYSDATE, 'MI'))) / 60);
EXCEPTION WHEN OTHERS THEN
  ROLLBACK;
  RETURN 0;                                          -- bookkeeping failure never blocks a farmer
END hv_rate_hit;
/

-- R2 C-02 / C-05: the status a new reply row gets, as a VARCHAR2 (so no BOOLEAN ever appears inside SQL):
--   QUEUED     normal
--   CANCELLED  the phone has opted out (except the STOP confirmation itself, C-01)
--   SKIPPED    over the reply budget: per phone per hour / per day, system-wide per day, and the how-to cap for strangers
-- R3 C3-02: the rules now live in harvestly_engine.reply_status, which queue_message applies to every REPLY row (known
-- senders and the welcome included). This wrapper keeps the old name for the helpers below and the tests.
CREATE OR REPLACE FUNCTION hv_reply_status(p_hash IN VARCHAR2, p_code IN VARCHAR2) RETURN VARCHAR2 IS
BEGIN
  RETURN harvestly_engine.reply_status(p_hash, p_code);
END hv_reply_status;
/

-- R2 C-05 forged-sender / SMS-bombing limit: a phone may register only a few batches a day (max_batches_per_day, 3).
-- R3 C3-02: and the whole system only max_batches_global_per_day (300), because forged senders rotate numbers.
CREATE OR REPLACE FUNCTION hv_can_register(p_hash IN VARCHAR2) RETURN BOOLEAN IS
  n   NUMBER;
  n_g NUMBER;
BEGIN
  SELECT COUNT(*) INTO n FROM hv_batches WHERE farmer_hash = p_hash AND stored_since = harvestly_engine.today_eat;
  IF n >= hv_limit('max_batches_per_day', 3) THEN RETURN FALSE; END IF;
  SELECT COUNT(*) INTO n_g FROM hv_batches WHERE stored_since = harvestly_engine.today_eat;
  RETURN n_g < hv_limit('max_batches_global_per_day', 300);
END hv_can_register;
/

-- New batch for a farmer. p_storage uses the engine words: drying | sack | crib | floor | hermetic.
-- R1-03 / R1-11: farmer_hash is the identity used for matching; farmer_ref (plaintext) is kept only so the sender can
-- reach the farmer, and is blanked by erase / retention. Bags are clamped to 1..9999 (R1-10).
CREATE OR REPLACE FUNCTION hv_register_batch(p_channel IN VARCHAR2, p_from IN VARCHAR2, p_ward_id IN NUMBER,
                                             p_storage IN VARCHAR2, p_bags IN NUMBER,
                                             p_lang IN VARCHAR2 DEFAULT 'en') RETURN NUMBER IS
  v_id NUMBER;
BEGIN
  INSERT INTO hv_batches (farmer_ref, farmer_hash, channel, ward_id, storage, stored_since, lang, bags)
  VALUES (TRIM(p_from), harvestly_engine.address_hash(p_from), p_channel, p_ward_id, p_storage,
          harvestly_engine.today_eat, p_lang, LEAST(9999, GREATEST(1, NVL(TRUNC(p_bags), 1))))
  RETURNING batch_id INTO v_id;
  RETURN v_id;
END hv_register_batch;
/

-- R1-03 / R1-18: idempotent registration. An Africa's Talking retry of the same USSD text must not create a second batch.
--   1. same (sessionId, phone): a marker row in hv_inbound (cmd 'USSD_REG', norm_text 'SESSION <id>') points at the batch;
--   2. else same (farmer_hash, channel, ward, storage, bags, stored_since = today, active): reuse that batch.
-- p_is_new = FALSE means "already registered, do not queue the guide again".
-- R3 C3-07: the daily registration cap is checked only AFTER the two idempotency checks, so a retry of the 3rd registration
-- of the day finds its batch and is not told "too many". p_blocked = TRUE: over the cap, nothing was registered (returns NULL). Residual race: two retries inside the same
-- millisecond can both pass the check; AT retries come seconds apart and the first has committed by then.
CREATE OR REPLACE FUNCTION hv_register_once(p_channel IN VARCHAR2, p_from IN VARCHAR2, p_session IN VARCHAR2,
                                            p_ward_id IN NUMBER, p_storage IN VARCHAR2, p_bags IN NUMBER,
                                            p_lang IN VARCHAR2, p_is_new OUT BOOLEAN, p_blocked OUT BOOLEAN) RETURN NUMBER IS
  v_hash  VARCHAR2(64) := harvestly_engine.address_hash(p_from);
  v_bags  NUMBER := LEAST(9999, GREATEST(1, NVL(TRUNC(p_bags), 1)));
  v_mark  VARCHAR2(80) := CASE WHEN p_session IS NOT NULL THEN 'SESSION ' || SUBSTR(p_session, 1, 64) END;
  v_today DATE := harvestly_engine.today_eat;
  v_id    NUMBER;

  PROCEDURE put_marker(p_batch IN NUMBER) IS
  BEGIN
    IF v_mark IS NOT NULL THEN
      INSERT INTO hv_inbound (batch_id, channel, from_hash, rcv_date, norm_text, cmd)
      VALUES (p_batch, p_channel, v_hash, v_today, v_mark, 'USSD_REG');
    END IF;
  END put_marker;
BEGIN
  p_is_new := FALSE;
  p_blocked := FALSE;
  IF v_mark IS NOT NULL THEN
    SELECT MAX(batch_id) INTO v_id FROM hv_inbound
     WHERE cmd = 'USSD_REG' AND from_hash = v_hash AND norm_text = v_mark;
    IF v_id IS NOT NULL THEN RETURN v_id; END IF;
  END IF;
  SELECT MAX(batch_id) INTO v_id FROM hv_batches
   WHERE channel = p_channel AND farmer_hash = v_hash AND ward_id = p_ward_id AND storage = p_storage
     AND bags = v_bags AND stored_since = v_today AND status = 'active';
  IF v_id IS NOT NULL THEN
    put_marker(v_id);
    RETURN v_id;
  END IF;
  IF NOT hv_can_register(v_hash) THEN
    p_blocked := TRUE;
    RETURN NULL;
  END IF;
  v_id := hv_register_batch(p_channel, p_from, p_ward_id, p_storage, v_bags, p_lang);
  put_marker(v_id);
  p_is_new := TRUE;
  RETURN v_id;
END hv_register_once;
/

-- Queue the first message for a just-registered (untested) batch: ask for a moisture test.
-- The row is CANCELLED at once when the phone has opted out (R1-03), SKIPPED when over the reply budget (C-05) or when it
-- would not fit in 2 SMS segments (C-17; same rule as the package's queue_message). The status is computed into a
-- variable first: a BOOLEAN function inside the INSERT does not compile before 23ai (C-02).
CREATE OR REPLACE PROCEDURE hv_queue_test_first(p_batch_id IN NUMBER, p_reply OUT VARCHAR2) IS
  b         harvestly_engine.t_batch;
  v_places  harvestly_engine.t_places;
  v_alert   harvestly_engine.t_alert;
  v_ref     hv_batches.farmer_ref%TYPE;
  v_hash    hv_batches.farmer_hash%TYPE;
  v_chan    hv_batches.channel%TYPE;
  v_status  VARCHAR2(10);
  v_today   DATE := harvestly_engine.today_eat;
BEGIN
  harvestly_engine.load_batch(p_batch_id, b);
  v_places := harvestly_engine.load_places(b.ward_id);
  v_alert := harvestly_engine.render('TEST_FIRST', b, 'UNKNOWN', NULL, v_today, v_places);
  SELECT farmer_ref, farmer_hash, channel INTO v_ref, v_hash, v_chan FROM hv_batches WHERE batch_id = p_batch_id;
  v_status := hv_reply_status(v_hash, 'TEST_FIRST');
  IF v_status = 'QUEUED'
     AND harvestly_engine.sms_segments(v_alert.msg) NOT BETWEEN 1 AND harvestly_engine.c_sms_max_segments THEN
    v_status := 'SKIPPED';
  END IF;
  INSERT INTO hv_messages (batch_id, msg_date, code, kind, lang, body, body_other, channel, to_addr, to_hash, status)
  VALUES (p_batch_id, v_today, 'TEST_FIRST', 'REPLY', b.lang, v_alert.msg, v_alert.other, v_chan, v_ref, v_hash, v_status);
  p_reply := v_alert.msg;
END hv_queue_test_first;
/

-- R1-02: a reply for a sender who has no batch (how-to, ward list, STOP / START confirmation). The package queues
-- nothing for them, so this does, with batch_id NULL. to_addr stays plaintext only until the message is sent or fails
-- (R1-11). Status as in hv_queue_test_first (C-02, C-05); the STOPPED confirmation is exempt from the opt-out check (C-01).
CREATE OR REPLACE PROCEDURE hv_queue_reply(p_channel IN VARCHAR2, p_from IN VARCHAR2, p_code IN VARCHAR2,
                                           p_lang IN VARCHAR2, p_body IN VARCHAR2) IS
  v_hash   VARCHAR2(64) := harvestly_engine.address_hash(p_from);
  v_status VARCHAR2(10) := hv_reply_status(v_hash, p_code);
BEGIN
  INSERT INTO hv_messages (batch_id, msg_date, code, kind, lang, body, channel, to_addr, to_hash, status)
  VALUES (NULL, harvestly_engine.today_eat, p_code, 'REPLY', p_lang, p_body, p_channel, TRIM(p_from), v_hash, v_status);
END hv_queue_reply;
/

-- One inbound farmer message from any channel (SMS or Telegram). Replies are queued in hv_messages and also returned;
-- nothing is delivered from here (R1-01, R1-02), the caller may ask hv_send_reply_now to try at once.
--   * R1-07: text is cut to 1000 characters before anything else; the procedure never raises on farmer input
--     (an unexpected error is a real fault and propagates).
--   * Known sender: harvestly_engine.process_reply does everything (STOP/START phone-wide, hashes, queueing).
--   * Unknown sender: "JOIN <ward words> <storage> <bags> [SW]" registers a batch. Otherwise the how-to is queued.
--     R1-11 / C-09: process_reply stores neither raw nor normalised text for unknown senders; this procedure stores none either.
--   R2: per-phone hourly cap (STOP exempt), STOP confirmation sent once, START works for an opted-out stranger.
--   R3 C3-01: a KNOWN sender's repeated STOP gets no second confirmation either (process_reply checks hv_optout first).
CREATE OR REPLACE PROCEDURE hv_handle_inbound(p_channel IN VARCHAR2, p_from IN VARCHAR2, p_text IN VARCHAR2,
                                              p_reply OUT VARCHAR2, p_cmd OUT VARCHAR2) IS
  TYPE t_ids IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
  v_ids    t_ids;
  v_batch  NUMBER;
  v_text   VARCHAR2(4000);
  v_norm   VARCHAR2(4000);
  v_rest   VARCHAR2(4000);
  v_hash   VARCHAR2(64);
  v_was_out BOOLEAN;
  v_ward_t VARCHAR2(200);
  v_store_t VARCHAR2(40);
  v_bags_t VARCHAR2(40);
  v_store  VARCHAR2(10);
  v_bags   NUMBER;
  v_lang   VARCHAR2(2) := 'en';
  v_list   VARCHAR2(400);
  v_name   hv_wards.name%TYPE;
  v_today  DATE := harvestly_engine.today_eat;
  c_howto  CONSTANT VARCHAR2(300) :=
        'Harvestly: To join, reply JOIN <ward> <storage> <bags>, e.g. JOIN KITALE SACK 12. '
     || 'Storage: DRYING, SACK, CRIB, FLOOR or SEALED. Add SW for Kiswahili.';
  c_howto_sw CONSTANT VARCHAR2(300) :=                                              -- C5-02: the same, in Kiswahili, with a SAJILI example
        'Harvestly: Kusajili, jibu SAJILI <kata> <hifadhi> <magunia>, mf. SAJILI KITALE MAGUNIA 12. '
     || 'Hifadhi: ANIKA, MAGUNIA, KIHENGE, SAKAFU au NIMEFUNGA.';

  FUNCTION storage_word(p_w IN VARCHAR2) RETURN VARCHAR2 IS
  BEGIN
    RETURN CASE p_w WHEN 'DRYING' THEN 'drying' WHEN 'SACK' THEN 'sack' WHEN 'SACKS' THEN 'sack'
                    WHEN 'MAGUNIA' THEN 'sack' WHEN 'ANIKA' THEN 'drying' WHEN 'NIMEFUNGA' THEN 'hermetic'
                    WHEN 'CRIB' THEN 'crib' WHEN 'FLOOR' THEN 'floor' WHEN 'KIHENGE' THEN 'crib' WHEN 'SAKAFU' THEN 'floor' WHEN 'SEALED' THEN 'hermetic'
                    WHEN 'HERMETIC' THEN 'hermetic' END;
  END storage_word;

  -- ward names for the "which ward?" reply: the given ids, or the first wards when none matched
  FUNCTION ward_list RETURN VARCHAR2 IS
    v_out VARCHAR2(400);
  BEGIN
    IF v_ids.COUNT = 0 THEN
      FOR w IN (SELECT name FROM hv_wards ORDER BY ward_id FETCH FIRST 8 ROWS ONLY) LOOP
        EXIT WHEN LENGTH(v_out) > 120;
        v_out := v_out || CASE WHEN v_out IS NOT NULL THEN ', ' END || SUBSTR(w.name, 1, 20);
      END LOOP;
    ELSE
      FOR i IN 1 .. LEAST(v_ids.COUNT, 8) LOOP
        EXIT WHEN LENGTH(v_out) > 120;
        SELECT name INTO v_name FROM hv_wards WHERE ward_id = v_ids(i);
        v_out := v_out || CASE WHEN v_out IS NOT NULL THEN ', ' END || SUBSTR(v_name, 1, 20);
      END LOOP;
    END IF;
    RETURN v_out;
  END ward_list;
BEGIN
  v_text := SUBSTR(p_text, 1, harvestly_engine.c_max_text_chars);          -- R1-07
  v_hash := harvestly_engine.address_hash(p_from);
  v_norm := UPPER(harvestly_engine.normalise(v_text));                      -- R1-10: punctuation, double spaces
  v_was_out := hv_is_optedout(v_hash);
  p_cmd := NULL;

  -- R2 C-05: per phone per hour cap. A STOP is never limited. Over the cap: no reply, no processing.
  IF hv_rate_hit(v_hash) > hv_limit('max_in_per_hour', 12) AND NOT harvestly_engine.is_optout(v_norm) THEN
    p_reply := NULL;
    p_cmd := 'RATE_LIMITED';
    RETURN;
  END IF;

  harvestly_engine.process_reply(p_channel, p_from, v_text, NULL, v_batch, p_cmd, p_reply);
  IF v_batch IS NOT NULL THEN
    RETURN;                                          -- known sender: the package queued the reply (STOP confirmation too)
  END IF;

  -- ---- unknown sender: no batch, so the package queued nothing ----
  IF harvestly_engine.is_optout(v_norm) THEN
    -- process_reply has recorded the opt-out. C-01: confirm it ONCE (the first STOP only; a repeat stays silent).
    p_cmd := 'STOP';
    IF NOT v_was_out THEN
      v_lang := CASE WHEN REGEXP_LIKE(v_norm, '(^| )(SIMAMISHA|ACHA|SITISHA|SITAKI)( |$)') THEN 'sw' ELSE 'en' END;
      SELECT body INTO p_reply FROM hv_templates WHERE code = 'STOPPED' AND lang = v_lang;
      hv_queue_reply(p_channel, p_from, 'STOPPED', v_lang, p_reply);
    ELSE
      p_reply := NULL;
    END IF;
    RETURN;
  END IF;
  IF v_was_out THEN
    IF REGEXP_LIKE(v_norm, '^(START|ANZA)( |$)') THEN                      -- C-06: an opted-out stranger can come back
      DELETE FROM hv_optout WHERE addr_hash = v_hash;
      p_cmd := 'START';
      v_lang := CASE WHEN REGEXP_LIKE(v_norm, '^ANZA( |$)') THEN 'sw' ELSE 'en' END;
      SELECT body INTO p_reply FROM hv_templates WHERE code = 'START_OK' AND lang = v_lang;     -- C3-14: a template, EN and SW
      hv_queue_reply(p_channel, p_from, 'START_OK', v_lang, p_reply);
    ELSE
      p_reply := NULL;                               -- never answer an opted-out number
    END IF;
    RETURN;
  END IF;

  -- C5-02: a Kiswahili command word (or a trailing SW) means Kiswahili guidance even when the rest is mistyped
  IF REGEXP_LIKE(v_norm, '^SAJILI( |$)') OR REGEXP_LIKE(v_norm, '^(JOIN|REGISTER) .* SW$') THEN v_lang := 'sw'; END IF;
  p_reply := CASE v_lang WHEN 'sw' THEN c_howto_sw ELSE c_howto END;
  IF REGEXP_LIKE(v_norm, '^(JOIN|REGISTER|SAJILI) [A-Z][A-Z ]* [0-9]+( SW)?$') THEN
    v_rest := REGEXP_REPLACE(v_norm, '^(JOIN|REGISTER|SAJILI) ', '');
    IF REGEXP_LIKE(v_norm, '^SAJILI ') THEN v_lang := 'sw'; END IF;          -- C4-01: the Kiswahili command implies a Kiswahili batch
    IF REGEXP_LIKE(v_rest, ' SW$') THEN
      v_lang := 'sw';
      v_rest := REGEXP_REPLACE(v_rest, ' SW$', '');
    END IF;
    v_bags_t  := REGEXP_SUBSTR(v_rest, '[0-9]+$');
    v_rest    := RTRIM(REGEXP_REPLACE(v_rest, ' *[0-9]+$', ''));
    v_store_t := REGEXP_SUBSTR(v_rest, '[A-Z]+$');
    v_ward_t  := TRIM(REGEXP_REPLACE(v_rest, ' *[A-Z]+$', ''));
    v_store   := storage_word(v_store_t);
    IF v_store IS NOT NULL AND v_ward_t IS NOT NULL AND v_bags_t IS NOT NULL AND REGEXP_LIKE(v_ward_t, '^[A-Z ]+$') THEN
      -- R1-10: bags clamped to 1..9999 without raising (a long digit string is simply 9999)
      v_bags := CASE WHEN LENGTH(LTRIM(v_bags_t, '0')) > 4 THEN 9999
                     ELSE LEAST(9999, GREATEST(1, NVL(hv_to_num(v_bags_t), 1))) END;
      -- R1-10: ward = exact name (case-insensitive), else a UNIQUE prefix. No ROWNUM guessing.
      SELECT ward_id BULK COLLECT INTO v_ids FROM hv_wards WHERE UPPER(name) = v_ward_t ORDER BY ward_id;
      IF v_ids.COUNT = 0 THEN
        SELECT ward_id BULK COLLECT INTO v_ids FROM hv_wards
         WHERE UPPER(name) LIKE v_ward_t || '%' ORDER BY name, ward_id;       -- v_ward_t is only [A-Z ]: no wildcards
      END IF;
      IF v_ids.COUNT = 1 THEN
        IF NOT hv_can_register(v_hash) THEN                                   -- C-05: no registration floods
          p_reply := CASE v_lang WHEN 'sw' THEN 'Harvestly: Usajili mwingi sana kutoka namba hii leo. Tafadhali jaribu tena kesho.'
                                 ELSE 'Harvestly: Too many registrations from this number today. Please try again tomorrow.' END;   -- C4-03
          hv_queue_reply(p_channel, p_from, 'HOWTO', v_lang, p_reply);
          RETURN;
        END IF;
        v_batch := hv_register_batch(p_channel, p_from, v_ids(1), v_store, v_bags, v_lang);
        harvestly_engine.queue_welcome(v_batch, v_today);                     -- C-17: welcome (credit, how to STOP) FIRST
        hv_queue_test_first(v_batch, p_reply);
        p_cmd := 'JOIN';
        RETURN;
      END IF;
      -- ambiguous (more than one) or unknown ward: register nothing, send the candidates
      p_reply := CASE v_lang WHEN 'sw' THEN 'Harvestly: Kata gani? Jibu SAJILI <kata> <hifadhi> <magunia> na mojawapo ya: ' || ward_list || '.'
                             ELSE 'Harvestly: Which ward? Reply JOIN <ward> <storage> <bags> with one of: ' || ward_list || '.' END;   -- C4-03
    END IF;
  END IF;
  hv_queue_reply(p_channel, p_from, 'HOWTO', v_lang, p_reply);                 -- R1-02: the how-to IS queued
END hv_handle_inbound;
/

-- =====================================================================================
-- 2. USSD menu (Africa's Talking: text = answers so far joined by '*'; reply starts CON or END)
--    Safaricom limit is 160 characters per screen, enforced here with SUBSTR as a last resort.
--    All text is GSM-7. Language: the batch language of this phone when known (R1-18), else English.
-- =====================================================================================
CREATE OR REPLACE FUNCTION hv_ussd_menu(p_phone IN VARCHAR2, p_text IN VARCHAR2,
                                        p_session IN VARCHAR2 DEFAULT NULL) RETURN VARCHAR2 IS
  nl CONSTANT VARCHAR2(1) := CHR(10);
  TYPE t_parts IS TABLE OF VARCHAR2(2000) INDEX BY PLS_INTEGER;   -- C-15: bytes, not characters
  parts   t_parts;
  n       PLS_INTEGER := 0;
  v_text  VARCHAR2(2000 CHAR) := SUBSTR(p_text, 1, 500);                    -- R1-07
  v_out   VARCHAR2(600);
  v_ward  NUMBER;
  v_name  hv_wards.name%TYPE;
  v_batch NUMBER;
  v_cmd   VARCHAR2(20);
  v_reply VARCHAR2(1000);
  v_new   BOOLEAN;
  v_blocked BOOLEAN;
  b       harvestly_engine.t_batch;
  v_days  harvestly_engine.t_weather_tab;
  v_fc    harvestly_engine.t_weather_tab;
  v_today DATE := harvestly_engine.today_eat;
  v_left  PLS_INTEGER;
  v_adv   VARCHAR2(20);
  v_hash  VARCHAR2(64);
  v_lang  VARCHAR2(2) := 'en';
  v_adv_t VARCHAR2(60);
  v_core  VARCHAR2(400);
  v_next  VARCHAR2(120);

  FUNCTION t(p_en IN VARCHAR2, p_sw IN VARCHAR2) RETURN VARCHAR2 IS
  BEGIN
    RETURN CASE WHEN v_lang = 'sw' THEN p_sw ELSE p_en END;
  END t;

  -- R1-18: stable order by ward_id (not by name), so a ward added mid-session cannot shift the numbers
  FUNCTION ward_by_index(p_n IN NUMBER, p_name OUT VARCHAR2) RETURN NUMBER IS
    v_id NUMBER;
  BEGIN
    SELECT ward_id, SUBSTR(name, 1, 18) INTO v_id, p_name
      FROM (SELECT ward_id, name, ROW_NUMBER() OVER (ORDER BY ward_id) rn FROM hv_wards)
     WHERE rn = p_n;
    RETURN v_id;
  EXCEPTION WHEN NO_DATA_FOUND THEN
    RETURN NULL;
  END ward_by_index;

  FUNCTION storage_of(p_choice IN VARCHAR2) RETURN VARCHAR2 IS
  BEGIN
    RETURN CASE p_choice WHEN '1' THEN 'drying' WHEN '2' THEN 'sack' WHEN '3' THEN 'crib'
                         WHEN '4' THEN 'floor' WHEN '5' THEN 'hermetic' END;
  END storage_of;

  FUNCTION advice_label(p_adv IN VARCHAR2) RETURN VARCHAR2 IS
  BEGIN
    RETURN CASE p_adv
             WHEN 'TEST_FIRST'     THEN t('get a moisture test', 'pima unyevu')
             WHEN 'SORT_AND_SELL'  THEN t('sort and sell soon', 'chagua na uuze mapema')
             WHEN 'OPEN_AND_DRY'   THEN t('open the bags and dry', 'fungua magunia ukaushe')
             WHEN 'CONFIRM_DRY'    THEN t('confirm it is dry', 'thibitisha imekauka')
             WHEN 'RETEST'         THEN t('test again', 'pima tena')
             WHEN 'DRY_NOW'        THEN t('dry it now', 'kausha sasa')
             WHEN 'READY_TO_STORE' THEN t('ready to store', 'tayari kuhifadhi')
             WHEN 'NEARLY_DRY'     THEN t('nearly dry, keep drying', 'karibu kukauka, endelea')
             ELSE t('nothing now', 'hakuna sasa') END;
  END advice_label;
BEGIN
  IF p_phone IS NULL THEN
    RETURN 'END Phone number missing.';
  END IF;
  v_hash := harvestly_engine.address_hash(p_phone);
  -- R3 C3-02: USSD has its own inbound cap per phone (a separate counter from SMS: the key is the hash with a 'u' suffix).
  -- A menu session is a handful of requests, so 30 an hour is far above honest use. Over the cap: a short END screen.
  IF hv_rate_hit(SUBSTR(v_hash, 1, 63) || 'u') > hv_limit('max_ussd_per_hour', 30) THEN
    RETURN 'END Too many requests. Please try again later.';
  END IF;
  BEGIN                                              -- batch language of this phone, if it has one
    SELECT lang INTO v_lang FROM (
      SELECT lang FROM hv_batches WHERE channel = 'sms' AND farmer_hash = v_hash
       ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, created_at DESC, batch_id DESC)
     WHERE ROWNUM = 1;
  EXCEPTION WHEN NO_DATA_FOUND THEN
    v_lang := 'en';
  END;

  IF v_text IS NOT NULL THEN                         -- split 'a*b*c'
    FOR i IN 1 .. LEAST(REGEXP_COUNT(v_text, '[^*]+'), 10) LOOP
      n := n + 1;
      parts(n) := REGEXP_SUBSTR(v_text, '[^*]+', 1, i);
    END LOOP;
  END IF;

  IF n = 0 THEN
    v_out := t('CON Harvestly maize alerts' || nl || '1 Register grain' || nl || '2 My grain' || nl || '3 Test result',
               'CON Harvestly arifa za mahindi' || nl || '1 Sajili mahindi' || nl || '2 Mahindi yangu' || nl || '3 Matokeo ya kipimo');

  ELSIF parts(1) = '1' THEN                          -- register: ward -> storage -> bags
    IF n = 1 THEN
      v_out := t('CON Your ward?', 'CON Kata yako?');
      FOR i IN 1 .. 6 LOOP
        v_ward := ward_by_index(i, v_name);
        EXIT WHEN v_ward IS NULL;
        v_out := v_out || nl || i || ' ' || v_name;
      END LOOP;
    ELSIF n = 2 THEN
      v_out := t('CON Where is the grain?' || nl || '1 Drying outside' || nl || '2 Sacks' || nl || '3 Crib'
                 || nl || '4 Floor' || nl || '5 Sealed bags',
                 'CON Mahindi yako wapi?' || nl || '1 Yanakaushwa nje' || nl || '2 Magunia' || nl || '3 Kihenge'
                 || nl || '4 Sakafuni' || nl || '5 Mifuko iliyofungwa');
    ELSIF n = 3 THEN
      v_out := t('CON How many 90 kg bags? Type a number, e.g. 12',
                 'CON Magunia mangapi ya kilo 90? Andika namba, mf. 12');
    ELSE
      v_ward := ward_by_index(hv_to_num(parts(2)), v_name);
      IF v_ward IS NULL OR storage_of(parts(3)) IS NULL OR NOT REGEXP_LIKE(parts(4), '^[0-9]{1,4}$') THEN
        v_out := t('END Sorry, that did not work. Dial again and follow the menu.',
                   'END Samahani, haikufaulu. Piga tena ufuate menyu.');
      ELSIF hv_is_optedout(v_hash) THEN
        v_out := t('END You opted out. SMS START to this number to receive alerts, then dial again.',
                   'END Ulijiondoa. Tuma SMS START ili kupata arifa, kisha upige tena.');
      ELSE
        -- R1-03 / R1-18: idempotent per sessionId and per (phone, ward, storage, bags, day)
        -- R3 C3-07: the daily cap is applied inside hv_register_once, after the retry checks (C-05 cap still holds)
        v_batch := hv_register_once('sms', p_phone, p_session, v_ward, storage_of(parts(3)), TO_NUMBER(parts(4)), v_lang, v_new, v_blocked);
        IF v_blocked THEN
          v_out := t('END Too many registrations from this number today. Try again tomorrow.',
                     'END Usajili mwingi sana leo kutoka namba hii. Jaribu kesho.');
        ELSE
          IF v_new THEN
            harvestly_engine.queue_welcome(v_batch, v_today);    -- C-17: welcome (credit, how to STOP) first
            hv_queue_test_first(v_batch, v_reply);               -- then the ask-for-a-test message
          END IF;
          v_out := t('END Registered. We are sending you an SMS on how to test your grain.',
                     'END Umesajiliwa. Tutakutumia SMS ya jinsi ya kupima mahindi yako.');
        END IF;
      END IF;
    END IF;

  ELSIF parts(1) = '2' THEN                          -- status of the latest batch (read only)
    BEGIN
      SELECT batch_id INTO v_batch FROM (
        SELECT batch_id FROM hv_batches WHERE channel = 'sms' AND farmer_hash = v_hash
         ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, created_at DESC, batch_id DESC)
       WHERE ROWNUM = 1;
      harvestly_engine.load_batch(v_batch, b);
      harvestly_engine.load_weather(b.ward_id, v_today, v_days);
      FOR i IN 1 .. v_days.COUNT LOOP
        IF v_days(i).wx_date > v_today THEN v_fc(v_fc.COUNT + 1) := v_days(i); END IF;
      END LOOP;
      IF b.moisture IS NULL THEN
        v_out := t('END Not tested yet. Get a meter reading at your co-op or NCPB depot and SMS METER and the number.',
                   'END Bado haijapimwa. Pima kwa mita kwenye chama chako au NCPB, kisha tuma SMS MITA na namba.');
      ELSE
        v_left := harvestly_engine.days_left(b, v_fc);
        v_adv  := harvestly_engine.advice(b);
        -- C-07 / K-04: say what was measured and when, and that the storage time is an estimate; never "safe".
        -- Same wording helpers as the SMS templates (measured_text, risk_text). 365 is the horizon cap, never a prediction;
        -- risk_text turns it into "3 months or more".
        v_core := t('END Last test: ', 'END Kipimo cha mwisho: ') || harvestly_engine.measured_text(b, v_lang <> 'sw')
               || t('. Storage time left: ', '. Muda uliobaki: ') || harvestly_engine.risk_text(v_left, v_lang <> 'sw', b.storage <> 'hermetic') || '.';
        v_next := t(' Next: ', ' Hatua: ') || advice_label(v_adv) || '.';
        v_out := CASE WHEN LENGTH(v_core || v_next) <= 160 THEN v_core || v_next ELSE v_core END;
      END IF;
    EXCEPTION WHEN NO_DATA_FOUND THEN
      v_out := t('END No grain registered for this number. Dial again and choose 1.',
                 'END Hakuna mahindi yaliyosajiliwa. Piga tena uchague 1.');
    END;

  ELSIF parts(1) = '3' THEN                          -- farmer's test result -> same engine path as an SMS reply
    IF n = 1 THEN
      v_out := t('CON Test result' || nl || '1 Salt sticks' || nl || '2 Salt loose' || nl || '3 Meter reading',
                 'CON Matokeo ya kipimo' || nl || '1 Chumvi inagandamana' || nl || '2 Chumvi inatiririka' || nl || '3 Namba ya mita');
    ELSIF n = 2 AND parts(2) = '3' THEN
      v_out := t('CON Type the meter reading, e.g. 13.5', 'CON Andika namba ya mita, mf. 13.5');
    ELSIF n = 3 AND parts(2) = '3' AND NOT REGEXP_LIKE(parts(3), '^[0-9]{1,2}([.,][0-9]{1,2})?$') THEN
      -- R3 C3-06: only a number is sent on as METER. Anything else ("STOP", "END", words) used to become "METER STOP",
      -- which the engine reads as an opt-out while the screen said "did not understand".
      v_out := t('END That was not a number. Dial again and type the reading, e.g. 13.5',
                 'END Hiyo si namba. Piga tena uandike namba ya mita, mf. 13.5');
    ELSIF (n = 2 AND parts(2) IN ('1', '2')) OR (n = 3 AND parts(2) = '3') THEN
      -- R1-18: call the engine directly (no JOIN attempt, no how-to SMS) and look at what it understood
      harvestly_engine.process_reply('sms', p_phone,
                        CASE parts(2) WHEN '1' THEN 'SALT YES' WHEN '2' THEN 'SALT NO' ELSE 'METER ' || parts(3) END,
                        NULL, v_batch, v_cmd, v_reply);
      IF v_batch IS NULL THEN
        v_out := t('END No grain registered for this number. Dial again and choose 1.',
                   'END Hakuna mahindi yaliyosajiliwa. Piga tena uchague 1.');
      ELSIF v_cmd IN ('SALT_YES', 'SALT_NO', 'SALT_NO_IGNORED', 'METER') THEN
        v_out := t('END Recorded. We are sending you the advice by SMS.', 'END Imerekodiwa. Tutakutumia ushauri kwa SMS.');
      ELSE
        v_out := t('END Sorry, we did not understand that. Dial again and try once more.',
                   'END Samahani, hatukuelewa. Piga tena ujaribu.');
      END IF;
    ELSE
      v_out := t('END Wrong choice. Dial again.', 'END Chaguo si sahihi. Piga tena.');
    END IF;

  ELSE
    v_out := t('END Wrong choice. Dial again.', 'END Chaguo si sahihi. Piga tena.');
  END IF;
  RETURN SUBSTR(v_out, 1, 160);                      -- hard cap: Safaricom USSD screen
END hv_ussd_menu;
/

-- =====================================================================================
-- 3. Open-Meteo weather cache: ONE call per ward (not per farmer); needs an APEX session
--    (APEX Automation provides it). Mirrors engine.daily_from_open_meteo / rain_next_hours:
--      * hourly values -> one row per local day, days with < 20 hourly temp/RH values are dropped
--      * rain24 = precipitation sum and max probability over the 24 hourly steps from 17:00 today
--    Open-Meteo free tier is non-commercial and needs CC BY 4.0 credit (templates print "Open-Meteo").
--    The refresh never raises: each ward has its own exception block, the outcome goes to hv_weather_fetch
--    through harvestly_engine.record_weather_fetch (R1-09), and the work of a ward is committed before the next (R1-16).
-- =====================================================================================
CREATE OR REPLACE PROCEDURE hv_refresh_ward_weather(p_ward_id IN NUMBER, p_today IN DATE DEFAULT NULL,
                                                    p_max_age_hours IN NUMBER DEFAULT 6) IS
  c_amp   CONSTANT VARCHAR2(1) := CHR(38);
  v_today DATE := TRUNC(NVL(p_today, harvestly_engine.today_eat));
  v_lat   hv_wards.lat%TYPE;
  v_lon   hv_wards.lon%TYPE;
  v_url   VARCHAR2(1000);
  v_json  CLOB;
  v_fresh PLS_INTEGER;
  v_err   VARCHAR2(500);
  v_start VARCHAR2(16) := TO_CHAR(v_today, 'YYYY-MM-DD') || 'T17:00';

  -- R1-27: always a dot decimal separator, never a trailing dot ("1." for a whole degree)
  FUNCTION fmt_coord(p_v IN NUMBER) RETURN VARCHAR2 IS
  BEGIN
    RETURN RTRIM(TO_CHAR(p_v, 'FM990.99999', 'NLS_NUMERIC_CHARACTERS=''. '''), '.');
  END fmt_coord;
BEGIN
  SAVEPOINT hv_wx_start;
  -- R1-17 / R1-26: cache keyed on run_date. Fresh = the rain24 row of TODAY exists and was fetched within
  -- p_max_age_hours (compared as TIMESTAMP WITH TIME ZONE against SYSTIMESTAMP), and tomorrow is covered.
  SELECT COUNT(*) INTO v_fresh FROM hv_weather_rain24 r
   WHERE r.ward_id = p_ward_id AND r.run_date = v_today
     AND r.fetched_at > SYSTIMESTAMP - NUMTODSINTERVAL(p_max_age_hours, 'HOUR')
     AND EXISTS (SELECT 1 FROM hv_weather w WHERE w.ward_id = p_ward_id AND w.wx_date = v_today + 1);
  IF v_fresh > 0 THEN
    RETURN;
  END IF;

  SELECT lat, lon INTO v_lat, v_lon FROM hv_wards WHERE ward_id = p_ward_id;
  v_url := 'https://api.open-meteo.com/v1/forecast'
        || '?latitude='  || fmt_coord(v_lat)
        || c_amp || 'longitude=' || fmt_coord(v_lon)
        || c_amp || 'hourly=temperature_2m,relative_humidity_2m,precipitation,precipitation_probability'
        || c_amp || 'past_days=2' || c_amp || 'forecast_days=8'
        || c_amp || 'timezone=Africa%2FNairobi';

  v_json := apex_web_service.make_rest_request(p_url => v_url, p_http_method => 'GET');
  IF apex_web_service.g_status_code <> 200 THEN
    RAISE_APPLICATION_ERROR(-20010, 'Open-Meteo HTTP ' || apex_web_service.g_status_code);
  END IF;

  MERGE INTO hv_weather t USING (
    WITH h AS (
      SELECT x.rn, x.ts, tp.v temp_c, rh.v rh, pr.v rain, pp.v prob
        FROM JSON_TABLE(v_json, '$.hourly.time[*]' COLUMNS (rn FOR ORDINALITY, ts VARCHAR2(16) PATH '$')) x
        LEFT JOIN JSON_TABLE(v_json, '$.hourly.temperature_2m[*]' COLUMNS (rn FOR ORDINALITY, v NUMBER PATH '$')) tp ON tp.rn = x.rn
        LEFT JOIN JSON_TABLE(v_json, '$.hourly.relative_humidity_2m[*]' COLUMNS (rn FOR ORDINALITY, v NUMBER PATH '$')) rh ON rh.rn = x.rn
        LEFT JOIN JSON_TABLE(v_json, '$.hourly.precipitation[*]' COLUMNS (rn FOR ORDINALITY, v NUMBER PATH '$')) pr ON pr.rn = x.rn
        LEFT JOIN JSON_TABLE(v_json, '$.hourly.precipitation_probability[*]' COLUMNS (rn FOR ORDINALITY, v NUMBER PATH '$')) pp ON pp.rn = x.rn)
    SELECT TO_DATE(SUBSTR(ts, 1, 10), 'YYYY-MM-DD') wx_date, AVG(temp_c) temp_c, AVG(rh) rh,
           SUM(rain) rain_mm, MAX(prob) rain_prob
      FROM h GROUP BY SUBSTR(ts, 1, 10)
    HAVING COUNT(temp_c) >= 20 AND COUNT(rh) >= 20) s
  ON (t.ward_id = p_ward_id AND t.wx_date = s.wx_date)
  WHEN MATCHED THEN UPDATE SET t.temp_c = s.temp_c, t.rh = s.rh, t.rain_mm = s.rain_mm,
                               t.rain_prob = s.rain_prob, t.fetched_at = SYSTIMESTAMP
  WHEN NOT MATCHED THEN INSERT (ward_id, wx_date, temp_c, rh, rain_mm, rain_prob)
                        VALUES (p_ward_id, s.wx_date, s.temp_c, s.rh, s.rain_mm, s.rain_prob);

  -- rain in the 24 h after the 17:00 run (the engine then says "in the next 24 hours", not "tomorrow").
  -- R1-17: keyed on run_date; fetched_at is TIMESTAMP WITH TIME ZONE (R1-26).
  DELETE FROM hv_weather_rain24 WHERE ward_id = p_ward_id AND run_date = v_today;
  INSERT INTO hv_weather_rain24 (ward_id, run_date, rain_mm, rain_prob, fetched_at)
  SELECT p_ward_id, v_today, SUM(rain), MAX(prob), SYSTIMESTAMP
    FROM (SELECT x.rn, pr.v rain, pp.v prob
            FROM JSON_TABLE(v_json, '$.hourly.time[*]' COLUMNS (rn FOR ORDINALITY, ts VARCHAR2(16) PATH '$')) x
            LEFT JOIN JSON_TABLE(v_json, '$.hourly.precipitation[*]' COLUMNS (rn FOR ORDINALITY, v NUMBER PATH '$')) pr ON pr.rn = x.rn
            LEFT JOIN JSON_TABLE(v_json, '$.hourly.precipitation_probability[*]' COLUMNS (rn FOR ORDINALITY, v NUMBER PATH '$')) pp ON pp.rn = x.rn
           WHERE x.rn >= (SELECT MIN(y.rn) FROM JSON_TABLE(v_json, '$.hourly.time[*]' COLUMNS (rn FOR ORDINALITY, ts VARCHAR2(16) PATH '$')) y
                           WHERE y.ts = v_start)
             AND x.rn < (SELECT MIN(y.rn) FROM JSON_TABLE(v_json, '$.hourly.time[*]' COLUMNS (rn FOR ORDINALITY, ts VARCHAR2(16) PATH '$')) y
                          WHERE y.ts = v_start) + 24)
   HAVING COUNT(*) > 0;          -- start time not in the payload: no row (the stale one was deleted above); the engine falls back

  harvestly_engine.record_weather_fetch(p_ward_id, TRUE, NULL);     -- R1-09 (autonomous transaction)
  COMMIT;                                                           -- R1-16: a later ROLLBACK must not discard this ward
EXCEPTION WHEN OTHERS THEN
  v_err := hv_scrub(SQLERRM);                                       -- R1-09: not swallowed; recorded, scrubbed
  ROLLBACK TO hv_wx_start;
  harvestly_engine.record_weather_fetch(p_ward_id, FALSE, v_err);
  COMMIT;
END hv_refresh_ward_weather;
/

-- Every ward that has an active batch. Used by the 16:45 automation and again (cheaply, cache) by the daily job.
CREATE OR REPLACE PROCEDURE hv_refresh_all_weather(p_today IN DATE DEFAULT NULL) IS
  v_today DATE := TRUNC(NVL(p_today, harvestly_engine.today_eat));
BEGIN
  FOR w IN (SELECT DISTINCT ward_id FROM hv_batches WHERE status = 'active' ORDER BY ward_id) LOOP
    hv_refresh_ward_weather(w.ward_id, v_today);                    -- never raises, commits per ward
  END LOOP;
END hv_refresh_all_weather;
/

-- =====================================================================================
-- 4. Outgoing messages. Queue protocol (see harvestly_engine.pks):
--      QUEUED -> SENDING (claimed and committed BEFORE any HTTP call) -> SENT, or back to QUEUED (retry, max 3), or FAILED.
--    The sender never selects QUEUED rows itself (R1-05): claim_queued does it with FOR UPDATE SKIP LOCKED and skips
--    and CANCELs rows of opted-out numbers (R1-03).
--    Config keys (hv_config): at_username, at_api_key, at_sender_id (optional), at_base_url
--    (default https://api.africastalking.com; sandbox: https://api.sandbox.africastalking.com), telegram_bot_token.
--    A Telegram user must message the bot first before it can write to them.
--
--    SECRETS IN URLS (R1-01 / R1-11 / R2 C-04): the Telegram Bot API REQUIRES the bot token in the URL path; it has no
--    header or body alternative. So it cannot be kept out of the URL. What is done, and what is NOT guaranteed:
--      * the URL is built only inside hv_send_one, in a local variable, and is never written by this code;
--      * APEX debug is switched OFF for the call (hv_ws_quiet), so debug level 4+ cannot record the URL;
--      * every error string passes through hv_scrub before it reaches hv_messages.error_text / hv_run_log;
--      * NOT guaranteed: APEX may still record the request URL in its own web-service activity log
--        (APEX_WEBSERVICE_LOG / Monitor Activity), whatever the debug level. This was not tested (no APEX here).
--        Operator steps: after any Telegram use, search that log for 'api.telegram.org/bot'; if found, revoke the token
--        (BotFather /revoke) and purge the log; use a throw-away demo bot and revoke it after the demo; for a real pilot
--        send by Africa's Talking SMS only, whose key travels in a header (apiKey), not in the URL.
--    Message statuses: QUEUED -> SENDING (claimed and committed BEFORE any HTTP call; sent_at = claim time) -> SENT,
--    or back to QUEUED (retry, max 3), or FAILED. A row stuck in SENDING for 15 minutes is put back to QUEUED by
--    claim_queued itself (C-18: no manual step; delivery is then at-least-once).
-- =====================================================================================
-- R2 C-04: switch APEX debug off before a call whose URL holds a secret. Dynamic SQL, so a missing procedure
-- cannot make the sender invalid; failure to switch it off is ignored (the call still goes ahead).
CREATE OR REPLACE PROCEDURE hv_ws_quiet IS
BEGIN
  EXECUTE IMMEDIATE 'BEGIN apex_debug.disable; END;';
EXCEPTION WHEN OTHERS THEN
  NULL;
END hv_ws_quiet;
/

-- Send one claimed (SENDING) message. Never raises: the outcome goes to mark_sent / mark_failed.
CREATE OR REPLACE PROCEDURE hv_send_one(p_msg_id IN NUMBER) IS
  v_chan    hv_messages.channel%TYPE;
  v_to      hv_messages.to_addr%TYPE;
  v_body    hv_messages.body%TYPE;
  v_resp    CLOB;
  v_json    CLOB;
  v_ok      BOOLEAN := FALSE;
  v_ref     VARCHAR2(100);
  v_err     VARCHAR2(1000);
  v_code    NUMBER;
  v_stat    VARCHAR2(100);
BEGIN
  SELECT channel, to_addr, body INTO v_chan, v_to, v_body FROM hv_messages WHERE msg_id = p_msg_id;
  BEGIN
    IF v_to IS NULL THEN
      RAISE_APPLICATION_ERROR(-20011, 'no recipient address');
    END IF;
    apex_web_service.g_request_headers.DELETE;
    IF v_chan = 'telegram' THEN
      apex_web_service.g_request_headers(1).name := 'Content-Type';
      apex_web_service.g_request_headers(1).value := 'application/json';
      -- C-16: Telegram addresses are stored as 'tg:<chat id>' so they can never collide with a phone number's hash
      SELECT JSON_OBJECT('chat_id' VALUE TO_NUMBER(REPLACE(v_to, 'tg:', '')), 'text' VALUE v_body RETURNING CLOB)
        INTO v_json FROM dual;
      hv_ws_quiet;                                   -- C-04
      v_resp := apex_web_service.make_rest_request(
                  p_url => 'https://api.telegram.org/bot' || hv_cfg('telegram_bot_token') || '/sendMessage',
                  p_http_method => 'POST', p_body => v_json);
      IF apex_web_service.g_status_code NOT BETWEEN 200 AND 299 THEN
        v_err := 'HTTP ' || apex_web_service.g_status_code || ' ' || SUBSTR(JSON_VALUE(v_resp, '$.description'), 1, 200);
      ELSIF JSON_VALUE(v_resp, '$.ok') = 'true' THEN
        v_ok := TRUE;
        v_ref := SUBSTR(JSON_VALUE(v_resp, '$.result.message_id'), 1, 100);
      ELSE
        v_err := 'Telegram not ok ' || SUBSTR(JSON_VALUE(v_resp, '$.description'), 1, 200);
      END IF;
    ELSE
      apex_web_service.g_request_headers(1).name := 'apiKey';
      apex_web_service.g_request_headers(1).value := hv_cfg('at_api_key');
      apex_web_service.g_request_headers(2).name := 'Content-Type';
      apex_web_service.g_request_headers(2).value := 'application/x-www-form-urlencoded';
      apex_web_service.g_request_headers(3).name := 'Accept';
      apex_web_service.g_request_headers(3).value := 'application/json';
      v_resp := apex_web_service.make_rest_request(
                  p_url => hv_cfg('at_base_url', 'https://api.africastalking.com') || '/version1/messaging',
                  p_http_method => 'POST',
                  p_body => 'username=' || apex_util.url_encode(hv_cfg('at_username'))
                         || CHR(38) || 'to=' || apex_util.url_encode(v_to)
                         || CHR(38) || 'message=' || apex_util.url_encode(v_body)
                         || CASE WHEN hv_cfg('at_sender_id') IS NOT NULL
                                 THEN CHR(38) || 'from=' || apex_util.url_encode(hv_cfg('at_sender_id')) END);
      IF apex_web_service.g_status_code NOT BETWEEN 200 AND 299 THEN
        v_err := 'HTTP ' || apex_web_service.g_status_code || ' ' || SUBSTR(v_resp, 1, 300);
      ELSE
        -- R1-06: HTTP 201 alone is never success. AT answers 201 even when a recipient failed.
        -- Recipient statusCode: 100 Processed, 101 Sent, 102 Queued are accepted; anything else
        -- (InvalidPhoneNumber 403, InsufficientBalance 405, UserInBlacklist, ...) fails the message.
        BEGIN
          SELECT status_code, status_text, message_id INTO v_code, v_stat, v_ref
            FROM JSON_TABLE(v_resp, '$.SMSMessageData.Recipients[*]'
                   COLUMNS (status_code NUMBER        PATH '$.statusCode',
                            status_text VARCHAR2(100) PATH '$.status',
                            message_id  VARCHAR2(100) PATH '$.messageId',
                            msisdn      VARCHAR2(30)  PATH '$.number'))
           FETCH FIRST 1 ROWS ONLY;
          IF v_code IN (100, 101, 102) THEN
            v_ok := TRUE;
          ELSE
            v_err := 'AT ' || v_code || ' ' || v_stat;
          END IF;
        EXCEPTION WHEN NO_DATA_FOUND THEN
          v_err := 'AT no recipient in reply: ' || SUBSTR(JSON_VALUE(v_resp, '$.SMSMessageData.Message'), 1, 200);
        END;
      END IF;
    END IF;
  EXCEPTION WHEN OTHERS THEN
    v_ok := FALSE;
    v_err := SQLERRM;
  END;

  IF v_ok THEN
    harvestly_engine.mark_sent(p_msg_id, v_ref);
  ELSE
    harvestly_engine.mark_failed(p_msg_id, hv_scrub(v_err));          -- R1-01 / R1-11: scrubbed before it is stored
  END IF;
  -- R1-11: the plaintext address is not kept once the message is final (SENT or FAILED); a retry keeps it
  UPDATE hv_messages SET to_addr = NULL WHERE msg_id = p_msg_id AND status IN ('SENT', 'FAILED');
  COMMIT;
EXCEPTION WHEN OTHERS THEN
  -- the row could not even be read or updated; make a last attempt to release it, then give up quietly
  BEGIN
    ROLLBACK;
    harvestly_engine.mark_failed(p_msg_id, hv_scrub(SQLERRM));
    COMMIT;
  EXCEPTION WHEN OTHERS THEN
    NULL;                          -- row stays SENDING; visible in hv_messages for the operator
  END;
END hv_send_one;
/

-- Claim ONE queued message for an immediate send (used by hv_send_reply_now). Same protocol as claim_queued:
-- the UPDATE takes the row lock, so if the 5-minute sender claimed it first this does nothing.
CREATE OR REPLACE PROCEDURE hv_claim_and_send(p_msg_id IN NUMBER) IS
BEGIN
  -- C-01: the STOP confirmation (code STOPPED) is the one message an opted-out number still receives, exactly once
  UPDATE hv_messages m SET status = 'CANCELLED', to_addr = NULL
   WHERE m.msg_id = p_msg_id AND m.status = 'QUEUED' AND m.code <> 'STOPPED'
     AND EXISTS (SELECT 1 FROM hv_optout o WHERE o.addr_hash = m.to_hash);            -- R1-03
  IF SQL%ROWCOUNT > 0 THEN COMMIT; RETURN; END IF;
  UPDATE hv_messages SET status = 'SENDING', sent_at = SYSTIMESTAMP WHERE msg_id = p_msg_id AND status = 'QUEUED';   -- C-08: the 15-minute requeue needs sent_at
  IF SQL%ROWCOUNT = 0 THEN
    COMMIT;
    RETURN;                                          -- someone else has it
  END IF;
  COMMIT;                                            -- SENDING is visible before the HTTP call
  hv_send_one(p_msg_id);
END hv_claim_and_send;
/

-- R1-02: try to deliver the reply(ies) just queued for this sender at once. Any failure here is harmless: the row is
-- either still QUEUED (the 5-minute sender job delivers it) or already marked FAILED / retried by hv_send_one.
-- This also COMMITs the inbound work, which is intended in an ORDS handler. Not used by USSD (its HTTP answer must be fast).
CREATE OR REPLACE PROCEDURE hv_send_reply_now(p_channel IN VARCHAR2, p_from IN VARCHAR2) IS
  v_hash VARCHAR2(64) := harvestly_engine.address_hash(p_from);
BEGIN
  COMMIT;                                            -- make sure the queued rows are durable before any HTTP call
  -- R3 C3-08: APEX_WEB_SERVICE needs an APEX session, and an ORDS handler does not have one (section 3). Until someone has
  -- shown on the target that it works from here, the inline send is OFF and the mandatory 5-minute sender delivers the reply
  -- (at most about 5 minutes later) without burning one of the 3 attempts on a failed inline call. After checking on the
  -- target, switch it on with: INSERT INTO hv_config (cfg_key, cfg_value) VALUES ('inline_send', 'Y');
  IF NVL(hv_cfg('inline_send'), 'N') <> 'Y' THEN
    RETURN;
  END IF;
  FOR r IN (SELECT msg_id FROM hv_messages
             WHERE to_hash = v_hash AND channel = p_channel AND kind = 'REPLY' AND status = 'QUEUED'
               AND created_at > SYSTIMESTAMP - INTERVAL '2' MINUTE
             ORDER BY msg_id FETCH FIRST 5 ROWS ONLY) LOOP
    hv_claim_and_send(r.msg_id);
  END LOOP;
EXCEPTION WHEN OTHERS THEN
  NULL;                    -- fall back to the sender job (section 7 makes it mandatory); the message is never lost
END hv_send_reply_now;
/

-- The 5-minute sender (mandatory, R1-02). Work is selected ONLY through claim_queued (R1-05, R1-03).
CREATE OR REPLACE PROCEDURE hv_send_queued(p_limit IN NUMBER DEFAULT 500) IS
  v_ids SYS.ODCINUMBERLIST;
BEGIN
  harvestly_engine.claim_queued(p_limit, v_ids);     -- QUEUED -> SENDING, committed; opted-out rows are CANCELLED
  FOR i IN 1 .. v_ids.COUNT LOOP
    hv_send_one(v_ids(i));                           -- never raises, commits per message
  END LOOP;
END hv_send_queued;
/

-- =====================================================================================
-- 5. The 17:00 job: weather (cached, so cheap when the 16:45 refresh worked), then every active batch.
--    daily_run_all locks each batch (SELECT ... FOR UPDATE) and is idempotent per batch per day (hv_batches.last_run),
--    so a second run or a concurrent reply cannot lose an update. An error in one ward (e.g. Open-Meteo down) never
--    stops the others; daily_run_* logs a per-batch error row in hv_run_log when tomorrow's weather is missing.
--    R1-05: this job does NOT call the sender. Nothing else fires at exactly 17:00; the sender runs at :02/:07/...
-- =====================================================================================
CREATE OR REPLACE PROCEDURE hv_daily_job(p_today IN DATE DEFAULT NULL) IS
  v_today DATE := TRUNC(NVL(p_today, harvestly_engine.today_eat));
BEGIN
  hv_refresh_all_weather(v_today);
  harvestly_engine.daily_run_all(v_today);
  COMMIT;
END hv_daily_job;
/

-- =====================================================================================
-- 6. ORDS module   (base URL: https://<host>/ords/<schema alias>/hv/...)
--    Webhook secrets live in hv_config only (telegram_secret, sms_secret, ussd_secret); prefer APEX Web Credentials
--    if you can. A path secret ends up in ORDS and proxy access logs and in the AT dashboard: rotate it. The AT callbacks
--    are ALSO refused unless hv_config 'at_ip_allowlist' lists the caller (R2 C-05; fail closed, see hv_ip_allowed).
--
--    HOW THE REQUEST BODY IS READ (R1-12 / R2 C-03; Oracle ORDS Developer's Guide, "Implicit Parameters"):
--      * ":body_text ... must only be dereferenced once inside the entire PL/SQL block. If you need this value more than
--        once, assign it to a local variable, and dereference the local variable instead." Every handler below does
--        exactly that: one assignment into a local CLOB, then only the local variable is used.
--      * The same page says ORDS binds form fields (application/x-www-form-urlencoded) automatically as :fieldname ONLY
--        when none of :body, :body_text, :body_json is used in the block. These handlers use :body_text on purpose and
--        therefore declare NO parameters for the form fields (the old 'URI' source-type parameters are gone) and parse
--        the raw body themselves (hv_body_value). That does not depend on how ORDS binds form data.
--      * Africa's Talking: its own documentation pages could not be fetched (HTTP 403). Third-party documentation and
--        examples say the SMS callback sends the fields from, to, text, date, id, linkId and the USSD callback sends
--        sessionId, serviceCode, phoneNumber, text, as form-encoded POST fields. hv_body_value also accepts a JSON body.
--        UNVERIFIED against a real callback: test with an Africa's Talking SANDBOX callback before anything is claimed.
--        R3: the parser is defensive in both directions. hv_body_ok answers 400 for a malformed body (bad JSON, a '%' not
--        followed by two hex digits, invalid UTF-8, too long); hv_body_value reads a form body or a JSON body, whichever
--        arrives, from the CLOB; every value is cut to the width of the variable it goes into. The one-callback test
--        procedure is in plsql/README.md ("Testing against a real callback").
--
--    FORGED SENDERS (R2 C-05): AT sets `from` itself; the only way to forge it is to reach the endpoint, which needs the
--    path secret AND a source IP on the allowlist. If either leaks, a forger can (a) JOIN a victim's number (a welcome and
--    a test message go to the victim; capped by max_batches_per_day and the reply budgets), (b) STOP a farmer, (c) START
--    an opted-out number, (d) plant a METER reading for a farmer. Mitigations here: secret + allowlist, per-phone caps,
--    replay protection on AT `id` / Telegram `update_id`, and a STOP confirmation to the real phone. Not mitigated: a
--    forged START or METER from someone who has both the secret and an allowed IP. Rotate the secret if in doubt.
-- =====================================================================================
BEGIN
  ORDS.ENABLE_SCHEMA(p_enabled => TRUE, p_url_mapping_type => 'BASE_PATH', p_url_mapping_pattern => 'harvestly');

  ORDS.DEFINE_MODULE(p_module_name => 'harvestly', p_base_path => '/hv/', p_items_per_page => 0, p_status => 'PUBLISHED');

  -- ---- Telegram webhook ----------------------------------------------------------------
  -- setWebhook with secret_token=<telegram_secret> makes Telegram send it in the header
  -- X-Telegram-Bot-Api-Secret-Token (missing or wrong header: 403).
  -- R1-01: the reply is NOT returned inline ({"method":"sendMessage"} would be delivered by Telegram AND by the queue).
  -- The reply goes only through hv_messages; hv_send_reply_now tries to send it at once, the sender job is the fallback.
  -- Only private chats are served (a group message must not register the group as a farmer).
  -- C-03: :body_text is read ONCE into l_body. C-05: duplicate update_id ignored. C-16: the address is 'tg:<chat id>'.
  ORDS.DEFINE_TEMPLATE(p_module_name => 'harvestly', p_pattern => 'telegram');
  ORDS.DEFINE_HANDLER(
    p_module_name => 'harvestly', p_pattern => 'telegram', p_method => 'POST',
    p_source_type => ORDS.source_type_plsql, p_items_per_page => 0,
    p_source => q'~
DECLARE
  l_body  CLOB;
  l_upd   NUMBER;
  l_chat  NUMBER;
  l_ctype VARCHAR2(20);
  l_text  VARCHAR2(4000);
  l_reply VARCHAR2(1000);
  l_cmd   VARCHAR2(20);
  l_addr  VARCHAR2(64);
BEGIN
  IF NOT hv_check_secret('telegram_secret', :p_secret_hdr) THEN
    :status_code := 403;
    RETURN;
  END IF;
  l_body := :body_text;                              -- the ONLY dereference of :body_text (ORDS: read once)
  IF hv_body_ok(l_body) = 0 THEN                     -- R3: malformed body -> 400
    :status_code := 400;
    RETURN;
  END IF;
  SELECT JSON_VALUE(l_body, '$.update_id' RETURNING NUMBER),
         JSON_VALUE(l_body, '$.message.chat.id' RETURNING NUMBER),
         JSON_VALUE(l_body, '$.message.chat.type' RETURNING VARCHAR2(20)),
         JSON_VALUE(l_body, '$.message.text' RETURNING VARCHAR2(4000) TRUNCATE)
    INTO l_upd, l_chat, l_ctype, l_text FROM dual;
  :status_code := 200;
  IF l_chat IS NOT NULL AND l_text IS NOT NULL AND l_ctype = 'private'
     AND hv_seen_once('telegram', TO_CHAR(l_upd)) = 1 THEN
    l_addr := 'tg:' || TO_CHAR(l_chat);
    l_text := SUBSTR(l_text, 1, 1000);               -- R1-07
    IF TRIM(l_text) = '/start' THEN
      l_text := 'HELP';
    END IF;
    hv_handle_inbound('telegram', l_addr, l_text, l_reply, l_cmd);
    hv_send_reply_now('telegram', l_addr);
  END IF;
  owa_util.mime_header('application/json', FALSE, 'UTF-8');   -- empty JSON, never an inline reply
  owa_util.http_header_close;
  htp.prn('{}');
EXCEPTION WHEN OTHERS THEN
  ROLLBACK;
  :status_code := 500;                               -- Telegram retries; nothing secret is echoed
END;~');
  ORDS.DEFINE_PARAMETER(p_module_name => 'harvestly', p_pattern => 'telegram', p_method => 'POST',
    p_name => 'X-Telegram-Bot-Api-Secret-Token', p_bind_variable_name => 'p_secret_hdr',
    p_source_type => 'HEADER', p_param_type => 'STRING', p_access_method => 'IN');

  -- ---- Africa's Talking SMS callback (incoming messages) -----------------------------------
  -- AT posts form fields: from, to, text, date, id, linkId (see the note above). sms_secret is part of the URL you
  -- register in the AT dashboard (AT does not sign callbacks) and the source-IP allowlist is mandatory. Replies are queued;
  -- the handler tries to send the reply at once and the mandatory 5-minute sender is the fallback (R1-02).
  -- C-05: a repeated AT `id` is acknowledged (200) and ignored, so an AT retry or a replayed request does nothing twice.
  ORDS.DEFINE_TEMPLATE(p_module_name => 'harvestly', p_pattern => 'sms/:secret');
  ORDS.DEFINE_HANDLER(
    p_module_name => 'harvestly', p_pattern => 'sms/:secret', p_method => 'POST',
    p_source_type => ORDS.source_type_plsql, p_items_per_page => 0,
    p_source => q'~
DECLARE
  l_body  CLOB;
  l_from  VARCHAR2(200);
  l_text  VARCHAR2(4000);
  l_id    VARCHAR2(100);
  l_reply VARCHAR2(1000);
  l_cmd   VARCHAR2(20);
BEGIN
  IF NOT hv_check_secret('sms_secret', :secret) OR NOT hv_ip_allowed THEN
    :status_code := 403;
    RETURN;
  END IF;
  l_body := :body_text;                              -- the ONLY dereference of :body_text (ORDS: read once)
  IF hv_body_ok(l_body) = 0 THEN                     -- R3 R1-12: malformed body -> 400, so AT sees a failure, not a silent drop
    :status_code := 400;
    RETURN;
  END IF;
  l_from := SUBSTR(hv_body_value(l_body, 'from'), 1, 200);     -- cut to the variable's width: no ORA-06502
  l_text := SUBSTR(hv_body_value(l_body, 'text'), 1, 1000);   -- R1-07
  l_id   := SUBSTR(hv_body_value(l_body, 'id'), 1, 100);
  :status_code := 200;
  IF l_from IS NULL OR l_text IS NULL THEN
    RETURN;
  END IF;
  -- R3 C3-05: a sender must look like a phone number (to_addr is VARCHAR2(64)); anything else is acknowledged and dropped
  -- with a 200, so a forged 200-character `from` cannot cause an ORA-12899, a 500 and endless AT retries.
  IF NOT REGEXP_LIKE(l_from, '^\+?[0-9]{6,15}$') THEN
    RETURN;
  END IF;
  IF hv_seen_once('sms', l_id) = 0 THEN
    RETURN;                                          -- duplicate / replay
  END IF;
  hv_handle_inbound('sms', l_from, l_text, l_reply, l_cmd);
  hv_send_reply_now('sms', l_from);
EXCEPTION WHEN OTHERS THEN
  ROLLBACK;
  :status_code := 500;                               -- AT retries; nothing secret is echoed
END;~');

  -- ---- Africa's Talking USSD callback -------------------------------------------------------
  -- AT posts: sessionId, serviceCode, phoneNumber, networkCode, text. Reply is text/plain "CON ..." or "END ...".
  -- A session lasts 180 s on Safaricom; the cumulative `text` means no server-side session state is needed.
  -- sessionId makes registration idempotent against AT retries (R1-03, R1-18). USSD is NOT deduplicated by id: each step of
  -- a session is a legitimate new request with the same sessionId. The write paths are idempotent instead
  -- (hv_register_once) and rate limited (hv_can_register).
  ORDS.DEFINE_TEMPLATE(p_module_name => 'harvestly', p_pattern => 'ussd/:secret');
  ORDS.DEFINE_HANDLER(
    p_module_name => 'harvestly', p_pattern => 'ussd/:secret', p_method => 'POST',
    p_source_type => ORDS.source_type_plsql, p_items_per_page => 0,
    p_source => q'~
DECLARE
  l_body  CLOB;
  l_phone VARCHAR2(200);
  l_text  VARCHAR2(4000);
  l_sess  VARCHAR2(200);
  l_out   VARCHAR2(600);
BEGIN
  IF NOT hv_check_secret('ussd_secret', :secret) OR NOT hv_ip_allowed THEN
    :status_code := 403;
    RETURN;
  END IF;
  l_body  := :body_text;                             -- the ONLY dereference of :body_text (ORDS: read once)
  IF hv_body_ok(l_body) = 0 THEN                     -- R3 R1-12: malformed body -> 400
    :status_code := 400;
    RETURN;
  END IF;
  BEGIN                                              -- R3 C3-04: nothing below can leak an ORA- text or a 555
    l_phone := SUBSTR(hv_body_value(l_body, 'phoneNumber'), 1, 200);
    l_text  := SUBSTR(hv_body_value(l_body, 'text'), 1, 500);   -- R1-07
    l_sess  := SUBSTR(hv_body_value(l_body, 'sessionId'), 1, 200);
    IF l_phone IS NULL OR NOT REGEXP_LIKE(l_phone, '^\+?[0-9]{6,15}$') THEN   -- R3 C3-05
      l_out := 'END Phone number missing.';
    ELSE
      l_out := hv_ussd_menu(l_phone, l_text, l_sess);
    END IF;
  EXCEPTION WHEN OTHERS THEN
    ROLLBACK;
    l_out := 'END Service busy. Please try again later.';
  END;
  :status_code := 200;
  owa_util.mime_header('text/plain', FALSE, 'UTF-8');
  owa_util.http_header_close;
  htp.prn(l_out);
EXCEPTION WHEN OTHERS THEN
  ROLLBACK;
  :status_code := 200;                               -- R3 C3-04: even a fault in the output step answers a screen
  BEGIN
    owa_util.mime_header('text/plain', FALSE, 'UTF-8');
    owa_util.http_header_close;
    htp.prn('END Service busy. Please try again later.');
  EXCEPTION WHEN OTHERS THEN
    NULL;
  END;
END;~');
  -- R3 C3-12: the callbacks are server-to-server, so no browser origin needs access. An origin list that can never match
  -- keeps CORS closed on the module explicitly instead of relying on the ORDS default.
  ORDS.SET_MODULE_ORIGINS_ALLOWED(p_module_name => 'harvestly', p_origins_allowed => 'https://no-browser-origin.invalid');
  COMMIT;
END;
/

-- =====================================================================================
-- 7. APEX Automations (create in App Builder; the APEX session they provide is what APEX_WEB_SERVICE needs)
--    App Builder > Automations > Create. FOUR automations, all Type "Scheduled", error handling "Log and continue".
--    Times are EAT (UTC+3, no DST). If the form is in UTC use the UTC column (BYHOUR / BYMINUTE).
--
--    1. Harvestly weather refresh      16:45 EAT daily  (UTC FREQ=DAILY;BYHOUR=13;BYMINUTE=45;BYSECOND=0)
--         BEGIN hv_refresh_all_weather; END;
--       Fresh before the 17:00 run (R1-09, R1-17). hv_daily_job refreshes again only if this one failed (6 h cache).
--
--    2. Harvestly 17:00 evening run    17:00 EAT daily  (UTC FREQ=DAILY;BYHOUR=14;BYMINUTE=0;BYSECOND=0)
--         BEGIN hv_daily_job; END;
--       Does NOT call the sender (R1-05). It is idempotent per batch per day, so a re-run is harmless.
--
--    3. Harvestly sender               MANDATORY (R1-02), every 5 minutes, offset to :02,:07,:12,...,:57
--         FREQ=MINUTELY;INTERVAL=5;BYMINUTE=2,7,12,17,22,27,32,37,42,47,52,57;BYSECOND=0   (same minutes in UTC)
--         BEGIN hv_send_queued; END;
--       Nothing else fires at exactly :00 or :05, so the sender never collides with the 17:00 job. It delivers the
--       17:00 messages at about 17:02 and is the fallback for replies that hv_send_reply_now could not send.
--       Without this automation no proactive message is ever delivered. A message left in SENDING for 15 minutes
--       (a session died between claim and send) is put back to QUEUED by claim_queued itself (R2 C-18).
--
--    4. Harvestly retention purge      02:30 EAT daily  (UTC FREQ=DAILY;BYHOUR=23;BYMINUTE=30;BYSECOND=0)
--         BEGIN harvestly_engine.purge_retention; END;
--       Blanks raw inbound text after 30 days and sent addresses after 30 days, deletes old messages and run logs,
--       and removes the phone number of long-ended batches (R1-11). Erase on request:
--         DECLARE n NUMBER; BEGIN harvestly_engine.erase_by_phone('sms', '+2547XXXXXXXX', n); DBMS_OUTPUT.PUT_LINE(n); END;
--
--    DBMS_SCHEDULER equivalents are possible only if the job first creates an APEX session
--    (APEX_SESSION.CREATE_SESSION); Automations avoid that.
--    Limits (concept note, section 5): 1,000 outbound web-service calls per workspace per day by default;
--    the jobs make one Open-Meteo call per ward with active batches plus one AT/Telegram call per message.
-- =====================================================================================
