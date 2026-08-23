# Typer — SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Bertan Taskiran. Derived from backtalk,
# Copyright (C) 2026 Jared Rhodenizer.
"""Kulaklar — mikrofon kaydı ve süreç içinde faster-whisper ile çeviri.

Yerel, ücretsiz, sunucusuz, API anahtarsız. Ses hiçbir zaman bu makineden
çıkmaz.

Burada ses etkinliği algılayıcı YOK ve olmasına gerek de yok: kayıt
tuşun kendisiyle başlar ve biter, yani düğme zaten VAD'in ta kendisidir.
(backtalk'ta bir de açık mikrofon kipi vardı ve onun için webrtcvad
gerekiyordu; Typer o kipi taşımadığı için bağımlılık da gelmedi — bu
C eklentisi macOS'ta derlenmesi en zahmetli parçaydı.)
"""
import os
import re
import sys
import threading

import numpy as np
import sounddevice as sd

from typer_engine.bus import log
from typer_engine.config import CFG, resolve_backend

RATE = 16000
FRAME_MS = 30
FRAME_LEN = RATE * FRAME_MS // 1000  # kare başına örnek

_NONSPEECH = re.compile(r"[\[(][^\])]*[\])]")

# Bunun altında mikrofon kapalı, fişi çıkmış ya da kayıt dijital
# sessizlik demektir. Üstündeki her şey modele gider.
DEAD_MIC_RMS = 25.0

# WHISPER'IN HAYALETLERİ. Neredeyse sessizlik beslendiğinde model boş
# dönmez; kendinden emin bir cümle döner, ve eğitim verisi altyazılı
# videoyla dolu olduğu için jeneriğe uzanır. Aşağıdakiler burada gerçekten
# ürettikleridir. Yalnızca çevirinin TAMAMI bunlardan biriyse eşleşir —
# gerçek bir cümlenin içinde geçtiklerinde sıradan kelimelerdir ve
# hayatta kalmaları gerekir.
_PHANTOMS = {
    "altyazi mk", "altyazi m k", "altyazilar",
    "altyazi icin tesekkurler", "altyazi ceviri",
    "izlediginiz icin tesekkur ederim", "izlediginiz icin tesekkurler",
    "abone olmayi unutmayin", "kanalima abone olmayi unutmayin",
    "bir sonraki videoda gorusmek uzere", "gorusmek uzere",
    "tesekkurler", "tesekkur ederim",
    "thank you", "thanks for watching", "thank you for watching",
    "subtitles by the amaraorg community", "you", "bye", "the end",
}

_TR_FOLD = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def _is_phantom(text: str) -> bool:
    """Çeviri, Whisper'ın stok halüsinasyonlarından biri ve yalnızca o mu?
    Aksanı sadeleştirilmiş ve noktalamadan arındırılmış olarak bakılır,
    çünkü model iki koşuda aynı cümleyi farklı şapkalarla döndürür."""
    t = text.translate(_TR_FOLD).lower()
    t = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in t)
    return " ".join(t.split()) in _PHANTOMS


_model = None
_model_lock = threading.Lock()
# CTranslate2 varsayılan olarak tek işçiyle çalışır, o yüzden üst üste
# binen transcribe() çağrıları çalışma zamanına yarıştırılmak yerine
# burada sıraya sokulur.
_use_lock = threading.Lock()

# warm() tarafından çözülür; teşhis satırları buradan okur.
BACKEND = {"model": None, "device": None, "compute": None}


def _wire_cuda_dlls():
    """Windows: pip ile kurulan CUDA kütüphanelerini bulunur kıl.

    faster-whisper CTranslate2 üzerinde koşar, o da cuBLAS ve cuDNN'i
    düz Windows DLL aramasıyla — eskisiyle, yani PATH'e bakanla — yükler.
    os.add_dll_directory() TEK BAŞINA yetmez (sahada denendi: yine de
    "cublas64_12.dll is not found" der). O yüzden nvidia-*-cu12
    tekerleklerinin bin klasörleri, import'tan önce PATH'e konur;
    add_dll_directory da modern aramayı kullananlar için üstüne eklenir.

    Başka her yerde işlemsizdir, ve tekerlekler kurulu değilken de
    zararsızdır: CPU cihazı bunları hiç istemez.
    """
    if sys.platform != "win32":
        return
    import glob
    import site
    dirs = []
    for base in site.getsitepackages():
        dirs += [d for d in glob.glob(os.path.join(base, "nvidia", "*", "bin"))
                 if os.path.isdir(d)]
    if not dirs:
        return
    os.environ["PATH"] = os.pathsep.join(dirs) + os.pathsep + \
        os.environ.get("PATH", "")
    for d in dirs:
        try:
            os.add_dll_directory(d)
        except Exception:
            pass


