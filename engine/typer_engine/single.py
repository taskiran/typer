# Typer — SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Bertan Taskiran.
"""Tek kopya kilidi — ikinci bir motor asla ayağa kalkmasın.

NEDEN VAR. Bu tam olarak bir kez yaşandı ve makineyi dize getirdi: art
arda yapılan testlerden geriye dört motor kaldı, her biri `large-v3`
modelini belleğinde tutuyordu — toplam 16 GB RAM ve o kadar da VRAM. Dahası
dördü birden aynı kısayolu dinliyordu, yani tuşa her basışta dört mikrofon
birden açılmaya çalışıyor ve dikte hiç çalışmıyordu. Bir kopya öldürülemeden
kalırsa, ikincisinin üstüne binmemesi gerekir.

MEKANİZMA, İŞLETİM SİSTEMİNİN KENDİ ARAÇLARIYLA. İkisi de sürecin ölümünde
çekirdek tarafından serbest bırakılır, yani sert bir kill'den sonra bile
geride kilitli bir şey kalmaz:

  Windows  adlandırılmış mutex (CreateMutexW)
  POSIX    bir dosya üzerinde flock

Bir soket bağlamak da işe yarardı ama bir port numarası uydurmak gerekirdi,
ve o port bir gün başka birinin geçici bağlantısına düşerdi. Bu ikisinde
çakışacak bir kaynak yok.
"""
import os
import sys
import tempfile

_NAME = "TyperEngineSingleInstance"
_held = None            # kilidi canlı tutan tutamak; asla çöpe atılmamalı


def claim() -> bool:
    """Kilidi al. Başka bir motor zaten çalışıyorsa False döner.

    Kilit süreç boyunca tutulur ve süreçle birlikte kendiliğinden düşer;
    ayrıca serbest bırakmaya gerek yok.
    """
    global _held
    if _held is not None:
        return True
    try:
        _held = _claim_windows() if sys.platform == "win32" else _claim_posix()
    except Exception:
        # Kilit mekanizması çalışmıyorsa dikteyi engellemek yanlış olur:
        # asıl iş çalışsın, korumadan vazgeç.
        return True
    return _held is not None


def _claim_windows():
    import ctypes
    ERROR_ALREADY_EXISTS = 183
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    # "Local\" ön eki kilidi bu oturuma bağlar: aynı makinede başka bir
    # kullanıcının kendi Typer'ı bizimkini engellememeli.
    handle = k32.CreateMutexW(None, False, f"Local\\{_NAME}")
    if not handle:
        return None
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        k32.CloseHandle(ctypes.c_void_p(handle))
        return None
    return handle          # kapatma: süreç ölünce çekirdek bırakır


def _claim_posix():
    import fcntl
    path = os.path.join(tempfile.gettempdir(), f".{_NAME}.lock")
    f = open(path, "w")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    f.write(str(os.getpid()))
    f.flush()
    return f               # açık kalmalı: kapanırsa kilit de düşer
