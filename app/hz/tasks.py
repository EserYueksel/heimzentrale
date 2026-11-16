"""Auftraege an die Agenten auf den Pis.

Arten:
  core-update   Bitcoin Core aktualisieren            params: {"version": "31.2"}       PIN noetig
  app-preview   Vorschau: was wuerde entfernt?         params: {"type", "name"}          ohne PIN
  app-remove    Programm entfernen (nach Vorschau)     params: {"type", "name", "preview"} PIN noetig

Ablauf: Seite legt Auftrag an (requested) -> Agent holt ihn ab (claimed) -> meldet Fortschritt
(running) -> Ende (done | failed). Auftraege, die nicht abgeholt werden oder sich nicht mehr melden,
gelten nach einer Weile als gescheitert. Pro Pi immer nur ein offener Auftrag.
"""
import hashlib
import hmac
import json
import time

from . import config, db, inventory, notify, reports
from .core import VER_RE, offers
from .fmt import seit

ACTIVE = ("requested", "claimed", "running")
KINDS = ("core-update", "app-preview", "app-remove")
PIN_FAILS = {"count": 0, "until": 0.0}
PREVIEW_VALID_S = 30 * 60
TITLES = {"core-update": "Bitcoin-Core-Update", "app-preview": "Vorschau", "app-remove": "Programm entfernen"}


class TaskError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- Lesen

def _row(r):
    if r is None:
        return None
    d = dict(r)
    for key, empty in (("params", {}), ("log", []), ("result", None)):
        try:
            d[key] = json.loads(d[key]) if d.get(key) else empty
        except ValueError:
            d[key] = empty
    return d


def get(task_id):
    return _row(db.get().one("SELECT * FROM tasks WHERE id=?", (task_id,)))


def active(host):
    return _row(db.get().one("SELECT * FROM tasks WHERE host=? AND state IN (?,?,?) ORDER BY id DESC LIMIT 1",
                             (host,) + ACTIVE))


def recent(host, since):
    return _row(db.get().one("SELECT * FROM tasks WHERE host=? AND updated>=? ORDER BY id DESC LIMIT 1",
                             (host, int(since))))


# ---------------------------------------------------------------- Schreiben

def _log(task_id, state, step, text, result=None):
    t = get(task_id)
    if not t:
        return
    now = int(time.time())
    t["log"].append({"ts": now, "state": state, "step": str(step)[:40], "text": str(text)[:600]})
    db.get().run("UPDATE tasks SET state=?, updated=?, log=?, result=COALESCE(?, result) WHERE id=?",
                 (state, now, json.dumps(t["log"][-80:], ensure_ascii=False),
                  json.dumps(result, ensure_ascii=False) if result is not None else None, task_id))


def _create(host, kind, params, text):
    now = int(time.time())
    log = [{"ts": now, "state": "requested", "step": "auftrag", "text": text}]
    return db.get().run("INSERT INTO tasks(host, kind, params, state, created, updated, log) VALUES(?,?,?,?,?,?,?)",
                        (host, kind, json.dumps(params), "requested", now, now, json.dumps(log, ensure_ascii=False)))


def _finish(task, state, text, data=None):
    _log(task["id"], state, "ende", text, result={"text": text, "data": data})
    if task["kind"] == "app-preview":
        return  # Vorschau: kein Handy
    ok = state == "done"
    title = {"core-update": ("Bitcoin Core aktualisiert", "Update fehlgeschlagen"),
             "app-remove": ("Programm entfernt", "Entfernen fehlgeschlagen")}[task["kind"]][0 if ok else 1]
    notify.send(f"Heimzentrale: {title} ({task['host']})", text, priority=3 if ok else 4,
                tags=["white_check_mark" if ok else "warning"])


# ---------------------------------------------------------------- PIN

def pin_set():
    return bool(config.get("UPDATE_PIN_SHA256"))


def check_pin(pin):
    want = config.get("UPDATE_PIN_SHA256").lower()
    if not want:
        raise TaskError(403, "Noch keine PIN eingerichtet.")
    now = time.time()
    if PIN_FAILS["until"] > now:
        raise TaskError(429, "Zu viele falsche PINs. Die Knöpfe sind 15 Minuten gesperrt.")
    given = hashlib.sha256(str(pin or "").encode()).hexdigest()
    if isinstance(pin, str) and hmac.compare_digest(given, want):
        PIN_FAILS["count"] = 0
        return
    PIN_FAILS["count"] += 1
    if PIN_FAILS["count"] >= 5:
        PIN_FAILS.update(count=0, until=now + 900)
        notify.log("5 falsche PINs - Knöpfe 15 Minuten gesperrt")
    raise TaskError(403, "Falsche PIN.")


# ---------------------------------------------------------------- Von der Seite

