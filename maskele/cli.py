"""maskele komut satırı arayüzü."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from . import __version__, clipboard
from .config import (
    SAMPLE,
    Config,
    ConfigError,
    find_project_config,
    is_trusted,
    load_config,
    set_trust,
    user_config_path,
)
from .core import Masker, summarize
from .detectors import ALL_KINDS, KIND_INFO
from .vault import VaultError, VaultStore, sessions_dir, sweep_expired, vault_path

# ---------------------------------------------------------------------------
# yardımcılar
# ---------------------------------------------------------------------------


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _c(s: str, code: str) -> str:
    return f"\033[{code}m{s}\033[0m" if sys.stderr.isatty() and not os.environ.get("NO_COLOR") else s


def _read_input(args) -> str:
    if getattr(args, "clip", False):
        return clipboard.paste()
    f = getattr(args, "file", None)
    if f and f != "-":
        return Path(f).read_text(encoding="utf-8")
    if sys.stdin.isatty():
        _err(_c("Metni yapıştır, bitince Ctrl+D (Windows: Ctrl+Z, Enter):", "2"))
    return sys.stdin.read()


def _write_output(args, text: str) -> None:
    if getattr(args, "clip", False):
        clipboard.copy(text)
        _err(_c("✓ Sonuç panoya kopyalandı.", "32"))
    elif getattr(args, "output", None):
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _config(args) -> Config:
    cfg = load_config(args.config, use_files=not args.no_config)
    if cfg.ignored and not getattr(args, "_warned", False):
        args._warned = True
        _err(
            _c(
                "⚠ Güvenilmeyen proje yapılandırmasındaki şu ayarlar yok sayıldı: "
                + ", ".join(cfg.ignored)
                + ". Uygulamak için: maskele config trust",
                "33",
            )
        )
    return cfg


def _kinds(args, cfg: Config) -> list[str]:
    kinds = list(cfg.all_kinds)
    if getattr(args, "only", None):
        kinds = [k.strip().upper() for k in args.only.split(",") if k.strip()]
    if getattr(args, "hosts", False) and "HOST" not in kinds:
        kinds.append("HOST")
    if getattr(args, "skip", None):
        skip = {k.strip().upper() for k in args.skip.split(",")}
        kinds = [k for k in kinds if k not in skip]
    known = set(ALL_KINDS) | {c.name for c in cfg.custom}
    bad = [k for k in kinds if k not in known]
    if bad:
        raise SystemExit(f"Bilinmeyen tür: {', '.join(bad)}. `maskele kinds` ile listeleyin.")
    return kinds


def _password(store: VaultStore, cfg: Config, args, creating: bool) -> str | None:
    want = store.is_encrypted() or cfg.vault_encrypt or getattr(args, "encrypt", False)
    if not want:
        return None
    pw = os.environ.get("MASKELE_PASSWORD")
    if pw:
        return pw
    try:
        pw = getpass.getpass("Kasa parolası: ")
        if creating and not store.exists():
            if getpass.getpass("Tekrar: ") != pw:
                raise SystemExit("Parolalar eşleşmiyor.")
    except (EOFError, OSError):
        raise SystemExit("Şifreli kasa için parola gerekli: MASKELE_PASSWORD ortam değişkenini ayarlayın.") from None
    if not pw:
        raise SystemExit("Boş parola kullanılamaz.")
    return pw


def _store(args, cfg: Config, creating: bool = False) -> VaultStore:
    path = vault_path(args.session)
    sweep_expired(cfg.vault_ttl_hours)
    store = VaultStore(path, ttl_hours=cfg.vault_ttl_hours)
    pw = _password(store, cfg, args, creating)
    if pw is not None:
        store.password, store.encrypt = pw, True
    return store


def _extra(args) -> dict[str, str]:
    return {v: "CUSTOM" for v in (getattr(args, "also", None) or []) if v.strip()}


def _masker(args, cfg: Config, store: VaultStore) -> Masker:
    keep_local = not (getattr(args, "mask_localhost", False) or cfg.mask_localhost)
    return Masker(store.load(), _kinds(args, cfg), keep_localhost=keep_local, config=cfg, extra_values=_extra(args))


# ---------------------------------------------------------------------------
# komutlar
# ---------------------------------------------------------------------------


def cmd_mask(args) -> int:
    cfg = _config(args)
    store = _store(args, cfg, creating=True)
    m = _masker(args, cfg, store)
    res = m.mask(_read_input(args))
    blocked = m.blocked_kinds & set(res.counts)
    if blocked:
        _err(
            _c(
                "✗ Politika gereği engellenen veri türü bulundu: " + ", ".join(sorted(blocked)) + ". Çıktı üretilmedi.",
                "31",
            )
        )
        return 3
    if res.matches:
        store.save(m.vault)
    _write_output(args, res.text)
    if not args.quiet:
        if res.matches:
            _err(_c(f"✓ {len(res.matches)} değer maskelendi ({summarize(res.counts)}) · oturum: {args.session}", "32"))
        else:
            _err(_c("Maskelenecek bir şey bulunamadı.", "33"))
    return 0


def cmd_unmask(args) -> int:
    cfg = _config(args)
    store = _store(args, cfg)
    if not store.exists():
        _err(f"'{args.session}' oturumu için kasa yok (süresi dolmuş olabilir). Önce `maskele mask` çalıştırın.")
        return 1
    m = Masker(store.load(), config=cfg)
    mode = "strict" if args.strict else "loose" if args.loose else "standard"
    res = m.unmask(_read_input(args), mode=mode)
    _write_output(args, res.text)
    if not args.quiet:
        _err(_c(f"✓ {res.restored} token geri çevrildi.", "32"))
        if res.unknown:
            _err(_c("⚠ Kasada olmayan token'lar (model uydurmuş olabilir): " + ", ".join(res.unknown), "33"))
        if res.bare:
            _err(
                _c(
                    "ℹ Köşeli parantezsiz geçtiği için çevrilmeyenler: "
                    + ", ".join(res.bare)
                    + ". Bunlar gerçekten token ise --loose ile çevirin.",
                    "33",
                )
            )
    return 0


def cmd_scan(args) -> int:
    from .detectors import detect
    from .report import geometry_blanked, iter_files, render_json, render_sarif, render_text, to_findings

    cfg = _config(args)
    kinds = _kinds(args, cfg)
    keep_local = not (args.mask_localhost or cfg.mask_localhost)
    findings = []
    if args.clip or not args.paths or args.paths == ["-"]:
        text = clipboard.paste() if args.clip else _read_input(argparse.Namespace(file=None))
        findings = to_findings("<stdin>", text, detect(text, kinds, keep_local, cfg), args.include_examples, args.all)
    else:
        for p in iter_files(args.paths, args.exclude or []):
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            scanned = geometry_blanked(str(p), text)
            findings += to_findings(
                str(p), text, detect(scanned, kinds, keep_local, cfg), args.include_examples, args.all
            )

    if args.format == "json":
        out = render_json(findings, args.reveal)
    elif args.format == "sarif":
        out = render_sarif(findings)
    else:
        out = render_text(findings, args.reveal)
    if args.output:
        Path(args.output).write_text(out + "\n", encoding="utf-8")
    else:
        print(out)
    return 2 if (args.fail and findings) else 0


def cmd_show(args) -> int:
    from .report import preview

    cfg = _config(args)
    store = _store(args, cfg)
    if not store.exists():
        print(f"'{args.session}' oturumu boş.")
        return 0
    v = store.load()
    if args.json:
        items = [{"token": t, "value": val if args.reveal else preview(val)} for t, val in v.tokens.items()]
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0
    if not v.tokens:
        print(f"'{args.session}' oturumu boş.")
    w = max((len(t) for t in v.tokens), default=0) + 4
    for tok, val in v.tokens.items():
        print(f"{'[[' + tok + ']]':<{w}}  {val if args.reveal else preview(val)}")
    return 0


def cmd_clear(args) -> int:
    if args.all:
        n = 0
        for p in sessions_dir().glob("*.json") if sessions_dir().exists() else []:
            VaultStore(p).delete()
            n += 1
        print(f"{n} oturum silindi.")
        return 0
    store = VaultStore(vault_path(args.session))
    if store.exists():
        store.delete()
        print(f"'{args.session}' oturumu silindi.")
    else:
        print(f"'{args.session}' oturumu zaten yok.")
    return 0


def cmd_sessions(args) -> int:
    import time

    files = sorted(sessions_dir().glob("*.json")) if sessions_dir().exists() else []
    if not files:
        print("Kayıtlı oturum yok.")
    for p in files:
        st = VaultStore(p)
        age = (time.time() - p.stat().st_mtime) / 3600
        lock = "şifreli" if st.is_encrypted() else "düz"
        size = "?" if st.is_encrypted() else str(len(st.load()))
        print(f"{p.stem:<24} {size:>5} değer   {lock:<7}  {age:5.1f} saat önce")
    return 0


def cmd_kinds(args) -> int:
    cfg = _config(args)
    for k in ALL_KINDS:
        state = "açık" if k in cfg.kinds else "kapalı"
        print(f"{k:<12} {state:<7} {KIND_INFO.get(k, '')}")
    for c in cfg.custom:
        print(f"{c.name:<12} {'açık':<7} Özel desen: {c.regex.pattern}")
    return 0


def cmd_config(args) -> int:
    if args.action == "init":
        target = user_config_path() if args.user else Path(".maskele.toml")
        if target.exists() and not args.force:
            _err(f"{target} zaten var (üzerine yazmak için --force).")
            return 1
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(SAMPLE, encoding="utf-8")
        print(f"Yazıldı: {target}")
        return 0
    if args.action in ("trust", "untrust"):
        proj = find_project_config()
        if not proj:
            _err("Bu dizinde ya da üstlerinde .maskele.toml yok.")
            return 1
        if args.action == "trust":
            print(proj.read_text(encoding="utf-8"))
            print(f"--- {proj}")
            print("Bu dosya artık korumayı zayıflatabilir (tür kapatma, izin listesi, upstream).")
        set_trust(proj, args.action == "trust")
        print(("Güvenildi" if args.action == "trust" else "Güven kaldırıldı") + f": {proj}")
        return 0
    cfg = _config(args)
    print("Okunan dosyalar:", ", ".join(map(str, cfg.source)) or "(yok, varsayılanlar)")
    proj = find_project_config()
    if proj:
        print(
            "Proje dosyası:  ",
            proj,
            "· güvenilir" if is_trusted(proj) else "· GÜVENİLMİYOR (yalnızca sıkılaştırabilir)",
        )
    if cfg.ignored:
        print("Yok sayılanlar: ", ", ".join(cfg.ignored), "→ `maskele config trust` ile uygulanır")
    print("Açık türler:   ", ", ".join(cfg.all_kinds))
    print("İzin listesi:  ", len(cfg.allow_values), "değer,", len(cfg.allow_patterns), "desen")
    print("Kasa:          ", "şifreli" if cfg.vault_encrypt else "düz", f"· TTL {cfg.vault_ttl_hours:g} saat")
    print("Proxy:         ", cfg.proxy_upstream, f"· port {cfg.proxy_port}")
    return 0


def _server_store(args, cfg):
    """Sunucular varsayılan olarak kasayı yalnızca bellekte tutar; --persist ile diske yazar."""
    if not getattr(args, "persist", False):
        sweep_expired(cfg.vault_ttl_hours)
        keep_local = not (getattr(args, "mask_localhost", False) or cfg.mask_localhost)
        return None, Masker(None, _kinds(args, cfg), keep_localhost=keep_local, config=cfg, extra_values=_extra(args))
    store = _store(args, cfg, creating=True)
    return store, _masker(args, cfg, store)


def cmd_proxy(args) -> int:
    from .proxy import PROVIDERS, serve

    cfg = _config(args)
    store, m = _server_store(args, cfg)
    upstream = args.upstream or (PROVIDERS[args.provider] if args.provider else cfg.proxy_upstream)
    key = None
    external = args.host not in ("127.0.0.1", "localhost", "::1")
    if args.access_key_env:
        key = os.environ.get(args.access_key_env)
        if not key:
            raise SystemExit(f"{args.access_key_env} ortam değişkeni boş.")
        if len(key) < 16:
            raise SystemExit("Erişim anahtarı en az 16 karakter olmalı (örn. openssl rand -hex 24).")
    elif external:
        raise SystemExit(
            "Proxy yerel makinenin dışına açılıyorsa erişim anahtarı zorunludur: --access-key-env DEGISKEN_ADI"
        )
    if bool(args.tls_cert) != bool(args.tls_key):
        raise SystemExit("--tls-cert ve --tls-key birlikte verilmeli.")
    if external and not args.tls_cert and not args.no_tls:
        raise SystemExit(
            "Proxy yerel makinenin dışına açılıyorsa TLS zorunludur: --tls-cert/--tls-key verin. "
            "TLS'i önünde bir ters proxy (Caddy, nginx) sonlandırıyorsa ya da port yalnızca "
            "127.0.0.1'e yayınlanıyorsa (Docker) --no-tls ile açıkça onaylayın."
        )
    serve(
        m,
        upstream,
        host=args.host,
        port=args.port or cfg.proxy_port,
        hint=cfg.proxy_hint and not args.no_hint,
        audit_path=args.audit_log,
        allowed_hosts=set(args.allow_host or []),
        quiet=args.quiet,
        access_key=key,
        max_body=int(cfg.proxy_max_body_mb * 1024 * 1024),
        timeout=args.timeout or cfg.proxy_timeout_s,
        unsafe_passthrough=args.unsafe_passthrough,
        forward_headers=set(args.forward_header or []),
        max_connections=args.max_connections,
        tls_cert=args.tls_cert,
        tls_key=args.tls_key,
    )
    return 0


def cmd_ui(args) -> int:
    from .ui import serve

    cfg = _config(args)
    store, m = _server_store(args, cfg)
    serve(
        m,
        args.session if store else f"{args.session} (bellek içi)",
        port=args.port,
        open_browser=not args.no_browser,
        save=(lambda: store.save(m.vault)) if store else None,
        clear=store.delete if store else None,
    )
    return 0


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="maskele",
        description="LLM'e göndermeden önce hassas veriyi maskele, cevabı geri çevir.",
        epilog="Örnek: maskele mask app.log | pbcopy    ·    maskele ui    ·    maskele proxy --provider openai",
    )
    p.add_argument("--version", action="version", version=f"maskele {__version__}")
    p.add_argument("--config", help="belirli bir yapılandırma dosyası kullan")
    p.add_argument("--no-config", action="store_true", help="yapılandırma dosyalarını okuma")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="KOMUT")

    def session(sp):
        sp.add_argument(
            "-s",
            "--session",
            default=os.environ.get("MASKELE_SESSION", "default"),
            help="oturum adı (varsayılan: default)",
        )

    def io(sp):
        sp.add_argument("file", nargs="?", help="girdi dosyası (yoksa stdin)")
        sp.add_argument("-c", "--clip", action="store_true", help="panodan oku, panoya yaz")
        sp.add_argument("-o", "--output", help="çıktı dosyası")
        sp.add_argument("-q", "--quiet", action="store_true", help="özet yazma")

    def detect_opts(sp):
        sp.add_argument("--only", help="sadece bu türler, virgülle (örn. IP,EMAIL,TCKN)")
        sp.add_argument("--skip", help="bu türleri atla, virgülle")
        sp.add_argument("--hosts", action="store_true", help="dahili host adlarını da maskele")
        sp.add_argument("--mask-localhost", action="store_true", help="127.0.0.1 / ::1'i de maskele")

    def also(sp):
        sp.add_argument(
            "-a",
            "--also",
            action="append",
            metavar="DEĞER",
            help='tespit edilmese de bu değeri maskele (tekrarlanabilir), örn. -a "Proje Kartal"',
        )

    def enc(sp):
        sp.add_argument(
            "--encrypt",
            action="store_true",
            help="kasayı AES-256-GCM ile şifrele (parola: MASKELE_PASSWORD ya da istem)",
        )

    sp = sub.add_parser("mask", help="metni maskele")
    session(sp)
    io(sp)
    detect_opts(sp)
    enc(sp)
    also(sp)
    sp.set_defaults(func=cmd_mask)

    sp = sub.add_parser("unmask", help="modelin cevabındaki token'ları geri çevir")
    session(sp)
    io(sp)
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--strict", action="store_true", help="yalnızca tam [[TOKEN]] biçimini çevir")
    g.add_argument(
        "--loose",
        action="store_true",
        help="köşeli parantezsiz IP_1 gibi çıplak token'ları da çevir (kodda değişken adlarını bozabilir)",
    )
    sp.set_defaults(func=cmd_unmask)

    sp = sub.add_parser("scan", help="dosya/klasörlerde hassas veri ara (kasaya yazmaz)")
    sp.add_argument("paths", nargs="*", help="dosya ya da klasörler (yoksa stdin)")
    sp.add_argument("-c", "--clip", action="store_true", help="panoyu tara")
    sp.add_argument("-f", "--format", choices=["text", "json", "sarif"], default="text")
    sp.add_argument("-o", "--output", help="raporu dosyaya yaz")
    sp.add_argument("--reveal", action="store_true", help="değerleri açık göster (SARIF'te hiçbir zaman)")
    sp.add_argument("--fail", action="store_true", help="bulgu varsa 2 ile çık (CI / pre-commit)")
    sp.add_argument(
        "-x",
        "--exclude",
        action="append",
        metavar="GLOB",
        help="bu desene uyan dosya/klasörleri atla (tekrarlanabilir)",
    )
    sp.add_argument(
        "--all",
        action="store_true",
        help="düşük güvenli bulguları da raporla (parola bağlamında etiket/tanımlayıcı gibi görünen değerler)",
    )
    sp.add_argument(
        "--include-examples", action="store_true", help="example.com, 192.0.2.x gibi belgeleme değerlerini de raporla"
    )
    detect_opts(sp)
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("show", help="oturumdaki eşlemeleri listele")
    session(sp)
    sp.add_argument("--reveal", action="store_true", help="değerleri açık göster")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("clear", help="oturum kasasını sil (üzerine yazarak, en iyi çaba)")
    session(sp)
    sp.add_argument("--all", action="store_true", help="tüm oturumları sil")
    sp.set_defaults(func=cmd_clear)

    sp = sub.add_parser("sessions", help="oturumları listele")
    sp.set_defaults(func=cmd_sessions)

    sp = sub.add_parser("kinds", help="desteklenen veri türlerini listele")
    sp.set_defaults(func=cmd_kinds)

    sp = sub.add_parser("config", help="yapılandırma dosyası oluştur / göster")
    sp.add_argument(
        "action",
        choices=["init", "show", "trust", "untrust"],
        help="trust: bu dizindeki .maskele.toml korumayı zayıflatabilsin (içeriğe sabitlenir)",
    )
    sp.add_argument("--user", action="store_true", help="init: kullanıcı dosyasına yaz (~/.config/maskele)")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_config)

    sp = sub.add_parser("proxy", help="OpenAI/Anthropic uyumlu yerel maskeleme proxy'si")
    sp.add_argument("-s", "--session", default="proxy", help="oturum adı (varsayılan: proxy)")
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--provider", choices=["openai", "anthropic", "openrouter", "groq", "mistral", "deepseek", "ollama"])
    g.add_argument("--upstream", help="hedef API adresi (örn. https://api.openai.com)")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("-p", "--port", type=int, default=0, help="varsayılan: 8787")
    sp.add_argument("--no-hint", action="store_true", help="modele token koruma notu ekleme")
    sp.add_argument("--audit-log", help="istek başına JSONL denetim kaydı (değer içermez)")
    sp.add_argument("--allow-host", action="append", help="ek izinli Host başlığı (Docker vb.)")
    sp.add_argument(
        "--access-key-env",
        metavar="DEGISKEN",
        help="istemcilerin X-Maskele-Key başlığında göndermesi gereken anahtarın ortam değişkeni",
    )
    sp.add_argument(
        "--forward-header",
        action="append",
        metavar="AD",
        help="upstream'e iletilecek ek istek başlığı (varsayılan: yalnızca kimlik ve sürüm başlıkları)",
    )
    sp.add_argument("--timeout", type=float, default=0, help="upstream zaman aşımı, saniye (varsayılan 300)")
    sp.add_argument(
        "--unsafe-passthrough", action="store_true", help="JSON olmayan gövdeleri MASKELEMEDEN ilet (önerilmez)"
    )
    sp.add_argument("--tls-cert", metavar="PEM", help="TLS sertifikası (zincir dahil)")
    sp.add_argument("--tls-key", metavar="PEM", help="TLS özel anahtarı")
    sp.add_argument(
        "--no-tls",
        action="store_true",
        help="dış adrese TLS'siz bağlan; yalnızca TLS'i önündeki ters proxy sonlandırıyorsa",
    )
    sp.add_argument("--max-connections", type=int, default=128, help="eşzamanlı açık bağlantı sınırı")
    sp.add_argument("-q", "--quiet", action="store_true")
    detect_opts(sp)
    also(sp)
    sp.set_defaults(func=cmd_proxy, persist=False)

    sp = sub.add_parser("ui", help="tarayıcıda yerel arayüzü aç")
    session(sp)
    sp.add_argument("-p", "--port", type=int, default=8788)
    sp.add_argument("--no-browser", action="store_true", help="tarayıcıyı otomatik açma")
    sp.add_argument(
        "--persist",
        action="store_true",
        help="kasayı diske yaz; CLI ile aynı oturumu paylaşmak için (varsayılan: yalnızca bellek)",
    )
    detect_opts(sp)
    enc(sp)
    sp.set_defaults(func=cmd_ui)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (clipboard.ClipboardError, ConfigError, VaultError, ValueError, FileNotFoundError) as e:
        _err(_c(f"Hata: {e}", "31"))
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
