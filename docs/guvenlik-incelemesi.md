# Güvenlik incelemeleri: bulgular ve düzeltmeler

Bu incelemeler, geliştirme sürecinden ayrı bir yapay zekâ modeliyle yapılmış harici kod
incelemeleridir: kaynak kod okuma, testleri çalıştırma ve yerel sahte sunucularla davranış
denemeleri. Profesyonel bir sızma testi değildir. Değeri, her bulgunun depodaki bir testle
yeniden üretilebilmesindedir: aşağıdaki testler ilgili sürümden önce başarısız, sonra başarılıdır.

## v0.4.0 incelemesi → v0.4.1

| # | Bulgu | Önem | Düzeltme | Kanıtlayan test |
|---|---|---|---|---|
| Y-01 | JSON Schema `properties` anahtarındaki PII açık gidiyordu | Yüksek | Şema anahtarları taranır; hassas veri varsa 422 (şema değiştirilmez) | `test_y01_pii_in_schema_key_rejected`, `test_y01_normal_schema_untouched` |
| Y-02 | `media = "block"` uzak görsel URL'si ve dosya kimliklerini kapsamıyordu | Yüksek | Tüm medya biçimleri (URL, `file_id`, ses, belge) tanınır; block hepsini reddeder, allow hepsini bildirir | `test_y02_block_covers_all_media` (6), `test_y02_allow_still_flags_all_media` (6), `test_y02_plain_text_not_flagged` |
| Y-03 | Reddedilen PII'li URL yolu audit log'a açık yazılıyordu | Orta–yüksek | `redact_path`: sorgu atılır, hassas yol bileşenleri REDACTED (yüzde kodlu dahil) | `test_y03_audit_log_path_redacted`, `test_y03_redact_path_variants` (3) |
| Y-T | İstek başına kasa `previous_response_id` akışlarını bozabilirdi | Tasarım | Kimliğe bağlı, TTL ve boyut sınırlı konuşma kasası | `test_conversation_previous_response_id`, `test_conversation_bound_to_credentials`, `test_conversation_store_is_bounded` |

## v0.3.0 incelemesi → v0.4.0

İkinci harici inceleme 8 bulgu ve 5 tasarım riski raporladı. Her biri `tests/test_security_v04.py` içinde önce başarısız bir testle yeniden üretildi.

| # | Bulgu | Önem | Düzeltme | Kanıtlayan test |
|---|---|---|---|---|
| F-01 | `id`/`signature` ve JSON sayıları maskelenmeden gidiyordu | Yüksek | Protokol alanları taranır, hassas veri varsa 422; sayılar taranır, protokol ayarları muaf | `test_f01_pii_in_protocol_field_rejected` (4), `test_f01_numbers_scanned`, `test_f01_structural_ids_still_work` |
| F-02 | `letmein`, `"summer"`, parola cümleleri atlanıyordu | Yüksek | Parola bağlamında koşulsuz maskeleme; yalnızca kesin kod muaf | `test_f02_weak_passwords_masked` (8), `test_f02_code_still_not_secret` (8) |
| F-03 | `HTTP-Referer`, `X-Title` taranmadan iletiliyordu | Orta–yüksek | Kimlik başlıkları ayrı; diğerleri taranır; serbest metin başlıkları varsayılan listeden çıktı | `test_f03_metadata_headers_dropped`, `test_f03_forwarded_headers_are_scanned` |
| F-04 | Proje `.maskele.toml` korumayı sessizce kapatabiliyordu | Yüksek | Güven modeli: onaysız proje yalnızca sıkılaştırır; onay içeriğe sabit | `test_f04_untrusted_project_cannot_weaken`, `test_f04_trust_is_explicit_and_pinned`, `test_f04_explicit_config_is_trusted` |
| F-05 | 302 ile API anahtarı başka sunucuya gidiyordu | Yüksek | Yönlendirme takip edilmez, 502 | `test_f05_redirects_not_followed` |
| F-06 | Eşzamanlılık sınırı bağlantı açılmasını sınırlamıyordu | Orta–yüksek | Bağlantı sınırı iş parçacığından önce; okuma zaman aşımları | `test_f06_connection_cap`, `test_f06_slow_client_times_out` |
| F-07 | Dışa açık proxy'de TLS yoktu | Yüksek | Yerleşik TLS; dış adreste TLS ya da açık `--no-tls` zorunlu | `test_f07_tls_serving`, `test_f07_external_bind_requires_tls` |
| F-08 | Rapor yollarında PII | Orta | Göreli yol + `REDACTED-<parmak izi>` | `test_f08_report_paths_redacted` |
| T-1 | Paylaşılan, büyüyen kasa | Tasarım | İstek başına kasa | `test_design_per_request_vault` |
| T-2 | Görseller taranmıyor | Tasarım | `X-Maskele-Unscanned` + `media = "block"` | `test_media_default_flags_unscanned`, `test_media_block_policy` |
| T-3 | CLI kasası şifresiz varsayılan | Tasarım | Değişmedi; aşağıda açık olarak listelendi | — |
| T-4 | README kasa tutarsızlığı | Belge | Düzeltildi | — |
| T-5 | Benchmark fazla kolay | Ölçüm | Zayıf parola, parola cümlesi, JSON sayı, adres, yabancı isim eklendi; v0.3.0'ın gerçek sızıntısı %9,46 çıktı | `test_benchmark.py` |

