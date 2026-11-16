"""Tests fuer die Heimzentrale (Server). Start im Ordner app/:  python3 -m unittest -v"""
import hashlib
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

TMP = tempfile.mkdtemp(prefix="hz-test-")
os.environ["HZ_DATA"] = TMP
os.environ["STARTUP_GRACE_MIN"] = "0"

from hz import alerts, checks, config, core, db, inventory, metrics, nettip, notify, reports, status, tasks, web  # noqa: E402

GiB = 1024 ** 3
SENT = []


def fake_send(title, message, priority=4, tags=None):
    SENT.append((title, message))
    return True


notify.send = fake_send


def v2(host="pi", *, avail=50 * GiB, temp=45.0, bitcoin=None, docker=None, cpu=10.0):
    return {"v": 2, "agent": "2.0.0", "host": host, "ts": int(time.time()),
            "device": {"model": "Raspberry Pi 4 Model B Rev 1.5", "os": "Debian", "ip": "192.168.1.5"},
            "system": {"cpu": {"percent": cpu, "cores": 4, "load": [0.1, 0.2, 0.3]},
                       "mem": {"total": 4 * GiB, "available": 3 * GiB, "swap_total": 0, "swap_used": 0},
                       "disks": [{"mount": "/", "size": 100 * GiB, "used": 100 * GiB - avail, "avail": avail}],
                       "temp_c": temp, "throttled": "0x0", "uptime_s": 1000, "net": {"iface": "wlan0", "rx": 1000, "tx": 500}},
            "docker": docker, "bitcoin": bitcoin}


def btc(height=975_398, version="31.1.0", service="active"):
    return {"service": service, "error": "",
            "blockchain": {"blocks": height, "headers": height, "time": int(time.time()) - 300, "initialblockdownload": False,
                           "verificationprogress": 1, "warnings": []},
            "network": {"subversion": f"/Satoshi:{version}/", "connections": 10, "connections_in": 0, "connections_out": 10},
            "mempool": {"size": 10, "bytes": 1000, "usage": 2000, "maxmempool": 300_000_000},
            "nettotals": {"totalbytesrecv": 1, "totalbytessent": 1}, "uptime_s": 100}


class Base(unittest.TestCase):
    def setUp(self):
        db.use(os.path.join(TMP, f"{self._testMethodName}.db"))
        config.reload()
        SENT.clear()
        tasks.PIN_FAILS.update(count=0, until=0)
        nettip.NET.update(tip=None, ts=0, source=None, error=None)
        core.CORE.update(versions=[], ts=0, source=None, error=None)
        alerts.STARTED = 0

    def set_conf(self, **kw):
        for k, v in kw.items():
            os.environ[k] = str(v)
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in kw])
        config.reload()


class TestConfigAndMetrics(Base):
    def test_read_file(self):
        p = os.path.join(TMP, "x.conf")
        with open(p, "w") as f:
            f.write("# Kommentar\nA=1\nexport B = 'zwei'\n\nC=\"drei\"\nkaputt\n")
        self.assertEqual(config.read_file(p), {"A": "1", "B": "zwei", "C": "drei"})

    def test_extract_v1(self):
        m = metrics.extract({"host": "btcnode", "melder": 1, "system": {"temp_c": 47.2, "throttled": "0x0",
                             "disk": {"size": 100, "used": 60, "avail": 40}, "mem_kb": {"total": 1000, "available": 250},
                             "load": [0.1, 0.2, 0.3], "uptime_s": 5}, "bitcoin": btc()})
        self.assertEqual(m["version"], 1)
        self.assertEqual(m["disk_avail"], 40)
        self.assertEqual(m["mem_total"], 1000 * 1024)
        self.assertAlmostEqual(m["mem_pct"], 75.0)
        self.assertEqual(m["core_installed"], "31.1.0")
        self.assertTrue(m["has_bitcoin"])

    def test_extract_v2_with_docker(self):
        m = metrics.extract(v2(docker={"available": True, "containers": [
            {"name": "b", "image": "x", "state": "running", "status": "Up"}, {"name": "a", "state": "exited"}]}))
        self.assertEqual(m["version"], 2)
        self.assertEqual([c["name"] for c in m["docker"]], ["a", "b"])
        self.assertEqual(m["cpu_pct"], 10.0)
        self.assertFalse(m["has_bitcoin"])

    def test_extract_garbage_is_safe(self):
        m = metrics.extract({"host": "x", "system": "kaputt", "bitcoin": [1], "docker": 5})
        self.assertIsNone(m["disk_avail"])
        self.assertIsNone(m["docker"])


