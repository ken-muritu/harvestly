// Static build: tools/site-src/pages/*.mjs -> site/*.html, plus sitemap.xml and robots.txt, and hashed JS/CSS.
// Re-runnable at any time (the engine worker regenerates site/assets/js/data.js with tools/gen_site_data.py):
//   python3 tools/gen_site_data.py   (engine -> site/assets/js/data.js, first)
//   node tools/build-site.mjs
import fs from 'node:fs';
import { ORIGIN } from './site-src/config.mjs';
import { buildAssets } from './site-src/fingerprint.mjs';

const OUT = new URL('../site/', import.meta.url).pathname;
const manifest = buildAssets();
console.log('assets', Object.keys(manifest).length, 'hashed files');

// Pages are imported only now, so they pick up the fresh manifest.
const load = async (n) => (await import(`./site-src/pages/${n}.mjs`)).default;
const pages = { 'index.html': await load('home'), 'how-it-works.html': await load('how'), 'pilot.html': await load('pilot'),
  'partners.html': await load('partners'), 'sources.html': await load('sources'), '404.html': await load('notfound'), 'privacy.html': await load('privacy'), 'thanks.html': await load('thanks') };
for (const [f, html] of Object.entries(pages)) { fs.writeFileSync(OUT + f, html); console.log(f, html.length); }

const paths = ['/', '/how-it-works', '/pilot', '/partners', '/sources', '/privacy'];
fs.writeFileSync(OUT + 'sitemap.xml', `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${paths.map((p) => `  <url><loc>${ORIGIN}${p}</loc><lastmod>2026-10-12</lastmod></url>`).join('\n')}\n</urlset>\n`);
fs.writeFileSync(OUT + 'robots.txt', `User-agent: *\nAllow: /\n\nSitemap: ${ORIGIN}/sitemap.xml\n`);
