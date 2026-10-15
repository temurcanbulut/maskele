"""Web sürümü (GitHub Pages + Pyodide): ortak mantık, Pyodide uyumluluğu ve site üretimi."""

import json
import subprocess
import sys
from pathlib import Path

from maskele import Masker
from maskele.uiapp import UIApp

ROOT = Path(__file__).resolve().parents[1]


def _call(app, method, path, body=None):
    r = json.loads(app.handle_json(method, path, json.dumps(body) if body is not None else ""))
    return r["status"], r["body"]


def test_bridge_roundtrip():
    app = UIApp(Masker(), "web")
    code, r = _call(app, "POST", "/api/mask", {"text": "tckn=10000000146 ali@ornekfirma.com.tr", "commit": True})
    assert code == 200 and r["masked"] == "tckn=[[TCKN_1]] [[EMAIL_1]]"
    code, r = _call(app, "POST", "/api/unmask", {"text": "[[EMAIL_1]] yaz"})
    assert r["text"] == "ali@ornekfirma.com.tr yaz" and r["spans"][0]["token"] == "EMAIL_1"
    assert _call(app, "GET", "/api/vault")[1]["size"] == 2
    assert _call(app, "POST", "/api/clear", {})[0] == 200
    assert _call(app, "GET", "/api/vault")[1]["size"] == 0


def test_bridge_rejects_bad_input():
    app = UIApp(Masker(), "web")
    assert json.loads(app.handle_json("POST", "/api/mask", "{bozuk"))["status"] == 400
    assert _call(app, "POST", "/api/yok", {})[0] == 404
    assert _call(app, "POST", "/api/also", {"value": "x", "kind": "IBAN"})[0] == 400


def test_works_without_modules_missing_in_pyodide():
    """Pyodide'de bulunmayan ya da işlemeyen modüller olmadan da motor çalışmalı."""
    code = (
        "import sys\n"
        "for m in ('ssl','_ssl','lzma','_lzma','_hashlib','sqlite3','bz2','_bz2','webbrowser',"
        "'http','socket','_socket','select'):\n"
        "    sys.modules[m] = None\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "import json\nfrom maskele import Masker\nfrom maskele.uiapp import UIApp\n"
        "r = json.loads(UIApp(Masker(), 'w').handle_json('POST', '/api/mask', "
        "json.dumps({'text': 'TR33 0006 1005 1978 6457 8413 26'})))\n"
        "assert r['body']['masked'] == '[[IBAN_1]]', r\n"
    )
    subprocess.run([sys.executable, "-I", "-c", code], check=True)


def test_build_site(tmp_path):
    fake = tmp_path / "pyodide"
    fake.mkdir()
    for f in ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"):
        (fake / f).write_text("")
    out = tmp_path / "site"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_site.py"), "--pyodide", str(fake), "--out", str(out)],
        check=True,
        capture_output=True,
    )
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "Content-Security-Policy" in html and "connect-src 'self'" in html
    assert "{{" not in html and 'src="/' not in html and 'href="/' not in html
    import re

    assert not re.search(r'(?:src|href)="(?:https?:)?//', html)  # üçüncü taraf kaynak yüklenmiyor
    assert html.index("pyodide/pyodide.js") < html.index("boot.js") < html.index('src="app.js"')
    import zipfile

    names = zipfile.ZipFile(out / "maskele-py.zip").namelist()
    assert "maskele/uiapp.py" in names and not any(n.endswith((".html", ".css", ".js")) for n in names)