class TestChecksAndAlerts(Base):
    def test_disk_warn_then_crit_then_resolve(self):
        reports.store(v2(avail=25 * GiB))
        alerts.run()
        self.assertIn("Speicherplatz wird knapp", SENT[-1][0])
        reports.store(v2(avail=9 * GiB), now=time.time() + 120)
        alerts.run()
        self.assertIn("fast voll", SENT[-1][0])
        n = len(SENT)
        reports.store(v2(avail=10.5 * GiB), now=time.time() + 240)  # Puffer: bleibt dringend
        alerts.run()
        self.assertEqual(len(SENT), n)
        reports.store(v2(avail=80 * GiB), now=time.time() + 360)
        alerts.run()
        self.assertIn("wieder in Ordnung", SENT[-1][0])

    def test_silent_does_not_resolve_other_alerts(self):
        reports.store(v2(avail=25 * GiB))
        alerts.run()
        db.get().run("UPDATE latest SET received = received - 3600")
        alerts.run()
        titles = [t for t, _ in SENT]
        self.assertTrue(any("meldet sich nicht" in t for t in titles))
        self.assertFalse(any("wieder in Ordnung" in t for t in titles))

    def test_behind_needs_delay(self):
        reports.store(v2(bitcoin=btc(height=1_000_000)))
        nettip.NET.update(tip=1_000_005, ts=time.time())
        alerts.run()
        self.assertFalse(any("hinter" in t for t, _ in SENT))
        db.get().run("UPDATE alerts SET first_seen = first_seen - 3600 WHERE key LIKE '%:blocks'")
        alerts.run()
        self.assertTrue(any("Hängt hinter dem Netz" in t for t, _ in SENT))

    def test_own_alarms_only_shown_other_pi_notified(self):
        p = v2("btcnode", temp=80, bitcoin=btc())
        p["own_alarms"] = True
        reports.store(p)
        reports.store(v2("argon", temp=80))
        alerts.run()
        titles = [t for t, _ in SENT]
        self.assertTrue(any("Sehr warm (argon)" in t for t in titles))
        self.assertFalse(any("Sehr warm (btcnode)" in t for t in titles))

    def test_core_update_hides_service_down(self):
        reports.store(v2("btcnode", bitcoin=btc(service="inactive")))
        db.get().run("INSERT INTO tasks(host, kind, params, state, created, updated) VALUES('btcnode','core-update','{}','running',?,?)",
                     (int(time.time()), int(time.time())))
        f = checks.evaluate()[0]["findings"]
        self.assertEqual([x["kind"] for x in f], ["updating"])


class TestCoreVersions(Base):
    def test_parse_github_and_listing(self):
        gh = json.dumps([{"tag_name": "v32.1"}, {"tag_name": "v32.0rc1", "prerelease": True}, {"tag_name": "v31.2"},
                         {"tag_name": "v0.21.0"}, {"tag_name": "nightly"}])
        self.assertEqual(core.parse_versions(gh), ["31.2", "32.1"])
        listing = '<a href="bitcoin-core-31.2/">x</a><a href="bitcoin-core-32.0rc1/">y</a><a href="bitcoin-core-30.4/">'
        self.assertEqual(core.parse_versions(listing), ["30.4", "31.2"])

    def test_offers(self):
        core.CORE["versions"] = ["30.4", "31.1", "31.2", "32.0", "32.1"]
        self.assertEqual([o["version"] for o in core.offers("31.1.0")], ["31.2", "32.1"])
        self.assertTrue(core.offers("31.1.0")[1]["major"])
        self.assertEqual([o["version"] for o in core.offers("32.1")], [])
        self.assertEqual([o["version"] for o in core.offers("31.2.0")], ["32.1"])


