"""Türkçe ad-soyad tespiti.

Serbest metinde isim bulmak regex'le zordur. Yaklaşım: yaygın Türkçe ilk adlar
sözlüğü + ardından gelen büyük harfli soyad. Yalnız başına geçen bir ilk ad
("Can", "Deniz", "Umut" gibi kelimeler de olabilir) maskelenmez; sadece
"Ad Soyad" veya "Ad İkinciAd Soyad" kalıbı maskelenir. Böylece yanlış pozitif
oranı düşük tutulur.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

_FIRST_NAMES = """
abdullah abdulkadir abdurrahman adem adnan ahmet akif alanur ali alp alper alperen altan arda arif
arzu asli aslı asım aybüke aydın ayhan aylin ayse ayşe aysel ayşegül aysu aytaç azra bahar baran
barış başak batuhan bayram belgin belma berat berk berkay berke beril betül beyza bilal bilge
binnur birsen bora buğra bulut burak burcu burhan büşra cafer can canan caner cansu celal cem
cemal cemil cemre cengiz cenk ceren ceyda ceylan cihan cüneyt çağan çağatay çağla çağrı çiğdem
damla deniz derya dilan dilek dilara dursun duygu ebru ece ecem eda edanur ege egemen ekin ekrem
elçin elif elifnur emel emine emir emirhan emre enes engin enis ercan erdal erdem erdoğan eren
ergün erhan erkan erol ersin ertan ertuğrul esin esma esra eylül ezgi faruk fatih fatma fatmanur
fehmi ferhat feride figen filiz fırat fikret fuat funda furkan gamze gizem gökay gökhan göksel
gökçe gönül görkem gül gülay gülşen gülsüm gülten güler güneş gürkan habib hacer hakan halil
halime halit hamza hande hasan hatice havva hayati hayriye hazal hilal hikmet hülya hüseyin ibrahim
ilayda ilhan ilker ilknur irem ismail ismet işil işıl kaan kader kadir kamil kaya kemal kenan kerem
kevser kübra levent leyla mahmut mehmet mehtap melek melike melis meltem mert merve mesut metin
mevlüt mihriban mine mukaddes murat musa mustafa müge nail necati necla nedim nehir nermin nesrin
nevin nihat nilay nilüfer nur nuray nurcan nuri nurullah oğuz oğuzhan okan oktay onur orhan osman
ozan ömer önder özge özgür özlem pelin pınar rabia ramazan rana recep refik reşat rıza rukiye
rümeysa sabri sadık sait salih sami samet savaş seda sedat sefa selahattin selim selin selçuk
selma sema semih semra senem serap serdar serhat serkan sermin sevda sevgi sevil sevim seyfi
sezer sezgin sibel simge sinan sinem songül soner suat sude sultan sunay süleyman şahin şebnem
şenay şengül şerif şeyma şükrü şule tahir talha taner tarık tayfun tayyip tolga tuba tuğba tuğçe
tuncay tunç turan turgay tülay türkan uğur ufuk umut ümit ümran ünal vedat volkan yağız yakup
yasemin yasin yavuz yeliz yeşim yıldız yılmaz yiğit yunus yusuf zafer zehra zekeriya zeki zerrin
zeynep ziya zübeyde
açelya ada adar akasya alaz alin almina arya asel aslı atlas ayaz aybars ayda aysima azra beril
berra birsu buğlem cemre çağan defne demir derin deniz doruk duru ecrin ekin elanur eliz elçin
eslem eylül eymen hiranur ılgın ilkim irmak kerem kuzey lina mavi mina mira miraç nehir nisanur
öykü poyraz ravza rüzgar selin sema serra talya toprak tuana umay uras yaren yiğit zümra
abdi abidin acar adil afet ağah ahu akın akça alara alaz alican alihan alim alişan almila
alparslan alpay alptekin amine anıl arca arel arın arif arslan aslıhan asya ata atakan atilla
ayberk aybike aycan ayça aydan ayla aynur aysun aytekin ayten aziz bade bağış balkan bartu batu
batın bedirhan behiye beren berfin berkan beste betül beyazıt bilgehan billur birce birgül boran
buse caner cansın cavit ceren cevdet cevriye cihangir cüneyd çınar dağhan defne demet demir
demirhan deren derin devrim didem dila doğa doğan doğukan doruk duru durmuş ecrin ediz efe
efecan efsun egemen ekim ela elanur elvan emek emine emirhan engin enver erdi ergin erkut erkin
ersan ertunç esat eser evren eyüp ezel fadime fahri feyza feyyaz fikriye gaye gizem gökalp göktuğ
gönenç gülbahar gülizar güven hakkı halis hamdi hatice haydar helin hilmi hira hümeyra ılgaz
ılayda ımran inci ipek irfan iskender işık kağan kamuran kenan kıvanç koray kutay kutlu kübra
lale lütfi mahir mahmut makbule meriç mertcan metehan mihrimah mirac miray mithat muammer
muhammed muharrem mutlu necdet necmi nermin nesibe nevzat nida nihan nisa nurhan nursel oğulcan
okay oktay olcay orkun ozan öykü özden özkan papatya perihan poyraz rahmi rasim reha remzi
rüya sabahat sabiha saadet sadettin sahra salim sanem sarp sedef selen semiha serdal serra
sertaç seyit sezai simay soykan su suna şafak şenol şeref şirin taha tamer tayfur tekin temur
toprak tuana tunahan turgut tülin uğurcan ulaş umay ümmühan vahit veli vildan yağmur yaman
yaşar yekta yeter yiğitcan yunus zahide zekai zeliha zuhal
"""

UPPER = "A-ZÇĞİÖŞÜÂÎÛ"
LOWER = "a-zçğıöşüâîû"
_WORD_CAP = rf"[{UPPER}][{LOWER}]+"
_WORD_ALLCAP = rf"[{UPPER}]{{2,}}"


def tr_lower(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def fold(s: str) -> str:
    """Sözlük karşılaştırması için: Türkçe küçük harf + ı/i birleştirme.
    "IBRAHIM", "İBRAHİM", "ibrahim" ve "ıbrahım" aynı anahtara iner."""
    return tr_lower(s).replace("ı", "i")


def tr_title(s: str) -> str:
    return " ".join(w[:1].replace("i", "İ").upper() + tr_lower(w[1:]) for w in s.split())


FIRST_NAMES: frozenset[str] = frozenset(fold(w) for w in _FIRST_NAMES.split())

# Aynı zamanda sıradan kelime olan adlar ("Deniz Kuvvetleri", "Umut Var mı?").
# Bunlar için soyadın yaygın soyadlarından biri olması ya da -oğlu ile bitmesi gerekir.
AMBIGUOUS = frozenset(
    fold(w)
    for w in """