## v0.2.0 incelemesi → v0.3.0

v0.2.0 üzerinde yapılan harici kod incelemesi 9 bulgu raporladı. Her bulgu önce
`tests/test_security.py` içinde **başarısız bir testle yeniden üretildi**, sonra düzeltildi.
Aşağıdaki testlerin hepsi v0.2.0'da başarısız, v0.3.0'da başarılıdır.

| # | Bulgu | Önem | Düzeltme | Kanıtlayan test |
|---|---|---|---|---|
| M-01 | JSON olmayan ve bozuk gövdeler maskelenmeden iletiliyordu | Yüksek | Fail closed: yalnızca JSON nesne gövdeleri; diğerleri 415/400/422. Eski davranış yalnızca `--unsafe-passthrough` ile | `test_m01_unknown_bodies_rejected` (5 durum) |
| M-02 | İstekler arası token karışması | Yüksek | Cevaplar yalnızca o istekte açık metinden üretilen token'larla çevrilir (akış dahil); dışa açık proxy için erişim anahtarı zorunlu | `test_m02_tokens_scoped_to_request`, `test_m02_stream_scoped`, `test_m02_access_key`, `test_m02_tokens_in_history_still_restore` |
| M-02b | İstemcinin gövdeye yazdığı `[[EMAIL_1]]` ile başkasının değerini çekmesi | Yüksek | İnceleme sonrası kendi testimizle bulundu. Gövdedeki hazır token'lar yetki vermez | `test_m02_literal_token_fishing` |
| M-03 | `user`, `name`, `url` alanları ve sözlük anahtarları atlanıyordu | Orta–yüksek | Muaf liste yalnızca protokol tanımlayıcıları; anahtarlar da maskelenir; base64 ve şema adları korunur | `test_m03_keys_and_user_fields_masked`, `test_m03_structural_fields_untouched` |
| M-04 | Başlıklar ve URL maskelenmiyordu | Orta–yüksek | Başlık izin listesi; URL'de hassas değer → 422; log'larda sorgu dizesi yok | `test_m04_headers_allowlisted`, `test_m04_pii_in_url_rejected` |
| M-05 | Tuzsuz SHA-256 parmak izi geri çözülebiliyordu | Orta | Makineye özel anahtarla HMAC-SHA256; raporlarda değer karakteri yok | `test_m05_fingerprints_not_reversible`, `test_m05_sarif_has_no_value_chars` |
| M-06 | Gevşek geri çevirme kodu bozuyordu (`def IP_1()`) | Orta | strict / standard / loose modları; proxy strict, CLI standard | `test_m06_bare_names_not_restored_by_default`, `test_m06_proxy_is_strict` |
| M-07 | `password="Good,Secret123!"`, "Temur Can Bulut" gibi kaçaklar | Orta | Tırnaklı değer ayrıştırma; isimde ı/i katlama, bağlam ipuçları, unvanlar, sola genişleme, küçük harf | `test_m07_quoted_secrets` (4), `test_m07_names_fully_masked` (3), benchmark |
| M-08 | Disk kasası varsayılan şifresiz, TTL yalnızca yüklemede | Tasarım | Proxy/arayüz varsayılan olarak bellek içi; TTL her çalıştırmada süpürülür; silme "en iyi çaba" olarak belgelendi | `test_m08_expired_sessions_swept`, `test_m08_servers_memory_only_by_default` |
| M-09 | Sınırsız gövde ve bağlantı | Orta | Gövde (20 MB), eşzamanlılık (64), zaman aşımı (300 sn) sınırları | `test_m09_body_limit`, `test_m09_concurrency_limit` |

Kalite notları da kapatıldı: CI artık `master` dalında da çalışıyor, Docker imajında `/data`
izinleri ayarlandı ve sağlık kontrolü eklendi.

## Hâlâ açık olanlar (v0.4.0)

- **İsim tespiti en zayıf halka.** Sözlük dışı adlarda %12,2, küçük harfli isimlerde %35,7,
  yabancı isimlerde %51,2 sızıntı ([benchmark](benchmark.md)). Arayüzdeki olası kaçak
  işaretlemesi insan kontrolünü kolaylaştırır. Türkçe NER modeli opsiyonel bir eklenti olarak
  planlanıyor; çekirdeğin sıfır bağımlılığı korunacak.
- **Görsel içeriği taranmıyor.** Bildiriliyor ve engellenebiliyor; OCR yok.
- **CLI kasası varsayılan olarak şifresiz.** Her komutta parola sormak kullanılabilirliği ciddi
  düşürüyor; işletim sistemi anahtarlığı (keyring) entegrasyonu planlanıyor.
- **Gerçek veriyle bağımsız ölçüm yok.** Benchmark sentetik ve geliştirici tarafından yazıldı.
- **Proxy sunucusu `http.server` tabanlı.** İnternete doğrudan açılmak için değil; ekip
  kullanımında TLS sonlandıran bir ters proxy önerilir.
