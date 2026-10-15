# Ayrıntılı kullanım

[← Ana sayfa](../README.tr.md)

## Web sürümü

[temurcanbulut.github.io/maskele](https://temurcanbulut.github.io/maskele/) yereldeki arayüzün aynısıdır ve
aynı Python motorunu kullanır. Motor tarayıcıda [Pyodide](https://pyodide.org) (WebAssembly) ile
çalışır. Sayfa yalnızca kendi dosyalarını yükler: Pyodide de aynı adresten sunulur ve sıkı bir
Content-Security-Policy sayfanın başka hiçbir adrese bağlanmasını engeller. Yapıştırdığın metin
hiçbir sunucuya gönderilmez; sekmeyi kapatınca kasa silinir.

Sınırları:
- İlk açılışta motor (~10 MB) indirilir; sonraki açılışlar tarayıcı önbelleğinden gelir.
- Proxy, CLI, `.maskele.toml` ayarları ve şifreli kasa yalnızca yerel kurulumda var.
- Hassas veriyle düzenli çalışıyorsan yerel kurulumu tercih et: bir web sayfasının içeriği,
  yayımlandığı depo kadar güvenilirdir. Sayfanın kaynağı bu depodaki `scripts/build_site.py`;
  her yayın, gerçek tarayıcıda çalıştırılan bir duman testinden geçer.

## Kurulum

```bash
pip install "maskele[crypto] @ git+https://github.com/temurcanbulut/maskele"
```

Çekirdek sıfır bağımlılıklıdır; `[crypto]` yalnızca şifreli kasa için `cryptography` ekler. Python 3.11+.

## Arayüz

```bash
maskele ui
```

Tarayıcıda yerel bir sayfa açılır:

1. **Yapıştır.** Metni sol tarafa yapıştırırsın; hassas değerler türüne göre renklenerek işaretlenir, sağda modele gidecek hâli oluşur.
2. **Kaçakları kapat.** Maskelenmemiş ama isim olabilecek ifadeler ("Zerda Tekeli") kesik çizgiyle işaretlenir ve tek tıkla maskelenir. Herhangi bir değeri de "Bunu da maskele" kutusuyla elle ekleyebilirsin.
3. **Kopyala ve gönder.** "Maskele ve kopyala" ile panoya alır, modele yapıştırırsın.
4. **Geri çevir.** Cevabı alt bölüme yapıştırınca gerçek değerler geri gelir. Modelin uydurduğu ya da köşeli parantezsiz bıraktığı token'lar ayrıca işaretlenir.

Bir token'ın üzerine gelince orijinal metindeki karşılığı yanar.

Sayfa dışarıya tek bir istek atmaz: harici font, CDN ya da analitik yok, sıkı bir CSP ile korunur.

## CLI

```bash
maskele mask app.log > masked.log        # dosyayı maskele
maskele mask --clip                      # panodan oku, maskele, panoya yaz
maskele unmask --clip                    # modelin cevabını panodan geri çevir
maskele mask -a "Proje Kartal" app.log   # tespit edilmeyen bir değeri de maskele
maskele scan app.log                     # neyin maskeleneceğini önizle (kasaya yazmaz)
maskele show                             # oturumdaki eşlemeler (değerler gizli)
maskele clear                            # kasayı sil (üzerine yazarak, en iyi çaba)
```

Geri çevirme üç modda çalışır. Varsayılan (`standard`), `[[IP_1]]` ve `[IP_1]` biçimlerini çevirir; köşeli parantezsiz `IP_1`'e dokunmaz, çünkü kodda değişken adı olabilir, onu yalnızca raporlar. `--strict` yalnızca `[[IP_1]]`'i, `--loose` çıplak `IP_1`'i de çevirir.

Her iş için ayrı oturum açabilirsin; numaralar oturum içinde tutarlı kalır:

```bash
maskele mask -s incident-42 --clip
maskele unmask -s incident-42 --clip
maskele sessions
```

## Proxy

Uygulaman OpenAI ya da Anthropic API'sini çağırıyorsa, kodda tek satır değiştirerek araya maskele'yi koyabilirsin:

```bash
maskele proxy --provider openai          # ya da anthropic, openrouter, groq, mistral, deepseek, ollama
```

```python
client = OpenAI(base_url="http://127.0.0.1:8787/v1")  # OpenAI
client = anthropic.Anthropic(base_url="http://127.0.0.1:8787")  # Anthropic
```

```mermaid
sequenceDiagram
    participant App as Uygulaman
    participant M as maskele proxy (yerel)
    participant API as OpenAI / Anthropic
    App->>M: "10.20.3.7 neden çöktü?"
    M->>M: maskele, kasaya yaz
    M->>API: "[[IP_2]] neden çöktü?"
    API-->>M: "[[IP_2]] üzerinde..." (stream)
    M->>M: parça parça geri çevir
    M-->>App: "10.20.3.7 üzerinde..."
```

- **Tespit edilen bulgularda politika denetimi.** Aşağıdaki istek biçimleri ve bulgular reddedilir; tespit edilemeyen değerler yine geçebilir:
  - Yalnızca JSON gövdeler kabul edilir; bozuk JSON, `multipart` ve ikili veri 415/400 ile reddedilir.
  - `id`, `model`, `signature` gibi protokol alanları maskelenemez (API bozulur); hassas veri içeriyorlarsa istek 422 ile reddedilir.
  - URL'de hassas değer varsa istek 422 ile durur.
- **Desteklenen JSON metin alanları taranır.** JSON'daki metinler, sözlük anahtarları ve **sayılar** (`{"tel": 5321234567}`) taranır; yalnızca `temperature`, `max_tokens` gibi protokol ayarları dokunulmadan kalır.
- **Başlıklar.** Kimlik başlıkları (`Authorization`, `x-api-key`) dokunulmadan iletilir. Diğer izinli başlıklar taranır, hassas veri içerirlerse istek reddedilir. `Cookie`, `HTTP-Referer`, `X-Title` ve özel `X-*` başlıkları düşer.
- **Yönlendirme yok.** Upstream 3xx dönerse takip edilmez; API anahtarın başka bir sunucuya gitmez.
- **İstek başına kasa.** Her istek kendi boş kasasıyla işlenir. Bir cevap yalnızca o istekte açık metin olarak gelen değerlerle geri çevrilir. Model başka bir isteğin token'ını üretse de, istemci gövdeye `[[EMAIL_1]]` yazıp tekrarlatmaya çalışsa da başka isteğin verisi açığa çıkmaz. İstemciler numaralandırma alanını paylaşmaz, sunucuda eşleme birikmez.
- **Kodu bozmaz.** Proxy yalnızca tam `[[TOKEN]]` biçimini çevirir; modelin yazdığı kodda `IP_1` adlı bir değişken varsa dokunulmaz.
- **Görseller ve dosyalar.** Görsel, ses ve dosya içerikleri taranamaz: base64 olarak gömülü olanlar da, URL ya da `file_id` ile referans verilenler de. Varsayılan olarak iletilir ve cevaba `X-Maskele-Unscanned: media` başlığı eklenir; `[proxy] media = "block"` ile hepsi reddedilir.
- **Çok turlu konuşmalar.** Responses API'nin `previous_response_id` akışında önceki turun token'ları da geri çevrilir. Eşlemeler aynı kimlik bilgisine bağlı ve bir saatle sınırlı olarak bellekte tutulur.
- **Streaming tam destekli.** Token'lar parçalar arasında bölünse bile (`"[[IP"` + `"_2]]"`) doğru geri çevrilir. Chat Completions, Responses API ve Anthropic Messages akışları ayrı ayrı ele alınır.
- **Tool call'lar dahil.** Fonksiyon argümanlarındaki token'lar JSON kaçışlarına dikkat edilerek geri çevrilir.
- **Modele ipucu.** Proxy, maskeleme yaptığında modele token'ları olduğu gibi korumasını söyleyen kısa bir sistem notu ekler (`--no-hint` ile kapatılır).
- **API anahtarı dokunulmadan iletilir.** Yalnızca protokol alanları (`model`, `role`, `tool_call_id`, `type`…) ve base64 görseller maskelenmez. `user`, `name`, `metadata` ve sözlük anahtarları dahil diğer her şey taranır.
- **Sınırlar.** Gövde boyutu (20 MB), açık bağlantı (128, iş parçacığı açılmadan önce uygulanır), eşzamanlı istek (64), yavaş istemci zaman aşımı (30 sn) ve upstream zaman aşımı (300 sn).
- **Denetim kaydı.** `--audit-log audit.jsonl` istek başına hangi türden kaç değer maskelendiğini yazar, değerlerin kendisini asla. Yollar sorgu dizesi olmadan ve hassas bileşenleri `REDACTED` olarak yazılır.
- **İstatistik.** `GET /maskele/stats`, toplam istek, maskelenen ve geri çevrilen sayıları ve tür dağılımını döndürür.

### Ekip kullanımı

Proxy varsayılan olarak yalnızca bu makineden erişilebilir. Dışarı açmak farklı bir tehdit modelidir; ham veri ağda taşınır. Bu yüzden iki şart var: erişim anahtarı ve TLS.

```bash
export MASKELE_PROXY_KEY=$(openssl rand -hex 24)
maskele proxy --host 0.0.0.0 --access-key-env MASKELE_PROXY_KEY \
  --tls-cert cert.pem --tls-key key.pem
# istemcide: base_url="https://maskele.ic-ag:8787/v1",
#            default_headers={"X-Maskele-Key": os.environ["MASKELE_PROXY_KEY"]}
```

TLS'i önünde bir ters proxy sonlandırıyorsa `--no-tls` ile açıkça onaylarsın. Caddy ile örnek:

```
maskele.ic-ag {
    reverse_proxy 127.0.0.1:8787 {
        header_up Host 127.0.0.1:8787
    }
}
```

Docker ile (port yalnızca 127.0.0.1'e yayınlanır, imaj bu yüzden `--no-tls` ile çalışır):

```bash
docker build -t maskele .
docker run --rm -p 127.0.0.1:8787:8787 -e MASKELE_PROXY_KEY maskele --provider anthropic
```

`http.server` tabanlı bu sunucu internete doğrudan açılmak için tasarlanmadı; internet erişimi gerekiyorsa önüne olgun bir ters proxy koy.

## Desteklenen türler

| Tür | Örnek | Doğrulama |
|---|---|---|
| `TCKN` | `10000000146` | 10. ve 11. hane checksum |
| `VKN` | `vergi no: 1234567890` | GİB algoritması + yakında "vergi/VKN" bağlamı |
| `IBAN` | `TR33 0006 1005 1978 6457 8413 26` | ISO 13616 mod-97 (tüm ülkeler) |
| `PHONE` | `+90 532 123 45 67`, `0532…` | TR mobil biçimleri |
| `PLATE` | `34 ABC 123`, `06 A 1234` | İl kodu 01–81, harf/rakam sayısı kuralı |
| `NAME` | `Ahmet Yılmaz`, `AYŞE NUR DEMİR`, `Sayın Doruk Ekinci` | Ad sözlüğü + soyad biçimi + bağlam ipuçları ("Müşteri:", "... adına"); "Deniz Kuvvetleri", "Kanal Doğan" gibi kalıplar elenir |
| `ADDRESS` | `Cumhuriyet Mah. Atatürk Cad. No: 12 D: 5 34380 Şişli/İstanbul` | Cadde/sokak/bulvar + kapı numarası şart; mahalle, daire, kat, posta kodu ve ilçe/il dahil edilir |
| `CARD` | `4111 1111 1111 1111` | Luhn + kart ön eki |
| `EMAIL`, `IP` (v4/v6), `MAC` | | `ipaddress` doğrulaması; `127.0.0.1` varsayılan olarak bırakılır |
| `API_KEY` | OpenAI, Anthropic, AWS, GitHub, GitLab, Slack, Google, Stripe, HF, npm | Sağlayıcı ön ekleri |
| `JWT`, `PRIVATE_KEY` | | Yapısal desen |
| `SECRET` | `password=letmein`, `parola: "Uzun bir cümle"`, `Bearer …` | Parola bağlamında değer **her zaman** maskelenir, ne kadar zayıf ya da kısa olursa olsun. Yalnızca sözdizimsel olarak kesin kod (`os.environ[…]`, `password: str`, `${VAR}`) muaf |
| `PASSWORD` | `postgres://user:PAROLA@host` | Bağlantı dizesindeki parola |
| `HOST` | `db01.prod.internal` | Opsiyonel (`--hosts`) |

Checksum doğrulaması yanlış pozitifleri ciddi şekilde azaltır: rastgele 11 haneli bir sayının geçerli TCKN olma ihtimali yaklaşık %1'dir. `maskele kinds` tüm türleri ve durumlarını listeler.

### Sentetik korpusta doğruluk

| | Sızıntı |
|---|---:|
| TCKN, VKN, IBAN, kart, e-posta, IP, telefon, plaka, MAC, adres | **%0** |
| `password=` değerleri (zayıf parolalar ve parola cümleleri dahil), API anahtarları | **%0** |
| İsim, sözlükteki ad | %0,7 |
| İsim, sözlük dışı ad | %12,2 |
| İsim, küçük harfle yazılmış | %35,7 |
| İsim, yabancı | %51,2 |
| **Toplam (4556 etiketli değer)** | **%2,50** |

Ayrıntılar, yöntem ve sınırlar: [docs/benchmark.md](benchmark.md). Benchmark CI'da çalışır; sızıntı %3'ü geçerse ya da negatif sette tek bir yanlış pozitif çıkarsa build kırılır.

## Yapılandırma

```bash
maskele config init          # proje köküne .maskele.toml yazar
maskele config init --user   # ~/.config/maskele/config.toml
maskele config show          # etkin ayarlar, kaynaklar, yok sayılanlar
maskele config trust         # bu projenin .maskele.toml'una güven
```

**Güvenilmeyen depolara karşı koruma.** Klonladığın bir depodaki `.maskele.toml`, sen `maskele config trust` diyene kadar korumayı yalnızca **sıkılaştırabilir**:

- **Yapabildikleri:** Yeni tür açmak, `block` politikası, özel desen, ek isim, kasayı şifrelemek, TTL'yi kısaltmak.
- **Yok sayılanlar:** Tür kapatma, `allow` politikası, izin listesi, upstream ve diğer proxy ayarları. Her çalıştırmada uyarı olarak gösterilir.

Güven, dosyanın içeriğine sabitlenir: dosya değişirse güven düşer. Kendi kullanıcı dosyan ve `--config` ile açıkça verdiğin dosya her zaman güvenilirdir.

```toml
[detect]
disable = ["PLATE"]
enable = ["HOST"]

[policy]                                     # tür başına: mask | block | allow
PRIVATE_KEY = "block"                        # bulunursa istek reddedilir, modele hiç gitmez

[allowlist]
values = ["destek@firmam.com.tr"]            # asla maskelenmez
patterns = ['^10\.0\.0\.\d+$']              # test ağı

[names]
extra_first_names = ["Temur"]

[[patterns]]                                 # şirkete özel kimlikler
name = "CUSTOMER_ID"
regex = 'CUS-\d{6}'

[vault]
encrypt = true      # AES-256-GCM, parola MASKELE_PASSWORD ya da istemden
ttl_hours = 24      # eski oturumlar otomatik silinir

[proxy]
upstream = "https://api.anthropic.com"
media = "block"     # taranamayan görsel/dosya içeren istekleri reddet
```

## Tarama, CI ve pre-commit

`scan` komutu kasaya dokunmadan dosya ve klasörleri tarar. `node_modules`, `.git` ve ikili dosyalar atlanır.

```bash
maskele scan src/ logs/ -x "*.min.js"                  # metin raporu
maskele scan . -f json -o rapor.json                    # JSON (değerler gizli)
maskele scan . -f sarif -o maskele.sarif --fail         # SARIF 2.1.0, bulgu varsa çıkış kodu 2
```

SARIF çıktısı GitHub Code Scanning'e doğrudan yüklenebilir. Paylaşılabilir raporlarda (JSON, SARIF) korumalar şunlar:

- **Değer yok.** Değerin tek karakteri bile rapora yazılmaz.
- **Yollar anonim.** Dosya yolları göreli yazılır; klasör adında hassas veri varsa `REDACTED-<parmak izi>` ile değiştirilir.
- **Anahtarlı parmak izi.** Parmak izleri bu makineye özel gizli anahtarla HMAC'lenir, böylece düşük entropili değerler (IP aralıkları gibi) hash'ten kaba kuvvetle geri bulunamaz.

**Maskeleme ile tarama farklı davranır.** Maskelemede parola bağlamındaki belirsiz değerler de maskelenir, çünkü fazla maskelemenin bedeli küçüktür. Taramada ise CI gürültüsünü önlemek için varsayılan olarak yalnızca yüksek güvenli bulgular raporlanır. `PASSWORD: "Parola"` gibi etiket olabilecek değerler `--all` ile gelir. Bir satırı bilerek bırakmak için sonuna `maskele:ignore` yorumu ekle. `example.com`, `192.0.2.x` gibi RFC'lerle belgelemeye ayrılmış değerler varsayılan olarak raporlanmaz.

pre-commit için `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/temurcanbulut/maskele
    rev: v0.4.2
    hooks:
      - id: maskele-scan
```

## Kütüphane olarak

```python
from maskele import Masker

m = Masker()
masked = m.mask(open("app.log").read()).text
reply = senin_llm_cagrin(masked)
print(m.unmask(reply).text)

# Streaming cevaplar için
s = m.stream()
for parca in akis:
    print(s.feed(parca), end="")
print(s.flush())
```

Daha fazlası için [`examples/`](../examples) klasörüne bak.

## Güvenlik modeli

**Neyi korur:** LLM sağlayıcısına (ve onun log'larına, eğitim verisine, alt işlemcilerine) giden metindeki tespit edilen değerleri.

**Neyi korumaz:**
- **Kaçırılan değerleri.** Tespit edilemeyen bir değer olduğu gibi gider. Kaçırma oranları [ölçüldü](benchmark.md); isimler en zayıf halka.
- **Maskelenmiş metnin kendisini.** Model, `[[IP_2]]` gibi token'ları ve aralarındaki ilişkileri görmeye devam eder; metnin geri kalanı da olduğu gibi gider.
- **Bu makinedeki saldırgana karşı.** Kasa, değerleri geri çevirebilmek için bu makinede durmak zorundadır.
- **KVKK uyumluluğunu tek başına sağlamaz.** Veri aktarımını azaltan teknik bir önlemdir; hukuki değerlendirmenin yerini tutmaz.

- **Görselleri ve dosyaları.** base64 içerik taranamaz; içindeki kimlik kartı fotoğrafını model görür. Proxy bunu `X-Maskele-Unscanned` ile bildirir, `media = "block"` ile reddeder.

**Nasıl:**
- Tespit ve maskeleme tamamen yerelde çalışır; maskele hiçbir telemetri ya da dış istek göndermez.
- Proxy ve arayüz varsayılan olarak `127.0.0.1`'e bağlanır ve Host başlığını doğrular (DNS rebinding). Proxy her isteği ayrı, geçici bir kasayla işler. Dışarı açılan proxy için erişim anahtarı ve TLS zorunludur. Arayüz API'si her çalıştırmada üretilen rastgele bir anahtar ister (CSRF) ve sıkı CSP ile sunulur.
- Güvenilmeyen bir depodaki yapılandırma korumayı zayıflatamaz.
- CLI kasası `~/.maskele/sessions/` altında `600` izinli dosyadadır. `encrypt = true` ile scrypt + AES-256-GCM kullanılır. `ttl_hours` (varsayılan 24) eski oturumları her çalıştırmada siler.
- `clear`, silmeden önce dosyanın üzerine rastgele veri yazar. Bu **en iyi çabadır**: SSD'ler, kopyala-yaz dosya sistemleri, anlık görüntüler ve yedekler eski blokları tutabilir. Hassas kullanımda şifreli kasa kullanın.

Harici kod incelemelerinin (bir yapay zekâ modeliyle yapıldı; profesyonel pentest değildir) bulguları, düzeltmeleri ve kanıtlayan testler: [docs/guvenlik-incelemesi.md](guvenlik-incelemesi.md). Açık bildirmek için [SECURITY.md](../SECURITY.md).

## Neden başka bir araç değil?

Bu alanda olgun araçlar var ve hangisinin sana uyduğunu bilmen önemli:

- **Microsoft Presidio**, NER destekli, özel tanıyıcılarla genişletilebilen olgun bir PII tespit ve anonimleştirme çatısı.
- **LLM Guard**, LLM etkileşimleri için tarayıcı seti; anonimleştirme, geri çevirme ve kasa bileşenleri içeriyor.
- **LiteLLM**, çok sağlayıcılı bir API geçidi; Presidio entegrasyonuyla PII maskeleme ve geri koyma sunuyor.

maskele bunlarla özellik sayısında yarışmıyor. Odaklandığı şeyler: **sıfır bağımlılıkla tek komutta kurulum**, Türkiye'ye özgü veri biçimlerinde **ölçülmüş ve yayımlanmış doğruluk**, **fail-closed ve istek izolasyonlu** bir proxy, elle yapıştıranlar için **yerel bir arayüz** ve kodu bozmayan geri çevirme. Çok dilli NER ya da geniş bir guardrail seti gerekiyorsa yukarıdakiler daha iyi bir tercih olabilir; ikisini birlikte de kullanabilirsin.

## Geliştirme

```bash
git clone https://github.com/temurcanbulut/maskele && cd maskele
pip install -e ".[dev]"
pytest
ruff check .
python benchmarks/run.py
```

Katkı rehberi: [CONTRIBUTING.md](../CONTRIBUTING.md) · Değişiklikler: [CHANGELOG.md](../CHANGELOG.md)

## Lisans

MIT © Temur Can Bulut


### Windows kasa izinleri

POSIX sistemlerde kasa dosyası `0600`, dizini `0700` kullanır. Windows'ta bu bitler NTFS erişim izinlerini temsil etmez; dosya erişimi dizinin ACL'lerine bağlıdır. Hassas CLI oturumlarında özel kullanıcı dizini ve şifreli kasa kullanın. Şifreleme ve geri çevirme testleri tüm platformlarda çalışır.
