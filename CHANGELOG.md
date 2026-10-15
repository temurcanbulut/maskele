# Değişiklik günlüğü

Biçim [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/), sürümleme [SemVer](https://semver.org/lang/tr/).

## [0.4.2] — 2026-10-16 · Yayın hazırlığı

- Türkçe/İngilizce giriş, uygulamadan kaydedilen kullanım akışı, mimari ve doğrulama kayıtları.
- Yerel arayüzde hatalı/negatif/tekrarlı Content-Length ve Transfer-Encoding gövdelerini okumadan reddet; dört HTTP regresyon testi ekle.
- POSIX dosya izni testlerini POSIX ile sınırla; Windows'ta şifreleme/geri çevirme kontrollerini koru, ACL sınırını belgele.
- Bağlantı sınırı testinde Windows'un bağlantı sıfırlama sonucunu kabul et; zaman aşımı başarısız kalır.
- Emoji içeren metinlerde Python kod noktası ile JavaScript UTF-16 konumlarını eşleştir; gerçek tarayıcı duman testinde tam çıktıyı doğrula.
- Kod biçimini ve denetim hatalarını düzelt; CI eylemlerini ve Pyodide arşiv özetini sabitle, wheel kurulum kontrolü ekle.
- Mevcut sentetik benchmark'ı yeniden çalıştır: 4.556 değerde 114 açıkta kalan değer (%2,50), negatif sette 0/38 yanlış pozitif satır. Gerçek veri garantisi değildir.

## [0.4.1] — 2026-10-15 · Üçüncü inceleme düzeltmeleri

v0.4.0 incelemesinin 3 doğrulanmış bulgusu ve bir tasarım sınırı. Testler:
`tests/test_security_v041.py`.

### Güvenlik
- **Y-01 · JSON Schema anahtarları.** `properties`, `$defs` gibi şema kapsayıcılarındaki
  anahtarlar değiştirilmiyor ama artık taranıyor; hassas veri varsa istek 422 ile reddediliyor.
- **Y-02 · Medya politikası.** Yalnızca base64 değil, uzak görsel URL'leri (`image_url`,
  `input_image`, Anthropic `source.type = url`), dosya referansları (`file_id`, `input_file`,
  `document`) ve ses girdileri de medya sayılıyor. `media = "block"` hepsini reddediyor;
  `allow` iken hepsi `X-Maskele-Unscanned: media` ile bildiriliyor.
- **Y-03 · Log'larda yol.** Denetim kaydı ve stderr log'u yolu `redact_path` ile yazıyor:
  sorgu dizesi atılıyor, hassas veri içeren yol bileşenleri (yüzde kodlanmış biçimler dahil)
  `REDACTED` oluyor.

