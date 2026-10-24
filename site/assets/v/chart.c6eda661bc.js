// Tiny SVG chart helpers shared by the build and the browser. No dependencies.
/** Linear scales for a chart area. area = [left, top, right, bottom] in SVG units. */
export function scales(area, [x0, x1], [y0, y1]) {
  const [l, t, r, b] = area;
  return { X: (x) => l + ((x - x0) / (x1 - x0)) * (r - l), Y: (y) => b - ((y - y0) / (y1 - y0)) * (b - t) };
}
/** "M x y L x y ..." through points [[x, y], ...]. */
export const linePath = (pts, X, Y) => pts.map(([x, y], i) => `${i ? 'L' : 'M'}${X(x).toFixed(1)} ${Y(y).toFixed(1)}`).join('');
