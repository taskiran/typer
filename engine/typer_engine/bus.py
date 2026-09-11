# Typer — SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Bertan Taskiran.
"""Motor ile arayüz arasındaki hat — stdout üzerinde satır başına JSON.

Neden dosya değil: önceki sürümde durum bir dosyaya yazılıyor, arayüz de
onu saniyede 16 kez okuyordu. Oysa arayüz motoru zaten kendi çocuğu
olarak başlatıyor, yani stdout hazır ve bedava duruyor. Boru hattı
gecikmesizdir, disk trafiği yaratmaz, geçici dosya bırakmaz ve motor
öldüğünde kendini kapatır — dosya ise son durumda donup kalır.

SATIR BİÇİMİ. Her protokol satırı "@TYPER " ile başlar ve arkasından tek
satırlık JSON gelir. Ön ek şarttır: numpy'den ffmpeg'e kadar herhangi bir
bağımlılık bir gün stdout'a bir şey basacak, ve ön ek olmadan o satır
ayrıştırıcıyı bozar. Ön eki taşımayan her şey arayüz tarafında bir günlük
satırı sayılır.

JSON kasten ASCII'ye kaçışlı yazılır (ensure_ascii). Windows'ta stdout'un
varsayılan kodlaması yerel kod sayfasıdır, arayüz ise UTF-8 bekler;
kaçışlı ASCII bu ikisinin hiç karşılaşmamasını sağlar.
"""
import json
import sys
import threading
import time

PREFIX = "@TYPER "

_lock = threading.Lock()


def _setup_streams():
    """Türkçe karakterler kod sayfası ne olursa olsun geçsin."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_setup_streams()


def emit(state: str, level: float = 0.0, text: str = "", bands=None,
         kesin=None):
    """Arayüze ne olduğunu söyle.

    Durumlar:
      idle       görünecek bir şey yok. text taşıyabilir: son çeviri,
                 arayüz onu tepsiden geri verebilsin diye
      listening  mikrofon açık; level ve bands ölçer için
      thinking   mikrofon kapandı, çeviri sürüyor
      meeting    arka planda toplantı çevriliyor; level 0..1 ilerleme
      transcript bir transkript yazıldı; text dosyanın yoludur
      preview    metin kartta bekliyor; kesin, yazacak yerin gerçekten
                 bulunamadığını mı yoksa yalnızca bilinmediğini mi söyler
      error      bir şey ters gitti; text açıklamadır

    "thinking" sonradan geldi ve kapsülü mikrofon kapanınca kapatmıyor:
    uzun bir diktede çeviri saniyeler sürüyor, ve kapsülün o an yok olması
    kelimelerin kaybolduğu izlenimini veriyordu. Kapsül metin
    yapıştırıldığında kapanır.
    """
    payload = {
        "state": state,
        "level": round(float(level), 3),
        "bands": bands or [],
        "text": text,
        # Yalnızca "preview" için anlamlı: True ise yazacak yer gerçekten
        # yoktu, False ise bilinmiyordu. Kart etiketi buna göre değişir —
        # bilmediğini bilmek, bilmediğini bildirmekten iyidir.
        "kesin": kesin,
        "ts": time.time(),
    }
    line = PREFIX + json.dumps(payload, ensure_ascii=True)
    with _lock:
        try:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
        except Exception:
            # Arayüz kapandıysa boru kırılır. Motor bunu umursamaz: dikte,
            # ekranda bir şey olmasa da çalışmaya devam eder.
            pass


def log(line: str):
    """İnsan için. stderr'e gider; arayüz onu logs/engine.log dosyasına
    yazar, terminalden çalıştırdığında doğrudan ekrandadır."""
    try:
        sys.stderr.write(f"{time.strftime('%H:%M:%S')} {line}\n")
        sys.stderr.flush()
    except Exception:
        pass
