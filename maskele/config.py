"""Yapılandırma: .maskele.toml (proje) ve ~/.config/maskele/config.toml (kullanıcı).

Proje dosyası, çalışma dizininden köke doğru aranır; bulunan ilk dosya kullanıcı
dosyasının üzerine yazılır (alan bazında birleşir).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .detectors import ALL_KINDS, DEFAULT_KINDS

KIND_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")

SAMPLE = """\
# maskele yapılandırması — https://github.com/temurcanbulut/maskele
# Bu dosya proje kökünde .maskele.toml olarak durabilir.

[detect]
# Varsayılan türlerden kapatmak istediklerin:
disable = []            # örn. ["PLATE", "NAME"]
# Varsayılanda kapalı olup açmak istediklerin:
enable = []             # örn. ["HOST"]
mask_localhost = false

[policy]
# Tür başına davranış: "mask" (varsayılan), "block" (istek/işlem reddedilir),
# "allow" (hiç dokunulmaz). Örneğin özel anahtarların modele hiç gitmemesi için:
# PRIVATE_KEY = "block"
# PLATE = "allow"

[allowlist]
# Bu değerler ASLA maskelenmez (birebir eşleşme, büyük/küçük harf duyarsız)
values = [
  # "destek@example.com",
]
# Bu regex'lerden birine tam uyan değerler maskelenmez
patterns = [
  # '^10\\.0\\.0\\.\\d+$',    # test ağı
]

[names]
# Sözlükte olmayan ilk adları ekle
extra_first_names = []

# Şirkete özel kimlikler
# [[patterns]]
# name = "CUSTOMER_ID"
# regex = 'CUS-\\d{6}'

# [[patterns]]
# name = "INTERNAL_TICKET"
# regex = 'ticket[:#](?P<v>\\d+)'
# group = "v"           # sadece bu grup maskelenir

[vault]
encrypt = false         # true ise parola MASKELE_PASSWORD'dan ya da istemden alınır
ttl_hours = 24          # bu süreden eski oturumlar her çalıştırmada silinir (0 = kapalı)

