// Gemeinsame Teile fuer Uebersicht und Detailseite.
import { el, lamp } from '../dom.js';
import { GiB, dec1, gb, int } from '../format.js';

const ORDER = { ok: 0, info: 1, warn: 2, crit: 3 };
export const LEVEL_WORD = { ok: 'In Ordnung', info: 'Hinweis', warn: 'Achtung', crit: 'Problem', off: 'Keine Meldung' };

// Gesamtzustand eines Pi: meldet er sich nicht -> crit; sonst der schlimmste Befund (Hinweise zaehlen als ok)
export function deviceLevel(d) {
  if (!d.online) return 'crit';
  let w = 'ok';
  for (const f of d.findings) if (ORDER[f.level] > ORDER[w]) w = f.level;
  return w === 'info' ? 'ok' : w;
}

export function worstLevel(levels) {
  return levels.reduce((w, l) => (ORDER[l] > ORDER[w] ? l : w), 'ok');
}

export function modelShort(m) {
  const model = (m.model || '').replace(/ Model B| Rev [\d.]+/g, '').trim();
  const ram = m.mem_total ? `${Math.round(m.mem_total / GiB)} GB` : null;
  return [model || null, ram].filter(Boolean).join(', ');
}

export function roleText(m) {
  const roles = [];
  if (m.has_bitcoin) roles.push('Bitcoin Full Node');
  if (m.docker) roles.push(`${int(m.docker.length)} Docker-Apps`);
  return roles.join(' und ');
}

function scale(pctValue, fill) {
  const on = Math.round(Math.max(0, Math.min(100, pctValue ?? 0)) / 5);
  return el('div', { class: 'scale', style: fill ? `--fill:${fill}` : null, 'aria-hidden': 'true' },
    Array.from({ length: 20 }, (_, i) => el('i', { class: i < on ? 'on' : null })));
}

const FILL = { ok: null, warn: 'var(--warning)', crit: 'var(--critical)' };

// Eine Messskala: Beschriftung, 20 Segmente, Wert
export function gauge(label, pctValue, valueNode, level, big) {
  const known = pctValue != null;
  return el('div', { class: `gauge${big ? ' big' : ''}`, role: 'group', 'aria-label': label },
    el('span', { class: 'g-label', text: label }),
    el('span', { class: 'g-value' }, valueNode),
    known ? scale(pctValue, FILL[level] || null) : el('span', { class: 'g-none', text: 'keine Daten' }));
}

// Die vier Grundwerte jedes Pi
export function gauges(m, t, big) {
  const cpuLevel = m.cpu_pct != null && m.cpu_pct >= t.CPU_WARN ? 'warn' : 'ok';
  const memLevel = m.mem_pct != null && m.mem_pct >= t.MEM_WARN ? 'warn' : 'ok';
  const avail = m.disk_avail;
  const diskLevel = avail == null ? 'ok' : avail < t.DISK_CRIT_GB * GiB ? 'crit' : avail < t.DISK_WARN_GB * GiB ? 'warn' : 'ok';
  const diskPct = m.disk_size ? (m.disk_used / m.disk_size) * 100 : null;
  const tempLevel = m.temp == null ? 'ok' : m.temp >= t.TEMP_CRIT ? 'crit' : m.temp >= t.TEMP_WARN ? 'warn' : 'ok';
  return el('div', { class: 'gauges' },
    gauge('Prozessor', m.cpu_pct, m.cpu_pct == null ? '–' : `${int(m.cpu_pct)} %`, cpuLevel, big),
    gauge('Arbeitsspeicher', m.mem_pct, m.mem_pct == null ? '–' : `${int(m.mem_pct)} %`, memLevel, big),
    gauge('Speicherplatz', diskPct, [gb(avail), ' ', el('small', { text: 'frei' })], diskLevel, big),
    gauge('Temperatur', m.temp == null ? null : (m.temp / 85) * 100, m.temp == null ? '–' : `${dec1(m.temp)} °C`, tempLevel, big));
}

export function findingsList(findings, opts = {}) {
  const items = opts.limit ? findings.slice(0, opts.limit) : findings;
  const ul = el('ul', { class: `findings${opts.roomy ? ' roomy' : ''}` }, items.map(f => el('li', {},
    lamp(f.level, LEVEL_WORD[f.level]), el('strong', { text: f.title }),
    opts.roomy ? el('span', { class: 'ftext', text: f.text }) : null,
    opts.roomy && f.notified ? el('span', { class: 'ftag', text: 'Aufs Handy gemeldet' }) : null)));
  if (opts.limit && findings.length > opts.limit) {
    ul.append(el('li', {}, el('span'), el('span', { class: 'ftext', text: `und ${findings.length - opts.limit} weitere` })));
  }
  return ul;
}
