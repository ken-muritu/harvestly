// Shared pieces of the static build: page shell, masthead, footer, section marker, reference links.
import fs from 'node:fs';
import { markSvg } from '../../site/assets/js/dial.js';
import { ORIGIN, CONTACT_EMAIL, FORMS } from './config.mjs';

export { ORIGIN, CONTACT_EMAIL, FORMS };
export const EMAIL = CONTACT_EMAIL;   // older name, kept so pages can import either
export const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
/** Keeps a short phrase on one line ("7-day", "salt-test"). */
export const nb = (s) => `<span class="nb">${s}</span>`;

const EXT = '<svg class="ext" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
/** A call to action that opens a Tally form in a new tab. cls: 'btn' or 'textlink'. Visible text, hidden warning, icon cue. */
export const formLink = (key, cls = 'btn', text = FORMS[key].label) =>
  `<a class="${cls}" href="${FORMS[key].url}" target="_blank" rel="noopener noreferrer">${esc(text)}<span class="vh"> (opens in a new tab)</span>${EXT}</a>`;

export const NAV = [
  ['/how-it-works', 'How it works'],
  ['/pilot', 'Pilot'],
  ['/partners', 'Partners'],
  ['/sources', 'Sources'],
];

/** Hashed asset URL from the manifest written by tools/build-site.mjs (falls back to the plain path). */
export const asset = (name) => {
  try {
    const m = JSON.parse(fs.readFileSync(new URL('../../site/assets/v/manifest.json', import.meta.url)));
    if (m[name]) return `/assets/v/${m[name]}`;
  } catch { /* no manifest yet */ }
  return `/assets/${name.endsWith('.css') ? 'css' : 'js'}/${name}`;
};

/** Inline reference link(s): ref(8, 9) -> [8][9], each a link to /sources#rN. No whitespace around the markers. */
export const ref = (...ns) => `<span class="refs">${ns.map((n) => `<a class="ref" href="/sources#r${n}" aria-label="Source ${n}">${n}</a>`).join('')}</span>`;

/** Section marker: the dial with n of `total` ticks lit, then "02 The problem". */
export const mark = (n, label, total = 9) =>
  `<p class="mark">${markSvg(n, total)}<span><span class="mark-n">${String(n).padStart(2, '0')}</span> ${esc(label)}</span></p>`;

const THEME_ICON = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor"/></svg>';

const masthead = (path) => `<header class="masthead" id="top">
  <a class="brand" href="/" aria-label="Harvestly, home"><img class="logo-l" src="/brand/harvestly-horizontal.svg" alt="Harvestly" width="117" height="30"><img class="logo-d" src="/brand/harvestly-horizontal-reversed.svg" alt="" width="117" height="30"></a>
  <nav aria-label="Main"><ul>${NAV.map(([h, t]) => `<li><a href="${h}"${path === h ? ' aria-current="page"' : ''}>${t}</a></li>`).join('')}</ul></nav>
  <button type="button" class="theme-btn" id="theme" aria-pressed="false" aria-label="Dark theme">${THEME_ICON}</button>
</header>`;

const footer = () => `<footer class="foot">
  <div class="wrap foot-grid">
    <div class="foot-brand">
      <a class="foot-logo" href="/" aria-label="Harvestly, home"><img src="/brand/harvestly-horizontal-reversed.svg" alt="Harvestly" width="140" height="36"></a>
      <p class="foot-line">Hackathon prototype. The pilot has not run.</p>
      <p class="foot-line">Contact: ${formLink('team', 'textlink foot-form')} or <a href="mailto:${CONTACT_EMAIL}">${CONTACT_EMAIL}</a></p>
    </div>
    <nav class="foot-nav" aria-label="Footer"><ul>
      <li><a href="/how-it-works">How it works</a></li><li><a href="/pilot">Pilot</a></li><li><a href="/partners">Partners</a></li><li><a href="/sources">Sources</a></li><li><a href="/privacy">Privacy</a></li>
    </ul></nav>
  </div>
  <div class="wrap"><p class="foot-small">Demos use simulated weather. The engine is designed to read forecasts from <a href="https://open-meteo.com/">Open-Meteo.com</a> (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>). Figures come from the cited <a href="/sources">sources</a> (checked 9 to 12 October 2026) or the engine&rsquo;s own scenarios.</p></div>
</footer>`;

/** The full HTML document. `path` is the clean URL ("/" or "/pilot"). */
export function page({ path, title, desc, og, ogAlt, body, cls = '', scripts = ['main.js'], noindex = false }) {
  if (desc.length > 160) throw new Error(`description too long (${desc.length}) for ${path}`);
  if (title.length > 60) throw new Error(`title too long (${title.length}) for ${path}: ${title}`);
  const url = ORIGIN + (path === '/' ? '/' : path);
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(desc)}">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#FDFBF8" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#09342B" media="(prefers-color-scheme: dark)">
${noindex ? '<meta name="robots" content="noindex">' : `<link rel="canonical" href="${url}">`}
<meta property="og:type" content="website">
<meta property="og:site_name" content="Harvestly">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(desc)}">
<meta property="og:url" content="${url}">
<meta property="og:image" content="${ORIGIN}/og/${og}.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="${esc(ogAlt || title)}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preload" href="/assets/fonts/dm-sans-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/assets/fonts/dm-sans-latin-700-normal.woff2" as="font" type="font/woff2" crossorigin>
<script src="${asset('theme.js')}"></script>
<link rel="stylesheet" href="${asset('style.css')}">
${scripts.map((s) => `<script type="module" src="${asset(s)}"></script>`).join('\n')}
</head>
<body class="${cls}">
<a class="skip" href="#main">Skip to content</a>
${masthead(path)}
<main id="main">
${body}
</main>
${footer()}
</body>
</html>
`;
}
