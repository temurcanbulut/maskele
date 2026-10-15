"""v0.3.0 bağımsız incelemesinin (F-01..F-08) ve tasarım risklerinin regresyon testleri.

Kural aynı: upstream'e giden hiçbir baytta tespit edilebilir hassas değer olmamalı,
şüphede kalınca istek reddedilmeli; kodu ve protokolü bozmadan.
"""

import json
import socket
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_security import EMAIL, RawUpstream, _start, jpost, raw, upstream_bytes

from maskele import Masker, load_config
from maskele.cli import main
from maskele.proxy import ProxyServer


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


def sent_json(i=0):
    return json.loads(RawUpstream.log[i]["body"])


# --- F-01: protokol alanları ve sayılar --------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"id": EMAIL, "messages": []},
        {"messages": [{"role": "user", "content": [{"type": "thinking", "signature": f"sig {EMAIL}"}]}]},
        {"messages": [{"role": "tool", "tool_call_id": f"call-{EMAIL}", "content": "ok"}]},
        {"model": f"gpt-{EMAIL}", "messages": []},
    ],
)
def test_f01_pii_in_protocol_field_rejected(px, body):
    st, data = jpost(px, body)
    assert st == 422 and "protocol_field" in data
    assert EMAIL not in upstream_bytes()


def test_f01_numbers_scanned(px):
    jpost(
        px,
        {
            "model": "x",
            "temperature": 0.7,
            "max_tokens": 1024,
            "seed": 10000000146,
            "metadata": {"phone": 5321234567, "tckn": 10000000146, "count": 3},
            "messages": [{"role": "user", "content": "x"}],
        },
    )
    sent = sent_json()
    raw_sent = upstream_bytes()
    assert "5321234567" not in raw_sent.replace('"seed": 10000000146', "")
    assert sent["metadata"]["count"] == 3
    assert isinstance(sent["metadata"]["phone"], str) and sent["metadata"]["phone"].startswith("[[PHONE_")
    assert sent["metadata"]["tckn"].startswith("[[TCKN_")
    # Protokolün sayısal ayarları dokunulmadan kalır
    assert sent["temperature"] == 0.7 and sent["max_tokens"] == 1024 and sent["seed"] == 10000000146


def test_f01_structural_ids_still_work(px):
    """Normal protokol kimlikleri (PII içermeyen) aynen geçer."""
    jpost(
        px,
        {
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {"id": "call_abc123", "type": "function", "function": {"name": "f", "arguments": "{}"}}
                    ],
                },
                {"role": "tool", "tool_call_id": "call_abc123", "content": "ok"},
            ],
        },
    )
    sent = sent_json()
    assert sent["messages"][-1]["tool_call_id"] == "call_abc123"


# --- F-02: parola bağlamında koşulsuz maskeleme ------------------------------


@pytest.mark.parametrize(
    "line,val",
    [
        ("password=letmein", "letmein"),
        ('password="summer"', "summer"),
        ('password="welcome"', "welcome"),
        ('password="Correct Horse Battery Staple"', "Correct Horse Battery Staple"),
        ("api_key=foobar", "foobar"),
        ("parola: Ankara", "Ankara"),
        ("şifre: deneme", "deneme"),
        ('"client_secret": "Secret"', "Secret"),
    ],
)
def test_f02_weak_passwords_masked(line, val):
    assert val not in Masker().mask(line).text


@pytest.mark.parametrize(
    "line",
    [
        "self.secret = secrets.token_urlsafe(24)",
        "api_key = os.environ['OPENAI_API_KEY']",
        "password: str = Field(..., min_length=8)",
        "token: Optional[str] = None",
        "DB_PASSWORD=${DB_PASSWORD}",
        "self.access_key = access_key",
        'client_secret: "<your-client-secret>"',
        "password = [[SECRET_1]]",
    ],
)
def test_f02_code_still_not_secret(line):
    assert Masker().mask(line).text == line


# --- F-03: başlıklar ---------------------------------------------------------