def request(body):
    host, kind = body.get("host"), body.get("kind")
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    if not reports.valid_host(host) or kind not in KINDS:
        raise TaskError(400, "Ungültige Anfrage.")
    if kind != "app-preview":
        check_pin(body.get("pin"))
    if active(host):
        raise TaskError(409, f"Auf dem {host} läuft schon ein Auftrag. Bitte warten, bis er fertig ist.")
    m = reports.latest_metrics(host)
    if m is None:
        raise TaskError(404, f"Vom {host} ist noch keine Meldung da.")

    if kind == "core-update":
        version = params.get("version")
        inst = m.get("core_installed")
        if not isinstance(version, str) or not VER_RE.match(version) or not inst:
            raise TaskError(409, "Version unbekannt.")
        if version not in [o["version"] for o in offers(inst)]:
            raise TaskError(409, f"Version {version} wird für den {host} nicht angeboten.")
        return _create(host, kind, {"version": version, "from": inst},
                       f"Auftrag: Bitcoin Core {inst} → {version}. Der {host} holt ihn innerhalb von 2 Minuten ab.")

    typ, name = params.get("type"), params.get("name")
    prog = inventory.find(host, typ, name) if isinstance(typ, str) and isinstance(name, str) else None
    if not prog:
        raise TaskError(404, "Dieses Programm ist in der Liste nicht (mehr) vorhanden.")
    if prog["protected"]:
        raise TaskError(409, f"{prog['title']} ist geschützt und wird nicht entfernt: {prog['reason']}")
    if kind == "app-preview":
        return _create(host, kind, {"type": typ, "name": name, "title": prog["title"]},
                       f"Vorschau für {prog['title']} angefordert.")

    try:
        preview = get(int(params.get("preview")))
    except (TypeError, ValueError):
        preview = None
    data = (preview or {}).get("result") or {}
    data = data.get("data") or {}
    if (not preview or preview["host"] != host or preview["kind"] != "app-preview" or preview["state"] != "done"
            or preview["params"].get("type") != typ or preview["params"].get("name") != name):
        raise TaskError(409, "Bitte zuerst die Vorschau abwarten.")
    if time.time() - preview["updated"] > PREVIEW_VALID_S:
        raise TaskError(409, "Die Vorschau ist älter als 30 Minuten. Bitte neu anzeigen lassen.")
    if not data.get("allowed"):
        raise TaskError(409, "Laut Vorschau kann dieses Programm nicht sicher entfernt werden.")
    return _create(host, kind, {"type": typ, "name": name, "title": prog["title"], "preview": preview["id"],
                                "expect": data.get("packages") or []},
                   f"Auftrag: {prog['title']} entfernen. Der {host} holt ihn innerhalb von 2 Minuten ab.")


def cancel(body):
    host = body.get("host")
    t = active(host) if reports.valid_host(host) else None
    if not t:
        raise TaskError(409, "Kein offener Auftrag.")
    if t["state"] != "requested":
        raise TaskError(409, "Der Auftrag wurde schon abgeholt und läuft jetzt durch.")
    _log(t["id"], "cancelled", "abbruch", "Auftrag zurückgezogen.", result={"text": "Auftrag zurückgezogen."})


# ---------------------------------------------------------------- Vom Agenten

def next_for(host, peek=False):
    t = active(host)
    if not t or t["state"] != "requested":
        return None
    if not peek:
        _log(t["id"], "claimed", "abgeholt", f"Der {host} hat den Auftrag abgeholt.")
    return {"id": t["id"], "kind": t["kind"], "params": t["params"]}


def progress(body):
    try:
        task_id = int(body.get("job"))
    except (TypeError, ValueError):
        raise TaskError(400, "job fehlt") from None
    state = body.get("state")
    if state not in ("running", "done", "failed"):
        raise TaskError(400, "state ungültig")
    t = get(task_id)
    if not t:
        raise TaskError(404, "Auftrag unbekannt")
    if t["state"] not in ACTIVE:
        return False  # schon beendet (z. B. als gescheitert markiert)
    text = str(body.get("text") or "")
    if state == "running":
        _log(task_id, "running", body.get("step") or "", text)
    else:
        data = body.get("data") if isinstance(body.get("data"), dict) else None
        _finish(t, state, text, data)
    return True


def check_stale(now=None):
    now = now or time.time()
    for r in db.get().query("SELECT * FROM tasks WHERE state IN (?,?,?)", ACTIVE):
        t = _row(r)
        if t["state"] == "requested" and now - t["created"] > config.num("JOB_PICKUP_MIN") * 60:
            _finish(t, "failed", f"Der {t['host']} hat den Auftrag nicht abgeholt. Läuft dort der Agent "
                                 f"(heimzentrale-agent, crontab von root)?")
        elif t["state"] != "requested" and now - t["updated"] > config.num("JOB_STALE_MIN") * 60:
            _finish(t, "failed", f"Keine Rückmeldung vom {t['host']} seit {seit(now - t['updated'])}. "
                                 f"Dort nachsehen: sudo tail -n 40 /var/log/heimzentrale-agent.log")


def public(t):
    """Fuer die Seite (ohne interne Felder)."""
    if not t:
        return None
    return {"id": t["id"], "kind": t["kind"], "title": TITLES.get(t["kind"], t["kind"]), "state": t["state"],
            "params": {k: v for k, v in t["params"].items() if k != "expect"},
            "created": t["created"], "updated": t["updated"], "log": t["log"], "result": t["result"]}
