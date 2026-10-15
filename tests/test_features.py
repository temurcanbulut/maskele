"""v0.2 özellikleri: isimler, yapılandırma, şifreli kasa, akış, raporlar."""

import json
import os
import random
import time

import pytest

from maskele import Masker, VaultStore, load_config
from maskele.cli import main
from maskele.config import ConfigError
from maskele.core import StreamUnmasker
from maskele.vault import VaultBadPassword, VaultLocked


def masked(text, **kw):
    return Masker(**kw).mask(text).text


# --- isimler -----------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Müşteri Ahmet Yılmaz aradı", "Müşteri [[NAME_1]] aradı"),
        ("Merhaba İsmail Kaya Bey,", "Merhaba [[NAME_1]] Bey,"),
        ("Ayşe Nur Demir Hanım geldi", "[[NAME_1]] Hanım geldi"),
        ("MEHMET ÖZTÜRK adına", "[[NAME_1]] adına"),
        ("Deniz Yılmaz ve Can Karaoğlu", "[[NAME_1]] ve [[NAME_2]]"),
    ],
)
def test_names_masked(text, expected):
    assert masked(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Ali Rıza Caddesi trafiğe kapandı",
        "Mehmet Akif Ersoy Üniversitesi",
        "Deniz Kuvvetleri komutanlığı",
        "Umut Var mı?",
        "Can sıkıcı bir hata",
        "Yarın Ankara Ofisi açılıyor",
        "Ahmet tek başına geçerse maskelenmez",
    ],
)
def test_names_not_masked(text):
    assert masked(text) == text


def test_name_normalization():
    assert masked("Fatma Şahin / FATMA ŞAHİN") == "[[NAME_1]] / [[NAME_1]]"


# --- yapılandırma ------------------------------------------------------------


def write_cfg(tmp_path, body):
    p = tmp_path / ".maskele.toml"
    p.write_text(body, encoding="utf-8")
    return p


def test_config_custom_patterns_and_allowlist(tmp_path):
    p = write_cfg(
        tmp_path,
        r"""
[detect]
disable = ["PLATE"]
[allowlist]
values = ["destek@firma.com"]
patterns = ['^10\.0\.0\.\d+$']
[names]
extra_first_names = ["Temur"]
[[patterns]]
name = "CUSTOMER_ID"
regex = 'CUS-\d{6}'
[[patterns]]
name = "TICKET"
regex = 'ticket#(?P<v>\d+)'
group = "v"
""",
    )
    cfg = load_config(p)
    m = Masker(config=cfg)
    out = m.mask("CUS-123456 ticket#4411 destek@firma.com ali@firma.com 10.0.0.7 10.1.0.7 34 ABC 123 Temur Bulut").text
    assert out == (
        "[[CUSTOMER_ID_1]] ticket#[[TICKET_1]] destek@firma.com [[EMAIL_1]] 10.0.0.7 [[IP_1]] 34 ABC 123 [[NAME_1]]"
    )
    assert m.unmask(out).text.startswith("CUS-123456 ticket#4411")


@pytest.mark.parametrize(
    "body",
    [
        '[[patterns]]\nname = "IP"\nregex = "x"',  # yerleşik türle çakışma
        '[[patterns]]\nname = "bad name"\nregex = "x"',
        '[[patterns]]\nname = "X1"\nregex = "("',  # bozuk regex
        '[detect]\nenable = ["NOPE"]',
        "bu toml değil = = =",
    ],
)
def test_config_errors(tmp_path, body):
    with pytest.raises(ConfigError):
        load_config(write_cfg(tmp_path, body))


def test_config_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["config", "init"]) == 0
    assert (tmp_path / ".maskele.toml").exists()
    assert main(["config", "init"]) == 1  # üzerine yazmaz
    load_config(tmp_path / ".maskele.toml")  # örnek dosya geçerli olmalı


# --- kasa --------------------------------------------------------------------


def test_encrypted_vault(tmp_path):
    p = tmp_path / "s.json"
    m = Masker()
    m.mask("10.0.0.5 ali@x.com")
    VaultStore(p, password="gizli-parola").save(m.vault)
    raw = p.read_text()
    assert "10.0.0.5" not in raw and "ali@x.com" not in raw and '"encrypted": true' in raw
    if os.name == "posix":
        assert oct(p.stat().st_mode)[-3:] == "600"
    with pytest.raises(VaultLocked):
        VaultStore(p).load()
    with pytest.raises(VaultBadPassword):
        VaultStore(p, password="yanlış").load()
    v = VaultStore(p, password="gizli-parola").load()
    assert v.tokens == {"IP_1": "10.0.0.5", "EMAIL_1": "ali@x.com"}


def test_vault_ttl(tmp_path):
    import os

    p = tmp_path / "s.json"
    m = Masker()
    m.mask("10.0.0.5")
    VaultStore(p).save(m.vault)
    old = time.time() - 3 * 3600
    os.utime(p, (old, old))
    assert len(VaultStore(p, ttl_hours=24).load()) == 1
    assert len(VaultStore(p, ttl_hours=2).load()) == 0
    assert not p.exists()


