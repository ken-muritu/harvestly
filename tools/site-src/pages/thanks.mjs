import { page, CONTACT_EMAIL } from '../lib.mjs';

const body = `
<section class="phero">
  <div class="wrap phero-in">
    <h1>Thank you.</h1>
    <p class="lede">We have your answers. This does not sign you up for alerts: Harvestly is a hackathon prototype and no alerts are live. We have not promised a reply or a date.</p>
    <p class="lede">To have your answers deleted, email <a href="mailto:${CONTACT_EMAIL}?subject=Harvestly%20data%20request">${CONTACT_EMAIL}</a>. More in the <a href="/privacy">privacy note</a>.</p>
    <p class="actions"><a class="btn" href="/">Back to the story</a></p>
  </div>
</section>`;

export default page({ path: '/thanks', title: 'Thank you: Harvestly', desc: 'Your answers were received. This is not a sign-up for alerts, and nothing is promised.', og: 'home', scripts: ['main.js'], body, noindex: true });
