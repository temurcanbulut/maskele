"""Yerel web arayüzü: `maskele ui`.

Güvenlik:
- Yalnızca 127.0.0.1'e bağlanır.
- Host başlığı kontrolü (DNS rebinding'e karşı).
- Her çalıştırmada rastgele bir oturum anahtarı üretilir; API çağrıları bu anahtarı
  `X-Maskele-Token` başlığında taşımak zorundadır (CSRF'e karşı: başka bir site
  özel başlık gönderemez, anahtarı da okuyamaz).
- Sıkı CSP: sayfa yalnızca kendi kaynağından script/stil yükler, dışarıya istek atmaz.
"""

from __future__ import annotations

import hmac
import json
import secrets
import sys
import threading
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from .core import Masker
from .uiapp import UIApp

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src data:; "
    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
MAX_BODY = 5 * 1024 * 1024


def _asset(name: str) -> bytes:
    return resources.files("maskele").joinpath("web", name).read_bytes()


class UIServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        addr,
        masker: Masker,
        session: str,
        save: Callable[[], None] | None = None,
        clear: Callable[[], None] | None = None,
        quiet: bool = True,
    ):
        super().__init__(addr, UIHandler)
        self.app = UIApp(masker, session, save, clear)
        self.session = session
        self.quiet = quiet
        self.token = secrets.token_urlsafe(24)
        port = self.server_address[1]
        self.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}


class UIHandler(BaseHTTPRequestHandler):
    server: UIServer
    server_version = "maskele-ui"

    def log_message(self, fmt, *args):  # noqa: N802
        if not self.server.quiet:
            sys.stderr.write(f"[maskele-ui] {fmt % args}\n")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _guard(self, api: bool) -> bool:
        if (self.headers.get("Host") or "").lower() not in self.server.allowed_hosts:
            self._json(403, {"error": "Host izinli değil."})
            return False
        if api:
            tok = self.headers.get("X-Maskele-Token") or ""
            if not hmac.compare_digest(tok, self.server.token):
                self._json(403, {"error": "Geçersiz oturum anahtarı. Sayfayı yenileyin."})
                return False
        return True

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if not self._guard(api=path.startswith("/api/")):
            return
        if path == "/":
            html = _asset("index.html").decode()
            html = html.replace("{{TOKEN}}", self.server.token).replace("{{SESSION}}", _esc(self.server.session))
            return self._send(200, html.encode(), "text/html; charset=utf-8")
        if path == "/app.js":
            return self._send(200, _asset("app.js"), "text/javascript; charset=utf-8")
        if path == "/app.css":
            return self._send(200, _asset("app.css"), "text/css; charset=utf-8")
        if path.startswith("/api/"):
            return self._json(*self.server.app.handle("GET", path, {}))
        self._json(404, {"error": "Bulunamadı."})

    def do_POST(self):  # noqa: N802
        if not self._guard(api=True):
            return
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._json(415, {"error": "JSON bekleniyor."})
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get("Transfer-Encoding") or len(lengths) > 1:
            return self._json(400, {"error": "Belirsiz istek gövdesi."})
        raw_length = lengths[0] if lengths else "0"
        if not raw_length.isascii() or not raw_length.isdecimal():
            return self._json(400, {"error": "Geçersiz Content-Length."})
        raw_length = raw_length.lstrip("0") or "0"
        if len(raw_length) > len(str(MAX_BODY)):
            return self._json(413, {"error": "Metin çok büyük (en fazla 5 MB)."})
        n = int(raw_length)
        if n > MAX_BODY:
            return self._json(413, {"error": "Metin çok büyük (en fazla 5 MB)."})
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._json(400, {"error": "Geçersiz JSON."})
        if not isinstance(body, dict):
            return self._json(400, {"error": "JSON nesnesi bekleniyor."})
        path = self.path.split("?", 1)[0]
        self._json(*self.server.app.handle("POST", path, body))


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def serve(masker: Masker, session: str, port: int = 8788, open_browser: bool = True, **kw) -> None:
    srv = UIServer(("127.0.0.1", port), masker, session, **kw)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    sys.stderr.write(f"maskele arayüzü: {url}\nDurdurmak için Ctrl+C.\n")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


UIServer.masker = property(lambda self: self.app.masker)
