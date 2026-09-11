# Typer — SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Bertan Taskiran. Derived from backtalk,
# Copyright (C) 2026 Jared Rhodenizer.
"""Ayarlar — kök dizindeki typer.json, varsayılanların üzerine binen.

Dosya yoksa varsayılanlar çalışır; yani Typer sıfır yapılandırmayla
açılır. Yalnızca değiştirmek istediğin anahtarı yaz, gerisi buradan gelir.

Tek bir typer.json var ve onu HEM motor HEM arayüz okuyor. İki ayrı ayar
dosyası, kısayolu bir yerde değiştirip diğerinde unutmanın garantili
yoludur.
"""
import json
import os
import sys
from pathlib import Path

# engine/typer_engine/config.py -> engine/typer_engine -> engine -> kök
ROOT = Path(__file__).resolve().parents[2]
# Kişisel ayar dosyası depoda tutulmaz; arayüz ilk açılışta örnekten
# kopyalar. Motor tek başına, arayüz hiç çalışmadan da başlatılabildiği
# için örneğe düşmeyi burası da bilir — yoksa `doctor` bir yapılandırma,
# uygulama başka bir yapılandırma görürdü.
_EXAMPLE_PATH = ROOT / "typer.example.json"
_LOCAL_PATH = ROOT / "typer.json"
CONFIG_PATH = _LOCAL_PATH if _LOCAL_PATH.exists() else _EXAMPLE_PATH

