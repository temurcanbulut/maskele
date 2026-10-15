"""Arayüzün HTTP'den bağımsız uygulama mantığı.

Aynı kod iki yerde çalışır:
- `maskele ui`: yerel HTTP sunucusu (`ui.py`) istekleri buraya iletir.
- Web sürümü (GitHub Pages): tarayıcıda Pyodide içinde çalışır, istekler JavaScript'ten
  doğrudan `handle_json` ile gelir; metin hiçbir sunucuya gönderilmez.
"""

from __future__ import annotations

import copy
import json
import re
import threading
from collections import Counter
from collections.abc import Callable

from .core import Masker
from .names import suspects
from .vault import Vault

_OPEN, _SEP, _CLOSE = "", "", ""
_MARKERS = re.compile(f"({_OPEN}[^{_CLOSE}]*{_CLOSE})")
MAX_TEXT = 5 * 1024 * 1024


class UIApp:
    def __init__(
        self,
        masker: Masker,
        session: str,
        save: Callable[[], None] | None = None,
        clear: Callable[[], None] | None = None,
    ):
        self.masker = masker
        self.session = session
        self.save = save or (lambda: None)
        self.clear = clear or (lambda: None)
        self.lock = threading.Lock()

    # JavaScript köprüsü: düz metin girer, düz metin çıkar (Pyodide nesne dönüşümü gerekmez)
    def handle_json(self, method: str, path: str, body: str = "") -> str:
        try:
            data = json.loads(body) if body else {}
        except ValueError:
            code, obj = 400, {"error": "Geçersiz JSON."}
        else:
            if len(body) > MAX_TEXT:
                code, obj = 413, {"error": "Metin çok büyük (en fazla 5 MB)."}
            else:
                code, obj = self.handle(method, path, data if isinstance(data, dict) else {})
        return json.dumps({"status": code, "body": obj}, ensure_ascii=False)

    def handle(self, method: str, path: str, body: dict) -> tuple[int, dict]:
        if method == "GET" and path == "/api/vault":
            return self.vault()
        if method == "POST":
            route = {
                "/api/mask": self.mask,
                "/api/unmask": self.unmask,
                "/api/also": self.also,
                "/api/clear": self.clear_all,
            }.get(path)
            if route:
                return route(body)
        return 404, {"error": "Bulunamadı."}

    def vault(self, _body=None):
        items = [
            {"token": t, "kind": t.rsplit("_", 1)[0], "value": val}
            for t, val in self.masker.vault.to_dict()["tokens"].items()
        ]
        return 200, {"session": self.session, "size": len(items), "items": items}

    def mask(self, body):
        text = str(body.get("text", ""))
        commit = bool(body.get("commit"))
        mk = self.masker
        blocked = sorted(mk.blocked_kinds)
        with self.lock:
            if commit and blocked and mk.blocked_kinds & {m.kind for m in mk.detect(text)}:
                return 422, {"error": "Politika gereği engellenen veri türü var: " + ", ".join(blocked) + "."}
            if commit:
                m = mk
            else:  # önizleme: kasayı değiştirmeden aynı numaralandırmayı göster
                m = Masker(
                    Vault.from_dict(copy.deepcopy(mk.vault.to_dict())),
                    mk.kinds,
                    mk.keep_localhost,
                    mk.config,
                    mk.extra_values,
                )
            r = m.mask(text)
            if commit and r.matches:
                self.save()
        spans = [{"start": mt.start, "end": mt.end, "kind": mt.kind, "token": tok} for mt, tok in r.replacements]
        sus = [
            {"start": a, "end": b, "text": t} for a, b, t in suspects(text, [(mt.start, mt.end) for mt in r.matches])
        ]
        counts = dict(Counter(mt.kind for mt in r.matches))
        return 200, {
            "masked": r.text,
            "spans": spans,
            "counts": counts,
            "suspects": sus,
            "blocked": sorted(set(counts) & mk.blocked_kinds),
            "vault_size": len(mk.vault),
        }

    def unmask(self, body):
        text = "".join(c for c in str(body.get("text", "")) if c not in (_OPEN, _SEP, _CLOSE))
        # Çevrilen her değeri işaretlerle sar, sonra işaretleri span'e dönüştür
        with self.lock:
            r = self.masker.unmask(text, wrap=lambda tok, v: f"{_OPEN}{tok}{_SEP}{v}{_CLOSE}")
        out, spans, length = [], [], 0
        for part in _MARKERS.split(r.text):
            if part.startswith(_OPEN):
                tok, val = part[1:-1].split(_SEP, 1)
                spans.append({"start": length, "end": length + len(val), "token": tok})
                part = val
            out.append(part)
            length += len(part)
        return 200, {"text": "".join(out), "spans": spans, "restored": r.restored, "unknown": r.unknown, "bare": r.bare}

    def also(self, body):
        value = str(body.get("value", "")).strip()
        kind = str(body.get("kind", "CUSTOM")).upper()
        if not value or len(value) > 500:
            return 400, {"error": "Değer 1-500 karakter olmalı."}
        if kind not in ("NAME", "CUSTOM", "ADDRESS"):
            return 400, {"error": "Tür NAME, CUSTOM ya da ADDRESS olmalı."}
        with self.lock:
            self.masker.extra_values[value] = kind
        return 200, {"ok": True, "extra": len(self.masker.extra_values)}

    def clear_all(self, _body):
        with self.lock:
            self.masker.vault = Vault()
            self.masker.extra_values.clear()
            self.masker._cache.clear()
            self.clear()
        return 200, {"ok": True}
