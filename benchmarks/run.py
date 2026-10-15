"""maskele doğruluk benchmark'ı.

Etiketli sentetik bir Türkçe korpus üretir ve tespit motorunu ölçer:

- Tür bazında kesinlik (precision) ve duyarlılık (recall)
- SIZINTI ORANI: etiketli değerin herhangi bir karakteri maskelenmeden kaldıysa sızıntı sayılır.
  Gizlilik açısından asıl önemli sayı budur.
- Negatif set: hiç kişisel veri içermeyen kod/log/metin satırlarındaki yanlış pozitifler.

Önemli: İsimler tespit sözlüğünden BAĞIMSIZ bir listeden seçilir ve bir kısmı sözlükte
yoktur. Küçük harfle yazılmış isimler gibi bilinen zor durumlar da bilerek dahildir.
Sentetik veri gerçek dünyayı tam temsil etmez; sonuçlar bir alt sınır değil, bir göstergedir.

    python benchmarks/run.py            # özet tablo
    python benchmarks/run.py --md       # Markdown (docs/benchmark.md için)
    python benchmarks/run.py --misses   # kaçan örnekleri göster
"""

from __future__ import annotations

import argparse
import random
import string
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maskele import Masker  # noqa: E402

SEED = 20261015
N = 3000

# --- Bağımsız isim listeleri (tespit sözlüğünden kopyalanmadı) ---------------
FIRST = """Ahmet Mehmet Mustafa Ali Hüseyin Hasan İbrahim Ömer Yusuf Murat Emre Burak Kerem Eymen
Göktuğ Alparslan Talha Batuhan Çağan Aras Atlas Kuzey Rüzgar Miraç Asaf Yağız Doruk Ayaz Kaan
Ayşe Fatma Emine Hatice Zeynep Elif Meryem Defne Eylül Ecrin Asel Nisanur Ravza Yaren Hiranur
Erva Beren Mira Lina Duru Azra Zehra Elanur İkra Medine Gülsüm Şükran Nurten Saniye Hayriye""".split()
LAST = """Yılmaz Kaya Demir Şahin Çelik Yıldız Yıldırım Öztürk Aydın Özdemir Arslan Doğan Kılıç
Aslan Çetin Kara Koç Kurt Özkan Şimşek Karadağ Bozdağ Tekeli Gümüş Sarıkaya Akkaya Ceylan
Erbaş Kandemir Pehlivan Uğurlu Yüce Türkmen Boz Akgün Başaran Taşdemir Kahveci Ilgaz""".split()
FOREIGN = """John Smith|Maria Garcia|Wei Zhang|Olga Ivanova|Ahmed Hassan|Sarah Johnson|Pierre Dubois|
Yuki Tanaka|Lukas Müller|Anna Kowalska|Omar Farouk|Elena Petrova""".replace("\n", "").split("|")
WEAK_PASSWORDS = [
    "letmein",
    "123456",
    "qwerty",
    "summer2024",
    "Ankara06",
    "Galatasaray1905",
    "sifre123",
    "welcome",
    "parola",
    "admin",
    "iloveyou",
    "Fenerbahce1907",
    "P@ssw0rd",
    "deneme",
]
PASSPHRASES = [
    "correct horse battery staple",
    "mavi kedi sabah kahve",
    "Uzun bir yol ve sessiz deniz",
    "kirmizi elma yesil armut",
]
STREETS = [
    "Atatürk",
    "Cumhuriyet",
    "İnönü",
    "Gazi",
    "Bağdat",
    "Büyükdere",
    "Barbaros",
    "Gül",
    "Lale",
    "Menekşe",
    "1453",
    "Hürriyet",
    "İstiklal",
    "Fevzi Çakmak",
]
NEIGH = ["Esentepe", "Moda", "Kızılay", "Alsancak", "Bahçelievler", "Çankaya", "Göztepe", "Levent"]
CITY = ["Şişli/İstanbul", "Kadıköy/İstanbul", "Çankaya/Ankara", "Konak/İzmir", "Nilüfer/Bursa", "Ankara"]
MAIL_DOMAINS = ["gmail.com", "firma.com.tr", "ornek.net", "sirket.com", "hotmail.com", "edu.tr"]
TR_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


