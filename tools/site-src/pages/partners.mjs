import { page, mark, ref, CONTACT_EMAIL, formLink } from '../lib.mjs';

const body = `
<section class="phero">
  <div class="wrap phero-in">
    <h1>For <span class="nb">co-operatives</span>, extension officers, counties and warehouses.</h1>
    <p class="lede">Harvestly is designed to sit inside what you already run: tell a farmer how long a batch will keep, and send the farmer to you at the right moment. It is a prototype.</p>
    <p class="actions">${formLink('partner')}<a class="textlink" href="mailto:${CONTACT_EMAIL}?subject=Harvestly%20partnership">Or email ${CONTACT_EMAIL}</a><a class="textlink" href="#fit">How it fits</a></p>
  </div>
</section>

<section class="sec" aria-labelledby="h-get">
  <div class="wrap">
    ${mark(1, 'What each gets', 4)}
    <h2 id="h-get">What each of you would get.</h2>
    <dl class="who who-wide">
      <div><dt>Co-operatives and aggregators</dt><dd>A planned list of members&rsquo; batches by risk and ward. A way to enter a meter reading on a farmer&rsquo;s behalf. Dry grain at your door, because the farmer was told to dry it first.</dd></div>
      <div><dt>Extension officers</dt><dd>A planned dashboard (built in Oracle APEX) of batches by risk and ward, messages sent, replies (the alert-to-action rate), data flags, and a directory of stockists and warehouses.</dd></div>
      <div><dt>County governments</dt><dd>Agriculture is devolved. This would be extension advice delivered on the day it matters, at the cost of an SMS, and a ward-level record of farm-gate moisture and storage practice.</dd></div>
      <div><dt>Warehouse-receipt operators and NCPB</dt><dd>Grain that arrives already measured against the 13.5% line ${ref(3, 17)}. Warehouses name farm-gate drying and testing as binding constraints; this would address testing.</dd></div>
    </dl>
  </div>
</section>

<section class="sec panel" id="fit" aria-labelledby="h-fit">
  <div class="wrap">
    ${mark(2, 'How it fits', 4)}
    <h2 id="h-fit">As a module inside MoA-INFO or KAOP.</h2>
    <div class="two">
      <div class="prose">
        <p>MoA-INFO, run by Precision Development, sends free SMS and Telegram crop advice ward by ward, in English and Kiswahili ${ref(14)}. KAOP, the Kenya Agricultural Observatory Platform, sends ward-level forecasts and agro-advisories ${ref(15)}. We found no per-batch storage monitoring in either, so Harvestly is designed to run inside them, not to compete for farmers&rsquo; attention.</p>
      </div>
      <div class="prose">
        <p>The engine is one package. In: a ward, a batch (storage type, harvest date, language) and any readings the farmer sends. Out: a recommendation code and the message, in English or Kiswahili. Templates sit in a table keyed by code and language, so your wording can replace ours.</p>
      </div>
    </div>
  </div>
</section>

<section class="sec" aria-labelledby="h-farmer">
  <div class="wrap">
    ${mark(3, 'The farmer', 4)}
    <h2 id="h-farmer">What it costs the farmer.</h2>
    <div class="prose-wide">
      <p>The design is for alerts to be free to the farmer. A reply, such as SALT YES or METER 14.2, would be an ordinary SMS, charged at the sender&rsquo;s network rate unless the short code is arranged otherwise; who pays for inbound SMS is not settled. Unprompted messages are at most one a day, at most two SMS, and STOP ends them. Only a meter, hygrometer or depot reading clears grain, which needs a visit to a co-operative or an NCPB depot.</p>
    </div>
  </div>
</section>

<section class="sec panel" aria-labelledby="h-pay">
  <div class="wrap">
    ${mark(4, 'Who might pay', 4)}
    <h2 id="h-pay">Who might pay. Hypotheses, not agreements.</h2>
    <p class="prose-wide">Nobody has agreed to anything. Each idea is untested.</p>
    <ul class="measures">
      <li><b>Counties,</b> for advice that arrives at SMS cost.</li>
      <li><b>Warehouse-receipt operators, aggregators and millers,</b> per tonne that passes intake. Dry grain means fewer rejections and lower drying costs.</li>
      <li><b>Hermetic-bag makers and distributors,</b> for a stockist listing that is clearly labelled as one. A design rule: payment never changes the advice a farmer receives.</li>
      <li><b>Existing advisory services,</b> licensing the engine as their post-harvest module.</li>
    </ul>
    <p class="actions actions-left">${formLink('partner')}<a class="textlink" href="/pilot">Read the pilot plan</a></p>
  </div>
</section>
`;

export default page({
  path: '/partners',
  title: 'Harvestly for co-operatives, counties and warehouses',
  desc: 'What a maize-storage countdown gives co-operatives, extension officers, counties and warehouses, and how it fits MoA-INFO or KAOP as a post-harvest module.',
  og: 'partners',
  scripts: ['main.js'],
  body,
});
