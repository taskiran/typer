# Typer — SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Bertan Taskiran.
"""Toplantı transkripti — Zoom'un yerel kaydından, konuşmacı adlarıyla.

KONUŞMACI AYRIŞTIRMA BURADA YAPILMAZ, ÇÜNKÜ GEREKMEZ. Zoom'un masaüstü
istemcisinde "Record a separate audio file of each participant" ayarı
açıkken yerel kayıt, kayıt klasörünün altındaki `Audio Record/` içine her
katılımcı için AYRI bir ses dosyası bırakır ve adını dosya adına yazar:

    audio_only_16778242_Bertan_Taskiran.m4a

Yani her dosya tanımı gereği tek kişidir. Bir diarization modeli (pyannote
gibi) burada yalnızca hata kaynağı olurdu: tahmin ettiği şeyi Zoom zaten
kesin olarak biliyor, üstelik "SPEAKER_01" yerine gerçek adıyla.

Ses hiçbir yere gönderilmez; dikte tarafıyla aynı yerel model, aynı süreç.
"""
import re
import sys
import time
from pathlib import Path

from typer_engine.bus import log
from typer_engine.config import CFG
from typer_engine.stt import BACKEND, transcribe_file, warm

# Zoom m4a yazar. Ötekiler elle beslenen kayıtlar için — dosyayı PyAV
# çözüyor, yani kabul etmemek için bir sebep yok.
_SES = {".m4a", ".mp4", ".wav", ".mp3", ".m4v", ".aac", ".flac", ".ogg"}
# Görüntü taşıyan kapsayıcılar. Aynı klasörde bir ses dosyası varsa
# bunlar atlanır — bkz. ses_dosyalari.
_GORUNTU = {".mp4", ".m4v"}

# audio_only_<katilimci id>_<Gorunen_Ad>
_AD = re.compile(r"^audio_only_\d+_(.+)$", re.I)

# Zoom'un KARIŞIK ses/görüntü dosyası: audio<toplantı kimliği>. Bu
# bilgisayardaki gerçek bir kayıtta böyle çıktı (audio1990253058.m4a,
# video1990253058.mp4); "audio_only" adını hiç taşımadı.
_KARISIK = re.compile(r"^(audio|video)(_only)?_?\d*$", re.I)

# Katılımcı başına dosyanın öteki adlandırması: audio<AdSoyad><sayılar>.
# Zoom sürümüne göre değişiyor. Bu biçim bu bilgisayarda henüz görülmedi;
# tanınıyor, çünkü tanımamanın bedeli transkriptte konuşmacı adı olarak
# "audioBertanTaskiran21990253058" yazmasıdır.
_AD2 = re.compile(r"^audio([^\d_].*?)\d+$", re.I)
_BUYUK_HARF_ONU = re.compile(r"(?<=[a-zçğıöşü])(?=[A-ZÇĞİÖŞÜ])")

# Aynı konuşmacının arka arkaya gelen parçaları tek paragrafta toplanır.
# Bundan uzun bir sessizlikten sonrası yeni bir söz sayılır: aradan bir
# dakika geçmişken iki cümleyi aynı paragrafa koymak, okuyanı konuşmanın
# kesintisiz sürdüğüne inandırır.
_ARA = 8.0


def _katilimci(p: Path) -> str:
    """Dosya adından görünen ad. Çıkaramazsa dosya adının kendisi."""
    kok = p.stem
    m = _AD.match(kok)
    if m:
        return m.group(1).replace("_", " ").strip() or kok
    if _KARISIK.match(kok):
        return "Karışık ses"
    m = _AD2.match(kok)
    if m:
        # Boşluksuz yazılmış ad: "ÇağatayGülten" -> "Çağatay Gülten"
        ad = _BUYUK_HARF_ONU.sub(" ", m.group(1))
        return ad.replace("_", " ").strip() or kok
    return kok.replace("_", " ").strip() or kok


def _sure(p: Path) -> float:
    """Saniye. Okunamazsa 0 — çağıran bunu uyarı olarak kullanır."""
    try:
        import av
        with av.open(str(p)) as c:
            if c.duration:
                return float(c.duration) / av.time_base
    except Exception:
        pass
    return 0.0


def _saat(sn: float) -> str:
    sn = max(0, int(sn))
    return f"{sn // 3600:02d}:{(sn % 3600) // 60:02d}:{sn % 60:02d}"


