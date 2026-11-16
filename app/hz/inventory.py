"""Installierte Programme je Pi (vom Agenten gemeldet)."""
import json
import time

from . import db
from .metrics import as_int, as_str

TYPES = ("apt", "flatpak")


def _program(p):
    if not isinstance(p, dict) or p.get("type") not in TYPES:
        return None
    name = as_str(p.get("name"), 200)
    if not name:
        return None
    return {
        "type": p["type"],
        "name": name,
        "title": as_str(p.get("title"), 120) or name,
        "summary": as_str(p.get("summary"), 300) or "",
        "version": as_str(p.get("version"), 80) or "",
        "size": as_int(p.get("size")),
        "protected": bool(p.get("protected")),
        "reason": as_str(p.get("reason"), 200) or "",
    }


def store(host, body):
    programs = [x for x in (_program(p) for p in (body.get("programs") or [])[:1000]) if x]
    programs.sort(key=lambda p: p["title"].lower())
    db.get().run("INSERT INTO inventory(host, updated, data) VALUES(?,?,?) "
                 "ON CONFLICT(host) DO UPDATE SET updated=excluded.updated, data=excluded.data",
                 (host, int(time.time()), json.dumps({"programs": programs}, ensure_ascii=False)))
    return len(programs)


def get(host):
    row = db.get().one("SELECT updated, data FROM inventory WHERE host=?", (host,))
    if not row:
        return None
    data = json.loads(row["data"])
    data["updated"] = row["updated"]
    return data


def hosts_with_inventory():
    """{host: {"updated", "count"}}"""
    out = {}
    for r in db.get().query("SELECT host, updated, data FROM inventory"):
        try:
            count = len(json.loads(r["data"]).get("programs", []))
        except ValueError:
            count = 0
        out[r["host"]] = {"updated": r["updated"], "count": count}
    return out


def find(host, typ, name):
    inv = get(host)
    if not inv:
        return None
    for p in inv["programs"]:
        if p["type"] == typ and p["name"] == name:
            return p
    return None
