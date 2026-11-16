// Bereich Bitcoin auf der Detailseite: Kennzahlen und Bitcoin-Core-Update.
import { api } from '../api.js';
import { el, lamp } from '../dom.js';
import { ago, bytes, dec2, duration, int, now } from '../format.js';
import { hideResult, isActive, showResult, taskResult, taskView } from './tasks.js';

function figure(label, value, unit, lines) {
  return el('div', { class: 'figure' },
    el('div', { class: 'f-label', text: label }),
    el('div', { class: 'f-value num' }, value, unit ? el('small', { text: unit }) : null),
    lines.filter(Boolean).map(l => (Array.isArray(l)
      ? el('div', { class: 'f-line' }, lamp(l[0]), el('span', { text: l[1] }))
      : el('div', { class: 'f-line', text: l }))));
}

export function bitcoinFigures(d) {
  const m = d.metrics;
  const behind = d.derived.behind;
  const height = [];
  if (m.ibd) height.push(`Synchronisiert: ${dec2((m.verification || 0) * 100)} %`);
  else if (behind != null) height.push(behind <= 1 ? ['ok', 'auf dem Stand des Netzes'] : ['warn', `${int(behind)} Blöcke hinter dem Netz`]);
  else height.push('Netz-Blockhöhe gerade nicht abrufbar');
  if (m.block_time) height.push(`Letzter Block ${ago(now() - m.block_time)}`);
  const ver = m.core_installed ? `Bitcoin Core ${m.core_installed}` : null;
  return el('div', { class: 'figures' },
    figure('Blockhöhe', m.height != null ? int(m.height) : '–', null, height),
    figure('Verbindungen', m.peers != null ? int(m.peers) : '–', null, [
      m.peers_out != null ? `${int(m.peers_out)} ausgehend, ${int(m.peers_in || 0)} eingehend` : null,
      m.peers_in === 0 ? 'Eingehend 0 ist normal ohne Portweiterleitung am Router' : null]),
    figure('Mempool', m.mempool_tx != null ? int(m.mempool_tx) : '–', 'Transaktionen', [
      m.mempool_bytes != null ? `${bytes(m.mempool_bytes)} an Daten` : null,
      m.mempool_usage != null && m.mempool_max ? `Speicher ${int(m.mempool_usage / 1e6)} von ${int(m.mempool_max / 1e6)} MB` : null]),
    figure('Node läuft seit', duration(m.node_uptime_s), null, [ver,
      m.size_on_disk ? `Blockchain ${bytes(m.size_on_disk)}` : null]));
}

// Bitcoin-Core-Update: Angebote, PIN-Abfrage, Fortschritt
export function coreBlock(box, d, ui, ctx) {
  if (ui.coreConfirm) return; // PIN-Feld offen: nicht ueberschreiben
  const core = d.core;
  const kids = [];
  const task = d.task && d.task.kind === 'core-update' ? d.task : null;
  const title = task ? `Update ${task.params.from ? `${task.params.from} → ` : 'auf '}${task.params.version}` : '';
  if (isActive(task)) {
    kids.push(taskView(task, { title, onCancel: async () => { await api.cancel(d.host).catch(() => null); ctx.refresh(); } }));
  } else if (showResult(task)) {
    kids.push(taskResult(task, { title, onHide: () => { hideResult(task.id); ctx.render(); } }));
  }
  if (!isActive(task)) {
    if (core.offers.length) {
      for (const o of core.offers) {
        kids.push(el('div', { class: 'offer' },
          el('div', { class: 'o-text' }, lamp(o.major ? 'warn' : 'info'),
            el('span', {}, el('strong', { text: `Version ${o.version} ist verfügbar` }), '. ',
              el('a', { href: o.notes, target: '_blank', rel: 'noopener noreferrer', text: 'Release Notes lesen' })),
            el('span', { class: 'o-sub', text: o.major ? 'Großer Versionssprung: vorher die Release Notes lesen.' : 'Gleiche Reihe wie deine Version, vor allem Fehlerbehebungen.' })),
          el('button', { type: 'button', class: 'btn', disabled: !ctx.status.pin, text: `Auf ${o.version} aktualisieren`,
            onclick: () => { ui.coreConfirm = o; openConfirm(box, d, o, ui, ctx); } })));
      }
      if (!ctx.status.pin) kids.push(el('p', { class: 'note' }, lamp('info'), el('span', { text: 'Der Knopf ist gesperrt, bis eine PIN eingerichtet ist (Anleitung im LIESMICH).' })));
    } else if (core.checked) {
      kids.push(el('p', { class: 'note' }, lamp('ok'), el('span', { text: `Bitcoin Core ${core.installed || ''} ist aktuell. Geprüft ${ago(now() - core.checked)}.` })));
    } else {
      kids.push(el('p', { class: 'note' }, lamp('info'), el('span', { text: core.error ? `Versionsliste gerade nicht abrufbar (${core.error}).` : 'Versionsliste wird geladen …' })));
    }
  }
  box.replaceChildren(...kids);
}

function openConfirm(box, d, o, ui, ctx) {
  const pin = el('input', { class: 'pin', type: 'password', inputmode: 'numeric', autocomplete: 'off', maxlength: 8, 'aria-label': 'PIN', placeholder: 'PIN' });
  const err = el('div', { class: 'err', role: 'alert' });
  const go = el('button', { type: 'submit', class: 'btn primary', text: `Auf ${o.version} aktualisieren` });
  const close = () => { ui.coreConfirm = null; ctx.render(); };
  const form = el('form', { class: 'panel', onsubmit: async e => {
    e.preventDefault();
    go.disabled = true;
    err.replaceChildren();
    try {
      await api.task(d.host, 'core-update', { version: o.version }, pin.value);
      ui.coreConfirm = null;
      ctx.refresh();
    } catch (ex) {
      err.replaceChildren(lamp('crit'), el('span', { text: ex.message }));
      go.disabled = false;
      pin.select();
    }
  } },
  el('p', { class: 'lead', text: `Bitcoin Core von ${d.core.installed} auf ${o.version} aktualisieren?` }),
  el('p', { text: `Der ${d.host} lädt die neue Version von bitcoincore.org, prüft Prüfsumme und Signaturen der Entwickler und tauscht dann das Programm aus. Der Node ist dabei ein paar Minuten aus. Geht etwas schief, läuft die alte Version weiter.` }),
  o.major ? el('p', { class: 'note' }, lamp('warn'), el('span', { text: 'Großer Versionssprung. Lies vorher die Release Notes, ob du Einstellungen ändern musst.' })) : null,
  el('div', { class: 'row' }, pin, go, el('button', { type: 'button', class: 'btn quiet', text: 'Abbrechen', onclick: close })),
  err);
  box.replaceChildren(form);
  pin.focus();
}