### Eklendi (web)
- **Tarayıcıda çalışan sürüm** ([temurcanbulut.github.io/maskele](https://temurcanbulut.github.io/maskele/)).
  Aynı Python motoru Pyodide ile tarayıcıda çalışır; metin hiçbir sunucuya gitmez. Pyodide
  siteyle aynı kaynaktan sunulur, CSP üçüncü taraf bağlantıları engeller. Yayın iş akışı siteyi
  gerçek bir tarayıcıda deneyip ancak çalışıyorsa yayımlar.
- Arayüz mantığı HTTP'den ayrıldı (`maskele/uiapp.py`); yerel arayüz ve web sürümü aynı kodu
  kullanıyor.

### Güvenlik
- **Tek başına geçen ad ve soyad sızıyordu.** "Kimden: Selin Aydın … Teşekkürler, Selin"
  metninde imzadaki "Selin" modele gidiyordu ve arayüz bunu olası kaçak olarak da
  göstermiyordu. Artık metinde ya da oturum kasasında tam adı maskelenmiş birinin adı veya
  soyadı tek başına geçtiğinde de maskeleniyor. Parça tek bir kişiye aitse o kişinin token'ını
  alıyor (model "Selin" ile "Selin Aydın"ın aynı kişi olduğunu görüyor); birden fazla kişiye
  uyuyorsa kendi token'ını alıyor.

### Dokümantasyon
- README'ye gerçek motor çıktısıyla üretilen dört senaryo görseli: NetSec erişim talebi
  (şirkete özel kurallarla), gün boyu talepler, müşteri destek, DevOps hata logu.

### Düzeltildi
- **SVG'de sahte bulgu.** `maskele scan`, SVG dosyalarındaki yol koordinatlarını (`d`,
  `points`, `transform`…) telefon ve kart numarası sanıyordu; depodaki tek bir logo 60'tan fazla
  sahte bulgu üretiyordu. Geometri öznitelikleri artık taranmıyor, `<text>` içeriği taranıyor.
- **Parantezli kod ifadesi parola sanılıyordu:** `TOKEN = (document.querySelector(…))` gibi
  atamalar artık secret sayılmıyor; `password = (Xk9…` gibi değerler maskelenmeye devam ediyor.

### Marka
- Yeni işaret: token parantezleri, aralarından akan veri çizgileri ve iki token hapı. Yeni
  palet (indigo `#6366F1`), arayüz renkleri ve sekme ikonu buna göre güncellendi.

### Eklendi
- **Çok turlu konuşmalar (`previous_response_id`).** İstek başına kasa korunarak, Responses
  API'nin sunucu tarafında geçmiş tutan akışları destekleniyor. Bir yanıtın eşlemeleri, aynı
  kimlik bilgisiyle o yanıta bağlanan bir sonraki istek için saklanıyor (1 saat, en fazla 5000
  kayıt, ham anahtar değil HMAC parmak izi). Numaralandırma turlar arasında tutarlı; başka
  kimlik bilgisiyle bağlanan istek eski değerleri alamıyor.

## [0.4.0] — 2026-10-15 · İkinci güvenlik incelemesi

v0.3.0 üzerindeki ikinci harici incelemenin 8 bulgusu ve 5 tasarım riski ele alındı. Her
bulgu önce `tests/test_security_v04.py` içinde başarısız bir testle yeniden üretildi.

### Güvenlik
- **F-01 · Protokol alanları ve sayılar.** `id`, `model`, `signature`, `tool_call_id` gibi
  alanlar artık taranıyor; hassas veri içeriyorlarsa istek 422 ile reddediliyor (maskelenirlerse
  API bozulur, maskelenmezlerse veri sızar). JSON sayıları da taranıyor
  (`{"tel": 5321234567}` → `"[[PHONE_1]]"`); yalnızca `temperature`, `max_tokens` gibi protokol
  ayarları muaf.
- **F-02 · Parola bağlamında koşulsuz maskeleme.** `password=letmein`, `"summer"`, parola
  cümleleri ve `api_key=foobar` artık maskeleniyor. "Kısa kelime parola olamaz" tahmini tamamen
  kaldırıldı; yalnızca sözdizimsel olarak kesin kod (çağrı, nitelik erişimi, tip ipucu,
  `${VAR}`) muaf.
- **F-03 · Başlıklar.** Kimlik başlıkları dokunulmadan, diğer izinli başlıklar taranarak
  iletiliyor; hassas veri varsa 422. `HTTP-Referer` ve `X-Title` varsayılan listeden çıktı.
- **F-04 · Güvenilmeyen proje yapılandırması.** Çalışma dizinindeki `.maskele.toml`, kullanıcı
  `maskele config trust` diyene kadar korumayı yalnızca sıkılaştırabiliyor. Güven dosya
  içeriğine sabitleniyor; dosya değişince düşüyor. Yok sayılan ayarlar her çalıştırmada
  gösteriliyor.
- **F-05 · Yönlendirmeler.** Upstream 3xx yönlendirmeleri takip edilmiyor (502); API anahtarı
  başka bir origin'e gitmiyor.
- **F-06 · Bağlantı sınırları.** Açık bağlantı sınırı iş parçacığı açılmadan önce uygulanıyor;
  yavaş istemcilere bağlantı ve gövde okuma zaman aşımı.
- **F-07 · TLS.** Yerleşik TLS (`--tls-cert/--tls-key`); proxy dışarı açılırken TLS ya da
  açık `--no-tls` onayı zorunlu. El sıkışma kabul döngüsünü engellemez.
- **F-08 · Rapor yolları.** JSON/SARIF'te yollar göreli; yolda hassas veri varsa
  `REDACTED-<parmak izi>`.

### Tasarım
- **İstek başına kasa.** Proxy artık paylaşılan kasa tutmuyor: istemciler numaralandırma
  alanını paylaşmıyor, bellekte eşleme birikmiyor. `--persist` proxy'den kaldırıldı.
- **Medya politikası.** Taranamayan base64 görsel/dosya içeren isteklere
  `X-Maskele-Unscanned: media` başlığı; `[proxy] media = "block"` ile reddetme.
- **Güven düzeyi.** Tespitler `high`/`low` güvenle işaretleniyor. Maskeleme her ikisini de
  maskeliyor; `scan` varsayılan olarak yalnızca `high` raporluyor (`--all`).
- README'deki "üçü de aynı kasayı kullanır" tutarsızlığı düzeltildi; ürün "local-first gizlilik
  yardımcısı" olarak konumlandırıldı.

### Eklendi
- **Adres tespiti** (`ADDRESS`): mahalle, cadde/sokak/bulvar, kapı no, daire/kat, posta kodu,
  ilçe/il.
- **Arayüzde olası kaçaklar.** Maskelenmemiş, isim olabilecek ifadeler işaretleniyor ve tek
  tıkla maskeleniyor; "Bunu da maskele" kutusu; tespitin eksiksiz olmadığını söyleyen kalıcı not.
- **Elle maskeleme:** `maskele mask --also "Proje Kartal"`, `Masker(extra_values=...)`.
- **Daha zor benchmark:** zayıf parolalar, parola cümleleri, JSON sayıları, adresler, yabancı
  isimler. Aynı benchmark'la v0.3.0 %9,46, v0.4.0 %2,50 toplam sızıntı.
- İsimlerde Türkçe yazım kuralı: kesme işaretsiz ek almış kelime ("Toplantıya") isme katılmıyor.

### Değişti (geriye uyumsuz)
- Parola bağlamındaki belirsiz değerler artık maskeleniyor (`PASSWORD: "Parola"` dahil).
- `maskele proxy` dış adreste TLS ya da `--no-tls` istiyor; erişim anahtarı en az 16 karakter.
- `ProxyServer(opener=...)` yerine `use_env_proxy`; `save`/`--persist` proxy'den kaldırıldı.

## [0.3.0] — 2026-10-15 · Güvenlik sertleştirmesi

v0.2.0 üzerinde yapılan harici kod incelemesinin (9 bulgu) tamamı düzeltildi. Her bulgu
önce `tests/test_security.py` içinde başarısız bir testle yeniden üretildi, sonra kapatıldı.

### Güvenlik
- **M-01 · Fail closed proxy.** JSON olmayan, bozuk JSON ya da kökü nesne olmayan gövdeler
  upstream'e iletilmeden 415/400/422 ile reddediliyor. Eski davranış yalnızca açık
  `--unsafe-passthrough` bayrağıyla.
- **M-02 · İstekler arası izolasyon.** Cevaplar yalnızca *o istekte açık metinden üretilen*
  token'larla geri çevriliyor (akış dahil). İstemcinin gövdeye yazdığı token'lar yetki vermiyor
  (inceleme sonrası kendi testimizle bulunan ek açık). Dışarı açılan proxy için
  `--access-key-env` ile erişim anahtarı zorunlu.
- **M-03 · JSON şema politikası.** Muaf alan listesi yalnızca protokol tanımlayıcılarına
  daraltıldı; `user`, `name`, `metadata`, `url` ve sözlük anahtarları artık maskeleniyor.
  base64 görseller ve JSON Schema özellik adları korunuyor.
- **M-04 · Başlık ve URL.** Upstream'e yalnızca izin listesindeki başlıklar gidiyor (`Cookie`
  ve özel `X-*` düşüyor, `--forward-header` ile eklenebilir). URL'de hassas değer varsa 422.
  Denetim kaydı ve log'lar sorgu dizesini yazmıyor.
