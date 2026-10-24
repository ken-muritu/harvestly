// The hero phone: plays the engine's own messages one by one (registration, welcome, the warning, the farmer's reply, the answer),
// with a typing indicator, the thread scrolling to the newest. The HTML already holds the final state, so without JavaScript or
// under prefers-reduced-motion nothing moves. Pauses when the tab is hidden or the phone is off screen; a button pauses it by hand.
const fig = document.getElementById('hero-phone');
const thread = document.getElementById('hero-thread');
const calm = matchMedia('(prefers-reduced-motion: reduce)');
if (fig && thread && !calm.matches) {
  const items = [...thread.querySelectorAll('.msg')];
  const phone = fig.querySelector('.phone');
  const alt = document.getElementById('hero-alt');
  let paused = false, inView = true, token = 0;

  // one text alternative for the whole conversation instead of announcing every bubble as it arrives
  phone.setAttribute('aria-hidden', 'true');
  phone.removeAttribute('role'); phone.removeAttribute('aria-label');
  if (alt) alt.hidden = false;

  const btn = document.createElement('button');
  btn.type = 'button'; btn.className = 'hero-ctl';
  // the label follows the language toggle (html[data-sms], CSS shows one of the two spans)
  const LAB = { en: ['Pause', 'Play'], sw: ['Simamisha', 'Cheza'] };
  const label = () => { btn.innerHTML = `<span data-l="en">${LAB.en[+paused]}</span><span data-l="sw" lang="sw">${LAB.sw[+paused]}</span>`; };
  label();
  btn.addEventListener('click', () => { paused = !paused; label(); });
  fig.appendChild(btn);

  const running = () => !paused && inView && !document.hidden;
  const wait = (ms, my) => new Promise((res) => {
    let left = ms;
    const t = () => { if (my !== token) return res(false); if (running()) left -= 100; if (left <= 0) return res(true); setTimeout(t, 100); };
    t();
  });
  const typing = document.createElement('li');
  typing.className = 'msg msg-in msg-typing'; typing.setAttribute('aria-hidden', 'true');
  typing.innerHTML = '<p><i></i><i></i><i></i></p>';
  const toEnd = () => { thread.scrollTop = thread.scrollHeight; };   // N6-05: instant, so scrolling never records layout shift
  const reset = () => { typing.remove(); items.forEach((li) => { li.hidden = true; li.classList.remove('is-new'); }); thread.scrollTop = 0; };
  const show = (li) => { typing.remove(); li.hidden = false; li.classList.add('is-new'); toEnd(); };
  const type = () => { thread.appendChild(typing); toEnd(); };

  // [wait before, show the typing indicator first]
  const plan = [[700, false], [900, true], [2200, true], [2600, false], [1100, true]];
  const loop = async () => {
    const my = ++token;
    for (;;) {
      reset();
      for (let i = 0; i < items.length; i++) {
        const [gap, typed] = plan[i];
        if (!(await wait(gap, my))) return;
        if (typed && items[i].classList.contains('msg-in')) { type(); if (!(await wait(i === 1 ? 1200 : 1400, my))) return; }
        show(items[i]);
      }
      if (!(await wait(6000, my))) return;
    }
  };
  fig.classList.add('playing');
  if ('IntersectionObserver' in window) new IntersectionObserver((es) => { inView = es[es.length - 1].isIntersecting; }, { threshold: 0.2 }).observe(fig);
  calm.addEventListener?.('change', () => { if (calm.matches) { token++; typing.remove(); items.forEach((li) => { li.hidden = false; li.classList.remove('is-new'); }); fig.classList.remove('playing'); phone.removeAttribute('aria-hidden'); if (alt) alt.hidden = true; btn.remove(); } });
  loop();
}
