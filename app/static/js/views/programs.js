// Bereich Programme: installierte Programme, Entfernen mit Vorschau und PIN.
// Ablauf: "Entfernen" -> Vorschau (der Pi rechnet aus, was mitgeht) -> PIN -> Entfernen -> Ergebnis.
import { api } from '../api.js';
import { el, lamp } from '../dom.js';
import { ago, bytes, int, now } from '../format.js';
import { isActive, taskView } from './tasks.js';

const same = (a, b) => a && b && a.type === b.type && a.name === b.name;

export function createPrograms(host, ctx) {
  const ui = { query: '', showProtected: false, open: null, pinOpen: false, removeId: null, previewId: null };
  let inv = null;
  let lastDevice = null;

  const search = el('input', { class: 'search', type: 'search', placeholder: 'Programm suchen', 'aria-label': 'Programm suchen',
    oninput: () => { ui.query = search.value.trim().toLowerCase(); renderList(); } });
  const protCheck = el('input', { type: 'checkbox', onchange: () => { ui.showProtected = protCheck.checked; renderList(); } });
  const count = el('span', { class: 'count' });
  const list = el('ul', { class: 'list', 'aria-label': 'Installierte Programme' });
  const section = el('section', { class: 'section', 'aria-labelledby': `prog-${host}` },
    el('h2', { id: `prog-${host}` }, 'Programme', el('span', { class: 'aside', id: `prog-age-${host}` })),
    el('div', { class: 'toolbar' }, search, el('label', { class: 'check' }, protCheck, 'Geschützte zeigen'), count),
    list);

  async function load() {
    try { inv = await api.inventory(host); } catch (e) { inv = inv || { programs: [] }; }
    renderList();
  }

  function startPreview(p) {
    ui.open = p; ui.pinOpen = false; ui.removeId = null; ui.previewId = null;
    renderList();
    api.task(host, 'app-preview', { type: p.type, name: p.name })
      .then(r => { ui.previewId = r.id; ctx.refresh(); })
      .catch(ex => { ui.error = ex.message; renderList(); });
  }

  function close() {
    ui.open = null; ui.pinOpen = false; ui.previewId = null; ui.removeId = null; ui.error = null;
    renderList();
  }

  function panel(p) {
    const t = lastDevice && lastDevice.task;
    if (ui.error) {
      return el('div', { class: 'panel' }, el('div', { class: 'err' }, lamp('crit'), el('span', { text: ui.error })),
        el('div', { class: 'row' }, el('button', { type: 'button', class: 'btn', text: 'Schließen', onclick: close })));
    }
    // Entfernen laeuft oder ist fertig
    if (ui.removeId && t && t.id === ui.removeId) {
      const kids = [taskView(t, { title: `${p.title} entfernen` })];
      if (!isActive(t)) kids.push(el('div', { class: 'row' }, el('button', { type: 'button', class: 'btn', text: 'Schließen', onclick: () => { close(); load(); } })));
      return el('div', { class: 'panel' }, kids);
    }
    // Vorschau
    if (!ui.previewId || !t || t.id !== ui.previewId || isActive(t)) {
      return el('div', { class: 'panel' }, t && t.id === ui.previewId ? taskView(t, { title: 'Vorschau' })
        : el('div', { class: 'task-head' }, el('span', { class: 'spin', 'aria-hidden': 'true' }), el('span', { text: 'Vorschau wird angefordert …' })));
    }
    const data = (t.result && t.result.data) || {};
    if (t.state !== 'done') {
      return el('div', { class: 'panel' }, el('div', { class: 'err' }, lamp('crit'), el('span', { text: (t.result && t.result.text) || 'Vorschau fehlgeschlagen.' })),
        el('div', { class: 'row' }, el('button', { type: 'button', class: 'btn', text: 'Schließen', onclick: close })));
    }
    const pkgs = el('ul', { class: 'pkgs' }, (data.details || (data.packages || []).map(n => ({ name: n }))).map(x =>
      el('li', {}, el('span', {}, el('b', { text: x.name }), x.summary ? ` – ${x.summary}` : ''), el('span', { class: 'num', text: x.size ? bytes(x.size) : '' }))));
    const kids = [el('p', { class: 'lead', text: t.result.text }), pkgs];
    if (data.blocked && data.blocked.length) {
      kids.push(el('p', { class: 'note' }, lamp('warn'), el('span', { text: `Geschützt: ${data.blocked.map(b => `${b.name} (${b.reason})`).join(', ')}` })));
    }
    if (!data.allowed) {
      kids.push(el('div', { class: 'row' }, el('button', { type: 'button', class: 'btn', text: 'Schließen', onclick: close })));
      return el('div', { class: 'panel' }, kids);
    }
    if (!ctx.status.pin) {
      kids.push(el('p', { class: 'note' }, lamp('info'), el('span', { text: 'Zum Entfernen braucht es eine PIN. Sie ist noch nicht eingerichtet.' })));
      return el('div', { class: 'panel' }, kids);
    }
    const pin = el('input', { class: 'pin', type: 'password', inputmode: 'numeric', autocomplete: 'off', maxlength: 8, 'aria-label': 'PIN', placeholder: 'PIN',
      onfocus: () => { ui.pinOpen = true; } });
    const err = el('div', { class: 'err', role: 'alert' });
    const go = el('button', { type: 'submit', class: 'btn danger primary', text: 'Endgültig entfernen' });
    kids.push(el('p', { text: 'Persönliche Einstellungen im Benutzerordner bleiben erhalten.' }));
    kids.push(el('form', { class: 'row', onsubmit: async e => {
      e.preventDefault();
      go.disabled = true;
      try {
        const r = await api.task(host, 'app-remove', { type: p.type, name: p.name, preview: t.id }, pin.value);
        ui.removeId = r.id; ui.pinOpen = false;
        ctx.refresh();
      } catch (ex) {
        err.replaceChildren(lamp('crit'), el('span', { text: ex.message }));
        go.disabled = false;
        pin.select();
      }
    } }, pin, go, el('button', { type: 'button', class: 'btn quiet', text: 'Abbrechen', onclick: close })));
    kids.push(err);
    return el('div', { class: 'panel' }, kids);
  }

  function renderList() {
    if (ui.pinOpen) return; // PIN-Feld offen: nicht ueberschreiben
    const progs = (inv && inv.programs) || [];
    const busy = lastDevice && isActive(lastDevice.task);
    const shown = progs.filter(p => (ui.showProtected || !p.protected || same(p, ui.open))
      && (!ui.query || `${p.title} ${p.name} ${p.summary}`.toLowerCase().includes(ui.query)));
    const hidden = progs.filter(p => p.protected).length;
    count.textContent = `${int(shown.length)} von ${int(progs.length)} Programmen${!ui.showProtected && hidden ? `, ${int(hidden)} geschützte ausgeblendet` : ''}`;
    const age = document.getElementById(`prog-age-${host}`);
    if (age) age.textContent = inv && inv.updated ? `Liste ${ago(now() - inv.updated)}` : '';
    if (!inv) { list.replaceChildren(el('li', { text: 'Lade …' })); return; }
    if (!progs.length) { list.replaceChildren(el('li', { class: 'note', text: 'Keine Programme gemeldet. Der Agent schickt die Liste einmal pro Stunde.' })); return; }
    list.replaceChildren(...shown.map(p => {
      const isOpen = same(p, ui.open);
      return el('li', {},
        el('div', { class: 'row-main' },
          p.protected ? lamp('info', 'Geschützt') : el('span', { 'aria-hidden': 'true' }),
          el('span', { class: 'row-title' }, p.title, p.type === 'flatpak' ? el('span', { class: 'pill', text: 'Flatpak' }) : null),
          el('span', { class: 'row-actions' },
            el('span', { class: 'row-side num', text: p.size ? bytes(p.size) : '' }),
            p.protected ? el('span', { class: 'row-side', text: 'geschützt' })
              : el('button', { type: 'button', class: 'btn', disabled: (busy && !isOpen) || isOpen, text: 'Entfernen …', onclick: () => startPreview(p) })),
          el('span', { class: 'row-sub', text: p.protected ? p.reason : [p.summary, p.name !== p.title ? p.name : null].filter(Boolean).join(' – ') })),
        isOpen ? panel(p) : null);
    }));
  }

  return {
    section,
    load,
    update(d) {
      const before = lastDevice && lastDevice.task;
      lastDevice = d;
      const t = d.task;
      if (ui.removeId && t && t.id === ui.removeId && !isActive(t) && before && isActive(before)) load();
      renderList();
    },
    waiting: () => !!ui.open && !ui.pinOpen,
  };
}
