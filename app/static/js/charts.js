// Linienkurven mit Fadenkreuz, Tooltip (alle Reihen), Tastatur und Luecken bei fehlenden Meldungen.
// Eine Reihe: kein Legendenkasten (der Titel sagt, was gezeigt wird). Ab zwei Reihen: Legende.
import { el, sv } from './dom.js';
import { when } from './format.js';

function niceTicks(lo, hi, n, floor0) {
  if (floor0) lo = Math.min(lo, 0);
  if (lo === hi) { const pad = Math.abs(lo) * 0.05 || 1; lo -= pad; hi += pad; }
  const raw = (hi - lo) / n;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const r = raw / mag;
  const nice = r <= 1 ? 1 : r <= 2 ? 2 : r <= 2.5 ? 2.5 : r <= 5 ? 5 : 10;
  const step = nice * mag;
  const min = Math.floor(lo / step) * step;
  const max = Math.ceil(hi / step) * step;
  const values = [];
  for (let v = min; v <= max + step / 2; v += step) values.push(+v.toFixed(10));
  const dec = Math.max(0, -Math.round(Math.log10(mag)) + (nice === 2.5 ? 1 : 0) - (nice === 10 ? 1 : 0));
  return { min, max, values, dec };
}

function timeTicks(start, end) {
  const span = end - start;
  const steps = [[3, 'h'], [6, 'h'], [12, 'h'], [1, 'd'], [2, 'd'], [7, 'd'], [14, 'd'], [30, 'd']];
  let [k, u] = steps[steps.length - 1];
  for (const s of steps) { if (span / (s[0] * (s[1] === 'h' ? 3600 : 86400)) <= 6) { [k, u] = s; break; } }
  const out = [];
  const d = new Date(start * 1000);
  d.setMinutes(0, 0, 0);
  if (u === 'h') {
    d.setHours(Math.ceil((d.getHours() + (d.getTime() / 1000 < start ? 1 : 0)) / k) * k);
    while (d.getTime() / 1000 <= end) {
      out.push([d.getTime() / 1000, d.getHours() === 0
        ? d.toLocaleDateString('de-DE', { weekday: 'short' })
        : d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })]);
      d.setHours(d.getHours() + k);
    }
  } else {
    d.setHours(0);
    if (d.getTime() / 1000 < start) d.setDate(d.getDate() + 1);
    while (d.getTime() / 1000 <= end) {
      out.push([d.getTime() / 1000, d.toLocaleDateString('de-DE', k <= 2 ? { weekday: 'short', day: 'numeric', month: 'numeric' } : { day: 'numeric', month: 'numeric' })]);
      d.setDate(d.getDate() + k);
    }
  }
  return out;
}

/**
 * Kurve zeichnen.
 * opts: { title, series: [{ name, color, points: [[ts, value|null]] }], fmt, start, end, gap, floor0 }
 */
