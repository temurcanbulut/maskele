import os
import random

from maskele import Masker, Vault, detect
from maskele.cli import main
from maskele.detectors import valid_iban, valid_tckn, valid_vkn

# --- yardımcılar -------------------------------------------------------------


def make_tckn(rng: random.Random) -> str:
    d = [rng.randint(1, 9)] + [rng.randint(0, 9) for _ in range(8)]
    d10 = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    d.append(d10)
    d.append(sum(d) % 10)
    return "".join(map(str, d))


def make_vkn(rng: random.Random) -> str:
    while True:
        s = "".join(str(rng.randint(0, 9)) for _ in range(9))
        for last in "0123456789":
            if valid_vkn(s + last):
                return s + last


def kinds(text, **kw):
    return [(m.kind, m.value) for m in detect(text, **kw)]


# --- checksum'lar -----------------------------------------------------------


def test_tckn_checksum():
    assert valid_tckn("10000000146")
    assert not valid_tckn("10000000147")
    assert not valid_tckn("01234567890")
    rng = random.Random(1)
    for _ in range(200):
        assert valid_tckn(make_tckn(rng))


def test_iban_checksum():
    assert valid_iban("TR330006100519786457841326")
    assert valid_iban("TR33 0006 1005 1978 6457 8413 26")
    assert not valid_iban("TR330006100519786457841327")
    assert valid_iban("DE89370400440532013000")


def test_random_11_digits_rarely_pass():
    rng = random.Random(7)
    hits = sum(valid_tckn(str(rng.randint(10**10, 10**11 - 1))) for _ in range(10000))
    assert hits < 200  # ~%1


# --- dedektörler ------------------------------------------------------------


def test_turkish_types():
    t = "Müşteri TCKN 10000000146, IBAN TR33 0006 1005 1978 6457 8413 26, tel 0532 123 45 67, araç 34 ABC 123."
    got = kinds(t)
    assert ("TCKN", "10000000146") in got
    assert ("IBAN", "TR33 0006 1005 1978 6457 8413 26") in got
    assert ("PHONE", "0532 123 45 67") in got
    assert ("PLATE", "34 ABC 123") in got


def test_no_false_positives_in_logs():
    t = (
        "2026-10-15T14:02:11.482Z [svc v2.14.3] req=7f3e9a12-4b8c-4d1e-9f00-2a6b1c3d4e5f "
        "port 8080 latency 1532ms order_id 2026101500123 amount 15499.90 build 34A12"
    )
    assert kinds(t) == []


def test_plate_rules():
    for p in ["34 A 1234", "06 AB 123", "06 AB 1234", "35 ABC 12", "35 ABC 123", "34ABC123"]:
        assert [k for k, _ in kinds(f"plaka {p}")] == ["PLATE"], p
    for p in ["34 A 12", "34 ABC 1234", "99 AB 123", "34 QW 123"]:
        assert kinds(f"plaka {p}") == [], p


def test_bearer_keyword_not_secret():
    m = Masker().mask("Authorization: Bearer abcdefghijklmnop1234567890").text
    assert m == "Authorization: Bearer [[SECRET_1]]"


def test_phone_variants():
    for p in ["+90 532 123 45 67", "05321234567", "(532) 123-45-67", "+905321234567"]:
        assert [k for k, _ in kinds(f"ara: {p}")] == ["PHONE"], p


def test_vkn_needs_context():
    v = make_vkn(random.Random(3))
    assert ("VKN", v) in kinds(f"Vergi no: {v}")
    assert not any(k == "VKN" for k, _ in kinds(f"sipariş {v}"))


def test_invalid_tckn_not_masked():
    assert kinds("sipariş no 10000000147") == []


def test_ip_and_localhost():
    got = kinds("from 10.0.0.5 to 192.168.1.20 via 127.0.0.1 and 2001:db8::1")
    vals = [v for k, v in got if k == "IP"]
    assert vals == ["10.0.0.5", "192.168.1.20", "2001:db8::1"]
    assert "127.0.0.1" in [v for _, v in kinds("x 127.0.0.1", keep_localhost=False)]


def test_not_ip():
    assert kinds("version 999.1.2.3 and 1.2.3") == []
    assert kinds("time 12:30:45") == []


def test_email_and_mac():
    got = kinds("mail ali.veli+test@firma.com.tr mac AA:BB:CC:DD:EE:FF")
    assert ("EMAIL", "ali.veli+test@firma.com.tr") in got
    assert ("MAC", "AA:BB:CC:DD:EE:FF") in got


def test_card_luhn():
    assert ("CARD", "4111 1111 1111 1111") in kinds("kart 4111 1111 1111 1111")
    assert not any(k == "CARD" for k, _ in kinds("kart 4111 1111 1111 1112"))


def test_secrets():
    t = """
    OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz123456
    aws = AKIAIOSFODNN7EXAMPLE
    db_password: "S3cr3t!Pass"
    url = postgres://admin:hunter2pw@db.example.com:5432/app
    Authorization: Bearer abcdefghijklmnop1234567890
    token: ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    """
    got = kinds(t)
    vals = {v for _, v in got}
    assert "sk-proj-abcdefghijklmnopqrstuvwxyz123456" in vals
    assert "AKIAIOSFODNN7EXAMPLE" in vals
    assert "S3cr3t!Pass" in vals
    assert "hunter2pw" in vals
    assert "abcdefghijklmnop1234567890" in vals
    assert "ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in vals
    # anahtar adları maskelenmemeli
    m = Masker().mask(t).text
    assert "db_password" in m and "OPENAI_API_KEY" in m and "postgres://admin:" in m


