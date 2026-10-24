// The 15 parameters of the engine, each labelled SOURCE, SOURCE-BASED, CALIBRATION, PROGRAMME or UNVALIDATED as in engine/harvestly_engine.py.
export const PARAMS = [
  { name: 'Moisture table', value: '14 × 14 values: 35–100 °F, 25–90% humidity', tag: 'SOURCE', from: 'University of Arkansas Extension FSA1074, Table A [6]. Checked cell by cell against the publication.', code: 'EMC_TABLE' },
  { name: 'Storage time table', value: '9 × 7 values: 35–75 °F, 15–30% moisture', tag: 'SOURCE', from: 'University of Arkansas Extension FSA1058, Table 1 [7]. Checked cell by cell. Time to about 0.5% dry-matter loss, a US grade level. The source counts from harvest; the engine counts from the first test.', code: 'AST_TABLE' },
  { name: 'Limit for storage, sale and warehouse intake', value: '13.5% moisture', tag: 'SOURCE', from: 'East African Standard EAS 2, draft revision DEAS 2:2024 [3]. This is the limit for sale; Arkansas guidance for keeping corn a full year is 12%.', code: 'EAS_MAX_MC' },
  { name: 'Limit for hermetic bags', value: '14% moisture', tag: 'SOURCE', from: 'Ng’ang’a et al. 2016a [4], cited and not re-opened in our checks: sealed bags stop aflatoxin building up only below 14%.', code: 'HERMETIC_MAX_MC' },
  { name: 'Salt test line', value: '15% moisture', tag: 'UNVALIDATED', from: 'Secondary, unverified: a rule of thumb attributed to Johnson 1992 [18]. We have not opened that paper, so the 15% line is not checked against it. The salt-test protocol is being verified, so our first message gives no amounts or times. Only a meter, hygrometer or depot reading clears grain. The protocol asks for non-iodised salt.', code: 'SALT_LINE_MC' },
  { name: 'Week-7 weevil reminder', value: '49 days in sacks', tag: 'SOURCE-BASED', from: 'Based on Ng’ang’a et al. 2016b [22], one trial in Makueni. The week-7 timing is our reading and is not stated in the abstract. The count starts at the first test, not at harvest.', code: 'INSECT_REMINDER_DAYS' },
  { name: 'Moisture used when salt sticks', value: '18%', tag: 'CALIBRATION', from: 'Our assumption. The true value is only known to be above 15%. A pilot would replace it with meter readings.', code: 'SALT_STICKY_MC' },
  { name: 'Moisture used when salt flows', value: '14.5%', tag: 'CALIBRATION', from: 'Our assumption: at most about 15%. Never treated as proof of 13.5%.', code: 'SALT_FLOWS_MC' },
  { name: 'Drift in sacks, cribs and floors', value: '5% of the gap to the air’s equilibrium moisture, each day', tag: 'CALIBRATION', from: 'Our assumption, not fitted to data. Afzal et al. [21] report grain wetting from 12.5% to 15.6% over 2 months in polypropylene bags in Pakistan (final reading only), the same order of magnitude.', code: 'SACK_EXCHANGE_RATE' },
  { name: 'Grain temperature', value: 'The day’s mean air temperature', tag: 'CALIBRATION', from: 'A stand-in. Grain temperature is not air temperature.', code: 'temp_c' },
  { name: 'Risk levels', value: 'HIGH: 80% of storage life used, or 14 days or fewer. MEDIUM: 50%, or 30 days or fewer. Warn again when the countdown has halved and is 60 days or fewer.', tag: 'PROGRAMME', from: 'Our thresholds, set for the lead time sun-drying needs in a wet season.', code: 'HIGH_LIFE, HIGH_DAYS, MEDIUM_LIFE, MEDIUM_DAYS, WORSE_FACTOR' },
  { name: 'Rain alert', value: '60% chance, or 5 mm, in the next 24 hours, while grain is drying', tag: 'PROGRAMME', from: 'Our rule.', code: 'RAIN_PROB_ALERT, RAIN_MM_ALERT' },
  { name: 'Spacing and cap of repeats', value: 'One rule for an unanswered HIGH batch: after the ordinary advice message (repeated at most twice, 3 days apart, sealed bags 7), an urgent reminder goes out weekly, at most four times per test result. The fourth says it is the last reminder, then nothing more is sent until a new test result', tag: 'PROGRAMME', from: 'Our rule, against alert fatigue.', code: 'REMIND_GAP_DAYS, SEALED_GAP_DAYS, REPEAT_MAX, HIGH_ALERT_GAP_DAYS, HIGH_ALERT_MAX' },
  { name: 'Re-test trigger', value: 'The estimate is 1 point past the salt line (16% going up, 14% going down). At most 2 re-test requests in 30 days', tag: 'PROGRAMME', from: 'Our rule. The engine never orders drying on an estimate alone.', code: 'RETEST_MARGIN, RETEST_PER_30_DAYS' },
  { name: 'Other caps', value: 'An untested farmer is asked to test at most 3 times. Rain alerts pause after 3 unanswered. One proactive message a day', tag: 'PROGRAMME', from: 'Our rule.', code: 'TEST_REMINDERS_MAX, RAIN_UNACKED_MAX' },
];

/** Settings the engine also uses that are not among the 15 rows above. Shown as a list so nothing is hidden. */
export const ALSO_IN_CODE = [
  ['HORIZON_DAYS = 365', 'A countdown is capped at 365 days. The site shows 365+.'],
  ['MAX_AST_DAYS = 3650', 'Storage time is capped at 3,650 days.'],
  ['Forecast beyond day 7', 'After the 7-day forecast the engine repeats the forecast’s average.'],
  ['Humidity clamp', 'Humidity above 90% is treated as 90%, and below 25% as 25%, because the moisture table ends there.'],
  ['Same drift for all permeable storage', 'Sacks, cribs and floors drift at the same rate.'],
  ['PLACE_MAX_CHARS', 'A place or stockist name is cut to a fixed length so a message stays within two SMS.'],
];