class TestTasks(Base):
    def setUp(self):
        super().setUp()
        self.set_conf(UPDATE_PIN_SHA256=hashlib.sha256(b"4711").hexdigest())
        core.CORE["versions"] = ["31.1", "31.2", "32.1"]
        reports.store(v2("btcnode", bitcoin=btc()))
        reports.store(v2("argon"))
        inventory.store("argon", {"programs": [
            {"type": "apt", "name": "gimp", "title": "GIMP", "size": 100},
            {"type": "apt", "name": "lxterminal", "title": "Terminal", "protected": True, "reason": "System"},
            {"type": "kaputt", "name": "x"}]})

    def test_pin_and_lockout(self):
        with self.assertRaises(tasks.TaskError) as e:
            tasks.request({"host": "btcnode", "kind": "core-update", "params": {"version": "31.2"}, "pin": "0000"})
        self.assertEqual(e.exception.code, 403)
        for _ in range(4):
            with self.assertRaises(tasks.TaskError):
                tasks.check_pin("0000")
        with self.assertRaises(tasks.TaskError) as e:
            tasks.check_pin("4711")
        self.assertEqual(e.exception.code, 429)

    def test_core_update_flow(self):
        with self.assertRaises(tasks.TaskError):
            tasks.request({"host": "btcnode", "kind": "core-update", "params": {"version": "40.0"}, "pin": "4711"})
        tid = tasks.request({"host": "btcnode", "kind": "core-update", "params": {"version": "31.2"}, "pin": "4711"})
        with self.assertRaises(tasks.TaskError) as e:  # nur ein Auftrag je Pi
            tasks.request({"host": "btcnode", "kind": "core-update", "params": {"version": "32.1"}, "pin": "4711"})
        self.assertEqual(e.exception.code, 409)
        self.assertEqual(tasks.next_for("btcnode", peek=True)["id"], tid)
        job = tasks.next_for("btcnode")
        self.assertEqual(job["params"]["version"], "31.2")
        self.assertIsNone(tasks.next_for("btcnode"))
        tasks.progress({"job": tid, "state": "running", "step": "laden", "text": "Lade"})
        tasks.progress({"job": tid, "state": "done", "text": "Bitcoin Core 31.2 läuft"})
        self.assertEqual(tasks.get(tid)["state"], "done")
        self.assertTrue(any("aktualisiert" in t for t, _ in SENT))
        self.assertFalse(tasks.progress({"job": tid, "state": "failed", "text": "zu spät"}))

    def test_app_remove_requires_good_preview(self):
        with self.assertRaises(tasks.TaskError):
            tasks.request({"host": "argon", "kind": "app-preview", "params": {"type": "apt", "name": "lxterminal"}})
        pid = tasks.request({"host": "argon", "kind": "app-preview", "params": {"type": "apt", "name": "gimp"}})
        tasks.next_for("argon")
        with self.assertRaises(tasks.TaskError):  # Vorschau noch nicht fertig
            tasks.request({"host": "argon", "kind": "app-remove", "params": {"type": "apt", "name": "gimp", "preview": pid}, "pin": "4711"})
        tasks.progress({"job": pid, "state": "done", "text": "2 Pakete", "data": {"allowed": True, "packages": ["gimp", "gimp-data"]}})
        rid = tasks.request({"host": "argon", "kind": "app-remove", "params": {"type": "apt", "name": "gimp", "preview": pid}, "pin": "4711"})
        job = tasks.next_for("argon")
        self.assertEqual(job["id"], rid)
        self.assertEqual(job["params"]["expect"], ["gimp", "gimp-data"])
        self.assertNotIn("expect", tasks.public(tasks.get(rid))["params"])

    def test_preview_not_allowed_blocks_remove(self):
        pid = tasks.request({"host": "argon", "kind": "app-preview", "params": {"type": "apt", "name": "gimp"}})
        tasks.next_for("argon")
        tasks.progress({"job": pid, "state": "done", "text": "nein", "data": {"allowed": False, "packages": ["gimp", "libc6"]}})
        with self.assertRaises(tasks.TaskError):
            tasks.request({"host": "argon", "kind": "app-remove", "params": {"type": "apt", "name": "gimp", "preview": pid}, "pin": "4711"})

    def test_stale_tasks_fail(self):
        tid = tasks.request({"host": "argon", "kind": "app-preview", "params": {"type": "apt", "name": "gimp"}})
        tasks.check_stale(time.time() + 3600)
        self.assertEqual(tasks.get(tid)["state"], "failed")

    def test_cancel_only_before_pickup(self):
        tasks.request({"host": "argon", "kind": "app-preview", "params": {"type": "apt", "name": "gimp"}})
        tasks.cancel({"host": "argon"})
        self.assertIsNone(tasks.active("argon"))
        tasks.request({"host": "argon", "kind": "app-preview", "params": {"type": "apt", "name": "gimp"}})
        tasks.next_for("argon")
        with self.assertRaises(tasks.TaskError):
            tasks.cancel({"host": "argon"})


