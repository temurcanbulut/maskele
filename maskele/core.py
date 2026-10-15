"""Maskeleme motoru: tutarlı takma adlar, geri dönüş, akış (streaming) desteği.

Geri çevirme modları
--------------------
strict    Yalnızca `[[TOKEN]]` (içinde boşluk olabilir). Proxy bunu kullanır.
standard  + tek köşeli `[TOKEN]`. Çıplak `TOKEN` çevrilmez, uyarı olarak raporlanır.
          CLI ve arayüzün varsayılanı.
loose     + çıplak `TOKEN`. Model köşeli parantezleri attıysa elle açılır. Kodda
          `IP_1` adlı bir değişken varsa onu da çevirir; bu yüzden varsayılan değil.

`allowed` verilirse yalnızca o kümedeki token'lar çevrilir. Proxy, bir isteğin
cevabını yalnızca o istekte modele giden token'larla sınırlar; böylece bir isteğin
değeri başka bir isteğin cevabında açığa çıkamaz.
"""

from __future__ import annotations

import ipaddress
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .detectors import Match, _resolve, detect
from .names import _TITLES, fold, tr_lower
from .vault import Vault, default_home, vault_path  # noqa: F401  (geri uyumluluk)

_TOK = r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*?_\d+"
TOKEN_RE = re.compile(r"\[\[\s*(" + _TOK + r")\s*\]\]")
TOKEN_ANY = re.compile(r"(?<![\w])(" + _TOK + r")(?![\w])")
MODES = ("strict", "standard", "loose")

HINT = (
    "Some values in this conversation were replaced with placeholders such as "
    "[[IP_1]] or [[EMAIL_2]] for privacy. Treat each placeholder as an opaque value. "
    "When you refer to one, copy it exactly as written, including the double square "
    "brackets, also inside code, JSON and tool arguments. Do not invent new placeholders "
    "or try to guess the original values."
)


def normalize(kind: str, value: str) -> str:
    """Aynı değerin farklı yazımlarını tek anahtara indirger (tutarlılık için)."""
    v = value.strip()
    if kind in ("EMAIL", "HOST"):
        return v.lower()
    if kind in ("IBAN", "PLATE"):
        return re.sub(r"\s", "", v).upper()
    if kind in ("CARD", "TCKN", "VKN"):
        return re.sub(r"\D", "", v)
    if kind == "PHONE":
        return re.sub(r"\D", "", v)[-10:]
    if kind == "MAC":
        return v.lower().replace("-", ":")
    if kind == "NAME":
        return " ".join(tr_lower(v).split())
    if kind == "IP":
        try:
            return ipaddress.ip_address(v).compressed
        except ValueError:
            return v
    return v


def json_escape(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)[1:-1]


def tokens_in(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text))


@dataclass
class MaskResult:
    text: str
    matches: list[Match]
    replacements: list[tuple[Match, str]]

    @property
    def counts(self) -> Counter:
        return Counter(m.kind for m in self.matches)


@dataclass
class UnmaskResult:
    text: str
    restored: int
    unknown: list[str]  # kasada olmayan / bu istekte görülmeyen
    bare: list[str] = field(default_factory=list)  # köşeli parantezsiz geçen, çevrilmeyen


# --- JSON şema politikası ----------------------------------------------------
# Bu anahtarların DEĞERLERİ protokol tanımlayıcısıdır; değiştirilirse API bozulur.
# Liste bilerek dar tutuldu: `user`, `name`, `metadata`, `url` gibi alanlar maskelenir.
STRUCTURAL_KEYS = frozenset(
    {
        "model",
        "role",
        "type",
        "object",
        "id",
        "tool_call_id",
        "tool_use_id",
        "call_id",
        "item_id",
        "response_id",
        "previous_response_id",
        "finish_reason",
        "stop_reason",
        "stop_sequence",
        "media_type",
        "mime_type",
        "detail",
        "format",
        "encoding_format",
        "service_tier",
        "reasoning_effort",
        "voice",
        "truncation",
        "signature",
        "redacted_thinking",
        "cache_control",
        "anthropic_version",
        "tool_choice",
        "parallel_tool_calls",
        "modalities",
        "include",
    }
)
# Bu anahtarların altındaki sözlük ANAHTARLARI JSON Schema özellik adlarıdır
SCHEMA_CONTAINERS = frozenset({"properties", "patternProperties", "$defs", "definitions"})
_B64 = re.compile(r"[A-Za-z0-9+/=_-]{200,}\Z")