# --- Geçerli değer üreticileri ------------------------------------------------
def tckn(r):
    d = [r.randint(1, 9)] + [r.randint(0, 9) for _ in range(8)]
    d.append(((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10)
    d.append(sum(d) % 10)
    return "".join(map(str, d))


def vkn(r):
    from maskele.detectors import valid_vkn

    while True:
        s = "".join(str(r.randint(0, 9)) for _ in range(9))
        for c in "0123456789":
            if valid_vkn(s + c):
                return s + c


def iban(r, spaced):
    bban = f"{r.randint(0, 99999):05d}0" + "".join(str(r.randint(0, 9)) for _ in range(16))
    num = "".join(str(int(c, 36)) for c in bban + "TR00")
    chk = 98 - int(num) % 97
    s = f"TR{chk:02d}{bban}"
    return " ".join(s[i : i + 4] for i in range(0, len(s), 4)) if spaced else s


def card(r):
    d = [4] + [r.randint(0, 9) for _ in range(14)]
    total = 0
    for i, x in enumerate(reversed(d)):
        if i % 2 == 0:
            x *= 2
            x = x - 9 if x > 9 else x
        total += x
    d.append((10 - total % 10) % 10)
    s = "".join(map(str, d))
    return r.choice(
        [s, " ".join(s[i : i + 4] for i in range(0, 16, 4)), "-".join(s[i : i + 4] for i in range(0, 16, 4))]
    )


def phone(r):
    n = f"5{r.randint(0, 59):02d}{r.randint(0, 9999999):07d}"
    return r.choice(
        [
            f"0{n[:3]} {n[3:6]} {n[6:8]} {n[8:]}",
            f"+90 {n[:3]} {n[3:6]} {n[6:8]} {n[8:]}",
            f"0{n}",
            f"+90{n}",
            f"({n[:3]}) {n[3:6]}-{n[6:8]}-{n[8:]}",
        ]
    )


def plate(r):
    il = f"{r.randint(1, 81):02d}"
    k = r.choice([1, 2, 3])
    letters = "".join(r.choice("ABCDEFGHJKLMNPRSTUVYZ") for _ in range(k))
    digits = {1: r.randint(1000, 9999), 2: r.randint(100, 9999), 3: r.randint(10, 999)}[k]
    return r.choice([f"{il} {letters} {digits}", f"{il}{letters}{digits}"])


def ip(r):
    return r.choice(
        [
            f"10.{r.randint(0, 255)}.{r.randint(0, 255)}.{r.randint(1, 254)}",
            f"192.168.{r.randint(0, 255)}.{r.randint(1, 254)}",
            f"{r.choice([n for n in range(11, 224) if n != 127])}."
            f"{r.randint(0, 255)}.{r.randint(0, 255)}.{r.randint(1, 254)}",
            f"2a02:{r.randint(0, 65535):x}:{r.randint(0, 65535):x}::{r.randint(1, 65535):x}",
        ]
    )


def mac(r):
    return ":".join(f"{r.randint(0, 255):02X}" for _ in range(6))


def name(r):
    parts = [r.choice(FIRST)] + ([r.choice(FIRST)] if r.random() < 0.15 else []) + [r.choice(LAST)]
    s = " ".join(parts)
    if r.random() < 0.1:  # büyük harf: yarısı Türkçe kurallı (İBRAHİM), yarısı ASCII (IBRAHIM)
        return s.replace("i", "İ").upper() if r.random() < 0.5 else s.upper()
    return s


def email(r, nm=None):
    from maskele.names import tr_lower

    nm = tr_lower(nm or name(r)).translate(TR_ASCII).split()
    return (
        f"{r.choice(['.', '_', ''])}".join(nm[:2]) + f"{r.choice(['', str(r.randint(1, 99))])}@{r.choice(MAIL_DOMAINS)}"
    )


def address(r):
    st = f"{r.choice(STREETS)} {r.choice(['Caddesi', 'Cad.', 'Sokak', 'Sk.', 'Bulvarı'])}"
    no = f"No: {r.randint(1, 250)}" + (f"/{r.randint(1, 20)}" if r.random() < 0.3 else "")
    unit = r.choice(["", f" D: {r.randint(1, 30)}", f" Daire {r.randint(1, 30)}", f", Kat {r.randint(1, 15)}"])
    mah = f"{r.choice(NEIGH)} {r.choice(['Mahallesi', 'Mah.'])}, " if r.random() < 0.6 else ""
    tail = r.choice(["", f" {r.randint(10000, 81999)} {r.choice(CITY)}", f" {r.choice(CITY)}"])
    return f"{mah}{st} {no}{unit}{tail}"


def api_key(r):
    a = string.ascii_letters + string.digits
    return r.choice(
        [
            "sk-proj-" + "".join(r.choice(a) for _ in range(40)),
            "sk-ant-api03-" + "".join(r.choice(a + "-_") for _ in range(60)),
            "AKIA" + "".join(r.choice(string.ascii_uppercase + string.digits) for _ in range(16)),
            "ghp_" + "".join(r.choice(a) for _ in range(36)),
            "AIza" + "".join(r.choice(a + "-_") for _ in range(35)),
            "xoxb-" + "-".join("".join(r.choice(string.digits) for _ in range(12)) for _ in range(2)),
        ]
    )


def password(r):
    pool = string.ascii_letters + string.digits + "!#$%&*+-.;,?@^_~"
    return "".join(r.choice(pool) for _ in range(r.randint(8, 20)))


# --- Şablonlar: (metin, [(tür, değer)]) ---------------------------------------
def sample(r):
    t = r.randrange(32)
    if t == 0:
        n, e, p = name(r), email(r), phone(r)
        return "Müşteri {} ({}) {} numarasından aradı.", [("NAME", n), ("EMAIL", e), ("PHONE", p)]
    if t == 1:
        return "2026-10-15T14:02:11Z ERROR db connect {}:5432 failed user={}", [("IP", ip(r)), ("EMAIL", email(r))]
    if t == 2:
        return "Ödeme IBAN: {} Alıcı: {}", [("IBAN", iban(r, r.random() < 0.6)), ("NAME", name(r))]
    if t == 3:
        return "Sayın {}, {} plakalı aracınızın muayene tarihi yaklaşıyor.", [("NAME", name(r)), ("PLATE", plate(r))]
    if t == 4:
        return "TCKN {} olan kişinin kaydı güncellendi.", [("TCKN", tckn(r))]
    if t == 5:
        return "export OPENAI_API_KEY={}", [("API_KEY", api_key(r))]
    if t == 6:
        q = r.choice(['"', "'"])
        return f"db_password: {q}{{}}{q}", [("SECRET", password(r))]
    if t == 7:
        return "DATABASE_URL=postgres://app:{}@{}/prod", [
            ("PASSWORD", password(r).replace("@", "x").replace("/", "x")),
            ("IP", ip(r)),
        ]
    if t == 8:
        return "Kart: {} son kullanma 12/28", [("CARD", card(r))]
    if t == 9:
        return "Firma vergi no: {} — fatura kesildi", [("VKN", vkn(r))]
    if t == 10:
        return "{} ile {} toplantıya katıldı.", [("NAME", name(r)), ("NAME", name(r))]
    if t == 11:
        return "Cihaz MAC {} ağdan düştü, son IP {}", [("MAC", mac(r)), ("IP", ip(r))]
    if t == 12:
        n = name(r)
        return "Gönderen: {} <{}>", [("NAME", n), ("EMAIL", email(r, n))]
    if t == 13:
        return "Merhaba, ben {}. Telefonum {}, mailim {}", [("NAME", name(r)), ("PHONE", phone(r)), ("EMAIL", email(r))]
    if t == 14:
        return 'headers["Authorization"] = "Bearer {}"', [
            ("SECRET", "".join(r.choice(string.ascii_letters + string.digits) for _ in range(32)))
        ]
    if t == 15:
        return "Kargo {} adına {} plakalı araçla teslim edildi.", [("NAME", name(r)), ("PLATE", plate(r))]
    if t == 16:
        return "{} adlı hastanın TC kimlik no: {}", [("NAME", name(r)), ("TCKN", tckn(r))]
    if t == 17:
        return "api_key = '{}'  # prod", [("API_KEY", api_key(r))]
    if t == 18:
        return "Şikayet: {} {}'e ulaşamıyor.", [("NAME", name(r)), ("IP", ip(r))]
    if t == 19:
        return "IBAN'ım {} — hesap sahibi {}", [("IBAN", iban(r, True)), ("NAME", name(r))]
    if t == 20:  # bilinen zor durum: küçük harfli isim
        from maskele.names import tr_lower

        return "kullanıcı {} şifresini unuttu", [("NAME", tr_lower(name(r)))]
    if t == 22:  # bağlamsız: isimden önce/sonra ipucu kelime yok
        return "Toplantı notu: {} ve {} sunumu hazırlayacak.", [("NAME", name(r)), ("NAME", name(r))]
    if t == 23:
        return "{} dün akşam sisteme giriş yaptı.", [("NAME", name(r))]
    if t == 24:  # zayıf, sözlükte bulunan parolalar
        return r.choice(["password={}", 'db_password: "{}"', "parola: {}", "PASSWORD='{}'"]), [
            ("SECRET", r.choice(WEAK_PASSWORDS))
        ]
    if t == 25:  # parola cümlesi
        return 'passphrase = "{}"', [("SECRET", r.choice(PASSPHRASES))]
    if t == 26:  # JSON içinde sayı olarak kişisel veri
        return '{{"musteri": {{"tel": {}, "tckn": {}}}}}', [
            ("PHONE", f"5{r.randint(0, 59):02d}{r.randint(0, 9999999):07d}"),
            ("TCKN", tckn(r)),
        ]
    if t in (27, 28):
        return r.choice(["Teslimat adresi: {}. Teşekkürler.", "Adres: {}", "Kargo {} adresine bırakıldı."]), [
            ("ADDRESS", address(r))
        ]
    if t == 29:  # bilinen zayıflık: yabancı isimler
        return r.choice(["Meeting with {} tomorrow.", "Müşteri {} aradı."]), [("NAME", r.choice(FOREIGN))]
    if t == 30:
        return "api_key={}", [("SECRET", r.choice(["foobar", "test", "abc123", "secretkey"]))]
    return "parola: {}", [("SECRET", password(r).replace(" ", "x"))]


NEGATIVES = [
    "2026-10-15T14:02:11.482Z INFO [api-gateway v2.14.3] req=7f3e9a12-4b8c-4d1e-9f00-2a6b1c3d4e5f",
    "listening on 0.0.0.0:8080, pid 41823, build 2026101500123",
    "self.secret = secrets.token_urlsafe(24)",
    "api_key = os.environ['OPENAI_API_KEY']",
    "password: str = Field(..., min_length=8)",
    "token: Optional[str] = None",
    "--k-secret: #A61E37;",
    "DB_PASSWORD=${DB_PASSWORD}",
    'client_secret: "<your-client-secret>"',
    "Ali Rıza Caddesi trafiğe kapandı, Mehmet Akif Ersoy Üniversitesi önünde kuyruk var",
    "No 1 Kafe ile Bağdat Caddesi'ndeki şube arasında servis var.",
    "Deniz Kuvvetleri komutanlığı tatbikat yaptı.",
    "Umut Var mı? Can sıkıcı bir hata aldık.",
    "Sipariş no 10000000147 kargoya verildi.",
    "Tutar 15499.90 TL, taksit 12, oran %3.49",
    "Sürüm 1.2.3.4 yayınlandı; önceki 999.1.2.3 idi.",
    "Saat 12:30:45'te toplantı var.",
    "Ankara Ofisi yarın açılıyor, İstanbul Ofisi kapalı.",
    "for i in range(10): print(i)",
    "SELECT id, created_at FROM orders WHERE status = 'paid' LIMIT 50;",
    "docker run -p 8787:8787 -v data:/data maskele",
    "Bugün Yarın Dün kelimeleri büyük harfle başlıyor.",
    "https://docs.example.com/v2/guide#install",
    "commit 97157c3 Merge pull request #42 from feature/x",
    # "sözlük dışı ad + soyad gibi kelime" kuralının tuzakları
    "Yeni Demir Çelik fabrikası açıldı.",
    "Kırmızı Kaya Oteli'nde kaldık.",
    "Proje Karadağ ikinci fazına geçti.",
    "Ege Bölgesi ve Toros Dağları rotası.",
    "Hazır Beton Kaya firması teklif verdi.",
    "Global Akdeniz Lojistik ile görüşüldü.",
    "Kanal Doğan yayın akışı değişti.",
    "Kurumsal Yıldırım Paketi satışta.",
    "Taksim Meydanı ve Galata Kulesi yakın.",
    "Sabah Güneş doğarken yola çıktık.",
    "Fenerbahçe Ülker Spor Salonu doldu.",
    "Mavi Deniz Restoran rezervasyonu alındı.",
    "the Aslan Hotel booking failed",
    "Error: Kafka Consumer Demirtaş timeout",
]


# Bilinçli fazla maskeleme: parola bağlamındaki belirsiz değerler gerçek bir parola olabilir,
# bu yüzden maskelenir. Yanlış pozitif sayılmaz ama ayrı raporlanır.
OVERMASK = [
    'PASSWORD: "Parola",',
    "secret: required",
    'API_KEY: "API anahtarı",',
]


def build(r):
    tmpl, ents = sample(r)
    # şablonu doldururken her değerin konumunu kaydet
    parts = tmpl.split("{}")
    text, gold = parts[0], []
    for (kind, val), tail in zip(ents, parts[1:], strict=True):
        gold.append((len(text), len(text) + len(val), kind, val))
        text += val + tail
    return text, gold


def name_bucket(val: str) -> str:
    from maskele.names import FIRST_NAMES, tr_lower

    if val in FOREIGN:
        return "NAME (yabancı)"
    if val == val.lower():
        return "NAME (küçük harf)"
    return "NAME (sözlükte)" if tr_lower(val.split()[0]) in FIRST_NAMES else "NAME (sözlük dışı)"


def evaluate(n=N, show_misses=False):
    r = random.Random(SEED)  # noqa: S311 — reproducible synthetic corpus, not a secret
    tp, fn, fp = Counter(), Counter(), Counter()
    leaks, total = Counter(), Counter()
    misses = defaultdict(list)
    for _ in range(n):
        text, gold = build(r)
        assert all(text[s:e] == v for s, e, _, v in gold), text
        dets = Masker().detect(text)
        for s, e, kind, val in gold:
            if kind == "NAME":
                kind = name_bucket(val)
            total[kind] += 1
            same = [d for d in dets if d.start < e and s < d.end and d.kind == kind.split(" ")[0]]
            if same:
                tp[kind] += 1
            else:
                fn[kind] += 1
            covered = set()
            for d in dets:
                covered.update(range(max(s, d.start), min(e, d.end)))
            if any(i not in covered and not text[i].isspace() for i in range(s, e)):
                leaks[kind] += 1
                if len(misses[kind]) < 8:
                    misses[kind].append(text)
        for d in dets:
            if not any(d.start < e and s < d.end for s, e, _, _ in gold):
                fp[d.kind] += 1
    over = sum(1 for line in OVERMASK if Masker().detect(line))
    neg_fp = []
    for line in NEGATIVES:
        dets = Masker().detect(line)
        if dets:
            neg_fp.append((line, [(d.kind, d.value) for d in dets]))
    evaluate.overmask = over
    return tp, fn, fp, leaks, total, misses, neg_fp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--misses", action="store_true")
    ap.add_argument("-n", type=int, default=N)
    a = ap.parse_args()
    tp, fn, fp, leaks, total, misses, neg_fp = evaluate(a.n)
    kinds = sorted(total, key=lambda k: -total[k])
    rows = []
    for k in kinds:
        f = fp[k.split(" ")[0]] if not k.startswith("NAME") else fp["NAME"]
        p = tp[k] / (tp[k] + f) if tp[k] + f else 1.0
        rc = tp[k] / (tp[k] + fn[k]) if tp[k] + fn[k] else 1.0
        rows.append((k, total[k], p, rc, leaks[k] / total[k]))
    allg = sum(total.values())
    overall_leak = sum(leaks.values()) / allg
    if a.md:
        print(
            f"Sentetik korpus: {a.n} örnek, {allg} etiketli değer, tohum {SEED}. Negatif set: {len(NEGATIVES)} satır.\n"
        )
        print("| Tür | Örnek | Kesinlik | Duyarlılık | Sızıntı |")
        print("|---|---:|---:|---:|---:|")
        for k, t, p, rc, lk in rows:
            print(f"| {k if ' ' in k else '`' + k + '`'} | {t} | {p:.1%} | {rc:.1%} | {lk:.1%} |")
        print(f"| **Toplam** | {allg} | | | **{overall_leak:.2%}** |")
        print(
            f"\nNegatif setteki yanlış pozitif: **{len(neg_fp)} / {len(NEGATIVES)}** satır. "
            f"Bilinçli fazla maskeleme (parola bağlamında belirsiz değerler): "
            f"{evaluate.overmask} / {len(OVERMASK)}."
        )
    else:
        print(f"{'tür':<20} {'örnek':>6} {'kesinlik':>9} {'duyarlılık':>11} {'sızıntı':>8}")
        for k, t, p, rc, lk in rows:
            print(f"{k:<20} {t:>6} {p:>9.1%} {rc:>11.1%} {lk:>8.1%}")
        print(f"\nToplam sızıntı oranı: {overall_leak:.2%} ({sum(leaks.values())}/{allg})")
        print(f"Negatif set yanlış pozitif: {len(neg_fp)}/{len(NEGATIVES)}")
        for line, d in neg_fp:
            print(f"  FP: {line!r} → {d}")
    if a.misses:
        for k, ex in misses.items():
            print(f"\n## {k} kaçanlar")
            for t in ex:
                print("  ", t)


if __name__ == "__main__":
    main()
