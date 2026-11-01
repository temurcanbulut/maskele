"""Proxy-only restoration: display text may recover PII; tool data never does.

This is a reduction in automatic disclosure, not an agent egress firewall.
Callers must still authorize tool execution and treat model text as untrusted.
The explicit CLI/UI unmask command remains a user-directed operation.
"""

from __future__ import annotations

import re
from collections import Counter

from .core import TOKEN_RE, Masker

DISPLAY_KINDS = frozenset(
    {"EMAIL", "PHONE", "NAME", "ADDRESS", "IP", "MAC", "HOST", "TCKN", "VKN", "IBAN", "CARD", "PLATE"}
)
# Also preserve scheme-less web links. Do not decode/rewrite their destinations.
URL = re.compile(r"(?:[A-Za-z][A-Za-z0-9+.-]{0,31}:(?://)?|//|www\.)[^\s<>]+", re.IGNORECASE)
BLOCKED_FIELDS = frozenset(
    {
        "tool_calls",
        "function_call",
        "function",
        "arguments",
        "partial_json",
        "input",
        "url",
        "uri",
        "href",
        "image_url",
        "metadata",
        "thinking",
        "reasoning",
        "refusal",
    }
)


def display_allowed(masker: Masker, allowed: set[str] | None) -> set[str]:
    candidates = set(masker.vault.tokens) if allowed is None else allowed
    return {t for t in candidates if t.rsplit("_", 1)[0] in DISPLAY_KINDS}


def restore_text(masker: Masker, text: str, allowed: set[str] | None, mode: str, stats: Counter) -> str:
    safe = display_allowed(masker, allowed)

    def restore(segment: str) -> str:
        result = masker.unmask(segment, mode=mode, allowed=safe)
        stats["restored"] += result.restored
        stats["unknown"] += len(result.unknown)
        return result.text

    parts, start = [], 0
    for match in URL.finditer(text):
        parts.extend((restore(text[start : match.start()]), match.group()))
        start = match.end()
    parts.append(restore(text[start:]))
    return "".join(parts)


def restore_response(masker: Masker, obj, stats: Counter | None = None, *, mode="strict", allowed=None):
    """Restore only known human-facing protocol fields; preserve all keys/IDs."""
    stats = stats if stats is not None else Counter()

    def walk(value, key=None):
        if key in BLOCKED_FIELDS:
            return value
        if isinstance(value, dict):
            # Entire executable/provider-specific blocks remain opaque.
            kind = value.get("type", "")
            if kind not in {"", "message", "text", "output_text", "text_delta", "content_block_start"}:
                # Response event envelopes have explicit children handled below.
                if not (isinstance(kind, str) and kind.startswith("response.")):
                    return value
            return {k: walk(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v, key) for v in value]
        if isinstance(value, str) and key in {"text", "content", "output_text"}:
            return restore_text(masker, value, allowed, mode, stats)
        return value

    return walk(obj)


class DisplayStream:
    """Delay one lexical unit so chunk boundaries cannot hide a URL prefix.

    Overlong units pass through verbatim, with restoration suppressed until the
    next whitespace boundary. Buffering is bounded to 4096 characters.
    """

    def __init__(self, masker, allowed, mode):
        self.masker, self.allowed, self.mode = masker, allowed, mode
        self.buf = ""
        self.raw_unit = False
        self.restored = 0
        self.unknown = set()

    def _emit(self, text):
        stats = Counter()
        out = restore_text(self.masker, text, self.allowed, self.mode, stats)
        self.restored += stats["restored"]
        safe = display_allowed(self.masker, self.allowed)
        self.unknown.update(t for t in TOKEN_RE.findall(text) if t not in safe)
        return out

    def feed(self, chunk):
        out = []
        for part in re.findall(r"\S+|\s+", chunk):
            if part.isspace():
                out.append(self.buf if self.raw_unit else self._emit(self.buf))
                out.append(part)
                self.buf, self.raw_unit = "", False
            elif self.raw_unit:
                out.append(part)
            else:
                self.buf += part
                if len(self.buf) > 4096:
                    out.append(self.buf)
                    self.buf, self.raw_unit = "", True
        return "".join(out)

    def flush(self):
        out = self.buf if self.raw_unit else self._emit(self.buf)
        self.buf, self.raw_unit = "", False
        return out
