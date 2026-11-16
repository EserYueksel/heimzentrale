// Kleine Bausteine fuer das Erzeugen von HTML und SVG.
// Texte aus Meldungen werden immer als Text eingesetzt (nie als HTML).

const SVGNS = 'http://www.w3.org/2000/svg';

export function el(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'text') n.textContent = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : v);
  }
  append(n, kids);
  return n;
}

export function sv(tag, attrs, ...kids) {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null) n.setAttribute(k, v);
  append(n, kids);
  return n;
}

function append(n, kids) {
  for (const c of kids.flat(Infinity)) {
    if (c == null || c === false) continue;
    n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

// Statuslampe: Form + Farbe (+ Text daneben). ok = Kreis mit Haken, warn = Dreieck, crit = Kreis mit Kreuz,
// info = Ring, off = grauer Ring.
export function lamp(level, label) {
  const s = sv('svg', { viewBox: '0 0 16 16', width: '100%', height: '100%', 'aria-hidden': 'true' });
  if (level === 'ok') {
    s.append(sv('circle', { cx: 8, cy: 8, r: 7.2, fill: 'var(--good)' }),
      sv('path', { d: 'M4.8 8.3 7 10.4 11.2 5.9', fill: 'none', stroke: '#fff', 'stroke-width': 1.8, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
  } else if (level === 'warn') {
    s.append(sv('path', { d: 'M8 1.2 15.3 14.2H.7z', fill: 'var(--warning)', 'stroke-linejoin': 'round' }),
      sv('path', { d: 'M8 5.9v3.7M8 11.7v.1', stroke: '#14201d', 'stroke-width': 1.7, 'stroke-linecap': 'round' }));
  } else if (level === 'crit') {
    s.append(sv('circle', { cx: 8, cy: 8, r: 7.2, fill: 'var(--critical)' }),
      sv('path', { d: 'M5.4 5.4l5.2 5.2M10.6 5.4l-5.2 5.2', stroke: '#fff', 'stroke-width': 1.8, 'stroke-linecap': 'round' }));
  } else if (level === 'off') {
    s.append(sv('circle', { cx: 8, cy: 8, r: 6.3, fill: 'none', stroke: 'var(--muted)', 'stroke-width': 1.6, 'stroke-dasharray': '2.4 2' }));
  } else {
    s.append(sv('circle', { cx: 8, cy: 8, r: 6.3, fill: 'none', stroke: 'var(--muted)', 'stroke-width': 1.4 }),
      sv('path', { d: 'M8 7.3v4M8 4.9v.1', stroke: 'var(--muted)', 'stroke-width': 1.6, 'stroke-linecap': 'round' }));
  }
  const wrap = el('span', { class: 'lamp', role: label ? 'img' : null, 'aria-label': label || null });
  wrap.append(s);
  return wrap;
}

export const ICONS = {
  back: 'M10 3 5 8l5 5',
  plus: 'M8 3v10M3 8h10',
  sun: null,
  moon: 'M13.5 10.2A5.8 5.8 0 0 1 5.8 2.5a5.8 5.8 0 1 0 7.7 7.7z',
  copy: 'M5 5V3h8v8h-2M3 5h8v8H3z',
};

export function icon(name) {
  const s = sv('svg', { viewBox: '0 0 16 16', width: 16, height: 16, 'aria-hidden': 'true' });
  if (name === 'sun') {
    s.append(sv('circle', { cx: 8, cy: 8, r: 3.2, fill: 'currentColor' }),
      sv('path', { d: 'M8 .9v2M8 13.1v2M.9 8h2M13.1 8h2M3 3l1.4 1.4M11.6 11.6 13 13M3 13l1.4-1.4M11.6 4.4 13 3', stroke: 'currentColor', 'stroke-width': 1.5, 'stroke-linecap': 'round' }));
  } else if (name === 'moon') {
    s.append(sv('path', { d: ICONS.moon, fill: 'currentColor' }));
  } else {
    s.append(sv('path', { d: ICONS[name], fill: 'none', stroke: 'currentColor', 'stroke-width': 1.7, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
  }
  return s;
}

export function toast(text) {
  const t = el('div', { class: 'toast', role: 'status', text });
  document.body.append(t);
  setTimeout(() => t.remove(), 2600);
}
