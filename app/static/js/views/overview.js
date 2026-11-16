// Uebersicht: die Antwort auf "Ist alles in Ordnung?" und alle Pis als Module.
import { el, lamp } from '../dom.js';
import { ago, int, now } from '../format.js';
import { LEVEL_WORD, deviceLevel, findingsList, gauges, modelShort, roleText, worstLevel } from './common.js';

function verdict(s) {
  const devices = s.devices;
  if (!devices.length) {
    return { level: 'info', title: 'Noch kein Pi meldet sich.',
      sub: ['Binde deinen ersten Pi über „Pi hinzufügen“ an.'] };
  }
  const troubled = devices.filter(d => deviceLevel(d) !== 'ok');
  const level = worstLevel(devices.map(deviceLevel));
  if (!troubled.length) {
    return { level: 'ok', title: 'Alles in Ordnung.',
      sub: [devices.length === 1 ? 'Dein Pi meldet sich regelmäßig.' : `Alle ${int(devices.length)} Pis melden sich regelmäßig.`] };
  }
  if (troubled.length === 1) {
    const d = troubled[0];
    const first = d.online ? d.findings.find(f => f.level !== 'info') : null;
    return { level, title: `${d.host}: ${first ? first.title : 'meldet sich nicht'}.`, sub: [first ? first.text : ''] };
  }
  return { level, title: `${int(troubled.length)} Pis brauchen Aufmerksamkeit.`,
    sub: [troubled.map(d => d.host).join(', ')] };
}

function moduleCard(d, s) {
  const m = d.metrics;
  const level = deviceLevel(d);
  const relevant = d.findings.filter(f => f.level !== 'info' || !d.online);
  let foot = '';
  if (m.has_bitcoin && m.height != null) {
    const behind = d.derived.behind;
    foot = `Block ${int(m.height)}${behind == null ? '' : behind <= 1 ? ', auf dem Stand des Netzes' : `, ${int(behind)} hinter dem Netz`}`;
  } else if (m.docker) {
    const running = m.docker.filter(c => c.state === 'running').length;
    foot = `${int(running)} von ${int(m.docker.length)} Apps laufen`;
  } else if (m.uptime_s != null) {
    foot = `Läuft seit ${Math.floor(m.uptime_s / 86400)} Tagen`;
  }
  return el('a', { class: `module${d.online ? '' : ' offline'}`, href: `#/pi/${encodeURIComponent(d.host)}`,
    'aria-label': `${d.host}: ${LEVEL_WORD[level]}. Details öffnen.` },
    el('div', { class: 'module-head' },
      lamp(d.online ? level : 'off', LEVEL_WORD[d.online ? level : 'off']),
      el('h2', { text: d.host }),
      el('span', { class: 'seen', 'data-received': d.received, text: ago(now() - d.received) }),
      el('span', { class: 'role', text: [roleText(m), modelShort(m)].filter(Boolean).join(', ') })),
    el('div', { class: 'module-body' },
      gauges(m, s.thresholds, false),
      relevant.length ? findingsList(relevant, { limit: 2 }) : null),
    el('div', { class: 'module-foot' }, el('span', { text: foot }), el('span', { class: 'open', text: 'Details' })));
}

export function renderOverview(root, s) {
  const v = verdict(s);
  root.replaceChildren(
    el('section', { class: 'verdict', 'aria-live': 'polite' }, lamp(v.level, LEVEL_WORD[v.level]), el('h1', { text: v.title })),
    el('p', { class: 'verdict-sub', text: v.sub.filter(Boolean).join(' ') }),
    el('div', { class: 'wall' }, s.devices.map(d => moduleCard(d, s))));
}
