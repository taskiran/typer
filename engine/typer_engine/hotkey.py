# Typer — SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Bertan Taskiran. Derived from backtalk,
# Copyright (C) 2026 Jared Rhodenizer.
"""Küresel kısayol dinleyicisi.

İki şekli var, tek arayüzü:

  toggle (varsayılan) bir bas aç, bir bas kapat. Arada tuş serbesttir,
                      yani konuşurken iki elin de klavyede kalır.
  hold                mikrofon yalnızca tuş basılıyken açıktır.

Ne olursa olsun aşağısı yalnızca is_held() sorar, yani kayıt döngüsünün
hangi şeklin çalıştığını bilmesine gerek yoktur.

TUŞ TEKRARI TUZAĞI (her acemi kurulum bunun üzerinde ölür): işletim
sistemi bir tuş basılı durduğu sürece on_press olaylarını ARKA ARKAYA
üretir. Aşağıdaki _armed bayrağı olmadan her tekrar taze bir basış gibi
okunur ve toggle, parmağını tuttuğun sürece açılıp kapanıp durur.

İZİN NOTU. macOS iki ayrı izin ister ve ikisi de SESSİZCE reddedilir —
hata yok, olay da yok. Girdi İzleme tuşları duymak, Erişilebilirlik de
Cmd+V göndermek için gerekir. İkincisi işletim sistemine sorulabiliyor
(can_control); birincisi ise ölçülüyor (saw_input), çünkü ölçmek
soramamaktan iyidir. Windows'ta kutudan çıktığı gibi çalışır; bazı
Linux masaüstlerinde kullanıcının input grubunda olması ya da bir X11
oturumu gerekir.
"""
import ctypes
import sys
import threading

from pynput import keyboard

from typer_engine.bus import log


# --------------------------------------------------------------- izinler

def can_control() -> bool | None:
    """macOS Erişilebilirlik izni verilmiş mi? Başka platformlarda None.

    AXIsProcessTrusted() argümansızdır ve doğrudan Boolean döner — yani
    doğru okunması için hiçbir sabite güvenmek gerekmiyor. Yapıştırmayı
    (sentetik Cmd+V) mümkün kılan izin budur.

    GİRDİ İZLEME için buranın bir eşi YOK, ve bu kasten böyle: onu soran
    IOKit çağrısı, elimde doğrulayabileceğim bir SDK başlığı olmadan
    yanlış yazılması kolay bir numaralandırma sabiti istiyor, ve yanlış
    bir sabit "izin yok" diye bağıran sağlıklı bir kuruluma yol açardı.
    Onun yerine ölçüm var: dinleyici gerçekten tuş görüyor mu (aşağıda
    Hotkey.saw_input, ve `doctor` içinde tuşa basmanı isteyen test).
    Gerçek sinyal, adı yanlış hatırlanmış bir sabitten iyidir.
    """
    if sys.platform != "darwin":
        return None
    try:
        appserv = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework"
            "/ApplicationServices")
        appserv.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(appserv.AXIsProcessTrusted())
    except Exception:
        return None


def warn_if_blocked():
    """Eksik izni bir kez, adıyla sanıyla söyle."""
    if can_control() is False:
        log("[hotkey] macOS Erişilebilirlik izni yok — metin imlece "
            "yapıştırılamaz (kart yine de çıkar). Sistem Ayarları > "
            "Gizlilik ve Güvenlik > Erişilebilirlik'ten bu uygulamayı ekle.")


# ------------------------------------------------------------ tuş adları

