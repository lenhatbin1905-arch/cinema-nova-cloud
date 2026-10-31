"""Local-only CINEMA NOVA connector. Uses only the Python standard library."""
from __future__ import annotations

import json
import os
import secrets
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("CINEMA_NOVA_PORT", "8765"))
ALLOWED_ORIGINS = {
    "https://cinemanova-e8rx.onrender.com",
    f"http://127.0.0.1:{PORT}",
    f"http://localhost:{PORT}",
}
DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CinemaNova"
TOKEN_FILE = DATA_ROOT / "connector.token"
DB_FILE = DATA_ROOT / "cinema-nova.sqlite3"
MAX_BODY = 2_000_000


def _token() -> str:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        value = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if len(value) >= 40:
            return value
    except OSError:
        pass
    value = secrets.token_urlsafe(36)
    TOKEN_FILE.write_text(value, encoding="utf-8")
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass
    return value


PAIR_TOKEN = ""


@contextmanager
def _db():
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_FILE, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, updated_at INTEGER NOT NULL, body TEXT NOT NULL)")
    db.commit()
    try:
        yield db
    finally:
        db.close()


def _probe(url: str, path: str, timeout: float = 1.2) -> dict:
    try:
        req = urllib.request.Request(url + path, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read(1_000_000)
            data = json.loads(raw) if raw else {}
            def safe_summary(value, depth=0):
                if depth > 3:
                    return None
                if isinstance(value, dict):
                    return {str(k)[:50]: safe_summary(v, depth + 1) for k, v in list(value.items())[:20]
                            if not any(word in str(k).lower() for word in ("cookie", "token", "secret", "password", "email", "account"))}
                if isinstance(value, list):
                    return [safe_summary(v, depth + 1) for v in value[:10]]
                if isinstance(value, (str, int, float, bool)) or value is None:
                    return value if not isinstance(value, str) else value[:160]
                return None
            return {"available": 200 <= response.status < 300, "http_status": response.status,
                    "detail": safe_summary(data)}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {"available": False, "detail": str(exc.reason if isinstance(exc, urllib.error.URLError) else exc)[:240]}


def provider_status() -> dict:
    flow_agent = _probe("http://127.0.0.1:8001", "/health")
    flowkit = _probe("http://127.0.0.1:8100", "/api/providers/status")
    return {
        "flow_agent": {**flow_agent, "name": "Flow Agent", "checked_endpoint": "http://127.0.0.1:8001/health",
                       "generation_enabled": False},
        "flowkit": {**flowkit, "name": "FlowKit", "checked_endpoint": "http://127.0.0.1:8100/api/providers/status",
                    "generation_enabled": False},
        "mock": {"available": True, "name": "Bản mẫu ngoại tuyến", "generation_enabled": False,
                 "detail": "Không tạo clip hoặc tiêu credits."},
    }


class ConnectorServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    server_version = "CinemaNovaConnector/1.0"

    def log_message(self, fmt, *args):
        # Avoid logging request bodies, tokens, project text or media names.
        print("[connector] " + (fmt % args).split("?")[0])

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        return (host in {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
                and (origin is None or origin in ALLOWED_ORIGINS))

    def _headers(self, status=200, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CinemaNova-Token")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        self.end_headers()

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._headers(status)
        self.wfile.write(body)

    def _authorized(self):
        if not self._origin_allowed():
            self._json({"ok": False, "error": "Origin hoặc Host không được phép."}, 403)
            return False
        if not secrets.compare_digest(self.headers.get("X-CinemaNova-Token", ""), PAIR_TOKEN):
            self._json({"ok": False, "error": "Mã ghép nối không đúng. Mở connector trên Windows để xem hướng dẫn."}, 401)
            return False
        return True

    def do_OPTIONS(self):
        if not self._origin_allowed():
            self._json({"ok": False, "error": "Origin hoặc Host không được phép."}, 403)
            return
        self._headers(204)

    def do_GET(self):
        if not self._origin_allowed():
            self._json({"ok": False, "error": "Origin hoặc Host không được phép."}, 403)
            return
        path = urlparse(self.path).path
        if path in ("/", "/index.html", "/cloud-connector.js"):
            try:
                is_script = path == "/cloud-connector.js"
                body = (ROOT / ("cloud-connector.js" if is_script else "index.html")).read_bytes()
                self._headers(200, "text/javascript; charset=utf-8" if is_script else "text/html; charset=utf-8")
                self.wfile.write(body)
            except OSError:
                self._json({"ok": False, "error": "Không đọc được giao diện CINEMA NOVA."}, 500)
        elif path == "/api/health":
            self._json({"ok": True, "version": "1.0.0", "bound_to": "127.0.0.1", "providers": provider_status()})
        elif path == "/api/session":
            # Same-origin local UI only; remote sites must enter the pairing token manually.
            if self.headers.get("Origin") not in (None, f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
                self._json({"ok": False, "error": "Mã chỉ được cấp cho giao diện cục bộ."}, 403)
                return
            self._json({"ok": True, "token": PAIR_TOKEN})
        elif path == "/api/providers":
            if not self._authorized():
                return
            self._json({"ok": True, "providers": provider_status()})
        elif path == "/api/projects":
            if not self._authorized():
                return
            with _db() as db:
                rows = db.execute("SELECT id, updated_at, body FROM projects ORDER BY updated_at DESC").fetchall()
            self._json({"ok": True, "projects": [dict(id=r["id"], updated_at=r["updated_at"], project=json.loads(r["body"])) for r in rows]})
        else:
            self._json({"ok": False, "error": "Không tìm thấy endpoint."}, 404)

    def do_POST(self):
        if not self._authorized():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > MAX_BODY:
                raise ValueError("Dữ liệu rỗng hoặc vượt giới hạn 2 MB.")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Nội dung cần là JSON dạng đối tượng.")
        except (ValueError, json.JSONDecodeError) as exc:
            self._json({"ok": False, "error": str(exc)}, 400)
            return
        path = urlparse(self.path).path
        if path == "/api/projects":
            project_id = str(payload.get("id", ""))[:100]
            if not project_id:
                self._json({"ok": False, "error": "Thiếu ID dự án."}, 400)
                return
            with _db() as db:
                db.execute("INSERT INTO projects(id, updated_at, body) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, body=excluded.body",
                           (project_id, int(time.time()), json.dumps(payload, ensure_ascii=False)))
                db.commit()
            self._json({"ok": True, "id": project_id, "saved": True})
        else:
            self._json({"ok": False, "error": "Không có endpoint tạo job thật. Chưa gửi gì tới Google Flow."}, 409)

    def do_HEAD(self):
        self._json({"ok": False, "error": "Phương thức không hỗ trợ."}, 405)


def main():
    global PAIR_TOKEN
    PAIR_TOKEN = _token()
    try:
        server = ConnectorServer(("127.0.0.1", PORT), Handler)
    except OSError as exc:
        raise SystemExit("Không thể mở cổng 127.0.0.1:%s (có thể cổng đang được dùng): %s" % (PORT, exc))
    print("CINEMA NOVA Local Connector đang chạy chỉ trên máy này: http://127.0.0.1:%s" % PORT)
    print("Mã ghép nối cho website Render (giữ riêng): %s" % PAIR_TOKEN)
    status = provider_status()
    print("Flow Agent: %s | FlowKit: %s" % ("sẵn sàng" if status["flow_agent"]["available"] else "chưa kết nối",
                                            "sẵn sàng" if status["flowkit"]["available"] else "chưa kết nối"))
    threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:%s" % PORT)).start()
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("Đã dừng connector.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
