// Detailseite eines Pi: Zustand, Verlauf, Bitcoin, Docker-Apps, Programme.
import { api } from '../api.js';
import { lineChart, legend } from '../charts.js';
import { el, icon, lamp } from '../dom.js';
import { GiB, ago, bytes, dec1, dec2, duration, gb, inDays, int, month, now, rate, when } from '../format.js';
import { bitcoinFigures, coreBlock } from './bitcoin.js';
import { LEVEL_WORD, deviceLevel, findingsList, gauges, modelShort, roleText } from './common.js';
import { createPrograms } from './programs.js';
import { isActive } from './tasks.js';

const RANGES = [['24h', '24 Std.'], ['7d', '7 Tage'], ['30d', '30 Tage'], ['90d', '90 Tage']];
const kib = v => v / 1024;

const CHARTS = [
  { title: 'Prozessor', fmt: v => `${int(v)} %`, floor0: true, series: [{ name: 'Prozessor', key: 'cpu', color: 'var(--series-1)' }] },
  { title: 'Temperatur', fmt: v => `${dec1(v)} °C`, series: [{ name: 'Temperatur', key: 'temp', color: 'var(--series-1)' }] },
  { title: 'Speicherplatz frei', fmt: v => `${dec1(v)} GB`, series: [{ name: 'Speicherplatz frei', key: 'disk_avail', color: 'var(--series-1)', scale: v => v / GiB }] },
  { title: 'Netzwerk', fmt: v => `${int(v)} kB/s`, floor0: true, series: [
    { name: 'Empfangen', key: 'rx', color: 'var(--series-1)', scale: kib },
    { name: 'Gesendet', key: 'tx', color: 'var(--series-2)', scale: kib }] },
];

function store(key, value) {
  try { if (value === undefined) return localStorage.getItem(key); localStorage.setItem(key, value); } catch (e) { return null; }
  return null;
}

function section(title, id, ...kids) {
  return el('section', { class: 'section', 'aria-labelledby': id }, el('h2', { id }, title), ...kids);
}

function dockerState(c) {
  if (c.state === 'running') return ['ok', 'läuft'];
  if (c.state === 'restarting') return ['warn', 'startet ständig neu'];
  if (c.state === 'paused') return ['info', 'pausiert'];
  return ['off', 'gestoppt'];
}

