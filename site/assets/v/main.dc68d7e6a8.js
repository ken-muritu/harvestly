// Shared behaviour: js class, theme button, sticky header, chart text scaling, message-language toggle, hero dial,
// moisture reveal, and the page modules (home only).
const root = document.documentElement;
root.classList.add('js');
const safe = (fn) => { try { return fn(); } catch { return null; } };

// ---- language of the SMS text (English / Kiswahili), remembered per browser -------------------------
const setLang = (l) => {
  if (l === 'sw') root.setAttribute('data-sms', 'sw'); else root.removeAttribute('data-sms');
  document.querySelectorAll('.seg [data-sms]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.sms === (l === 'sw' ? 'sw' : 'en'))));
};
setLang(safe(() => localStorage.getItem('hv-sms')) === 'sw' ? 'sw' : 'en');
document.addEventListener('click', (e) => {
  const b = e.target.closest('.seg [data-sms]');
  if (!b) return;
  setLang(b.dataset.sms);
  safe(() => localStorage.setItem('hv-sms', b.dataset.sms));
});

// ---- theme: follows the system until the button is used; then the choice is remembered --------------
const dark = matchMedia('(prefers-color-scheme: dark)');
const themeBtn = document.getElementById('theme');
const effective = () => root.getAttribute('data-theme') || (dark.matches ? 'dark' : 'light');
const syncTheme = () => {
  if (!themeBtn) return;
  const d = effective() === 'dark';
  themeBtn.setAttribute('aria-pressed', String(d));
  themeBtn.setAttribute('aria-label', d ? 'Dark theme, on. Switch to light' : 'Dark theme, off. Switch to dark');
  document.querySelectorAll('meta[name=theme-color]').forEach((m) => m.removeAttribute('media'));
  const metas = document.querySelectorAll('meta[name=theme-color]');
  if (metas.length) { metas[0].setAttribute('content', d ? '#09342B' : '#FDFBF8'); metas.forEach((m, i) => { if (i) m.remove(); }); }
};
themeBtn?.addEventListener('click', () => {
  const next = effective() === 'dark' ? 'light' : 'dark';
  root.setAttribute('data-theme', next);
  safe(() => localStorage.setItem('hv-theme', next));
  syncTheme();
  window.dispatchEvent(new Event('hv-theme'));
});
dark.addEventListener?.('change', syncTheme);
syncTheme();

// ---- header: hides while reading down, returns on any scroll up ---------------------------------------
const header = document.querySelector('.masthead');
if (header) {
  let last = scrollY, ticking = false;
  const update = () => {
    ticking = false;
    const y = scrollY, dy = y - last;
    if (Math.abs(dy) < 8) return;
    const hide = dy > 0 && y > 160 && !header.contains(document.activeElement);
    header.classList.toggle('is-hidden', hide);
    last = y;
  };
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
  header.addEventListener('focusin', () => header.classList.remove('is-hidden'));
}

// ---- chart text: one size in screen pixels. --u = SVG units per CSS pixel, set on every chart svg -------
const charts = document.querySelectorAll('.chart svg, .chart-svg, .tape70, .gate');
if (charts.length && 'ResizeObserver' in window) {
  const ro = new ResizeObserver((entries) => {
    for (const { target: svg } of entries) {
      const vb = svg.viewBox && svg.viewBox.baseVal;
      const w = svg.getBoundingClientRect().width;
      if (vb && vb.width && w) svg.style.setProperty('--u', (vb.width / w).toFixed(3));
    }
  });
  charts.forEach((c) => ro.observe(c));
}

// ---- hero dial: ticks light up in turn (time passing), then the hand settles ------------------------
const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
if (!calm) document.querySelectorAll('.hero-ring .t.on').forEach((t, i) => { t.style.animationDelay = `${i * 55}ms`; });

// ---- problem: reveal the moisture ---------------------------------------------------------------------
const reveal = document.getElementById('reveal');
if (reveal) {
  const sacks = document.getElementById('sacks');
  const toggle = () => {
    const on = reveal.getAttribute('aria-pressed') !== 'true';
    reveal.setAttribute('aria-pressed', String(on));
    sacks.dataset.state = on ? 'shown' : 'hidden';
  };
  reveal.addEventListener('click', toggle);
  sacks.addEventListener('click', toggle);
}

// ---- page modules (home only) -------------------------------------------------------------------------
if (document.getElementById('hero-phone')) import('./hero.b3aad64280.js');
if (document.getElementById('stage')) import('./story.a81f9db32e.js');
if (document.getElementById('calc')) import('./calc.cd126083c9.js');
