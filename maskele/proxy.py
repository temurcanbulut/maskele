"""OpenAI ve Anthropic uyumlu yerel maskeleme proxy'si.

Uygulamalar `base_url`'i bu proxy'ye çevirir; API anahtarı ve kod aynı kalır.
İstek gövdesindeki metinler maskelenir, cevaplar (streaming dahil) geri çevrilir.

Güvenlik varsayılanları (fail closed):
- Yalnızca JSON nesne gövdeleri kabul edilir; başka her şey 415/400 ile reddedilir.
- URL'de tespit edilen hassas değer varsa istek 422 ile reddedilir.
- Upstream'e yalnızca izin listesindeki başlıklar iletilir (Cookie vb. düşer).
- Cevaplar yalnızca AYNI istekte modele giden token'larla, yalnızca tam
  `[[TOKEN]]` biçiminde geri çevrilir.
- Politikada "block" olan bir tür bulunursa istek 422 ile reddedilir.

    maskele proxy --provider openai     # → http://127.0.0.1:8787/v1
    maskele proxy --provider anthropic  # → http://127.0.0.1:8787
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .core import HINT, Masker, ProtocolFieldError, StreamUnmasker
from .vault import Vault

PROVIDERS = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "openrouter": "https://openrouter.ai/api",
    "groq": "https://api.groq.com/openai",
    "mistral": "https://api.mistral.ai",
    "deepseek": "https://api.deepseek.com",
    "ollama": "http://127.0.0.1:11434",
}

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    "accept-encoding",
    "content-encoding",
}


# ---------------------------------------------------------------------------
# İstek dönüşümü
# ---------------------------------------------------------------------------


def inject_hint(body: dict, path: str) -> None:
    """Modele token'ları koruması gerektiğini söyleyen notu ekler."""
    if "/messages" in path and "messages" in body and "max_tokens" in body:  # Anthropic
        sys_ = body.get("system")
        if isinstance(sys_, list):
            sys_.append({"type": "text", "text": HINT})
        elif sys_:
            body["system"] = f"{sys_}\n\n{HINT}"
        else:
            body["system"] = HINT
    elif isinstance(body.get("messages"), list):  # Chat Completions
        msgs = body["messages"]
        if msgs and msgs[0].get("role") in ("system", "developer") and isinstance(msgs[0].get("content"), str):
            msgs[0]["content"] = f"{msgs[0]['content']}\n\n{HINT}"
        else:
            msgs.insert(0, {"role": "system", "content": HINT})
    elif "input" in body:  # Responses API
        ins = body.get("instructions")
        body["instructions"] = f"{ins}\n\n{HINT}" if ins else HINT


# ---------------------------------------------------------------------------
# SSE akış dönüşümü
# ---------------------------------------------------------------------------


