# Güvenlik politikası

## Açık bildirme

Bir güvenlik açığı bulduysan lütfen herkese açık issue açma. Bunun yerine GitHub'ın
[özel güvenlik bildirimi](https://github.com/temurcanbulut/maskele/security/advisories/new)
özelliğini kullan. 72 saat içinde dönüş yapmayı, doğrulanan açıklar için 30 gün içinde
düzeltme yayımlamayı hedefliyorum.

Özellikle ilgilendiğim konular:

- Kasadaki gerçek değerlerin istenmeden diske, log'a, rapora ya da upstream'e sızması
- Proxy ya da arayüze başka bir siteden, yerel ağdan veya DNS rebinding ile erişim
- Şifreli kasanın parolasız açılabilmesi
- Tespit atlatma: maskelenmesi gereken bir değerin sistematik olarak kaçması

## Tehdit modeli

**Korunan varlık:** Kullanıcının LLM'e göndermek istediği metindeki kişisel ve gizli değerler.

**Hedef saldırgan / gözlemci:** LLM sağlayıcısı ve onun log'ları, alt işlemcileri ya da
sızıntıları. maskele bu tarafın tespit edilen değerleri görmesini engeller.

**Paylaşımlı proxy'de diğer istemciler:** Bir istemci, başka bir istemcinin değerlerini
cevap içinde geri çevirtememeli. Proxy her isteği ayrı, geçici bir kasayla işler ve cevapları
yalnızca aynı istekte açık metin olarak gelen değerlerle geri çevirir
(`tests/test_security.py::test_m02_*`, `tests/test_security_v04.py::test_design_per_request_vault`).

**Güvenilmeyen depolar:** Klonlanan bir depodaki `.maskele.toml`, kullanıcı onaylamadan
korumayı zayıflatamaz ya da verinin gideceği upstream'i değiştiremez.

**Ağ:** Proxy dışarı açıldığında erişim anahtarı ve TLS (ya da açıkça onaylanmış bir TLS
sonlandırıcı) zorunludur. Upstream yönlendirmeleri takip edilmez.

**Kapsam dışı:**
- Bu makinedeki yetkili kullanıcı ya da kötü amaçlı yazılım. Kasa, geri çevirme için bu
  makinede durmak zorundadır; şifreli kasa diskteki kopyayı korur, çalışan süreci korumaz.
- Tespit edilemeyen değerler. Tespit eksiksiz değildir; kaçırma oranları
  [docs/benchmark.md](docs/benchmark.md)'de ölçülüp yayımlanır. Tek bir kaçan değer güvenlik
  açığı sayılmaz, ama sistematik bir atlatma yöntemi ya da belirli bir türde ölçülebilir
  gerileme bildirim konusudur.
- Takma adlar arasındaki ilişkiler ve maskelenmemiş bağlam metninden çıkarım.

## Geçmiş incelemeler

Aşağıdaki incelemeler, geliştirme sürecinden ayrı bir yapay zekâ modeliyle (kaynak kod okuma ve
yerel sahte sunucularla davranış testleri) yapılmış harici kod incelemeleridir. Profesyonel bir
sızma testi ya da güvenlik denetimi değildir. Bulguların her biri depodaki testlerle
yeniden üretilebilir.


- **2026-10-15, v0.2.0:** Harici kod incelemesi, 9 bulgu (2 yüksek, 5 orta, 2 tasarım).
  Tamamı v0.3.0'da düzeltildi.
- **2026-10-15, v0.3.0:** İkinci harici inceleme, 8 bulgu + 5 tasarım riski. v0.4.0'da ele
  alındı. Bulgu → düzeltme → test eşlemesi: [docs/guvenlik-incelemesi.md](docs/guvenlik-incelemesi.md).

## Desteklenen sürümler

Yalnızca en son küçük sürüm güvenlik düzeltmesi alır.


### Windows kasa izinleri

POSIX sistemlerde kasa dosyası `0600`, dizini `0700` kullanır. Windows'ta bu bitler NTFS erişim izinlerini temsil etmez; dosya erişimi dizinin ACL'lerine bağlıdır. Hassas CLI oturumlarında özel kullanıcı dizini ve şifreli kasa kullanın. Şifreleme ve geri çevirme testleri tüm platformlarda çalışır.
