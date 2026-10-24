// Runs before first paint (classic script, in <head>): marks the page as scripted (so the no-JS view can hide dead controls) and applies a saved theme choice so there is no flash.
document.documentElement.classList.add('js');
try { var t = localStorage.getItem('hv-theme'); if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t); } catch (e) { /* storage blocked: follow the system */ }