class SSERewriter:
    """SSE olaylarını okur, metin deltalarını parçalar arası güvenli şekilde geri çevirir."""

    def __init__(self, masker: Masker, allowed: set[str] | None = None, mode: str = "strict"):
        self.m = masker
        self.allowed = allowed
        self.mode = mode
        self.streams: dict[tuple, StreamUnmasker] = {}
        self._unknown: set[str] = set()
        self.response_id: str | None = None
        self.anthropic_types: dict[int, str] = {}
        self.template: dict | None = None
        self.restored = 0

    def _s(self, key: tuple, json_ctx: bool = False) -> StreamUnmasker:
        if key not in self.streams:
            self.streams[key] = self.m.stream(json_ctx, mode=self.mode, allowed=self.allowed)
        return self.streams[key]

    @property
    def unknown_count(self) -> int:
        return len(set().union(*(s.unknown for s in self.streams.values())) | self._unknown)

    def _obj(self, obj):
        return self.m.unmask_obj(obj, mode=self.mode, allowed=self.allowed)

    def _flush(self, key: tuple) -> str:
        s = self.streams.pop(key, None)
        if not s:
            return ""
        out = s.flush()
        self.restored += s.restored
        self._unknown |= s.unknown
        return out

    # Her olay bloğu → çıktı blokları listesi
    def process(self, event: str | None, data: str) -> list[tuple[str | None, str]]:
        if data.strip() == "[DONE]":
            extra = self._flush_openai_all()
            return extra + [(event, data)]
        try:
            obj = json.loads(data)
        except ValueError:
            return [(event, self.m.unmask(data, mode=self.mode, allowed=self.allowed).text)]
        if not isinstance(obj, dict):
            return [(event, json.dumps(self._obj(obj), ensure_ascii=False))]

        t = obj.get("type", "")
        out: list[tuple[str | None, Any]] = []
        if t in ("response.created", "response.completed") and isinstance(obj.get("response"), dict):
            self.response_id = obj["response"].get("id") or self.response_id

        # --- Anthropic Messages ------------------------------------------------
        if t == "content_block_start":
            self.anthropic_types[obj.get("index", 0)] = (obj.get("content_block") or {}).get("type", "text")
            out.append((event, self._obj(obj)))
        elif t == "content_block_delta":
            i, d = obj.get("index", 0), obj.get("delta", {})
            for field, json_ctx in (("text", False), ("thinking", False), ("partial_json", True)):
                if isinstance(d.get(field), str):
                    d[field] = self._s(("a", i, field), json_ctx).feed(d[field])
            out.append((event, obj))
        elif t == "content_block_stop":
            i = obj.get("index", 0)
            for field in ("text", "thinking", "partial_json"):
                rem = self._flush(("a", i, field))
                if rem:
                    dtype = {"text": "text_delta", "thinking": "thinking_delta", "partial_json": "input_json_delta"}[
                        field
                    ]
                    out.append(
                        (
                            "content_block_delta",
                            {"type": "content_block_delta", "index": i, "delta": {"type": dtype, field: rem}},
                        )
                    )
            out.append((event, obj))

        # --- OpenAI Responses API -----------------------------------------------
        elif t in (
            "response.output_text.delta",
            "response.function_call_arguments.delta",
            "response.reasoning_summary_text.delta",
            "response.refusal.delta",
        ):
            key = ("r", t.rsplit(".", 1)[0], obj.get("item_id"), obj.get("output_index"), obj.get("content_index"))
            obj["delta"] = self._s(key, "arguments" in t).feed(obj.get("delta", ""))
            out.append((event, obj))
        elif t.endswith(".done") and t.startswith("response.") and t != "response.done":
            base = t.rsplit(".", 1)[0]
            key = ("r", base, obj.get("item_id"), obj.get("output_index"), obj.get("content_index"))
            rem = self._flush(key)
            if rem:
                out.append(
                    (
                        base + ".delta",
                        {
                            **{k: obj[k] for k in ("item_id", "output_index", "content_index") if k in obj},
                            "type": base + ".delta",
                            "delta": rem,
                        },
                    )
                )
            out.append((event, self._obj(obj)))

        # --- OpenAI Chat Completions --------------------------------------------
        elif isinstance(obj.get("choices"), list) and obj.get("object", "").endswith("chunk"):
            self.template = {k: obj[k] for k in ("id", "object", "created", "model") if k in obj}
            for ch in obj["choices"]:
                ci, d = ch.get("index", 0), ch.get("delta") or {}
                if isinstance(d.get("content"), str):
                    d["content"] = self._s(("c", ci)).feed(d["content"])
                for tc in d.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    if isinstance(fn.get("arguments"), str):
                        fn["arguments"] = self._s(("t", ci, tc.get("index", 0)), True).feed(fn["arguments"])
                if ch.get("finish_reason"):
                    self._flush_choice(ci, d)
                    ch["delta"] = d
            out.append((event, obj))

        else:
            out.append((event, self._obj(obj)))

        return [(e, o if isinstance(o, str) else json.dumps(o, ensure_ascii=False)) for e, o in out]

    def _flush_choice(self, ci: int, delta: dict) -> None:
        rem = self._flush(("c", ci))
        if rem:
            delta["content"] = (delta.get("content") or "") + rem
        for key in [k for k in self.streams if k[0] == "t" and k[1] == ci]:
            rem = self._flush(key)
            if rem:
                delta.setdefault("tool_calls", []).append({"index": key[2], "function": {"arguments": rem}})

    def _flush_openai_all(self) -> list[tuple[str | None, str]]:
        choices = sorted({k[1] for k in self.streams if k[0] in ("c", "t")})
        out = []
        for ci in choices:
            d: dict = {}
            self._flush_choice(ci, d)
            if d:
                chunk = {
                    **(self.template or {"object": "chat.completion.chunk"}),
                    "choices": [{"index": ci, "delta": d, "finish_reason": None}],
                }
                out.append((None, json.dumps(chunk, ensure_ascii=False)))
        return out

    def finish(self) -> list[tuple[str | None, str]]:
        """Akış [DONE] olmadan biterse kalanları boşalt."""
        out = self._flush_openai_all()
        for key in list(self.streams):
            rem = self._flush(key)
            if rem:
                out.append((None, json.dumps({"type": "maskele.flush", "text": rem}, ensure_ascii=False)))
        return out