DEFAULTS = {
    # DİKTE TUŞU. Tek bir tuş ("f13", "home"), tek karakter, ya da bir
    # kombinasyon: "ctrl+win", "ctrl+alt+d", "win+6". Değiştiriciler
    # win/ctrl/alt/shift; sağ ve sol ayrımı yapılmaz.
    #
    # macOS'ta "win" = Command tuşudur (pynput ikisini de Key.cmd olarak
    # görür), yani "ctrl+win" iki işletim sisteminde de tek satırla
    # çalışır; Mac'te Ctrl+Command anlamına gelir.
    #
    # İşletim sisteminin zaten sahip olduğu bir kombinasyon (Win+1..9
    # görev çubuğunu gezer) kendi işini de yapmaya devam eder: bu
    # dinleyici tuşları izler, yutamaz.
    "hotkey": "ctrl+win",

    # "toggle": bir bas aç, bir bas kapat. Arada tuş serbesttir, yani
    # konuşurken iki elin de klavyede kalır.
    # "hold": mikrofon yalnızca tuş basılıyken açıktır.
    "mode": "toggle",

    # Tek bir kaydın emniyet sınırı (saniye). Kapatmayı unuttuğun bir
    # kilit eninde sonunda kendiliğinden dursun diye var.
    "max_seconds": 180,

    # BEKLENEN DİL. Üç şekli var:
    #   "tr"          sabitle; dil tespiti hiç çalışmaz, en hızlı seçenek
    #   ["tr", "en"]  tespit et, ama YALNIZCA bunlar arasından seç
    #   ""            tam otomatik tespit
    # Liste şekli cümle başına ~0.12 sn'ye mal olur ve tek bir şey satın
    # alır: Whisper gürültülü seste üçüncü bir dile savrulamaz, ama
    # baştan sona İngilizce bir cümle yine İngilizce çıkar.
    "language": ["tr", "en"],

    # KONUŞMA MODELİ. "auto" donanıma göre seçer: CUDA varsa large-v3,
    # yoksa small. Elle de verebilirsin: tiny / base / small / medium /
    # large-v3, ya da bir HuggingFace deposu adı.
    #
    # Mac için önemli: CTranslate2'nin Metal arka ucu yoktur, yani Apple
    # Silicon dahil her Mac CPU'da çalışır. large-v3 CPU'da bir cümleyi
    # on saniyenin üzerinde çevirir ve dikte için kullanılamaz; "auto"
    # bu yüzden orada small'a düşer.
    "model": "auto",

    # "auto" CUDA varsa onu, yoksa CPU'yu kullanır. "cuda" / "cpu" ile
    # zorlayabilirsin.
    "device": "auto",
    # "auto" cihaza göre seçer: CUDA'da float16, CPU'da int8.
    "compute": "auto",

    # ÇÖZÜM ARAMASININ GENİŞLİĞİ (ışın araması). Whisper her kelimeyi
    # seçerken birden çok adayı paralel yürütür; beş aday bir adaydan
    # daha iyi cümle kurar, ama beklediğin süreyi de uzatır.
    #
    # "auto": CUDA'da 5, CPU'da 1 — çünkü ikisinde aynı şeye mal olmaz.
    # GPU'da bir cümle zaten 0.7 saniyede biter ve genişlik bedavaya
    # yakındır; CPU'da ise beklenen sürenin doğrudan kendisidir.
    #
    # Ölçüldü (Ryzen, 8 çekirdek, small/int8, 40 sn ses):
    #     ışın 5 -> 3.12 sn      ışın 1 -> 2.43 sn
    # ve iki çeviri BİREBİR aynı metni verdi. Gürültülü ya da aksanlı
    # seste 5'in kazandığı yerler vardır; orası önemliyse buraya 5 yaz.
    "beam_size": "auto",

    # CPU'DA KAÇ İŞ PARÇACIĞI. "auto" gerçek çekirdek sayısını kullanır —
    # hiper iş parçacıklarını değil, Apple Silicon'da ise yalnızca
    # performans çekirdeklerini.
    #
    # Kütüphanenin kendi varsayılanı ölçülenin gerisinde kaldı; aynı
    # makinede 3.42 -> 3.12 sn (ışın 5) ve 2.89 -> 2.43 sn (ışın 1).
    # Çekirdek sayısının ÜSTÜNE çıkmak ise geri götürüyor: 16 iş
    # parçacığı 8'den yavaş.
    #
    # 0 = kütüphane ne diyorsa o. Bir sayı = tam olarak o kadar.
    "cpu_threads": "auto",

    # İki blip: mikrofon açılınca yukarı giden bir tane, kapanınca kısa
    # bir tane. Çevirirken hiçbir ses yok — o an kelimeler zaten imlece
    # doğru yola çıkmıştır.
    "sounds": True,

    # Mikrofon açıkken diğer uygulamaları sustur, ki müzik ya da video
    # kaydın içine karışmasın.
    #   Windows: her uygulama tek tek susturulur (WASAPI oturum sesi).
    #   macOS:   yalnızca Music kısılır — işletim sistemi uygulama
    #            başına susturma sunmaz.
    # Kendi sürecimiz ve çocukları asla susturulmaz.
    "mute_others": True,

    # Spotify'ı susturmak yerine DURAKLAT. Susturulmuş bir Spotify
    # çalmaya devam eder: bir dakikalık dikte, şarkının bir dakikasını
    # yutar. Kayıt bitince müzik kaldığı yerden devam eder.
    #
    # Kullanıcının kendi duraklattığı müzik ASLA kendiliğinden çalmaz:
    # yalnızca bizim duraklattığımız, hâlâ duraklı duran Spotify
    # sürdürülür. Spotify kapalıysa hiçbir şey yapılmaz ve asla
    # açılmaz.
    #
    # mute_others kapalıysa bu da çalışmaz: o düğme "başka
    # uygulamaların sesine dokunma" demektir ve duraklatma da ona
    # dokunmaktır.
    "pause_spotify": True,

    # Metni imlece yapıştır. False yaparsan Typer yalnızca panoya kopyalar
    # ve hiçbir tuşa basmaz.
    "paste": True,

    # Yapıştırmadan sonra panoyu eski içeriğine geri koy.
    "restore_clipboard": True,

    # KOPYALAMA KARTI NE ZAMAN ÇIKSIN.
    #
    # Odak kontrolünün üç cevabı var: "editable" (yazı kabul eden bir
    # alan), "nowhere" (masaüstü ya da salt okunur bir belge) ve "assume"
    # — yani BİLMİYORUM. Sonuncusu, odakta hiçbir desen taşımayan bir
    # Chromium paneli olduğunda dönüyor, ve orada yazı kutuya düşmüş de
    # olabilir hiçbir yere gitmemiş de. Ölçüldü: diktelerin ~%5'i burada.
    #
    #   "unsure"   (varsayılan) nowhere + assume — bilinmediğinde de göster
    #   "nowhere"  yalnızca kesin olduğunda
    #   "always"   her diktede
    #
    # Varsayılan "unsure", çünkü iki hata aynı ağırlıkta değil: kartın
    # çıkmaması kelimelerin sessizce kaybolması demek, fazladan çıkması
    # ise bir tıkla kapanan bir kutu. Kart WhatsApp gibi yazının zaten
    # düzgün düştüğü yerlerde rahatsız ederse "nowhere" eski davranıştır.
    "card_when": "unsure",
}

