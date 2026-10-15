"""v0.4.0 bağımsız incelemesinin (Y-01..Y-03) ve çok turlu konuşma desteğinin testleri."""

import itertools
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_security import EMAIL, RawUpstream, _start, jpost, upstream_bytes

from maskele import Masker, load_config
from maskele.proxy import ProxyServer, redact_path


def _proxy(upstream_port, **kw):
    return _start(
        ProxyServer(
            ("127.0.0.1", 0),
            kw.pop("masker", Masker()),
            f"http://127.0.0.1:{upstream_port}",
            quiet=True,
            use_env_proxy=False,
            **kw,
        )
    )


@pytest.fixture
def px():
    RawUpstream.log, RawUpstream.reply = [], "ok"
    up = _start(ThreadingHTTPServer(("127.0.0.1", 0), RawUpstream))
    srv = _proxy(up.server_address[1])
    yield srv
    srv.shutdown()
    up.shutdown()
    srv.server_close()
    up.server_close()


# --- Y-01: JSON Schema anahtarları -------------------------------------------


def test_y01_pii_in_schema_key_rejected(px):
    body = {
        "messages": [],
        "tools": [
            {
                "type": "function",
                "function": {"name": "x", "parameters": {"type": "object", "properties": {EMAIL: {"type": "string"}}}},
            }
        ],
    }
    st, data = jpost(px, body)
    assert st == 422 and "protocol_field" in data
    assert EMAIL not in upstream_bytes()


def test_y01_normal_schema_untouched(px):
    params = {
        "type": "object",
        "properties": {"email": {"type": "string", "description": "Alıcı adresi"}, "tckn": {"type": "string"}},
        "required": ["email"],
    }
    jpost(px, {"messages": [], "tools": [{"type": "function", "function": {"name": "x", "parameters": params}}]})
    sent = json.loads(RawUpstream.log[0]["body"])
    assert sent["tools"][0]["function"]["parameters"] == params


# --- Y-02: medya politikası tüm medya biçimlerini kapsar ---------------------

MEDIA_BODIES = [
    {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "https://images.example.invalid/private/photo.png"}}
                ],
            }
        ]
    },
    {"input": [{"role": "user", "content": [{"type": "input_file", "file_id": "file_public_12345"}]}]},
    {"input": [{"role": "user", "content": [{"type": "input_image", "image_url": "https://x.invalid/a.jpg"}]}]},
    {
        "max_tokens": 10,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "image", "source": {"type": "url", "url": "https://x.invalid/scan.png"}}],
            }
        ],
    },
    {
        "max_tokens": 10,
        "messages": [
            {"role": "user", "content": [{"type": "document", "source": {"type": "file", "file_id": "file_abc"}}]}
        ],
    },
    {
        "messages": [
            {"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": "UklGR", "format": "wav"}}]}
        ]
    },
]


@pytest.mark.parametrize("body", MEDIA_BODIES)
def test_y02_block_covers_all_media(tmp_path, px, body):
    p = tmp_path / "c.toml"
    p.write_text('[proxy]\nmedia = "block"\n', encoding="utf-8")
    px.masker = Masker(config=load_config(p))
    st, data = jpost(px, body)
    assert st == 422 and "media" in data and RawUpstream.log == []


@pytest.mark.parametrize("body", MEDIA_BODIES)
def test_y02_allow_still_flags_all_media(px, body):
    import http.client

    c = http.client.HTTPConnection("127.0.0.1", px.server_address[1], timeout=5)
    c.request("POST", "/v1/chat/completions", body=json.dumps(body), headers={"Content-Type": "application/json"})
    r = c.getresponse()
    r.read()
    assert r.status == 200 and r.getheader("X-Maskele-Unscanned") == "media"


def test_y02_plain_text_not_flagged(px):
    import http.client

    c = http.client.HTTPConnection("127.0.0.1", px.server_address[1], timeout=5)
    c.request(
        "POST",
        "/v1/chat/completions",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"messages": [{"role": "user", "content": "https://docs.example.invalid/page"}]}),
    )
    r = c.getresponse()
    r.read()
    assert r.getheader("X-Maskele-Unscanned") is None


# --- Y-03: log'larda yol anonimleştirme --------------------------------------