export function createDeviceView(host, ctx) {
  const ui = { range: store('hz-range') || '24h', coreConfirm: null };
  let history = null;
  let device = null;

  const head = el('div');
  const findings = el('div');
  const stateBox = el('div', { class: 'cols' });
  const seg = el('div', { class: 'seg', role: 'group', 'aria-label': 'Zeitraum' });
  const charts = el('div', { class: 'charts' });
  const tableBox = el('div', { class: 'tscroll' });
  const details = el('details', { class: 'table', ontoggle: () => details.open && fillTable() },
    el('summary', { text: 'Werte als Tabelle' }), tableBox);
  const btcFigures = el('div');
  const coreBox = el('div');
  const btcSection = section('Bitcoin', `btc-${host}`, btcFigures,
    el('h3', { style: 'font-size:15px;margin:18px 0 6px', text: 'Bitcoin Core' }), coreBox);
  const dockerList = el('ul', { class: 'list' });
  const dockerSection = section('Docker-Apps', `dock-${host}`, dockerList);
  const programs = createPrograms(host, ctx);

  for (const [key, label] of RANGES) {
    seg.append(el('button', { type: 'button', 'data-range': key, 'aria-pressed': String(key === ui.range), text: label,
      onclick: () => { ui.range = key; store('hz-range', key); seg.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.range === key))); loadHistory(); } }));
  }

  const root = el('div', {},
    el('a', { class: 'back', href: '#/' }, icon('back'), 'Alle Pis'),
    head, findings,
    section('Zustand', `state-${host}`, stateBox),
    section('Verlauf', `hist-${host}`, el('div', { class: 'filters' }, seg), charts, details),
    btcSection, dockerSection, programs.section);

  async function loadHistory() {
    charts.classList.add('loading');
    try { history = await api.history(host, ui.range); } catch (e) { /* alter Stand bleibt */ }
    charts.classList.remove('loading');
    drawCharts();
  }

  function drawCharts() {
    if (!history) return;
    const idx = Object.fromEntries(history.fields.map((f, i) => [f, i]));
    const gap = Math.max(history.bucket * 2.5, 900);
    charts.replaceChildren();
    const boxes = CHARTS.map(def => {
      const series = def.series.map(s => ({ name: s.name, color: s.color,
        points: history.points.map(p => [p[0], p[idx[s.key]] == null ? null : (s.scale || (v => v))(p[idx[s.key]])]) }));
      const last = series.map(s => [...s.points].reverse().find(p => p[1] != null)).filter(Boolean);
      const box = el('div', { class: 'chart-box' });
      charts.append(el('div', { class: 'chart' },
        el('div', { class: 'chart-head' }, el('h3', { text: def.title }),
          el('span', { class: 'chart-now', text: last.length ? `zuletzt ${last.map(p => def.fmt(p[1])).join(' / ')}` : '' })),
        legend(series), box));
      return [box, def, series];
    });
    for (const [box, def, series] of boxes) {
      lineChart(box, { title: def.title, fmt: def.fmt, series, start: history.now - history.span, end: history.now, gap, floor0: def.floor0 });
    }
    if (details.open) fillTable();
  }

  function fillTable() {
    if (!history) return;
    const idx = Object.fromEntries(history.fields.map((f, i) => [f, i]));
    const btc = device && device.metrics.has_bitcoin;
    const cols = [['Zeit', p => when(p[0])], ['Prozessor', p => (p[idx.cpu] == null ? '–' : `${int(p[idx.cpu])} %`)],
      ['Temperatur', p => (p[idx.temp] == null ? '–' : `${dec1(p[idx.temp])} °C`)], ['Speicherplatz frei', p => gb(p[idx.disk_avail])],
      ['Empfangen', p => rate(p[idx.rx])], ['Gesendet', p => rate(p[idx.tx])]];
    if (btc) cols.push(['Blockhöhe', p => int(p[idx.height])], ['Verbindungen', p => int(p[idx.peers])]);
    const rows = [...history.points].reverse().map(p => el('tr', {}, cols.map(([, f]) => el('td', { text: f(p) }))));
    tableBox.replaceChildren(el('table', {},
      el('thead', {}, el('tr', {}, cols.map(([t]) => el('th', { scope: 'col', text: t })))),
      el('tbody', {}, rows.length ? rows : el('tr', {}, el('td', { colspan: cols.length, text: 'Noch keine Werte in diesem Zeitraum.' })))));
  }

  function renderHead(d) {
    const m = d.metrics;
    const level = d.online ? deviceLevel(d) : 'off';
    const facts = [['Adresse', m.ip], ['System', m.os], ['Kernel', m.kernel],
      ['Letzte Meldung', ago(now() - d.received)], ['Agent', m.agent]].filter(([, v]) => v);
    head.replaceChildren(
      el('div', { class: 'device-head' }, lamp(level, LEVEL_WORD[level]), el('h1', { text: d.host }),
        el('span', { class: 'role', text: [roleText(m), modelShort(m)].filter(Boolean).join(', ') })),
      el('dl', { class: 'facts' }, facts.map(([k, v]) => el('div', {}, el('dt', { text: k }), el('dd', { text: v })))));
    findings.replaceChildren(d.findings.length ? findingsList(d.findings, { roomy: true }) : '');
  }

  function renderState(d, s) {
    const m = d.metrics;
    const net = d.derived.net;
    const f = d.derived.forecast;
    const rows = [];
    if (m.load) rows.push(['Last (1/5/15 Min.)', m.load.map(dec2).join('  ')]);
    if (m.cores) rows.push(['Prozessorkerne', int(m.cores)]);
    if (m.mem_total) rows.push(['Arbeitsspeicher', `${bytes(m.mem_total - (m.mem_avail || 0))} von ${bytes(m.mem_total)} belegt`]);
    if (m.swap_total) rows.push(['Auslagerung', `${bytes(m.swap_used)} von ${bytes(m.swap_total)}`]);
    for (const disk of m.disks || []) rows.push([disk.mount === '/' ? 'Hauptlaufwerk' : `Laufwerk ${disk.mount}`, `${gb(disk.avail)} frei von ${gb(disk.size)}`]);
    if (f && f.ready && f.days_to_full != null) rows.push(['Voll in', `ca. ${inDays(f.days_to_full)} (${month(now() + f.days_to_full * 86400)}), bei ${dec1(-f.per_day / GiB)} GB pro Tag`]);
    else if (f && f.ready) rows.push(['Voll in', 'nimmt gerade nicht ab']);
    else if (f) rows.push(['Voll in', `Prognose ab ${when(f.ready_at)}`]);
    if (net) rows.push([`Netzwerk${m.net_iface ? ` (${m.net_iface})` : ''}`, `↓ ${rate(net.rx)}   ↑ ${rate(net.tx)}`]);
    if (m.uptime_s != null) rows.push(['Läuft seit', duration(m.uptime_s)]);
    if (m.throttled) rows.push(['Drosselung', m.throttled === '0x0' ? 'keine' : m.throttled]);
    const kids = [gauges(m, s.thresholds, true), el('dl', { class: 'kv' }, rows.map(([k, v]) => [el('dt', { text: k }), el('dd', { text: v })]))];
    if (m.version < 2) {
      kids.push(el('p', { class: 'note', style: 'grid-column:1/-1' }, lamp('info'),
        el('span', { text: 'Dieser Pi meldet noch mit dem alten Melder. Mit dem Agenten kommen Prozessor, Netzwerk und die Programmliste dazu.' })));
    }
    stateBox.replaceChildren(...kids);
  }

  function renderDocker(m) {
    dockerSection.hidden = !m.docker;
    if (!m.docker) return;
    dockerList.replaceChildren(...(m.docker.length ? m.docker.map(c => {
      const [lv, word] = dockerState(c);
      return el('li', {}, el('div', { class: 'row-main' }, lamp(lv, word), el('span', { class: 'row-title', text: c.name }),
        el('span', { class: 'row-side', text: c.status || word }), el('span', { class: 'row-sub', text: c.image || '' })));
    }) : [el('li', { class: 'note', text: 'Keine Docker-Apps installiert.' })]));
  }

  let first = true;
  return {
    root,
    update(d, s) {
      device = d;
      renderHead(d);
      renderState(d, s);
      btcSection.hidden = !d.metrics.has_bitcoin;
      if (d.metrics.has_bitcoin) {
        btcFigures.replaceChildren(bitcoinFigures(d));
        coreBlock(coreBox, d, ui, ctx);
      }
      renderDocker(d.metrics);
      programs.section.hidden = !d.inventory || !d.inventory.count;
      programs.update(d);
      if (first) { first = false; loadHistory(); if (!programs.section.hidden) programs.load(); }
    },
    reloadHistory: loadHistory,
    redraw: drawCharts,
    busy: () => isActive(device && device.task) || programs.waiting(),
  };
}
