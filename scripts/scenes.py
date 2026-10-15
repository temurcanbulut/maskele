"""README senaryo görsellerini üretir: docs/senaryolar/*.png

    python scripts/scenes.py

Görsellerdeki maskeleme ve geri çevirme bu betik çalışırken gerçek maskele motorundan geçer;
elle yazılan tek şey modelin cevabıdır (temsili). Motor değişirse görseller de değişir.
Gerekir: playwright (Chromium).
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maskele import Masker  # noqa: E402
from maskele.config import load_config  # noqa: E402

OUT = ROOT / "docs" / "senaryolar"
MARK = (ROOT / "assets" / "brand" / "mark-light.svg").read_text()

GROUP = {
    "TCKN": "id",
    "VKN": "id",
    "NAME": "id",
    "PLATE": "id",
    "IP": "net",
    "MAC": "net",
    "HOST": "net",
    "IBAN": "money",
    "CARD": "money",
    "API_KEY": "sec",
    "SECRET": "sec",
    "PASSWORD": "sec",
    "JWT": "sec",
    "PRIVATE_KEY": "sec",
    "EMAIL": "con",
    "PHONE": "con",
    "ADDRESS": "con",
}
TOKEN = re.compile(r"\[\[([A-Z][A-Z0-9_]*?)_(\d+)\]\]")
_O, _S, _C = "", "", ""


def grp(kind: str) -> str:
    return GROUP.get(kind, "cus")


def render_source(text: str, m: Masker) -> str:
    """Orijinal metin: maskelenecek değerlerin altı türüne göre çizili."""
    out, pos = [], 0
    for mt in m.detect(text):
        out.append(html.escape(text[pos : mt.start]))
        out.append(f'<u class="{grp(mt.kind)}">{html.escape(text[mt.start : mt.end])}</u>')
        pos = mt.end
    out.append(html.escape(text[pos:]))
    return "".join(out)


def render_tokens(text: str) -> str:
    """Token içeren metin: token'lar renkli hap olarak."""
    return TOKEN.sub(lambda t: f'<b class="t {grp(t.group(1))}">{html.escape(t.group(0))}</b>', html.escape(text))


def render_restored(text: str, m: Masker) -> str:
    r = m.unmask(text, wrap=lambda tok, v: f"{_O}{tok}{_S}{v}{_C}")
    out = []
    for part in re.split(f"({_O}[^{_C}]*{_C})", r.text):
        if part.startswith(_O):
            tok, val = part[1:-1].split(_S, 1)
            out.append(f'<u class="{grp(tok.rsplit("_", 1)[0])}">{html.escape(val)}</u>')
        else:
            out.append(html.escape(part))
    return "".join(out)


