import { page, mark, ref, CONTACT_EMAIL, formLink } from '../lib.mjs';

const body = `
<section class="phero">
  <div class="wrap phero-in">
    <h1>A proposed pilot in Trans Nzoia.</h1>
    <p class="lede">One crop, one county, one season: October 2026 to January 2027. It has not started. Nothing on this page is a result or a promise.</p>
    <p class="actions">${formLink('farmer')}<a class="textlink" href="mailto:${CONTACT_EMAIL}?subject=Harvestly%20pilot">Or email about the pilot</a><a class="textlink" href="#estimate">See the impact estimate</a></p>
  </div>
</section>

<section class="sec" aria-labelledby="h-where">
  <div class="wrap">
    ${mark(1, 'Where and who', 5)}
    <h2 id="h-where">Why Trans Nzoia, and for whom.</h2>
    <div class="two">
      <div class="prose">
        <h3>Where</h3>
        <p>Trans Nzoia (Kitale): above-average rain is forecast through the harvest ${ref(12)} and the drought cut the crop, so each sack is likely to be worth more ${ref(8, 9)}. The National Cereals and Produce Board (NCPB) depot at Kitale is among the certified warehouse-receipt stores ${ref(30)}, so the advice has a real destination.</p>
      </div>
      <div class="prose">
        <h3>Who</h3>
        <p>Smallholders who keep maize at home in woven sacks, use a basic phone, and read Kiswahili or English. 29.6 million feature phones are connected, out of 78.3 million mobile connections in Kenya ${ref(23)}, so SMS and USSD would come first and Telegram would serve smartphone users.</p>
      </div>
    </div>
    <figure class="sat">
      <img src="/assets/img/trans-nzoia-modis-2025-12-20.jpg" width="800" height="800" loading="lazy" decoding="async" alt="Satellite view of the Trans Nzoia area from NASA MODIS Terra, true colour, 20 December 2025. The dark mass at the left is Mount Elgon; there is scattered cloud, mostly along the left edge. Individual farms are not visible.">
      <figcaption>
        <p>Satellite view of the Trans Nzoia area, NASA MODIS Terra true colour, 20 December 2025. About 88 km across; individual farms are not visible. Scattered cloud is visible. It is one day&rsquo;s picture of the ground, not today&rsquo;s view and not a picture of crop conditions. ${ref(39)}</p>
        <p class="sat-credit">Imagery: NASA Worldview / GIBS (MODIS Terra).</p>
      </figcaption>
    </figure>
  </div>
</section>

<section class="sec panel" aria-labelledby="h-plan">
  <div class="wrap">
    ${mark(2, 'The plan', 5)}
    <h2 id="h-plan">The proposed plan, in four steps.</h2>
    <ol class="steps steps-4">
      <li><h3>Register</h3><p>Planned: in under a minute, by SMS, USSD or Telegram. The farmer gives a ward, a harvest date, a number of bags, and how the grain is kept.</p></li>
      <li><h3>Test</h3><p>The free salt test is only a screen and never clears grain. A meter reading from a co-operative or an NCPB depot does, and so can a hygrometer of about US$4 sealed in a bag of grain; cheap ones need 30 to 45 minutes to settle ${ref(18, 19)}.</p></li>
      <li><h3>Watch</h3><p>Every evening the engine would update each batch from that day&rsquo;s weather and the 7-day forecast, and send at most one unprompted message, only when something changes.</p></li>
      <li><h3>Check</h3><p>Proposed: about 200 farmers through one or two co-operatives and the county extension office, with meter spot checks to calibrate the drift rate and the two salt-test values. We found no randomised trial of SMS advice on storage behaviour, so the roll-out would be staggered, which can measure the effect.</p></li>
    </ol>
    <p class="prose-wide">The dates are a proposal and depend on partners and approvals.</p>
  </div>
</section>

<section class="sec" aria-labelledby="h-measure">
  <div class="wrap">
    ${mark(3, 'What would count', 5)}
    <h2 id="h-measure">What would count as working.</h2>
    <p class="prose-wide">Definitions, not targets.</p>
    <ul class="measures">
      <li><b>Test completion.</b> The share of registered farmers who complete at least one test.</li>
      <li><b>Alert to action.</b> Replies such as &ldquo;1&rdquo; (covered), DRYING or SEALED, plus spot checks.</li>
      <li><b>Meter before sealing.</b> The share of batches meter-tested at 13.5% or below before sealing or delivery.</li>
      <li><b>False alarms and opt-outs.</b> A warning was sent and the meter shows dry grain; the farmer sends STOP.</li>
      <li><b>Stored loss.</b> Self-reported loss after 3 months, compared with non-users in the same wards. Self-reports are a weak measure, so meter spot checks would back them up.</li>
    </ul>
    <h3 class="h3-gap">The data it would build</h3>
    <p class="prose-wide">A ward-level record of farm-gate grain moisture and storage practice. It is scarce today, and useful to county governments and warehouse operators.</p>
  </div>
</section>

<section class="sec panel" id="estimate" aria-labelledby="h-est">
  <div class="wrap">
    ${mark(4, 'Impact estimate', 5)}
    <h2 id="h-est"><span class="tag tag-estimate">ILLUSTRATIVE</span> An upper bound, per 10,000 bags stored in woven sacks.</h2>
    <div class="table-wrap"><table class="est"><caption class="vh">Estimated bags, tonnes, value and water saved per 10,000 bags, at three rates of switching to hermetic bags</caption>
      <thead><tr><th scope="col">If this many switch to hermetic bags</th><th scope="col">2% (trial average)</th><th scope="col">10%</th><th scope="col">25%</th></tr></thead>
      <tbody>
        <tr><th scope="row">Bags saved</th><td data-label="If 2% switch (trial average)">17</td><td data-label="If 10% switch">85</td><td data-label="If 25% switch">213</td></tr>
        <tr><th scope="row">Tonnes saved</th><td data-label="If 2% switch (trial average)">1.5 t</td><td data-label="If 10% switch">7.7 t</td><td data-label="If 25% switch">19.1 t</td></tr>
        <tr><th scope="row">Value saved</th><td data-label="If 2% switch (trial average)">KES 68,000</td><td data-label="If 10% switch">KES 340,000</td><td data-label="If 25% switch">KES 850,000</td></tr>
        <tr><th scope="row">Water embodied in that maize</th><td data-label="If 2% switch (trial average)">1,900 m³</td><td data-label="If 10% switch">9,300 m³</td><td data-label="If 25% switch">23,400 m³</td></tr>
      </tbody></table></div>
    <p class="prose-wide">Rounded. Gross: the cost of the hermetic bags is not taken off. Only the switch to hermetic bags is counted. No trial shows that Harvestly itself reduces loss, so this is an illustration built from other trials, not a measurement and not a forecast.</p>
    <details class="more"><summary>How the estimate is built</summary>
      <p><b>Inputs.</b> In a randomised trial (abstract only; we have not confirmed the county), maize in ordinary polypropylene bags lost 12.4% of its weight in 4 months and maize in hermetic bags lost 3.9%: 8.5 points saved per bag switched ${ref(31)}. Six SMS-advice trials in Kenya and Rwanda raised adoption of recommended practices by about 2 percentage points on average ${ref(32)}. We use that as the base case and show higher uptake as scenarios. Grain is valued at the January 2026 NCPB price of KES 4,000 a bag ${ref(11)}. Water uses a global average footprint ${ref(33)}, not a Trans Nzoia measurement.</p>
      <p><b>Why it is an upper bound.</b> We have no current price quote for the bags. The 2-point effect is an average across six SMS programmes on recommended practices in general, not a measured effect of switching to hermetic bags, and the 8.5 points saved come from a different trial in different conditions.</p>
      <p><b>Left out.</b> The drying and testing path, lower aflatoxin exposure, drying charges avoided, and access to warehouse-receipt credit.</p>
    </details>
  </div>
</section>

<section class="sec" aria-labelledby="h-open">
  <div class="wrap">
    ${mark(5, 'Still open', 5)}
    <h2 id="h-open">What is still open.</h2>
    <ul class="measures">
      <li><b>Iodised salt.</b> The salt test asks for non-iodised salt, and Kenyan table salt is normally iodised. A side-by-side salt and meter test on the same maize would show what happens.</li>
      <li><b>Channels.</b> Only a Telegram test bot exists, with simulated weather and no alerts. No SMS shortcode or USSD code is provisioned. The test bot replies only after someone messages it and sends no unprompted alerts; Telegram bots can message a person only once that person has messaged them first ${ref(26)}. Africa&rsquo;s Talking sandbox SMS reaches only a simulator. A USSD session lasts up to 180 seconds, but Safaricom ends it after 30 seconds without input, so the menus must be short ${ref(27)}.</li>
      <li><b>Weather data.</b> The free <a href="https://open-meteo.com/">Open-Meteo.com</a> tier is for non-commercial use ${ref(29)}. A pilot or production service would need a paid plan, or a data agreement with the Kenya Meteorological Department (KMD) or the Kenya Agricultural Observatory Platform.</li>
      <li><b>Data protection.</b> The plan is consent at registration and no ID numbers, under the Data Protection Act 2019. A small controller (turnover under KES 5 million, fewer than 10 staff) need not register with the Data Protection Commissioner unless it processes data for a purpose the regulations list; agriculture is not among them. The Act applies either way ${ref(37)}. Retention, and where messaging providers process data (Telegram is outside Kenya), still have to be written down.</li>
    </ul>
  </div>
</section>
`;

export default page({
  path: '/pilot',
  title: 'The Harvestly pilot proposal: Trans Nzoia, 2026 to 2027',
  desc: 'A proposal, not a pledge: how Harvestly would be tested with about 200 maize farmers in Trans Nzoia, what would count as working, and what is still open.',
  og: 'pilot',
  scripts: ['main.js'],
  body,
});