# Taranamayan medya: içeriği metin değil (görsel, ses, dosya). Base64 olarak gömülü ya da
# URL/dosya kimliğiyle referans verilmiş olabilir; ikisi de "taranmadı" sayılır.
MEDIA_TYPES = frozenset(
    {
        "image_url",
        "input_image",
        "image",
        "input_file",
        "file",
        "input_audio",
        "audio",
        "video",
        "video_url",
        "document",
        "file_url",
    }
)
MEDIA_KEYS = frozenset({"image_url", "input_audio", "file_id", "file_url", "file_data", "audio_url", "video_url"})


def _is_media(o: dict) -> bool:
    return o.get("type") in MEDIA_TYPES or any(k in o for k in MEDIA_KEYS)


def _is_blob(s: str) -> bool:
    """data: URI'ları ve uzun base64 blokları (görsel, ses, dosya) olduğu gibi bırakılır."""
    return s.startswith("data:") and ";base64," in s[:120] or bool(_B64.match(s.replace("\n", "")))


class ProtocolFieldError(ValueError):
    """Protokol alanında (id, model, signature…) hassas veri var.

    Bu alanlar maskelenirse API isteği bozulabilir, maskelenmezse veri sızar.
    Tek güvenli seçenek isteği reddetmektir."""

    def __init__(self, key: str, kinds: set[str]):
        self.key, self.kinds = key, kinds
        super().__init__(f"'{key}' alanında hassas veri var ({', '.join(sorted(kinds))})")


# Bu anahtarlardaki SAYILAR protokol ayarıdır (sıcaklık, token sınırı, tohum…); taranmaz.
NUMERIC_PROTOCOL_KEYS = frozenset(
    {
        "max_tokens",
        "max_completion_tokens",
        "max_output_tokens",
        "temperature",
        "top_p",
        "top_k",
        "seed",
        "n",
        "index",
        "frequency_penalty",
        "presence_penalty",
        "logprobs",
        "top_logprobs",
        "budget_tokens",
        "created",
        "created_at",
        "timeout",
        "dimensions",
        "best_of",
        "output_index",
        "content_index",
        "sequence_number",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "cached_tokens",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    }
)