def test_y03_audit_log_path_redacted(tmp_path):
    RawUpstream.log = []
    up = _start(ThreadingHTTPServer(("127.0.0.1", 0), RawUpstream))
    log = tmp_path / "audit.jsonl"
    srv = _proxy(up.server_address[1], audit_path=str(log))
    try:
        st, _ = jpost(srv, {"messages": []}, path=f"/v1/customers/{EMAIL}?x=1")
        assert st == 422
        text = log.read_text()
        assert EMAIL not in text and "x=1" not in text and "REDACTED" in text
    finally:
        srv.shutdown()
        up.shutdown()
        srv.server_close()
        up.server_close()


@pytest.mark.parametrize(
    "path",
    [
        f"/v1/customers/{EMAIL}",
        "/v1/customers/alice%40firma.com.tr",
        "/v1/u/10000000146/x?y=z",
    ],
)
def test_y03_redact_path_variants(path):
    out = redact_path(path)
    assert "alice" not in out and "10000000146" not in out and "?" not in out
    assert out.startswith("/v1/")


# --- Çok turlu: previous_response_id ----------------------------------------


class ResponsesUpstream(BaseHTTPRequestHandler):
    """Responses API'yi taklit eder: her cevaba yeni bir id verir, ayarlanmış metni döndürür."""

    protocol_version = "HTTP/1.1"
    ids = itertools.count(1)
    reply = ""
    log: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        ResponsesUpstream.log.append(body)
        out = json.dumps(
            {
                "id": f"resp_{next(self.ids)}",
                "object": "response",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": ResponsesUpstream.reply}]}],
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


@pytest.fixture
def rx():
    ResponsesUpstream.log, ResponsesUpstream.ids = [], itertools.count(1)
    up = _start(ThreadingHTTPServer(("127.0.0.1", 0), ResponsesUpstream))
    srv = _proxy(up.server_address[1])
    yield srv
    srv.shutdown()
    up.shutdown()
    srv.server_close()
    up.server_close()


def _text(data):
    return json.loads(data)["output"][0]["content"][0]["text"]


def test_conversation_previous_response_id(rx):
    auth = {"Authorization": "Bearer sk-a"}
    ResponsesUpstream.reply = "Not aldım: [[EMAIL_1]]"
    st, d1 = jpost(rx, {"model": "x", "input": f"mailim {EMAIL}"}, "/v1/responses", auth)
    assert _text(d1) == f"Not aldım: {EMAIL}"
    # İkinci tur: e-posta bu istekte yok; yalnızca previous_response_id ile bağlı
    ResponsesUpstream.reply = "Mailin [[EMAIL_1]] idi. Yeni adres: [[EMAIL_2]]"
    st, d2 = jpost(
        rx,
        {"model": "x", "previous_response_id": "resp_1", "input": "yeni adresim bob@firma.com.tr"},
        "/v1/responses",
        auth,
    )
    assert _text(d2) == f"Mailin {EMAIL} idi. Yeni adres: bob@firma.com.tr"
    # Numaralandırma tutarlı: yeni değer EMAIL_1 ile çakışmaz
    assert "[[EMAIL_2]]" in ResponsesUpstream.log[1]["input"]
    assert EMAIL not in json.dumps(ResponsesUpstream.log)


def test_conversation_bound_to_credentials(rx):
    ResponsesUpstream.reply = "ok [[EMAIL_1]]"
    jpost(rx, {"model": "x", "input": f"mailim {EMAIL}"}, "/v1/responses", {"Authorization": "Bearer sk-a"})
    # Başka kimlik bilgisiyle aynı yanıt kimliğine bağlanan istek eski değeri alamaz
    st, d = jpost(
        rx,
        {"model": "x", "previous_response_id": "resp_1", "input": "tekrarla"},
        "/v1/responses",
        {"Authorization": "Bearer sk-baska"},
    )
    assert EMAIL not in d and "[[EMAIL_1]]" in _text(d)


def test_conversation_store_is_bounded(rx):
    store = rx.conversations
    for i in range(store.max_items + 50):
        store.put("k", f"resp_x{i}", {"tokens": {}, "index": {}, "counters": {}})
    assert len(store) <= store.max_items