- **M-05 · Rapor parmak izleri.** Tuzsuz SHA-256 yerine makineye özel anahtarla HMAC-SHA256.
  JSON ve SARIF raporlarında değerin hiçbir karakteri yer almıyor (`value: null`, `length`).
- **M-06 · Kodu bozmayan geri çevirme.** Üç mod: `strict` (proxy), `standard` (CLI/arayüz
  varsayılanı, çıplak `IP_1`'e dokunmaz ve raporlar), `loose` (eski davranış, `--loose`).
- **M-07 · Kaçan değerler.** Tırnaklı `password="Good,Secret123!"` değerleri kapanış tırnağına
  kadar; tırnaksız değerler boşluğa kadar alınıyor. Karışık harfli kısa secret'lar
  (`ASecretPass`) yakalanıyor. İsimler: ı/i katlama (`IBRAHIM`), daha büyük sözlük,
  unvanlar ("Sayın", "Dr."), bağlam ipuçları ("Müşteri:", "... adına"), soldaki ada genişleme
  ("Temur Can Bulut"), küçük harfli isimler.
- **M-08 · Kasa varsayılanları.** Proxy ve arayüz kasayı varsayılan olarak yalnızca bellekte
  tutuyor (`--persist` ile diske). Süresi dolan oturumlar her çalıştırmada siliniyor. Silme
  belgelerde "en iyi çaba" olarak tanımlandı.
- **M-09 · Kaynak sınırları.** Gövde boyutu (20 MB), eşzamanlılık (64) ve zaman aşımı (300 sn)
  sınırları; chunked istek gövdeleri reddediliyor.

### Eklendi
- **Doğruluk benchmark'ı** (`benchmarks/run.py`, `docs/benchmark.md`): tür bazında kesinlik,
  duyarlılık ve sızıntı oranı; isimler sözlük içi/dışı/küçük harf olarak ayrı raporlanıyor;
  isme benzeyen tuzaklarla dolu negatif set. CI'da regresyon kapısı (sızıntı < %3, sıfır
  yanlış pozitif). O zamanki benchmark'la toplam sızıntı v0.2.0'da %22,65, v0.3.0'da %2,05.
  *Not: v0.4.0'daki zorlaştırılmış benchmark'la v0.3.0'ın gerçek değeri %9,46 çıktı.*