Can Deniz Umut Ümit Barış Nur Gül Güneş Bahar Bulut Kaya Yılmaz Savaş Zafer Sultan Yıldız
Ekin Nehir Ufuk Kader Sevgi Sevda Ege Bora Yavuz Alp Mert Dilek Ceylan Damla Ezgi Simge Su Esin
Pınar Ozan Selin Toprak Kuzey Rüzgar Mavi Derin Duru Doruk Ada Ayaz Demir Irmak Poyraz Eylül
Defne Lale Papatya Yağmur Şafak Doğa Gökçe Inci Ipek Ay Yıldırım Kartal Aslan Arslan Kurt Er
""".split()
)

COMMON_SURNAMES = frozenset(
    fold(w)
    for w in """
Yılmaz Kaya Demir Şahin Çelik Yıldız Yıldırım Öztürk Aydın Özdemir Arslan Doğan Kılıç Aslan
Çetin Kara Koç Kurt Özkan Şimşek Polat Korkmaz Özcan Çakır Erdoğan Yavuz Can Acar Şen Aktaş
Güler Yalçın Güneş Bozkurt Bulut Keskin Ünal Turan Gül Özer Işık Kaplan Avcı Sarı Tekin Taş
Köse Yüksel Ateş Aksoy Yiğit Uçar Altun Karaca Çiftçi Kaçar Tunç Kurtuluş Akın Duman Bayram
Erdem Tuncer Coşkun Uysal Durmaz Toprak Akbulut Sezer Bilgin Karakaya Kocabaş Demirci Ekinci
Esen Özgür Akgül Bayrak Altıntaş Yazıcı Özbek Kahraman Eren Çınar Aydoğan Akyüz Karataş Tekin
Ay Soylu Bilgiç Gündoğdu Kurtoğlu Akdeniz Uzun Kalkan Alkan Önal Ergin Sevim Topal Dinç Baysal
Başpınar Karaoğlu Atalay Bilgili Ekşi Güngör Kocaman Oral Özkök Sönmez Tan Tuna Ulusoy Yazgan
Acar Ağca Akbaş Akçay Akdağ Akgün Akkaya Akkuş Aksu Aktürk Alp Altay Altıntaş Arı Arıkan Aslantaş
Atasoy Avşar Aydemir Aygün Aytekin Baran Barut Başaran Batur Bayraktar Bektaş Bilgin Bingöl Bozdağ
Bulut Cengiz Ceylan Coşar Çakmak Çam Çevik Çiçek Dağ Demirel Demirtaş Dinçer Doğru Duran Durmuş
Ekici Elmas Erbaş Erdal Erkan Ersoy Ertürk Eser Gök Gökçe Göktaş Gönül Gümüş Gündüz Güneş Gür
Gürbüz Güven Işıklı Kalaycı Kandemir Kaplan Karabulut Karadağ Karadeniz Karagöz Karakuş Karaman
Kartal Kaçmaz Keleş Kılınç Kınık Koca Kocabıyık Korkut Kuş Kutlu Metin Oğuz Okur Orhan Önder
Özbay Özçelik Özden Özgen Özkaya Özmen Öztekin Özyurt Parlak Pehlivan Polater Sağlam Sarıkaya
Savaş Sevinç Seyhan Solmaz Sözen Şeker Şener Tanrıverdi Taşdemir Taşkın Tatlı Temel Tezcan Turgut
Türkmen Uçan Uğurlu Uysal Yalın Yaman Yavaş Yaşar Yazar Yener Yeşil Yiğit Yörük Yüce Yücel Zengin
""".split()
)

_ALLOWED_SUFFIX = ("oğlu", "gil")

# Türkçe soyadlarında sık görülen bileşik ekler: Kara+dağ, Sarı+kaya, Taş+demir, Öz+türk, Ak+soy
_SURNAME_MORPHEMES = tuple(
    fold(x) for x in ("oğlu", "dağ", "kaya", "demir", "taş", "soy", "türk", "gün", "yüz", "baş", "göz", "kurt")
)

# Aynı zamanda sıradan kelime olan soyadlar: "Kanal Doğan", "Sabah Güneş", "Hazır Beton Kaya".
# Sözlükte olmayan bir kelimeyle birleştiklerinde isim sayılmazlar.
WORD_SURNAMES = frozenset(
    fold(w)
    for w in """
