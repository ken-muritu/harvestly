// Port of the Harvestly risk engine's physics (engine/harvestly_engine.py): equilibrium moisture,
// allowable storage time, the daily drift and the countdown. The tables are copied from the engine and
// tools/test-engine-js.mjs proves this file reproduces engine/vectors.json (EMC and AST to 1e-6).
// Plain ES module, no dependencies, runs in the browser and in Node.
export const EMC_TEMPS_F = [35,40,45,50,55,60,65,70,75,80,85,90,95,100];
export const EMC_RH = [25,30,35,40,45,50,55,60,65,70,75,80,85,90];
export const EMC_TABLE = [
  [9.3,10.3,11.2,12.1,13.0,13.9,14.8,15.7,16.6,17.6,18.7,19.8,21.2,22.9],
  [9.1,10.0,10.9,11.8,12.7,13.5,14.4,15.3,16.2,17.1,18.2,19.3,20.7,22.3],
  [8.8,9.8,10.6,11.5,12.3,13.2,14.0,14.9,15.8,16.7,17.7,18.9,20.2,21.8],
  [8.6,9.5,10.4,11.2,12.0,12.9,13.7,14.5,15.4,16.3,17.3,18.5,19.8,21.4],
  [8.4,9.3,10.1,11.0,11.8,12.6,13.4,14.2,15.1,16.0,17.0,18.1,19.3,20.9],
  [8.2,9.1,9.9,10.7,11.5,12.3,13.1,13.9,14.8,15.7,16.6,17.7,18.9,20.5],
  [8.0,8.9,9.7,10.5,11.3,12.0,12.8,13.6,14.5,15.3,16.3,17.4,18.6,20.1],
  [7.9,8.7,9.5,10.3,11.0,11.8,12.6,13.4,14.2,15.0,16.0,17.0,18.2,19.8],
  [7.7,8.5,9.3,10.1,10.8,11.6,12.3,13.1,13.9,14.8,15.7,16.7,17.9,19.4],
  [7.6,8.4,9.1,9.9,10.6,11.4,12.1,12.9,13.7,14.5,15.4,16.4,17.6,19.1],
  [7.4,8.2,9.0,9.7,10.4,11.2,11.9,12.6,13.4,14.3,15.2,16.2,17.3,18.8],
  [7.3,8.1,8.8,9.5,10.3,11.0,11.7,12.4,13.2,14.0,14.9,15.9,17.0,18.5],
  [7.2,7.9,8.7,9.4,10.1,10.8,11.5,12.2,13.0,13.8,14.7,15.6,16.8,18.2],
  [7.1,7.8,8.5,9.2,9.9,10.6,11.3,12.0,12.8,13.6,14.5,15.4,16.5,17.9]
];
export const AST_TEMPS_F = [35,40,45,50,55,60,65,70,75];
export const AST_MC = [15,17,19,21,23,25,30];
export const AST_TABLE = [
  [2126,671,295,161,102,72,41],
  [1413,448,197,107,68,48,27],
  [931,299,131,72,45,32,18],
  [621,199,88,48,30,21,12],
  [414,133,58,32,21,14,8],
  [275,88,39,22,14,10,6],
  [206,66,29,16,11,8,5],
  [154,49,22,12,8,6,4],
  [115,37,16,9,6,5,3]
];
export const P = {
  EAS_MAX_MC: 13.5, HERMETIC_MAX_MC: 14.0, SALT_LINE_MC: 15.0, SALT_STICKY_MC: 18.0, SALT_FLOWS_MC: 14.5,
  SACK_EXCHANGE_RATE: 0.05, MAX_AST_DAYS: 3650, HIGH_LIFE: 0.8, HIGH_DAYS: 14, MEDIUM_LIFE: 0.5, MEDIUM_DAYS: 30,
  HORIZON_DAYS: 365,
};
export const PERMEABLE = new Set(['sack', 'crib', 'floor']);

const cToF = (c) => (c * 9) / 5 + 32;

// Index i and fraction t so that x = axis[i] + t*(axis[i+1]-axis[i]); t < 0 or > 1 only at the edges.
function bracket(axis, x) {
  let i;
  if (x <= axis[0]) i = 0;
  else if (x >= axis[axis.length - 1]) i = axis.length - 2;
  else { i = 0; for (let j = 0; j < axis.length - 1; j++) if (axis[j] <= x) i = j; }
  return [i, (x - axis[i]) / (axis[i + 1] - axis[i])];
}