def test_private_key_block():
    t = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\nabc\n-----END RSA PRIVATE KEY-----"
    assert [k for k, _ in kinds(t)] == ["PRIVATE_KEY"]


def test_jwt():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    assert ("JWT", jwt) in kinds(f"cookie={jwt}")


def test_hosts_optional():
    assert kinds("db01.prod.internal") == []
    assert ("HOST", "db01.prod.internal") in kinds("db01.prod.internal", kinds=["HOST"])


# --- maskeleme / geri dönüş -------------------------------------------------


def test_consistent_tokens():
    m = Masker()
    r = m.mask("10.0.0.5 failed, retry 10.0.0.5, then 10.0.0.6")
    assert r.text == "[[IP_1]] failed, retry [[IP_1]], then [[IP_2]]"


def test_normalized_consistency():
    m = Masker()
    r = m.mask("0532 123 45 67 / +905321234567 / Ali@Firma.com / ali@firma.com")
    assert r.text == "[[PHONE_1]] / [[PHONE_1]] / [[EMAIL_1]] / [[EMAIL_1]]"


def test_roundtrip():
    rng = random.Random(42)
    tckn = make_tckn(rng)
    src = (
        f"User {tckn} (mail: ayse@example.org) logged in from 172.16.4.9 "
        "with key sk-ant-api03-ZZZZZZZZZZZZZZZZZZZZZZZZ; IBAN TR330006100519786457841326"
    )
    m = Masker()
    masked = m.mask(src).text
    for secret in [tckn, "ayse@example.org", "172.16.4.9", "TR330006100519786457841326"]:
        assert secret not in masked
    assert m.unmask(masked).text == src


def test_unmask_tolerates_llm_mangling():
    m = Masker()
    m.mask("a 10.0.0.5 b 10.0.0.6 ... " + " ".join(f"10.0.1.{i}" for i in range(1, 12)))
    reply = "Sorun [IP_1] ile `IP_2` arasında. IP_11 de etkilenmiş. [[ IP_1 ]]"
    # standard: köşeli parantezli biçimler çevrilir, çıplaklar raporlanır
    r = m.unmask(reply)
    assert r.text == "Sorun 10.0.0.5 ile `IP_2` arasında. IP_11 de etkilenmiş. 10.0.0.5"
    assert r.bare == ["IP_11", "IP_2"]
    # loose: çıplaklar da çevrilir
    out = m.unmask(reply, mode="loose").text
    assert out == "Sorun 10.0.0.5 ile `10.0.0.6` arasında. 10.0.1.9 de etkilenmiş. 10.0.0.5"


def test_unmask_reports_unknown():
    m = Masker()
    m.mask("10.0.0.5")
    res = m.unmask("[[IP_1]] ve [[IP_7]] ve IP_9")
    assert res.text.startswith("10.0.0.5")
    assert res.unknown == ["IP_7", "IP_9"]


def test_strict_unmask():
    m = Masker()
    m.mask("10.0.0.5")
    assert m.unmask("IP_1 [[IP_1]]", strict=True).text == "IP_1 10.0.0.5"


def test_vault_persistence(tmp_path):
    p = tmp_path / "v.json"
    m = Masker(Vault())
    m.mask("10.0.0.5")
    m.vault.save(p)
    if os.name == "posix":
        assert oct(p.stat().st_mode)[-3:] == "600"
    m2 = Masker(Vault.load(p))
    assert m2.mask("x 10.0.0.5 y 10.0.0.9").text == "x [[IP_1]] y [[IP_2]]"


# --- CLI ---------------------------------------------------------------------


def test_cli_roundtrip(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MASKELE_HOME", str(tmp_path))
    src = tmp_path / "log.txt"
    src.write_text("err from 10.0.0.5 user ali@x.com\n", encoding="utf-8")
    assert main(["mask", str(src), "-s", "t1", "-q"]) == 0
    masked = capsys.readouterr().out
    assert "[[IP_1]]" in masked and "[[EMAIL_1]]" in masked
    reply = tmp_path / "reply.txt"
    reply.write_text("Check firewall for IP_1 and contact [[EMAIL_1]].", encoding="utf-8")
    assert main(["unmask", str(reply), "-s", "t1", "-q", "--loose"]) == 0
    assert capsys.readouterr().out.strip() == "Check firewall for 10.0.0.5 and contact ali@x.com."


def test_cli_bad_session(tmp_path, monkeypatch):
    monkeypatch.setenv("MASKELE_HOME", str(tmp_path))
    assert main(["show", "-s", "../etc"]) == 1


def test_cli_scan_fail(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("10.0.0.5", encoding="utf-8")
    assert main(["scan", str(f), "--fail"]) == 2
    assert "10.0.0.5" not in capsys.readouterr().out  # varsayılan olarak gizli
