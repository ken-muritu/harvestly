// One place for site-wide constants. Everything that prints the contact address or the site origin imports it from here.
export const ORIGIN = 'https://harvestly-roan.vercel.app';
// Contact address used on every page (footer, calls to action, mailto links).
export const CONTACT_EMAIL = 'harvestlyafrica@gmail.com';
export const LAST_CHECKED = '12 October 2026';
// The three Tally forms (plain links that open in a new tab; nothing is embedded, the CSP stays strict).
export const FORMS = {
  farmer: { url: 'https://tally.so/r/D4rAxR', label: 'Join the Harvestly interest list' },
  partner: { url: 'https://tally.so/r/lboKYk', label: 'Partner with Harvestly' },
  team: { url: 'https://tally.so/r/RGXvb9', label: 'Talk to the Harvestly team' },
};
