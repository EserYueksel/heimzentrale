// Verbindung zur Heimzentrale.

async function getJSON(url) {
  const r = await fetch(url, { cache: 'no-store' });
  if (!r.ok) throw new Error(`Fehler ${r.status}`);
  return r.json();
}

async function postJSON(url, body) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const answer = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(answer.error || `Fehler ${r.status}`);
  return answer;
}

export const api = {
  status: () => getJSON('/api/status'),
  history: (host, range) => getJSON(`/api/history?host=${encodeURIComponent(host)}&range=${encodeURIComponent(range)}`),
  inventory: host => getJSON(`/api/inventory?host=${encodeURIComponent(host)}`),
  task: (host, kind, params, pin) => postJSON('/api/tasks', { host, kind, params, pin }),
  cancel: host => postJSON('/api/tasks/cancel', { host }),
  connect: pin => postJSON('/api/connect', { pin }),
};