def test_cli_encrypted_roundtrip(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MASKELE_HOME", str(tmp_path))
    monkeypatch.setenv("MASKELE_PASSWORD", "pw-123")
    src = tmp_path / "in.txt"
    src.write_text("hata 10.0.0.5", encoding="utf-8")
    assert main(["mask", str(src), "--encrypt", "-q"]) == 0
    assert capsys.readouterr().out.strip() == "hata [[IP_1]]"
    assert "10.0.0.5" not in (tmp_path / "sessions" / "default.json").read_text()
    rep = tmp_path / "r.txt"
    rep.write_text("[[IP_1]] kapalı", encoding="utf-8")
    assert main(["unmask", str(rep), "-q"]) == 0
    assert capsys.readouterr().out.strip() == "10.0.0.5 kapalı"
    monkeypatch.setenv("MASKELE_PASSWORD", "yanlış")
    assert main(["unmask", str(rep), "-q"]) == 1


# --- akış --------------------------------------------------------------------


def _split(rng, s, n):
    cuts = sorted(rng.sample(range(1, len(s)), min(n, len(s) - 1)))
    return [s[i:j] for i, j in zip([0] + cuts, cuts + [len(s)])]


def test_stream_unmasker_fuzz():
    m = Masker()
    m.mask(" ".join(f"10.0.0.{i}" for i in range(1, 13)) + " a@b.com")
    src = (
        "Hata [[IP_1]] ve IP_2 arasında; [[EMAIL_1]] bilgilendirildi. [ IP_12 ] tekrar, "
        "[[IP_11]]. XIP_1 değil, HTTP 500, IP_1x de değil. Sonunda IP_3"
    )
    expected = m.unmask(src).text
    rng = random.Random(0)
    for _ in range(2000):
        s = StreamUnmasker(m)
        got = "".join(s.feed(p) for p in _split(rng, src, rng.randint(1, 25))) + s.flush()
        assert got == expected


def test_stream_json_context_escapes():
    m = Masker()
    m.vault.token_for("SECRET", 'ab"c\\d')
    s = StreamUnmasker(m, json_context=True)
    parts = ['{"pw": "[[SEC', 'RET_1]]"}']
    out = "".join(s.feed(p) for p in parts) + s.flush()
    assert json.loads(out) == {"pw": 'ab"c\\d'}


def test_stream_releases_long_uppercase():
    m = Masker()
    m.mask("10.0.0.5")
    s = StreamUnmasker(m)
    out = s.feed("A" * 100)
    assert len(out) >= 30  # uzun büyük harf dizisi sonsuza dek tutulmaz


# --- raporlar ----------------------------------------------------------------


def test_scan_dir_json_sarif(tmp_path, capsys):
    (tmp_path / "a.log").write_text("ok\nuser ali@x.com from 10.0.0.5\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.env").write_text("API_KEY=sk-proj-abcdefghijklmnopqrstuvwx1234\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("ali@x.com", encoding="utf-8")
    (tmp_path / "bin.dat").write_bytes(b"\0\0ali@x.com")

    assert main(["scan", str(tmp_path), "-f", "json"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["count"] == 3
    assert {f["kind"] for f in rep["findings"]} == {"EMAIL", "IP", "API_KEY"}
    f = [x for x in rep["findings"] if x["kind"] == "EMAIL"][0]
    assert (f["line"], f["column"]) == (2, 6) and f["value"] is None and f["length"] == 9

    assert main(["scan", str(tmp_path), "-f", "sarif", "--fail"]) == 2
    out = capsys.readouterr().out
    sarif = json.loads(out)
    assert sarif["version"] == "2.1.0"
    assert len(sarif["runs"][0]["results"]) == 3
    assert "ali@x.com" not in out and "sk-proj-abcdefghijklmnopqrstuvwx1234" not in out


def test_kinds_cmd(capsys):
    assert main(["kinds"]) == 0
    assert "TCKN" in capsys.readouterr().out


# --- kod yapıştırırken yanlış pozitifler -------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "self.secret = secrets.token_urlsafe(24)",
        "api_key = os.environ['OPENAI_API_KEY']",
        "password: str",
        "token: Optional[str] = None",
        "--k-secret: #A61E37;",
        "DB_PASSWORD=${DB_PASSWORD}",
        'client_secret: "<your-client-secret>"',
        "authors = Temur",
        "password = [[SECRET_1]]",
        "api_key = your_api_key",
        "self.access_key = access_key",
    ],
)
def test_code_is_not_secret(line):
    assert masked(line) == line


@pytest.mark.parametrize(
    "line",
    [
        'PASSWORD: "Parola",',
        "secret: required",
        "parola: MASKELE_PASSWORD",
        'API_KEY: "API anahtarı",',
        '"PRIVATE_KEY": "PEM özel anahtar bloğu",',
    ],
)
def test_ambiguous_values_are_masked(line):
    """Belirsiz durumlarda maskele (v0.4): etiket gibi görünen değerler de gerçek bir
    parola olabilir. Fazla maskeleme, gerçek bir parolayı modele göndermekten iyidir."""
    assert "[[SECRET_1]]" in Masker().mask(line).text


@pytest.mark.parametrize(
    "line,val",
    [
        ('db_password: "S3cr3t!Pass"', "S3cr3t!Pass"),
        ("SECRET_KEY=django-insecure-8x$k2!m", "django-insecure-8x$k2!m"),
        ("token=abc123def456", "abc123def456"),
        ("parola: Gizli.2026", "Gizli.2026"),
    ],
)
def test_real_secrets_still_masked(line, val):
    out = masked(line)
    assert val not in out and "[[SECRET_1]]" in out


def test_scan_suppression_examples_exclude(tmp_path, capsys):
    (tmp_path / "a.py").write_text(
        "ADMIN = 'ali@firma.com'  # maskele:ignore\n"
        "DOC = 'ornek@example.com 192.0.2.10 2001:db8::1'\n"
        "REAL = 'veli@firma.com'\n",
        encoding="utf-8",
    )
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "fixtures" / "b.txt").write_text("x@firma.com", encoding="utf-8")
    assert main(["scan", str(tmp_path), "-f", "json", "-x", "fixtures"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert [(f["line"], f["kind"]) for f in rep["findings"]] == [(3, "EMAIL")]
    assert main(["scan", str(tmp_path / "a.py"), "-f", "json", "--include-examples"]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 4


def test_scan_ignores_svg_geometry_but_keeps_svg_text(tmp_path):
    """SVG yol koordinatları telefon/kart sanılmamalı; SVG içindeki gerçek metin yine taranmalı."""
    from maskele.report import geometry_blanked

    svg = (
        '<svg viewBox="0 0 533 987"><path d="M533 987 65 43 L4111 1111 1111 1111 '
        '5333 9876 5432" transform="translate(0 12)"/>'
        "<text>ali.veli@ornekfirma.com.tr</text></svg>"
    )
    out = geometry_blanked("logo.svg", svg)
    assert len(out) == len(svg)
    kinds = {m.kind for m in Masker().detect(out)}
    assert kinds == {"EMAIL"}
    assert geometry_blanked("notes.txt", svg) == svg


def test_parenthesized_code_expression_is_not_a_secret():
    """`const TOKEN = (document.querySelector(...) || {}).content` bir ifade, sır değil."""
    m = Masker()
    code = 'const TOKEN = (document.querySelector(\'meta[name="t"]\') || {}).content || "";'
    assert [x for x in m.detect(code) if x.kind == "SECRET"] == []
    assert m.mask("password = (Xk9#mP2v").text == "password = [[SECRET_1]]"
    assert Masker().mask("parola: (gizli123)").text == "parola: [[SECRET_1]]"


def test_name_echo_masks_lone_first_name_and_surname():
    """Tam adı maskelenen kişinin adı ya da soyadı tek başına geçtiğinde de sızmamalı."""
    m = Masker()
    t = "Kimden: Selin Aydın\nTeşekkürler, Selin. Murat Koç onayladı; Koç'a da yazın."
    out = m.mask(t).text
    assert "Selin" not in out and "Koç" not in out and "Aydın" not in out.replace("[[", "")
    assert out.startswith("Kimden: [[NAME_1]]")
    # Tek başına geçen ad, sahibinin token'ını alır: model ikisinin aynı kişi olduğunu görür
    assert "Teşekkürler, [[NAME_1]]." in out and "[[NAME_2]]'a da yazın." in out
    assert m.unmask("[[NAME_1]] onayladı").text == "Selin Aydın onayladı"


def test_name_echo_ambiguous_part_gets_own_token():
    m = Masker()
    out = m.mask("Ayşe Kaya ve Ayşe Demir geldi. Ayşe not bıraktı.").text
    assert out == "[[NAME_1]] ve [[NAME_2]] geldi. [[NAME_3]] not bıraktı."


def test_name_echo_uses_session_vault():
    """Aynı oturumda daha önce tam adı geçen kişinin sonraki mesajdaki tek adı da maskelenir."""
    m = Masker()
    m.mask("Talep sahibi: Selin Aydın")
    assert m.mask("Selin yarın tekrar yazacak.").text == "[[NAME_1]] yarın tekrar yazacak."


def test_name_echo_is_case_and_boundary_aware():
    m = Masker()
    out = m.mask("Selin Aydın · selinay@ornekfirma.com.tr · selin.aydin.yedek · Selinay geldi").text
    assert "[[EMAIL_1]]" in out and "Selinay geldi" in out and "selin.aydin.yedek" in out


def test_no_echo_without_a_detected_name():
    assert Masker().mask("Aydın şubesinden Selin geldi.").text == "Aydın şubesinden Selin geldi."
