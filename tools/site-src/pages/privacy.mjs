import { page, mark, formLink, CONTACT_EMAIL } from '../lib.mjs';

const body = `
<section class="phero">
  <div class="wrap phero-in">
    <h1>Privacy note.</h1>
    <p class="lede">Harvestly is a hackathon prototype. This page says what we collect, why, who sees it and how to ask us to delete it. A plain explanation, not legal advice. Last changed 12 October 2026.</p>
  </div>
</section>

<section class="sec" aria-labelledby="h-site">
  <div class="wrap">
    ${mark(1, 'This website', 6)}
    <h2 id="h-site">What the website itself does.</h2>
    <div class="prose-wide">
      <p>The site sets no cookies and has no analytics, advertising or tracking scripts. The calculator runs in your browser and sends nothing you type anywhere. Nothing about weather is requested when a page loads. Only if you tap the optional &ldquo;Show recent weather near Kitale&rdquo; button under the calculator does your browser ask a small function on this site for the latest days at one example ward; that function asks NASA POWER for the weather at a rounded ward centre (one decimal of latitude and longitude) and sends NASA nothing about you, and it keeps the answer in its memory for a few hours. To limit how often it can be called, the function keeps a short, salted hash of the caller&rsquo;s address in its memory for up to one minute (the salt is random, held only in memory and lost when the instance ends); it does not store or log the address itself. Your browser keeps two small preferences on your own device (light or dark, English or Kiswahili); we never receive them. Our host, Vercel, handles every request and keeps ordinary server logs (such as the time, the page and the IP address), as any web host does. The three form links open pages on tally.so, which is a different site with its own cookies and policy that we do not control.</p>
    </div>
  </div>
</section>

<section class="sec panel" aria-labelledby="h-forms">
  <div class="wrap">
    ${mark(2, 'The forms', 6)}
    <h2 id="h-forms">What the three forms collect.</h2>
    <ul class="measures">
      <li><b>Join the Harvestly interest list:</b> your name; a phone number or email if you give one (only so the team can reply to you); your county and ward; how many bags of maize you store and how; and the channel and language you would prefer. It is a list of interest, not a sign-up for alerts.</li>
      <li><b>Partner with Harvestly:</b> your organisation, your role, your email and what you wrote.</li>
      <li><b>Talk to the Harvestly team:</b> your name, your email and your message.</li>
    </ul>
    <div class="prose-wide">
      <p><b>Why.</b> To see where interest is, to shape a prototype, and to read what you wrote. We use your answers for nothing else and send no marketing.</p>
      <p><b>Who is responsible.</b> The Harvestly team, a group of individuals running a hackathon prototype. No company or other legal entity exists yet. You can reach us at <a href="mailto:${CONTACT_EMAIL}">${CONTACT_EMAIL}</a>.</p>
    </div>
  </div>
</section>

<section class="sec" aria-labelledby="h-path">
  <div class="wrap">
    ${mark(3, 'Where your answers go', 6)}
    <h2 id="h-path">The exact path, and where the copies are.</h2>
    <ol class="measures">
      <li><b>Tally</b> (tally.so) hosts the form and stores your answers. It also records technical details such as your IP address when you submit.</li>
      <li>Tally then sends each answer to a small function on this site, which runs on <b>Vercel</b>. The function runs in one place, Washington, D.C. in the United States (Vercel region iad1); the site&rsquo;s pages themselves are served from Vercel&rsquo;s worldwide network. The function does not store anything and does not write your answers to its logs.</li>
      <li>The function asks <b>Brevo</b> (an email service) to send one email with your answers to the team inbox, ${CONTACT_EMAIL}. That inbox is a <b>Gmail</b> account run by Google (United States and other countries). If you gave an address in the email box of the partner or team form, it is set as the reply address, so the team can answer you. The interest-list form has one box for a phone number or an email; the team reads it in the email and replies by hand.</li>
    </ol>
    <div class="prose-wide">
      <p><b>We send nothing to you automatically.</b> There is no confirmation email. The only email made because of your answers is the one to the team. We cannot tell you what Brevo or Google record on their own systems beyond that, and we do not claim they record nothing; see their policies.</p>
      <p><b>Outside Kenya.</b> We expect the services above to process your answers outside Kenya, so the form asks for your agreement to a transfer abroad before you can submit it. We have not checked where Tally and Brevo store data; see their policies.</p>
      <p><b>Copies.</b> Your answers exist in Tally, in the Gmail inbox and in Brevo&rsquo;s message log, which keeps the text of each email. We have not yet written retention rules, so they stay in all three until deleted. We do not sell your answers.</p>
      <p><b>Children.</b> The forms are meant for adults. Do not submit answers for a child.</p>
    </div>
  </div>
</section>

<section class="sec" aria-labelledby="h-bot">
  <div class="wrap">
    ${mark(4, 'The test bot', 6)}
    <h2 id="h-bot">The Telegram test bot.</h2>
    <p>@HarvestlyBot is a prototype test with simulated weather. It replies only after you message it and sends no unprompted alerts.</p>
    <ul class="measures">
      <li><b>Kept, per chat:</b> a salted one-way code made from your Telegram chat id (the id itself is not kept), the language, the test registration (an example ward, how the grain is stored, number of bags, dates, and the readings and answers you send), whether you sent STOP, and a message counter. Separately, the numbers Telegram gives each update are kept for 2 days, only so the same update is not answered twice.</li>
      <li><b>Not kept:</b> your message text as typed, names, usernames, phone numbers, profile details or location. Telegram itself sees the conversation under its own privacy policy.</li>
      <li><b>Where:</b> a Vercel function in Dublin, Ireland, and a Turso database on AWS in Ireland.</li>
      <li><b>Weather:</b> /weather asks NASA POWER, from our server, for the weather at the rounded centre of an example ward (Kitale if you have not registered). Only that rounded point is sent: no chat id, message or other chat data.</li>
      <li><b>Deleting:</b> send /reset to erase the registration and readings at once. The small record that stays after /reset (the one-way code, the language and the message counter) is deleted with the rest: a clean-up that runs once a day deletes every chat record not used for 30 days, counted from your last message or /reset. To have everything removed sooner, write to the project contact.</li>
    </ul>
  </div>
</section>

<section class="sec panel" aria-labelledby="h-rights">
  <div class="wrap">
    ${mark(5, 'Your rights', 6)}
    <h2 id="h-rights">Ask us to delete, correct or show you your answers.</h2>
    <div class="prose-wide">
      <p>Email <a href="mailto:${CONTACT_EMAIL}?subject=Harvestly%20data%20request">${CONTACT_EMAIL}</a>. Say which form and which name or email you used. Ask for your answers to be deleted from Tally, from the Gmail inbox and from Brevo&rsquo;s log. The Kenya Data Protection Act, 2019 gives you the right to know what is held about you, to see it, to correct it, to object, and to have it erased. If you are unhappy, you can complain to the Office of the Data Protection Commissioner (<a href="https://www.odpc.go.ke/" rel="noopener">odpc.go.ke</a>). We cannot promise how quickly we reply, because this is a prototype run by a small team.</p>
    </div>
  </div>
</section>

<section class="sec" aria-labelledby="h-open">
  <div class="wrap">
    ${mark(6, 'What we have not settled', 6)}
    <h2 id="h-open">Open points.</h2>
    <div class="prose-wide">
      <p>We have not yet decided whether registration with the ODPC applies to us. The exemption depends on both turnover and staff numbers, and a pilot with counties or a messaging service could change the answer. A qualified person has not reviewed this note. If Harvestly sends alerts in future, this page would change first.</p>
    </div>
    <p class="actions actions-left">${formLink('team', 'btn')}<a class="textlink" href="mailto:${CONTACT_EMAIL}">Or email ${CONTACT_EMAIL}</a></p>
  </div>
</section>
`;

export default page({
  path: '/privacy',
  title: 'Harvestly privacy note',
  desc: 'What the Harvestly site and its three forms collect, where answers go and are copied, and how to ask for deletion. A prototype; no alerts are live.',
  og: 'privacy',
  scripts: ['main.js'],
  body,
});