CSS = """
*{box-sizing:border-box;margin:0}
body{width:1600px;background:#F4F6FB;font-family:"Inter Display",Inter,sans-serif;color:#0B1020;padding:56px 64px 44px}
header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:34px}
.kick{font:600 15px/1 "Inter Display";letter-spacing:.14em;text-transform:uppercase;color:#4F46E5;margin-bottom:14px}
h1{font:650 40px/1.15 "Inter Display";letter-spacing:-.02em;max-width:1150px}
.sub{font:500 19px/1.45 "Inter Display";color:#5B6478;margin-top:12px;max-width:1150px}
.brand{display:flex;align-items:center;gap:10px;font:650 24px "Inter Display";letter-spacing:-.02em;flex:none}
.brand svg{width:40px;height:40px}
.flow{display:grid;grid-template-columns:1fr 56px 1fr 56px 1fr;align-items:stretch}
.arrow{display:flex;align-items:center;justify-content:center;color:#A78BFA}
.arrow svg{width:34px;height:34px}
.card{background:#fff;border:1px solid #D8DCE8;border-radius:18px;padding:22px 24px;display:flex;flex-direction:column;gap:14px;min-width:0}
.card.model{border-color:#C7C9F7;box-shadow:0 0 0 4px #EEF0FF}
.label{display:flex;align-items:center;gap:10px;font:650 16px "Inter Display"}
.label i{font-style:normal;display:inline-grid;place-items:center;width:26px;height:26px;border-radius:50%;background:#4F46E5;color:#fff;font:700 14px "Inter Display"}
.label small{font:500 14px "Inter Display";color:#5B6478;margin-left:auto}
pre{font:500 15.5px/1.62 "DejaVu Sans Mono",monospace;white-space:pre-wrap;word-break:break-word;color:#0B1020}
.ask{background:#F4F6FB;border-radius:12px;padding:12px 14px;font:500 15px/1.45 "Inter Display";color:#2B3350}
.ask b{color:#4F46E5;font-weight:650}
.where{font:500 14px/1.4 "Inter Display";color:#5B6478;border-top:1px dashed #D8DCE8;padding-top:12px;margin-top:auto}
u{text-decoration:none;border-bottom:3px solid;padding-bottom:1px}
u.id{border-color:#E0A54A}u.net{border-color:#3CA9B2}u.money{border-color:#9B7BE0}u.sec{border-color:#D9677B}u.con{border-color:#5B8DEF}u.cus{border-color:#7FA33A}
.t{font-weight:700;border-radius:6px;padding:1px 5px}
.t.id{color:#8A5A0F;background:#FBEFD9}.t.net{color:#0D6E77;background:#DDF1F2}.t.money{color:#6D41B3;background:#ECE4F8}
.t.sec{color:#A61E37;background:#F8E1E6}.t.con{color:#2459B8;background:#E1EBFA}.t.cus{color:#4F6420;background:#E8EFD9}
.extra{display:grid;grid-template-columns:1.05fr 1fr;gap:24px;margin-top:24px}
.panel{background:#0B1020;color:#E6E9F5;border-radius:18px;padding:22px 26px}
.panel .label{color:#fff}.panel .label small{color:#9AA3BF}
.panel pre{color:#CBD5FF;font-size:14.5px}
.panel .c{color:#7C86A8}.panel .k{color:#A5B4FC}.panel .s{color:#F0BE6A}
.notes{display:flex;flex-direction:column;gap:12px;justify-content:center}
.note{display:flex;gap:14px;align-items:flex-start;font:500 17px/1.45 "Inter Display";color:#2B3350}
.note b{display:inline-grid;place-items:center;flex:none;width:30px;height:30px;border-radius:9px;background:#EEF0FF;color:#4F46E5;font:700 15px "Inter Display"}
footer{display:flex;justify-content:space-between;margin-top:26px;font:500 14px "Inter Display";color:#7A8299}
"""

ARROW = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>'
)


def page(kick, title, sub, src_label, src_meta, src_html, ask, masked_html, reply_html, where, extra="") -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<header><div><div class="kick">{kick}</div><h1>{title}</h1><p class="sub">{sub}</p></div>
<div class="brand">{MARK}maskele</div></header>
<div class="flow">
 <div class="card"><div class="label"><i>1</i>{src_label}<small>{src_meta}</small></div><pre>{src_html}</pre>
  <div class="where">Altı çizili değerler bilgisayarından çıkmaz.</div></div>
 <div class="arrow">{ARROW}</div>
 <div class="card model"><div class="label"><i>2</i>Modele giden<small>ChatGPT · Claude · API</small></div>
  <div class="ask"><b>İstek:</b> {ask}</div><pre>{masked_html}</pre>
  <div class="where">Model yapıyı görür, kimlikleri görmez.</div></div>
 <div class="arrow">{ARROW}</div>
 <div class="card"><div class="label"><i>3</i>Cevap, gerçek değerlerle<small>yerelde geri çevrildi</small></div>
  <pre>{reply_html}</pre><div class="where">{where}</div></div>
</div>{extra}
<footer><span>Maskeleme ve geri çevirme gerçek maskele çıktısıdır; model cevabı temsilîdir. Tüm kişi ve kurum bilgileri uydurmadır.</span>
<span>github.com/temurcanbulut/maskele</span></footer></body></html>"""


def scene(m: Masker, source: str, reply_masked: str):
    src_html = render_source(source, m)
    masked = m.mask(source).text
    return src_html, render_tokens(masked), render_restored(reply_masked, m), masked


def toml_html(path: Path) -> str:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        code, sep, comment = line.partition("#") if not line.lstrip().startswith("#") else ("", "#", line[1:])
        if line.lstrip().startswith("#"):
            out.append(f'<span class="c">{html.escape(line, quote=False)}</span>')
            continue
        e = html.escape(code, quote=False)
        e = re.sub(r"(\"[^\"]*\"|'[^']*')", r'<span class="s">\1</span>', e)
        e = re.sub(r"^(\[\[?\w+\]\]?)", r'<span class="k">\1</span>', e)
        if sep:
            e += f'<span class="c">#{html.escape(comment, quote=False)}</span>'
        out.append(e)
    return "\n".join(out)


def build() -> dict[str, str]:
    pages = {}

    # 1 · NetSec: erişim talebi + şirkete özel kurallar
    cfg_path = OUT / "netsec.maskele.toml"
    m = Masker(config=load_config(cfg_path, use_files=False))
    mail = """Kimden: Selin Aydın <selin.aydin@ornekfirma.com.tr>
