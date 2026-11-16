// Umschalter Hell/Dunkel. Ohne Wahl gilt die Systemeinstellung; die Wahl wird im Browser gemerkt.
import { el, icon } from './dom.js';

const query = window.matchMedia('(prefers-color-scheme: dark)');
const current = () => document.documentElement.dataset.theme || (query.matches ? 'dark' : 'light');

export function themeButton() {
  const b = el('button', { type: 'button', class: 'btn quiet', id: 'theme' });
  const paint = () => {
    const dark = current() === 'dark';
    b.replaceChildren(icon(dark ? 'sun' : 'moon'), el('span', { class: 'btn-label', text: dark ? 'Hell' : 'Dunkel' }));
    b.setAttribute('aria-label', dark ? 'Helles Design einschalten' : 'Dunkles Design einschalten');
    b.title = b.getAttribute('aria-label');
  };
  b.addEventListener('click', () => {
    const next = current() === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('hz-theme', next); } catch (e) { /* egal */ }
    paint();
  });
  query.addEventListener('change', paint);
  paint();
  return b;
}
