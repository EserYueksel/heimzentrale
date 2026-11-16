"""Was bei einem Pi auffaellt.

Jede Auffaelligkeit ist ein 'Befund' mit Stufe (info | warn | crit). notify=True heisst: die
Heimzentrale meldet ihn aufs Handy (siehe alerts). Hat ein Pi ein eigenes Melde-Skript (der Agent
meldet dann own_alarms), meldet die Heimzentrale Hitze, Drosselung und einen ausgefallenen
Bitcoin-Dienst dort nicht noch einmal, sondern zeigt sie nur an.
"""
import time

from . import config, db, nettip, reports, tasks
from .fmt import GiB, de_gb, de_int, de_num, seit

LEVELS = {"info": 0, "warn": 1, "crit": 2}
# Befunde, bei denen die uebrigen Werte unsicher sind: dann nichts als "behoben" melden
UNSURE_KINDS = ("silent", "service", "cli", "starting", "updating")


def finding(host, kind, level, title, text, notify=False, delay=0):
    return {"key": f"{host}:{kind}", "host": host, "kind": kind, "level": level,
            "title": title, "text": text, "notify": notify, "delay": delay}


def _disk(host, m, prev_levels):
    out = []
    avail = m.get("disk_avail")
    if avail is not None:
        warn_b, crit_b, margin = config.num("DISK_WARN_GB") * GiB, config.num("DISK_CRIT_GB") * GiB, GiB
        prev = prev_levels.get(f"{host}:disk", 0)
        level = 2 if avail < crit_b else 1 if avail < warn_b else 0
        # 1 GB Puffer, damit es an der Grenze nicht hin und her springt
        if prev == 2 and level < 2 and avail < crit_b + margin:
            level = 2
        elif prev >= 1 and level == 0 and avail < warn_b + margin:
            level = 1
        if level == 2:
            out.append(finding(host, "disk", "crit", "Speicherplatz fast voll",
                               f"Auf dem {host} sind nur noch {de_gb(avail)} frei. Ist der Speicher voll, "
                               f"funktionieren Programme nicht mehr richtig. Bald Platz schaffen.", notify=True))
        elif level == 1:
            out.append(finding(host, "disk", "warn", "Speicherplatz wird knapp",
                               f"Auf dem {host} sind noch {de_gb(avail)} frei (Warnschwelle "
                               f"{int(config.num('DISK_WARN_GB'))} GB). Rechtzeitig Platz schaffen.", notify=True))
    for d in (m.get("disks") or [])[1:]:
        if d.get("pct") is not None and d["pct"] >= 90:
            out.append(finding(host, f"disk:{d['mount']}", "warn", f"Laufwerk {d['mount']} fast voll",
                               f"{de_num(d['pct'], 0)} % belegt, noch {de_gb(d['avail'])} frei."))
    return out


def _system(host, m, own_alarms):
    """Temperatur, Drosselung, Auslastung. own_alarms: Pi meldet Hitze/Drosselung schon selbst."""
    out = []
    temp, th = m.get("temp"), m.get("throttled")
    try:
        bits = int(th, 16) if th else None
    except ValueError:
        bits = None
    if temp is not None and temp >= config.num("TEMP_CRIT"):
        out.append(finding(host, "temp", "crit", "Sehr warm", f"{de_num(temp)} °C. Kühlung prüfen.", notify=not own_alarms))
    elif temp is not None and temp >= config.num("TEMP_WARN"):
        out.append(finding(host, "temp", "warn", "Warm", f"{de_num(temp)} °C."))
    if bits is not None and bits & 0xF:
        out.append(finding(host, "throttle", "warn", "Pi bremst sich gerade aus",
                           f"throttled={th}. Netzteil oder Kühlung prüfen.", notify=not own_alarms))
    elif bits is not None and bits & 0x10000:
        out.append(finding(host, "undervolt", "info", "Unterspannung seit dem letzten Start",
                           "Seit dem letzten Neustart war die Spannung irgendwann kurz zu niedrig. "
                           "Kommt das öfter vor: Netzteil prüfen."))
    if m.get("cpu_pct") is not None and m["cpu_pct"] >= config.num("CPU_WARN"):
        out.append(finding(host, "cpu", "warn", "Prozessor stark ausgelastet", f"{de_num(m['cpu_pct'], 0)} % Auslastung."))
    if m.get("mem_pct") is not None and m["mem_pct"] >= config.num("MEM_WARN"):
        out.append(finding(host, "mem", "warn", "Arbeitsspeicher fast voll",
                           f"{de_num(m['mem_pct'], 0)} % belegt, frei {de_gb(m['mem_avail'])}."))
    for c in m.get("docker") or []:
        if c.get("state") == "restarting":
            out.append(finding(host, f"app:{c['name']}", "warn", f"App {c['name']} startet ständig neu",
                               c.get("status") or ""))
    return out


