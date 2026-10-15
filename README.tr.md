<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/logo-dark.png">
    <img src="assets/brand/logo-light.svg" alt="maskele — Share the problem, not the data." width="560">
  </picture>
</p>
<p align="center">
  <a href="https://github.com/temurcanbulut/maskele/actions/workflows/ci.yml"><img src="https://github.com/temurcanbulut/maskele/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-818cf8" alt="Python 3.11 or newer">
  <img src="https://img.shields.io/badge/core-zero_dependencies-6cd3db" alt="Zero runtime dependencies in the core">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-c3a4f5" alt="MIT License"></a>
</p>

<h1 align="center">Sorunu paylaş, veriyi paylaşma.</h1>
<p align="center">LLM'e göndermeden önce hassas değerleri yerelde maskele.<br>Tutarlı token'ları koru. Cevabı kendi bilgisayarında geri çevir.</p>
<p align="center"><a href="README.md">English</a> · <a href="https://temurcanbulut.github.io/maskele/">Tarayıcıda dene</a> · <a href="#yerel-kurulum">Yerel kurulum</a> · <a href="docs/USAGE.tr.md">Ayrıntılı kullanım</a></p>

![Gerçek arayüz akışı: sentetik metni inceleme, maskeleme, elle kural ekleme ve örnek cevabı geri çevirme](docs/images/workflow.gif)

Çalışan uygulamadan, sentetik verilerle kaydedildi. Cevap elle yazılmış bir örnektir; LLM çağrısı yapılmaz. [Kayıt açıklaması](docs/DEMO.md).

## Paylaşmadan önce bir adım

Log, config veya destek kaydındaki tespit edilen değerler `[[IP_1]]`, `[[NAME_1]]` gibi token'larla değiştirilir. Aynı değer oturum boyunca aynı token'ı alır; cevap geldiğinde yerel eşlemeyle geri çevrilir. Çekirdek motorun çalışma zamanı bağımlılığı yoktur.

**Tespit eksiksiz değildir.** Özellikle sözlük dışı ve yabancı isimler kaçabilir. Sağdaki metni göndermeden önce kontrol et; kaçan değerleri **Bunu da maskele** ile ekle. Metnin geri kalanı ve değerler arasındaki ilişkiler görünür kalır.

| Kullanım | Başlat | Eşlemeler |
|---|---|---|
| Kurulumsuz tarayıcı | [Demoyu aç](https://temurcanbulut.github.io/maskele/) | Sekme belleğinde |
| Yerel arayüz | `maskele ui` | Varsayılan olarak süreç belleğinde |
| Terminal | `maskele mask dosya.log` | Yerel kasa; isteğe bağlı şifreleme |
| API proxy | `maskele proxy --provider openai` | İstek belleğinde; bağlı Responses konuşmalarında en fazla bir saat |

Tarayıcı sürümü aynı Python motorunu Pyodide ile çalıştırır; uygulama ve motor dosyalarını kendi adresinden yükler, metni sunucuya göndermez. Proxy ise yapılandırılan LLM sağlayıcısına istek yapar; kimlik başlıkları ve izinli protokol alanları iletilir.

## Yerel kurulum

Python 3.11+ gerekir:

```sh
git clone https://github.com/temurcanbulut/maskele.git
cd maskele
python -m venv .venv
```

PowerShell'de `.venv\Scripts\Activate.ps1`; Linux/macOS'ta `source .venv/bin/activate` ile ortamı aç:

```sh
python -m pip install ".[crypto]"
maskele ui
```

`http://127.0.0.1:8788` adresini aç. Metni yapıştır, önizlemeyi kontrol et, **Maskele ve kopyala** ile eşlemeyi oluştur. Model cevabını alt bölüme yapıştırınca aynı oturumdaki token'lar geri çevrilir. `[crypto]`, diskte tutulan CLI kasasının şifrelenmesi için gerekir; çekirdek onsuz da çalışır.

```sh
maskele mask examples/ornek.log > masked.log
maskele unmask reply.txt
maskele scan src/ --format json --output report.json
maskele proxy --provider openai
```

[CLI, yapılandırma, şifreli kasa ve proxy rehberi](docs/USAGE.tr.md) · [SDK örnekleri](examples/).

[NetSec, müşteri destek ve DevOps senaryoları](docs/USE_CASES.tr.md).

## Ölçülen kapsam

E-posta, IPv4/IPv6, telefon, TCKN, VKN, IBAN, kart, plaka, ad, adres ve yaygın secret biçimleri desteklenir. Checksum doğrulaması yalnızca biçimi sınar; bir kimliğin gerçekliğini doğrulamaz.

Sabit tohumlu **3.000 sentetik örnek / 4.556 etiketli değerde**, boşluk dışındaki en az bir karakteri açıkta kalan değerlerin oranı **%2,50**. Negatif sette yanlış pozitif **0/38 satır**. Bu küçük, oluşturulmuş korpusun ölçümüdür; gerçek veride garanti değildir.

| İsim grubu | Karakteri açıkta kalan değer |
|---|---:|
| Sözlükteki isim | %0,7 |
| Sözlük dışı isim | %12,2 |
| Küçük harfle yazılmış isim | %35,7 |
| Yabancı isim | %51,2 |

[Yöntem ve tüm sonuçlar](docs/benchmark.md) · [Makinece okunabilir kayıt](docs/verification/benchmark.json).

Görsel, ses ve dosya içerikleri incelenmez; proxy'de `media = "block"` ile reddedilebilir. Kasa orijinal değerleri içerir. Tespit edilemeyen veriler ve maskelenmeyen bağlam kişiyi tanımlayabilir. Araç tek başına anonimlik veya mevzuat uyumu sağlamaz. Gerçek sağlayıcı entegrasyonları ayrıca doğrulanmalıdır; protokol testleri yerel sahte sunucular kullanır.

[Geliştirme ve testler](README.md#development) · [Doğrulama kaydı](docs/VERIFICATION.md) · [Güvenlik](SECURITY.md) · [Katkı](CONTRIBUTING.md) · [Değişiklikler](CHANGELOG.md).

MIT © Temur Can Bulut.