Kaya Demir Doğan Yıldırım Yıldız Güneş Bulut Taş Toprak Kara Akdeniz Karadeniz Ateş Gül Işık Kurt
Aslan Arslan Kartal Çiçek Elmas Altın Altun Gümüş Sarı Yeşil Uzun Temel Tatlı Parlak Güven Sağlam
Zengin Yaman Doğru Savaş Baran Yazar Metin Kuş Dağ Gök Çam Çelik Deniz Ay Tan Tuna Önder Duman
Bayrak Bayram Keskin Kaplan Avcı Koç Kılıç Şeker Barut Coşkun Kutlu Erdem Uçar Uysal Yavuz Yüce
Yalın Yavaş Bozkurt Çakır Çakmak Aksu Sevinç Solmaz Güler Esen Ekinci Duran Okur Kalkan Kocaman
""".split()
)


def surname_like(word: str) -> bool:
    w = fold(word)
    return w in COMMON_SURNAMES or (len(w) >= 6 and w.endswith(_SURNAME_MORPHEMES))


def strong_surname(word: str) -> bool:
    """Kelime anlamı taşımayan, güçlü soyad kanıtı: Öztürk, Karadağ, Yılmaz, Kurtoğlu."""
    return surname_like(word) and fold(word) not in WORD_SURNAMES


# İsimden sonra gelen unvanlar: kırpılır, isim yine maskelenir ("Ali Yılmaz Bey")
_TITLES = frozenset(
    fold(w)
    for w in """
