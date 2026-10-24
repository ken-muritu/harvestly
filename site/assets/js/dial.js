// The countdown dial: the dashed amber arc and tick from the Harvestly logo, redrawn as ticks on an arc.
// Used as the hero ring, the days-left gauge, the section marker and the loader. Returns an SVG string so the
// same code runs at build time (tools/build-site.mjs) and in the browser.
const rad = (d) => (d * Math.PI) / 180;
const r1 = (n) => Math.round(n * 10) / 10;

/**
 * ticks  number of ticks on the arc
 * on     how many (from the start) are lit
 * hand   null, or 0..1: where the short tick (the logo's hand) points along the arc
 * level  'low' | 'medium' | 'high': colour of lit ticks (red only for high)
 */
export function dialSvg({ ticks = 36, on = 0, hand = null, level = 'low', inner = 74, outer = 94, width = 6,
  handIn = 57, handOut = 68, sweep = 270, cls = 'dial' } = {}) {
  const start = -sweep / 2;
  const step = sweep / (ticks - 1);
  const pt = (r, a) => [r1(100 + r * Math.sin(rad(a))), r1(100 - r * Math.cos(rad(a)))];
  let s = `<svg class="${cls} dial-${level}" viewBox="0 0 200 200" aria-hidden="true" focusable="false">`;
  for (let i = 0; i < ticks; i++) {
    const a = start + i * step;
    const [x1, y1] = pt(inner, a);
    const [x2, y2] = pt(outer, a);
    s += `<line class="t${i < on ? ' on' : ''}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke-width="${width}"/>`;
  }
  if (hand !== null) {
    const a = start + Math.min(1, Math.max(0, hand)) * sweep;
    const [x1, y1] = pt(handIn, a);
    const [x2, y2] = pt(handOut, a);
    s += `<line class="hand" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke-width="${width + 1.5}"/>`;
  }
  return s + '</svg>';
}

/** Section marker: n of total lit, no hand. */
export const markSvg = (n, total = 9) =>
  dialSvg({ ticks: total, on: n, inner: 52, outer: 96, width: 20, sweep: 300, cls: 'mark-dial' });
