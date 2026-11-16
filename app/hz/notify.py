"""Handy-Meldungen ueber ntfy (JSON-Veroeffentlichung, damit Umlaute sicher ankommen)."""
import json
import time
import urllib.request

from . import VERSION, config


def log(*args):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *args, flush=True)


def ready():
    return bool(config.get("NTFY_TOPIC"))


def send(title, message, priority=4, tags=None):
    """True, wenn ntfy die Nachricht angenommen hat."""
    topic = config.get("NTFY_TOPIC")
    if not topic:
        log("ntfy: NTFY_TOPIC fehlt - nicht gesendet:", title)
        return False
    body = json.dumps({"topic": topic, "title": title, "message": message,
                       "priority": priority, "tags": tags or []}).encode("utf-8")
    req = urllib.request.Request(config.get("NTFY_SERVER").rstrip("/"), data=body, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": f"heimzentrale/{VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read(256)
        log("ntfy gesendet:", title)
        return True
    except Exception as e:  # noqa: BLE001
        log("ntfy fehlgeschlagen:", title, "-", e)
        return False