Bey Hanım Hoca Abi Abla Amca Teyze Usta Müdür Müdürü Şef
""".split()
)

# Kalıbı yer/kurum adına çeviren kelimeler: eşleşme tamamen atlanır
# ("Mehmet Akif Ersoy Üniversitesi", "Ali Rıza Caddesi")
_PLACES = frozenset(
    fold(w)
    for w in """
Mahallesi Mah Caddesi Cad Sokak Sokağı Sk Bulvarı Blv Meydanı Camii Parkı Köprüsü Hastanesi
Okulu Lisesi Üniversitesi Fakültesi Kampüsü İlkokulu Ortaokulu Stadyumu Havalimanı Tüneli
Holding Yazılım Teknoloji Bilişim Ltd Şti AŞ Grup Group Inc Vakfı Derneği Kütüphanesi Salonu
Fabrikası Fabrika Firması Firma Şirketi Oteli Otel Hotel Restoran Restaurant Kafe Cafe Paketi Paket
Lojistik İnşaat Gıda Market Marketi Turizm Tekstil Medya Yayın Yayınları Spor Kulübü Sanayi Ticaret
Enerji Mağazası Mağazaları Plaza Rezidans Sitesi Apartmanı Kulesi Köyü Mahalle İlçesi Bölgesi
Dağları Dağı Gölü Nehri Çayı Adası Burnu Vadisi Kalesi Sarayı Müzesi Projesi Operasyonu Tatbikatı
""".split()
)

_NEXT_WORD = re.compile(rf"[ \t]+([{UPPER}{LOWER}]+)")

# Bu unvanlardan sonra gelen büyük harfli 1-3 kelime, sözlükte olmasa da addır
_HONORIFIC = re.compile(
    rf"(?<![\w])(?:Sayın|Sn\.|Sevgili|Bay|Bayan|Dr\.|Doç\.|Prof\.|Av\.|Op\.|Uzm\.|Mr\.|Mrs\.|Ms\.)"
    rf"[ \t]+((?:Dr\.[ \t]+)?{_WORD_CAP}(?:[ \t]+{_WORD_CAP}){{0,2}})(?![\w])"
)

# Bir ismin soluna eklenmeyecek büyük harfli kelimeler (cümle başı, unvan, etiket)
_NOT_LEFT = (
    frozenset(
        fold(w)
        for w in """
Müşteri Merhaba Sayın Sevgili Değerli Bay Bayan Kullanıcı Personel Çalışan Yönetici Müdür Hasta
Öğrenci Öğretmen Hoca Bugün Yarın Dün Ve İle Ama Fakat Not Konu Kimden Kime Ad Adı Soyad Soyadı
İsim Gönderen Alıcı Teslim Sipariş Kargo Hata Uyarı Bilgi Ayrıca Sonra Önce Lütfen Teşekkürler
Saygılarımla Selam Selamlar Günaydın İyi Ekip Takım Firma Şirket Proje Toplantı Rapor Talep Eğer
Hello Hi Dear Customer User From To Subject Name Contact Owner Assignee Reporter Author
""".split()
    )
    | _TITLES
    | _PLACES
)
# Soyad gibi görünen bir kelimeden önce gelse de ad olmayan yaygın kelimeler
_NOT_FIRST = frozenset(
    fold(w)
    for w in """
