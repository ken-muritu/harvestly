import { page, mark, esc, ref } from '../lib.mjs';
import { REFS } from '../refs.mjs';

const LABEL = { verified: ['Verified', 'Read at the publisher or its official record.'], secondary: ['Secondary', 'Read through a mirror, a news report or a search summary.'], cited: ['Cited', 'Cited in concept note v3 (sources checked 9 October 2026). Not re-opened in the 12 October check.'] };
const items = REFS.map(([n, title, url, label, note]) => `<li id="r${n}" class="src"><span class="src-n">${n}</span><div><p class="src-t"><a href="${url}" rel="noopener">${esc(title)}</a></p><p class="src-m"><span class="tag tag-${label}">${LABEL[label][0]}</span>${note ? ` <span>${esc(note)}</span>` : ''}</p></div></li>`).join('');

const body = `
<section class="phero">
  <div class="wrap phero-in">
    <h1>Where every number comes from.</h1>
    <p class="lede">Thirty-nine numbered references, each labelled by how far we checked it. Links open the publisher or the copy we read. Checked 9 to 12 October 2026; a link can still change.</p>
    <p class="actions"><a class="btn" href="/how-it-works">How the engine uses them</a></p>
  </div>
</section>

<section class="sec" aria-labelledby="h-labels">
  <div class="wrap">
    ${mark(1, 'How we label', 3)}
    <h2 id="h-labels">Three labels.</h2>
    <ul class="key key-col">${Object.values(LABEL).map(([t, d], i) => `<li><span class="tag tag-${Object.keys(LABEL)[i]}">${t}</span> ${d}</li>`).join('')}</ul>
  </div>
</section>

<section class="sec panel" aria-labelledby="h-words">
  <div class="wrap">
    ${mark(2, 'Wording we chose', 3)}
    <h2 id="h-words">Four places where we chose our words with care.</h2>
    <ul class="measures">
      <li><b>&ldquo;USDA cut its forecast by half.&rdquo;</b> The 51% is a cut against USDA&rsquo;s earlier forecast of 4.5 Mt, not a fall against last year.</li>
      <li><b>Insects.</b> The Kenyan storage-loss study counts losses to two insects. It does not rank insects against moisture or mould, and its authors say its total looks high. We do not quote the total.</li>
      <li><b>Hermetic bags.</b> About one in six Kenyan maize farmers uses them: a focus-group estimate of farmers, not a household count ${ref(2)}.</li>
      <li><b>White maize.</b> The tables are for US corn. A study of US white and waxy corn found each type needs its own curve ${ref(36)}. That is not Kenyan white maize either.</li>
    </ul>
  </div>
</section>

<section class="sec" aria-labelledby="h-refs">
  <div class="wrap">
    ${mark(3, 'The references', 3)}
    <h2 id="h-refs">References.</h2>
    <ol class="srcs">${items}</ol>
  </div>
</section>
`;

export default page({
  path: '/sources',
  title: 'Harvestly sources: 39 references, each labelled',
  desc: 'The 39 references behind Harvestly, each labelled verified, secondary or cited, with the wording choices we made on USDA, insects and hermetic bags.',
  og: 'sources',
  scripts: ['main.js'],
  body,
});
