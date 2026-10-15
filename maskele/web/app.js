"use strict";
(() => {
  // Yerel sürüm: `maskele ui` sunucusu. Web sürümü: Pyodide köprüsü (window.maskeleBackend).
  const TOKEN = (document.querySelector('meta[name="maskele-token"]') || {}).content || "";
  const $ = (id) => document.getElementById(id);
  const GROUP = {
    TCKN: "id", VKN: "id", NAME: "id", PLATE: "id",
    IP: "net", MAC: "net", HOST: "net",
    IBAN: "money", CARD: "money",
    API_KEY: "secret", SECRET: "secret", PASSWORD: "secret", JWT: "secret", PRIVATE_KEY: "secret",
    EMAIL: "contact", PHONE: "contact", ADDRESS: "contact",
  };
  const LABEL = {
    TCKN: "TCKN", VKN: "VKN", NAME: "Ad soyad", PLATE: "Plaka", IP: "IP", MAC: "MAC", HOST: "Host",
    IBAN: "IBAN", CARD: "Kart", API_KEY: "API anahtarı", SECRET: "Secret", PASSWORD: "Parola",
    JWT: "JWT", PRIVATE_KEY: "Özel anahtar", EMAIL: "E-posta", PHONE: "Telefon", ADDRESS: "Adres",
    CUSTOM: "Elle",
  };
  const group = (k) => GROUP[k] || "custom";
  const kindOf = (tok) => tok.replace(/_\d+$/, "");
  // Python spans count Unicode code points; JS string.slice counts UTF-16 units.
  const pointSlicer = (text) => {
    const points = Array.from(text);
    return (start, end) => points.slice(start, end).join("");
  };

  async function api(path, body) {
    if (window.maskeleBackend) {
      const r = await window.maskeleBackend(body === undefined ? "GET" : "POST", path,
                                            body === undefined ? "" : JSON.stringify(body));
      if (r.status !== 200) throw new Error(r.body.error || "Hata");
      return r.body;
    }
    const r = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json", "X-Maskele-Token": TOKEN },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
    return r.json();
  }

  function el(tag, attrs, text) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function debounce(fn, ms) {
    let t;
    return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  }

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; }
    catch {
      const ta = el("textarea"); ta.value = text; document.body.append(ta); ta.select();
      const ok = document.execCommand("copy"); ta.remove(); return ok;
    }
  }

  // ---- 1. Maskeleme ---------------------------------------------------------
  const src = $("src"), hl = $("src-hl"), out = $("masked"), chips = $("chips");
  let lastMasked = "", seq = 0;

  function renderSource(text, spans, sus) {
    const slice = pointSlicer(text);
    hl.replaceChildren();
    const all = spans.map((s) => ({ ...s, t: "tok" }))
      .concat((sus || []).map((s) => ({ ...s, t: "sus" })))
      .sort((a, b) => a.start - b.start);
    let pos = 0;
    for (const s of all) {
      if (s.start < pos) continue;
      hl.append(slice(pos, s.start));
      hl.append(s.t === "tok"
        ? el("mark", { "data-g": group(s.kind), "data-tok": s.token }, slice(s.start, s.end))
        : el("mark", { class: "sus" }, slice(s.start, s.end)));
      pos = s.end;
    }
    hl.append(slice(pos) + "\n");
    hl.scrollTop = src.scrollTop;
  }

  function renderMasked(text, spans) {
    const slice = pointSlicer(text);
    out.replaceChildren();
    if (!text) {
      out.append(el("span", { class: "empty" }, "Soldaki metin burada maskelenmiş olarak görünür."));
      return;
    }
    let pos = 0;
    for (const s of spans) {
      out.append(slice(pos, s.start));
      out.append(el("span", { class: "tok", "data-g": group(s.kind), "data-tok": s.token,
        title: LABEL[s.kind] || s.kind }, `[[${s.token}]]`));
      pos = s.end;
    }
    out.append(slice(pos));
  }

  function renderChips(counts) {
    chips.replaceChildren();
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    for (const [k, n] of entries) {
      const c = el("span", { class: "chip", "data-g": group(k) }, LABEL[k] || k);
      c.append(el("b", {}, String(n)));
      chips.append(c);
    }
  }

  function renderSuspects(list) {
    const box = $("suspects"), wrap = $("suspect-list");
    const uniq = [...new Set((list || []).map((s) => s.text))];
    wrap.replaceChildren();
    box.hidden = uniq.length === 0;
    for (const t of uniq) {
      const b = el("button", { type: "button", title: "İsim olarak maskele" }, `${t} +`);
      b.addEventListener("click", () => addAlso(t, "NAME"));
      wrap.append(b);
    }
  }

  async function addAlso(value, kind) {
    try {
      await api("/api/also", { value, kind });
      preview();
    } catch (e) { $("commit-msg").textContent = e.message; $("commit-msg").className = "msg warn"; }
  }

  $("also-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const v = $("also").value.trim();
    if (v) { addAlso(v, "CUSTOM"); $("also").value = ""; }
  });

  const preview = debounce(async () => {
    const my = ++seq, text = src.value;
    if (!text.trim()) {
      renderSource("", [], []); renderMasked("", []); renderChips({}); renderSuspects([]);
      $("commit").disabled = true; return;
    }
    try {
      const r = await api("/api/mask", { text, commit: false });
      if (my !== seq) return;
      renderSource(text, r.spans, r.suspects); renderMasked(text, r.spans); renderChips(r.counts);
      renderSuspects(r.suspects);
      lastMasked = r.masked;
      if (r.blocked.length) {
        $("commit").disabled = true;
        $("commit-msg").textContent = `Politika gereği gönderilemez: ${r.blocked.map((k) => LABEL[k] || k).join(", ")}.`;
        $("commit-msg").className = "msg warn";
        return;
      }
      $("commit").disabled = false;
      $("commit-msg").textContent = r.spans.length ? "" : "Hassas değer bulunmadı.";
      $("commit-msg").className = "msg";
    } catch (e) { $("commit-msg").textContent = e.message; $("commit-msg").className = "msg warn"; }
  }, 160);

  src.addEventListener("input", preview);
  src.addEventListener("scroll", () => { hl.scrollTop = src.scrollTop; });

  // Token ↔ orijinal değer bağı
  out.addEventListener("mouseover", (e) => {
    const t = e.target.closest(".tok"); if (!t) return;
    for (const m of hl.querySelectorAll(`mark[data-tok="${CSS.escape(t.dataset.tok)}"]`)) m.classList.add("on");
    for (const p of out.querySelectorAll(`.tok[data-tok="${CSS.escape(t.dataset.tok)}"]`)) p.classList.add("on");
  });
  out.addEventListener("mouseout", () => {
    for (const n of document.querySelectorAll(".on")) n.classList.remove("on");
  });

  $("commit").addEventListener("click", async () => {
    try {
      const r = await api("/api/mask", { text: src.value, commit: true });
      lastMasked = r.masked;
      const ok = await copyText(r.masked);
      $("commit-msg").textContent = ok
        ? `${r.spans.length} değer maskelendi ve panoya kopyalandı.`
        : "Maskelendi. Panoya kopyalanamadı; sağdaki metni elle seç.";
      $("commit-msg").className = "msg";
      refreshVault();
    } catch (e) { $("commit-msg").textContent = e.message; $("commit-msg").className = "msg warn"; }
  });

  // ---- 2. Geri çevirme ------------------------------------------------------
  const reply = $("reply"), restored = $("restored");
  let lastRestored = "";

  const unmask = debounce(async () => {
    const text = reply.value;
    restored.replaceChildren();
    if (!text.trim()) {
      restored.append(el("span", { class: "empty" }, "Geri çevrilmiş cevap burada görünür."));
      $("copy-restored").disabled = true; $("restore-msg").textContent = ""; return;
    }
    try {
      const r = await api("/api/unmask", { text });
      const slice = pointSlicer(r.text);
      lastRestored = r.text;
      // Kasada olmayan token'ları kesik çizgili olarak işaretle
      const unknownRx = r.unknown.length
        ? new RegExp(`(\\[\\[${r.unknown.map((u) => u.replace(/[^A-Z0-9_]/g, "")).join("\\]\\]|\\[\\[")}\\]\\])`)
        : null;
      const appendPlain = (s) => {
        if (!unknownRx) return restored.append(s);
        for (const part of s.split(unknownRx)) {
          if (!part) continue;
          restored.append(unknownRx.test(part)
            ? el("span", { class: "tok unknown", title: "Kasada yok" }, part) : part);
        }
      };
      let pos = 0;
      for (const s of r.spans) {
        appendPlain(slice(pos, s.start));
        restored.append(el("span", { class: "val", "data-g": group(kindOf(s.token)),
          title: `[[${s.token}]]` }, slice(s.start, s.end)));
        pos = s.end;
      }
      appendPlain(slice(pos));
      $("copy-restored").disabled = false;
      const msg = $("restore-msg");
      const parts = [r.restored ? `${r.restored} token geri çevrildi.` : "Cevapta çevrilecek token bulunmadı."];
      if (r.bare.length) parts.push(`Köşeli parantezsiz geçtiği için çevrilmeyen: ${r.bare.join(", ")} (kodda değişken adı olabilir).`);
      if (r.unknown.length) parts.push(`Kasada olmayan token: ${r.unknown.join(", ")}; model uydurmuş olabilir.`);
      msg.textContent = parts.join(" ");
      msg.className = r.unknown.length ? "msg warn" : "msg";
    } catch (e) { $("restore-msg").textContent = e.message; $("restore-msg").className = "msg warn"; }
  }, 160);

  reply.addEventListener("input", unmask);
  $("copy-restored").addEventListener("click", async () => {
    $("restore-msg").textContent = (await copyText(lastRestored)) ? "Panoya kopyalandı." : "Kopyalanamadı.";
    $("restore-msg").className = "msg";
  });

  // ---- Kasa -----------------------------------------------------------------
  const reveal = $("reveal");
  let vaultItems = [];

  function hide(v) {
    if (v.length <= 4) return "•".repeat(v.length);
    return v.slice(0, 2) + "•".repeat(Math.min(v.length - 4, 18)) + v.slice(-2);
  }

  function renderVault() {
    const rows = $("vault-rows");
    rows.replaceChildren();
    $("vault-size").textContent = `${vaultItems.length} değer kasada`;
    if (!vaultItems.length) {
      const td = el("td", { colspan: "3", class: "muted" },
        "Kasa boş. İlk maskelemeden sonra eşlemeler burada listelenir.");
      const tr = el("tr"); tr.append(td); rows.append(tr);
      return;
    }
    for (const it of vaultItems) {
      const tr = el("tr");
      const t = el("td", { class: "mono" });
      t.append(el("span", { class: "tok", "data-g": group(it.kind) }, `[[${it.token}]]`));
      tr.append(t, el("td", {}, LABEL[it.kind] || it.kind),
        el("td", { class: "mono" }, reveal.checked ? it.value : hide(it.value)));
      rows.append(tr);
    }
  }

  async function refreshVault() {
    try { vaultItems = (await api("/api/vault")).items; renderVault(); } catch { /* sessiz */ }
  }

  reveal.addEventListener("change", renderVault);
  $("clear").addEventListener("click", async () => {
    if (!confirm("Bu oturumun kasası silinsin mi? Daha önce maskelenmiş cevaplar artık geri çevrilemez.")) return;
    await api("/api/clear", {});
    vaultItems = []; renderVault(); preview(); unmask();
  });

  refreshVault();
})();