class TestStatus(Base):
    def test_history_rates_and_forecast(self):
        t0 = int(time.time()) - 86400
        for i in range(0, 288):
            p = v2(avail=int((60 - i * 0.01) * GiB))
            p["system"]["net"].update(rx=i * 300 * 1000, tx=i * 300 * 500)
            reports.store(p, now=t0 + i * 300)
        h = status.history("pi", "24h")
        i_rx = h["fields"].index("rx")
        rates = [p[i_rx] for p in h["points"] if p[i_rx] is not None]
        self.assertTrue(rates and all(abs(r - 1000) < 1 for r in rates))
        f = status.disk_forecast("pi", 57 * GiB, time.time())
        self.assertTrue(f["ready"])
        self.assertLess(f["per_day"], 0)
        s = status.build()
        self.assertEqual(s["devices"][0]["host"], "pi")
        self.assertIn("forecast", s["devices"][0]["derived"])


class TestWeb(Base):
    @classmethod
    def setUpClass(cls):
        cls.httpd = web.make_server(0, "127.0.0.1")
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def req(self, path, method="GET", body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def test_pages_and_static(self):
        code, headers, body = self.req("/")
        self.assertEqual(code, 200)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(self.req("/js/main.js")[0], 200)
        self.assertEqual(self.req("/css/app.css")[1]["Content-Type"], "text/css; charset=utf-8")
        for bad in ("/../server.py", "/css/../../hz/db.py", "/.hidden", "/hz/db.py", "/js/../../server.py"):
            self.assertEqual(self.req(bad)[0], 404, bad)

    def test_agent_needs_token(self):
        self.set_conf(HZ_TOKEN="abcdefabcdefabcd")
        self.assertEqual(self.req("/api/report", "POST", v2(), {"Content-Type": "application/json"})[0], 401)
        code, _, body = self.req("/api/report", "POST", v2(), {"Content-Type": "application/json", "X-Token": "abcdefabcdefabcd"})
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["host"], "pi")
        code, _, body = self.req("/api/agent/job?host=pi", headers={"X-Token": "abcdefabcdefabcd"})
        self.assertEqual(json.loads(body), {"job": None})

    def test_browser_posts_need_json(self):
        code, _, _ = self.req("/api/tasks", "POST", {"host": "pi"}, {"Content-Type": "text/plain"})
        self.assertEqual(code, 415)
        code, _, body = self.req("/api/tasks", "POST", {"host": "pi", "kind": "nix"}, {"Content-Type": "application/json"})
        self.assertEqual(code, 400)
        self.assertIn("error", json.loads(body))

    def test_connect_needs_pin(self):
        self.set_conf(HZ_TOKEN="abcdefabcdefabcd", UPDATE_PIN_SHA256=hashlib.sha256(b"1234").hexdigest(),
                      PUBLIC_URL="http://192.168.1.10:8088")
        self.assertEqual(self.req("/api/connect", "POST", {"pin": "0000"}, {"Content-Type": "application/json"})[0], 403)
        code, _, body = self.req("/api/connect", "POST", {"pin": "1234"}, {"Content-Type": "application/json"})
        self.assertEqual(code, 200)
        self.assertIn("agent http://192.168.1.10:8088 abcdefabcdefabcd", json.loads(body)["command"])


if __name__ == "__main__":
    unittest.main()