class Masker:
    def __init__(
        self,
        vault: Vault | None = None,
        kinds: Iterable[str] | None = None,
        keep_localhost: bool | None = None,
        config=None,
        extra_values: dict[str, str] | None = None,
    ):
        self.vault = vault if vault is not None else Vault()
        self.config = config
        self.kinds = list(kinds) if kinds else None
        # Kullanıcının elle maskelettiği değerler: {"Proje Kartal": "CUSTOM"}
        self.extra_values = dict(extra_values or {})
        if keep_localhost is None:
            keep_localhost = not (config.mask_localhost if config is not None else False)
        self.keep_localhost = keep_localhost
        self._cache: dict[str, tuple[int, re.Pattern | None]] = {}

    @property
    def blocked_kinds(self) -> set[str]:
        return set(self.config.blocked) if self.config is not None else set()

    # --- maskeleme -----------------------------------------------------------
    def detect(self, text: str) -> list[Match]:
        found = detect(text, self.kinds, self.keep_localhost, self.config)
        extra = list(found)
        for value, kind in self.extra_values.items():
            if not value.strip():
                continue
            pat = re.escape(value)
            pat = (r"(?<!\w)" if value[0].isalnum() else "") + pat + (r"(?!\w)" if value[-1].isalnum() else "")
            extra += [Match(m.start(), m.end(), kind, m.group(0), 99) for m in re.finditer(pat, text, re.IGNORECASE)]
        echoes = self._name_echoes(text, found)
        if len(extra) == len(found) and not echoes:
            return found
        return _resolve(extra + echoes)

    def _name_echoes(self, text: str, found: list[Match]) -> list[Match]:
        """Tam adı maskelenen kişinin adı ya da soyadı tek başına geçerse onu da yakalar.

        "Kimden: Selin Aydın … Teşekkürler, Selin" → imzadaki "Selin" de maskelenir. Kaynak,  # maskele:ignore
        bu metinde bulunan ve oturum kasasında daha önce maskelenmiş tam adlardır. Parça tek bir
        kişiye aitse o kişinin token'ını alır (model "Selin" ile "Selin Aydın"ın aynı kişi  # maskele:ignore
        olduğunu görür; geri çevirmede tam ad yazılır). Birden fazla kişiye uyuyorsa kendi
        token'ını alır. Yalnızca büyük harfle başlayan, kelime sınırında duran tam eşleşmeler
        alınır; e-posta ve tanımlayıcı içindeki parçalara dokunulmaz.
        """
        full = [m.value for m in found if m.kind == "NAME"]
        full += [v for t, v in self.vault.to_dict()["tokens"].items() if t.startswith("NAME_")]
        owners: dict[str, set[str]] = {}
        for name in full:
            words = name.split()
            if len(words) < 2:
                continue
            for w in words:
                if len(w) >= 3 and w[:1].isupper() and fold(w) not in _TITLES:
                    owners.setdefault(w, set()).add(normalize("NAME", name))
        if not owners:
            return []
        canon = {normalize("NAME", n): n for n in full}
        alt = "|".join(re.escape(w) for w in sorted(owners, key=len, reverse=True))
        rx = re.compile(rf"(?<![\w.@-])(?:{alt})(?![\w@-]|\.\w)")
        out = []
        for m in rx.finditer(text):
            who = owners[m.group(0)]
            value = canon[next(iter(who))] if len(who) == 1 else m.group(0)
            out.append(Match(m.start(), m.end(), "NAME", value, 1))
        return out

    def fork(self) -> Masker:
        """Aynı ayarlarla, boş kasalı yeni bir maskeleyici (istek başına kasa için)."""
        return Masker(Vault(), self.kinds, self.keep_localhost, self.config, self.extra_values)

    def mask(self, text: str) -> MaskResult:
        matches = self.detect(text)
        out, pos, reps = [], 0, []
        for m in matches:
            tok = self.vault.token_for(m.kind, m.value)
            out.append(text[pos : m.start])
            out.append(f"[[{tok}]]")
            reps.append((m, tok))
            pos = m.end
        out.append(text[pos:])
        return MaskResult("".join(out), matches, reps)

    def mask_obj(
        self, obj: Any, counter: Counter | None = None, produced: set[str] | None = None, notes: Counter | None = None
    ) -> Any:
        """JSON ağacını maskeler: metin değerleri ve sözlük anahtarları.

        - Metin değerleri ve sözlük anahtarları maskelenir.
        - Sayılar da taranır (5321234567 → "[[PHONE_1]]"); yalnızca NUMERIC_PROTOCOL_KEYS  # maskele:ignore
          altındakiler (temperature, max_tokens…) dokunulmadan kalır.
        - STRUCTURAL_KEYS (id, model, signature…) maskelenmez ama yine de taranır: hassas
          veri içeriyorsa ProtocolFieldError fırlatılır (istek reddedilmeli).
        - base64 blokları ve data: URI'ları taranamaz; `notes["media"]` sayılır.
        `produced`, bu çağrıda açık metinden üretilen token'larla doldurulur.
        """
        counter = counter if counter is not None else Counter()
        notes = notes if notes is not None else Counter()

        def text(s: str) -> str:
            r = self.mask(s)
            counter.update(r.counts)
            if produced is not None:
                produced.update(tok for _, tok in r.replacements)
            return r.text

        def walk(o, key=None, parent_key=None):
            if isinstance(o, str):
                if _is_blob(o):
                    notes["media"] += 1
                    return o
                if key in STRUCTURAL_KEYS:
                    found = self.detect(o)
                    if found:
                        raise ProtocolFieldError(key, {m.kind for m in found})
                    return o
                return text(o)
            if isinstance(o, (int, float)) and not isinstance(o, bool):
                if key in NUMERIC_PROTOCOL_KEYS:
                    return o
                s = repr(o) if isinstance(o, float) else str(o)
                masked = text(s)
                return o if masked == s else masked
            if isinstance(o, dict):
                if _is_media(o):
                    notes["media"] += 1
                keep_keys = key in SCHEMA_CONTAINERS
                out = {}
                for k, v in o.items():
                    if keep_keys or k in STRUCTURAL_KEYS:
                        # Şema özellik adı ya da protokol anahtarı değiştirilemez; hassas veri
                        # içeriyorsa istek reddedilmeli (değiştirmek de geçirmek de yanlış).
                        found = self.detect(k)
                        if found:
                            raise ProtocolFieldError(f"{key or 'şema'} anahtarı", {m.kind for m in found})
                        out[k] = walk(v, k, key)
                    else:
                        out[text(k)] = walk(v, k, key)
                return out
            if isinstance(o, list):
                return [walk(v, key, parent_key) for v in o]
            return o

        return walk(obj)

    # --- geri dönüş ----------------------------------------------------------
    def _pattern(self, mode: str) -> re.Pattern | None:
        n = len(self.vault.tokens)
        cached = self._cache.get(mode)
        if cached and cached[0] == n:
            return cached[1]
        rx = None
        if n and mode != "strict":
            alt = "|".join(re.escape(t) for t in sorted(self.vault.tokens, key=len, reverse=True))
            if mode == "standard":
                rx = re.compile(r"\[{1,2}[ \t]*(" + alt + r")[ \t]*\]{1,2}")
            else:
                rx = re.compile(r"(?:\[{1,2}[ \t]*)?(?<![\w])(" + alt + r")(?![\w])(?:[ \t]*\]{1,2})?")
        self._cache[mode] = (n, rx)
        return rx

    def unmask(
        self,
        text: str,
        strict: bool = False,
        *,
        mode: str | None = None,
        escape: Callable[[str], str] | None = None,
        wrap: Callable[[str, str], str] | None = None,
        allowed: set[str] | None = None,
    ) -> UnmaskResult:
        """Token'ları orijinal değerlere çevirir (modlar için modül belgesine bakın)."""
        mode = mode or ("strict" if strict else "standard")
        if mode not in MODES:
            raise ValueError(f"Geçersiz mod: {mode}")
        restored = 0
        unknown: list[str] = []
        tokens = self.vault.tokens
        # Değiştirmeler önce yer tutucuya yazılır, en sonda tek seferde uygulanır;
        # böylece geri konan değer ikinci geçişte tekrar işlenmez.
        pending: list[str] = []
        text = text.replace("\x00", "")

        def sub(m: re.Match) -> str:
            nonlocal restored
            tok = m.group(1)
            if tok in tokens and (allowed is None or tok in allowed):
                restored += 1
                v = tokens[tok]
                v = escape(v) if escape else v
                pending.append(wrap(tok, v) if wrap else v)
                return f"\x00{len(pending) - 1}\x00"
            unknown.append(tok)
            return m.group(0)

        text = TOKEN_RE.sub(sub, text)
        rx = self._pattern(mode)
        if rx is not None:
            text = rx.sub(sub, text)

        # Çevrilmeden kalan çıplak token'lar: kasada varsa "bare", yoksa ve bilinen bir
        # türdense "unknown" (model uydurmuş olabilir)
        bare: list[str] = []
        kinds = set(self.vault.counters)
        for m in TOKEN_ANY.finditer(text):
            tok = m.group(1)
            if tok.rsplit("_", 1)[0] not in kinds:
                continue
            if tok in tokens and (allowed is None or tok in allowed):
                bare.append(tok)
            else:
                unknown.append(tok)
        if pending:
            text = re.sub(r"\x00(\d+)\x00", lambda m: pending[int(m.group(1))], text)
        return UnmaskResult(text, restored, sorted(set(unknown)), sorted(set(bare)))

    def unmask_obj(
        self, obj: Any, stats: Counter | None = None, *, mode: str = "standard", allowed: set[str] | None = None
    ) -> Any:
        stats = stats if stats is not None else Counter()

        def text(s: str, escape=None) -> str:
            r = self.unmask(s, mode=mode, allowed=allowed, escape=escape)
            stats["restored"] += r.restored
            stats["unknown"] += len(r.unknown)
            return r.text

        def walk(o, key=None):
            if isinstance(o, str):
                if key in ("arguments", "partial_json"):
                    # JSON-in-string: değerler JSON kaçışlı olarak yerleştirilir
                    return text(o, escape=json_escape)
                return text(o)
            if isinstance(o, dict):
                return {text(k): walk(v, k) for k, v in o.items()}
            if isinstance(o, list):
                return [walk(v, key) for v in o]
            return o

        return walk(obj)

    def stream(
        self, json_context: bool = False, *, mode: str = "standard", allowed: set[str] | None = None
    ) -> StreamUnmasker:
        return StreamUnmasker(self, json_context, mode=mode, allowed=allowed)