def test_f03_metadata_headers_dropped(px):
    jpost(
        px,
        {"messages": []},
        headers={
            "HTTP-Referer": f"https://x.invalid/c/{EMAIL}",
            "X-Title": f"Call {EMAIL}",
            "anthropic-beta": "tools-2024",
        },
    )
    h = {k.lower(): v for k, v in RawUpstream.log[0]["headers"].items()}
    assert "http-referer" not in h and "x-title" not in h and h["anthropic-beta"] == "tools-2024"
    assert EMAIL not in upstream_bytes()


def test_f03_forwarded_headers_are_scanned(px):
    st, data = jpost(px, {"messages": []}, headers={"User-Agent": f"app/1.0 ({EMAIL})"})
    assert st == 422 and "header" in data and RawUpstream.log == []


# --- F-04: güvenilmeyen proje yapılandırması ---------------------------------

WEAKEN = """
[detect]
disable = ["EMAIL", "SECRET", "API_KEY"]
[policy]
IBAN = "allow"
[allowlist]
values = ["alice@firma.com.tr"]
[proxy]
upstream = "https://unexpected.example.invalid"
[vault]
ttl_hours = 9999
"""
STRENGTHEN = """
[detect]
enable = ["HOST"]
[policy]
PRIVATE_KEY = "block"
[[patterns]]
name = "CUSTOMER_ID"
regex = 'CUS-\\d{6}'
"""


MIXED = """
[detect]
disable = ["EMAIL", "SECRET", "API_KEY"]
enable = ["HOST"]
[policy]
IBAN = "allow"
PRIVATE_KEY = "block"
[allowlist]
values = ["alice@firma.com.tr"]
[proxy]
upstream = "https://unexpected.example.invalid"
[vault]
ttl_hours = 9999
[[patterns]]
name = "CUSTOMER_ID"
regex = 'CUS-\\d{6}'
"""


