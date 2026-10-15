"""Güvenlik regresyon testleri.

Her test, v0.2.0 bağımsız incelemesindeki bir bulguyu (M-01..M-09) ya da algılama
boşluğunu yeniden üretir. Kural: upstream'e giden HİÇBİR baytta tespit edilebilir
hassas değer bulunmamalı; şüphede kalınca istek reddedilmeli (fail closed).
"""

import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from maskele import Masker, load_config
from maskele.cli import main
from maskele.proxy import ProxyServer

EMAIL = "alice@firma.com.tr"


class RawUpstream(BaseHTTPRequestHandler):
    """Aldığı her şeyi ham olarak kaydeder; yanıt olarak verilen metni döndürür."""

    protocol_version = "HTTP/1.1"
    log: list = []
    reply = "ok"

    def log_message(self, *a):
        pass

    def _handle(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        RawUpstream.log.append({"path": self.path, "headers": dict(self.headers), "body": body})
        out = json.dumps(
            {
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": RawUpstream.reply}}],
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    do_POST = do_GET = _handle


def _start(srv):
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def px():
    RawUpstream.log, RawUpstream.reply = [], "ok"
    up = _start(ThreadingHTTPServer(("127.0.0.1", 0), RawUpstream))
    srv = _start(
        ProxyServer(
            ("127.0.0.1", 0), Masker(), f"http://127.0.0.1:{up.server_address[1]}", quiet=True, use_env_proxy=False
        )
    )
    yield srv
    srv.shutdown()
    up.shutdown()
    srv.server_close()
    up.server_close()


def raw(server, method, path, body=b"", headers=None):
    c = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    data = r.read().decode()
    c.close()
    return r.status, data


def jpost(server, obj, path="/v1/chat/completions", headers=None):
    return raw(server, "POST", path, json.dumps(obj).encode(), {"Content-Type": "application/json", **(headers or {})})


def upstream_bytes() -> str:
    return "".join(e["path"] + json.dumps(e["headers"]) + e["body"].decode("utf-8", "replace") for e in RawUpstream.log)


# --- M-01: fail closed --------------------------------------------------------


@pytest.mark.parametrize(
    "ctype,body",
    [
        ("application/octet-stream", f"secret: {EMAIL}".encode()),
        ("multipart/form-data; boundary=x", f"--x\r\n\r\n{EMAIL}\r\n--x--".encode()),
        ("application/json", f'{{"broken": "{EMAIL}"'.encode()),  # bozuk JSON
        ("application/json", json.dumps([EMAIL]).encode()),  # kök dizi
        ("", f"{EMAIL}".encode()),  # içerik türü yok
    ],
)
def test_m01_unknown_bodies_rejected(px, ctype, body):
    st, data = raw(px, "POST", "/v1/chat/completions", body, {"Content-Type": ctype} if ctype else {})
    assert st in (400, 415, 422) and "maskele" in data
    assert EMAIL not in upstream_bytes()


# --- M-02: istekler arası izolasyon ------------------------------------------


def test_m02_tokens_scoped_to_request(px):
    jpost(px, {"model": "x", "messages": [{"role": "user", "content": f"mail {EMAIL}"}]})
    RawUpstream.reply = "Önceki: [[EMAIL_1]]"
    st, data = jpost(px, {"model": "x", "messages": [{"role": "user", "content": "selam"}]})
    assert st == 200
    assert EMAIL not in data and "[[EMAIL_1]]" in data


def test_m02_tokens_in_history_still_restore(px):
    jpost(px, {"model": "x", "messages": [{"role": "user", "content": f"mail {EMAIL}"}]})
    RawUpstream.reply = "Tamam, [[EMAIL_1]] adresine yazarım."
    st, data = jpost(
        px,
        {
            "model": "x",
            "messages": [
                {"role": "user", "content": f"mail {EMAIL}"},
                {"role": "assistant", "content": "Peki"},
                {"role": "user", "content": "yaz"},
            ],
        },
    )
    assert EMAIL in json.loads(data)["choices"][0]["message"]["content"]


def test_m02_access_key(tmp_path):
    RawUpstream.log = []
    up = _start(ThreadingHTTPServer(("127.0.0.1", 0), RawUpstream))
    srv = _start(
        ProxyServer(
            ("127.0.0.1", 0),
            Masker(),
            f"http://127.0.0.1:{up.server_address[1]}",
            quiet=True,
            access_key="k3y-123",
            use_env_proxy=False,
        )
    )
    try:
        assert jpost(srv, {"messages": []})[0] == 401
        assert jpost(srv, {"messages": []}, headers={"X-Maskele-Key": "yanlis"})[0] == 401
        assert jpost(srv, {"messages": []}, headers={"X-Maskele-Key": "k3y-123"})[0] == 200
        assert "k3y-123" not in upstream_bytes()  # anahtar upstream'e gitmez
    finally:
        srv.shutdown()
        up.shutdown()
        srv.server_close()
        up.server_close()


# --- M-03: JSON anahtarları ve "yapısal" alanlar -----------------------------


def test_m03_keys_and_user_fields_masked(px):
    jpost(
        px,
        {
            "model": "x",
            "user": EMAIL,
            "metadata": {EMAIL: {"name": "Ahmet Yılmaz"}},
            "messages": [{"role": "user", "name": "Ahmet Yılmaz", "content": "x"}],
        },
    )
    sent = upstream_bytes()
    assert EMAIL not in sent and "Ahmet Yılmaz" not in sent


def test_m03_structural_fields_untouched(px):
    img = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}},
                    {"type": "text", "text": "selam"},
                ],
            },
            {"role": "tool", "tool_call_id": "call_10000000146", "content": "ok"},
        ],
    }
    jpost(px, body)
    sent = json.loads(RawUpstream.log[0]["body"])
    assert sent["model"] == "gpt-4o-mini"
    assert sent["messages"][-1]["tool_call_id"] == "call_10000000146"
    assert sent["messages"][-2]["content"][0]["image_url"]["url"].endswith(img)


