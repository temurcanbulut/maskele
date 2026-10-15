# Katkı rehberi

Katkıların için teşekkürler. Küçük düzeltmeler için doğrudan PR açabilirsin; yeni bir
veri türü ya da büyük bir değişiklik için önce bir issue açıp konuşalım.

## Kurulum

```bash
git clone https://github.com/temurcanbulut/maskele && cd maskele
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest && ruff check .
```

## Yeni bir veri türü eklemek

1. `maskele/detectors.py` içine deseni ve mümkünse bir **doğrulayıcı** (checksum, aralık
   kontrolü, bağlam) ekle. Doğrulayıcısı olmayan desenler kabul edilir ama yanlış pozitif
   oranının neden düşük olduğunu PR'da açıkla.
2. Türü `ALL_KINDS` ve `KIND_INFO`'ya, gerekirse `core.normalize`'a ekle.
3. `tests/` altına hem yakalanması gereken hem de **yakalanmaması gereken** örnekler yaz.
   Gerçek kişisel veri kullanma; geçerli checksum'lı değerleri testte üret.
4. `README.md`'deki tür tablosunu ve `CHANGELOG.md`'yi güncelle.

## İlkeler

- Çekirdek sıfır bağımlılıklı kalır. İsteğe bağlı özellikler `extras` arkasına girer.
- Gerçek değer hiçbir log'a, rapora ya da hata mesajına yazılmaz.
- Yanlış pozitif, yanlış negatiften daha az zararlıdır ama ikisi de hatadır; test ekle.
- Kullanıcıya dönük metinler Türkçe, kod ve tanımlayıcılar İngilizce.
