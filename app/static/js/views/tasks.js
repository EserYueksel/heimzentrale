// Auftraege (Update, Vorschau, Entfernen): Fortschritt waehrend sie laufen, danach eine kurze Ergebniszeile.
import { el, lamp } from '../dom.js';
import { clock, now, when } from '../format.js';

export const ACTIVE = ['requested', 'claimed', 'running'];
const STATE_WORD = { requested: 'Wartet auf den Pi', claimed: 'Abgeholt', running: 'Läuft', done: 'Fertig', failed: 'Fehlgeschlagen', cancelled: 'Zurückgezogen' };
const RESULT_WORD = { done: 'abgeschlossen', failed: 'fehlgeschlagen', cancelled: 'zurückgezogen' };
// So lange bleibt die Ergebniszeile stehen (Sekunden) - ein Fehler am laengsten
const RESULT_FOR = { done: 24 * 3600, cancelled: 3600, failed: 7 * 86400 };
const HIDDEN_KEY = 'hz-hidden-tasks';

export const isActive = t => !!t && ACTIVE.includes(t.state);
const level = t => (t.state === 'done' ? 'ok' : t.state === 'cancelled' ? 'info' : 'crit');

function steps(log) {
  return el('ol', { class: 'steps', 'aria-label': 'Ablauf' }, log.map((e, i) => el('li', { class: i === log.length - 1 ? 'last' : null },
    lamp(e.state === 'failed' ? 'crit' : e.state === 'done' ? 'ok' : 'info'),
    el('time', { text: clock(e.ts) }), el('span', { text: e.text }))));
}

export function taskView(t, { title, onCancel } = {}) {
  const active = isActive(t);
  const icon = active ? el('span', { class: 'spin', 'aria-hidden': 'true' }) : lamp(level(t), STATE_WORD[t.state]);
  const kids = [el('div', { class: 'task-head' }, icon,
    el('span', {}, el('strong', { text: `${title || t.title}: ${STATE_WORD[t.state] || t.state}` }),
      t.state === 'requested' ? ' – der Pi holt den Auftrag innerhalb von 1 bis 2 Minuten ab.' : ''))];
  kids.push(steps(t.log || []));
  if (t.state === 'requested' && onCancel) {
    kids.push(el('div', {}, el('button', { type: 'button', class: 'btn', text: 'Auftrag zurückziehen', onclick: onCancel })));
  }
  return el('div', { class: 'task', 'aria-live': 'polite' }, kids);
}

// Ausgeblendete Ergebnisse merkt sich nur dieser Browser
function hiddenIds() {
  try { return JSON.parse(localStorage.getItem(HIDDEN_KEY) || '[]'); } catch (e) { return []; }
}

export function hideResult(id) {
  try { localStorage.setItem(HIDDEN_KEY, JSON.stringify([id, ...hiddenIds().filter(x => x !== id)].slice(0, 30))); } catch (e) { /* egal */ }
}

export function showResult(t) {
  if (!t || isActive(t) || hiddenIds().includes(t.id)) return false;
  return now() - t.updated < (RESULT_FOR[t.state] || 0);
}

// Abgeschlossener Auftrag als eine Zeile; der Ablauf bleibt zum Aufklappen da.
export function taskResult(t, { title, onHide } = {}) {
  const log = t.log || [];
  const reason = t.state === 'failed' && t.result && t.result.text ? t.result.text : null;
  return el('div', { class: 'offer task-result' },
    el('div', { class: 'o-text' }, lamp(level(t), STATE_WORD[t.state]),
      el('strong', { text: `${title || t.title} ${RESULT_WORD[t.state] || t.state}` }),
      el('span', { class: 'o-sub', text: when(t.updated) }),
      reason ? el('span', { class: 'o-sub', text: reason }) : null,
      log.length ? el('details', { class: 'o-sub' }, el('summary', { text: `Ablauf ansehen (${log.length} Schritte)` }), steps(log)) : null),
    onHide ? el('button', { type: 'button', class: 'btn quiet', text: 'Ausblenden', onclick: onHide }) : null);
}