def _sureli(sn: float) -> str:
    dk = int(sn // 60)
    if dk < 60:
        return f"{dk} dk"
    return f"{dk // 60} sa {dk % 60} dk"


# --------------------------------------------------------------- kayıt bulma

def _belgeler() -> Path | None:
    """İşletim sisteminin GERÇEK Belgeler klasörü (yalnızca Windows).

    Adı sabit yazmak sahada yanıldı: OneDrive, Belgeler'i hesabın diline
    göre adlandırıyor ve bu bilgisayarda klasör `OneDrive/Dokumente`,
    yani Almanca. Zoom kayıtları oraya yazdı; biz "Documents" ile
    "Belgeler"e bakıyorduk ve izleyici hiçbir şey bulamadan sustu.
    Windows'a sormak her dilde ve her taşınmış klasörde doğru cevabı
    verir.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        # CSIDL_PERSONAL (5): Belgeler — OneDrive'a taşındıysa taşındığı yer
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:
            return Path(buf.value) if buf.value else None
    except Exception:
        pass
    return None


def _zoom_kokleri() -> list[Path]:
    """Zoom'un yerel kayıtları nereye koyabileceği yerler.

    Önce Windows'un söylediği Belgeler klasörü, sonra bilinen adlar. Zoom
    varsayılan olarak Belgeler/Zoom'a yazar ve Belgeler taşınınca onu
    takip eder. Zoom ayarlarından başka bir klasör seçildiyse onu
    bilemeyiz — Zoom bu ayarı şifreli tutuyor; o durumda "meetings_dir".
    """
    elle = str(CFG.get("meetings_dir") or "").strip()
    if elle:
        # Elle verilmişse ARAMA YAPILMAZ. Kullanıcı klasörü söylediyse
        # başka bir yerde bulunan bir kayıt sürpriz olurdu.
        k = Path(elle).expanduser()
        return [k] if k.is_dir() else []
    ev = Path.home()
    belgeler = _belgeler()
    adaylar = ([belgeler / "Zoom"] if belgeler else []) + [
        ev / "Documents" / "Zoom",
        ev / "OneDrive" / "Documents" / "Zoom",
        ev / "Belgeler" / "Zoom",
        ev / "OneDrive" / "Belgeler" / "Zoom"]
    # Aynı klasör iki yoldan gelebilir (Windows'un cevabı çoğu zaman
    # listedekilerden biridir); iki kez taramak her kaydı iki kez bulurdu.
    return list(dict.fromkeys(k for k in adaylar if k.is_dir()))


def _kayit_mi(klasor: Path) -> bool:
    return (klasor / "Audio Record").is_dir() or any(
        p.suffix.lower() in _SES for p in klasor.glob("*"))


def kayitlar(kok: Path | None = None) -> list[Path]:
    """Bulunan bütün toplantı kayıtları, yeniden eskiye."""
    kokler = [kok] if kok else _zoom_kokleri()
    bulunan = []
    for k in kokler:
        if not k or not k.is_dir():
            continue
        if _kayit_mi(k):
            bulunan.append(k)          # doğrudan bir kaydın kendisi verildi
            continue
        bulunan += [d for d in k.iterdir() if d.is_dir() and _kayit_mi(d)]
    return sorted(set(bulunan), key=lambda d: d.stat().st_mtime, reverse=True)


def ses_dosyalari(kayit: Path) -> list[tuple[str, Path]]:
    """[(konuşmacı adı, dosya)] — katılımcı başına ayrı dosyalar.

    `Audio Record/` varsa YALNIZCA oradan okunur: kayıt klasörünün kökünde
    duran `audio_only.m4a` herkesin karıştığı tek kanaldır ve onu da
    çevirmek, her cümlenin transkripte iki kez düşmesi demektir.
    """
    ayri = _ayri_klasor(kayit)
    kaynak = ayri if ayri is not None else kayit
    dosyalar = sorted(p for p in kaynak.iterdir()
                      if p.is_file() and p.suffix.lower() in _SES)
    # AYNI SES İKİ KEZ OLMASIN. Katılımcı başına dosya yoksa Zoom köke
    # bir ses (audio<id>.m4a) ve bir görüntü (video<id>.mp4) bırakıyor ve
    # ikisinde de aynı karışık ses var. Görüntüyü de çevirmek, her cümleyi
    # transkripte iki ayrı "konuşmacı" adıyla yazdırırdı. Gerçek bir
    # kayıtta görüldü. Ses dosyası varsa görüntüler atlanır.
    if any(p.suffix.lower() not in _GORUNTU for p in dosyalar):
        dosyalar = [p for p in dosyalar if p.suffix.lower() not in _GORUNTU]
    return [(_katilimci(p), p) for p in dosyalar]


def _ayri_klasor(kayit: Path) -> Path | None:
    """Katılımcı başına seslerin durduğu alt klasör; yoksa None.

    Adı "Audio Record", ama Zoom klasör adlarını arayüz diline göre
    çevirebiliyor (bu bilgisayarda toplantı klasörü "Zoom Toplantısı"
    adını taşıyor). O yüzden ad tutmazsa İÇERİĞE bakılır: bir kayıt
    klasöründe ses dosyası taşıyan tek alt klasör budur.
    """
    tam = kayit / "Audio Record"
    if tam.is_dir():
        return tam
    for d in sorted(kayit.iterdir()):
        if d.is_dir() and any(p.is_file() and p.suffix.lower() in _SES
                              for p in d.iterdir()):
            return d
    return None


# ------------------------------------------------------------------ çeviri

def _sabit_dil() -> str | None:
    """Kullanıcı dili SABİTLEDİYSE o, yoksa None (tespit edilecek).

    typer.json'daki "language" üç şekilde okunur, dikte tarafındakiyle
    aynı anlamda: düz bir metin ("tr") sabitlemedir, tek elemanlı bir
    liste de öyle, çok elemanlı liste ise "şunlar arasından seç" demektir
    ve bu durumda tespit çalışır.

    BİR TOPLANTIYA DİL DAYATMAK PAHALI BİR HATA. Whisper'a yanlış dili
    verirsen boş dönmez — söyleneni O DİLE ÇEVİRİR. Sahada ölçüldü:
    İngilizce bir toplantı "tr" zorlanınca transkripte Türkçe olarak
    düştü, yani kayıt artık kimsenin söylemediği cümlelerden oluşuyordu.
    Bir transkriptin tek işi söyleneni yazmaktır.
    """
    d = CFG.get("language")
    if isinstance(d, str):
        return d.strip() or None
    if isinstance(d, (list, tuple)) and len(d) == 1:
        return str(d[0]).strip("<|>").strip() or None
    return None


def _izinli(bulunan: str | None) -> str | None:
    """Tespit edilen dili, ayardaki listeye göre kabul et ya da düzelt."""
    d = CFG.get("language")
    if not isinstance(d, (list, tuple)) or len(d) < 2:
        return bulunan
    liste = [str(x).strip("<|>").strip() for x in d if str(x).strip()]
    if bulunan in liste:
        return bulunan
    log(f"[toplantı] tespit edilen dil ({bulunan}) ayardaki listede yok "
        f"{liste} — {liste[0]} kullanılıyor")
    return liste[0]


def cevir(kayit: Path, dil: str | None = None, bekle=None,
          ilerleme=None) -> dict:
    """Kaydı çevir ve {konuşmacılar, sozler, sure...} döndür.

    ilerleme(oran) 0..1 arası ilerlemeyi bildirir. Oran bütün dosyaların
    TOPLAM süresine göre hesaplanır, dosya sayısına göre değil: iki
    kişilik bir toplantıda biri beş dakika diğeri kırk dakika
    konuşabiliyor ve "1/2 dosya bitti" bunu %50 diye gösterirdi.

    bekle() her dosyadan ÖNCE çağrılır ve dikte sürerken orada bloklar.
    Model tek işçiyle çalışıyor: bir toplantı dosyası çevrilirken tuşa
    basılırsa dikte onun bitmesini beklerdi. Dosya sınırında durmak bu
    beklemeyi dakikalardan saniyelere indiriyor — kayıt arka plandaki
    iştir, dikte ise kullanıcının parmağının ucundaki.
    """
    dosyalar = ses_dosyalari(kayit)
    if not dosyalar:
        raise FileNotFoundError(
            f"{kayit} içinde ses dosyası yok. Zoom ayarlarında "
            f"\"Record a separate audio file of each participant\" açık mı?")

    dil = dil or _sabit_dil()
    warm()
    log(f"[toplantı] {kayit.name} — {len(dosyalar)} ses dosyası, dil "
        f"{dil or 'tespit edilecek'}, model {BACKEND['model']} "
        f"({BACKEND['device']}/{BACKEND['compute']})")

    sureler = {ad: _sure(p) for ad, p in dosyalar}
    en_uzun = max(sureler.values(), default=0.0)

    # EN ÇOK KONUŞULAN DOSYA ÖNCE. Dil bir kez tespit edilip ötekilere
    # sabitleniyor, ve tespit ne kadar çok konuşma duyarsa o kadar isabetli
    # olur. Sessizlik AAC'de neredeyse yer kaplamadığı için dosya boyutu,
    # o kişinin ne kadar konuştuğunun ucuz ve iyi bir ölçüsü.
    sira = sorted(dosyalar, key=lambda x: x[1].stat().st_size, reverse=True)

    toplam = sum(sureler.values()) or 1.0
    bitmis = 0.0

    sozler = []
    sayim = {}
    for ad, p in sira:
        if bekle is not None:
            bekle()
        adim = None
        if ilerleme is not None:
            def adim(son, _b=bitmis):
                ilerleme(min(1.0, (_b + son) / toplam))
        # KATILIMCI BAŞINA DOSYALAR TOPLANTI BOYUNCA SÜRER ve konuşmadığın
        # her an sessizliktir. VAD süzgeci burada iki şey birden yapar:
        # sessizliği modele hiç göstermeyerek çeviriyi kat kat hızlandırır,
        # ve Whisper'ın sessizliğe uydurduğu hayalet cümleleri baştan
        # keser. (Diktede aynı süzgeç bir şey vermiyordu — orada kesintisiz
        # konuşma var, atılacak sessizlik yok.)
        t0 = time.perf_counter()
        parcalar, kullanilan = transcribe_file(p, language=dil, vad=True,
                                               ilerleme=adim)
        gecen = time.perf_counter() - t0
        bitmis += sureler.get(ad, 0.0)
        if ilerleme is not None:
            ilerleme(min(1.0, bitmis / toplam))
        if dil is None:
            dil = _izinli(kullanilan)
            log(f"[toplantı] dil: {dil} ({ad} dosyasından tespit edildi, "
                f"kalan dosyalara da bu uygulanacak)")
        for bas, bit, metin in parcalar:
            sozler.append((bas, bit, ad, metin))
        sayim[ad] = len(parcalar)
        log(f"[toplantı] {ad}: {_sureli(sureler[ad])} ses -> "
            f"{len(parcalar)} parça, {gecen:.0f} sn")
        if en_uzun and sureler[ad] and en_uzun - sureler[ad] > 5:
            # Geç katılan birinin dosyası kısa başlar ve NEREDEN başladığı
            # dosyada yazmaz. Zaman damgaları o kişide kayabilir; sessizce
            # kaymasındansa söylensin.
            log(f"[toplantı] uyarı: {ad} dosyası en uzun kayıttan "
                f"{_sureli(en_uzun - sureler[ad])} kısa — bu kişi sonradan "
                f"katıldıysa zaman damgaları kayabilir")

    sozler.sort(key=lambda s: (s[0], s[2]))
    return {"kayit": kayit, "sozler": sozler, "sayim": sayim,
            "sure": en_uzun, "dil": dil,
            "konusmacilar": [ad for ad, _ in dosyalar]}


def _paragraflar(sozler) -> list[tuple[float, str, str]]:
    """Aynı kişinin peş peşe sözlerini tek paragrafta topla."""
    cikti = []
    for bas, bit, ad, metin in sozler:
        if cikti and cikti[-1][1] == ad and bas - cikti[-1][3] <= _ARA:
            onceki = cikti[-1]
            cikti[-1] = (onceki[0], ad, (onceki[2] + " " + metin).strip(), bit)
        else:
            cikti.append((bas, ad, metin, bit))
    return [(b, ad, m) for b, ad, m, _ in cikti]


def markdown(sonuc: dict) -> str:
    kayit = sonuc["kayit"]
    satir = [f"# {kayit.name}", ""]
    ne_zaman = time.strftime("%d.%m.%Y %H:%M",
                             time.localtime(kayit.stat().st_mtime))
    satir.append(f"- **Kayıt:** {ne_zaman}")
    if sonuc["sure"]:
        satir.append(f"- **Süre:** {_sureli(sonuc['sure'])}")
    kisiler = ", ".join(f"{ad} ({sonuc['sayim'].get(ad, 0)} parça)"
                        for ad in sonuc["konusmacilar"])
    satir.append(f"- **Konuşmacılar:** {kisiler}")
    if sonuc.get("dil"):
        satir.append(f"- **Dil:** {sonuc['dil']}")
    satir.append(f"- **Kaynak:** `{kayit}`")
    satir.append(f"- **Çeviri:** Typer, {BACKEND['model']} "
                 f"({BACKEND['device']}), yerel")
    satir += ["", "---", ""]

    paragraflar = _paragraflar(sonuc["sozler"])
    if not paragraflar:
        satir.append("_Kayıtta konuşma bulunamadı._")
    for bas, ad, metin in paragraflar:
        satir.append(f"**{_saat(bas)} · {ad}**")
        satir.append("")
        satir.append(metin)
        satir.append("")
    return "\n".join(satir).rstrip() + "\n"


def yaz(kayit: Path, dil: str | None = None, yeniden: bool = False,
        bekle=None, ilerleme=None) -> Path | None:
    """Kaydı çevir ve yanına transkript.md bırak. Yol döner."""
    hedef = kayit / "transkript.md"
    if hedef.exists() and not yeniden:
        log(f"[toplantı] {hedef} zaten var — atlandı (--yeniden ile üzerine "
            f"yazılır)")
        return None
    sonuc = cevir(kayit, dil=dil, bekle=bekle, ilerleme=ilerleme)
    hedef.write_text(markdown(sonuc), encoding="utf-8")
    log(f"[toplantı] yazıldı: {hedef}")
    return hedef


# ------------------------------------------------------------------ izleyici

_DURULMA = 120.0        # kayıt klasörü bu kadar süre kıpırdamadıysa bitmiştir


def _hazir(kayit: Path) -> bool:
    """Zoom bu kayıtla işini bitirdi mi?

    Toplantı biter bitmez dosyalar orada DEĞİLDİR: Zoom kaydı m4a/mp4'e
    dönüştürürken klasöre yazmayı sürdürür, ve yarısı yazılmış bir dosyayı
    çevirmek yarım bir transkript demektir. Klasörün en son değişme anına
    bakmak, dönüştürmenin bittiğini anlamanın dosya kilidi denemeden en
    ucuz yolu.
    """
    try:
        en_son = max(p.stat().st_mtime for p in kayit.rglob("*") if p.is_file())
    except ValueError:
        return False
    return (time.time() - en_son) > _DURULMA


def izle(mesgul_mu=None, aralik: float = 60.0, en_fazla_saat: float = 24.0,
         ilerleme=None, bitti=None):
    """Yeni Zoom kayıtlarını bekle ve gelen her birini transkripte çevir.

    GEÇMİŞE DOKUNULMAZ. Yalnızca son `en_fazla_saat` içinde yazılmış
    kayıtlar alınır: Typer'ı ilk kez açan birinin bir yıllık toplantı
    arşivini kendiliğinden çevirmeye başlaması, istenen bir şey değil bir
    kaza olurdu.

    Süresiz döner; çağıran bunu daemon bir iş parçacığında başlatır.
    """
    log(f"[toplantı] izleyici açık — {aralik:.0f} sn'de bir bakılıyor")
    gorulen = set()
    while True:
        try:
            simdi = time.time()
            for kayit in kayitlar():
                if kayit in gorulen or (kayit / "transkript.md").exists():
                    continue
                if simdi - kayit.stat().st_mtime > en_fazla_saat * 3600:
                    gorulen.add(kayit)      # eski arşiv: bir daha bakma
                    continue
                if not _hazir(kayit):
                    continue                # Zoom hâlâ yazıyor
                gorulen.add(kayit)
                log(f"[toplantı] yeni kayıt: {kayit.name}")
                hedef = yaz(kayit, bekle=_bekleyici(mesgul_mu),
                            ilerleme=ilerleme)
                if hedef is not None and bitti is not None:
                    bitti(hedef)
        except Exception as e:
            log(f"[toplantı] izleyici hatası: {e!r}")
        time.sleep(aralik)


def _bekleyici(mesgul_mu):
    """Dikte sürerken bekleyen, sürmüyorsa hemen dönen bir kapı."""
    if mesgul_mu is None:
        return None

    def bekle():
        while mesgul_mu():
            time.sleep(0.5)
    return bekle
