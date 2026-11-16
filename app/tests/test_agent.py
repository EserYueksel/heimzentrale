"""Tests fuer den Agenten. Start im Ordner app/:  python3 -m unittest -v
Echte Signaturpruefung mit guix.sigs (braucht Internet):  HZ_NET_TESTS=1 python3 -m unittest tests.test_agent"""
import importlib.machinery
import importlib.util
import io
import os
import tarfile
import tempfile
import unittest
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="hz-agent-test-")
os.environ["HZ_AGENT_STATE"] = os.path.join(TMP, "state")
os.environ["HZ_AGENT_LOG"] = os.path.join(TMP, "agent.log")
os.environ["HZ_AGENT_CONF"] = os.path.join(TMP, "agent.conf")
os.makedirs(os.environ["HZ_AGENT_STATE"], exist_ok=True)

_path = str(Path(__file__).resolve().parent.parent / "agent" / "heimzentrale-agent")
_loader = importlib.machinery.SourceFileLoader("hz_agent", _path)
_spec = importlib.util.spec_from_loader("hz_agent", _loader)
agent = importlib.util.module_from_spec(_spec)
_loader.exec_module(agent)

APT_SIM = """NOTE: This is only a simulation!
Reading package lists...
Purg gimp [2.10.38-1]
Purg gimp-data [2.10.38-1]
Remv libgimp2.0 [2.10.38-1]
"""
DPKG_W = ("gimp\t2.10.38-1\t20480\toptional\tno\tii \tGNU Image Manipulation Program\n"
          "gimp-data\t2.10.38-1\t102400\toptional\tno\tii \tData files for GIMP\n"
          "libgimp2.0\t2.10.38-1\t11264\toptional\tno\tii \tLibraries for GIMP\n"
          "libc6\t2.41-1\t12000\trequired\tno\tii \tGNU C Library\n")


