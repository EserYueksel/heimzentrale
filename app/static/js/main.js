// Heimzentrale – Start, Navigation (#/ und #/pi/NAME), regelmaessiges Nachladen.
import { api } from './api.js';
import { el, icon, lamp, toast } from './dom.js';
import { ago, now } from './format.js';
import { themeButton } from './theme.js';
import { createDeviceView } from './views/device.js';
import { renderOverview } from './views/overview.js';

const main = document.getElementById('main');
const foot = document.getElementById('foot');
const ctx = { status: null, refresh: () => load(), render: () => render() };
let view = null; // { host, device } fuer die Detailseite
let timer = null;
let failed = false;

// ---------------------------------------------------------------- Kopfzeile
function brandMark() {
  // Bildmarke: Modul mit Lampe
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 30 30');
  s.setAttribute('class', 'brand-mark');
  s.setAttribute('aria-hidden', 'true');
  s.innerHTML = '<rect x="1.5" y="3.5" width="27" height="23" rx="5" fill="none" stroke="currentColor" stroke-width="2"/>'
    + '<circle cx="9" cy="11" r="3" fill="var(--good)"/><path d="M15 11h8M7 18h16M7 22h11" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>';
  return s;
}

function header() {
  const bar = document.getElementById('topbar');
  bar.replaceChildren(
    el('a', { class: 'brand', href: '#/' }, brandMark(), el('span', { class: 'brand-name', text: 'Heimzentrale' })),
    el('div', { class: 'topbar-actions' },
      el('button', { type: 'button', class: 'btn', onclick: openConnect }, icon('plus'), el('span', { class: 'btn-label', text: 'Pi hinzufügen' })),
      themeButton()));
}

// ---------------------------------------------------------------- Pi hinzufuegen
function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
  const ta = el('textarea', { style: 'position:fixed;opacity:0' });
  ta.value = text;
  document.body.append(ta);
  ta.select();
  const ok = document.execCommand('copy');
  ta.remove();
  return ok ? Promise.resolve() : Promise.reject(new Error('Kopieren nicht möglich'));
}

function openConnect() {
  const dlg = el('dialog', { 'aria-labelledby': 'connect-title' });
  const pin = el('input', { class: 'pin', type: 'password', inputmode: 'numeric', autocomplete: 'off', maxlength: 8, 'aria-label': 'PIN', placeholder: 'PIN' });
  const err = el('div', { class: 'err', role: 'alert' });
  const body = el('div');
  const close = () => { dlg.close(); dlg.remove(); };
  const form = el('form', { onsubmit: async e => {
    e.preventDefault();
    err.replaceChildren();
    try {
      const r = await api.connect(pin.value);
      const code = el('code', { class: 'code', text: r.command });
      body.replaceChildren(
        el('p', { text: 'Auf dem neuen Pi im Terminal diesen Befehl eingeben. Er installiert den Agenten und meldet den Pi hier an.' }),
        code,
        el('ol', {}, el('li', { text: 'Der Pi muss im selben Heimnetz sein.' }),
          el('li', { text: 'Danach erscheint er innerhalb von 5 Minuten in der Übersicht.' }),
          r.url.includes('ADRESSE') ? el('li', { text: 'Ersetze ADRESSE-DER-HEIMZENTRALE durch die Adresse dieses Pi (oder trag PUBLIC_URL in heimzentrale.conf ein).' }) : null),
        el('p', { text: 'Der Befehl enthält den Schlüssel der Heimzentrale. Gib ihn nicht weiter.' }),
        el('div', { class: 'dialog-actions' },
          el('button', { type: 'button', class: 'btn primary', onclick: () => copyText(r.command).then(() => toast('Befehl kopiert')).catch(() => toast('Bitte von Hand markieren und kopieren')) }, icon('copy'), 'Befehl kopieren'),
          el('button', { type: 'button', class: 'btn', text: 'Schließen', onclick: close })));
    } catch (ex) {
      err.replaceChildren(lamp('crit'), el('span', { text: ex.message }));
      pin.select();
    }
  } },
  el('p', { text: 'Jeder weitere Raspberry Pi mit Raspberry Pi OS oder Debian bekommt einen kleinen Agenten. Er meldet seine Werte hierher und führt Aufträge aus. Zum Anzeigen des Befehls bitte die PIN eingeben.' }),
  el('div', { class: 'row', style: 'display:flex;gap:8px;flex-wrap:wrap' }, pin,
    el('button', { type: 'submit', class: 'btn primary', text: 'Befehl anzeigen' }),
    el('button', { type: 'button', class: 'btn quiet', text: 'Abbrechen', onclick: close })),
  err);
  body.append(form);
  dlg.append(el('h2', { id: 'connect-title', text: 'Pi hinzufügen' }), body);
  dlg.addEventListener('cancel', () => setTimeout(() => dlg.remove(), 0));
  document.body.append(dlg);
  dlg.showModal();
  pin.focus();
}

// ---------------------------------------------------------------- Navigation und Darstellung
function route() {
  const m = location.hash.match(/^#\/pi\/([^/]+)$/);
  return m ? decodeURIComponent(m[1]) : null;
}

function render() {
  const s = ctx.status;
  if (!s) return;
  const host = route();
  if (!host) {
    view = null;
    renderOverview(main, s);
    document.title = 'Heimzentrale';
  } else {
    const d = s.devices.find(x => x.host === host);
    if (!d) {
      view = null;
      main.replaceChildren(el('a', { class: 'back', href: '#/' }, icon('back'), 'Alle Pis'),
        el('section', { class: 'verdict' }, lamp('info'), el('h1', { text: `Vom „${host}“ ist keine Meldung da.` })));
    } else {
      if (!view || view.host !== host) {
        view = { host, device: createDeviceView(host, ctx) };
        main.replaceChildren(view.device.root);
        window.scrollTo(0, 0);
      }
      view.device.update(d, s);
      document.title = `${host} – Heimzentrale`;
    }
  }
  renderFoot(s);
}

function renderFoot(s) {
  const n = s.network;
  foot.replaceChildren(
    el('span', { text: `Heimzentrale ${s.version}` }),
    el('span', { text: failed ? 'Keine Verbindung zur Heimzentrale – zeige den letzten Stand.' : `Aktualisiert ${ago(now() - s.now)}` }),
    el('span', { text: n.tip ? `Netz-Blockhöhe von ${n.source}` : '' }),
    el('span', { text: s.ntfy ? 'Handy-Meldungen eingerichtet' : 'Handy-Meldungen nicht eingerichtet' }),
    el('span', { text: s.pin ? 'PIN eingerichtet' : 'Keine PIN eingerichtet' }));
}

async function load() {
  clearTimeout(timer);
  try {
    ctx.status = await api.status();
    failed = false;
  } catch (e) {
    failed = true;
    if (!ctx.status) main.replaceChildren(el('section', { class: 'verdict' }, lamp('crit'), el('h1', { text: 'Die Heimzentrale antwortet nicht.' })));
  }
  render();
  const busy = ctx.status && (ctx.status.devices.some(d => d.task && ['requested', 'claimed', 'running'].includes(d.task.state))
    || (view && view.device.busy()));
  timer = setTimeout(load, busy ? 4000 : 20000);
}

let resizeTimer;
window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => view && view.device.redraw(), 150); });
window.addEventListener('hashchange', render);
document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });
setInterval(() => { if (view) view.device.reloadHistory(); }, 300000);
setInterval(() => document.querySelectorAll('[data-received]').forEach(n => { n.textContent = ago(now() - Number(n.dataset.received)); }), 15000);

header();
load();
