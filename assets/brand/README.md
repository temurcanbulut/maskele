# maskele marka varlıkları

## Fikir

İşaret, ürünün kendi sözdizimi: token parantezleri `[ ]`. Aralarından veri çizgileri akar ve
iki çizgi birer token hapı taşır. Okunuşu: "veri girer, token olarak geçer, yerine geri
döner." Alt yazı da bunu söyler: **Share the problem, not the data.**

Konsept bir ChatGPT tasarım çalışmasından geliyor; vektör çizim, küçük boy sürümü ve renk
dengesi bu depoda yeniden yapıldı.

## Dosyalar

| Dosya | Kullanım |
|---|---|
| `logo-light.svg`, `logo-dark.svg` | İşaret + kelime işareti + alt yazı. README başlığı, sunumlar |
| `wordmark-light.svg`, `wordmark-dark.svg` | Alt yazısız; dar alanlar |
| `mark.svg` | Yalnız işaret; açık/koyu temaya kendiliğinden uyar |
| `mark-light.svg`, `mark-dark.svg` | Yalnız işaret, sabit renk |
| `icon.svg`, `icon-512.png`, `icon-192.png` | Uygulama ikonu, avatar (indigo zemin) |
| `icon-dark.svg` | Koyu zeminli ikon |
| `favicon.svg`, `icon-32.png` | Tarayıcı sekmesi. Dalgasız, kalın çizgili küçük boy sürümü |
| `social-preview.png` | GitHub sosyal önizleme (1280×640) |

Kelime işaretindeki yazı vektöre çevrilmiştir (Inter Display SemiBold); yazı tipi kurulu
olmasa da her yerde aynı görünür. Ad her yerde küçük harfle yazılır: `maskele`, paket ve komut
adıyla aynı.

## Renkler

| Ad | Kod | Kullanım |
|---|---|---|
| Gece | `#0B1020` | Yazı (açık zemin), koyu zemin |
| İndigo | `#6366F1` | Parantezler, ikon zemini |
| Derin indigo | `#4F46E5` | Açık zeminde haplar, bağlantı ve düğmeler (beyaz yazıyla AA kontrast) |
| Menekşe | `#A78BFA` | Veri çizgileri (yarı saydam) |
| Lavanta | `#CBD5FF` | Koyu zeminde haplar |
| Sis | `#F4F6FB` | Açık zemin, koyu zeminde yazı |

## Kurallar

- Haplar her zaman çizgilerden **daha baskın** kalır; token işaretin öznesidir.
- İşareti döndürme, eğme, gölge, parıltı ya da gradyan ekleme.
- Kalkan, kilit ya da maske ikonuyla birlikte kullanma; işaret zaten "gizlemeyi" anlatıyor.
- 24 pikselin altında `favicon.svg` kullan; dalgalar o boyda leke olur.
- Tanıtım metinlerinde "tamamen güvenli", "sıfır risk" gibi iddialar kullanma. Ürün bir
  yardımcı; isim tespiti hâlâ kaçırabiliyor (bkz. `docs/benchmark.md`).

Varlıklar `scripts/brand.py` ile yeniden üretilebilir.
