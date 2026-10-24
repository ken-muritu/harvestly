import { page } from '../lib.mjs';
import { dialSvg } from '../../../site/assets/js/dial.js';

const body = `
<section class="phero nf">
  <div class="wrap phero-in">
    <div class="nf-dial">${dialSvg({ ticks: 36, on: 0, hand: 0.5, cls: 'dial hero-ring' })}<p class="nf-n" aria-hidden="true">404</p></div>
    <h1>This page is not here.</h1>
    <p class="lede">The link may be old, or mistyped. The home page has the story.</p>
    <p class="actions"><a class="btn" href="/">Back to the story</a><a class="textlink" href="/sources">Sources</a></p>
  </div>
</section>`;

export default page({ path: '/404', title: 'Page not found: Harvestly', desc: 'This page does not exist. Go back to the Harvestly home page.', og: 'home', scripts: ['main.js'], body, noindex: true });