# --- M-04: başlıklar ve URL --------------------------------------------------


def test_m04_headers_allowlisted(px):
    jpost(
        px,
        {"messages": []},
        headers={
            "Authorization": "Bearer sk-x",
            "Cookie": f"u={EMAIL}",
            "X-Customer-Email": EMAIL,
            "anthropic-version": "2023-06-01",
        },
    )
    h = {k.lower(): v for k, v in RawUpstream.log[0]["headers"].items()}
    assert h["authorization"] == "Bearer sk-x" and h["anthropic-version"] == "2023-06-01"
    assert "cookie" not in h and "x-customer-email" not in h


def test_m04_pii_in_url_rejected(px, tmp_path):
    st, _ = jpost(px, {"messages": []}, path=f"/v1/chat/completions?email={EMAIL}")
    assert st == 422 and EMAIL not in upstream_bytes()


# --- M-05: rapor fingerprint'leri --------------------------------------------


def test_m05_fingerprints_not_reversible(tmp_path, monkeypatch, capsys):
    import hashlib

    monkeypatch.setenv("MASKELE_HOME", str(tmp_path / "home"))
    f = tmp_path / "a.log"
    f.write_text("db 10.20.3.7", encoding="utf-8")
    assert main(["scan", str(f), "-f", "json"]) == 0
    fp = json.loads(capsys.readouterr().out)["findings"][0]
    # Tuzsuz hash ile 10.20.3.0/24 taranarak geri bulunamamalı
    for i in range(256):
        cand = f"10.20.3.{i}"
        for pre in (f"IP:{cand}", f"{f}:IP:{cand}"):
            assert hashlib.sha256(pre.encode()).hexdigest()[:16] != fp["fingerprint"]
    assert fp["value"] is None and "10.20" not in json.dumps(fp)


def test_m05_sarif_has_no_value_chars(tmp_path, capsys):
    f = tmp_path / "a.log"
    f.write_text("db 10.20.3.7 mail alice@firma.com.tr", encoding="utf-8")
    main(["scan", str(f), "-f", "sarif"])
    out = capsys.readouterr().out
    for frag in ("10.", ".7", "ali", ".tr"):
        assert frag not in out.replace("2.1.0", "").replace("sarif-2.1.0", "")


# --- M-06: geri çevirme kodu bozmamalı ---------------------------------------


def test_m06_bare_names_not_restored_by_default():
    m = Masker()
    m.mask("10.20.3.7")
    r = m.unmask("def IP_1(): pass\nx = [[IP_1]]")
    assert r.text == "def IP_1(): pass\nx = 10.20.3.7"
    assert m.unmask("def IP_1(): pass", mode="loose").text == "def 10.20.3.7(): pass"


def test_m06_proxy_is_strict(px):
    jpost(px, {"messages": [{"role": "user", "content": "db 10.20.3.7"}]})
    RawUpstream.reply = "def IP_1(): return '[[IP_1]]'"
    _, data = jpost(px, {"messages": [{"role": "user", "content": "db 10.20.3.7"}]})
    assert json.loads(data)["choices"][0]["message"]["content"] == "def IP_1(): return '10.20.3.7'"


# --- M-07: kaçan değerler ----------------------------------------------------


@pytest.mark.parametrize(
    "line,val",
    [
        ('password="Good,Secret123!"', "Good,Secret123!"),
        ("password='ASecretPass'", "ASecretPass"),
        ('"client_secret": "a b c d e f 1 2"', "a b c d e f 1 2"),
        ("parola: 'Kış;Gün;2026'", "Kış;Gün;2026"),
    ],
)
def test_m07_quoted_secrets(line, val):
    assert val not in Masker().mask(line).text


