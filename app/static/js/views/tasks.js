// Fortschritt eines Auftrags (Update, Vorschau, Entfernen).
import { el, lamp } from '../dom.js';
import { clock } from '../format.js';

export const ACTIVE = ['requested', 'claimed', 'running'];
const STATE_WORD = { requested: 'Wartet auf den Pi', claimed: 'Abgeholt', running: 'Läuft', done: 'Fertig', failed: 'Fehlgeschlagen', cancelled: 'Zurückgezogen' };

export const isActive = t => !!t && ACTIVE.includes(t.state);

export function taskView(t, { title, onCancel } = {}) {
  const active = isActive(t);
  const icon = active ? el('span', { class: 'spin', 'aria-hidden': 'true' })
    : lamp(t.state === 'done' ? 'ok' : t.state === 'cancelled' ? 'info' : 'crit', STATE_WORD[t.state]);
  const kids = [el('div', { class: 'task-head' }, icon,
    el('span', {}, el('strong', { text: `${title || t.title}: ${STATE_WORD[t.state] || t.state}` }),
      t.state === 'requested' ? ' – der Pi holt den Auftrag innerhalb von 1 bis 2 Minuten ab.' : ''))];
  const log = t.log || [];
  kids.push(el('ol', { class: 'steps', 'aria-label': 'Ablauf' }, log.map((e, i) => el('li', { class: i === log.length - 1 ? 'last' : null },
    lamp(e.state === 'failed' ? 'crit' : e.state === 'done' ? 'ok' : 'info'),
    el('time', { text: clock(e.ts) }), el('span', { text: e.text })))));
  if (t.state === 'requested' && onCancel) {
    kids.push(el('div', {}, el('button', { type: 'button', class: 'btn', text: 'Auftrag zurückziehen', onclick: onCancel })));
  }
  return el('div', { class: 'task', 'aria-live': 'polite' }, kids);
}
