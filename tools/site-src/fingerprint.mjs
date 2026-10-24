// Content-hashed copies of the site's JS and CSS, so they can be cached for a year ("immutable").
//   site/assets/js/*.js, site/assets/css/style.css  ->  site/assets/v/<name>.<hash>.<ext>   + manifest.json
// Imports between modules ("./data.js", import('./story.js')) are rewritten to the hashed names, dependencies first,
// so a change in data.js changes the hash of every file that imports it. The sources stay where they are (tests and
// the build import them); site/.vercelignore keeps them off the deployed site.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const SITE = new URL('../../site/', import.meta.url).pathname;
const JS = SITE + 'assets/js/', CSS = SITE + 'assets/css/', OUT = SITE + 'assets/v/';

export function buildAssets() {
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });
  const manifest = {};
  const files = fs.readdirSync(JS).filter((f) => f.endsWith('.js'));
  const IMPORT = /((?:from\s*|import\s*\(\s*|import\s+)['"])\.\/([\w-]+\.js)(['"])/g;
  const state = {};   // name -> 'busy' | 'done'
  const hashOf = (b) => crypto.createHash('sha256').update(b).digest('hex').slice(0, 10);
  const emit = (name) => {
    if (state[name] === 'done') return manifest[name];
    if (state[name] === 'busy') throw new Error(`import cycle through ${name}`);
    state[name] = 'busy';
    let src = fs.readFileSync(JS + name, 'utf8');
    src = src.replace(IMPORT, (_, a, dep, z) => {
      if (!files.includes(dep)) throw new Error(`${name} imports missing ${dep}`);
      return `${a}./${emit(dep)}${z}`;
    });
    const out = name.replace(/\.js$/, `.${hashOf(src)}.js`);
    fs.writeFileSync(OUT + out, src);
    manifest[name] = out; state[name] = 'done';
    return out;
  };
  for (const f of files) emit(f);
  let css = fs.readFileSync(CSS + 'style.css', 'utf8').replace(/url\(\.\.\/fonts\//g, 'url(/assets/fonts/');
  manifest['style.css'] = `style.${hashOf(css)}.css`;
  fs.writeFileSync(OUT + manifest['style.css'], css);
  fs.writeFileSync(OUT + 'manifest.json', JSON.stringify(manifest, null, 1));
  return manifest;
}
