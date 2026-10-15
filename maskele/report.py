"""Tarama: dosya/klasör gezme ve metin, JSON, SARIF raporları."""

from __future__ import annotations

import fnmatch
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .detectors import KIND_INFO, Match

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    "dist",
    "build",
    ".idea",
    ".vscode",
    ".next",
    "target",
}
MAX_FILE = 5 * 1024 * 1024

SEVERITY = {  # SARIF seviyesi
    "PRIVATE_KEY": "error",
    "API_KEY": "error",
    "SECRET": "error",
    "PASSWORD": "error",
    "JWT": "error",
    "TCKN": "error",
    "CARD": "error",
    "IBAN": "warning",
    "VKN": "warning",
    "NAME": "note",
    "EMAIL": "warning",
    "PHONE": "warning",
    "PLATE": "note",
    "IP": "note",
    "MAC": "note",
    "HOST": "note",
}


@dataclass
class Finding:
    path: str
    line: int
    col: int
    end_col: int
    kind: str
    value: str

    def preview(self) -> str:
        return preview(self.value)


def _report_key() -> bytes:
    """Bu makineye özel, rastgele HMAC anahtarı (~/.maskele/report.key, 600).

    Parmak izleri aynı makinede tekrar eden taramalarda sabit kalır (CI tekrarları,
    GitHub Code Scanning eşleştirmesi), ama anahtar olmadan düşük entropili değerler
    (IP aralıkları, kısa kimlikler) kaba kuvvetle geri bulunamaz.
    """
    from .vault import default_home

    env = os.environ.get("MASKELE_REPORT_KEY")
    if env:
        return env.encode()
    p = default_home() / "report.key"
    try:
        return bytes.fromhex(p.read_text().strip())
    except (OSError, ValueError):
        key = secrets.token_bytes(32)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key.hex())
        return key


def fingerprint(*parts: str) -> str:
    return hmac.new(_report_key(), "\x1f".join(parts).encode(), hashlib.sha256).hexdigest()


def preview(v: str) -> str:
    v = v.replace("\n", "⏎")
    if len(v) <= 6:
        return v[:1] + "•" * (len(v) - 1)
    return v[:3] + "•" * min(len(v) - 5, 20) + v[-2:]


def is_binary(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            return b"\0" in f.read(8192)
    except OSError:
        return True


def _excluded(p: Path, patterns: Iterable[str]) -> bool:
    s = p.as_posix()
    return any(
        fnmatch.fnmatch(s, pat) or fnmatch.fnmatch(p.name, pat) or fnmatch.fnmatch(s, f"*/{pat}") for pat in patterns
    )


def iter_files(paths: Iterable[str], exclude: Iterable[str] = ()) -> Iterator[Path]:
    exclude = list(exclude)
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for root, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not _excluded(Path(root) / d, exclude))
                for f in sorted(files):
                    fp = Path(root) / f
                    if _excluded(fp, exclude):
                        continue
                    if fp.stat().st_size <= MAX_FILE and not is_binary(fp):
                        yield fp
        elif p.is_file() and not _excluded(p, exclude):
            yield p


# Vektör çizim verisi: koordinat dizileri telefon ya da kart numarası gibi görünür.
_GEOMETRY_ATTR = re.compile(
    r'(?i)\b(?:d|points|viewBox|transform|x[12]?|y[12]?|cx|cy|r|rx|ry|width|height)\s*=\s*"[^"]*"'
)
_GEOMETRY_SUFFIXES = {".svg"}


def geometry_blanked(path: str, text: str) -> str:
    """SVG geometri özniteliklerindeki rakamları boşlukla değiştirir; uzunluk ve konumlar korunur,
    <text> içerikleri ve diğer öznitelikler taranmaya devam eder."""
    if Path(path).suffix.lower() not in _GEOMETRY_SUFFIXES:
        return text
    return _GEOMETRY_ATTR.sub(lambda m: re.sub(r"[0-9]", " ", m.group(0)), text)


SUPPRESS = "maskele:ignore"

# Belgeleme için ayrılmış değerler (RFC 2606, RFC 5737, RFC 3849)
_DOC_DOMAINS = re.compile(r"(?i)@(?:[\w-]+\.)*(?:example\.(?:com|org|net)|[\w-]+\.(?:example|test|invalid))$")
_DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")]


def is_documentation(kind: str, value: str) -> bool:
    if kind == "EMAIL":
        return bool(_DOC_DOMAINS.search(value))
    if kind == "IP":
        try:
            ip = ipaddress.ip_address(value)
        except ValueError:
            return False
        return any(ip.version == n.version and ip in n for n in _DOC_NETS)
    return False