export function lineChart(box, opts) {
  box.replaceChildren();
  const series = opts.series.map(s => ({ ...s, pts: s.points.filter(p => p[1] != null) }));
  const all = series.flatMap(s => s.pts);
  if (all.length < 2) {
    box.append(el('p', { class: 'empty', text: 'Noch zu wenige Messpunkte für eine Kurve.' }));
    return;
  }
  const W = Math.max(260, box.clientWidth);
  const H = 170;
  const M = { l: 48, r: 10, t: 10, b: 24 };
  const pw = W - M.l - M.r;
  const ph = H - M.t - M.b;
  const vals = all.map(p => p[1]);
  const tk = niceTicks(Math.min(...vals), Math.max(...vals), 4, opts.floor0);
  const X = t => M.l + (t - opts.start) / (opts.end - opts.start) * pw;
  const Y = v => M.t + ph - (v - tk.min) / (tk.max - tk.min) * ph;
  const last = series.map(s => s.pts[s.pts.length - 1]).filter(Boolean);
  const svg = sv('svg', {
    viewBox: `0 0 ${W} ${H}`, height: H, tabindex: 0, role: 'img',
    'aria-label': `${opts.title}: ${series.map((s, i) => `${s.name || ''} zuletzt ${last[i] ? opts.fmt(last[i][1]) : '–'}`).join(', ')}. Mit den Pfeiltasten durch die Werte gehen.`,
  });
  for (const v of tk.values) {
    svg.append(sv('line', { x1: M.l, x2: W - M.r, y1: Y(v), y2: Y(v), stroke: 'var(--line)', 'stroke-width': 1 }));
    svg.append(sv('text', { x: M.l - 6, y: Y(v) + 3.5, 'text-anchor': 'end' },
      v.toLocaleString('de-DE', { minimumFractionDigits: tk.dec, maximumFractionDigits: tk.dec })));
  }
  svg.append(sv('line', { x1: M.l, x2: W - M.r, y1: M.t + ph + 0.5, y2: M.t + ph + 0.5, stroke: 'var(--line-strong)', 'stroke-width': 1 }));
  for (const [ts, label] of timeTicks(opts.start, opts.end)) {
    const x = X(ts);
    if (x > M.l + 12 && x < W - M.r - 12) svg.append(sv('text', { x, y: H - 6, 'text-anchor': 'middle' }, label));
  }
  for (const s of series) {
    let d = '';
    let prev = null;
    for (const [ts, v] of s.pts) {
      d += `${prev == null || ts - prev > opts.gap ? 'M' : 'L'}${X(ts).toFixed(1)} ${Y(v).toFixed(1)} `;
      prev = ts;
    }
    svg.append(sv('path', { d, fill: 'none', stroke: s.color, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
    const e = s.pts[s.pts.length - 1];
    if (e) svg.append(sv('circle', { cx: X(e[0]), cy: Y(e[1]), r: 4, fill: s.color, stroke: 'var(--surface)', 'stroke-width': 2 }));
  }

  // Fadenkreuz: sucht den naechsten Zeitpunkt, zeigt alle Reihen
  const times = [...new Set(all.map(p => p[0]))].sort((a, b) => a - b);
  const byTs = series.map(s => new Map(s.pts.map(p => [p[0], p[1]])));
  const cross = sv('line', { y1: M.t, y2: M.t + ph, stroke: 'var(--line-strong)', 'stroke-width': 1, visibility: 'hidden' });
  const dots = series.map(s => sv('circle', { r: 4, fill: s.color, stroke: 'var(--surface)', 'stroke-width': 2, visibility: 'hidden' }));
  svg.append(cross, ...dots);
  const tip = el('div', { class: 'tip', hidden: true });
  box.append(svg, tip);
  let idx = -1;
  const show = i => {
    idx = Math.max(0, Math.min(times.length - 1, i));
    const ts = times[idx];
    const x = X(ts);
    cross.setAttribute('x1', x); cross.setAttribute('x2', x); cross.setAttribute('visibility', 'visible');
    let top = M.t + ph;
    const rows = [];
    series.forEach((s, k) => {
      const v = byTs[k].get(ts);
      if (v == null) { dots[k].setAttribute('visibility', 'hidden'); return; }
      dots[k].setAttribute('cx', x); dots[k].setAttribute('cy', Y(v)); dots[k].setAttribute('visibility', 'visible');
      top = Math.min(top, Y(v));
      rows.push(el('div', { class: 'row' }, series.length > 1 ? el('i', { style: `background:${s.color}` }) : null,
        el('b', { text: opts.fmt(v) }), series.length > 1 ? el('span', { text: s.name }) : null));
    });
    tip.replaceChildren(...rows, el('div', { class: 'when', text: when(ts) }));
    tip.hidden = false;
    const scale = box.clientWidth / W;
    tip.style.left = `${Math.min(Math.max(x * scale, 70), box.clientWidth - 70)}px`;
    tip.style.top = `${Math.max(0, top * scale - 10)}px`;
  };
  const hide = () => { cross.setAttribute('visibility', 'hidden'); dots.forEach(d => d.setAttribute('visibility', 'hidden')); tip.hidden = true; };
  const nearest = clientX => {
    const r = svg.getBoundingClientRect();
    const t = opts.start + ((clientX - r.left) * (W / r.width) - M.l) / pw * (opts.end - opts.start);
    let lo = 0;
    let hi = times.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (times[mid] < t) lo = mid; else hi = mid; }
    return Math.abs(times[lo] - t) <= Math.abs(times[hi] - t) ? lo : hi;
  };
  svg.addEventListener('pointermove', e => show(nearest(e.clientX)));
  svg.addEventListener('pointerdown', e => show(nearest(e.clientX)));
  svg.addEventListener('pointerleave', hide);
  svg.addEventListener('focus', () => show(times.length - 1));
  svg.addEventListener('blur', hide);
  svg.addEventListener('keydown', e => {
    const keys = { ArrowLeft: idx - 1, ArrowRight: idx + 1, Home: 0, End: times.length - 1 };
    if (e.key in keys) { show(keys[e.key]); e.preventDefault(); } else if (e.key === 'Escape') hide();
  });
}

export function legend(series) {
  if (series.length < 2) return null;
  return el('div', { class: 'legend' }, series.map(s => el('span', {}, el('i', { style: `background:${s.color}` }), s.name)));
}