class FakeRun:
    """Ersetzt agent.run: antwortet je nach Befehl."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, cmd, timeout=60, env=None):
        self.calls.append(cmd)
        for key, ans in self.answers.items():
            if " ".join(cmd).startswith(key):
                return ans(cmd) if callable(ans) else ans
        return 127, "", "nicht gefunden"


def dpkg_w(cmd):
    wanted = set(cmd[3:])
    lines = [ln for ln in DPKG_W.splitlines() if ln.split("\t")[0] in wanted]
    return 0, "\n".join(lines) + "\n", ""


class TestPrograms(unittest.TestCase):
    def setUp(self):
        self.orig = agent.run

    def tearDown(self):
        agent.run = self.orig

    def test_protection(self):
        self.assertTrue(agent.protection("lxterminal", {}))
        self.assertTrue(agent.protection("raspberrypi-ui-mods", {}))
        self.assertTrue(agent.protection("libc6", {"priority": "required"}))
        self.assertTrue(agent.protection("busybox", {"essential": True}))
        self.assertEqual(agent.protection("gimp", {"priority": "optional"}), "")

    def test_apt_simulate_parses_removals(self):
        agent.run = FakeRun({"apt-get -s": (0, APT_SIM, "")})
        self.assertEqual(agent.apt_simulate("gimp"), (["gimp", "gimp-data", "libgimp2.0"], ""))
        agent.run = FakeRun({"apt-get -s": (0, "Inst foo [1]\nPurg gimp [1]\n", "")})
        removed, err = agent.apt_simulate("gimp")
        self.assertIsNone(removed)
        self.assertIn("installieren", err)

    def test_preview_allowed(self):
        agent.run = FakeRun({"apt-get -s": (0, APT_SIM, ""), "dpkg-query -W": dpkg_w})
        ok, text, data = agent.preview({"type": "apt", "name": "gimp"})
        self.assertTrue(ok and data["allowed"])
        self.assertEqual(data["size"], (20480 + 102400 + 11264) * 1024)
        self.assertIn("3 Paket", text)

    def test_preview_blocked_by_protected_dependency(self):
        agent.run = FakeRun({"apt-get -s": (0, APT_SIM + "Remv libc6 [2.41-1]\n", ""), "dpkg-query -W": dpkg_w})
        ok, text, data = agent.preview({"type": "apt", "name": "gimp"})
        self.assertTrue(ok)
        self.assertFalse(data["allowed"])
        self.assertEqual(data["blocked"][0]["name"], "libc6")

    def test_preview_rejects_bad_names(self):
        self.assertFalse(agent.preview({"type": "apt", "name": "gimp; rm -rf /"})[0])
        self.assertFalse(agent.preview({"type": "snap", "name": "x"})[0])

    def test_remove_stops_when_changed_since_preview(self):
        fake = FakeRun({"apt-get -s": (0, APT_SIM, ""), "dpkg-query -W": dpkg_w, "apt-get -y": (0, "", "")})
        agent.run = fake
        ok, text = agent.remove({"type": "apt", "name": "gimp", "expect": ["gimp"]}, lambda *a: None)
        self.assertFalse(ok)
        self.assertIn("geändert", text)
        self.assertFalse(any(c[:2] == ["apt-get", "-y"] for c in fake.calls))

    def test_remove_runs_apt_and_checks(self):
        state = {"removed": False}

        def apt_y(cmd):
            state["removed"] = True
            return 0, "", ""

        def dpkg(cmd):
            rc, out, err = dpkg_w(cmd)
            return (rc, out.replace("\tii \t", "\tpn \t"), err) if state["removed"] else (rc, out, err)

        fake = FakeRun({"apt-get -s": (0, APT_SIM, ""), "dpkg-query -W": dpkg, "apt-get -y": apt_y})
        agent.run = fake
        ok, text = agent.remove({"type": "apt", "name": "gimp", "title": "GIMP", "expect": ["gimp", "gimp-data", "libgimp2.0"]},
                                lambda *a: None)
        self.assertTrue(ok, text)
        self.assertIn("GIMP wurde entfernt", text)

    def test_desktop_entries_and_programs(self):
        d = os.path.join(TMP, "apps")
        os.makedirs(d, exist_ok=True)
        Path(d, "gimp.desktop").write_text("[Desktop Entry]\nType=Application\nName=GIMP\nName[de]=GIMP-Bildbearbeitung\nComment=Bilder\n")
        Path(d, "hidden.desktop").write_text("[Desktop Entry]\nType=Application\nName=X\nNoDisplay=true\n")
        Path(d, "broken.desktop").write_text("kein ini")
        entries = agent.desktop_entries((d,))
        self.assertEqual(list(entries.values()), [{"title": "GIMP-Bildbearbeitung", "summary": "Bilder"}])
        gimp_path = os.path.join(d, "gimp.desktop")
        agent.run = FakeRun({"dpkg-query -S": (0, f"gimp: {gimp_path}\n", ""), "dpkg-query -W": dpkg_w, "flatpak": (127, "", "")})
        orig = agent.desktop_entries
        agent.desktop_entries = lambda dirs=(d,): orig((d,))
        try:
            progs = agent.programs()
        finally:
            agent.desktop_entries = orig
        self.assertEqual([(p["name"], p["title"], p["protected"]) for p in progs], [("gimp", "GIMP-Bildbearbeitung", False)])


class TestCoreUpdate(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(agent, k) for k in ("run", "core_installed", "fetch_and_verify", "install_binaries", "wait_node")}
        self.installs = []
        bindir = os.path.join(TMP, "bin")
        os.makedirs(bindir, exist_ok=True)
        for n in ("bitcoind", "bitcoin-cli"):
            Path(bindir, n).write_text("alt")
        agent.BIN_DIR = bindir
        agent.run = FakeRun({"systemctl is-active": (0, "inactive\n", ""), "systemctl": (0, "", ""),
                             "bitcoin-cli": (0, "975400\n", "")})
        agent.core_installed = lambda path=None: "31.1.0"
        agent.fetch_and_verify = lambda ver, progress: (True, "", "/neu/bin")
        agent.install_binaries = lambda d, c: self.installs.append((d, c))

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(agent, k, v)

    def test_not_newer(self):
        ok, text = agent.core_update({"version": "31.1"}, lambda *a: None, lambda: None)
        self.assertFalse(ok)
        self.assertIn("nicht neuer", text)

    def test_success(self):
        agent.wait_node = lambda want, hb: True
        ok, text = agent.core_update({"version": "31.2"}, lambda *a: None, lambda: None)
        self.assertTrue(ok, text)
        self.assertEqual(self.installs, [("/neu/bin/bitcoind", "/neu/bin/bitcoin-cli")])

    def test_rollback_when_new_version_does_not_start(self):
        agent.wait_node = lambda want, hb: want == "31.1.0"
        ok, text = agent.core_update({"version": "31.2"}, lambda *a: None, lambda: None)
        self.assertFalse(ok)
        self.assertIn("alte Version 31.1.0 läuft wieder", text)
        self.assertEqual(len(self.installs), 2)
        self.assertTrue(self.installs[1][0].endswith("bitcoind-31.1.0"))

    def test_verify_failure_changes_nothing(self):
        agent.fetch_and_verify = lambda ver, progress: (False, "Prüfsumme stimmt NICHT", None)
        ok, text = agent.core_update({"version": "31.2"}, lambda *a: None, lambda: None)
        self.assertFalse(ok)
        self.assertEqual(self.installs, [])
        self.assertFalse(any(c[:2] == ["systemctl", "stop"] for c in agent.run.calls))


class TestHelpers(unittest.TestCase):
    def test_safe_extract_rejects_escape(self):
        p = os.path.join(TMP, "evil.tar.gz")
        with tarfile.open(p, "w:gz") as tf:
            data = b"x"
            info = tarfile.TarInfo("../../ausserhalb.txt")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        with self.assertRaises(ValueError):
            agent.safe_extract(p, os.path.join(TMP, "x"))

    def test_safe_extract_skips_links(self):
        p = os.path.join(TMP, "ok.tar.gz")
        with tarfile.open(p, "w:gz") as tf:
            info = tarfile.TarInfo("bitcoin-1/bin/bitcoind")
            info.size = 2
            info.mode = 0o755
            tf.addfile(info, io.BytesIO(b"ok"))
            link = tarfile.TarInfo("bitcoin-1/link")
            link.type = tarfile.SYMTYPE
            link.linkname = "/etc/passwd"
            tf.addfile(link)
        dest = os.path.join(TMP, "y")
        os.makedirs(dest, exist_ok=True)
        agent.safe_extract(p, dest)
        self.assertTrue(os.path.isfile(os.path.join(dest, "bitcoin-1/bin/bitcoind")))
        self.assertFalse(os.path.lexists(os.path.join(dest, "bitcoin-1/link")))

    def test_norm_and_collect(self):
        self.assertGreater(agent.norm("31.2"), agent.norm("31.1.0"))
        self.assertEqual(agent.norm("31.2"), agent.norm("31.2.0"))
        payload = agent.collect(None)
        self.assertEqual(payload["v"], 2)
        self.assertIn("cpu", payload["system"])
        self.assertTrue(payload["system"]["disks"])


@unittest.skipUnless(os.environ.get("HZ_NET_TESTS"), "braucht Internet (HZ_NET_TESTS=1)")
class TestRealSignatures(unittest.TestCase):
    """Echte Pruefung: SHA256SUMS(.asc) von 31.2 aus guix.sigs nachgebaut, Schluessel von GitHub."""

    def test_31_2(self):
        import subprocess
        work = tempfile.mkdtemp(prefix="sigs-")
        subprocess.run(["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse",
                        "https://github.com/bitcoin-core/guix.sigs", f"{work}/g"], check=True)
        subprocess.run(["git", "-C", f"{work}/g", "sparse-checkout", "set", "31.2"], check=True)
        builders = sorted(Path(work, "g", "31.2").iterdir())
        sums = Path(work, "SHA256SUMS")
        sums.write_bytes((builders[0] / "all.SHA256SUMS").read_bytes())
        asc = Path(work, "SHA256SUMS.asc")
        asc.write_bytes(b"".join((b / "all.SHA256SUMS.asc").read_bytes() for b in builders if (b / "all.SHA256SUMS.asc").exists()))
        msgs = []
        ok, text = agent.verify_signatures(str(sums), str(asc), lambda step, t: msgs.append(t))
        self.assertTrue(ok, text)
        self.assertIn("gültige Signaturen", msgs[-1])
        sums.write_text(sums.read_text().replace("a", "b", 1))
        ok, text = agent.verify_signatures(str(sums), str(asc), lambda step, t: None)
        self.assertFalse(ok)
        self.assertIn("UNGÜLTIGE", text)


if __name__ == "__main__":
    unittest.main()