Kime: netsec@ornekfirma.com.tr
Konu: Erişim talebi REQ-48213

Merhaba, yeni raporlama sunucumuz 85.105.44.17
için db-pay-01.corp (10.20.3.9) üzerinde
5432/tcp erişimi gerekiyor. Onaylayan:
Murat Koç, sicil 20417. Yarın 09:00'da canlı.

Teşekkürler, Selin"""
    reply = """iptables -A INPUT -s [[IP_1]] \\
  -d [[IP_2]] -p tcp --dport 5432 \\
  -m comment --comment "[[TALEP_1]]" \\
  -j ACCEPT

Risk: [[HOST_1]] ödeme verisi taşıyor.
Kuralı 30 günlük açın; onay kaydına
sicil [[SICIL_1]] ([[NAME_2]]) yazılsın.
[[NAME_1]] için yalnızca okuma yetkisi
verin."""
    s, mk, rp, masked = scene(m, mail, reply)
    assert "Selin" not in masked and "REQ-48213" not in masked and "20417" not in masked, masked
    extra = f"""<div class="extra">
 <div class="panel"><div class="label">.maskele.toml<small>ekibin kendi kuralları, depoda durur</small></div>
 <pre>{toml_html(cfg_path)}</pre></div>
 <div class="notes">
  <div class="note"><b>1</b><span><strong>Şirketine özel kimlikler.</strong> Talep numarası, sicil, müşteri no: bir regex yeter, token'ı da kendi adınla gelir (<code>TALEP_1</code>, <code>SICIL_1</code>).</span></div>
  <div class="note"><b>2</b><span><strong>İç altyapı.</strong> <code>*.corp</code>, <code>*.local</code> host adları ve iç IP'ler maskelenir; ekip adresi gibi zararsız değerler izin listesinde kalır.</span></div>
  <div class="note"><b>3</b><span><strong>Kırmızı çizgiler.</strong> Özel anahtar gibi türler <code>block</code> ile hiç gönderilmez; işlem reddedilir.</span></div>
  <div class="note"><b>4</b><span><strong>İmzadaki tek ad da gider.</strong> "Selin Aydın" maskelenince imzadaki yalnız "Selin" de aynı token'ı (<code>NAME_1</code>) alır; model ikisinin aynı kişi olduğunu bilir.</span></div>
 </div></div>"""
    pages["netsec-erisim-talebi"] = page(
        "Senaryo 1 · NetSec ekibi",
        "Erişim talebini modele ver, kimlikleri ve altyapıyı kendinde tut",
        "Gelen talep e-postası olduğu gibi yapıştırılır. Model kuralı yazar ve riski değerlendirir; "
        "kişiler, IP'ler, iç host adları ve şirket numaraları hiç dışarı çıkmaz.",
        "Gelen e-posta",
        "Outlook'tan kopyalandı",
        s,
        "Bu talep için iptables kuralı yaz, riskleri değerlendir.",
        mk,
        rp,
        "Kural doğrudan uygulanabilir: gerçek IP'ler, host ve talep no yerinde.",
        extra,
    )

    # 2 · Aynı gün gelen talepler: tutarlı token'lar ilişkiyi korur
    m = Masker()
    day = """09:12 · Kerem Yıldız
"85.105.44.17 adresinden VPN erişimi
istiyorum, evden çalışacağım."

14:40 · Deniz Arslan
"85.105.44.17 için prod-db'ye SSH açar
mısınız? Kerem'in makinesinden
bağlanacağım, benimki bozuldu."

17:05 · Kerem Yıldız
"VPN talebimi iptal edin lütfen." """
    reply = """İki farklı kişi aynı kaynak adresten
([[IP_1]]) erişim istiyor: önce VPN,
sonra prod-db'ye SSH. VPN talebi
akşam iptal edilmiş, SSH açık duruyor.