def test_f04_untrusted_project_cannot_weaken(tmp_path, monkeypatch):
    monkeypatch.delenv("MASKELE_NO_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    proj = tmp_path / "repo"
    proj.mkdir()
    (proj / ".maskele.toml").write_text(MIXED, encoding="utf-8")
    monkeypatch.chdir(proj)
    cfg = load_config()
    assert "EMAIL" in cfg.kinds and "SECRET" in cfg.kinds and "IBAN" in cfg.kinds
    assert cfg.proxy_upstream == "https://api.openai.com"
    assert not cfg.allow_values and cfg.vault_ttl_hours == 24
    assert cfg.ignored and any("disable" in x for x in cfg.ignored)
    # Sıkılaştıran ayarlar güvensiz projeden de uygulanır
    assert "PRIVATE_KEY" in cfg.blocked and any(c.name == "CUSTOMER_ID" for c in cfg.custom)
    assert "HOST" in cfg.kinds


def test_f04_trust_is_explicit_and_pinned(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MASKELE_NO_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    proj = tmp_path / "repo"
    proj.mkdir()
    f = proj / ".maskele.toml"
    f.write_text(WEAKEN, encoding="utf-8")
    monkeypatch.chdir(proj)
    assert main(["config", "trust"]) == 0
    cfg = load_config()
    assert "EMAIL" not in cfg.kinds and cfg.proxy_upstream == "https://unexpected.example.invalid"
    # Dosya değişince güven düşer
    f.write_text(WEAKEN + "\n# değişti\n", encoding="utf-8")
    assert "EMAIL" in load_config().kinds


def test_f04_explicit_config_is_trusted(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text(WEAKEN, encoding="utf-8")
    assert "EMAIL" not in load_config(p).kinds


# --- F-05: yönlendirmeler ----------------------------------------------------


class Redirector(BaseHTTPRequestHandler):
    target = ""

    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(302)
        self.send_header("Location", Redirector.target + self.path)
        self.send_header("Content-Length", "0")
        self.end_headers()


def test_f05_redirects_not_followed():
    RawUpstream.log = []
    b = _start(ThreadingHTTPServer(("127.0.0.1", 0), RawUpstream))
    Redirector.target = f"http://127.0.0.1:{b.server_address[1]}"
    a = _start(ThreadingHTTPServer(("127.0.0.1", 0), Redirector))
    srv = _start(
        ProxyServer(
            ("127.0.0.1", 0), Masker(), f"http://127.0.0.1:{a.server_address[1]}", quiet=True, use_env_proxy=False
        )
    )
    try:
        st, data = jpost(
            srv, {"messages": []}, headers={"Authorization": "Bearer synthetic-123", "X-Api-Key": "synthetic-456"}
        )
        assert st == 502 and "redirect" in data
        assert RawUpstream.log == []  # B hiçbir şey almadı
        assert "Location" not in data and str(b.server_address[1]) not in data
    finally:
        for s in (srv, a, b):
            s.shutdown()
            s.server_close()


# --- F-06: bağlantı sınırları ------------------------------------------------


def _partial(port):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall(b"POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1\r\n")  # başlık yarım
    return s


def test_f06_connection_cap():
    srv = _start(
        ProxyServer(
            ("127.0.0.1", 0),
            Masker(),
            "http://127.0.0.1:9",
            quiet=True,
            use_env_proxy=False,
            max_connections=2,
            conn_timeout=5,
        )
    )
    port = srv.server_address[1]
    socks = []
    try:
        socks = [_partial(port), _partial(port)]
        time.sleep(0.2)
        before = threading.active_count()
        extra = [_partial(port) for _ in range(10)]
        time.sleep(0.3)
        assert threading.active_count() - before <= 1  # yeni iş parçacığı açılmadı
        for s in extra:
            s.settimeout(2)
            try:
                data = s.recv(1024)
            except (ConnectionAbortedError, ConnectionResetError):
                # Windows can reset a rejected connection with unread input.
                data = b""
            assert data == b"" or b"503" in data  # hemen reddedildi
            s.close()
    finally:
        for s in socks:
            s.close()
        srv.shutdown()
        srv.server_close()


def test_f06_slow_client_times_out():
    srv = _start(
        ProxyServer(("127.0.0.1", 0), Masker(), "http://127.0.0.1:9", quiet=True, use_env_proxy=False, conn_timeout=1)
    )
    try:
        s = _partial(srv.server_address[1])
        s.settimeout(5)
        t0 = time.time()
        data = s.recv(1024)
        assert time.time() - t0 < 3 and (data == b"" or b"408" in data)
        s.close()
    finally:
        srv.shutdown()
        srv.server_close()


# --- F-07: TLS ---------------------------------------------------------------


def _self_signed(tmp_path):
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    c, k = tmp_path / "c.pem", tmp_path / "k.pem"
    c.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    k.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return str(c), str(k)


def test_f07_tls_serving(tmp_path):
    cert, key = _self_signed(tmp_path)
    srv = _start(
        ProxyServer(
            ("127.0.0.1", 0),
            Masker(),
            "http://127.0.0.1:9",
            quiet=True,
            use_env_proxy=False,
            tls_cert=cert,
            tls_key=key,
        )
    )
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        import http.client

        c = http.client.HTTPSConnection("127.0.0.1", srv.server_address[1], context=ctx, timeout=5)
        c.request("GET", "/maskele/health")
        assert c.getresponse().status == 200
        # Düz HTTP ile bağlanılamaz
        with pytest.raises(Exception):
            raw(srv, "GET", "/maskele/health")
    finally:
        srv.shutdown()
        srv.server_close()


def test_f07_external_bind_requires_tls(monkeypatch):
    monkeypatch.setenv("K", "k" * 24)
    with pytest.raises(SystemExit) as e:
        main(["proxy", "--host", "0.0.0.0", "--access-key-env", "K", "-p", "0"])
    assert "TLS" in str(e.value)


# --- F-08: rapor yolları -----------------------------------------------------


def test_f08_report_paths_redacted(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "canary-check-9082@demo-fakecorp.com"
    d.mkdir()
    (d / "app.log").write_text("db 10.20.3.7", encoding="utf-8")
    for fmt in ("json", "sarif"):
        main(["scan", ".", "-f", fmt])
        out = capsys.readouterr().out
        assert "canary-check-9082@demo-fakecorp.com" not in out and "REDACTED" in out
        assert str(tmp_path) not in out  # mutlak yol da yok


# --- Tasarım: istek başına kasa ---------------------------------------------


def test_design_per_request_vault(px):
    jpost(px, {"messages": [{"role": "user", "content": "alice@firma.com.tr"}]})
    jpost(px, {"messages": [{"role": "user", "content": "bob@firma.com.tr"}]})
    a, b = sent_json(0), sent_json(1)
    # İkisi de EMAIL_1 alır: numaralandırma alanı paylaşılmaz
    assert "[[EMAIL_1]]" in a["messages"][-1]["content"] and "[[EMAIL_1]]" in b["messages"][-1]["content"]
    assert len(px.masker.vault) == 0  # sunucuda kalıcı eşleme birikmez


# --- Tasarım: medya politikası ----------------------------------------------

IMG = {
    "messages": [
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 300}}]}
    ]
}