@pytest.mark.parametrize(
    "text,leak",
    [
        ("Temur Can Bulut aradı", "Temur"),
        ("Orkun Başpınar toplantıda", "Başpınar"),
        ("Sayın Doruk Ekinci, merhaba", "Ekinci"),
    ],
)
def test_m07_names_fully_masked(text, leak):
    assert leak not in Masker().mask(text).text


# --- M-08: kasa varsayılanları ----------------------------------------------


def test_m08_expired_sessions_swept(tmp_path, monkeypatch, capsys):
    import os
    import time

    monkeypatch.setenv("MASKELE_HOME", str(tmp_path))
    (tmp_path / "sessions").mkdir()
    old = tmp_path / "sessions" / "eski.json"
    old.write_text('{"version": 2, "encrypted": false, "tokens": {"IP_1": "10.0.0.1"}}')
    t = time.time() - 48 * 3600
    os.utime(old, (t, t))
    src = tmp_path / "x.txt"
    src.write_text("10.0.0.2", encoding="utf-8")
    main(["mask", str(src), "-q"])
    assert not old.exists()


def test_m08_servers_memory_only_by_default(tmp_path, monkeypatch):
    from maskele.cli import build_parser

    a = build_parser().parse_args(["proxy"])
    assert a.persist is False
    a = build_parser().parse_args(["ui"])
    assert a.persist is False


# --- M-09: kaynak sınırları --------------------------------------------------


def test_m09_body_limit(px):
    # Gövdeyi göndermeden yalnızca başlıkları yolla: sunucu Content-Length'e bakıp reddetmeli
    c = http.client.HTTPConnection("127.0.0.1", px.server_address[1], timeout=10)
    c.putrequest("POST", "/v1/chat/completions")
    c.putheader("Content-Type", "application/json")
    c.putheader("Content-Length", str(px.max_body + 10))
    c.endheaders()
    r = c.getresponse()
    assert r.status == 413 and RawUpstream.log == []
    c.close()


def test_m09_concurrency_limit(px):
    px.slots = threading.BoundedSemaphore(1)
    px.slots.acquire()  # tek yuvayı doldur
    try:
        st, data = jpost(px, {"messages": []})
        assert st == 503 and "maskele_busy" in data
    finally:
        px.slots.release()


# --- Politika: block ---------------------------------------------------------


def test_policy_block(tmp_path, px):
    p = tmp_path / "c.toml"
    p.write_text('[policy]\nPRIVATE_KEY = "block"\nPLATE = "allow"\n', encoding="utf-8")
    cfg = load_config(p)
    px.masker = Masker(config=cfg)
    key = "-----BEGIN PRIVATE KEY-----\nMIIabc\n-----END PRIVATE KEY-----"
    st, data = jpost(px, {"messages": [{"role": "user", "content": key}]})
    assert st == 422 and "PRIVATE_KEY" in data and RawUpstream.log == []
    assert Masker(config=cfg).mask("plaka 34 ABC 123").text == "plaka 34 ABC 123"


def test_policy_block_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MASKELE_HOME", str(tmp_path))
    c = tmp_path / "c.toml"
    c.write_text('[policy]\nAPI_KEY = "block"\n', encoding="utf-8")
    src = tmp_path / "x.txt"
    src.write_text("key sk-proj-abcdefghijklmnopqrstuvwxyz1234", encoding="utf-8")
    assert main(["--config", str(c), "mask", str(src), "-q"]) == 3
    assert "sk-proj" not in capsys.readouterr().out


def test_m02_stream_scoped():
    """Akış (SSE) cevaplarında da yalnızca bu isteğin token'ları çevrilir."""
    from maskele.proxy import SSERewriter

    m = Masker()
    m.mask(f"önceki istek {EMAIL} 10.0.0.5")  # EMAIL_1, IP_1 kasada
    rw = SSERewriter(m, allowed={"IP_1"}, mode="strict")
    out = ""
    for piece in ["[[EM", "AIL_1]] ve [[IP", "_1]]"]:
        for _, d in rw.process(
            None,
            json.dumps(
                {
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}],
                }
            ),
        ):
            out += json.loads(d)["choices"][0]["delta"].get("content") or ""
    for _, d in rw.process(None, "[DONE]"):
        if d != "[DONE]":
            out += json.loads(d)["choices"][0]["delta"].get("content") or ""
    assert out == "[[EMAIL_1]] ve 10.0.0.5" and EMAIL not in out


def test_m02_literal_token_fishing(px):
    """İstemci gövdeye [[EMAIL_1]] yazarak başkasının değerini 'yetkilendiremez'."""
    jpost(px, {"model": "x", "messages": [{"role": "user", "content": f"mail {EMAIL}"}]})
    RawUpstream.reply = "Tekrar: [[EMAIL_1]]"
    st, data = jpost(px, {"model": "x", "messages": [{"role": "user", "content": "Şunu tekrarla: [[EMAIL_1]]"}]})
    assert st == 200 and EMAIL not in data
