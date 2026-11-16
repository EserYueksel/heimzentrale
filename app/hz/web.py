"""HTTP-Server: Seite, Dateien, Schnittstelle fuer Seite und Agenten.

Seite (ohne Schluessel, nur im Heimnetz erreichbar):
  GET  /                        Seite
  GET  /api/status              Zustand aller Pis
  GET  /api/history             Verlauf (?host=&range=24h|7d|30d|90d)
  GET  /api/inventory           Programme eines Pi (?host=)
  POST /api/tasks               Auftrag anlegen (JSON; Update/Entfernen mit PIN)
  POST /api/tasks/cancel        offenen Auftrag zurueckziehen
  POST /api/connect             Befehl zum Anbinden eines weiteren Pi (mit PIN)
Agenten (Header X-Token):
  POST /api/report              Zustand melden
  GET  /api/agent/job           naechsten Auftrag abholen (?host=&peek=1)
  POST /api/agent/progress      Fortschritt eines Auftrags
  POST /api/agent/inventory     installierte Programme
Downloads:
  GET  /agent/heimzentrale-agent, /install.sh
"""
import hmac
import json
import sys
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import VERSION, config, inventory, reports, status, tasks

APP_DIR = Path(__file__).resolve().parent.parent
STATIC = APP_DIR / "static"
DOWNLOADS = {"/agent/heimzentrale-agent": APP_DIR / "agent" / "heimzentrale-agent",
             "/install.sh": APP_DIR / "install.sh"}
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml", ".woff2": "font/woff2",
         ".json": "application/json", ".webmanifest": "application/manifest+json", ".png": "image/png"}
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
       "connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
BROWSER_POSTS = ("/api/tasks", "/api/tasks/cancel", "/api/connect")
AGENT_POSTS = ("/api/report", "/api/agent/progress", "/api/agent/inventory")


def static_file(path):
    """Datei unter static/ zum URL-Pfad - nie ausserhalb davon."""
    rel = path.lstrip("/")
    if not rel or any(part.startswith(".") for part in rel.split("/")):
        return None
    target = (STATIC / rel).resolve()
    root = STATIC.resolve()
    if root not in target.parents or not target.is_file() or target.suffix not in TYPES:
        return None
    return target


def connect_command(host_header):
    base = config.get("PUBLIC_URL") or (f"http://{host_header}" if host_header else "")
    if not base or "localhost" in base or "127.0.0.1" in base:
        base = "http://ADRESSE-DER-HEIMZENTRALE:8088"
    base = base.rstrip("/")
    return base, (f"curl -fsSL {base}/install.sh | sudo bash -s -- agent {base} {config.get('HZ_TOKEN')}")


class Handler(BaseHTTPRequestHandler):
    server_version = f"Heimzentrale/{VERSION}"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # nur Fehler ins Protokoll
        pass

    # ------------------------------------------------------------ Antworten
    def send_body(self, code, body, ctype, cache="no-store"):
        if code >= 400:
            self.close_connection = True
        self.send_response(code)
        if code >= 400:
            self.send_header("Connection", "close")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, obj, code=200):
        self.send_body(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def send_text(self, text, code=200):
        self.send_body(code, (text + "\n").encode("utf-8"), "text/plain; charset=utf-8")

    def fail(self, code, message):
        self.send_json({"error": message}, code)

    # ------------------------------------------------------------ Eingaben
    def token_ok(self):
        token = config.get("HZ_TOKEN")
        if not token:
            self.send_text("HZ_TOKEN fehlt in heimzentrale.conf", 503)
            return False
        if not hmac.compare_digest(self.headers.get("X-Token", "").encode(), token.encode()):
            self.send_text("Falscher Schluessel: HZ_TOKEN im Agenten und in der Heimzentrale vergleichen", 401)
            return False
        return True

    def read_json(self, limit):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > limit:
            self.send_text("Leere oder zu grosse Anfrage", 400)
            return None
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            data = None
        if not isinstance(data, dict):
            self.send_text("Anfrage nicht lesbar", 400)
            return None
        return data

    def query(self):
        return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()}

    # ------------------------------------------------------------ GET
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path in ("/", "/index.html"):
                self.send_body(200, (STATIC / "index.html").read_bytes(), TYPES[".html"])
            elif path.startswith("/api/"):
                self.api_get(path)
            elif path in DOWNLOADS and DOWNLOADS[path].is_file():
                self.send_body(200, DOWNLOADS[path].read_bytes(), "text/plain; charset=utf-8")
            else:
                f = static_file(path)
                if f is None:
                    self.send_text("Nicht gefunden", 404)
                else:
                    cache = "max-age=31536000, immutable" if f.suffix == ".woff2" else "no-cache"
                    self.send_body(200, f.read_bytes(), TYPES[f.suffix], cache=cache)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self.send_text("Interner Fehler", 500)

    def api_get(self, path):
        q = self.query()
        if path == "/api/health":
            self.send_json({"ok": True, "version": VERSION})
        elif path == "/api/status":
            self.send_json(status.build())
        elif path in ("/api/history", "/api/inventory"):
            host = q.get("host", "")
            if not reports.valid_host(host):
                self.fail(400, "host fehlt")
            elif path == "/api/history":
                self.send_json(status.history(host, q.get("range", "24h")))
            else:
                self.send_json(inventory.get(host) or {"programs": [], "updated": None})
        elif path == "/api/agent/job":
            if self.token_ok():
                host = q.get("host", "")
                if not reports.valid_host(host):
                    self.fail(400, "host fehlt")
                else:
                    self.send_json({"job": tasks.next_for(host, peek=q.get("peek") == "1")})
        else:
            self.send_text("Nicht gefunden", 404)

    # ------------------------------------------------------------ POST
    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if path not in BROWSER_POSTS + AGENT_POSTS:
            self.send_text("Nicht gefunden", 404)
            return
        try:
            if path in BROWSER_POSTS:
                self.browser_post(path)
            else:
                self.agent_post(path)
        except tasks.TaskError as e:
            self.fail(e.code, str(e))
        except ValueError as e:
            self.fail(400, f"Nicht lesbar: {e}")
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self.fail(500, "Interner Fehler")

    def browser_post(self, path):
        # nur JSON: fremde Webseiten koennen das ohne Vorabfrage (die wir nicht beantworten) nicht senden
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            self.send_text("Nur JSON", 415)
            return
        body = self.read_json(16 * 1024)
        if body is None:
            return
        if path == "/api/tasks":
            self.send_json({"ok": True, "id": tasks.request(body)})
        elif path == "/api/tasks/cancel":
            tasks.cancel(body)
            self.send_json({"ok": True})
        else:  # /api/connect
            tasks.check_pin(body.get("pin"))
            base, command = connect_command(self.headers.get("Host", ""))
            self.send_json({"ok": True, "url": base, "command": command})

    def agent_post(self, path):
        body = self.read_json(2 * 1024 * 1024)
        if body is None or not self.token_ok():
            return
        if path == "/api/report":
            self.send_json({"ok": True, "host": reports.store(body)})
        elif path == "/api/agent/progress":
            self.send_json({"ok": True, "accepted": tasks.progress(body)})
        else:  # /api/agent/inventory
            host = body.get("host")
            if not reports.valid_host(host):
                raise ValueError("host fehlt")
            self.send_json({"ok": True, "count": inventory.store(host, body)})


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError, TimeoutError)):
            return  # Browser hat die Verbindung geschlossen - kein Fehler
        super().handle_error(request, client_address)


def make_server(port, host="0.0.0.0"):
    return Server((host, port), Handler)
