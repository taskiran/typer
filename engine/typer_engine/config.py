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
