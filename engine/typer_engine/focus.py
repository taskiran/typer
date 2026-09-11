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
        karar, neden = _windows_karar(auto, el)
    except Exception as e:
        log(f"[focus] kontrol başarısız ({str(e)[:60]})")
        return ASSUME
    # TEŞHİS SATIRI, ve varlık sebebi şu: "kart neden çıkmadı?" sorusunun
    # cevabı hiçbir yerde yazmıyordu. Log yalnızca "odak: editable" diyordu,
    # NİYE editable dediğini değil — ve yanlış cevabın hangi kuraldan
    # geldiğini görmeden hiçbir düzeltme ölçülemez. Diktede bir satır.
    log(f"[focus] {karar} <- {neden}")
    return karar


def _windows_karar(auto, el) -> tuple[str, str]:
    """(karar, gerekçe). Gerekçe insana, karar çağırana.

    SALT OKUNUR BAYRAĞI TİPTEN ÖNCE GELİR.

    Okuduğun bir web sayfası, bir PDF, bir sohbet dökümü — hepsi
    DocumentControl'dür, ve tip listesi onları "yazılabilir" sayıyordu.
    Kartın 710 diktede yalnızca BİR kez çıkmasının sebebi buydu: alan
    dışında olduğun her an odak "editable" diyor, kart hiç düşünülmüyor,
    metin de boşluğa yapıştırılıyordu.

    Ölçüldü (Edge, metin kutusu olmayan düz bir sayfa):
        tip=DocumentControl  Value=VAR(saltokunur=True)  Text=VAR
    aynı tarayıcıdaki odaklı bir yazı kutusu ise saltokunur=False der.

    AMA BU AYRIM HENÜZ SAHADA DOĞRULANMADI. Aynı ölçümde ön plandaki
    WhatsApp penceresi de salt okunur bir DocumentControl gösterdi, ve
    orada yapıştırma ÇALIŞIYOR: eğer WhatsApp'ın mesaj kutusu odaktayken
    de aynı imzayı veriyorsa, bu kural başarılı yapıştırmanın üstüne kart
    açar — geçen sefer tersine çevrilmesinin sebebi olan arızanın ta
    kendisi. Yukarıdaki teşhis satırı tam olarak bunu ölçmek için var.
    """
    if el is None:
        return NOWHERE, "odakta denetim yok"
    try:
        top = el.GetTopLevelControl()
        if top is not None and (top.ClassName or "") in _SHELL_CLASSES:
            return NOWHERE, f"kabuk penceresi ({top.ClassName})"
    except Exception:
        pass
    try:
        tip = el.ControlTypeName
    except Exception:
        tip = "?"
    sinif = ""
    try:
        sinif = el.ClassName or ""
    except Exception:
        pass
    try:
        vp = el.GetPattern(auto.PatternId.ValuePattern)
        if vp is not None and bool(vp.IsReadOnly):
            return NOWHERE, f"{tip} kendini salt okunur ilan etti"
    except Exception:
        pass
    if el.ControlType in (auto.ControlType.EditControl,
                          auto.ControlType.DocumentControl,
                          auto.ControlType.ComboBoxControl):
        return EDITABLE, f"tip {tip}"
    for ad, pid in (("Value", auto.PatternId.ValuePattern),
                    ("Text", auto.PatternId.TextPattern)):
        try:
            if el.GetPattern(pid) is not None:
                return EDITABLE, f"{ad} deseni ({tip})"
        except Exception:
            pass
    if sinif in _SHELL_CLASSES:
        return NOWHERE, f"kabuk sınıfı ({sinif})"
    return ASSUME, f"{tip} / {sinif!r}, desen yok"


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