def warm():
    """Modeli yükle (ilk çağrı onu HuggingFace önbelleğine indirir).

    Açılışta, kısayol bağlanır bağlanmaz çağrılır: ilk gerçek cümlenin
    yükleme bedelini ödememesi için. large-v3 diskte ~1.5 GB'tır ve ilk
    indirme birkaç dakika sürebilir.
    """
    global _model
    with _model_lock:
        if _model is not None:
            return _model
        model, device, compute = resolve_backend(CFG)
        if device != "cpu":
            _wire_cuda_dlls()
        BACKEND.update(model=model, device=device, compute=compute)
        from faster_whisper import WhisperModel
        log(f"[stt] {model} yükleniyor ({device}/{compute})...")
        if device == "cpu" and model.startswith(("large", "medium")):
            log(f"[stt] uyarı: {model} CPU'da bir cümleyi on saniyenin "
                f"üzerinde çevirir. typer.json içinde \"model\": \"small\" "
                f"dikte için çok daha kullanışlıdır.")
        try:
            _model = WhisperModel(model, device=device, compute_type=compute)
        except Exception as e:
            if device == "cpu":
                raise
            # GPU yolu kurulumdan kuruluma kırılgan (eksik cuBLAS, sürücü
            # uyumsuzluğu, VRAM). Sessizce ölmektense yavaş çalış:
            # kullanılabilir bir dikte, hiç dikte olmamasından iyidir.
            log(f"[stt] {device} açılamadı ({str(e)[:120]}) — CPU'ya "
                f"düşülüyor")
            BACKEND.update(device="cpu", compute="int8")
            _model = WhisperModel(model, device="cpu", compute_type="int8")
        log("[stt] model hazır")
    return _model


def _norm_lang(tag) -> str:
    """detect_language bazı sürümlerde '<|tr|>', bazılarında 'tr' der.
    Buradan sonrası tek şekil."""
    return str(tag).strip("<|>").strip()


def _choose_language(model, audio):
    """Hangi dil olarak çevrilecek.

    language ayarının üç şekli için: bkz. config.py. Ölçülen bedel —
    kısıtlı liste şekli 0.73 sn, sabitlenmiş şekil 0.61 sn; yani tespit
    geçişi yaklaşık 0.12 saniye.
    """
    want = CFG.get("language")
    if isinstance(want, str):
        return want or None
    allowed = [_norm_lang(x) for x in (want or []) if str(x).strip()]
    if not allowed:
        return None
    if len(allowed) == 1:
        return allowed[0]
    try:
        _lang, _prob, probs = model.detect_language(audio)
        items = probs.items() if isinstance(probs, dict) else probs
        scored = [(p, _norm_lang(k)) for k, p in items
                  if _norm_lang(k) in allowed]
        if scored:
            best_p, best = max(scored)
            log(f"[stt] dil {best} ({best_p:.2f}) / {allowed}")
            return best
    except Exception as e:
        log(f"[stt] dil tespiti başarısız ({str(e)[:50]})")
    return allowed[0]          # birincil dil geri düşüştür


def transcribe(pcm: np.ndarray) -> str:
    """int16 mono 16kHz -> metin. Whisper'ın ürettiği parantezli konuşma
    dışı işaretler ([BLANK_AUDIO], [SIGHS], (öksürük)...) atılır; geriye
    bir şey kalmıyorsa o sessizlikti."""
    model = warm()
    audio = pcm.astype(np.float32) / 32768.0
    # .en modeli tanımı gereği İngilizcedir; gerisi _choose_language'a sorar.
    lang = ("en" if str(BACKEND["model"]).endswith(".en")
            else _choose_language(model, audio))
    with _use_lock:
        segments, _ = model.transcribe(audio, temperature=0.0, language=lang)
        segments = list(segments)   # kilidin içinde boşalt: bu bir üreteç
                                    # ve asıl iş gezinirken oluyor
    text = "".join(s.text for s in segments).strip()
    text = _NONSPEECH.sub("", text).strip()
    if text and _is_phantom(text):
        log(f"[stt] hayalet çeviri ({text!r}) — atıldı")
        return ""
    return text