def test_media_default_flags_unscanned(px):
    import http.client

    c = http.client.HTTPConnection("127.0.0.1", px.server_address[1], timeout=5)
    c.request("POST", "/v1/chat/completions", body=json.dumps(IMG), headers={"Content-Type": "application/json"})
    r = c.getresponse()
    r.read()
    assert r.status == 200 and r.getheader("X-Maskele-Unscanned") == "media"


def test_media_block_policy(tmp_path, px):
    p = tmp_path / "c.toml"
    p.write_text('[proxy]\nmedia = "block"\n', encoding="utf-8")
    px.masker = Masker(config=load_config(p))
    st, data = jpost(px, IMG)
    assert st == 422 and "media" in data and RawUpstream.log == []


# --- Kapsam: adres ve elle maskeleme ----------------------------------------


@pytest.mark.parametrize(
    "addr",
    [
        "Cumhuriyet Mah. Atatürk Cad. No: 12 D: 5 34380 Şişli/İstanbul",
        "Bağdat Caddesi No:145 Daire 7 Kadıköy",
        "Esentepe Mahallesi, Büyükdere Caddesi No: 199, Kat 6, 34394 Şişli / İstanbul",
        "Gül Sokak No 3/2 Çankaya Ankara",
    ],
)
def test_address_detected(addr):
    out = Masker().mask(f"Teslimat adresi: {addr}. Teşekkürler").text
    assert "No" not in out.split("Teslimat adresi:")[1].split(".")[0] or "[[ADDRESS_1]]" in out
    assert "[[ADDRESS_1]]" in out


def test_manual_values(tmp_path, monkeypatch, capsys):
    m = Masker(extra_values={"Proje Kartal": "CUSTOM", "Orkun": "NAME"})
    assert m.mask("Proje Kartal'da Orkun var").text == "[[CUSTOM_1]]'da [[NAME_1]] var"
    monkeypatch.setenv("MASKELE_HOME", str(tmp_path))
    f = tmp_path / "x.txt"
    f.write_text("Proje Kartal gecikti", encoding="utf-8")
    assert main(["mask", str(f), "-q", "--also", "Proje Kartal"]) == 0
    assert "Proje Kartal" not in capsys.readouterr().out


def test_scan_confidence_levels(tmp_path, capsys):
    """Maskeleme belirsiz değerleri de maskeler; tarama varsayılan olarak yalnızca eminleri raporlar."""
    f = tmp_path / "labels.js"
    f.write_text('const L = {PASSWORD: "Parola"};\nconst db = {password: "Kx9!mQ2v"};\n', encoding="utf-8")
    assert "Parola" not in Masker().mask(f.read_text()).text  # maskelemede yine maskelenir
    main(["scan", str(f), "-f", "json"])
    assert [x["line"] for x in json.loads(capsys.readouterr().out)["findings"]] == [2]
    main(["scan", str(f), "-f", "json", "--all"])
    assert [x["line"] for x in json.loads(capsys.readouterr().out)["findings"]] == [1, 2]
