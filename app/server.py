#!/usr/bin/env python3
"""Heimzentrale - Startpunkt.

  python server.py             Dienst starten (Port aus heimzentrale.conf, Standard 8088)
  python server.py test-ntfy   Testmeldung aufs Handy schicken
  python server.py status      Kurzbericht im Terminal
  python server.py pin         neue PIN fuer Update- und Entfernen-Knoepfe setzen (fragt danach)
"""
import getpass
import hashlib
import re
import sys

from hz import VERSION, config, core, db, nettip, notify, status, web, worker
from hz.fmt import de_gb


def serve():
    db.get()
    core.load_cache()
    port = int(config.num("PORT")) if config.get("PORT").isdigit() else 8088
    if not config.get("HZ_TOKEN"):
        notify.log("WARNUNG: HZ_TOKEN fehlt in", config.DATA_DIR / "heimzentrale.conf", "- Meldungen werden abgelehnt")
    if not notify.ready():
        notify.log("Hinweis: NTFY_TOPIC fehlt - keine Handy-Meldungen (Datei", config.DATA_DIR / "ntfy.conf", ")")
    worker.start()
    httpd = web.make_server(port)
    notify.log(f"Heimzentrale {VERSION} läuft auf Port {port}")
    httpd.serve_forever()


def report():
    nettip.fetch()
    core.load_cache()
    s = status.build()
    print(f"Heimzentrale {VERSION} · Handy-Meldungen: {'ja' if s['ntfy'] else 'NEIN (NTFY_TOPIC fehlt)'}"
          f" · PIN: {'eingerichtet' if s['pin'] else 'fehlt'}")
    print(f"Netz-Blockhöhe: {s['network']['tip'] or '?'} ({s['network']['source'] or s['network']['error']})")
    if not s["devices"]:
        print("Noch keine Meldung von einem Pi angekommen.")
    for d in s["devices"]:
        m = d["metrics"]
        free = de_gb(m["disk_avail"]) if m.get("disk_avail") is not None else "?"
        print(f"- {d['host']}: letzte Meldung vor {int(d['age'])} s, frei {free}, CPU {m.get('cpu_pct')} %")
        for f in d["findings"]:
            print(f"    [{f['level']}] {f['title']}: {f['text']}")


def set_pin():
    pin = getpass.getpass("Neue PIN (4 bis 8 Ziffern): ")
    if not re.fullmatch(r"\d{4,8}", pin):
        sys.exit("Ungültig: nur 4 bis 8 Ziffern.")
    if getpass.getpass("PIN wiederholen: ") != pin:
        sys.exit("Die beiden Eingaben sind verschieden.")
    path = config.DATA_DIR / "heimzentrale.conf"
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.startswith("UPDATE_PIN_SHA256=")] \
        if path.exists() else []
    lines.append("UPDATE_PIN_SHA256=" + hashlib.sha256(pin.encode()).hexdigest())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("PIN gespeichert. Sie gilt spätestens nach einer Minute.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "serve":
        serve()
    elif cmd == "test-ntfy":
        ok = notify.send("Heimzentrale: Test", "Die Heimzentrale kann dir Meldungen aufs Handy schicken.",
                         priority=3, tags=["white_check_mark"])
        print("OK: Testmeldung gesendet" if ok else "FEHLER: Testmeldung nicht gesendet (siehe oben)")
        sys.exit(0 if ok else 1)
    elif cmd == "status":
        report()
    elif cmd == "pin":
        set_pin()
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