Büyük Küçük Yeni Eski Kara Ak Mavi Kırmızı Yeşil Sarı Beyaz Siyah Altın Gümüş Demir Taş Yüksek
Alçak Uzun Kısa Genel Özel Milli Ulusal Türk Türkiye Ankara İstanbul İzmir Bursa Antalya Konya
Adana Kuzey Güney Doğu Batı Orta Merkez Şube Bölge Sistem Sunucu Servis Uygulama Veri Ağ Kod Test
Sürüm Versiyon Release Build Error Warning Info Debug Proje Modül Paket Hazır Global Kanal
Sabah Akşam Öğle Gece Kurumsal Bireysel Ticari Resmi Dijital Akıllı Mobil Online Kafka Consumer
Producer Service Server Client Kurum Kurumu Bakanlığı Başkanlığı Müdürlüğü Belediyesi Valiliği
""".split()
)
_PREV_WORD = re.compile(rf"(?<![\w])([{UPPER}][{LOWER}]+)[ \t]+$")

_RX_CAP = re.compile(rf"(?<![\w])({_WORD_CAP})((?:[ \t]+{_WORD_CAP}){{1,2}})(?![\w])")
_RX_ALLCAP = re.compile(rf"(?<![\w])({_WORD_ALLCAP})((?:[ \t]+{_WORD_ALLCAP}){{1,2}})(?![\w])")


_RX_LOWER = re.compile(rf"(?<![\w])([{LOWER}]{{3,}})((?:[ \t]+[{LOWER}]{{2,}}){{1,2}})(?![\w])")


# Türkçe yazımda özel adlar ek alırken kesme işareti kullanır ("Ahmet'e"). Büyük harfle
# başlayıp kesme işaretsiz hâl/çoğul eki taşıyan kelime büyük ihtimalle sıradan bir isimdir
# (cümle başındaki "Toplantıya", "Müşterinin", "Raporda").
_INFLECTED_LONG = (
    "dan",
    "den",
    "tan",
    "ten",
    "nın",
    "nin",
    "nun",
    "nün",
    "yla",
    "yle",
    "ları",
    "leri",
    "lar",
    "ler",
    "daki",
    "deki",
    "taki",
    "teki",
    "ndan",
    "nden",
)
_INFLECTED_SHORT = ("ya", "ye", "da", "de", "ta", "te", "yı", "yi", "yu", "yü", "na", "ne")


def looks_inflected(word: str) -> bool:
    w = tr_lower(word)
    if "'" in word or "’" in word:
        return False
    return len(w) >= 7 and w.endswith(_INFLECTED_LONG + _INFLECTED_SHORT)


def _lowercase_names(text: str, names: frozenset[str]) -> Iterator[tuple[int, int, str]]:
    """küçük harfli "zeynep kaya", "ali veli yıldırım". Yalnızca belirsiz olmayan bir ad +
    soyad gibi bir kelime (ya da ikinci bir ad + soyad) kabul edilir; günlük kelimelerle
    karışma riski bu yüzden düşük tutulur."""
    pos = 0
    while True:
        m = _RX_LOWER.search(text, pos)
        if not m:
            return
        pos = m.end(1)
        first = fold(m.group(1))
        if first not in names or first in AMBIGUOUS:
            continue
        rest = m.group(2).split()
        take = 0
        if surname_like(rest[0]):
            take = 1
        elif len(rest) > 1 and fold(rest[0]) in names and surname_like(rest[1]):
            take = 2
        if not take:
            continue
        end = m.start(2)
        for w in rest[:take]:
            end = text.index(w, end) + len(w)
        pos = end
        yield m.start(1), end, text[m.start(1) : end]


_CAPSEQ = rf"((?:{_WORD_CAP}|{_WORD_ALLCAP})(?:[ \t]+(?:{_WORD_CAP}|{_WORD_ALLCAP})){{1,2}})"
# Bağlam ipuçları: bu kalıplar arasındaki büyük harfli 2-3 kelime, sözlükte olmasa da addır
_CTX_BEFORE = re.compile(
    r"(?i:(?<![\w])(?:müşteri|alıcı|gönderen|hesap sahibi|sahibi|ben|kime|kimden|personel|hasta|"
    r"öğrenci|çalışan|yetkili|ilgili kişi|sorumlu|ad soyad|adı soyadı|isim|customer|contact|"
    r"name|from|to|assignee|reporter|owner))[ \t]*[:=-]?[ \t]*" + _CAPSEQ + r"(?![\w])"
)
_CTX_AFTER = re.compile(r"(?<![\w])" + _CAPSEQ + r"[ \t]+(?:adlı|isimli|adına|adındaki|namına)(?![\w])")


def _context_names(text: str) -> Iterator[tuple[int, int, str]]:
    for rx in (_CTX_BEFORE, _CTX_AFTER):
        for m in rx.finditer(text):
            words = m.group(1).split()
            # Baştaki etiket kelimelerini at: "Kargo Saniye Ilgaz adına" → "Saniye Ilgaz"
            while words and fold(words[0]) in _NOT_LEFT | _NOT_FIRST:
                words.pop(0)
            while words and fold(words[-1]) in _TITLES | _PLACES:
                words.pop()
            if len(words) < 2 or any(fold(w) in _PLACES for w in words):
                continue
            start = text.index(words[0], m.start(1))
            end = start
            for w in words:
                end = text.index(w, end) + len(w)
            yield start, end, text[start:end]


def find_names(text: str, extra_first_names: Iterable[str] = ()) -> Iterator[tuple[int, int, str]]:
    """(başlangıç, bitiş, değer) döndürür."""
    extra = {fold(n) for n in extra_first_names}
    names = FIRST_NAMES | extra
    for m in _HONORIFIC.finditer(text):
        words = m.group(1).split()
        while words and fold(words[-1]) in _TITLES | _PLACES:
            words.pop()
        if words:
            end = m.start(1)
            for w in words:
                end = text.index(w, end) + len(w)
            yield m.start(1), end, text[m.start(1) : end]
    yield from _context_names(text)
    yield from _lowercase_names(text, names)
    for rx in (_RX_CAP, _RX_ALLCAP):
        pos = 0
        while True:
            m = rx.search(text, pos)
            if not m:
                break
            # Bir sonraki aramayı bu eşleşmenin ikinci kelimesinden başlat:
            # "Merhaba İsmail Kaya" → "Merhaba" ad değilse "İsmail"den tekrar dene.
            pos = m.end(1)
            first = fold(m.group(1))
            rest = m.group(2).split()
            if first not in names:
                # Sözlükte olmayan ad + yaygın/biçimsel soyad: "Eymen Çelik", "Şükran Karadağ".
                # Etiket ve yer kelimeleriyle başlayanları ele ("Müşteri Kaya", "Ankara Demir").
                if first in _NOT_LEFT or first in _NOT_FIRST or not strong_surname(rest[0]):
                    continue
                rest = rest[:1]
            elif first in AMBIGUOUS and first not in extra:
                # "Deniz Kuvvetleri" değil "Deniz Yılmaz": kalan kelimelerden biri soyad gibi olmalı
                if not any(surname_like(w) or fold(w).endswith(_ALLOWED_SUFFIX) for w in rest):
                    continue
            nxt = _NEXT_WORD.match(text, m.end())
            if any(fold(w) in _PLACES for w in rest) or (nxt and fold(nxt.group(1)) in _PLACES):
                continue
            while rest and fold(rest[-1]) in _TITLES:
                rest.pop()
            if not rest:
                continue
            end = m.start(2)
            for w in rest:
                end = text.index(w, end) + len(w)
            pos = end
            start = m.start(1)
            # Sözlükte olmayan ilk adı da kapsa: "Temur Can Bulut" → "Can Bulut" değil hepsi
            prev = _PREV_WORD.search(text, 0, start) if rx is _RX_CAP else None
            # Kesme işaretsiz hâl eki almış kelime isme katılmaz ("Toplantıya Orkun Tekeli")
            if (
                prev
                and not looks_inflected(prev.group(1))
                and fold(prev.group(1)) not in _NOT_LEFT | _NOT_FIRST
                and text[prev.end(1) : start].strip(" \t") == ""
            ):
                start = prev.start(1)
            yield start, end, text[start:end]


_SUSPECT = re.compile(
    rf"(?<![\w])((?:{_WORD_CAP}|{_WORD_ALLCAP})(?:[ \t]+(?:{_WORD_CAP}|{_WORD_ALLCAP})){{1,2}})(?![\w])"
)


def suspects(text: str, covered: list[tuple[int, int]]) -> list[tuple[int, int, str]]:
    """Maskelenmemiş ama isim olabilecek büyük harfli 2-3 kelimelik diziler.

    Tespit motorunun kararı değildir; kullanıcıya "kontrol et" denecek adaylardır.
    Etiket/yer/kurum kelimelerinden oluşanlar ve zaten maskelenen aralıklar elenir.
    """
    out = []
    stop = _NOT_LEFT | _NOT_FIRST | _PLACES | _TITLES
    for m in _SUSPECT.finditer(text):
        words = m.group(1).split()
        while words and (fold(words[0]) in stop or looks_inflected(words[0])):
            words.pop(0)
        while words and fold(words[-1]) in stop:
            words.pop()
        if len(words) < 2:
            continue
        start = text.index(words[0], m.start(1))
        end = start
        for w in words:
            end = text.index(w, end) + len(w)
        if any(start < e and s < end for s, e in covered):
            continue
        out.append((start, end, text[start:end]))
    return out