def record(is_held, max_s: float = 180.0, min_s: float = 0.25,
           on_frame=None, on_stop=None) -> str | None:
    """is_held() True olduğu sürece kaydet, sonra çevir.

    Düğme VAD'in kendisidir — uç noktalama yok. min_s'den kısa dokunuşlar
    (kazara basışlar) None döner.

    on_frame(mono_int16) her 30 ms'lik kareyi geldiği anda alır; konuşurken
    canlı görünmesi gereken bir arayüz için. Tek bir sayı değil ham kare,
    çünkü yalnızca gürültü seviyesini bilen bir ölçer ancak tek parça
    halinde hareket edebilir — spektrum örnekleri ister. Ucuz olmalı ve
    asla hata fırlatmamalı: kayıt döngüsünün içinde, okumaların arasında
    koşar.

    on_stop() mikrofon kapandığı ANDA, çeviriden ÖNCE ateşlenir. Çeviri
    yavaş olan taraftır ve onu bekleyen bir arayüz tuşun hiç işlemediği
    hissini verir — çağıran, göstergesini kelimeler hazır olduğunda değil
    konuşmayı bıraktığın anda indirmek ister.
    """
    frames: list[np.ndarray] = []
    with sd.InputStream(samplerate=RATE, channels=1, dtype="int16",
                        blocksize=FRAME_LEN) as stream:
        while is_held() and len(frames) * FRAME_MS / 1000 < max_s:
            block, _ = stream.read(FRAME_LEN)
            if on_frame is not None:
                try:
                    on_frame(block[:, 0])
                except Exception:
                    pass
            frames.append(block[:, 0].copy())
        # küçük bir kuyruk, son kelime bırakışta kırpılmasın diye
        for _ in range(6):
            block, _ = stream.read(FRAME_LEN)
            frames.append(block[:, 0].copy())
    if on_stop is not None:
        try:
            on_stop()
        except Exception:
            pass
    if len(frames) * FRAME_MS / 1000 < min_s:
        return None
    audio = np.concatenate(frames)
    if not _has_speech(audio):
        return None
    return transcribe(audio)


def _has_speech(audio: np.ndarray) -> bool:
    """Burada HERHANGİ bir sinyal var mı? Kasten neredeyse her zaman evet.

    Daha önceki sürümler zeki olmayı denedi ve ikisi de bu makinede,
    ölçülerek, çöktü:

      - VAD'in seslendirilmiş saydığı en uzun kare dizisi: boş oda 15
        aldı, gerçek konuşma 8 ve 11. Test yalnızca zayıf değil, TERSİNE
        çalışıyordu, ve kullanıcının söylediği her şeyi çöpe atıyordu.
      - Tepe/taban enerji oranı: boş oda 4.8, kısık konuşma 4.4. İç içe.

    Gürültü tabanı bu kadar yüksekken saf akustik hiçbir şey ikisini
    ayırmıyor. Bu yüzden burası artık yalnızca ölü mikrofonu yakalar;
    Whisper'ın neredeyse sessizliğe uydurduğu kendinden emin saçmalık
    ise çeviriden SONRA, adıyla yakalanır (bkz. _PHANTOMS). Gerçek
    konuşmayı düşürmek, bilinen bir hayaleti geçirmekten çok daha kötüdür.
    """
    n = (len(audio) // FRAME_LEN) * FRAME_LEN
    if n == 0:
        return False
    fr = audio[:n].reshape(-1, FRAME_LEN).astype(np.float32)
    peak = float(np.percentile(np.sqrt((fr ** 2).mean(axis=1)), 95))
    if peak < DEAD_MIC_RMS:
        log(f"[stt] sinyal yok (tepe rms {peak:.0f}) — atıldı")
        return False
    return True
