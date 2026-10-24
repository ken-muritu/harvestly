// Reusable HTML fragments built from the engine's own data (site/assets/js/data.js).
import { SCENARIOS } from '../../site/assets/js/data.js';
import { dialSvg } from '../../site/assets/js/dial.js';
import { esc } from './lib.mjs';

export const SC = Object.fromEntries(SCENARIOS.map((s) => [s.name, s]));

export const fmtDate = (iso, opts = { day: 'numeric', month: 'short' }) =>
  new Date(iso + 'T12:00:00Z').toLocaleDateString('en-GB', { timeZone: 'UTC', ...opts });

/** Both languages of a string, toggled by html[data-sms]. */
export const bi = (en, sw) => `<span data-l="en">${esc(en)}</span><span data-l="sw" lang="sw">${esc(sw)}</span>`;

/** One SMS bubble. dir 'in' = Harvestly to farmer, 'out' = farmer reply. */
export const bubble = (dir, en, sw, meta = '') =>
  `<li class="msg msg-${dir}"><p>${bi(en, sw)}</p>${meta ? `<span class="msg-meta">${Array.isArray(meta) ? bi(meta[0], meta[1]) : esc(meta)}</span>` : ''}</li>`;

/** Language toggle for message text (JS wires it; without JS English shows). */
export const langToggle = (id = '', note = true) => `<div class="seg-wrap"><div class="seg" role="group" aria-label="Language of the messages"${id ? ` id="${id}"` : ''}>
  <button type="button" data-sms="en" aria-pressed="true">English</button><button type="button" data-sms="sw" aria-pressed="false" lang="sw">Kiswahili</button></div>${note ? '<span class="seg-note">Kiswahili is a draft, not yet reviewed by a native speaker.</span>' : ''}</div>`;

const SIGNAL = '<svg viewBox="0 0 16 12" width="16" height="12" aria-hidden="true" focusable="false"><path d="M1 11h2V8H1zM5 11h2V6H5zM9 11h2V3H9zM13 11h2V1h-2z" fill="currentColor"/></svg>';
const BATTERY = '<svg viewBox="0 0 24 12" width="24" height="12" aria-hidden="true" focusable="false"><rect x="1" y="1.5" width="19" height="9" rx="2.2" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="3" y="3.5" width="12" height="5" rx="1" fill="currentColor"/><rect x="21" y="4" width="2" height="4" rx="1" fill="currentColor"/></svg>';
export const STATUS_ICONS = `${SIGNAL}${BATTERY}`;
const BACK = '<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false"><path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const DOTS = '<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false"><circle cx="12" cy="5" r="1.8" fill="currentColor"/><circle cx="12" cy="12" r="1.8" fill="currentColor"/><circle cx="12" cy="19" r="1.8" fill="currentColor"/></svg>';

const CALL = '<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false"><path d="M6.6 3.5h3l1.4 4-2 1.4a11 11 0 0 0 5.1 5.1l1.4-2 4 1.4v3a2 2 0 0 1-2.1 2A15.5 15.5 0 0 1 4.6 5.6a2 2 0 0 1 2-2.1z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>';
const PLUS = '<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false"><path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>';
const SEND = '<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false"><path d="M5 12l14-7-4 14-3-6z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>';

/**
 * The one phone used everywhere on the site: an Android handset at real proportion (body 1 : 2.16, about 72 x 155 mm),
 * with bezel, punch-hole camera, status bar, Android messages header, thread, compose bar and gesture bar.
 * Every size is a multiple of --pw (the body width), so it is never stretched or squat; text never falls under 12 px.
 * crop: the story panel on a phone-sized screen shows the top of the same phone, open at the bottom (same width, same type).
 */
export const phone = (inner, { title = 'Harvestly', sub = 'SMS', cls = '', time = '17:04', id = '', threadAttrs = '', label = '' } = {}) => `<div class="phone ${cls}"${id ? ` id="${id}"` : ''}${label ? ` role="group" aria-label="${esc(label)}"` : ''}>
  <div class="phone-screen">
    <div class="ph-status" aria-hidden="true"><span class="ph-time">${time}</span><span class="ph-hole"></span><span class="ph-icons">${STATUS_ICONS}</span></div>
    <div class="phone-head"><span class="ph-ic" aria-hidden="true">${BACK}</span><span class="ph-avatar" aria-hidden="true"><img src="/brand/harvestly-symbol.svg" alt="" width="22" height="26"></span><span class="ph-who"><strong>${esc(title)}</strong><small>${Array.isArray(sub) ? bi(sub[0], sub[1]) : esc(sub)}</small></span><span class="ph-ic ph-call" aria-hidden="true">${CALL}</span><span class="ph-ic" aria-hidden="true">${DOTS}</span></div>
    <ol class="thread"${threadAttrs}>${inner}</ol>
    <div class="ph-compose" aria-hidden="true"><span class="ph-ic">${PLUS}</span><span class="ph-field">${bi('Text message', 'Ujumbe')}</span><span class="ph-ic">${SEND}</span></div>
    <div class="ph-nav" aria-hidden="true"><i></i></div>
  </div>
</div>`;

// ---- the sack: drawn from simple shapes, weave clipped to the body ---------------------------------
const weave = (() => {
  let d = '';
  for (let x = 30; x <= 192; x += 6) d += `M${x} 60V275`;
  for (let y = 66; y <= 275; y += 6) d += `M26 ${y}H196`;
  return d;
})();
const SACK_PATH = 'M76 34C92 42 128 42 144 34C140 56 147 80 170 100C188 132 192 205 184 252C183 262 175 266 164 267C128 272 92 272 56 267C45 266 37 262 36 252C28 205 32 132 50 100C73 80 80 56 76 34Z';
export const SACK_DEFS = `<svg class="defs" width="0" height="0" aria-hidden="true" focusable="false"><symbol id="sack" viewBox="0 0 220 280">
  <clipPath id="sack-clip"><path d="${SACK_PATH}"/></clipPath>
  <path class="sk-body" d="${SACK_PATH}"/>
  <path class="sk-weave" d="${weave}" clip-path="url(#sack-clip)"/>
  <path class="sk-shade" d="M146 98C176 124 190 190 184 252C183 262 175 266 164 267C150 268 142 268 134 268C160 232 164 150 146 98Z"/>
  <path class="sk-tie" d="M74 64C98 73 122 73 146 64"/>
  <path class="sk-knot" d="M106 68c-6 6-8 14-4 20M114 68c6 6 8 14 4 20"/>
  <path class="sk-ear" d="M76 34L68 22L82 30M144 34L152 22L138 30"/>
</symbol></svg>`;
export const sackUse = (cls = '') => `<svg class="sack ${cls}" viewBox="0 0 220 280" aria-hidden="true" focusable="false"><use href="#sack"/></svg>`;

/** Static dial for the hero: `days` on a 60-day scale, lit ticks and the hand. */
export const heroDial = (days) => dialSvg({ ticks: 36, on: Math.round((days / 60) * 36), hand: days / 60, handIn: 60, handOut: 74, level: 'low', cls: 'dial hero-ring' });