def iter_sse(lines) -> Any:
    """Satır akışından (event, data) blokları üretir."""
    event, data = None, []
    for raw in lines:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line == "":
            if data or event:
                yield event, "\n".join(data)
            event, data = None, []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" ") if line[5:6] == " " else line[5:])
    if data or event:
        yield event, "\n".join(data)


def format_sse(event: str | None, data: str) -> bytes:
    s = f"event: {event}\n" if event else ""
    s += "".join(f"data: {ln}\n" for ln in data.split("\n")) + "\n"
    return s.encode("utf-8")


# ---------------------------------------------------------------------------
# Sunucu
# ---------------------------------------------------------------------------

# Upstream'e iletilen istek başlıkları ve nasıl ele alındıkları:
# - AUTH: kimlik bilgisi; dokunulmadan iletilir (maskelenirse istek başarısız olur).
# - META: protokol/istemci bilgisi; iletilir ama içeriği taranır, hassas veri varsa istek
#   reddedilir. HTTP-Referer, X-Title gibi serbest metin taşıyan başlıklar varsayılan
#   listede YOKTUR (--forward-header ile eklenebilir, eklenirse onlar da taranır).
AUTH_HEADERS = {"authorization", "x-api-key", "api-key"}
META_HEADERS = {
    "anthropic-version",
    "anthropic-beta",
    "openai-organization",
    "openai-project",
    "openai-beta",
    "content-type",
    "accept",
    "user-agent",
    "idempotency-key",
}
META_PREFIXES = ("x-stainless-",)  # resmî SDK'ların istemci bilgileri


def redact_path(path: str) -> str:
    """Log ve denetim kaydı için güvenli yol: sorgu dizesi atılır, yoldaki hassas değerler
    (yüzde kodlanmış biçimleri dahil) REDACTED ile değiştirilir."""
    from .detectors import detect

    p = path.split("?", 1)[0].split("#", 1)[0]
    segs = []
    for seg in p.split("/"):
        plain = urllib.parse.unquote_plus(seg)
        segs.append("REDACTED" if detect(plain, keep_localhost=False) else seg)
    return "/".join(segs)


