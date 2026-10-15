"""Proxy ve web arayüzü uçtan uca testleri (sahte upstream ile, ağ gerekmez)."""

import http.client
import json
import re
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from maskele import Masker
from maskele.proxy import ProxyServer
from maskele.ui import UIServer

SECRET_TEXT = "Sunucu 10.20.3.7 çöktü, müşteri Ahmet Yılmaz (ahmet@firma.com.tr, TCKN 10000000146) şikayet etti."
SECRETS = ["10.20.3.7", "Ahmet Yılmaz", "ahmet@firma.com.tr", "10000000146"]


# ---------------------------------------------------------------------------
# Sahte upstream: aldığı metni geri yankılar, tüm biçimlerde
# ---------------------------------------------------------------------------


class Upstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    received: list = []

    def log_message(self, *a):
        pass

    def _text(self, body):
        if "messages" in body:
            last = body["messages"][-1]["content"]
            if isinstance(last, list):
                last = "".join(p.get("text", "") for p in last)
            return f"Gördüm: {last}"
        return f"Gördüm: {body['input']}"

    def _sse(self, events):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for ev, data in events:
            block = (f"event: {ev}\n" if ev else "") + f"data: {data}\n\n"
            b = block.encode()
            self.wfile.write(f"{len(b):x}\r\n".encode() + b + b"\r\n")
        self.wfile.write(b"0\r\n\r\n")

    def do_GET(self):
        self.received.append(("GET", self.path, self.headers.get("Authorization"), None))
        b = json.dumps({"data": [{"id": "m1"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.received.append(
            ("POST", self.path, self.headers.get("Authorization") or self.headers.get("x-api-key"), body)
        )
        text = self._text(body)
        pieces = [text[i : i + 3] for i in range(0, len(text), 3)]  # token'ları bölecek kadar küçük

        if self.path == "/v1/chat/completions" and body.get("tools"):
            args = json.dumps({"to": "[[EMAIL_1]]", "note": "[[IP_1]] kontrol", "code": "IP_1 = 1"})
            chunks = [
                {
                    "object": "chat.completion.chunk",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"tool_calls": [{"index": 0, "function": {"arguments": args[i : i + 4]}}]},
                            "finish_reason": None,
                        }
                    ],
                }
                for i in range(0, len(args), 4)
            ]
            chunks.append(
                {
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                }
            )
            return self._sse([(None, json.dumps(c)) for c in chunks] + [(None, "[DONE]")])

        if self.path == "/v1/chat/completions" and body.get("stream"):
            ev = [
                (
                    None,
                    json.dumps(
                        {
                            "id": "c1",
                            "object": "chat.completion.chunk",
                            "choices": [{"index": 0, "delta": {"content": p}, "finish_reason": None}],
                        }
                    ),
                )
                for p in pieces
            ]
            ev.append(
                (
                    None,
                    json.dumps(
                        {
                            "id": "c1",
                            "object": "chat.completion.chunk",
                            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                        }
                    ),
                )
            )
            return self._sse(ev + [(None, "[DONE]")])

        if self.path == "/v1/chat/completions":
            b = json.dumps(
                {
                    "id": "c1",
                    "object": "chat.completion",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            return self.wfile.write(b)

        if self.path == "/v1/messages":
            ev = [
                ("message_start", json.dumps({"type": "message_start", "message": {"id": "m"}})),
                (
                    "content_block_start",
                    json.dumps(
                        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}
                    ),
                ),
            ]
            ev += [
                (
                    "content_block_delta",
                    json.dumps({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": p}}),
                )
                for p in pieces
            ]
            ev += [
                ("content_block_stop", json.dumps({"type": "content_block_stop", "index": 0})),
                ("message_stop", json.dumps({"type": "message_stop"})),
            ]
            return self._sse(ev)

        if self.path == "/v1/responses":
            ev = [
                (
                    None,
                    json.dumps(
                        {
                            "type": "response.output_text.delta",
                            "item_id": "i",
                            "output_index": 0,
                            "content_index": 0,
                            "delta": p,
                        }
                    ),
                )
                for p in pieces
            ]
            ev.append(
                (
                    None,
                    json.dumps(
                        {
                            "type": "response.output_text.done",
                            "item_id": "i",
                            "output_index": 0,
                            "content_index": 0,
                            "text": text,
                        }
                    ),
                )
            )
            return self._sse(ev)

        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _start(server):
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


@pytest.fixture
def stack():
    Upstream.received = []
    up = _start(ThreadingHTTPServer(("127.0.0.1", 0), Upstream))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    px = _start(
        ProxyServer(("127.0.0.1", 0), Masker(), f"http://127.0.0.1:{up.server_address[1]}", quiet=True, opener=opener)
    )
    yield px
    px.shutdown()
    up.shutdown()
    px.server_close()
    up.server_close()


def call(server, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    h = {"Content-Type": "application/json", **(headers or {})}
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = c.getresponse()
    data = r.read().decode()
    c.close()
    return r.status, dict(r.getheaders()), data


def sse_events(raw):
    for block in raw.split("\n\n"):
        data = [ln[6:] for ln in block.split("\n") if ln.startswith("data: ")]
        ev = [ln[7:] for ln in block.split("\n") if ln.startswith("event: ")]
        if data:
            yield (ev[0] if ev else None), "\n".join(data)


def assert_upstream_clean():
    sent = json.dumps([r[3] for r in Upstream.received], ensure_ascii=False)
    for s in SECRETS:
        assert s not in sent, f"{s!r} upstream'e sızdı"


# ---------------------------------------------------------------------------


def test_openai_nonstream(stack):
    st, _, data = call(
        stack,
        "POST",
        "/v1/chat/completions",
        {"model": "gpt-x", "messages": [{"role": "user", "content": SECRET_TEXT}]},
        {"Authorization": "Bearer sk-test"},
    )
    assert st == 200
    assert json.loads(data)["choices"][0]["message"]["content"] == f"Gördüm: {SECRET_TEXT}"
    assert_upstream_clean()
    sent = Upstream.received[0]
    assert sent[2] == "Bearer sk-test"  # anahtar olduğu gibi iletilir
    assert sent[3]["model"] == "gpt-x"  # yapısal alanlar dokunulmaz
    assert sent[3]["messages"][0]["role"] == "system"  # ipucu eklendi
    assert "[[IP_1]]" in sent[3]["messages"][-1]["content"]


def test_openai_stream(stack):
    st, h, data = call(
        stack,
        "POST",
        "/v1/chat/completions",
        {"model": "x", "stream": True, "messages": [{"role": "user", "content": SECRET_TEXT}]},
    )
    assert st == 200 and "text/event-stream" in h["Content-Type"]
    text = ""
    for _, d in sse_events(data):
        if d != "[DONE]":
            text += json.loads(d)["choices"][0]["delta"].get("content") or ""
    assert text == f"Gördüm: {SECRET_TEXT}"
    assert_upstream_clean()


def test_openai_stream_tool_args(stack):
    call(stack, "POST", "/v1/chat/completions", {"model": "x", "messages": [{"role": "user", "content": SECRET_TEXT}]})
    st, _, data = call(
        stack,
        "POST",
        "/v1/chat/completions",
        {
            "model": "x",
            "stream": True,
            "tools": [{"type": "function", "function": {"name": "mail"}}],
            "messages": [{"role": "user", "content": SECRET_TEXT}],
        },
    )
    args = ""
    for _, d in sse_events(data):
        if d != "[DONE]":
            for tc in json.loads(d)["choices"][0]["delta"].get("tool_calls") or []:
                args += tc["function"]["arguments"]
    # Proxy katıdır: yalnızca [[TOKEN]] çevrilir, koddaki IP_1 değişken adı korunur
    assert json.loads(args) == {"to": "ahmet@firma.com.tr", "note": "10.20.3.7 kontrol", "code": "IP_1 = 1"}


def test_anthropic_stream(stack):
    st, _, data = call(
        stack,
        "POST",
        "/v1/messages",
        {
            "model": "claude-x",
            "max_tokens": 100,
            "stream": True,
            "system": "Sen yardımcısın.",
            "messages": [{"role": "user", "content": [{"type": "text", "text": SECRET_TEXT}]}],
        },
        {"x-api-key": "sk-ant-test", "anthropic-version": "2023-06-01"},
    )
    assert st == 200
    text = "".join(json.loads(d)["delta"]["text"] for e, d in sse_events(data) if e == "content_block_delta")
    assert text == f"Gördüm: {SECRET_TEXT}"
    sent = Upstream.received[0][3]
    assert sent["system"].startswith("Sen yardımcısın.") and "[[IP_1]]" in sent["system"]
    assert Upstream.received[0][2] == "sk-ant-test"
    assert_upstream_clean()


def test_responses_api_stream(stack):
    st, _, data = call(stack, "POST", "/v1/responses", {"model": "x", "stream": True, "input": SECRET_TEXT})
    deltas, done = "", None
    for _, d in sse_events(data):
        o = json.loads(d)
        if o["type"].endswith(".delta"):
            deltas += o["delta"]
        elif o["type"] == "response.output_text.done":
            done = o["text"]
    assert deltas == done == f"Gördüm: {SECRET_TEXT}"
    assert "[[" in Upstream.received[0][3]["instructions"]
    assert_upstream_clean()


def test_proxy_get_passthrough_and_stats(stack):
    st, _, data = call(stack, "GET", "/v1/models", headers={"Authorization": "Bearer k"})
    assert st == 200 and json.loads(data)["data"][0]["id"] == "m1"
    call(stack, "POST", "/v1/chat/completions", {"model": "x", "messages": [{"role": "user", "content": SECRET_TEXT}]})
    st, _, data = call(stack, "GET", "/maskele/stats")
    s = json.loads(data)
    assert s["requests"] == 2 and s["masked"] == 4 and s["by_kind"]["TCKN"] == 1


def test_proxy_rejects_foreign_host(stack):
    st, _, data = call(stack, "POST", "/v1/chat/completions", {"messages": []}, {"Host": "evil.example"})
    assert st == 403 and "maskele_forbidden_host" in data
    assert Upstream.received == []


def test_proxy_upstream_down():
    px = _start(ProxyServer(("127.0.0.1", 0), Masker(), "http://127.0.0.1:9", quiet=True, use_env_proxy=False))
    try:
        st, _, data = call(px, "POST", "/v1/chat/completions", {"messages": []})
        assert st == 502 and "maskele_upstream_error" in data
        stats = json.loads(call(px, "GET", "/maskele/stats")[2])
        assert stats["requests"] == 1 and stats["errors"] == 1
    finally:
        px.shutdown()
        px.server_close()


def test_proxy_audit_log(tmp_path):
    Upstream.received = []
    up = _start(ThreadingHTTPServer(("127.0.0.1", 0), Upstream))
    log = tmp_path / "audit.jsonl"
    px = _start(
        ProxyServer(
            ("127.0.0.1", 0),
            Masker(),
            f"http://127.0.0.1:{up.server_address[1]}",
            quiet=True,
            audit_path=str(log),
            use_env_proxy=False,
        )
    )
    try:
        call(px, "POST", "/v1/chat/completions", {"model": "x", "messages": [{"role": "user", "content": SECRET_TEXT}]})
        entry = json.loads(log.read_text().strip())
        assert entry["masked"] == {"IP": 1, "NAME": 1, "EMAIL": 1, "TCKN": 1} and entry["status"] == 200
        for s in SECRETS:
            assert s not in log.read_text()
    finally:
        px.shutdown()
        up.shutdown()
        px.server_close()
        up.server_close()


# ---------------------------------------------------------------------------
# Web arayüzü
# ---------------------------------------------------------------------------


@pytest.fixture
def ui():
    saved = []
    srv = _start(UIServer(("127.0.0.1", 0), Masker(), "test", save=lambda: saved.append(1)))
    srv.saved = saved
    yield srv
    srv.shutdown()
    srv.server_close()


def test_ui_page_and_headers(ui):
    st, h, html = call(ui, "GET", "/")
    assert st == 200 and ui.token in html and "{{TOKEN}}" not in html
    assert "default-src 'none'" in h["Content-Security-Policy"]
    assert h["X-Content-Type-Options"] == "nosniff"
    for asset in ("/app.js", "/app.css"):
        assert call(ui, "GET", asset)[0] == 200
    assert not re.search(r"https?://(?!127\.0\.0\.1)", html)  # dışarıya istek yok


def test_ui_requires_token_and_host(ui):
    assert call(ui, "POST", "/api/mask", {"text": "10.0.0.5"})[0] == 403
    assert call(ui, "POST", "/api/mask", {"text": "x"}, {"X-Maskele-Token": "wrong"})[0] == 403
    assert call(ui, "GET", "/api/vault", headers={"X-Maskele-Token": ui.token, "Host": "evil.com"})[0] == 403
    assert call(ui, "GET", "/", headers={"Host": "rebind.attacker.com"})[0] == 403


def test_ui_mask_preview_commit_unmask(ui):
    t = {"X-Maskele-Token": ui.token}
    st, _, d = call(ui, "POST", "/api/mask", {"text": SECRET_TEXT, "commit": False}, t)
    r = json.loads(d)
    assert st == 200 and "[[IP_1]]" in r["masked"] and r["counts"]["TCKN"] == 1
    assert SECRET_TEXT[r["spans"][0]["start"] : r["spans"][0]["end"]] == "10.20.3.7"
    assert len(ui.masker.vault) == 0 and not ui.saved  # önizleme kasaya yazmaz

    call(ui, "POST", "/api/mask", {"text": SECRET_TEXT, "commit": True}, t)
    assert len(ui.masker.vault) == 4 and ui.saved

    st, _, d = call(ui, "POST", "/api/unmask", {"text": "Bak: [IP_1] ve [[EMAIL_1]], [[IP_9]], TCKN_1"}, t)
    r = json.loads(d)
    assert r["text"] == "Bak: 10.20.3.7 ve ahmet@firma.com.tr, [[IP_9]], TCKN_1"
    assert r["bare"] == ["TCKN_1"]
    assert [(r["text"][s["start"] : s["end"]], s["token"]) for s in r["spans"]] == [
        ("10.20.3.7", "IP_1"),
        ("ahmet@firma.com.tr", "EMAIL_1"),
    ]
    assert r["unknown"] == ["IP_9"]

    items = json.loads(call(ui, "GET", "/api/vault", headers=t)[2])["items"]
    assert {"token": "TCKN_1", "kind": "TCKN", "value": "10000000146"} in items
    call(ui, "POST", "/api/clear", {}, t)
    assert len(ui.masker.vault) == 0


def test_ui_suspects_and_manual_mask(ui):
    t = {"X-Maskele-Token": ui.token}
    text = "Toplantıya Zerda Tekeli ve Ahmet Yılmaz katıldı. Proje Kartal gecikiyor."
    r = json.loads(call(ui, "POST", "/api/mask", {"text": text}, t)[2])
    sus = [s["text"] for s in r["suspects"]]
    assert "Zerda Tekeli" in sus and "Ahmet Yılmaz" not in sus  # maskelenen aday değil
    assert call(ui, "POST", "/api/also", {"value": "Zerda Tekeli", "kind": "NAME"}, t)[0] == 200
    assert call(ui, "POST", "/api/also", {"value": "Proje Kartal"}, t)[0] == 200
    assert call(ui, "POST", "/api/also", {"value": "x", "kind": "EVIL"}, t)[0] == 400
    r = json.loads(call(ui, "POST", "/api/mask", {"text": text}, t)[2])
    assert "Zerda Tekeli" not in r["masked"] and "Proje Kartal" not in r["masked"]
    assert "Zerda Tekeli" not in [s["text"] for s in r["suspects"]]