def _bitcoin(host, m, now):
    out = []
    own = bool(m.get("own_alarms"))
    service = m.get("service")
    if service and service != "active":
        out.append(finding(host, "service", "crit", "Bitcoin-Dienst läuft nicht",
                           f"Dienst bitcoind: {service}. Starten mit: sudo systemctl start bitcoind", notify=not own))
        return out
    err = m.get("btc_error") or ""
    if m.get("height") is None:
        if "-28" in err:
            out.append(finding(host, "starting", "info", "Node startet gerade", "Er lädt die Blockdaten. Das dauert ein paar Minuten."))
        else:
            out.append(finding(host, "cli", "crit", "Node antwortet nicht", err or "bitcoin-cli hat keine Antwort geliefert.",
                               notify=not own, delay=900))
        return out
    if m.get("ibd"):
        out.append(finding(host, "ibd", "info", "Synchronisiert gerade",
                           f"Geprüft: {de_num((m.get('verification') or 0) * 100, 2)} %."))
    else:
        tip, height = nettip.fresh(now), m["height"]
        if tip is not None:
            behind = tip - height
            if behind >= config.num("BEHIND_BLOCKS"):
                out.append(finding(host, "blocks", "warn", "Hängt hinter dem Netz",
                                   f"Der {host} ist {behind} Blöcke hinter dem Netz (Node {de_int(height)}, Netz {de_int(tip)}).",
                                   notify=True, delay=int(config.num("BEHIND_MIN") * 60)))
        elif m.get("block_time") and now - m["block_time"] > config.num("STALE_HOURS") * 3600:
            out.append(finding(host, "blocks", "warn", "Keine neuen Blöcke",
                               f"Seit {seit(now - m['block_time'])} kein neuer Block beim {host} (zuletzt {de_int(height)}).",
                               notify=True))
    if m.get("peers") == 0:
        out.append(finding(host, "peers", "warn", "Keine Verbindungen",
                           "Der Node hat gerade keine Verbindung zu anderen Nodes. WLAN prüfen."))
    if m.get("btc_warnings"):
        out.append(finding(host, "btcwarn", "info", "Hinweis von Bitcoin Core", m["btc_warnings"]))
    return out


def for_host(host, m, age, now, prev_levels, core_update=False):
    if age > config.num("SILENT_MIN") * 60:
        if core_update:
            return [finding(host, "updating", "info", "Update läuft",
                            "Während des Bitcoin-Core-Updates können Meldungen kurz ausbleiben.")]
        return [finding(host, "silent", "crit", f"{host} meldet sich nicht",
                        f"Seit {seit(age)} ist keine Meldung vom {host} gekommen. Strom, WLAN und den Pi prüfen.",
                        notify=True)]
    out = _disk(host, m, prev_levels) + _system(host, m, own_alarms=bool(m.get("own_alarms")))
    if m.get("has_bitcoin"):
        if core_update and (m.get("service") != "active" or m.get("height") is None):
            out.append(finding(host, "updating", "info", "Update läuft",
                               "Bitcoin Core wird gerade aktualisiert. Der Node ist dabei ein paar Minuten aus."))
        else:
            out += _bitcoin(host, m, now)
    return sorted(out, key=lambda f: -LEVELS[f["level"]])


def evaluate(now=None):
    """Zustand aller Pis: Liste von Woerterbuechern mit host, received, payload, metrics, findings."""
    now = now or time.time()
    prev = {r["key"]: r["notified_level"] for r in db.get().query("SELECT key, notified_level FROM alerts")}
    out = []
    for host, received, payload, m in reports.latest_all():
        job = tasks.active(host)
        core_update = bool(job and job["kind"] == "core-update")
        out.append({"host": host, "received": received, "payload": payload, "metrics": m,
                    "findings": for_host(host, m, now - received, now, prev, core_update)})
    return out
