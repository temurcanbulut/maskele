# Kullanım senaryoları

[← Ana sayfa](../README.tr.md) · [English](../README.md)

Dört görsel de sentetik verilerle hazırlanmıştır. Maskeleme ve geri çevirme Maskele motorunun çıktılarıdır; model cevapları temsili olarak yazılmıştır. Görsellerdeki senaryoların maskeleme kontrolleri [üretim betiğinde](../scripts/scenes.py) bulunur. Tespit eksiksiz değildir; paylaşılacak metin ayrıca gözden geçirilmelidir.

| Senaryo | Gösterdiği akış |
|---|---|
| [NetSec](#netsec-erişim-talebi) | Erişim e-postası, iç host adları ve ekibe özel kurallar |
| [Tutarlı token’lar](#tutarlı-tokenlar) | Aynı oturumda tekrarlanan IP ve kişi eşlemeleri |
| [Müşteri destek](#müşteri-destek) | Ad, TCKN, telefon, IBAN ve adres içeren kayıt |
| [DevOps / SRE](#devops--sre) | Hata logundaki bağlantı parolası, JWT ve IP adresleri |

## NetSec: erişim talebi

Örnek yapılandırma, iç host tespitini açar; talep numarası ve sicil için özel desenler ekler. Ekip e-posta adresi izin listesinde kalır. Görseldeki ağ kuralı ve risk yorumu temsili cevap metnidir.

[Örnek .maskele.toml](senaryolar/netsec.maskele.toml) · [Tam boyut](senaryolar/netsec-erisim-talebi.png)

![NetSec erişim talebinin özel kurallarla maskelenmesi ve temsili cevabın geri çevrilmesi](senaryolar/netsec-erisim-talebi.png)

## Tutarlı token’lar

Aynı yerel oturumda aynı IP aynı token'ı alır. Bilinen tam isim ve eşleşen kısa isim de aynı kişiye bağlanabilir. Böylece örnekteki taleplerin ortak adresi maskelenmiş metinde izlenebilir. Bu oturum davranışı, bağımsız proxy isteklerinin ortak bir kasa paylaştığı anlamına gelmez.

[Tam boyut](senaryolar/tutarli-tokenlar.png)

![Gün içindeki taleplerde aynı IP ve kişi için tutarlı token’lar](senaryolar/tutarli-tokenlar.png)

## Müşteri destek

Ad, TCKN, telefon, IBAN ve adres maskelenir. Temsili cevap içindeki isim, IBAN ve telefon aynı kasadan geri çevrilir. Checksum denetimleri biçimi kontrol eder; kimlik veya hesap sahipliğini doğrulamaz.

[Tam boyut](senaryolar/destek-musteri-kaydi.png)

![Sentetik müşteri kaydının maskelenmesi ve örnek destek cevabının geri çevrilmesi](senaryolar/destek-musteri-kaydi.png)

## DevOps / SRE

Bağlantı dizesindeki parola, JWT, IP adresleri ve müşteri adı maskelenirken hata metni ile portlar görünür kalır. Örnek cevap, kasadaki token'larla gerçek değerlerine döndürülür.

[Tam boyut](senaryolar/devops-hata-logu.png)

![DevOps hata logunda parola, JWT, IP ve ismin maskelenmesi](senaryolar/devops-hata-logu.png)
