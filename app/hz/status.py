"""Antworten fuer die Seite: Zustand aller Pis und Verlauf eines Pi."""
import time

from . import VERSION, alerts, config, core, db, inventory, nettip, notify, tasks
from .checks import evaluate

RANGES = {"24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400, "90d": 90 * 86400}
STARTED = time.time()


def disk_forecast(host, avail, now):
    """Wann ist der Speicher voll? Gerade durch die Werte der letzten 7 Tage (ab 20 Stunden Daten)."""
    rows = db.get().query("SELECT ts, disk_avail FROM samples WHERE host=? AND ts>=? AND disk_avail IS NOT NULL "
                          "ORDER BY ts", (host, int(now - 7 * 86400)))
    need = 20 * 3600
    if len(rows) < 10 or rows[-1]["ts"] - rows[0]["ts"] < need:
        start = rows[0]["ts"] if rows else int(now)
        return {"ready": False, "ready_at": start + need}
    xs, ys = [r["ts"] for r in rows], [r["disk_avail"] for r in rows]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return {"ready": False, "ready_at": int(now) + 3600}
    per_day = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx * 86400
    res = {"ready": True, "per_day": per_day, "basis_days": (xs[-1] - xs[0]) / 86400}
    if per_day < -50e6 and avail is not None:
        res["days_to_full"] = max(0.0, avail / -per_day)
    return res


def net_rate(host):
    """Datenrate (Bytes/s) aus den letzten zwei Messpunkten."""
    rows = db.get().query("SELECT ts, net_rx, net_tx FROM samples WHERE host=? AND net_rx IS NOT NULL "
                          "ORDER BY ts DESC LIMIT 2", (host,))
    if len(rows) < 2:
        return None
    (b, a), dt = rows, rows[0]["ts"] - rows[1]["ts"]
    if dt <= 0 or b["net_rx"] < a["net_rx"] or b["net_tx"] < a["net_tx"]:
        return None  # Zaehler nach Neustart zurueckgesetzt
    return {"rx": (b["net_rx"] - a["net_rx"]) / dt, "tx": (b["net_tx"] - a["net_tx"]) / dt}


def _order(hosts):
    pref = [h.strip() for h in config.get("DEVICE_ORDER").split(",") if h.strip()]
    return sorted(hosts, key=lambda h: (pref.index(h) if h in pref else len(pref), h.lower()))


def build(now=None):
    now = now or time.time()
    notified = alerts.notified_keys()
    inv = inventory.hosts_with_inventory()
    states = {s["host"]: s for s in evaluate(now)}
    devices = []
    for host in _order(states):
        s = states[host]
        m, age = s["metrics"], now - s["received"]
        derived = {"net": net_rate(host)}
        if m.get("disk_avail") is not None:
            derived["forecast"] = disk_forecast(host, m["disk_avail"], now)
        if m.get("has_bitcoin") and m.get("height") is not None:
            tip = nettip.fresh(now)
            derived["net_tip"] = tip
            derived["behind"] = tip - m["height"] if tip is not None else None
        devices.append({
            "host": host,
            "received": s["received"],
            "age": age,
            "online": age <= config.num("SILENT_MIN") * 60,
            "metrics": m,
            "derived": derived,
            "findings": [{"level": f["level"], "title": f["title"], "text": f["text"], "notify": f["notify"],
                          "notified": notified.get(f["key"], 0) > 0} for f in s["findings"]],
            "core": core.summary(m) if m.get("has_bitcoin") else None,
            # letzter Auftrag der Woche - wie lange das Ergebnis sichtbar bleibt, entscheidet die Seite
            "task": tasks.public(tasks.active(host) or tasks.recent(host, now - 7 * 86400)),
            "inventory": inv.get(host),
        })
    return {
        "version": VERSION,
        "now": now,
        "started": STARTED,
        "ntfy": notify.ready(),
        "pin": tasks.pin_set(),
        "thresholds": {k: config.num(k) for k in ("DISK_WARN_GB", "DISK_CRIT_GB", "SILENT_MIN", "TEMP_WARN",
                                                   "TEMP_CRIT", "CPU_WARN", "MEM_WARN")},
        "network": {"tip": nettip.NET["tip"], "ts": nettip.NET["ts"] or None, "source": nettip.NET["source"],
                    "error": nettip.NET["error"]},
        "devices": devices,
    }


FIELDS = ["ts", "disk_avail", "temp", "cpu", "mem_pct", "rx", "tx", "height", "peers", "mempool_tx"]


def history(host, rng, now=None):
    span = RANGES.get(rng, RANGES["24h"])
    now = int(now or time.time())
    bucket = max(300, span // 300)
    rows = db.get().query(
        "SELECT ts, disk_avail, temp, cpu, mem_pct, net_rx, net_tx, height, "
        "COALESCE(peers_out, 0) + COALESCE(peers_in, 0) AS peers, peers_out, mempool_tx "
        "FROM samples WHERE host=? AND ts>=? ORDER BY ts", (host, now - span - 3600))
    buckets, prev = {}, None
    for r in rows:
        rx = tx = None
        if prev and r["net_rx"] is not None and prev["net_rx"] is not None:
            dt = r["ts"] - prev["ts"]
            if 0 < dt <= 3600 and r["net_rx"] >= prev["net_rx"] and r["net_tx"] >= prev["net_tx"]:
                rx, tx = (r["net_rx"] - prev["net_rx"]) / dt, (r["net_tx"] - prev["net_tx"]) / dt
        prev = r
        if r["ts"] < now - span:
            continue
        b = buckets.setdefault(r["ts"] // bucket, {k: [] for k in FIELDS[1:]})
        vals = {"disk_avail": r["disk_avail"], "temp": r["temp"], "cpu": r["cpu"], "mem_pct": r["mem_pct"],
                "rx": rx, "tx": tx, "height": r["height"],
                "peers": r["peers"] if r["peers_out"] is not None else None, "mempool_tx": r["mempool_tx"]}
        for k, v in vals.items():
            if v is not None:
                b[k].append(v)
    points = []
    for key in sorted(buckets):
        b = buckets[key]
        row = [min(now, key * bucket + bucket // 2)]
        for k in FIELDS[1:]:
            v = b[k]
            if not v:
                row.append(None)
            elif k == "height":
                row.append(max(v))
            else:
                avg = sum(v) / len(v)
                row.append(round(avg, 1) if k in ("temp", "cpu", "mem_pct") else round(avg))
        points.append(row)
    return {"host": host, "range": rng if rng in RANGES else "24h", "span": span, "bucket": bucket, "now": now,
            "fields": FIELDS, "points": points}
