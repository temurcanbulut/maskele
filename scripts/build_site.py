"""GitHub Pages için statik web sürümünü üretir.

    python scripts/build_site.py --pyodide PYODIDE_DIR --out site

PYODIDE_DIR, Pyodide "core" dağıtımının açıldığı klasördür (pyodide.js, pyodide.asm.wasm,
python_stdlib.zip …). Pyodide siteyle birlikte aynı kaynaktan sunulur; sayfa üçüncü taraf
hiçbir adrese istek atmaz.
"""

from __future__ import annotations

import argparse
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "maskele" / "web"
PYODIDE_FILES = ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")

# 'wasm-unsafe-eval': WebAssembly derlemesi için gerekli; genel eval'e izin vermez.
CSP = (
    "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; "
    "img-src data:; connect-src 'self'; base-uri 'none'; form-action 'none'"
)

SITE = "https://temurcanbulut.github.io/maskele/"
OG = (
    f'<meta name="description" content="LLM\'e göndermeden önce hassas veriyi tarayıcında maskele.">\n'
    f'<meta property="og:title" content="maskele">\n'
    f'<meta property="og:description" content="Share the problem, not the data.">\n'
    f'<meta property="og:image" content="{SITE}social-preview.png">\n'
    f'<meta name="twitter:card" content="summary_large_image">'
)

NOTE_LOCAL = "Her şey bu bilgisayarda çalışır. Bu sayfa dışarıya hiçbir istek atmaz."
NOTE_WEB = (
    "Web sürümü: metin bu tarayıcıda, WebAssembly ile işlenir ve hiçbir sunucuya gönderilmez. "
    "Proxy ve terminal komutları için yerel kurulum: github.com/temurcanbulut/maskele"
)


def build(pyodide: Path, out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    (out / "pyodide").mkdir(parents=True)
    for name in PYODIDE_FILES:
        src = pyodide / name
        if not src.exists():
            raise SystemExit(f"Pyodide dosyası eksik: {src}")
        shutil.copy2(src, out / "pyodide" / name)

    with zipfile.ZipFile(out / "maskele-py.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted((ROOT / "maskele").rglob("*.py")):
            z.write(f, f.relative_to(ROOT).as_posix())

    html = (WEB / "index.html").read_text(encoding="utf-8")
    html = re.sub(r'<meta name="maskele-token"[^>]*>\n', "", html)
    html = html.replace(
        '<meta charset="utf-8">',
        f'<meta charset="utf-8">\n<meta http-equiv="Content-Security-Policy" content="{CSP}">\n'
        '<meta name="referrer" content="no-referrer">',
        1,
    )
    html = html.replace("<title>maskele</title>", "<title>maskele · tarayıcıda dene</title>\n" + OG, 1)
    html = html.replace('href="/app.css"', 'href="app.css"')
    html = html.replace("{{SESSION}}", "tarayıcı")
    if NOTE_LOCAL not in html:
        raise SystemExit("index.html alt notu bulunamadı; build_site.py'yi güncelleyin")
    html = html.replace(NOTE_LOCAL, NOTE_WEB)
    html = html.replace("<main", '<p id="boot" class="boot" role="status"></p>\n<main', 1)
    html = html.replace(
        '<script src="/app.js"></script>',
        '<script src="pyodide/pyodide.js"></script>\n<script src="boot.js"></script>\n<script src="app.js"></script>',
    )
    (out / "index.html").write_text(html, encoding="utf-8")

    css = (WEB / "app.css").read_text(encoding="utf-8") + (ROOT / "site-src" / "boot.css").read_text()
    (out / "app.css").write_text(css, encoding="utf-8")
    shutil.copy2(WEB / "app.js", out / "app.js")
    shutil.copy2(ROOT / "site-src" / "boot.js", out / "boot.js")
    shutil.copy2(ROOT / "assets" / "brand" / "social-preview.png", out / "social-preview.png")
    (out / ".nojekyll").write_text("")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pyodide", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "site")
    a = ap.parse_args()
    build(a.pyodide, a.out)
    print(f"site: {a.out}")