# backtalk'tan taşınan adlar sessizce kabul edilir, ki eski bir ayar
# dosyasını kopyalayan biri sessizce varsayılanlara düşmesin.
_LEGACY = {
    "dictate_key": "hotkey",
    "dictate_mode": "mode",
    "dictate_max_seconds": "max_seconds",
    "dictate_sounds": "sounds",
    "stt_model": "model",
    "stt_device": "device",
    "stt_compute": "compute",
    "stt_language": "language",
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        raw = CONFIG_PATH.read_text(encoding="utf-8-sig")   # BOM'a dayanıklı
        user = json.loads(raw)
        if not isinstance(user, dict):
            raise ValueError("kök bir nesne olmalı")
        for k, v in user.items():
            if k.startswith("_"):
                continue                       # "_note" gibi yorum anahtarları
            cfg[_LEGACY.get(k, k)] = v
    except FileNotFoundError:
        pass
    except ValueError as e:
        # Bozuk bir ayar dosyası uygulamayı düşürmemeli: varsayılanlarla
        # çalışmak, hiç çalışmamaktan iyidir.
        print(f"[config] typer.json geçerli JSON değil ({e}) — "
              f"varsayılanlar kullanılıyor", file=sys.stderr, flush=True)
    return cfg


CFG = load()


def resolve_backend(cfg: dict) -> tuple[str, str, str]:
    """(model, device, compute) — "auto" olanları donanıma göre açar.

    CUDA sorgusu sürücüyü sorar (nvcuda), cuBLAS'ı değil; yani CUDA
    kütüphaneleri eksikse bile burada patlamaz, yalnızca 0 döner.
    """
    device = cfg.get("device", "auto")
    if device == "auto":
        device = "cpu"
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                device = "cuda"
        except Exception:
            pass

    compute = cfg.get("compute", "auto")
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"

    model = cfg.get("model", "auto")
    if model == "auto":
        model = "large-v3" if device == "cuda" else "small"

    return model, device, compute


def _cores() -> int:
    """Kaç GERÇEK çekirdek var — hiper iş parçacıkları sayılmaz.

    Apple Silicon'da yalnızca PERFORMANS çekirdekleri sayılır. M serisi
    yongalarda verim çekirdekleri birkaç kat yavaştır ve CTranslate2 işi
    iş parçacıklarına eşit böler: verim çekirdeğine düşen parça bitene
    kadar ötekiler bekler. Yani onu işe katmak toplamı hızlandırmaz,
    yavaşlatır.
    """
    if sys.platform == "darwin":
        import subprocess
        # perflevel0 = performans çekirdekleri (Apple Silicon). Intel
        # Mac'lerde bu anahtar yoktur; orada fiziksel çekirdek doğru
        # cevaptır.
        for anahtar in ("hw.perflevel0.physicalcpu", "hw.physicalcpu"):
            try:
                cikti = subprocess.run(["sysctl", "-n", anahtar],
                                       capture_output=True, text=True,
                                       timeout=2).stdout.strip()
                if cikti and int(cikti) > 0:
                    return int(cikti)
            except Exception:
                pass
    elif sys.platform == "win32":
        try:
            import psutil
            n = psutil.cpu_count(logical=False)
            if n:
                return int(n)
        except Exception:
            pass
    else:
        try:
            # /proc/cpuinfo: (fiziksel yonga, çekirdek) çiftlerinin tekili
            ciftler, yonga, cekirdek = set(), None, None
            with open("/proc/cpuinfo", encoding="utf-8") as f:
                for satir in f:
                    if satir.startswith("physical id"):
                        yonga = satir.split(":")[1].strip()
                    elif satir.startswith("core id"):
                        cekirdek = satir.split(":")[1].strip()
                    elif not satir.strip() and yonga is not None:
                        ciftler.add((yonga, cekirdek))
                        yonga = cekirdek = None
            if yonga is not None:
                ciftler.add((yonga, cekirdek))
            if ciftler:
                return len(ciftler)
        except Exception:
            pass
    # Bilinmiyorsa hiper iş parçacığı varsay ve yarısını al. Yanılmanın
    # bedeli birkaç yüz milisaniyedir, ve bu yön yanlış tarafa sapmaz.
    return max(1, (os.cpu_count() or 4) // 2)


def resolve_speed(cfg: dict, device: str) -> tuple[int, int]:
    """(beam_size, cpu_threads) — "auto" olanları cihaza göre açar.

    resolve_backend'in içine katılmadı: onun üç elemanlı sözleşmesini
    doctor da çağırıyor ve imzayı genişletmek iki çağıranı birden
    kırardı.
    """
    beam = cfg.get("beam_size", "auto")
    if beam == "auto":
        beam = 5 if device == "cuda" else 1
    try:
        beam = max(1, int(beam))
    except (TypeError, ValueError):
        beam = 5 if device == "cuda" else 1

    threads = cfg.get("cpu_threads", "auto")
    if threads == "auto":
        # GPU'da iş parçacığı sayısının hükmü yok; 0 "kütüphane bilsin"
        # demektir ve orada doğru cevap odur.
        threads = _cores() if device == "cpu" else 0
    try:
        threads = max(0, int(threads))
    except (TypeError, ValueError):
        threads = 0

    return beam, threads