class ConversationStore:
    """Sunucu tarafında geçmiş tutan akışlar (Responses API `previous_response_id`) için
    süre ve boyut sınırlı, kimlik bilgisine bağlı eşleme deposu.

    Her istek yine kendi kasasıyla başlar; yalnızca istek aynı kimlik bilgisiyle önceki bir
    yanıta bağlanıyorsa o yanıtın eşlemeleri yüklenir. Anahtar olarak ham API anahtarı değil,
    süreç başına rastgele bir anahtarla HMAC'lenmiş parmak izi tutulur.
    """

    def __init__(self, ttl: float = 3600, max_items: int = 5000):
        self.ttl, self.max_items = ttl, max_items
        self._data: dict[tuple[str, str], tuple[float, dict]] = {}
        self._lock = threading.Lock()
        self._key = secrets.token_bytes(32)

    def principal(self, headers) -> str:
        cred = "\x1f".join((headers.get(h) or "") for h in ("Authorization", "x-api-key", "api-key", "X-Maskele-Key"))
        return hmac.new(self._key, cred.encode(), hashlib.sha256).hexdigest()

    def put(self, principal: str, response_id: str, vault: dict) -> None:
        now = time.time()
        with self._lock:
            self._data[(principal, response_id)] = (now + self.ttl, vault)
            if len(self._data) > self.max_items:
                for k, (_exp, _) in sorted(self._data.items(), key=lambda kv: kv[1][0])[
                    : len(self._data) - self.max_items
                ]:
                    self._data.pop(k, None)

    def get(self, principal: str, response_id: str) -> dict | None:
        with self._lock:
            item = self._data.get((principal, response_id))
            if not item:
                return None
            if item[0] < time.time():
                self._data.pop((principal, response_id), None)
                return None
            return item[1]

    def __len__(self) -> int:
        return len(self._data)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Upstream yönlendirmeleri takip edilmez: kimlik bilgileri başka bir origin'e gitmesin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64

    def __init__(
        self,
        addr,
        masker: Masker,
        upstream: str,
        *,
        hint: bool = True,
        audit_path: str | None = None,
        allowed_hosts: set[str] | None = None,
        quiet: bool = False,
        use_env_proxy: bool = True,
        access_key: str | None = None,
        max_body: int = 20 * 1024 * 1024,
        max_concurrency: int = 64,
        max_connections: int = 128,
        conn_timeout: float = 30,
        timeout: float = 300,
        unsafe_passthrough: bool = False,
        unmask_mode: str = "strict",
        forward_headers: set[str] | None = None,
        tls_cert: str | None = None,
        tls_key: str | None = None,
        **_ignored,
    ):
        super().__init__(addr, ProxyHandler)
        # `masker` yalnızca ayar şablonudur; her istek kendi boş kasasıyla çalışır (fork).
        self.masker = masker
        self.upstream = upstream.rstrip("/")
        self.hint = hint
        self.audit_path = audit_path
        self.quiet = quiet
        handlers: list = [_NoRedirect()]
        if not use_env_proxy:
            handlers.append(urllib.request.ProxyHandler({}))
        self.opener = urllib.request.build_opener(*handlers)
        self.access_key = access_key
        self.max_body = max_body
        self.timeout = timeout
        self.conn_timeout = conn_timeout
        self.unsafe_passthrough = unsafe_passthrough
        self.unmask_mode = unmask_mode
        self.extra_headers = {h.lower() for h in (forward_headers or set())} - AUTH_HEADERS
        self.slots = threading.BoundedSemaphore(max_concurrency)
        self.conn_slots = threading.BoundedSemaphore(max_connections)
        self.tls = None
        if tls_cert:
            ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.load_cert_chain(tls_cert, tls_key)
            # El sıkışma kabul döngüsünde değil, bağlantının kendi iş parçacığında yapılır;
            # yavaş bir istemci yeni bağlantıların kabulünü engelleyemez.
            self.socket = ctx.wrap_socket(self.socket, server_side=True, do_handshake_on_connect=False)
            self.tls = ctx
        port = self.server_address[1]
        self.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}", "127.0.0.1", "localhost"} | (
            allowed_hosts or set()
        )
        self.stats = Counter(
            {
                "requests": 0,
                "masked": 0,
                "restored": 0,
                "errors": 0,
                "rejected": 0,
                "unrestored": 0,
                "media_unscanned": 0,
            }
        )
        self.kind_stats: Counter = Counter()
        self.started = time.time()
        self._lock = threading.Lock()
        self.conversations = ConversationStore()

    # --- bağlantı sınırı: iş parçacığı açılmadan ÖNCE uygulanır --------------------
    def process_request(self, request, client_address):
        if not self.conn_slots.acquire(blocking=False):
            try:
                request.settimeout(1)
                if not self.tls:
                    request.sendall(
                        b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                    )
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.conn_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.conn_slots.release()

    def record(self, entry: dict, kinds: Counter) -> None:
        with self._lock:
            self.stats["requests"] += 1
            status = entry.get("status", 200)
            if status >= 500:
                self.stats["errors"] += 1
            elif entry.get("rejected"):
                self.stats["rejected"] += 1
            self.stats["masked"] += sum(kinds.values())
            self.stats["restored"] += entry.get("restored", 0)
            self.stats["unrestored"] += entry.get("unrestored", 0)
            self.stats["media_unscanned"] += entry.get("media", 0)
            self.kind_stats.update(kinds)
            if self.audit_path:
                with open(self.audit_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def save_now(self) -> None:  # geri uyumluluk; proxy kalıcı kasa tutmaz
        pass


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: ProxyServer
    server_version = "maskele-proxy"

    def setup(self):
        # Her okuma/yazma için zaman aşımı: yarım başlık gönderip bekleyen (slowloris)
        # bağlantılar conn_timeout sonunda kapanır.
        self.timeout = self.server.conn_timeout
        if self.server.tls:
            self.request.settimeout(self.server.conn_timeout)
            self.request.do_handshake()
        super().setup()

    def handle(self):
        try:
            super().handle()
        except (TimeoutError, ssl.SSLError, ConnectionError, OSError):
            self.close_connection = True

    def log_message(self, fmt, *args):  # noqa: N802
        if not self.server.quiet:
            # İstek satırı URL içerir; sorgu dizesini log'a yazma
            msg = (fmt % args).replace(self.path, redact_path(self.path)) if self.path else fmt % args
            sys.stderr.write(f"[maskele] {msg}\n")

    # --- yardımcılar ---------------------------------------------------------
    def _json(self, code: int, obj: Any) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        if code >= 400:
            # Okunmamış istek gövdesi bir sonraki istek gibi ayrıştırılmasın
            self.close_connection = True
            self.send_header("Connection", "close")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _reject(self, code: int, typ: str, message: str, kinds: Counter | None = None, t0: float | None = None) -> None:
        self.server.record(
            {
                "ts": round(t0 or time.time(), 3),
                "method": self.command,
                "path": self._safe_path(),
                "status": code,
                "rejected": typ,
                "masked": dict(kinds or {}),
            },
            Counter(),
        )
        self._json(code, {"error": {"type": f"maskele_{typ}", "message": message}})

    def _safe_path(self) -> str:
        return redact_path(self.path)

    def _guard(self) -> bool:
        # DNS rebinding koruması: yalnızca beklenen Host başlıkları
        host = (self.headers.get("Host") or "").lower()
        if host not in self.server.allowed_hosts:
            self._json(
                403,
                {"error": {"type": "maskele_forbidden_host", "message": f"Host {host!r} izinli değil (--allow-host)."}},
            )
            return False
        key = self.server.access_key
        if key and not hmac.compare_digest((self.headers.get("X-Maskele-Key") or "").encode(), key.encode()):
            self._json(
                401, {"error": {"type": "maskele_unauthorized", "message": "X-Maskele-Key başlığı eksik ya da yanlış."}}
            )
            return False
        return True

    def _chunk(self, b: bytes) -> None:
        if b:
            self.wfile.write(f"{len(b):x}\r\n".encode() + b + b"\r\n")
            self.wfile.flush()

    def _read_body(self, n: int) -> bytes | None:
        """Gövdeyi toplam süre sınırıyla okur (bayt bayt damlatan istemcilere karşı)."""
        deadline = time.time() + max(self.server.conn_timeout, 5) * 2
        parts, got = [], 0
        while got < n:
            if time.time() > deadline:
                self._reject(408, "timeout", "İstek gövdesi zamanında gelmedi.")
                return None
            chunk = (
                self.rfile.read1(min(65536, n - got))
                if hasattr(self.rfile, "read1")
                else self.rfile.read(min(65536, n - got))
            )
            if not chunk:
                self._reject(400, "bad_request", "İstek gövdesi eksik.")
                return None
            parts.append(chunk)
            got += len(chunk)
        return b"".join(parts)

    # --- uçlar ---------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        if not self._guard():
            return
        if self.path == "/maskele/health":
            return self._json(200, {"ok": True, "upstream": self.server.upstream})
        if self.path == "/maskele/stats":
            s = self.server
            return self._json(
                200, {"uptime_s": round(time.time() - s.started), **s.stats, "by_kind": dict(s.kind_stats)}
            )
        self._handle(b"")

    def do_DELETE(self):  # noqa: N802
        if self._guard():
            self._handle(b"")

    def do_POST(self):  # noqa: N802
        if not self._guard():
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._reject(400, "bad_request", "Geçersiz Content-Length.")
        if self.headers.get("Transfer-Encoding"):
            return self._reject(411, "length_required", "Chunked istek gövdesi desteklenmiyor.")
        if n > self.server.max_body:
            return self._reject(413, "too_large", f"İstek {self.server.max_body // (1024 * 1024)} MB sınırını aşıyor.")
        raw = self._read_body(n) if n else b""
        if raw is not None:
            self._handle(raw)

    def _handle(self, raw: bytes) -> None:
        if not self.server.slots.acquire(blocking=False):
            return self._json(503, {"error": {"type": "maskele_busy", "message": "Çok fazla eşzamanlı istek."}})
        try:
            self._forward(raw, self.server.masker.fork())
        finally:
            self.server.slots.release()

    # --- iletme --------------------------------------------------------------
    @staticmethod
    def _previous_response_id(raw: bytes) -> str | None:
        if not raw or b"previous_response_id" not in raw:
            return None
        try:
            v = json.loads(raw).get("previous_response_id")
        except (ValueError, AttributeError):
            return None
        return v if isinstance(v, str) and len(v) < 256 else None

    def _check_url(self, m: Masker, kinds: Counter) -> bool:
        """URL yolu ve sorgu dizesinde hassas değer varsa reddet (maskelenmiş URL API'yi bozar)."""
        target = urllib.parse.unquote_plus(self.path)
        found = m.detect(target)
        if found:
            kinds.update(f.kind for f in found)
            self._reject(
                422,
                "pii_in_url",
                "URL'de hassas veri var ("
                + ", ".join(sorted({f.kind for f in found}))
                + "). Bu değerleri istek gövdesine taşıyın.",
                kinds,
            )
            return False
        return True

    def _headers(self, m: Masker, kinds: Counter) -> dict | None:
        """İletilecek başlıklar; serbest metin başlıklarda hassas veri varsa reddeder."""
        out = {}
        for k, v in self.headers.items():
            lk = k.lower()
            if lk in AUTH_HEADERS:
                out[k] = v
            elif lk in META_HEADERS or lk in self.server.extra_headers or lk.startswith(META_PREFIXES):
                found = m.detect(v)
                if found:
                    kinds.update(f.kind for f in found)
                    self._reject(
                        422,
                        "pii_in_header",
                        f"{k} başlığında hassas veri var (" + ", ".join(sorted({f.kind for f in found})) + ").",
                        kinds,
                    )
                    return None
                out[k] = v
        out["Accept-Encoding"] = "identity"
        return out

    def _prepare_body(
        self, m: Masker, raw: bytes, kinds: Counter, produced: set[str], notes: Counter
    ) -> tuple[bytes | None, bool]:
        """(gövde, başarı). Başarısızsa yanıt zaten gönderilmiştir."""
        if not raw:
            return raw, True
        ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        is_json = ctype == "application/json" or ctype.endswith("+json")
        if not is_json:
            if self.server.unsafe_passthrough:
                return raw, True
            self._reject(
                415,
                "unsupported_media_type",
                f"Yalnızca application/json gövdeler maskelenebilir; {ctype or 'içerik türü yok'} "
                "reddedildi. Maskelenmeden iletmek için --unsafe-passthrough.",
                kinds,
            )
            return None, False
        try:
            obj = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            self._reject(400, "invalid_json", "Gövde geçerli JSON değil; maskelenemediği için iletilmedi.", kinds)
            return None, False
        if not isinstance(obj, dict):
            self._reject(422, "unsupported_body", "JSON gövdesinin kökü bir nesne olmalı.", kinds)
            return None, False
        try:
            obj = m.mask_obj(obj, kinds, produced, notes)
        except ProtocolFieldError as e:
            self._reject(
                422,
                "protocol_field",
                f"{e}. Protokol alanları maskelenirse API isteği bozulur; istek iletilmedi.",
                kinds,
            )
            return None, False
        blocked = m.blocked_kinds & set(kinds)
        if blocked:
            self._reject(
                422, "blocked", "Politika gereği gönderilemeyen veri türü: " + ", ".join(sorted(blocked)) + ".", kinds
            )
            return None, False
        media_policy = m.config.proxy_media if m.config is not None else "allow"
        if notes["media"] and media_policy == "block":
            self._reject(
                422,
                "media_blocked",
                "İstek taranamayan görsel/dosya içeriyor; politika gereği iletilmedi (proxy.media = block).",
                kinds,
            )
            return None, False
        if self.server.hint and kinds:
            inject_hint(obj, self.path)
        return json.dumps(obj, ensure_ascii=False).encode("utf-8"), True

    def _forward(self, raw: bytes, m: Masker) -> None:
        t0 = time.time()
        kinds: Counter = Counter()
        notes: Counter = Counter()
        if not self._check_url(m, kinds):
            return
        headers = self._headers(m, kinds)
        if headers is None:
            return
        # Cevap yalnızca bu istekte AÇIK METİN olarak gelip maskelenen değerlerin
        # token'larıyla geri çevrilir. İstemcinin gövdeye kendisi yazdığı "[[EMAIL_1]]"
        # gibi token'lar yetki vermez. Kasa da istek başına boştur.
        allowed: set[str] = set()
        principal = self.server.conversations.principal(self.headers)
        prev_id = self._previous_response_id(raw)
        if prev_id:
            stored = self.server.conversations.get(principal, prev_id)
            if stored:
                # Önceki turun eşlemeleri: numaralar tutarlı kalır, eski token'lar geri çevrilir
                m.vault = Vault.from_dict(json.loads(json.dumps(stored)))
                allowed |= set(m.vault.tokens)
        body, ok = self._prepare_body(m, raw, kinds, allowed, notes)
        if not ok:
            return

        def remember(response_id) -> None:
            if isinstance(response_id, str) and response_id and m.vault.tokens:
                self.server.conversations.put(principal, response_id, m.vault.to_dict())

        req = urllib.request.Request(
            self.server.upstream + self.path, data=body or None, headers=headers, method=self.command
        )
        try:
            resp = self.server.opener.open(req, timeout=self.server.timeout)
        except urllib.error.HTTPError as e:
            if 300 <= e.code < 400:
                e.close()
                self._reject(
                    502,
                    "upstream_redirect",
                    f"Upstream {e.code} yönlendirmesi döndü; kimlik bilgilerinin başka bir "
                    "sunucuya gitmemesi için takip edilmedi. --upstream adresini kontrol edin.",
                    kinds,
                    t0,
                )
                return
            resp = e
        except (urllib.error.URLError, OSError) as e:
            self.server.record(
                {
                    "ts": round(t0, 3),
                    "method": self.command,
                    "path": self._safe_path(),
                    "status": 502,
                    "masked": dict(kinds),
                    "restored": 0,
                    "ms": round((time.time() - t0) * 1000),
                    "error": "upstream",
                },
                kinds,
            )
            self._json(502, {"error": {"type": "maskele_upstream_error", "message": str(e)}})
            return

        status = resp.status if hasattr(resp, "status") else resp.code
        rtype = resp.headers.get("Content-Type", "")
        mode = self.server.unmask_mode

        def record(restored: int, unrestored: int) -> None:
            # Cevabın son baytından önce yazılır: istemci bittiğini gördüğünde kayıt hazırdır
            self.server.record(
                {
                    "ts": round(t0, 3),
                    "method": self.command,
                    "path": self._safe_path(),
                    "status": status,
                    "masked": dict(kinds),
                    "restored": restored,
                    "unrestored": unrestored,
                    "media": notes["media"],
                    "ms": round((time.time() - t0) * 1000),
                },
                kinds,
            )

        self.send_response(status)
        for k, v in resp.headers.items():
            if k.lower() not in HOP_BY_HOP and k.lower() != "set-cookie":
                self.send_header(k, v)
        if notes["media"]:
            # İstemci, taranamayan içerik gönderdiğini bilsin
            self.send_header("X-Maskele-Unscanned", "media")

        if "text/event-stream" in rtype:
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            rw = SSERewriter(m, allowed, mode)
            try:
                for event, data in iter_sse(resp):
                    for e2, d2 in rw.process(event, data):
                        self._chunk(format_sse(e2, d2))
                for e2, d2 in rw.finish():
                    self._chunk(format_sse(e2, d2))
                remember(rw.response_id)
                record(rw.restored, rw.unknown_count)
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                record(rw.restored, rw.unknown_count)
                self.close_connection = True
            return

        data = resp.read()
        restored = unrestored = 0
        if "json" in rtype:
            try:
                stats: Counter = Counter()
                parsed = json.loads(data)
                if isinstance(parsed, dict) and parsed.get("object") == "response":
                    remember(parsed.get("id"))
                data = json.dumps(m.unmask_obj(parsed, stats, mode=mode, allowed=allowed), ensure_ascii=False).encode(
                    "utf-8"
                )
                restored, unrestored = stats["restored"], stats["unknown"]
            except ValueError:
                pass
        elif rtype.startswith("text/"):
            r = m.unmask(data.decode("utf-8", errors="replace"), mode=mode, allowed=allowed)
            restored, unrestored, data = r.restored, len(r.unknown), r.text.encode("utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        record(restored, unrestored)
        self.wfile.write(data)


LOOPBACK = ("127.0.0.1", "localhost", "::1")


def serve(masker: Masker, upstream: str, host: str = "127.0.0.1", port: int = 8787, **kw) -> None:
    srv = ProxyServer((host, port), masker, upstream, **kw)
    scheme = "https" if srv.tls else "http"
    base = f"{scheme}://{host if ':' not in host else f'[{host}]'}:{srv.server_address[1]}"
    cfg = masker.config
    sys.stderr.write(
        f"maskele proxy {base}  →  {upstream}\n"
        f'  OpenAI SDK:    base_url="{base}/v1"\n'
        f'  Anthropic SDK: base_url="{base}"\n'
        f"  İstatistik:    {base}/maskele/stats\n"
        f"  Açık türler:   {', '.join(masker.kinds or (cfg.all_kinds if cfg else []))}\n"
        f"  Kasa:          istek başına, yalnızca bellekte\n"
    )
    if cfg is not None:
        if cfg.source:
            sys.stderr.write(f"  Yapılandırma:  {', '.join(map(str, cfg.source))}\n")
        if cfg.blocked:
            sys.stderr.write(f"  Engellenen:    {', '.join(sorted(cfg.blocked))}\n")
        media_note = "reddedilir" if cfg.proxy_media == "block" else "taranmadan iletilir (X-Maskele-Unscanned)"
        sys.stderr.write(f"  Medya:         {media_note}\n")
    if srv.access_key:
        sys.stderr.write("  Erişim:        X-Maskele-Key başlığı gerekli\n")
    if srv.unsafe_passthrough:
        sys.stderr.write("⚠ --unsafe-passthrough açık: JSON olmayan gövdeler MASKELENMEDEN iletilir.\n")
    if host not in LOOPBACK and not srv.tls:
        sys.stderr.write(
            "⚠ TLS kapalı ve proxy yerel makinenin dışına açık. Yalnızca TLS sonlandıran bir "
            "ters proxy ya da güvenilir bir tünel arkasında kullanın.\n"
        )
    sys.stderr.write("Durdurmak için Ctrl+C.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
