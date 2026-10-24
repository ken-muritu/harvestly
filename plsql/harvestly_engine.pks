CREATE OR REPLACE PACKAGE harvestly_engine AUTHID DEFINER AS
  /*
    Harvestly risk engine v3 - PL/SQL port of engine/harvestly_engine.py (Oracle 19c / 23ai).

    Tracks one farmer's batch of shelled maize and answers, every evening:
      1. Is this grain dry enough for its storage method?
      2. If not, roughly how many days before mould starts to cost grade, and what is the ONE thing to do?

    Every parameter below is tagged exactly as in the Python reference:
      SOURCE        - taken from a published table/standard (reference in the concept note)
      CALIBRATION   - a stated pilot value, to be replaced by meter data from the pilot
      PROGRAMME     - a design rule we chose (alert thresholds, reminder spacing)

    Entry points that mirror the Python module one to one (same names, same order of rules):
      emc, ast_days, advance_day, days_left, risk_level, advice, evaluate, normalise,
      apply_reply, respond, render, daily_run.
    Database wrappers (not part of the golden vectors): load_batch, save_batch, process_reply,
      queue_message, claim_queued, mark_sent, mark_failed, daily_run_batch, daily_run_all,
      purge_retention, erase_by_phone, record_weather_fetch.

    NULL in a field means "None" in the Python (untested moisture, no last alert, no forecast...).
    All dates are TRUNC'd calendar days (no time part).
  */

  -- ====================================================================================
  -- Thresholds and parameters
  -- ====================================================================================
  c_eas_max_mc           CONSTANT NUMBER := 13.5;   -- SOURCE: EAS 2 maize grain standard (DEAS 2:2024) - storage/sale/NCPB/WRS gate
  c_hermetic_max_mc      CONSTANT NUMBER := 14.0;   -- SOURCE: Ng'ang'a et al. 2016 (J. Stored Prod. Res. 69) - hermetic bags stop
                                                    --         aflatoxin build-up only if grain is below 14 %
  c_salt_line_mc         CONSTANT NUMBER := 15.0;   -- SECONDARY, UNVERIFIED: rule of thumb attributed to Johnson 1992 (CSIR-FRI Ghana); the paper was never opened
  c_salt_sticky_mc       CONSTANT NUMBER := 18.0;   -- CALIBRATION: point value for the countdown when salt sticks (true value >15 %)
  c_salt_flows_mc        CONSTANT NUMBER := 14.5;   -- CALIBRATION: salt flows = at most ~15 %; never proof of <=13.5 %
  c_sack_exchange_rate   CONSTANT NUMBER := 0.05;   -- CALIBRATION: share of the gap to EMC closed per day in woven sacks
                                                    --   (same order of magnitude as Afzal et al. 2017, NOT a validation)
  c_max_ast_days         CONSTANT NUMBER := 3650;   -- cap for very dry grain (table edge is 15 %; below that we extrapolate and flag)

  c_rain_prob_alert      CONSTANT NUMBER := 60;     -- PROGRAMME: % chance of rain in the next 24 h that triggers "cover it"
  c_rain_mm_alert        CONSTANT NUMBER := 5;      -- PROGRAMME: mm of rain in the next 24 h that triggers "cover it"
  c_high_life            CONSTANT NUMBER := 0.8;    -- PROGRAMME: HIGH if >=80 % of safe life used ...
  c_high_days            CONSTANT NUMBER := 14;     --            ... or <=14 days left
  c_medium_life          CONSTANT NUMBER := 0.5;    -- PROGRAMME: MEDIUM if >=50 % used ...
  c_medium_days          CONSTANT NUMBER := 30;     --            ... or <=30 days left (sun-drying needs several dry days)
  c_remind_gap_days      CONSTANT NUMBER := 3;      -- PROGRAMME: an unanswered HIGH warning repeats at most every 3 days
  c_sealed_gap_days      CONSTANT NUMBER := 7;      -- PROGRAMME: an unanswered sealed-bag warning repeats at most every 7 days
  c_repeat_max           CONSTANT NUMBER := 2;      -- PROGRAMME: at most 2 repeats of the same warning per test result
  c_worse_factor         CONSTANT NUMBER := 0.5;    -- PROGRAMME: also warn again when the countdown has at least halved
  c_worse_within         CONSTANT NUMBER := 60;     --            since the farmer was last told, and is now 60 days or less
  c_retest_margin        CONSTANT NUMBER := 1.0;    -- PROGRAMME: estimate must pass the salt line by 1 point (16 % up, 14 % down)
  c_retest_per_30_days   CONSTANT NUMBER := 2;      -- PROGRAMME: at most 2 re-test requests in any 30 days (no test-loops)
  c_test_reminders_max   CONSTANT NUMBER := 3;      -- PROGRAMME: an untested farmer is asked to test at most 3 times
  c_rain_unacked_max     CONSTANT NUMBER := 3;      -- PROGRAMME: rain alerts pause after 3 in a row with no reply
  c_place_max_chars      CONSTANT NUMBER := 32;     -- PROGRAMME: directory names are cut to this length
  c_insect_reminder_days CONSTANT NUMBER := 49;     -- SOURCE-BASED (week 7 unverified): Ng'ang'a et al. 2016 (Food Security 8)
  c_horizon_days         CONSTANT PLS_INTEGER := 365;  -- longest countdown computed: 365 means "365 or more"
  c_high_alert_gap_days  CONSTANT NUMBER := 7;      -- PROGRAMME: a HIGH batch whose normal messages are capped still hears weekly ...
  c_optout_max_tokens    CONSTANT NUMBER := 6;      -- PROGRAMME: an opt-out word counts anywhere in a message of at most 6 words
  c_high_alert_max       CONSTANT NUMBER := 4;      -- PROGRAMME: ... at most 4 times per test result (the 4th says it is the last)
  c_weather_stale_hours  CONSTANT NUMBER := 24;     -- PROGRAMME: weather older than this is flagged stale, never used for rain alerts
  c_weeks_cap            CONSTANT NUMBER := 99;     -- PROGRAMME: {weeks} never exceeds 2 digits
  c_norm_store_chars     CONSTANT PLS_INTEGER := 250;  -- PROGRAMME: only this much of a normalised reply is stored / compared for duplicates
  c_max_text_chars       CONSTANT PLS_INTEGER := 1000; -- PROGRAMME: inbound text is cut to this before parsing; never raises
  c_credit_open_meteo    CONSTANT VARCHAR2(40) := 'Open-Meteo.com';   -- short credit inside alerts (full text: WELCOME + README)
  -- Retention in days (same numbers as the Python reference RETAIN_*); see purge_retention and README "Privacy"
  c_retain_inbound_text  CONSTANT PLS_INTEGER := 30;   -- raw inbound text blanked
  c_retain_sent_address  CONSTANT PLS_INTEGER := 30;   -- recipient address blanked from a sent/failed message
  c_retain_message       CONSTANT PLS_INTEGER := 180;  -- message rows deleted
  c_retain_runlog        CONSTANT PLS_INTEGER := 90;   -- run-log rows deleted
  c_retain_ended_batch   CONSTANT PLS_INTEGER := 90;   -- closed/stopped batch loses its phone number
  c_sms_gsm7_single      CONSTANT PLS_INTEGER := 160;  -- SOURCE: GSM 03.38 single segment (153 per concatenated segment)
  c_sms_max_segments     CONSTANT PLS_INTEGER := 2;    -- PROGRAMME: every message must fit in 2 SMS

  -- Generic fallbacks when the pilot directory has no entry, so no placeholder reaches a farmer.
  c_place_stockist_en    CONSTANT VARCHAR2(60) := 'an agro-dealer near you';
  c_place_warehouse_en   CONSTANT VARCHAR2(60) := 'a certified warehouse';
  c_place_checkpoint_en  CONSTANT VARCHAR2(60) := 'your co-op or NCPB depot';
  c_place_stockist_sw    CONSTANT VARCHAR2(60) := 'duka la pembejeo karibu nawe';
  c_place_warehouse_sw   CONSTANT VARCHAR2(60) := 'ghala lililoidhinishwa';
  c_place_checkpoint_sw  CONSTANT VARCHAR2(60) := 'chama chako au bohari ya NCPB';

  -- Errors (RAISE_APPLICATION_ERROR codes; the Python raises ValueError)
  e_bad_input  EXCEPTION;  PRAGMA EXCEPTION_INIT(e_bad_input, -20001);
  e_no_weather EXCEPTION;  PRAGMA EXCEPTION_INIT(e_no_weather, -20002);
  e_no_batch   EXCEPTION;  PRAGMA EXCEPTION_INIT(e_no_batch, -20003);

  -- ====================================================================================
  -- Types
  -- ====================================================================================
  TYPE t_weather_day IS RECORD (
    wx_date    DATE,
    temp_c     NUMBER,          -- daily mean air temperature (used as grain temperature: CALIBRATION)
    rh         NUMBER,          -- daily mean relative humidity, %
    rain_mm    NUMBER,          -- daily total; NULL = not available
    rain_prob  NUMBER);         -- daily max probability of precipitation, %; NULL = not available
  TYPE t_weather_tab IS TABLE OF t_weather_day INDEX BY PLS_INTEGER;   -- 1..COUNT, ascending dates

  TYPE t_sent IS RECORD (sent_date DATE, code VARCHAR2(30));
  TYPE t_sent_tab IS TABLE OF t_sent INDEX BY PLS_INTEGER;
  TYPE t_reply IS RECORD (rcv_date DATE, norm VARCHAR2(4000));
  TYPE t_reply_tab IS TABLE OF t_reply INDEX BY PLS_INTEGER;

  TYPE t_batch IS RECORD (
    batch_id        NUMBER,
    ward_id         NUMBER,
    storage         VARCHAR2(10),   -- drying | sack | crib | floor | hermetic
    stored_since    DATE,           -- date the grain entered its current storage
    lang            VARCHAR2(2)     := 'en',
    bags            NUMBER          := 1,
    moisture        NUMBER,         -- current ESTIMATE (% w.b.); NULL = untested
    source          VARCHAR2(12)    := 'none',   -- none | salt_sticky | salt_flows | hygro | meter
    last_test       DATE,
    test_value      NUMBER,         -- value set by the last test, before any drift
    peak_since_test NUMBER,         -- highest estimate since the last test
    life_used       NUMBER          := 0,        -- share of allowable storage time used (never decreases)
    last_advanced   DATE,
    last_alert      DATE,           -- last PROACTIVE message (replies do not count)
    last_advice     VARCHAR2(20),   -- last recommendation the farmer was given (alert or reply)
    told_level      VARCHAR2(8)     := 'UNKNOWN',
    told_left       NUMBER,
    rain_unacked    NUMBER          := 0,        -- rain alerts sent since the farmer last replied
    status          VARCHAR2(8)     := 'active', -- active | closed (sold/deposited) | stopped (opted out)
    last_run        DATE,           -- day the evening job last completed for this batch (idempotency)
    sent            t_sent_tab,     -- every outgoing message (date, code)
    replies         t_reply_tab);   -- every incoming reply (date, normalised text)

  -- What a message changes on the batch; kept so an undelivered (SKIPPED / finally FAILED) message can be undone.
  TYPE t_undo IS RECORD (
    present        BOOLEAN := FALSE,
    sent_len       PLS_INTEGER,
    last_alert     DATE,
    last_advice    VARCHAR2(20),
    told_level     VARCHAR2(8),
    told_left      NUMBER,
    rain_unacked   NUMBER);

  TYPE t_alert IS RECORD (
    code   VARCHAR2(30),            -- NULL = no message
    risk   VARCHAR2(8),
    msg    VARCHAR2(2000),          -- in the farmer's language
    other  VARCHAR2(2000),          -- the same message in the other language (dashboard / audit)
    undo   t_undo);

  -- Where the weather came from: fetch date, age, and the credit shown in alerts (demos: 'Simulated weather').
  TYPE t_weather_meta IS RECORD (
    given      BOOLEAN := FALSE,
    fetched_on DATE,
    age_hours  NUMBER := 0,
    credit     VARCHAR2(40) := 'Open-Meteo.com');

  FUNCTION no_meta RETURN t_weather_meta;       -- 'weather meta not given' (default of every p_meta parameter)

  TYPE t_places IS RECORD (stockist VARCHAR2(200), warehouse VARCHAR2(200), checkpoint VARCHAR2(200));

  TYPE t_rain24 IS RECORD (given BOOLEAN := FALSE, mm NUMBER, prob NUMBER);

  TYPE t_diag IS RECORD (
    moisture       NUMBER,          -- rounded to 1 decimal (half up, fmt1)
    moisture_raw   NUMBER,          -- unrounded
    life_used_raw  NUMBER,          -- unrounded
    days_left_capped BOOLEAN,       -- days_left = c_horizon_days: "that many or more", not a prediction
    weather_stale  BOOLEAN,
    source         VARCHAR2(12),
    verdict        VARCHAR2(12),
    life_used_pct  NUMBER,          -- rounded to 1 decimal
    days_left      PLS_INTEGER,
    risk           VARCHAR2(8),
    advice         VARCHAR2(20),
    emc_tomorrow   NUMBER,
    flags          VARCHAR2(500),   -- '; ' separated, same order as the Python (sorted, then "rain data missing")
    missing_days   PLS_INTEGER);

  -- ====================================================================================
  -- Physics
  -- ====================================================================================
  FUNCTION emc(p_temp_c IN NUMBER, p_rh IN NUMBER, p_warn OUT VARCHAR2) RETURN NUMBER;
  FUNCTION emc(p_temp_c IN NUMBER, p_rh IN NUMBER) RETURN NUMBER;
  FUNCTION ast_days(p_temp_c IN NUMBER, p_mc IN NUMBER, p_warn OUT VARCHAR2) RETURN NUMBER;
  FUNCTION ast_days(p_temp_c IN NUMBER, p_mc IN NUMBER) RETURN NUMBER;

  -- ====================================================================================
  -- State
  -- ====================================================================================
  FUNCTION new_batch(p_batch_id IN NUMBER, p_ward_id IN NUMBER, p_storage IN VARCHAR2,
                     p_stored_since IN DATE, p_lang IN VARCHAR2 DEFAULT 'en') RETURN t_batch;
  FUNCTION stale(b IN t_batch) RETURN BOOLEAN;
  FUNCTION verdict(b IN t_batch) RETURN VARCHAR2;   -- UNTESTED | WET | NOT_PROVEN | DRY
  FUNCTION count_sent(b IN t_batch, p_code IN VARCHAR2, p_since IN DATE DEFAULT NULL) RETURN PLS_INTEGER;

  -- ====================================================================================
  -- Daily simulation, countdown, risk, advice
  -- ====================================================================================
  PROCEDURE advance_day(b IN OUT NOCOPY t_batch, w IN t_weather_day);
  FUNCTION days_left(b IN t_batch, p_forecast IN t_weather_tab) RETURN PLS_INTEGER;
  FUNCTION risk_level(p_life_used IN NUMBER, p_left IN PLS_INTEGER) RETURN VARCHAR2;
  FUNCTION advice(b IN t_batch) RETURN VARCHAR2;     -- NULL = nothing to do

  -- ====================================================================================
  -- Messages
  -- ====================================================================================
  -- The ONE rounding rule (all ports): ROUND(ROUND(x, 10), places), half up on the decimal value.
  FUNCTION fmt0(p_x IN NUMBER) RETURN VARCHAR2;
  FUNCTION fmt1(p_x IN NUMBER) RETURN VARCHAR2;
  FUNCTION fmt2(p_x IN NUMBER) RETURN VARCHAR2;
  FUNCTION sanitise_place(p_name IN VARCHAR2) RETURN VARCHAR2;
  FUNCTION evidence_text(b IN t_batch, p_en IN BOOLEAN) RETURN VARCHAR2;
  FUNCTION measured_text(b IN t_batch, p_en IN BOOLEAN) RETURN VARCHAR2;      -- 'meter 13.1% on 12/10' (used by the USSD status)
  FUNCTION risk_text(p_left IN PLS_INTEGER, p_en IN BOOLEAN, p_tracks_air IN BOOLEAN DEFAULT TRUE) RETURN VARCHAR2;  -- 'about 40 days (estimate)'; never 'safe'
  FUNCTION render(p_code IN VARCHAR2, b IN t_batch, p_risk IN VARCHAR2, p_left IN PLS_INTEGER,
                  p_today IN DATE, p_places IN t_places, p_rain_mm IN NUMBER DEFAULT NULL,
                  p_rain_prob IN NUMBER DEFAULT NULL, p_rain_window IN BOOLEAN DEFAULT TRUE,
                  p_meta IN t_weather_meta DEFAULT no_meta) RETURN t_alert;
  FUNCTION welcome(b IN t_batch, p_today IN DATE) RETURN t_alert;
  -- Take back an undelivered message (SKIPPED / finally FAILED): it burns no cap, the farmer is told next time.
  PROCEDURE revert_undelivered(b IN OUT NOCOPY t_batch, p_undo IN t_undo);
  FUNCTION sms_segments(p_text IN VARCHAR2) RETURN PLS_INTEGER;   -- 0 = not GSM-7 (would go UCS-2)

  -- ====================================================================================
  -- Evening decision, replies
  -- ====================================================================================
  PROCEDURE evaluate(b IN OUT NOCOPY t_batch, p_today IN DATE, p_forecast IN t_weather_tab,
                     p_places IN t_places, p_rain24 IN t_rain24, p_alert OUT t_alert, p_diag OUT t_diag,
                     p_meta IN t_weather_meta DEFAULT no_meta, p_send IN BOOLEAN DEFAULT TRUE);
  FUNCTION normalise(p_text IN VARCHAR2) RETURN VARCHAR2;
  FUNCTION is_optout(p_norm IN VARCHAR2) RETURN BOOLEAN;
  FUNCTION normalise_address(p_addr IN VARCHAR2) RETURN VARCHAR2;
  FUNCTION address_hash(p_addr IN VARCHAR2, p_pepper IN VARCHAR2) RETURN VARCHAR2;
  FUNCTION address_hash(p_addr IN VARCHAR2) RETURN VARCHAR2;      -- pepper from hv_config 'hash_pepper'
  FUNCTION apply_reply(b IN OUT NOCOPY t_batch, p_text IN VARCHAR2, p_today IN DATE,
                       p_temp_hint IN NUMBER DEFAULT NULL) RETURN VARCHAR2;
  PROCEDURE respond(b IN OUT NOCOPY t_batch, p_text IN VARCHAR2, p_today IN DATE,
                    p_forecast IN t_weather_tab, p_places IN t_places, p_temp_hint IN NUMBER,
                    p_cmd OUT VARCHAR2, p_alert OUT t_alert, p_meta IN t_weather_meta DEFAULT no_meta);
  PROCEDURE daily_run(b IN OUT NOCOPY t_batch, p_today IN DATE, p_days IN t_weather_tab,
                      p_places IN t_places, p_rain24 IN t_rain24, p_alert OUT t_alert, p_diag OUT t_diag,
                      p_meta IN t_weather_meta DEFAULT no_meta);

  -- ====================================================================================
  -- Database wrappers
  -- ====================================================================================
  PROCEDURE load_batch(p_batch_id IN NUMBER, b OUT NOCOPY t_batch);
  PROCEDURE save_batch(b IN t_batch);
  -- Calendar day in Africa/Nairobi (EAT, UTC+3); ADB's SYSDATE is UTC. p_today = NULL means this.
  FUNCTION today_eat RETURN DATE;
  FUNCTION load_places(p_ward_id IN NUMBER) RETURN t_places;
  PROCEDURE load_weather(p_ward_id IN NUMBER, p_today IN DATE, p_days OUT NOCOPY t_weather_tab);
  FUNCTION load_rain24(p_ward_id IN NUMBER, p_today IN DATE) RETURN t_rain24;

  -- Handle one inbound farmer message. p_batch_id is NULL when the sender is unknown.
  -- p_reply receives the text to send back (also queued in hv_messages).
  PROCEDURE process_reply(p_channel IN VARCHAR2, p_from IN VARCHAR2, p_text IN VARCHAR2,
                          p_today IN DATE, p_batch_id OUT NUMBER, p_cmd OUT VARCHAR2,
                          p_reply OUT VARCHAR2);

  -- Queue / send protocol. A row is QUEUED -> SENDING (claim_queued, committed before any HTTP call) ->
  -- SENT (mark_sent) or back to QUEUED for a retry (mark_failed, up to 3 attempts) or FAILED (final: the batch
  -- state the message changed is rolled back). SKIPPED (too long / not GSM-7) is rolled back at once.
  -- CANCELLED = the phone opted out. Only QUEUED, SENDING and SENT rows count as "sent" for caps.
  PROCEDURE queue_message(b IN OUT NOCOPY t_batch, p_alert IN t_alert, p_kind IN VARCHAR2, p_today IN DATE,
                          p_ignore_optout IN BOOLEAN DEFAULT FALSE);   -- TRUE only for the STOPPED confirmation
  -- R3 C3-02: the reply budget. 'QUEUED' | 'SKIPPED' | 'CANCELLED'. Per phone per hour (max_reply_per_hour, 6) and per day
  -- (max_reply_per_day, 20), system-wide per day (max_reply_global_per_day, 3000), and the how-to cap for strangers
  -- (max_howto_per_day, 300). The STOPPED confirmation is exempt. queue_message applies it to every REPLY row, so known
  -- senders and the welcome are budgeted too; hv_reply_status in ords_handlers.sql only delegates here.
  FUNCTION reply_status(p_hash IN VARCHAR2, p_code IN VARCHAR2) RETURN VARCHAR2;
  PROCEDURE queue_welcome(p_batch_id IN NUMBER, p_today IN DATE DEFAULT NULL);
  PROCEDURE claim_queued(p_limit IN NUMBER, p_ids OUT SYS.ODCINUMBERLIST);
  PROCEDURE mark_sent(p_msg_id IN NUMBER, p_provider_ref IN VARCHAR2);
  PROCEDURE mark_failed(p_msg_id IN NUMBER, p_error IN VARCHAR2);

  -- Weather freshness. record_weather_fetch is an autonomous transaction, so a failure is recorded even when
  -- the caller rolls back. load_weather_meta says how old the cached forecast is (stale after 24 h).
  PROCEDURE record_weather_fetch(p_ward_id IN NUMBER, p_ok IN BOOLEAN, p_error IN VARCHAR2);
  FUNCTION load_weather_meta(p_ward_id IN NUMBER) RETURN t_weather_meta;

  -- Privacy. purge_retention: run daily. erase_by_phone: erase one person on request (see README "Privacy").
  PROCEDURE purge_retention(p_today IN DATE DEFAULT NULL);
  PROCEDURE erase_by_phone(p_channel IN VARCHAR2, p_addr IN VARCHAR2, p_deleted OUT NUMBER);

  -- Tables and templates are cached per session; call this (or start a new session) after editing them.
  PROCEDURE reset_cache;

  -- One batch / every active batch of a ward / every active batch. Weather must already be cached
  -- in hv_weather (see ords_handlers.sql: hv_refresh_ward_weather).
  PROCEDURE daily_run_batch(p_batch_id IN NUMBER, p_today IN DATE DEFAULT NULL);
  PROCEDURE daily_run_ward(p_ward_id IN NUMBER, p_today IN DATE DEFAULT NULL);
  PROCEDURE daily_run_all(p_today IN DATE DEFAULT NULL);
END harvestly_engine;
/
