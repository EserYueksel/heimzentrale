"""Bitcoin-Core-Versionen: Liste holen, Angebote fuer einen Node, Hinweis aufs Handy."""
import json
import re
import time
import urllib.parse
import urllib.request

from . import VERSION, config, db, notify, reports

VER_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
CORE = {"versions": [], "ts": 0, "source": None, "error": None}


def vtuple(v):
    parts = [int(x) for x in str(v).split(".")]
    return tuple((parts + [0, 0, 0])[:3])


def parse_versions(raw):
    """Fertige Versionen aus GitHub-JSON oder dem Verzeichnis von bitcoincore.org/bin/."""
    found = set()
    if raw.lstrip().startswith("["):
        for rel in json.loads(raw):
            tag = str(rel.get("tag_name", ""))
            if rel.get("draft") or rel.get("prerelease"):
                continue
            if tag.startswith("v") and VER_RE.match(tag[1:]):
                found.add(tag[1:])
    else:
        found.update(re.findall(r"bitcoin-core-(\d+\.\d+(?:\.\d+)?)/", raw))
    return sorted((v for v in found if vtuple(v)[0] >= 22), key=vtuple)


def load_cache():
    try:
        cached = json.loads(db.get().kv_get("core_versions", "") or "{}")
    except ValueError:
        return
    if cached.get("versions"):
        CORE.update(cached)


def fetch():
    err = None
    for url in config.url_list("VERSION_URLS"):
        src = urllib.parse.urlsplit(url).hostname
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"heimzentrale/{VERSION}",
                                                       "Accept": "application/vnd.github+json, text/html"})
            with urllib.request.urlopen(req, timeout=20) as r:
                found = parse_versions(r.read(3_000_000).decode("utf-8", "replace"))
            if found:
                CORE.update(versions=found, ts=int(time.time()), source=src, error=None)
                db.get().kv_set("core_versions", json.dumps(CORE))
                return True
            err = f"{src}: keine Versionen gefunden"
        except Exception as e:  # noqa: BLE001
            err = f"{src}: {e}"
    CORE["error"] = err
    return False


def offers(installed):
    """Neueste Version der eigenen Reihe und neueste Version ueberhaupt (wenn neuer als installiert)."""
    if not installed or not CORE["versions"]:
        return []
    inst = vtuple(installed)
    newer = [v for v in CORE["versions"] if vtuple(v) > inst]
    same = [v for v in newer if vtuple(v)[0] == inst[0]]
    picks = ([max(same, key=vtuple)] if same else []) + ([max(newer, key=vtuple)] if newer else [])
    out = []
    for v in picks:
        if v not in [o["version"] for o in out]:
            out.append({"version": v, "major": vtuple(v)[0] > inst[0],
                        "notes": f"https://bitcoincore.org/en/releases/{v}/"})
    return out


def notice():
    """Einmal pro neuer Version aufs Handy melden."""
    for host, _received, _payload, m in reports.latest_all():
        found = offers(m.get("core_installed"))
        if not found:
            continue
        newest = found[-1]["version"]
        key = f"core_notified:{host}"
        if db.get().kv_get(key) == newest:
            continue
        names = " und ".join(o["version"] for o in found)
        if notify.send(f"Heimzentrale: Bitcoin Core {newest} verfügbar ({host})",
                       f"Installiert ist {m.get('core_installed')}. Neu: {names}. Update über die Heimzentrale möglich. "
                       f"Vorher die Release Notes lesen: bitcoincore.org/en/releases/{newest}/",
                       priority=3, tags=["package"]):
            db.get().kv_set(key, newest)


def summary(m):
    return {"installed": m.get("core_installed"), "offers": offers(m.get("core_installed")),
            "checked": CORE["ts"] or None, "source": CORE["source"], "error": CORE["error"]}
