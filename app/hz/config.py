"""Einstellungen.

Gelesen werden (spaetere Dateien ueberschreiben fruehere):
  /data/ntfy.conf          Kanal fuer die Handy-Meldungen (vom btcnode kopiert)
  /data/heimzentrale.conf  alles andere
Umgebungsvariablen mit gleichem Namen gehen vor. Die Dateien werden jede Minute neu gelesen.
"""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("HZ_DATA", "/data"))

DEFAULTS = {
    "PORT": "8088",
    "HZ_TOKEN": "",
    "NTFY_SERVER": "https://ntfy.sh",
    "NTFY_TOPIC": "",
    # Speicher: Warnung / dringend, wenn weniger frei (GB)
    "DISK_WARN_GB": "30",
    "DISK_CRIT_GB": "10",
    # so lange ohne Meldung = Pi meldet sich nicht (Minuten)
    "SILENT_MIN": "20",
    # Node haengt hinterher: ab so vielen Bloecken, wenn es so lange anhaelt
    "BEHIND_BLOCKS": "3",
    "BEHIND_MIN": "20",
    # ohne Netz-Blockhoehe: so lange kein neuer Block = Alarm (Stunden)
    "STALE_HOURS": "3",
    "TEMP_WARN": "70",
    "TEMP_CRIT": "75",
    "CPU_WARN": "90",
    "MEM_WARN": "90",
    "KEEP_DAYS": "400",
    "STARTUP_GRACE_MIN": "10",
    "TIP_URLS": "https://mempool.space/api/blocks/tip/height,https://blockstream.info/api/blocks/tip/height",
    "VERSION_URLS": "https://api.github.com/repos/bitcoin/bitcoin/releases?per_page=40,https://bitcoincore.org/bin/",
    # sha256 der PIN fuer Update- und Entfernen-Knoepfe (leer = Knoepfe gesperrt)
    "UPDATE_PIN_SHA256": "",
    # Auftrag nicht abgeholt / keine Rueckmeldung (Minuten)
    "JOB_PICKUP_MIN": "15",
    "JOB_STALE_MIN": "90",
    # Reihenfolge der Pis in der Uebersicht (Rest alphabetisch dahinter)
    "DEVICE_ORDER": "",
    # Adresse der Heimzentrale im Heimnetz, fuer den Befehl "Pi hinzufuegen"
    "PUBLIC_URL": "",
}

_current = dict(DEFAULTS)


def read_file(path):
    """SCHLUESSEL=Wert-Datei lesen. Kommentare (#) und Leerzeilen werden uebersprungen."""
    out = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, IsADirectoryError):
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[7:].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key] = value
    return out


def reload():
    global _current
    cfg = dict(DEFAULTS)
    for name in ("ntfy.conf", "heimzentrale.conf"):
        cfg.update(read_file(DATA_DIR / name))
    for key in DEFAULTS:
        if key in os.environ:
            cfg[key] = os.environ[key]
    _current = cfg
    return cfg


def get(key):
    return str(_current.get(key, DEFAULTS.get(key, ""))).strip()


def num(key):
    try:
        return float(_current.get(key, DEFAULTS[key]))
    except (TypeError, ValueError):
        return float(DEFAULTS[key])


def url_list(key):
    return [u.strip() for u in get(key).split(",") if u.strip()]


reload()