def resolve_key(name: str):
    """'home' / 'f13' / 'right_alt' / tek karakter -> pynput tuşu."""
    name = (name or "home").strip().lower()
    if len(name) == 1:
        return keyboard.KeyCode.from_char(name)
    # İnsanca adlar -> pynput'un adları. pynput sağ seçenek tuşuna
    # right_alt değil alt_r der; belgeler insanca konuşur, bu harita
    # çevirir. (Sahada yakalandı: right_alt sessizce home'a düşerdi, ki
    # Mac dizüstülerinde öyle bir tuş yok — kısayol sağlıklı görünüp
    # hiç ateşlenmiyordu.)
    aliases = {
        "right_alt": "alt_r", "left_alt": "alt_l",
        "right_option": "alt_r", "left_option": "alt_l",
        "right_ctrl": "ctrl_r", "left_ctrl": "ctrl_l",
        "right_cmd": "cmd_r", "left_cmd": "cmd_l",
        "right_shift": "shift_r", "left_shift": "shift_l",
    }
    name = aliases.get(name, name)
    try:
        return getattr(keyboard.Key, name)
    except AttributeError:
        log(f"[hotkey] bilinmeyen tuş {name!r} — 'home' varsayılıyor")
        return keyboard.Key.home


# Bir değiştiricinin sağ ve sol sürümü insana göre aynı değiştiricidir,
# o yüzden karşılaştırılmadan önce tek bir aile adına indirgenirler.
def _mod_families():
    fam = {}
    for family, names in (
        ("win",   ("cmd", "cmd_l", "cmd_r")),
        ("ctrl",  ("ctrl", "ctrl_l", "ctrl_r")),
        ("alt",   ("alt", "alt_l", "alt_r", "alt_gr")),
        ("shift", ("shift", "shift_l", "shift_r")),
    ):
        for n in names:
            k = getattr(keyboard.Key, n, None)
            if k is not None:
                fam[k] = family
    return fam


_MOD_FAMILY = _mod_families()
_MOD_ALIASES = {"win": "win", "super": "win", "meta": "win", "cmd": "win",
                "command": "win", "windows": "win",
                "ctrl": "ctrl", "control": "ctrl",
                "alt": "alt", "option": "alt",
                "shift": "shift"}

# Çıplak şekiller: "alt" iki alt tuşundan herhangi biri demektir,
# "right_alt" yalnızca sağdaki. Kombinasyon eşleşirken sol/sağ ayrımını
# yalnızca çıplak şekiller yok sayar.
_GENERIC_MODS = {k for k in (getattr(keyboard.Key, n, None)
                             for n in ("cmd", "ctrl", "alt", "shift"))
                 if k is not None}


def same_key(k, ref) -> bool:
    """Bu olay tuşu, ayarlananı karşılıyor mu? Çıplak bir değiştirici
    ("alt") iki yanı da kabul eder; belirli olan ("right_alt") etmez."""
    if k == ref:
        return True
    if ref in _GENERIC_MODS:
        return _MOD_FAMILY.get(k) is not None and \
            _MOD_FAMILY.get(k) == _MOD_FAMILY.get(ref)
    return False


def parse_combo(spec: str):
    """spec -> (gereken değiştirici aileleri, tetik tuşu ya da None).

      "home"      -> (frozenset(),        <home>)
      "win+6"     -> ({"win"},            <'6'>)
      "ctrl+win"  -> ({"ctrl", "win"},    None)      yalnızca değiştirici

    Yalnızca değiştiricilerden oluşan bir kombinasyonun tetik tuşu yoktur:
    sonuncusu aşağı indiği anda, hangi sırada basıldıklarından bağımsız
    olarak ateşlenir. '+', '-' ve boşluk ayırıcı olarak eşdeğerdir.
    """
    spec = (spec or "home").strip().lower()
    parts = [p for p in spec.replace("-", "+").replace(" ", "+").split("+") if p]
    if not parts:
        parts = ["home"]
    mods, plain = set(), []
    for p in parts:
        fam = _MOD_ALIASES.get(p)
        if fam:
            mods.add(fam)
        else:
            plain.append(p)
    if len(plain) > 1:
        log(f"[hotkey] {spec!r} birden fazla normal tuş adlıyor "
            f"({plain}) — {plain[-1]!r} kullanılıyor")
    trigger = resolve_key(plain[-1]) if plain else None
    return frozenset(mods), trigger


