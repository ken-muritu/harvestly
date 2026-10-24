// Local static server for the site with clean URLs and the production CSP (so inline code shows up as errors).
//   node tools/serve.mjs [port]
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path'; import { createRequire } from 'node:module';
const recentWeather = createRequire(import.meta.url)('../site/api/recent-weather.js');   // the one serverless function the page calls
const ROOT = new URL('../site/', import.meta.url).pathname; const PORT = Number(process.argv[2] || 4173);
const vercel = JSON.parse(fs.readFileSync(ROOT + 'vercel.json', 'utf8'));
const hdrs = Object.fromEntries(vercel.headers[0].headers.map((h) => [h.key, h.value]));
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.xml': 'application/xml', '.txt': 'text/plain', '.json': 'application/json' };
http.createServer(async (req, res) => {
  if (req.url.split('?')[0] === '/api/recent-weather') {
    for (const [k, v] of Object.entries(hdrs)) res.setHeader(k, v);
    const r = Object.assign(res, { status(c) { res.statusCode = c; return res; }, json(j) { res.end(JSON.stringify(j)); return res; } });
    return recentWeather(req, r);
  }
  let p = decodeURIComponent(req.url.split('?')[0]); if (p === '/') p = '/index.html';
  let f = path.join(ROOT, p); if (!path.extname(f) && fs.existsSync(f + '.html')) f += '.html';
  const ok = f.startsWith(ROOT) && fs.existsSync(f) && fs.statSync(f).isFile();
  if (!ok) { f = ROOT + '404.html'; res.statusCode = 404; }
  res.setHeader('Content-Type', TYPES[path.extname(f)] || 'application/octet-stream'); for (const [k, v] of Object.entries(hdrs)) res.setHeader(k, v);
  fs.createReadStream(f).pipe(res);
}).listen(PORT, () => console.log('http://localhost:' + PORT));
