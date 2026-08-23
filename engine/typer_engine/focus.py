# Typer — SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Bertan Taskiran. Derived from backtalk,
# Copyright (C) 2026 Jared Rhodenizer.
"""Odaktaki şey yazı kabul eder mi?

Üç cevap: "editable", "nowhere", "assume".

SERT SINIR, varsayılmadan ölçüldü. Erişilebilirlik ağaçları, Chromium'un
içine bir ekran okuyucu algılamadığı sürece bakamaz. WhatsApp'ın ağacı
iki `EmbeddedBrowserTab` panelinde bitiyor — mesaj kutusu ağaçta HİÇBİR
derinlikte yok. Yani "burası yazılabilir mi?" sorusunun, diktenin en çok
kullanıldığı uygulamalar için bir cevabı yok, ve denetim tipi listesini
genişletmek bunu düzeltmez. macOS tarafında da aynısı geçerli: Electron
ve Chrome pencereleri AXWebArea'nın altını göstermez.

KARAR BU YÜZDEN TERSİNE ÇEVRİLDİ. Belirsizlik eskiden "kartı göster"
demekti, ve sonuç metin mesaj kutusuna kusursuzca düşmüşken üstüne açılan
bir kart oldu. Artık belirsizlik "çalıştığını varsay" demek, çünkü opak
pencereler ezici çoğunlukla yazıyı kabul ediyor; kart ise gerçekten
bilinebilir olan tek duruma ayrıldı: hiçbir şeyin klavye odağında
olmaması, yani masaüstü.

Varsayım yanıldığında kelimeler kaybolmaz — arayüz son çeviriyi saklar
ve tepsi menüsünden panoya geri koyar.
"""
import subprocess
import sys

from typer_engine.bus import log

EDITABLE = "editable"
NOWHERE = "nowhere"
ASSUME = "assume"

# Masaüstü ve diğer kabuk yüzeyleri: oralarda yazı alan bir şey yok.
_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd",
                  "Shell_SecondaryTrayWnd", "SysListView32"}

# macOS'ta metin kabul eden erişilebilirlik rolleri.
_AX_EDITABLE = {"AXTextField", "AXTextArea", "AXComboBox",
                "AXSearchField", "AXSecureTextField"}

_MAC_SCRIPT = '''
tell application "System Events"
  try
    set p to first application process whose frontmost is true
  on error
    return "?|?"
  end try
  set appName to name of p
  try
    set el to value of attribute "AXFocusedUIElement" of p
  on error
    return appName & "|none"
  end try
  if el is missing value then return appName & "|none"
  try
    return appName & "|" & (role of el)
  on error
    return appName & "|?"
  end try
end tell
'''


def _windows_kind() -> str:
    try:
        import uiautomation as auto
    except Exception:
        return ASSUME
    try:
        auto.SetGlobalSearchTimeout(0.4)
        el = auto.GetFocusedControl()
        if el is None:
            return NOWHERE
        try:
            top = el.GetTopLevelControl()
            if top is not None and (top.ClassName or "") in _SHELL_CLASSES:
                return NOWHERE
        except Exception:
            pass
        if el.ControlType in (auto.ControlType.EditControl,
                              auto.ControlType.DocumentControl,
                              auto.ControlType.ComboBoxControl):
            return EDITABLE
        for pid in (auto.PatternId.ValuePattern, auto.PatternId.TextPattern):
            try:
                if el.GetPattern(pid) is not None:
                    return EDITABLE
            except Exception:
                pass
        if (el.ClassName or "") in _SHELL_CLASSES:
            return NOWHERE
        return ASSUME
    except Exception as e:
        log(f"[focus] kontrol başarısız ({str(e)[:60]})")
        return ASSUME


def _mac_kind() -> str:
    """System Events'e öndeki sürecin odaklı öğesinin rolünü sordurur.

    Otomasyon + Erişilebilirlik izni ister; ikisi de yoksa osascript hata
    verir ve "assume"a düşeriz, ki bu zaten güvenli taraf.
    """
    try:
        r = subprocess.run(["osascript", "-e", _MAC_SCRIPT],
                           capture_output=True, text=True, timeout=1.5)
    except Exception as e:
        log(f"[focus] osascript çalışmadı ({str(e)[:60]})")
        return ASSUME
    out = (r.stdout or "").strip()
    if not out or "|" not in out:
        return ASSUME
    app, role = out.split("|", 1)
    if role in _AX_EDITABLE:
        return EDITABLE
    # Masaüstüne tıklamak Finder'ı öne alır ve odaklı bir metin öğesi
    # bırakmaz — Windows'taki Progman/WorkerW kuralının Mac karşılığı.
    if app == "Finder" and role in ("none", "AXList", "AXScrollArea", "?"):
        return NOWHERE
    if role == "none":
        return NOWHERE
    return ASSUME


def kind() -> str:
    """Bu işletim sisteminde odağın ne olduğuna dair en iyi cevap."""
    if sys.platform == "win32":
        return _windows_kind()
    if sys.platform == "darwin":
        return _mac_kind()
    # Linux: tek tip bir erişilebilirlik yolu yok (X11'de AT-SPI, Wayland'da
    # o da değil). Her zaman yapıştır, kart gösterme.
    return ASSUME
