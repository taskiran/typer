# Typer — SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Bertan Taskiran.
"""Ekolayzer — mikrofonun gerçek frekans içeriği, bant bant.

Kapsülün içindeki çubuklar rastgele değildir ve bir döngüden gelmez:
her çubuk bir frekans bandına sahiptir ve konuşmanın o bandındaki
enerjiyle yükselip alçalır. Sessizlik düzdür; ıslık sağı, "o" sesi solu
kaldırır.

İKİ AYAR, İKİSİ DE ÖLÇÜMLE BULUNDU:

  Bant başına referans. Konuşma enerjisi frekansla dik biçimde düşer —
  burada ölçülen 90. yüzdelikler en alt bantta ~1.1 milyon, en üstte
  ~23 bin. Tek bir küresel ölçek sağ yarıyı kalıcı olarak yatık
  bırakırdı; her bandı kendi tipik seviyesine bölmek bütün çubukları
  eşit derecede canlı yapan şeydir.

  Koşan kazanç. Yukarıdaki sabit referanslar temiz ve yüksek sesli
  sentezlenmiş konuşmadan ölçüldü; sohbet mesafesindeki gerçek bir
  mikrofon çok daha kısıktır ve sabit ölçeğe karşı çubuklar tabandan
  zar zor ayrılır. Bu yüzden yakın geçmişte görülen en yüksek bant
  "tam"ı tanımlar: ölçer, kim konuşuyorsa ona ve hangi seviyede
  konuşuyorsa ona kendini yeniden ayarlar. 1x, 1/6 ve 1/20 girişte
  aynı davrandığı doğrulandı.
"""
import numpy as np

from typer_engine.stt import RATE

BANDS = 26
_NFFT = 1024                          # 16 kHz'de 64 ms'lik geçmiş
# 480 örneklik kareler 33 Hz çözünürlük verir ve 26 bantta en alttakiler
# bundan dardır — ölçüldü, ikisinde HİÇ FFT kutusu yoktu ve kalıcı olarak
# ölü çubuklar olacaklardı. Kayan 1024'lük pencere çözünürlüğü 15.6 Hz'e
# çıkarır; yine de kutuların arasına düşen bir bant en yakınını alır.
_EDGES = np.logspace(np.log10(90), np.log10(5200), BANDS + 1)
_FREQS = np.fft.rfftfreq(_NFFT, 1.0 / RATE)


def _band_masks():
    out = []
    for i in range(BANDS):
        m = (_FREQS >= _EDGES[i]) & (_FREQS < _EDGES[i + 1])
        if not m.any():
            centre = (_EDGES[i] + _EDGES[i + 1]) / 2
            m = np.zeros_like(_FREQS, dtype=bool)
            m[int(np.argmin(np.abs(_FREQS - centre)))] = True
        out.append(m)
    return out


_SEL = _band_masks()
_WIN = np.hanning(_NFFT).astype(np.float32)
_RING = np.zeros(_NFFT, dtype=np.float32)

_REF = np.array([
    1108621., 1341022., 720564., 258852., 467364., 849529.,
    449120., 375781., 393842., 332681., 265004., 220897.,
    170385., 108703., 82726., 67796., 60682., 51151.,
    33022., 30451., 30891., 34437., 36868., 33969.,
    21476., 23053.,
])

_GAIN = {"peak": 0.25}
_GAIN_ATTACK = 0.30      # yüksek bir hece tavanı hızla kaldırır
_GAIN_DECAY = 0.004      # aşağı inişi kareler değil saniyeler alır
_GAIN_FLOOR = 0.06       # sıfıra bölüp uğultuyu ışık şovuna çevirme


def reset():
    """Her kayda taze başla: tavan yok, önceki sesten taşınan da yok."""
    global _RING
    _GAIN["peak"] = 0.25
    _RING = np.zeros(_NFFT, dtype=np.float32)


def spectrum(frame) -> list:
    """30 ms'lik bir kare -> ekolayzer için 0..1 arası BANDS değer."""
    global _RING
    f = np.asarray(frame, dtype=np.float32).ravel()
    if len(f):
        _RING = np.concatenate((_RING, f))[-_NFFT:]
    mag = np.abs(np.fft.rfft(_RING * _WIN))
    v = np.array([mag[sl].mean() for sl in _SEL]) / _REF

    m = float(v.max())
    k = _GAIN_ATTACK if m > _GAIN["peak"] else _GAIN_DECAY
    _GAIN["peak"] += (m - _GAIN["peak"]) * k

    v = v / max(_GAIN_FLOOR, _GAIN["peak"])
    # Gama kaldırışı: onsuz aralığın ortası "neredeyse hiç" gibi okunur
    # ve çubukları yalnızca bağırmak oynatır.
    v = np.clip(v, 0.0, 1.0) ** 0.55
    return [round(float(x), 3) for x in v]


def level(frame) -> float:
    """Tek sayılık kaba seviye, 0..1. Ekolayzeri çizemeyen bir arayüz
    için yedek."""
    rms = float(np.sqrt(np.mean(np.asarray(frame, dtype=np.float32) ** 2)))
    return min(1.0, rms / 4000.0)