def describe(spec: str) -> str:
    """Kombinasyonu BU işletim sisteminde okunduğu gibi yaz. Aynı
    "ctrl+win" satırı Windows'ta Ctrl+Win, Mac'te Ctrl+Command demektir;
    kullanıcıya hangisi olduğunu söylemek gerekir."""
    mods, trigger = parse_combo(spec)
    mac = sys.platform == "darwin"
    labels = {"ctrl": "Ctrl", "alt": "Option" if mac else "Alt",
              "shift": "Shift", "win": "Command" if mac else "Win"}
    out = [labels[m] for m in ("ctrl", "alt", "shift", "win") if m in mods]
    if trigger is not None:
        name = getattr(trigger, "name", None) or getattr(trigger, "char", "?")
        out.append(str(name).replace("_", " ").title())
    return " + ".join(out) or spec


class Hotkey:
    """Kısayolu ve durumunu sahiplenir; dinleyici kendi ipliğinde koşar."""

    def __init__(self, key="ctrl+win", toggle=True):
        if isinstance(key, str):
            self._required, self._trigger = parse_combo(key)
        else:
            self._required, self._trigger = frozenset(), key
        self._toggle = bool(toggle)
        self._held = False
        self._armed = False         # kombinasyonun tamamı şu an basılı
        self._trigger_down = False
        self._mods_down = set()     # basılı değiştirici aileleri
        self._press_evt = threading.Event()
        self._seen_any = False      # hiç tuş olayı gördü mü (izin teşhisi)
        self._listener = keyboard.Listener(on_press=self._on_press,
                                           on_release=self._on_release)
        self._listener.daemon = True
        self._listener.start()

    @property
    def saw_input(self) -> bool:
        """Dinleyici bu ana kadar tek bir tuş bile gördü mü? macOS'ta izin
        verilmemişse hiçbir zaman görmez, ve bu "çalışmıyor"un sessiz
        halidir — hata yok, olay da yok."""
        return self._seen_any

    def _complete(self) -> bool:
        """Kombinasyonun adladığı her tuş şu an basılı mı? Fazladan
        değiştirici sorun değil — kimse "ctrl+win" derken "ve başka
        hiçbir şey" demiyor."""
        if not self._required <= self._mods_down:
            return False
        return self._trigger is None or self._trigger_down

    def _on_press(self, k):
        self._seen_any = True
        fam = _MOD_FAMILY.get(k)
        if fam:
            self._mods_down.add(fam)
        if self._trigger is not None and same_key(k, self._trigger):
            self._trigger_down = True
        if not self._complete() or self._armed:
            return                  # tuş tekrarı tuzağı: bkz. modül başlığı
        self._armed = True
        if self._toggle:
            self._held = not self._held
            if self._held:
                self._press_evt.set()
        else:
            self._held = True
            self._press_evt.set()

    def _on_release(self, k):
        fam = _MOD_FAMILY.get(k)
        if fam:
            self._mods_down.discard(fam)
        if self._trigger is not None and same_key(k, self._trigger):
            self._trigger_down = False
        if self._armed and not self._complete():
            self._armed = False          # yeniden ateşlemeye hazır
            if not self._toggle:
                self._held = False       # hold: bırakmak bitirir

    def stop(self):
        """Kaydı dışarıdan kapat (emniyet sınırı, kapanış)."""
        self._held = False

    def modifiers_clear(self) -> bool:
        """Bu kombinasyonun değiştiricilerinden hiçbiri hâlâ basılı
        değilse True. Kullanıcı hâlâ Win'e yaslanırken gönderilen bir
        Ctrl+V karşı tarafa Ctrl+Win+V olarak varır, o yüzden
        yapıştıranlar önce bunu bekler."""
        return not (self._required & self._mods_down)

    def wait_press(self):
        """Tuş AŞAĞI inene kadar blokla (fiziksel basış başına bir olay)."""
        self._press_evt.wait()
        self._press_evt.clear()

    def is_held(self) -> bool:
        return self._held
