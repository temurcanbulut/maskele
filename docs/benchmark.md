# Doğruluk benchmark'ı

Bu tür bir aracın başarısı yalnızca yakaladıklarıyla değil, **kaçırdıklarıyla** ölçülür.
`benchmarks/run.py`, etiketli sentetik bir Türkçe korpus üretir ve tespit motorunu
tür bazında ölçer. CI'da bir regresyon kapısıdır: toplam sızıntı %3'ü geçerse ya da negatif
sette tek bir yanlış pozitif çıkarsa testler kırılır.

```bash
python benchmarks/run.py            # özet
python benchmarks/run.py --misses   # kaçan örnekler
python benchmarks/run.py --md       # bu tablo
```

## Sonuçlar (v0.4.2, 2026-10-16)

Sentetik korpus: 3000 örnek, 4556 etiketli değer, tohum 20261015. Negatif set: 38 satır.

| Tür | Örnek | Kesinlik | Duyarlılık | Sızıntı |
|---|---:|---:|---:|---:|
| NAME (sözlükte) | 1044 | 100.0% | 99.3% | 0.7% |
| `SECRET` | 689 | 100.0% | 100.0% | 0.0% |
| `IP` | 377 | 100.0% | 100.0% | 0.0% |
| `EMAIL` | 368 | 100.0% | 100.0% | 0.0% |
| `TCKN` | 284 | 100.0% | 100.0% | 0.0% |
| `PHONE` | 271 | 100.0% | 100.0% | 0.0% |
| NAME (sözlük dışı) | 237 | 100.0% | 89.0% | 12.2% |
| `IBAN` | 198 | 100.0% | 100.0% | 0.0% |
| `API_KEY` | 198 | 100.0% | 99.0% | 0.0% |
| `ADDRESS` | 172 | 100.0% | 100.0% | 0.0% |
| `PLATE` | 168 | 100.0% | 100.0% | 0.0% |
| NAME (küçük harf) | 98 | 100.0% | 66.3% | 35.7% |
| `PASSWORD` | 97 | 100.0% | 100.0% | 0.0% |
| `VKN` | 97 | 100.0% | 100.0% | 0.0% |
| `MAC` | 95 | 100.0% | 100.0% | 0.0% |
| NAME (yabancı) | 84 | 100.0% | 48.8% | 51.2% |
| `CARD` | 79 | 100.0% | 100.0% | 0.0% |
| **Toplam** | 4556 | | | **2.50%** |

Negatif setteki yanlış pozitif: **0 / 38** satır. Bilinçli fazla maskeleme (parola bağlamında belirsiz değerler): 3 / 3.

### Sürümler arası karşılaştırma

v0.3.0 incelemesi benchmark'ın fazla kolay olduğunu doğru tespit etti: hep uzun, rastgele
parolalar üretiyordu ve adres yoktu. v0.4.0'da korpusa zayıf parolalar (letmein,
Galatasaray1905), parola cümleleri, JSON içinde sayı olarak telefon/TCKN, adresler ve yabancı
isimler eklendi. Aynı zorlaştırılmış benchmark eski sürümlere karşı çalıştırıldığında:

| Sürüm | Toplam sızıntı | Parola sızıntısı | Adres sızıntısı | Yanlış pozitif |
|---|---:|---:|---:|---:|
| v0.2.0 | %22,65 (eski korpus) | | | 1 |
| v0.3.0 | **%9,46** | %21,0 | %100 | 0 |
| v0.4.0 | **%2,50** | %0 | %0 | 0 |

v0.3.0 için daha önce yayımlanan %2,05 rakamı, kolay korpusta ölçülmüştü; gerçek değer bu
tablodaki %9,46'dır.

Güncel çalıştırma: [benchmark.json](verification/benchmark.json). Eski sürüm karşılaştırmaları arşivle gelen geliştirme kayıtlarıdır; bu yayın kontrolünde yalnızca mevcut motor yeniden ölçüldü.

## Nasıl okunmalı

- **Sızıntı**, etiketli değerin boşluk dışındaki en az bir karakterinin maskelenmeden kalması demektir.
  Gizlilik açısından asıl önemli sayı budur. Duyarlılık ise doğru *türle* yakalanmayı ölçer.
- **Checksum'lı türler** (TCKN, VKN, IBAN, kart) ve yapısal türler (e-posta, IP, telefon,
  plaka, MAC) bu korpusta sızdırmadı.
- **İsimler en zayıf halka.** Sözlükteki adlar neredeyse tamamen yakalanıyor. Sözlükte olmayan
  adlarda yaklaşık her 8 isimden 1'i, küçük harfle yazılmış isimlerde 3'te 1'i, yabancı
  isimlerde yarısı sızıyor. Arayüzdeki "olası kaçak" işaretlemesi ve tek tıkla maskeleme bu
  boşluğa karşı insan kontrolünü kolaylaştırır; benchmark bu yardımı ölçmez.
- **Bilinçli fazla maskeleme.** Parola bağlamındaki `PASSWORD: "Parola"` gibi belirsiz değerler
  maskelenir; bunlar yanlış pozitif sayılmaz, ayrı raporlanır. Tarama (`scan`) bunları
  varsayılan olarak raporlamaz.
  Bunun ana nedeni bilinçli bir tercih: "Kanal Doğan", "Sabah Güneş" gibi ifadeleri isim
  sanmamak için, sözlükte olmayan bir ad ancak kelime anlamı taşımayan bir soyadla ya da
  "Müşteri:", "Alıcı:", "... adına" gibi bir bağlam ipucuyla kabul ediliyor.

## Sınırlar

- **Korpus sentetik.** Şablonlar gerçek hayattaki log, e-posta ve form metinlerini taklit eder,
  ama gerçek dağılımı temsil etmez. Bu sayılar bir garanti değil, bir göstergedir.
- **İsim listeleri bağımsız seçildi.** Benchmark'taki adlar ve soyadlar tespit sözlüğünden
  kopyalanmadı; bir kısmı sözlükte yok ve sonuçlar bu iki grubu ayrı raporluyor. Yine de
  yaygın Türkçe adlar doğal olarak her iki listede de bulunuyor.
- **Bağlam ipuçları.** Bazı şablonlar "Müşteri", "Alıcı" gibi ipucu kelimeler içeriyor ve bağlam
  kuralları bunlardan yararlanıyor. Bağlamsız şablonlar da bilerek eklendi.
- **Ölçülmeyenler.** Kapı numarası olmayan adresler ("Kadıköy'de, iskelenin yanında"), tek
  kelimelik isimler, serbest metindeki dolaylı tanımlayıcılar ("3. kattaki muhasebeci") ve
  görsellerin içeriği tespit edilmez. Gerçek şirket verisiyle bağımsız bir ölçüm yapılmadı.