/** Equilibrium moisture (% wet basis) of maize in air at tempC and rh. Returns {value, warnings}. */
export function emc(tempC, rh) {
  const warnings = [];
  let tf = cToF(tempC);
  if (!(EMC_TEMPS_F[0] <= tf && tf <= EMC_TEMPS_F[EMC_TEMPS_F.length - 1])) {
    warnings.push('EMC temperature clamped');
    tf = Math.min(Math.max(tf, EMC_TEMPS_F[0]), EMC_TEMPS_F[EMC_TEMPS_F.length - 1]);
  }
  if (!(EMC_RH[0] <= rh && rh <= EMC_RH[EMC_RH.length - 1])) {
    warnings.push('EMC humidity clamped');
    rh = Math.min(Math.max(rh, EMC_RH[0]), EMC_RH[EMC_RH.length - 1]);
  }
  const [i, ti] = bracket(EMC_TEMPS_F, tf);
  const [j, tj] = bracket(EMC_RH, rh);
  const top = EMC_TABLE[i][j] + tj * (EMC_TABLE[i][j + 1] - EMC_TABLE[i][j]);
  const bot = EMC_TABLE[i + 1][j] + tj * (EMC_TABLE[i + 1][j + 1] - EMC_TABLE[i + 1][j]);
  return { value: top + ti * (bot - top), warnings };
}

/** Allowable storage time in days (about 0.5% dry-matter loss) at grain temperature tempC and moisture mc.
 *  Interpolates ln(days). Below 15% moisture or above 75 F it extrapolates and flags it. Capped at 3650. */
export function astDays(tempC, mc) {
  const warnings = [];
  let tf = cToF(tempC);
  if (tf > AST_TEMPS_F[AST_TEMPS_F.length - 1]) warnings.push('AST temperature extrapolated');
  if (tf < AST_TEMPS_F[0]) { tf = AST_TEMPS_F[0]; warnings.push('AST temperature clamped'); }
  let m = mc;
  if (m > AST_MC[AST_MC.length - 1]) { m = AST_MC[AST_MC.length - 1]; warnings.push('AST moisture clamped'); }
  if (m < AST_MC[0]) warnings.push('AST moisture extrapolated');
  const [i, ti] = bracket(AST_TEMPS_F, tf);
  const [j, tj] = bracket(AST_MC, m);
  const ln = (r, c) => Math.log(AST_TABLE[r][c]);
  const top = ln(i, j) + tj * (ln(i, j + 1) - ln(i, j));
  const bot = ln(i + 1, j) + tj * (ln(i + 1, j + 1) - ln(i + 1, j));
  return { value: Math.min(Math.exp(top + ti * (bot - top)), P.MAX_AST_DAYS), warnings };
}

/** One day of drift: sacks, cribs and floors close 5% of the gap to the air's equilibrium moisture;
 *  hermetic bags and drying grain hold. Returns the new moisture. */
export function drift(moisture, storage, tempC, rh) {
  return PERMEABLE.has(storage) ? moisture + P.SACK_EXCHANGE_RATE * (emc(tempC, rh).value - moisture) : moisture;
}

/** Days until life used reaches 1, running forward over `forecast` ([{t, rh}], then its mean repeated).
 *  Mirrors engine days_left(). Returns the day count (365 = the horizon: "365 or more", not a prediction),
 *  or null when there is no forecast. */
export function daysLeft(moisture, storage, forecast, lifeUsed = 0) {
  if (!forecast || forecast.length === 0) return null;     // no forecast: no countdown (engine days_left)
  if (lifeUsed >= 1) return 0;
  const meanT = forecast.reduce((a, d) => a + d.t, 0) / forecast.length;
  const meanRh = forecast.reduce((a, d) => a + d.rh, 0) / forecast.length;
  let used = lifeUsed, m = moisture;
  for (let n = 0; n < P.HORIZON_DAYS; n++) {
    const d = n < forecast.length ? forecast[n] : { t: meanT, rh: meanRh };
    m = drift(m, storage, d.t, d.rh);
    used += 1 / astDays(d.t, m).value;
    if (used >= 1) return n + 1;
  }
  return P.HORIZON_DAYS;
}

/** Risk level from share of life used and days left (engine risk_level()). */
export function riskLevel(lifeUsed, left) {
  if (left === null || left === undefined) return 'UNKNOWN';
  if (lifeUsed >= P.HIGH_LIFE || left <= P.HIGH_DAYS) return 'HIGH';
  if (lifeUsed >= P.MEDIUM_LIFE || left <= P.MEDIUM_DAYS) return 'MEDIUM';
  return 'LOW';
}

/** The ONE rounding rule for every number shown (engine fmt()): correct the binary noise to 10 decimals, then
 *  round HALF UP on the decimal string. fmt(13.25, 1) = '13.3', fmt(5.05, 1) = '5.1', fmt(0.5, 0) = '1'.
 *  Same result as Python fmt() and PL/SQL ROUND(ROUND(x, 10), places) for every x >= 0. */
export function fmt(x, places = 1) {
  const neg = x < 0;
  const [ip, fp = ''] = Math.abs(x).toFixed(10).split('.');
  const digits = (ip + fp.slice(0, places)).split('').map(Number);
  let up = places < 10 ? Number(fp[places]) >= 5 : false;       // the next digit decides: half up
  for (let k = digits.length - 1; up && k >= 0; k--) { if (digits[k] === 9) digits[k] = 0; else { digits[k]++; up = false; } }
  let s = digits.join('');
  if (up) s = '1' + s;
  const whole = places ? s.slice(0, s.length - places) : s;
  const out = places ? `${whole}.${s.slice(s.length - places)}` : whole;
  return (neg && /[1-9]/.test(out) ? '-' : '') + out;
}
