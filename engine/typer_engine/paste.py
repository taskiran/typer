# Typer — SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Bertan Taskiran. Derived from backtalk,
# Copyright (C) 2026 Jared Rhodenizer.
"""Metni imlece koy.

METİN PANO ÜZERİNDEN GİDER, sentetik tuş vuruşlarıyla değil: harf harf
yazmak pek çok klavye düzeninde ASCII dışını bozar, ve Türkçede bu
kelimelerin çoğu demektir. Pano da yapıştırmadan sonra eski içeriğine
geri konur.

YAPIŞTIRMA TUŞU İŞLETİM SİSTEMİNE GÖRE DEĞİŞİR — macOS'ta Cmd+V,
başka her yerde Ctrl+V. Bu, taşınırken kolayca gözden kaçan ve Mac'te
sessizce hiçbir şey yapmayan türden bir ayrıntı.
"""
import sys
import threading
import time

from pynput import keyboard

from typer_engine.bus import log
from typer_engine.config import CFG

_MODS_TIMEOUT_S = 2.0        # değiştiricilerin kalkması ne kadar beklenir
_CLIP_RESTORE_S = 1.5        # yapıştırma panoyu tüketsin, sonra geri koy

# macOS Command, gerisi Ctrl.
PASTE_MOD = (keyboard.Key.cmd if sys.platform == "darwin"
             else keyboard.Key.ctrl)

_controller = None
_controller_lock = threading.Lock()


def _kb():
    global _controller
    with _controller_lock:
        if _controller is None:
            _controller = keyboard.Controller()
    return _controller


def clip_get():
    try:
        import pyperclip
        return pyperclip.paste()
    except Exception:
        return None


def clip_set(text) -> bool:
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception as e:
        # Linux'ta bu genelde xclip/xsel eksikliğidir.
        log(f"[paste] pano kullanılamıyor ({str(e)[:60]})")
        return False


def send(text: str, hotkey=None) -> bool:
    """Metni panoya koy ve yapıştır. Panoyu sonra geri verir."""
    if not text:
        return False
    if not CFG.get("paste", True):
        # Yapıştırma kapalı: metin yalnızca panoda beklesin.
        return clip_set(text)

    # Tetiğin değiştiricileri hâlâ basılıyken gönderilen Ctrl+V karşı
    # tarafa Ctrl+Win+V olarak varır. Elin tuşlardan kalkmasını bekle.
    if hotkey is not None:
        deadline = time.time() + _MODS_TIMEOUT_S
        while not hotkey.modifiers_clear() and time.time() < deadline:
            time.sleep(0.02)

    prev = clip_get() if CFG.get("restore_clipboard", True) else None
    if not clip_set(text):
        return False

    ok = True
    try:
        kb = _kb()
        with kb.pressed(PASTE_MOD):
            kb.press("v")
            kb.release("v")
    except Exception as e:
        # macOS'ta Erişilebilirlik izni yoksa buraya düşülür.
        log(f"[paste] yapıştırma başarısız ({str(e)[:80]})")
        ok = False

    if prev is not None and prev != text:
        t = threading.Timer(_CLIP_RESTORE_S, lambda: clip_set(prev))
        t.daemon = True
        t.start()
    return ok
