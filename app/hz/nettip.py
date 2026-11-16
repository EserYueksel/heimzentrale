"""Aktuelle Blockhoehe des Bitcoin-Netzes (mempool.space, Ersatz blockstream.info)."""
import time
import urllib.parse
import urllib.request

from . import VERSION, config

NET = {"tip": None, "ts": 0, "source": None, "error": None}


def fetch():
    err = None
    for url in config.url_list("TIP_URLS"):
        host = urllib.parse.urlsplit(url).hostname
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"heimzentrale/{VERSION}"})
            with urllib.request.urlopen(req, timeout=15) as r:
                val = int(r.read(64).decode().strip())
            if 800_000 < val < 10_000_000:
                NET.update(tip=val, ts=int(time.time()), source=host, error=None)
                return True
            err = f"{host}: unerwartete Antwort {val}"
        except Exception as e:  # noqa: BLE001 - jede Stoerung ist hier gleich
            err = f"{host}: {e}"
    NET["error"] = err
    return False


def fresh(now):
    """Blockhoehe, wenn sie hoechstens 30 Minuten alt ist, sonst None."""
    return NET["tip"] if NET["tip"] and now - NET["ts"] < 1800 else None
