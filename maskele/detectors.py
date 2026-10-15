"""Hassas veri dedektörleri.

Her dedektör metinde aday eşleşmeleri bulur, gerekiyorsa checksum ile doğrular
ve (başlangıç, bitiş, tür, değer) döndürür. Checksum doğrulaması yanlış pozitifleri
ciddi şekilde azaltır: rastgele 11 haneli bir sayının geçerli TCKN olma ihtimali ~%1.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    kind: str
    value: str
    priority: int = 0
    # "low": parola bağlamında ama değer etiket/tanımlayıcı gibi de görünüyor. Maskelemede
    # yine maskelenir (gizlilik önce); `scan` varsayılan olarak raporlamaz (--all ile gelir).
    confidence: str = "high"


# ---------------------------------------------------------------------------
# Checksum doğrulayıcılar
# ---------------------------------------------------------------------------


def valid_tckn(s: str) -> bool:
    """T.C. Kimlik No: 11 hane, ilk hane 0 değil, 10. ve 11. hane checksum."""
    if len(s) != 11 or not s.isdigit() or s[0] == "0":
        return False
    d = [int(c) for c in s]
    odd = d[0] + d[2] + d[4] + d[6] + d[8]
    even = d[1] + d[3] + d[5] + d[7]
    if (odd * 7 - even) % 10 != d[9]:
        return False
    return sum(d[:10]) % 10 == d[10]


def valid_vkn(s: str) -> bool:
    """Vergi Kimlik No: 10 hane, GİB algoritması."""
    if len(s) != 10 or not s.isdigit():
        return False
    total = 0
    for i in range(9):
        t = (int(s[i]) + (9 - i)) % 10
        t2 = (t * (2 ** (9 - i))) % 9
        if t != 0 and t2 == 0:
            t2 = 9
        total += t2
    return (10 - total % 10) % 10 == int(s[9])


def valid_iban(s: str) -> bool:
    """ISO 13616 mod-97 kontrolü (tüm ülkeler)."""
    s = s.replace(" ", "").upper()
    if not (15 <= len(s) <= 34) or not s[:2].isalpha() or not s[2:4].isdigit():
        return False
    if s.startswith("TR") and len(s) != 26:
        return False
    rearranged = s[4:] + s[:4]
    try:
        num = "".join(str(int(c, 36)) for c in rearranged)
    except ValueError:
        return False
    return int(num) % 97 == 1


def valid_luhn(s: str) -> bool:
    digits = [int(c) for c in s if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _card_prefix_ok(s: str) -> bool:
    d = "".join(c for c in s if c.isdigit())
    return bool(re.match(r"^(4|5[1-5]|2[2-7]|3[47]|6(011|5|4[4-9])|9792)", d))


# ---------------------------------------------------------------------------
# Regex tabanlı dedektörler
# ---------------------------------------------------------------------------

_D = r"(?<![\w.])"  # sol sınır: harf/rakam/nokta değil
_E = r"(?![\w])"  # sağ sınır

RE_EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?![\w-])")
RE_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w]|\.\d)")
RE_IPV6 = re.compile(r"(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])")
RE_MAC = re.compile(r"(?<![\w:-])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![\w:-])")
RE_TCKN = re.compile(_D + r"[1-9]\d{10}" + _E)
RE_VKN = re.compile(_D + r"\d{10}" + _E)
RE_IBAN = re.compile(r"(?<![\w])[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?(?![\w])")
RE_PHONE_TR = re.compile(r"(?<![\w+])(?:\+90|0090|0)?[ (-]*5\d{2}[ )-]*\d{3}[ -]*\d{2}[ -]*\d{2}(?![\w])")
RE_PLATE_TR = re.compile(r"(?<![\w:.-])(0[1-9]|[1-7]\d|8[01]) ?([A-PR-VYZ]{1,3}) ?(\d{2,5})(?![\w:-]|\.\w)")


def _plate_ok(v: str) -> bool:
    """Harf/rakam sayısı kuralı: 1 harf→4-5 rakam, 2 harf→3-4, 3 harf→2-3."""
    m = RE_PLATE_TR.fullmatch(v)
    if not m:
        return False
    lo, hi = {1: (4, 5), 2: (3, 4), 3: (2, 3)}[len(m.group(2))]
    return lo <= len(m.group(3)) <= hi


RE_CARD = re.compile(r"(?<![\w])(?:\d[ -]?){12,18}\d(?![\w])")

# Secret'lar — sağlayıcıya özel desenler
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "PRIVATE_KEY",
        re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----[\s\S]+?-----END (?:[A-Z ]+ )?PRIVATE KEY-----"),
    ),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("API_KEY", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),  # Anthropic
    ("API_KEY", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}")),  # OpenAI
    ("API_KEY", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),  # AWS access key
    ("API_KEY", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),  # GitHub
    ("API_KEY", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("API_KEY", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),  # GitLab
    ("API_KEY", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),  # Slack
    ("API_KEY", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),  # Google
    ("API_KEY", re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}\b")),  # Stripe
    ("API_KEY", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),  # HuggingFace
    ("API_KEY", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
]

# key=value / key: value biçimindeki secret'lar — sadece DEĞER maskelenir.
# Tırnaklı değer kapanış tırnağına kadar alınır (virgül, boşluk, noktalı virgül içerebilir);
# tırnaksız değer ilk ayırıcıda biter.
RE_KV_SECRET = re.compile(
    r"""(?ix)
    (?P<key>\b[\w.-]*(?:password|passwd|pwd|passphrase|parola|sifre|şifre|secret|token|api[_-]?key|
        apikey|access[_-]?key|private[_-]?key|client[_-]?secret|credential|auth(?!or))[\w.-]*)
    (?P<sep>\s*["']?\s*[:=]\s*)
    (?:
        (?P<q>["'])(?P<qval>(?:\\.|(?!(?P=q))[^\n]){1,256}?)(?P=q)
      | (?P<val>(?:\$\{[^}\s]{0,64}\}|[^\s"'{}]){1,256})
    )
    """
)

# Parola bağlamında (password=, api_key:, şifre:) değer HER ZAMAN maskelenir; tahmin yok.
# Tek istisna, sözdizimsel olarak kesin kod olan değerler: değeri modele göndermek bir sır
# sızdırmaz, maskelemek ise yapıştırılan kodu bozar. Belirsiz her şey maskelenir.
_KV_CODE = re.compile(
    r"""(?x)^(?:
      [A-Za-z_][\w]*(?:\.[\w]+)*[(\[].*            # çağrı / indeks: os.environ[ , secrets.token_hex(
    | (?:self|this|os|env|process|config|settings|cfg|args|opts|options|req|request|ctx|params|
         props|window|document|vault|store|data|kwargs|cls)\.[\w.]+  # nitelik erişimi
    | (?:str|bytes|int|bool|dict|list|Optional|Union|Any|string|number|boolean|SecretStr|
         SecretBytes)(?:\[.*\])?(?:\s*(?:=|\|).*)?     # tip ipucu: password: str = Field(...)
    | \#[0-9A-Fa-f]{3,8};?                          # CSS renk: --k-secret: #A61E37;
    | \$\{[\w.:-]+\}|\$(?-i:[A-Z_][A-Z0-9_]*)       # ${VAR}, $VAR (kabuk değişkenleri büyük harf)
    | \{\{.*\}\} | <[\w ._-]+> | %\(\w+\)s | %s     # şablon yer tutucuları
    | null|none|nil|true|false|undefined|bearer|basic
    | .*\[\[[A-Z_0-9]+\]\].*                        # zaten maskelenmiş
)$""",
    re.IGNORECASE,
)


def _kv_value_ok(v: str, quoted: bool = False, code_assign: bool = False) -> bool:
    """Değer secret olarak maskelenmeli mi? Kesin kod değilse evet."""
    v = v.strip()
    if not v or _KV_CODE.match(v):
        return False
    # Python/JS atamasında tırnaksız snake_case tanımlayıcı başka bir değişkendir:
    # "self.access_key = access_key". "password=letmein" (boşluksuz) yine maskelenir.
    if not quoted and code_assign and re.fullmatch(r"[a-z_][a-z0-9_]*", v) and "_" in v:
        return False
    # Parantezli ifade: "TOKEN = (document.querySelector(…) || {}).content"
    if not quoted and code_assign and re.match(r"\(\s*[A-Za-z_$][\w$]*(?:\.[\w$]+)+\s*[(\[]", v):
        return False
    return True


def _kv_confidence(v: str) -> str:
    """Değer gerçek bir sır mı, yoksa etiket/tanımlayıcı mı? Yalnızca raporlama için."""
    v = v.strip()
    if len(v) < 4:
        return "low"
    if re.fullmatch(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+", v):  # MASKELE_PASSWORD
        return "low"
    if re.fullmatch(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", v) and not re.search(r"[a-zçğıöşü][A-ZÇĞİÖŞÜ]", v):
        return "low"  # "Parola", "required"
    if " " in v and v[:1].isupper() and not re.search(r"\d", v):  # "API anahtarı"
        return "low"
    if re.fullmatch(r"[A-Za-z_][A-Za-z_]*", v) and "_" in v:  # tanımlayıcı
        return "low"
    if v.startswith(("/", "$")) or v.endswith("…)"):
        return "low"
    return "high"


def _kv_detect(text: str) -> Iterator[Match]:
    for m in RE_KV_SECRET.finditer(text):
        g = "qval" if m.group("qval") is not None else "val"
        v = m.group(g)
        start, end = m.start(g), m.end(g)
        if "[[" in v:
            continue  # zaten maskelenmiş
        rest = text[end : end + 200].split("\n", 1)[0].strip()
        if g == "val" and rest:
            # Tırnaksız değer boşluğa kadar sürer (parolalarda , ; olabilir). Arkasında başka
            # içerik varsa sondaki ayırıcılar kodun parçasıdır: {password: abc, user: x} → "abc".
            # Satırın son değeriyse dokunulmaz: "parola: Kış;Gün;" tamamen maskelenir.  # maskele:ignore
            stripped = v.rstrip(",;)]")
            end -= len(v) - len(stripped)
            v = stripped
        if v.lower().startswith(("bearer ", "basic ")):
            continue  # RE_BEARER halleder
        if _kv_value_ok(v, quoted=g == "qval", code_assign=" = " in m.group("sep")):
            yield Match(start, end, "SECRET", v, 90, _kv_confidence(v))


# scheme://user:pass@host — sadece parola maskelenir  # maskele:ignore
RE_CONN_PASS = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s:/@]+:(?P<pw>[^\s@/]+)@")

# Bearer token
RE_BEARER = re.compile(r"(?i)\bBearer\s+(?P<tok>[A-Za-z0-9._~+/=-]{16,})")

# VKN sadece yakınında bağlam kelimesi varsa (10 haneli rastgele sayıların ~%10'u checksum'dan geçer)
VKN_CONTEXT = re.compile(r"(?i)(vergi|vkn|v\.k\.n|tax\s*id|tax\s*no)")

# Türkiye adresi: [Mahalle] + Cadde/Sokak/Bulvar + kapı numarası (+ daire/kat, posta kodu, ilçe/il).
# Kapı numarası şart: "Ali Rıza Caddesi" tek başına yer adıdır, "Ali Rıza Cad. No: 5" adrestir.  # maskele:ignore
_AW = r"(?:[A-ZÇĞİÖŞÜ0-9][\wçğıöşüÇĞİÖŞÜ'.-]*)"
_ADDR_MAH = rf"(?:{_AW}(?:[ \t]+{_AW}){{0,3}}[ \t]+(?:Mahallesi|Mah\.?|Mh\.?)[ \t]*,?[ \t]*)"
_ADDR_STREET = (
    rf"{_AW}(?:[ \t]+{_AW}){{0,3}}[ \t]+"
    r"(?:Caddesi|Cadde|Cad\.?|Cd\.?|Sokağı|Sokak|Sok\.?|Sk\.?|Bulvarı|Bulv\.?|Blv\.?|Yolu)"
)
_ADDR_NO = r"[ \t]*,?[ \t]*(?:No|NO|no)[ \t]*[:.]?[ \t]*\d+[A-Za-z]?(?:[ \t]*/[ \t]*\d+[A-Za-z]?)?"
_ADDR_UNIT = r"(?:[ \t]*,?[ \t]*(?:D(?:aire)?|Kat|Blok|Bl\.?|İç[ \t]*Kapı)[ \t]*[:.]?[ \t]*[\w]+){0,3}"
_ADDR_TAIL = (
    r"(?:[ \t]*,?[ \t]*\d{5})?"
    r"(?:[ \t]*,?[ \t]*[A-ZÇĞİÖŞÜ][a-zçğıöşü]+(?:[ \t]*/[ \t]*[A-ZÇĞİÖŞÜ][a-zçğıöşü]+|[ \t]+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+)?)?"
)
RE_ADDRESS = re.compile(rf"(?<![\w]){_ADDR_MAH}?{_ADDR_STREET}{_ADDR_NO}{_ADDR_UNIT}{_ADDR_TAIL}")

# Dahili host adları (opsiyonel, --hosts ile)
RE_HOST = re.compile(
    r"(?<![\w.@-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:local|internal|intra|corp|lan|home|svc|cluster\.local)(?![\w.-])",
    re.I,
)


# ---------------------------------------------------------------------------


def _iter_regex(
    rx: re.Pattern, text: str, kind: str, prio: int, check: Callable[[str], bool] | None = None, group: str | int = 0
) -> Iterator[Match]:
    for m in rx.finditer(text):
        val = m.group(group)
        if val is None:
            continue
        if check and not check(val):
            continue
        yield Match(m.start(group), m.end(group), kind, val, prio)


_VERSION_CTX = re.compile(r"(?i)(?:\bv|version|ver\.?|sürüm|versiyon|release|build)\s*[:=]?\s*$")


def _ip_ok(keep_local: bool) -> Callable[[str], bool]:
    def check(v: str) -> bool:
        try:
            ip = ipaddress.ip_address(v)
        except ValueError:
            return False
        if keep_local and (ip.is_loopback or ip.is_unspecified):
            return False
        return True

    return check


def _phone_ok(v: str) -> bool:
    digits = re.sub(r"\D", "", v)
    if digits.startswith("0090"):
        digits = digits[4:]
    elif digits.startswith("90") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = digits[1:]
    return len(digits) == 10 and digits[0] == "5"


def _vkn_detect(text: str) -> Iterator[Match]:
    for m in RE_VKN.finditer(text):
        v = m.group(0)
        if not valid_vkn(v):
            continue
        window = text[max(0, m.start() - 40) : m.start()]
        if VKN_CONTEXT.search(window):
            yield Match(m.start(), m.end(), "VKN", v, 60)


ALL_KINDS = [
    "PRIVATE_KEY",
    "JWT",
    "API_KEY",
    "SECRET",
    "PASSWORD",
    "EMAIL",
    "IBAN",
    "CARD",
    "TCKN",
    "VKN",
    "PHONE",
    "PLATE",
    "IP",
    "MAC",
    "ADDRESS",
    "NAME",
    "HOST",
]
DEFAULT_KINDS = [k for k in ALL_KINDS if k != "HOST"]

KIND_INFO = {
    "PRIVATE_KEY": "PEM özel anahtar bloğu",
    "JWT": "JSON Web Token",
    "API_KEY": "Sağlayıcı API anahtarı (OpenAI, Anthropic, AWS, GitHub…)",
    "SECRET": "password=/token:/Bearer değeri",  # maskele:ignore
    "PASSWORD": "Bağlantı dizesindeki parola",
    "EMAIL": "E-posta adresi",
    "IBAN": "IBAN (mod-97 doğrulamalı)",
    "CARD": "Kart numarası (Luhn doğrulamalı)",
    "TCKN": "T.C. Kimlik No (checksum doğrulamalı)",
    "VKN": "Vergi Kimlik No (bağlam + checksum)",
    "PHONE": "Türkiye mobil numarası",
    "PLATE": "Türkiye araç plakası",
    "IP": "IPv4 / IPv6 adresi",
    "MAC": "MAC adresi",
    "NAME": "Türkçe ad-soyad",
    "ADDRESS": "Türkiye adresi (sokak/cadde + kapı no)",
    "HOST": "Dahili host adı (*.internal, *.corp…)",
}


def detect(text: str, kinds: Iterable[str] | None = None, keep_localhost: bool = True, config=None) -> list[Match]:
    """Metindeki tüm hassas değerleri bulur, çakışmaları çözer, sıralı döndürür.

    `config` verilirse özel desenler, izin listesi ve ek isimler uygulanır.
    """
    if kinds:
        enabled = set(kinds)
    elif config is not None:
        enabled = set(config.all_kinds)
    else:
        enabled = set(DEFAULT_KINDS)
    found: list[Match] = []

    def on(k: str) -> bool:
        return k in enabled

    if config is not None:
        for cp in config.custom:
            if on(cp.name):
                found += _iter_regex(cp.regex, text, cp.name, 97, group=cp.group)
    if on("NAME"):
        from .names import find_names

        extra = config.extra_first_names if config is not None else ()
        found += (Match(s, e, "NAME", v, 35) for s, e, v in find_names(text, extra))

    # Öncelik: yüksek sayı = çakışmada kazanır
    for kind, rx in SECRET_PATTERNS:
        if on(kind):
            found += _iter_regex(rx, text, kind, 100)
    if on("PASSWORD"):
        found += _iter_regex(RE_CONN_PASS, text, "PASSWORD", 95, _kv_value_ok, group="pw")
    if on("SECRET"):
        found += _iter_regex(RE_BEARER, text, "SECRET", 92, group="tok")
        found += _kv_detect(text)
    if on("EMAIL"):
        found += _iter_regex(RE_EMAIL, text, "EMAIL", 80)
    if on("IBAN"):
        found += _iter_regex(RE_IBAN, text, "IBAN", 75, valid_iban)
    if on("CARD"):
        found += _iter_regex(RE_CARD, text, "CARD", 70, lambda v: valid_luhn(v) and _card_prefix_ok(v))
    if on("TCKN"):
        found += _iter_regex(RE_TCKN, text, "TCKN", 65, valid_tckn)
    if on("VKN"):
        found += _vkn_detect(text)
    if on("ADDRESS"):
        found += _iter_regex(RE_ADDRESS, text, "ADDRESS", 58)
    if on("PHONE"):
        found += _iter_regex(RE_PHONE_TR, text, "PHONE", 55, _phone_ok)
    if on("MAC"):
        found += _iter_regex(RE_MAC, text, "MAC", 50)
    if on("IP"):
        found += (
            mt
            for mt in _iter_regex(RE_IPV4, text, "IP", 45, _ip_ok(keep_localhost))
            if not _VERSION_CTX.search(text, max(0, mt.start - 16), mt.start)
        )
        found += _iter_regex(RE_IPV6, text, "IP", 44, lambda v: v.count(":") >= 2 and _ip_ok(keep_localhost)(v))
    if on("PLATE"):
        found += _iter_regex(RE_PLATE_TR, text, "PLATE", 40, _plate_ok)
    if on("HOST"):
        found += _iter_regex(RE_HOST, text, "HOST", 30)

    if config is not None:
        found = [m for m in found if not config.is_allowed(m.value)]
    return _resolve([m for m in found if m.end > m.start])


def _resolve(matches: list[Match]) -> list[Match]:
    """Çakışan eşleşmelerde önceliği yüksek, sonra uzun olanı tutar."""
    matches.sort(key=lambda m: (-m.priority, -(m.end - m.start), m.start))
    taken: list[Match] = []
    for m in matches:
        if any(m.start < t.end and t.start < m.end for t in taken):
            continue
        taken.append(m)
    taken.sort(key=lambda m: m.start)
    return taken
