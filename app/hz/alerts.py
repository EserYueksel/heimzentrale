"""Wann aufs Handy gemeldet wird.

Jeder meldepflichtige Befund wird nur einmal gemeldet (erneut nur, wenn er schlimmer wird). Ist er
weg, kommt eine Entwarnung. Befunde mit 'delay' muessen so lange am Stueck bestehen.
"""
import time

from . import config, db, notify
from .checks import LEVELS, UNSURE_KINDS, evaluate

STARTED = time.time()


def run(now=None):
    now = now or time.time()
    if now - STARTED < config.num("STARTUP_GRACE_MIN") * 60:
        return
    d = db.get()
    active, unsure_hosts = {}, set()
    for state in evaluate(now):
        for f in state["findings"]:
            if f["notify"]:
                active[f["key"]] = f
            if f["kind"] in UNSURE_KINDS:
                unsure_hosts.add(f["host"])
    rows = {r["key"]: dict(r) for r in d.query("SELECT * FROM alerts")}

    for key, f in active.items():
        lvl = LEVELS[f["level"]]
        row = rows.get(key)
        if row is None:
            row = {"first_seen": int(now), "notified_level": 0}
            d.run("INSERT INTO alerts(key, level, first_seen, notified_level, title, text) VALUES(?,?,?,?,?,?)",
                  (key, lvl, int(now), 0, f["title"], f["text"]))
        if row["notified_level"] > lvl:  # z. B. von dringend zurueck auf Warnung: leise herabstufen
            row["notified_level"] = lvl
        if now - row["first_seen"] >= f["delay"] and lvl > row["notified_level"]:
            if notify.send(f"Heimzentrale: {f['title']} ({f['host']})", f["text"],
                           priority=5 if lvl == 2 and f["kind"] == "disk" else 4,
                           tags=["rotating_light" if lvl == 2 else "warning"]):
                row["notified_level"] = lvl
        d.run("UPDATE alerts SET level=?, notified_level=?, title=?, text=? WHERE key=?",
              (lvl, row["notified_level"], f["title"], f["text"], key))

    for key, row in rows.items():
        if key in active:
            continue
        host, kind = key.split(":", 1)
        if host in unsure_hosts and kind != "silent":
            continue
        if row["notified_level"] > 0:
            if not notify.send(f"Heimzentrale: wieder in Ordnung ({host})", f"Behoben: {row['title']}.",
                               priority=3, tags=["white_check_mark"]):
                continue  # beim naechsten Durchlauf nochmal
        d.run("DELETE FROM alerts WHERE key=?", (key,))


def notified_keys():
    return {r["key"]: r["notified_level"] for r in db.get().query("SELECT key, notified_level FROM alerts")}
