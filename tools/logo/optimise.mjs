// Shrinks the traced logo SVGs in site/brand/: rounds coordinates to a coarser grid and writes
// them as relative path data. Same artwork, <15 KB each. Run: node tools/logo/optimise.mjs [unit]
// unit = grid size in viewBox units (default 0.5). The trace itself is made by trace.js.
import fs from 'node:fs';
const DIR = new URL('../../site/brand/', import.meta.url).pathname;
const UNIT = Number(process.argv[2] || 0.5);
const STRAIGHT = Number(process.argv[3] || 0.7);        // grid units: a curve this close to its chord becomes a line
const SRC = process.env.HV_SRC || '/tmp/hv-brand-src/';           // cache of the raw traces (trace.js output)
fs.mkdirSync(SRC, { recursive: true });
for (const f of fs.readdirSync(DIR)) if (f.startsWith('harvestly-') && fs.readFileSync(DIR + f, 'utf8').includes('scale(0.3333)')) fs.copyFileSync(DIR + f, SRC + f);
function shrink(d) {
  // path data from potrace: M x y C x y, x y, x y ... L x y ...  (absolute, 3 dp, in 1/3 units)
  const toks = d.replace(/,/g, ' ').match(/[MCLZ]|-?\d*\.?\d+/g);
  const k = 1 / (3 * UNIT);                                        // source unit (1/3) -> grid
  let i = 0, out = '', cx = 0, cy = 0, cmd = '', last = '';
  const put = (c, a) => { const body = fmt(a); out += (c === last ? (/^-/.test(body) ? '' : ' ') : c) + body; last = c; };
  const num = () => Math.round(parseFloat(toks[i++]) * k);
  const fmt = (a) => a.map((n, j) => (j && n >= 0 ? ' ' : j ? ' ' : '') + n).join('').replace(/ -/g, '-');
  while (i < toks.length) {
    const t = toks[i];
    if (/[MCLZ]/.test(t)) { cmd = t; i++; if (cmd === 'Z') { out += 'z'; last = ''; continue; } }
    if (cmd === 'M') { const x = num(), y = num(); out += 'm' + fmt([x - cx, y - cy]); last = ''; cx = x; cy = y; cmd = 'L0'; }
    else if (cmd === 'C') {
      const a = [num(), num(), num(), num(), num(), num()];
      const dx = a[4] - cx, dy = a[5] - cy, len = Math.hypot(dx, dy) || 1;
      const dist = (px, py) => Math.abs((px - cx) * dy - (py - cy) * dx) / len;
      if (Math.max(dist(a[0], a[1]), dist(a[2], a[3])) <= STRAIGHT) put('l', [dx, dy]);   // near-straight curve -> line
      else put('c', [a[0] - cx, a[1] - cy, a[2] - cx, a[3] - cy, dx, dy]);
      cx = a[4]; cy = a[5]; cmd = 'C';
    }
    else { const x = num(), y = num(); put('l', [x - cx, y - cy]); cx = x; cy = y; }
  }
  return out;
}
let total = 0;
for (const f of fs.readdirSync(SRC)) {
  let s = fs.readFileSync(SRC + f, 'utf8');
  s = s.replace(/<g transform="scale\(0\.3333\)">/, `<g transform="scale(${UNIT})">`).replace(/ d="([^"]+)"/g, (_, d) => ` d="${shrink(d)}"`);
  fs.writeFileSync(DIR + f, s); total += s.length; console.log(f, s.length);
}
