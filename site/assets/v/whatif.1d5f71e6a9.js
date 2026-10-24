// "What if the sack does not dry?" Counterfactual countdowns for the story and the calculator.
// A copy of engine.js daysLeft() with the daily exchange rate as a parameter, built on engine.js's own emc() and
// astDays(), so it never drifts from the tables. With rate = P.SACK_EXCHANGE_RATE it returns exactly what
// engine.js daysLeft() returns (tools/test-site.mjs asserts that); with rate = 0 the grain keeps its moisture.
import * as E from './engine.61e9735e7e.js';

const PERMEABLE = E.PERMEABLE || new Set(['sack', 'crib', 'floor']);
const HORIZON = (E.P && E.P.HORIZON_DAYS) || 365;

export const driftAt = (rate, moisture, storage, t, rh) =>
  PERMEABLE.has(storage) ? moisture + rate * (E.emc(t, rh).value - moisture) : moisture;

/** Days until the storage life is used up, as engine daysLeft(), but with a chosen drift rate. */
export function daysLeftAt(rate, moisture, storage, forecast, lifeUsed = 0) {
  if (!forecast || forecast.length === 0) return null;
  if (lifeUsed >= 1) return 0;
  const meanT = forecast.reduce((a, d) => a + d.t, 0) / forecast.length;
  const meanRh = forecast.reduce((a, d) => a + d.rh, 0) / forecast.length;
  let used = lifeUsed, m = moisture;
  for (let n = 0; n < HORIZON; n++) {
    const d = n < forecast.length ? forecast[n] : { t: meanT, rh: meanRh };
    m = driftAt(rate, m, storage, d.t, d.rh);
    used += 1 / E.astDays(d.t, m).value;
    if (used >= 1) return n + 1;
  }
  return HORIZON;
}

/** Countdown on evening `k` of a scenario for a sack that never dries (rate 0), starting from `start` percent.
 *  weather[i] = {t, rh, fc:[{t, rh}...]} as written into data.js. Returns null if the data has no forecast. */
export function noDryingDays(weather, k, start = 18) {
  let life = 0;
  for (let i = 0; i <= k; i++) life += 1 / E.astDays(weather[i].t, start).value;
  const fc = weather[k].fc;
  return fc ? daysLeftAt(0, start, 'sack', fc, life) : null;
}
