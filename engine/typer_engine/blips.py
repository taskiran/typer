# Typer — SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Bertan Taskiran.
"""İki blip: mikrofon açılırken yukarı çıkan, kapanırken kısa olan.

Çeviri sürerken hiçbir ses yoktur — o an kelimeler zaten imlece doğru
yola çıkmıştır ve orada çalan bir ses "hâlâ dinliyorum" der.
"""
import threading

import numpy as np
import sounddevice as sd

from typer_engine.config import CFG
from typer_engine.stt import RATE


def _tone(freqs, ms, rate=RATE, gain=0.18):
    """Kısa bir blip. Hızlı atak ve sönümle sinüs, ki kuyruklu bir bip
    değil bir tık gibi okunsun."""
    n = int(rate * ms / 1000)
    t = np.arange(n) / rate
    wave = np.zeros(n, dtype=np.float32)
    seg = n // len(freqs)
    for i, f in enumerate(freqs):
        a, b = i * seg, (i + 1) * seg if i < len(freqs) - 1 else n
        tt = t[a:b] - t[a]
        wave[a:b] = np.sin(2 * np.pi * f * tt).astype(np.float32)
    env = np.minimum(1.0, np.arange(n) / max(1, int(rate * 0.004)))
    env *= np.exp(-np.arange(n) / (rate * (ms / 1000) / 3.0))
    return (wave * env * gain).astype(np.float32)


_START = None
_END = None
_lock = threading.Lock()


def _buffers():
    global _START, _END
    if _START is None:
        _START = _tone([660, 990], 110)     # iki nota yukarı: "dinliyorum"
        _END = _tone([520], 70)             # bir nota aşağı: "bitti"
    return _START, _END


def _play(buf):
    """Bir blip çal — eşzamanlı, ve kendine ait bir akış üzerinde.

    sounddevice.play() DEĞİL: o yardımcı MODÜL SEVİYESİNDE bir akış
    tutar, ve bir kayıt akışı açılıp kapanırken onu arka plan
    ipliklerinden sürmek süreci bozar. Bu teorik değil — sahada ses
    hattını öldürdü (ntdll içinde STATUS_HEAP_CORRUPTION), ve eski yolun
    30 turluk zorlaması yirmi tur dolmadan erişim ihlali olarak yeniden
    üretti.

    Bloklamak aynı zamanda daha doğru davranış: açılış blibi mikrofon
    açılmadan ÖNCE biter, yani hiçbir zaman kaydın içine düşmez.
    """
    if not CFG.get("sounds", True):
        return
    with _lock:
        try:
            with sd.OutputStream(samplerate=RATE, channels=1,
                                 dtype="float32") as out:
                out.write(buf)
        except Exception:
            # Ses aygıtı yoksa ya da meşgulse dikte yine de çalışmalı.
            pass


def start():
    _play(_buffers()[0])


def end():
    _play(_buffers()[1])
