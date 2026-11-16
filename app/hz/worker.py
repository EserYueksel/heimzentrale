"""Hintergrund: jede Minute pruefen, melden, aufraeumen."""
import threading
import time
import traceback

from . import alerts, config, core, db, nettip, notify, tasks


def tick(state, now=None):
    now = now or time.time()
    config.reload()
    if now - state.get("tip", 0) >= 300:
        if not nettip.fetch() and nettip.NET["error"]:
            notify.log("Netz-Blockhöhe nicht abrufbar:", nettip.NET["error"])
        state["tip"] = now
    alerts.run(now)
    tasks.check_stale(now)
    if now - state.get("versions", 0) >= 6 * 3600:
        if not core.fetch() and core.CORE["error"]:
            notify.log("Bitcoin-Core-Versionen nicht abrufbar:", core.CORE["error"])
        state["versions"] = now
    if now - alerts.STARTED >= config.num("STARTUP_GRACE_MIN") * 60:
        core.notice()
    if now - state.get("prune", 0) >= 86400:
        db.get().run("DELETE FROM samples WHERE ts < ?", (int(now - config.num("KEEP_DAYS") * 86400),))
        db.get().run("DELETE FROM tasks WHERE updated < ? AND state NOT IN ('requested','claimed','running')",
                     (int(now - 180 * 86400),))
        state["prune"] = now


def loop():
    state = {}
    while True:
        try:
            tick(state)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        time.sleep(60)


def start():
    threading.Thread(target=loop, name="worker", daemon=True).start()
