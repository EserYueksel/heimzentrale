// Zahlen und Zeiten auf Deutsch.

const nf0 = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const GiB = 1024 ** 3;

export const int = n => (n == null ? '–' : nf0.format(n));
export const dec1 = n => (n == null ? '–' : nf1.format(n));
export const dec2 = n => (n == null ? '–' : nf2.format(n));
export const pct = n => (n == null ? '–' : `${nf0.format(n)} %`);
export const now = () => Date.now() / 1000;

export function gb(b) {
  return b == null ? '–' : `${nf1.format(b / GiB)} GB`;
}

export function bytes(b) {
  if (b == null) return '–';
  if (b >= 1024 ** 4) return `${nf1.format(b / 1024 ** 4)} TB`;
  if (b >= GiB) return `${nf1.format(b / GiB)} GB`;
  if (b >= 1024 ** 2) return `${nf0.format(b / 1024 ** 2)} MB`;
  return `${nf0.format(b / 1024)} kB`;
}

export function rate(bps) {
  if (bps == null) return '–';
  if (bps >= 1024 ** 2) return `${nf1.format(bps / 1024 ** 2)} MB/s`;
  return `${nf0.format(bps / 1024)} kB/s`;
}

export function ago(sec) {
  sec = Math.max(0, sec);
  if (sec < 60) return 'gerade eben';
  const m = Math.floor(sec / 60);
  if (m < 60) return `vor ${m} Min.`;
  const h = Math.floor(m / 60);
  if (h < 48) return `vor ${h} Std.` + (h < 6 && m % 60 ? ` ${m % 60} Min.` : '');
  return `vor ${Math.floor(h / 24)} Tagen`;
}

export function duration(sec) {
  if (sec == null) return '–';
  const m = Math.floor(sec / 60);
  if (m < 60) return `${m} Min.`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h} Std.`;
  return `${Math.floor(h / 24)} Tage`;
}

// Dativ fuer "in ca. ..."
export function inDays(d) {
  if (d < 1.5) return '1 Tag';
  if (d < 14) return `${Math.round(d)} Tagen`;
  if (d < 60) { const w = Math.round(d / 7); return w === 1 ? '1 Woche' : `${w} Wochen`; }
  const mo = Math.round(d / 30.4);
  return mo === 1 ? '1 Monat' : `${mo} Monaten`;
}

export const clock = ts => new Date(ts * 1000).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
export const when = ts => new Date(ts * 1000).toLocaleString('de-DE', { weekday: 'short', day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' });
export const month = ts => new Date(ts * 1000).toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });

export function plural(n, one, many) {
  return `${int(n)} ${n === 1 ? one : many}`;
}
