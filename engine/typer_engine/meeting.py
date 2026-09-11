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
import time
from pathlib import Path

from typer_engine.bus import log
from typer_engine.config import CFG
from typer_engine.stt import BACKEND, transcribe_file, warm

# Zoom m4a yazar. Ötekiler elle beslenen kayıtlar için — dosyayı PyAV
# çözüyor, yani kabul etmemek için bir sebep yok.
_SES = {".m4a", ".mp4", ".wav", ".mp3", ".m4v", ".aac", ".flac", ".ogg"}

# audio_only_<katilimci id>_<Gorunen_Ad>
_AD = re.compile(r"^audio_only_\d+_(.+)$", re.I)

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
    if kok.lower() in ("audio_only", "audio"):
        return "Karışık ses"
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

def _zoom_kokleri() -> list[Path]:
    """Zoom'un yerel kayıtları nereye koyabileceği yerler.

    OneDrive "Belgeler"i kendine taşıdığında klasör ev dizininin altından
    çıkar ve Zoom onu takip eder — ikisine de bakmak, kullanıcıya klasör
    yolunu sordurmaktan ucuzdur.
    """
    elle = str(CFG.get("meetings_dir") or "").strip()
    if elle:
        # Elle verilmişse ARAMA YAPILMAZ. Kullanıcı klasörü söylediyse
        # başka bir yerde bulunan bir kayıt sürpriz olurdu.
        k = Path(elle).expanduser()
        return [k] if k.is_dir() else []
    ev = Path.home()
    adaylar = [ev / "Documents" / "Zoom",
               ev / "OneDrive" / "Documents" / "Zoom",
               ev / "Belgeler" / "Zoom",
               ev / "OneDrive" / "Belgeler" / "Zoom"]
    return [k for k in adaylar if k.is_dir()]


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
    ayri = kayit / "Audio Record"
    kaynak = ayri if ayri.is_dir() else kayit
    dosyalar = sorted(p for p in kaynak.iterdir()
                      if p.is_file() and p.suffix.lower() in _SES)
    return [(_katilimci(p), p) for p in dosyalar]


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


def cevir(kayit: Path, dil: str | None = None, bekle=None) -> dict:
    """Kaydı çevir ve {konuşmacılar, sozler, sure...} döndür.

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

    sozler = []
    sayim = {}
    for ad, p in sira:
        if bekle is not None:
            bekle()
        # KATILIMCI BAŞINA DOSYALAR TOPLANTI BOYUNCA SÜRER ve konuşmadığın
        # her an sessizliktir. VAD süzgeci burada iki şey birden yapar:
        # sessizliği modele hiç göstermeyerek çeviriyi kat kat hızlandırır,
        # ve Whisper'ın sessizliğe uydurduğu hayalet cümleleri baştan
        # keser. (Diktede aynı süzgeç bir şey vermiyordu — orada kesintisiz
        # konuşma var, atılacak sessizlik yok.)
        t0 = time.perf_counter()
        parcalar, kullanilan = transcribe_file(p, language=dil, vad=True)
        gecen = time.perf_counter() - t0
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
        bekle=None) -> Path | None:
    """Kaydı çevir ve yanına transkript.md bırak. Yol döner."""
    hedef = kayit / "transkript.md"
    if hedef.exists() and not yeniden:
        log(f"[toplantı] {hedef} zaten var — atlandı (--yeniden ile üzerine "
            f"yazılır)")
        return None
    sonuc = cevir(kayit, dil=dil, bekle=bekle)
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


def izle(mesgul_mu=None, aralik: float = 60.0, en_fazla_saat: float = 24.0):
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
                yaz(kayit, bekle=_bekleyici(mesgul_mu))
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