[proxy]
upstream = "https://api.openai.com"
port = 8787
hint = true             # modele "token'ları olduğu gibi koru" notu ekle
max_body_mb = 20        # daha büyük istekler 413 ile reddedilir
timeout_s = 300
"""


@dataclass
class CustomPattern:
    name: str
    regex: re.Pattern
    group: str | int = 0


@dataclass
class Config:
    kinds: list[str] = field(default_factory=lambda: list(DEFAULT_KINDS))
    mask_localhost: bool = False
    blocked: set[str] = field(default_factory=set)
    allowed_kinds: set[str] = field(default_factory=set)
    allow_values: set[str] = field(default_factory=set)
    allow_patterns: list[re.Pattern] = field(default_factory=list)
    extra_first_names: list[str] = field(default_factory=list)
    custom: list[CustomPattern] = field(default_factory=list)
    vault_encrypt: bool = False
    vault_ttl_hours: float = 24
    proxy_upstream: str = "https://api.openai.com"
    proxy_port: int = 8787
    proxy_hint: bool = True
    proxy_max_body_mb: float = 20
    proxy_timeout_s: float = 300
    proxy_media: str = "allow"  # allow | block: base64 görsel/dosya taranamaz
    source: list[Path] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)  # güvenilmeyen projeden yok sayılanlar
    untrusted: list[Path] = field(default_factory=list)

    def is_allowed(self, value: str) -> bool:
        if value.casefold() in self.allow_values:
            return True
        return any(p.fullmatch(value) for p in self.allow_patterns)

    @property
    def all_kinds(self) -> list[str]:
        return self.kinds + [
            c.name for c in self.custom if c.name not in self.kinds and c.name not in self.allowed_kinds
        ]


class ConfigError(ValueError):
    pass


def _apply(cfg: Config, data: dict, path: Path) -> None:
    det = data.get("detect", {})
    for k in det.get("disable", []):
        if k.upper() in cfg.kinds:
            cfg.kinds.remove(k.upper())
    for k in det.get("enable", []):
        if k.upper() not in ALL_KINDS:
            raise ConfigError(f"{path}: bilinmeyen tür {k!r}")
        if k.upper() not in cfg.kinds:
            cfg.kinds.append(k.upper())
    if "mask_localhost" in det:
        cfg.mask_localhost = bool(det["mask_localhost"])

    for kind, action in data.get("policy", {}).items():
        kind, action = kind.upper(), str(action).lower()
        if action not in ("mask", "block", "allow"):
            raise ConfigError(f"{path}: policy.{kind} = {action!r}; mask, block ya da allow olmalı")
        if (
            kind not in ALL_KINDS
            and kind not in {c.name for c in cfg.custom}
            and kind not in {str(p.get("name", "")).upper() for p in data.get("patterns", [])}
        ):
            raise ConfigError(f"{path}: policy içinde bilinmeyen tür {kind!r}")
        cfg.blocked.discard(kind)
        if action == "allow":
            if kind in cfg.kinds:
                cfg.kinds.remove(kind)
            cfg.allowed_kinds.add(kind)
        else:
            cfg.allowed_kinds.discard(kind)
            if kind in ALL_KINDS and kind not in cfg.kinds:
                cfg.kinds.append(kind)
            if action == "block":
                cfg.blocked.add(kind)

    allow = data.get("allowlist", {})
    cfg.allow_values |= {str(v).casefold() for v in allow.get("values", [])}
    for p in allow.get("patterns", []):
        try:
            cfg.allow_patterns.append(re.compile(p))
        except re.error as e:
            raise ConfigError(f"{path}: geçersiz allowlist regex {p!r}: {e}") from e

    cfg.extra_first_names += list(data.get("names", {}).get("extra_first_names", []))

    for i, p in enumerate(data.get("patterns", [])):
        name = str(p.get("name", "")).upper()
        if not KIND_RE.match(name) or name in ALL_KINDS:
            raise ConfigError(f"{path}: patterns[{i}].name geçersiz ya da yerleşik türle çakışıyor: {name!r}")
        try:
            rx = re.compile(p["regex"])
        except (KeyError, re.error) as e:
            raise ConfigError(f"{path}: patterns[{i}].regex geçersiz: {e}") from e
        group = p.get("group", 0)
        if isinstance(group, str) and group not in rx.groupindex:
            raise ConfigError(f"{path}: patterns[{i}] regex'inde {group!r} grubu yok")
        cfg.custom = [c for c in cfg.custom if c.name != name]
        cfg.custom.append(CustomPattern(name, rx, group))

    v = data.get("vault", {})
    cfg.vault_encrypt = bool(v.get("encrypt", cfg.vault_encrypt))
    cfg.vault_ttl_hours = float(v.get("ttl_hours", cfg.vault_ttl_hours))

    px = data.get("proxy", {})
    cfg.proxy_upstream = str(px.get("upstream", cfg.proxy_upstream)).rstrip("/")
    cfg.proxy_port = int(px.get("port", cfg.proxy_port))
    cfg.proxy_hint = bool(px.get("hint", cfg.proxy_hint))
    cfg.proxy_max_body_mb = float(px.get("max_body_mb", cfg.proxy_max_body_mb))
    cfg.proxy_timeout_s = float(px.get("timeout_s", cfg.proxy_timeout_s))
    media = str(px.get("media", cfg.proxy_media)).lower()
    if media not in ("allow", "block"):
        raise ConfigError(f"{path}: proxy.media = {media!r}; allow ya da block olmalı")
    cfg.proxy_media = media
    cfg.source.append(path)


def _strengthen_only(data: dict, cfg: Config, path: Path) -> tuple[dict, list[str]]:
    """Güvenilmeyen proje yapılandırmasından yalnızca korumayı ARTIRAN ayarları bırakır.

    Kalan: yeni türleri açmak, block/mask politikaları, özel desenler, ek adlar,
    localhost'u da maskelemek, kasayı şifrelemek, TTL'yi kısaltmak, medyayı engellemek.
    Atılan: tür kapatma, allow politikası, izin listesi, upstream ve diğer proxy ayarları,
    şifreyi kapatma, TTL'yi uzatma.
    """
    out: dict = {}
    ignored: list[str] = []
    det = dict(data.get("detect", {}))
    if det.pop("disable", None):
        ignored.append("detect.disable")
    if det.get("mask_localhost") is False:
        det.pop("mask_localhost")
        ignored.append("detect.mask_localhost = false")
    out["detect"] = det
    pol = {}
    for k, v in data.get("policy", {}).items():
        if str(v).lower() == "allow":
            ignored.append(f"policy.{k} = allow")
        else:
            pol[k] = v
    out["policy"] = pol
    if data.get("allowlist"):
        ignored.append("allowlist")
    for key in ("names", "patterns"):
        if key in data:
            out[key] = data[key]
    v = data.get("vault", {})
    vout = {}
    if v.get("encrypt") is True:
        vout["encrypt"] = True
    elif "encrypt" in v:
        ignored.append("vault.encrypt = false")
    if "ttl_hours" in v:
        if 0 < float(v["ttl_hours"]) <= (cfg.vault_ttl_hours or float("inf")):
            vout["ttl_hours"] = v["ttl_hours"]
        else:
            ignored.append("vault.ttl_hours (uzatma)")
    out["vault"] = vout
    px = data.get("proxy", {})
    pout = {}
    for k in px:
        if k == "media" and str(px[k]).lower() == "block":
            pout["media"] = "block"
        else:
            ignored.append(f"proxy.{k}")
    out["proxy"] = pout
    return out, ignored


# --- proje yapılandırmasına güven ---------------------------------------------


def _trust_file() -> Path:
    return user_config_path().parent / "trusted.json"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _trusted() -> dict[str, str]:
    try:
        return json.loads(_trust_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def is_trusted(path: Path) -> bool:
    path = path.resolve()
    return _trusted().get(str(path)) == _digest(path)


def set_trust(path: Path, trusted: bool) -> None:
    path = path.resolve()
    data = _trusted()
    if trusted:
        data[str(path)] = _digest(path)
    else:
        data.pop(str(path), None)
    f = _trust_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, f)


def user_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "maskele" / "config.toml"


def find_project_config(start: Path | None = None) -> Path | None:
    d = (start or Path.cwd()).resolve()
    for p in [d, *d.parents]:
        f = p / ".maskele.toml"
        if f.is_file():
            return f
    return None


def load_config(explicit: str | Path | None = None, use_files: bool = True) -> Config:
    """Yapılandırmayı yükler.

    Güvenilir kaynaklar: kullanıcının kendi dosyası (~/.config/maskele/config.toml) ve
    --config ile açıkça verilen dosya. Çalışma dizinindeki .maskele.toml ise, kullanıcı
    `maskele config trust` ile onaylayana kadar yalnızca korumayı sıkılaştırabilir. Onay,
    dosyanın içeriğine sabitlenir; dosya değişirse güven düşer.
    """
    cfg = Config()
    sources: list[tuple[Path, bool]] = []
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise ConfigError(f"Yapılandırma dosyası yok: {explicit}")
        sources = [(p, True)]
    elif use_files and not os.environ.get("MASKELE_NO_CONFIG"):
        if user_config_path().is_file():
            sources.append((user_config_path(), True))
        proj = find_project_config()
        if proj and proj.resolve() != user_config_path().resolve():
            sources.append((proj, is_trusted(proj)))
    for p, trusted in sources:
        try:
            data = tomllib.loads(p.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{p}: TOML hatası: {e}") from e
        if not trusted:
            data, ignored = _strengthen_only(data, cfg, p)
            cfg.ignored += ignored
            cfg.untrusted.append(p)
        _apply(cfg, data, p)
    return cfg
