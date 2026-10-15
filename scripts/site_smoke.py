"""Üretilmiş web sürümünü gerçek tarayıcıda ve gerçek Pyodide ile dener.

    python scripts/site_smoke.py site

Yayın iş akışı bunu çalıştırır; sayfa açılmaz, CSP ihlali olur ya da maskeleme beklenen
sonucu vermezse yayın yapılmaz.
"""

import functools
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright

SAMPLE = "😀 Müşteri Ahmet Yılmaz, tckn=10000000146, iban TR33 0006 1005 1978 6457 8413 26"
EXPECT = ("[[NAME_1]]", "[[TCKN_1]]", "[[IBAN_1]]")
MASKED = "😀 Müşteri [[NAME_1]], tckn=[[TCKN_1]], iban [[IBAN_1]]"


class Quiet(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".wasm": "application/wasm",
        ".js": "text/javascript",
        ".mjs": "text/javascript",
    }

    def log_message(self, *a):
        pass


def wait_for(page, selector: str, check, timeout: float) -> str:
    """CSP 'unsafe-eval'e izin vermediği için tarayıcıda değil, burada yoklanır."""
    deadline = time.monotonic() + timeout
    while True:
        el = page.query_selector(selector)
        text = el.inner_text() if el else ""
        if check(el, text):
            return text
        if time.monotonic() > deadline:
            raise TimeoutError(f"{selector}: {text!r}")
        page.wait_for_timeout(250)


def main(site: str) -> int:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=site))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    problems, external = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: problems.append(str(e)))
        page.on("request", lambda r: external.append(r.url) if not r.url.startswith(url) else None)
        page.goto(url)
        boot = wait_for(
            page, "#boot", lambda el, _: el and ({"ok", "err"} & set(el.get_attribute("class").split())), timeout=120
        )
        page.fill("#src", SAMPLE)
        if "err" in page.get_attribute("#boot", "class").split():
            print("SORUN: motor yüklenemedi:", boot, problems, file=sys.stderr)
            return 1
        out = wait_for(page, ".out", lambda _, t: "[[IBAN_1]]" in t, timeout=30)
        page.click("#commit")  # kasaya yaz; geri çevirme yalnızca kasadaki token'ları tanır
        page.wait_for_timeout(500)
        page.fill("#reply", "[[NAME_1]] ödemesi")
        back = wait_for(page, "body", lambda _, t: "Ahmet Yılmaz ödemesi" in t, timeout=30)
        browser.close()
    print("boot:", boot)
    print("out:", out)
    ok = (
        all(t in out for t in EXPECT)
        and out == MASKED
        and "Ahmet Yılmaz ödemesi" in back
        and not problems
        and not [u for u in external if not u.startswith("data:")]
    )
    if not ok:
        print("SORUN:", problems, external, file=sys.stderr)
        return 1
    print("web sürümü çalışıyor")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "site"))