def to_findings(
    path: str, text: str, matches: list[Match], include_examples: bool = False, include_low: bool = False
) -> list[Finding]:
    """Eşleşmeleri satır/sütun konumlu bulgulara çevirir.

    `maskele:ignore` içeren satırlar ve (varsayılan olarak) RFC'lerle belgelemeye
    ayrılmış örnek değerler atlanır.
    """
    out = []
    lines = text.split("\n")
    for m in matches:
        line = text.count("\n", 0, m.start) + 1
        if SUPPRESS in lines[line - 1]:
            continue
        if not include_examples and is_documentation(m.kind, m.value):
            continue
        if not include_low and m.confidence == "low":
            continue
        ls = text.rfind("\n", 0, m.start) + 1
        out.append(Finding(path, line, m.start - ls + 1, m.end - ls + 1, m.kind, m.value))
    return out


def render_text(findings: list[Finding], reveal: bool = False) -> str:
    if not findings:
        return "Hassas veri bulunamadı."
    lines = []
    w = max(len(f"{f.path}:{f.line}:{f.col}") for f in findings)
    for f in findings:
        loc = f"{f.path}:{f.line}:{f.col}"
        lines.append(f"{loc:<{w}}  {f.kind:<12} {f.value if reveal else f.preview()}")
    files = len({f.path for f in findings})
    lines.append(f"\n{len(findings)} bulgu, {files} dosyada.")
    return "\n".join(lines)


def share_path(path: str) -> str:
    """Paylaşılabilir raporlar için dosya yolu.

    - Çalışma dizinine göreli yazılır; dışındaysa ev dizini ~ ile kısaltılır ve yalnızca son
      iki bileşen kalır (kullanıcı adı, şirket klasör yapısı sızmasın).
    - Yolda hassas veri tespit edilirse (klasör adında e-posta, TCKN…) o parça
      REDACTED-<parmak izi> ile değiştirilir; aynı değer hep aynı etiketi alır.
    """
    from .detectors import detect

    p = Path(path)
    try:
        rel = p.resolve().relative_to(Path.cwd().resolve())
        out = rel.as_posix()
    except ValueError:
        parts = p.resolve().parts
        out = "…/" + "/".join(parts[-2:]) if len(parts) > 2 else p.as_posix()
    for m in reversed(detect(out, keep_localhost=False)):
        out = out[: m.start] + "REDACTED-" + fingerprint("path", m.value)[:8] + out[m.end :]
    return out


def render_json(findings: list[Finding], reveal: bool = False) -> str:
    return json.dumps(
        {
            "tool": "maskele",
            "version": __version__,
            "count": len(findings),
            "findings": [
                {
                    "path": f.path if reveal else share_path(f.path),
                    "line": f.line,
                    "column": f.col,
                    "end_column": f.end_col,
                    "kind": f.kind,
                    "value": f.value if reveal else None,
                    "length": len(f.value),
                    "fingerprint": fingerprint(f.kind, f.value)[:32],
                }
                for f in findings
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def render_sarif(findings: list[Finding]) -> str:
    """SARIF 2.1.0 — GitHub Code Scanning ve çoğu CI aracı tarafından okunur.

    Gerçek değer rapora asla yazılmaz (tek karakteri bile); yalnızca konum, tür,
    uzunluk ve anahtarlı parmak izi.
    """
    kinds = sorted({f.kind for f in findings})
    rules = [
        {
            "id": f"maskele/{k}",
            "name": k,
            "shortDescription": {"text": f"Hassas veri: {KIND_INFO.get(k, k)}"},
            "defaultConfiguration": {"level": SEVERITY.get(k, "warning")},
            "helpUri": "https://github.com/temurcanbulut/maskele#desteklenen-türler",
        }
        for k in kinds
    ]
    results = [
        {
            "ruleId": f"maskele/{f.kind}",
            "ruleIndex": kinds.index(f.kind),
            "level": SEVERITY.get(f.kind, "warning"),
            "message": {"text": f"{KIND_INFO.get(f.kind, f.kind)} bulundu ({len(f.value)} karakter)."},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": share_path(f.path)},
                        "region": {"startLine": f.line, "startColumn": f.col, "endColumn": f.end_col},
                    }
                }
            ],
            "partialFingerprints": {"maskele/v2": fingerprint(share_path(f.path), f.kind, f.value)},
        }
        for f in findings
    ]
    return json.dumps(
        {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "maskele",
                            "version": __version__,
                            "informationUri": "https://github.com/temurcanbulut/maskele",
                            "rules": rules,
                        }
                    },
                    "results": results,
                }
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
