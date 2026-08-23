# Typer — SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Bertan Taskiran. Derived from backtalk,
# Copyright (C) 2026 Jared Rhodenizer.
"""Mikrofon açıkken odayı sustur.

Mikrofon hoparlörden çıkan her şeyi de duyar. Bir videonun üstüne dikte
etmek videoyu da kaydeder ve çeviri seninle onun karışımı olur.

İki işletim sistemi, iki farklı en iyi:

  Windows  Her uygulama tek tek susturulur (WASAPI oturum sesi). Kendi
           sürecimiz ve çocukları asla susturulmaz — bliplerimizi
           kesmiş oluruz. Yalnızca BİZİM susturduklarımız geri açılır:
           zaten senin sustumuş olduğun bir uygulama susturulmuş kalır.

  macOS    İşletim sistemi uygulama başına susturma sunmaz. Bu yüzden
           yalnızca Music ve Spotify kısılır — pratikte suçluların
           ezici çoğunluğu. Sistem sesini komple kısmak daha bütün bir
           çözüm gibi görünür ama kendi bliplerimizi de yutar, ki o da
           tuşun işlemediği hissini verir.

ÇÖKME KURTARMASI. Sert bir kill atexit'i çalıştırmaz ve makineyi hiçbir
açıklama olmadan sessiz bırakır. O yüzden neyi sustuğumuz susturulmuş
olduğu sürece diske yazılır, ve bir sonraki açılış onu geri koyar.
"""
import atexit
import json
import os
import subprocess
import sys
import threading

from typer_engine.bus import log
from typer_engine.config import CFG, ROOT

_STATE_FILE = os.path.join(str(ROOT), ".typer-silenced.json")

_WINDOWS = sys.platform == "win32"
_DARWIN = sys.platform == "darwin"


def _write_state(payload):
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        pass