Öneri: SSH'yi onaylamadan önce
[[NAME_2]] ile telefonda doğrulayın;
[[NAME_1]]'ın makinesi paylaşılıyor
ya da ele geçirilmiş olabilir."""
    s, mk, rp, masked = scene(m, day, reply)
    assert masked.count("[[IP_1]]") == 2 and "Kerem" not in masked, masked
    assert "[[NAME_1]]'in makinesinden" in masked, masked
    pages["tutarli-tokenlar"] = page(
        "Senaryo 2 · Gün boyu gelen talepler",
        "Aynı değer her yerde aynı token: model ilişkiyi görür",
        "Talepler gün içinde ayrı ayrı gelse de aynı oturumda aynı IP hep IP_1, aynı kişi hep NAME_1 olur; yalnız adıyla anılsa bile. "
        "Model, kimseyi tanımadan örüntüyü yakalar.",
        "Bugünkü talepler",
        "ticket kuyruğundan",
        s,
        "Bugünkü erişim taleplerini özetle. Şüpheli bir durum var mı?",
        mk,
        rp,
        "Model kimin kim olduğunu bilmeden şüpheli örüntüyü buldu.",
    )

    # 3 · Destek: KVKK kapsamındaki müşteri kaydı
    m = Masker()
    ticket = """Konu: İade talebim hâlâ sonuçlanmadı
Ad Soyad: Elif Şahin
TCKN: 10000000146
Telefon: 0532 418 77 09
IBAN: TR33 0006 1005 1978 6457 8413 26
Adres: Atatürk Cad. No: 12 D: 4 Kadıköy

Sipariş 7741 için üç haftadır iade
bekliyorum, kimse dönmüyor. Elif"""
    reply = """Sayın [[NAME_1]],

Yaşadığınız gecikme için özür dileriz.
7741 numaralı siparişinizin iadesi
onaylandı; tutar 3 iş günü içinde
[[IBAN_1]]
numaralı hesabınıza yatırılacak.

Gelişmeleri [[PHONE_1]] numarasından
size ayrıca bildireceğiz."""
    s, mk, rp, masked = scene(m, ticket, reply)
    assert "Elif" not in masked and "10000000146" not in masked, masked
    pages["destek-musteri-kaydi"] = page(
        "Senaryo 3 · Müşteri destek",
        "Müşteri kaydıyla cevap yazdır, kişisel veriyi paylaşma",
        "TCKN ve IBAN checksum ile doğrulanarak bulunur. Model nazik bir cevap taslağı yazar; "
        "müşterinin kimliği modele hiç gitmez.",
        "Destek kaydı",
        "CRM'den kopyalandı",
        s,
        "Özür dileyen, iadenin 3 iş günü içinde yatacağını söyleyen bir cevap yaz.",
        mk,
        rp,
        "Taslak gönderilmeye hazır: ad, IBAN ve telefon yerinde.",
    )

    # 4 · DevOps: hata logu
    m = Masker()
    log = """14:02:11Z ERROR payment-api v2.14.3
POST /v1/charge from 85.105.44.17
  -> 10.20.3.7:8080 (customer: Ahmet Yılmaz)
psycopg.OperationalError: connection to
  server at "10.20.3.9", port 5432 failed
DATABASE_URL=postgresql://svc_pay:Xk9#mP2vL@10.20.3.9/pay
Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyLTQyIn0.dGVzdHNpZ25hdHVyZQ
retry 3/5 on 10.20.3.7 ... giving up"""
    reply = """Kök neden: [[IP_2]] üzerindeki
payment-api, [[IP_3]]:5432'deki
veritabanına bağlanamıyor. Ağ
kuralını ve DB'nin ayakta olduğunu
kontrol edin.

Ayrıca: DB parolası ([[PASSWORD_1]])
ve bir oturum token'ı ([[JWT_1]])
log'a düz yazılıyor; ikisini de
yenileyin ve log'dan çıkarın."""
    s, mk, rp, masked = scene(m, log, reply)
    assert "Xk9#mP2vL" not in masked and "eyJ" not in masked, masked
    pages["devops-hata-logu"] = page(
        "Senaryo 4 · DevOps / SRE",
        "Log'u yapıştır, parolaları ve token'ları değil",
        "Bağlantı adresindeki parola, JWT, iç ve dış IP'ler ayıklanır. Model kök nedeni bulur; "
        "üstelik log'a sızan sırları da fark eder.",
        "Hata logu",
        "kubectl logs",
        s,
        "Bu hatanın kök nedeni ne?",
        mk,
        rp,
        "Hangi sırrın sızdığını model söyledi, değerini hiç görmedi.",
    )
    return pages


def main() -> None:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    pages = build()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, doc in pages.items():
            pg = browser.new_page(viewport={"width": 1600, "height": 400}, device_scale_factor=1.5)
            pg.set_content(doc)
            pg.wait_for_timeout(200)
            pg.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            pg.close()
            print(OUT / f"{name}.png")
        browser.close()


if __name__ == "__main__":
    main()