- **Tür politikaları** (`[policy]`): `mask`, `block` (istek/işlem reddedilir; CLI çıkış kodu 3),
  `allow`.
- Sürüm numarası bağlamındaki IP benzeri dizeler ("Sürüm 1.2.3.4") artık IP sayılmıyor.

### Değişti (geriye uyumsuz)
- `unmask` varsayılanı çıplak `IP_1`'i artık çevirmiyor; eski davranış için `--loose`.
- JSON tarama raporunda `value` artık `null` (açık değer için `--reveal`).
- Proxy JSON dışı gövdeleri reddediyor; dışarı açılırken erişim anahtarı istiyor.

### Düzeltildi
- CI yalnızca `main` dalında tetikleniyordu; `master` eklendi. Docker imajında `/data`
  izinleri ve sağlık kontrolü.

## [0.2.0] — 2026-10-15

### Eklendi
- **Proxy** (`maskele proxy`): OpenAI ve Anthropic uyumlu yerel proxy. Chat Completions, Responses API ve Anthropic Messages için streaming; tool call argümanları; modele token koruma ipucu; JSONL denetim kaydı; `/maskele/stats`; Host başlığı doğrulaması. Hazır sağlayıcılar: openai, anthropic, openrouter, groq, mistral, deepseek, ollama.
- **Web arayüzü** (`maskele ui`): canlı önizleme, türe göre renklendirme, token ↔ orijinal değer bağı, uydurma token uyarısı, kasa görünümü. Dış istek yok, sıkı CSP, oturum anahtarı.
- **Türkçe ad-soyad tespiti** (`NAME`): ad sözlüğü, belirsiz adlar için soyad şartı, yer/kurum adı eleme, Türkçe büyük/küçük harf normalizasyonu.
- **Yapılandırma** (`.maskele.toml`): özel desenler, izin listesi, ek adlar, tür aç/kapa, kasa ve proxy ayarları; `maskele config init|show`.
- **Şifreli kasa**: scrypt + AES-256-GCM (`--encrypt` ya da `vault.encrypt`), otomatik süre sonu (`ttl_hours`), silmeden önce üzerine yazma.
- **Akış geri çevirici** (`Masker.stream()`): parçalar arasında bölünen token'ları doğru işler.
- **Tarama raporları**: klasör tarama, JSON ve SARIF 2.1.0, `--exclude`, `maskele:ignore` satır bastırma, belgeleme değerlerini (RFC 2606/5737/3849) eleme.
- `maskele kinds`, `maskele sessions` ayrıntıları, `show --json`.
- CI (3 işletim sistemi × 3 Python sürümü + SARIF öz-tarama), pre-commit kancası, Dockerfile, örnekler.

### Düzeltildi
- `password=`/`token:` kalıbının kod ifadelerini (`os.environ[...]`, `secrets.token_hex(...)`, tip ipuçları, CSS renkleri, `${VAR}`) secret sanması.
- Geri çevrilen değerin ikinci geçişte yeniden işlenebilmesi.
- `author` alanının `auth` anahtarı sanılması.

## [0.1.0] — 2026-10-15

İlk sürüm: CLI (`mask`, `unmask`, `scan`, `show`, `clear`), checksum doğrulamalı TCKN/VKN/IBAN/kart, TR telefon ve plaka, e-posta, IP, MAC, API anahtarları, JWT, özel anahtar, bağlantı dizesi parolası; tutarlı takma adlar ve LLM'lerin bozduğu token'lara dayanıklı geri çevirme.
