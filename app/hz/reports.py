"""Meldungen der Pis speichern: letzte Meldung je Pi + ein Messpunkt pro Minute fuer den Verlauf."""
import json
import re
import time

from . import db
from .metrics import extract

HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,62}$")


def valid_host(host):
    return isinstance(host, str) and bool(HOST_RE.match(host))


def store(payload, now=None):
    host = payload.get("host")
    if not valid_host(host):
        raise ValueError("Feld host fehlt oder ist ungültig")
    now = int(now or time.time())
    m = extract(payload)
    d = db.get()
    d.run("INSERT INTO latest(host, received, payload) VALUES(?,?,?) "
          "ON CONFLICT(host) DO UPDATE SET received=excluded.received, payload=excluded.payload",
          (host, now, json.dumps(payload, separators=(",", ":"))))
    last = d.one("SELECT MAX(ts) AS t FROM samples WHERE host=?", (host,))
    if last and last["t"] and now - last["t"] < 60:
        return host  # hoechstens ein Messpunkt pro Minute
    d.run("INSERT OR REPLACE INTO samples(host, ts, height, headers, disk_avail, disk_size, temp, peers_out, peers_in, "
          "mempool_tx, mempool_bytes, service_ok, cpu, mem_pct, net_rx, net_tx) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (host, now, m.get("height"), m.get("headers"), m.get("disk_avail"), m.get("disk_size"), m.get("temp"),
           m.get("peers_out"), m.get("peers_in"), m.get("mempool_tx"), m.get("mempool_bytes"),
           None if m.get("service") is None else int(m.get("service") == "active"),
           m.get("cpu_pct"), m.get("mem_pct"), m.get("net_rx"), m.get("net_tx")))
    return host


def latest_all():
    """[(host, received, payload, metrics)] fuer alle Pis."""
    out = []
    for row in db.get().query("SELECT host, received, payload FROM latest ORDER BY host"):
        try:
            payload = json.loads(row["payload"])
        except ValueError:
            continue
        out.append((row["host"], row["received"], payload, extract(payload)))
    return out


def latest_metrics(host):
    row = db.get().one("SELECT payload FROM latest WHERE host=?", (host,))
    if not row:
        return None
    try:
        return extract(json.loads(row["payload"]))
    except ValueError:
        return None