def _take_state():
    try:
        with open(_STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    try:
        os.remove(_STATE_FILE)
    except OSError:
        pass
    return data


def _clear_state():
    try:
        os.remove(_STATE_FILE)
    except OSError:
        pass


# ---------------------------------------------------------------- Windows

class _WindowsSilencer:
    def __init__(self):
        self._muted = []          # sustuğumuz SimpleAudioVolume tutamakları
        self._pids = []

    @property
    def active(self) -> bool:
        return bool(self._muted)

    @staticmethod
    def _ours() -> set:
        pids = {os.getpid()}
        try:
            import psutil
            pids |= {c.pid for c in
                     psutil.Process(os.getpid()).children(recursive=True)}
        except Exception:
            pass
        return pids

    def _remember(self):
        # Adlar pid'lerin yanına yazılır çünkü Windows pid'leri geri
        # dönüştürür: yeniden başlattıktan sonra 4312 bambaşka biridir.
        try:
            import psutil
            rows = []
            for pid in self._pids:
                try:
                    rows.append({"pid": pid, "name": psutil.Process(pid).name()})
                except Exception:
                    pass
            _write_state({"platform": "win32", "apps": rows})
        except Exception:
            pass

    def silence(self):
        if self._muted:
            return                              # zaten sessiz
        try:
            from pycaw.pycaw import AudioUtilities
        except Exception:
            return                              # pycaw yok: işlemsiz
        ours = self._ours()
        try:
            sessions = AudioUtilities.GetAllSessions()
        except Exception:
            return
        for s in sessions:
            proc = getattr(s, "Process", None)
            if proc is None:
                continue                        # sistem sesleri: dokunma
            try:
                if proc.pid in ours:
                    continue
                vol = s.SimpleAudioVolume
                if vol.GetMute():
                    continue                    # kullanıcı zaten susturmuş
                vol.SetMute(1, None)
                self._muted.append(vol)
                self._pids.append(proc.pid)
            except Exception:
                continue                        # oturum tarama sırasında öldü
        if self._muted:
            self._remember()

    def restore(self):
        for vol in self._muted:
            try:
                vol.SetMute(0, None)
            except Exception:
                pass
        self._muted = []
        self._pids = []
        _clear_state()

    @staticmethod
    def recover(rows):
        try:
            from pycaw.pycaw import AudioUtilities
            # proc.name() pycaw'ın verdiği psutil.Process'ten gelir, o
            # yüzden psutil'i ayrıca import etmeye gerek yok.
            want = {r["pid"]: r.get("name") for r in rows}
            n = 0
            for s in AudioUtilities.GetAllSessions():
                proc = getattr(s, "Process", None)
                if proc is None or proc.pid not in want:
                    continue
                try:
                    if proc.name() != want[proc.pid]:
                        continue          # pid geri dönüşmüş: bizim uygulama değil
                    s.SimpleAudioVolume.SetMute(0, None)
                    n += 1
                except Exception:
                    pass
            if n:
                log(f"[silence] çökmeden kalan {n} uygulama geri açıldı")
        except Exception:
            pass


# ------------------------------------------------------------------ macOS

_MAC_PLAYERS = ("Spotify", "Music")


def _osa(script: str, timeout: float = 2.0):
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except Exception:
        return None


def _mac_running(app: str) -> bool:
    # System Events üzerinden sormak GÜVENLİDİR. `tell application "Music"`
    # demek uygulamayı BAŞLATIR, ve mikrofona bastığın için müzik çalarının
    # açılması kabul edilemez.
    out = _osa(f'tell application "System Events" to '
               f'(name of processes) contains "{app}"')
    return out == "true"


class _MacSilencer:
    def __init__(self):
        self._saved = {}

    @property
    def active(self) -> bool:
        return bool(self._saved)

    def silence(self):
        if self._saved:
            return
        for app in _MAC_PLAYERS:
            if not _mac_running(app):
                continue
            v = _osa(f'tell application "{app}" to get sound volume')
            try:
                vol = int(v)
            except (TypeError, ValueError):
                continue
            if vol <= 0:
                continue                       # zaten kısık: dokunma
            self._saved[app] = vol
            _osa(f'tell application "{app}" to set sound volume to 0')
        if self._saved:
            _write_state({"platform": "darwin", "apps": self._saved})

    def restore(self):
        for app, vol in self._saved.items():
            if _mac_running(app):
                _osa(f'tell application "{app}" to set sound volume to {vol}')
        self._saved = {}
        _clear_state()

    @staticmethod
    def recover(apps):
        n = 0
        for app, vol in (apps or {}).items():
            if _mac_running(app):
                _osa(f'tell application "{app}" to set sound volume to {vol}')
                n += 1
        if n:
            log(f"[silence] çökmeden kalan {n} oynatıcı geri açıldı")


_BACKEND = (_WindowsSilencer() if _WINDOWS
            else _MacSilencer() if _DARWIN else None)


def _recover_previous():
    data = _take_state()
    if not data:
        return
    if data.get("platform") == "win32" and _WINDOWS:
        _WindowsSilencer.recover(data.get("apps") or [])
    elif data.get("platform") == "darwin" and _DARWIN:
        _MacSilencer.recover(data.get("apps") or {})


if _BACKEND is not None:
    atexit.register(_BACKEND.restore)
    # atexit sert bir kill'de hiç çalışmaz, o yüzden önceki koşudan kalan
    # artıklar burada, import anında, başka bir şey susturmadan önce
    # temizlenir.
    _recover_previous()


class Silencer:
    """Aç/kapa. Geri açma GECİKMELİDİR: kısa bir kayıttan hemen sonra
    gelen ikinci bir kayıt arada müziği bir anlığına geri getirirse bu
    sessizlikten daha rahatsız edicidir."""

    def __init__(self):
        self._lock = threading.Lock()
        self._timer = None

    def start(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            if _BACKEND is None or not CFG.get("mute_others", True):
                return
            _BACKEND.silence()

    def end(self, delay: float = 0.15):
        with self._lock:
            if _BACKEND is None or not _BACKEND.active:
                return
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(delay, self._restore)
            self._timer.daemon = True
            self._timer.start()

    def _restore(self):
        with self._lock:
            if _BACKEND is not None:
                _BACKEND.restore()
            self._timer = None

    def restore_now(self):
        """Kapanış yolları için eşzamanlı geri açma — gecikme zamanlayıcısı
        bir daemon ipliğidir ve süreçle birlikte ölür, ki bu da müziği
        kısık bırakır. Her çıkıştan önce çağır."""
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
        self._restore()