# Akışın sonunda bir token'ın başlangıcı olabilecek kuyruk
_TAIL = re.compile(r"(?:(?<![\w])\[{0,2}[ \t]*[A-Z][A-Z0-9_]*[ \t]*\]?|\[{1,2}[ \t]*)$")


class StreamUnmasker:
    """Parça parça gelen metni geri çevirir.

    Token'lar parçalar arasında bölünebilir ("[[IP" + "_1]]"). Bir token'ın
    başlangıcı olabilecek kuyruk, sonraki parça gelene kadar tutulur.
    """

    MAX_HOLD = 64

    def __init__(
        self, masker: Masker, json_context: bool = False, *, mode: str = "standard", allowed: set[str] | None = None
    ):
        self.m = masker
        self.escape = json_escape if json_context else None
        self.mode = mode
        self.allowed = allowed
        self.buf = ""
        self.ctx = ""
        self.restored = 0
        self.unknown: set[str] = set()

    def _unmask(self, s: str):
        r = self.m.unmask(s, mode=self.mode, escape=self.escape, allowed=self.allowed)
        self.unknown.update(r.unknown)
        return r

    def _emit(self, out: str) -> str:
        if not out:
            return ""
        # Bir önceki karakteri bağlam olarak kullan (kelime sınırı kontrolü için)
        if self.ctx and (self.ctx.isalnum() or self.ctx == "_"):
            r = self._unmask(self.ctx + out)
            if r.text.startswith(self.ctx):
                text = r.text[1:]
            else:
                r = self._unmask(out)
                text = r.text
        else:
            r = self._unmask(out)
            text = r.text
        self.restored += r.restored
        self.ctx = out[-1]
        return text

    def feed(self, chunk: str) -> str:
        self.buf += chunk
        mt = _TAIL.search(self.buf)
        cut = mt.start() if mt and len(self.buf) - mt.start() <= self.MAX_HOLD else len(self.buf)
        out, self.buf = self.buf[:cut], self.buf[cut:]
        return self._emit(out)

    def flush(self) -> str:
        out, self.buf = self.buf, ""
        return self._emit(out)


def summarize(counts: Counter) -> str:
    return ", ".join(f"{k}×{n}" for k, n in counts.most_common())
