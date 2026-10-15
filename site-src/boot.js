"use strict";
// maskele web sürümü: aynı Python motoru, tarayıcıda Pyodide (WebAssembly) içinde.
// Metin hiçbir sunucuya gönderilmez; sayfa yalnızca kendi dosyalarını yükler (bkz. CSP).
(() => {
  const status = document.getElementById("boot");
  const say = (t, cls) => { status.textContent = t; status.className = "boot " + (cls || ""); };

  const ready = (async () => {
    say("Motor yükleniyor… (ilk açılışta birkaç saniye sürer, sonra tarayıcı önbelleğinden gelir)");
    const py = await loadPyodide({ indexURL: "pyodide/" });
    const pkg = await fetch("maskele-py.zip");
    if (!pkg.ok) throw new Error("maskele paketi indirilemedi");
    py.unpackArchive(await pkg.arrayBuffer(), "zip");
    const app = py.runPython(
      "from maskele import Masker\nfrom maskele.uiapp import UIApp\nUIApp(Masker(), 'tarayıcı')");
    say("Hazır. Metin bu sekmede işlenir; sekmeyi kapatınca kasa silinir.", "ok");
    return app;
  })();
  ready.catch((e) => say("Motor yüklenemedi: " + e.message, "err"));

  window.maskeleBackend = async (method, path, body) =>
    JSON.parse((await ready).handle_json(method, path, body));
})();
