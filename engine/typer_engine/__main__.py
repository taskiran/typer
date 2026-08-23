# Typer — SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Bertan Taskiran.
"""Giriş noktası.

    python -m typer_engine                  dikteyi başlat
    python -m typer_engine doctor           bu makinede neyin çalıştığını söyle
    python -m typer_engine doctor --load    modeli de yükleyip süresini ölç
    python -m typer_engine doctor --auto    kimseye soru sorma (otomasyon)

`doctor` bir takıma dağıtırken asıl işi görür: "çalışmıyor" cümlesini
hangi parçanın eksik olduğuna çeviren tek şey odur.

VE SORMAK YERİNE ÖLÇER. İki kritik parça — mikrofon ve kısayol dinleyicisi
— işletim sistemi tarafından sessizce engellenebilir, hata da vermezler.
İzin API'sine sormak dolaylı bir kanıttır; kullanıcıdan konuşmasını ve
tuşa basmasını istemek ise doğrudan olanı. `--auto` bu iki testi atlar,
çünkü karşısında kimse olmayan bir koşu onları asla geçemez.
"""
import platform
import sys
import time


def _ok(label, value, good=True):
    mark = "  ok " if good else "  !! "
    print(f"{mark}{label:<26} {value}")


def _mic_test(seconds: float, prompt: str | None) -> tuple[bool, str]:
    """Mikrofonu aç ve gerçekten bir şey duyup duymadığını söyle."""
    import numpy as np
    import sounddevice as sd
    if prompt:
        print(f"\n  {prompt}", flush=True)
    n = int(seconds * 1000 / 30)
    with sd.InputStream(samplerate=16000, channels=1, dtype="int16",
                        blocksize=480) as s:
        frames = [s.read(480)[0][:, 0].copy() for _ in range(n)]
    fr = np.concatenate(frames).astype(np.float32).reshape(-1, 480)
    # Ortalama değil TEPE: bir cümlenin içinde sessizlik de vardır, ve
    # ortalama onu kısa bir konuşmayı ölü mikrofon gibi gösterecek kadar
    # aşağı çeker.
    peak = float(np.percentile(np.sqrt((fr ** 2).mean(axis=1)), 95))
    if peak < 25:
        return False, f"tepe rms {peak:.0f} — mikrofon kapalı ya da sessiz"
    return True, f"tepe rms {peak:.0f}"


def _key_test(spec: str, label: str) -> tuple[bool, str]:
    """Kısayolu GERÇEKTEN dene: kullanıcı bassın, dinleyici duysun."""
    from typer_engine.hotkey import Hotkey
    hk = Hotkey(spec, toggle=True)
    print(f"\n  Şimdi kısayola bas — {label} (10 saniye)", flush=True)
    deadline = time.time() + 10
    while time.time() < deadline:
        if hk.is_held():
            return True, "kısayol duyuldu"
        time.sleep(0.05)
    if hk.saw_input:
        return False, "tuşlar duyuluyor ama bu kombinasyon ateşlenmedi"
    return False, ("hiçbir tuş olayı görülmedi "
                   "(basmadıysan normal; bastıysan izin sorunu)")


def doctor(load_model: bool, interactive: bool) -> int:
    from typer_engine import __version__
    from typer_engine.config import CFG, CONFIG_PATH, resolve_backend
    from typer_engine.hotkey import can_control, describe

    problems = 0
    hotkey_label = describe(CFG.get("hotkey", "ctrl+win"))
    print(f"\nTyper {__version__} — teşhis\n")
    print(f"  {platform.python_implementation()} {platform.python_version()}"
          f" / {sys.platform} / {platform.machine()}")
    print(f"  ayarlar: {CONFIG_PATH}"
          f"{'' if CONFIG_PATH.exists() else '  (yok — varsayılanlar)'}\n")

    _ok("kısayol", f"{hotkey_label}  [{CFG.get('mode', 'toggle')}]")
    _ok("dil", CFG.get("language"))

    # --- izin (yalnızca macOS'ta sorulabilir) ----------------------------
    if sys.platform == "darwin":
        v = can_control()
        if v is True:
            _ok("Erişilebilirlik", "verildi")
        elif v is False:
            _ok("Erişilebilirlik", "YOK — imlece yapıştırmak için gerekli",
                good=False)
            problems += 1
        else:
            _ok("Erişilebilirlik", "sorulamadı", good=False)

    # --- pano -------------------------------------------------------------
    try:
        import pyperclip
        keep = pyperclip.paste()
        pyperclip.copy("typer-doctor")
        good = pyperclip.paste() == "typer-doctor"
        pyperclip.copy(keep if keep is not None else "")
        _ok("pano", "okur/yazar" if good else "yazdı ama geri okunmadı", good)
        problems += 0 if good else 1
    except Exception as e:
        _ok("pano", f"kullanılamıyor: {str(e)[:60]}", good=False)
        problems += 1

    # --- odak arka ucu ----------------------------------------------------
    if sys.platform == "win32":
        try:
            import uiautomation           # noqa: F401
            _ok("odak tespiti", "uiautomation")
        except Exception:
            _ok("odak tespiti", "uiautomation yok — kart hiç çıkmaz",
                good=False)
    elif sys.platform == "darwin":
        _ok("odak tespiti", "System Events (osascript)")
    else:
        _ok("odak tespiti", "yok — her zaman yapıştırılır")

    # --- diğerlerini susturma --------------------------------------------
    if sys.platform == "win32":
        try:
            from pycaw.pycaw import AudioUtilities   # noqa: F401
            import psutil                            # noqa: F401
            _ok("diğerlerini sustur", "pycaw (uygulama başına)")
        except Exception:
            _ok("diğerlerini sustur", "pycaw yok — susturma yapılmaz",
                good=False)
    elif sys.platform == "darwin":
        _ok("diğerlerini sustur", "Music + Spotify (AppleScript)")
    else:
        _ok("diğerlerini sustur", "bu platformda yok")

    # --- konuşma modeli ---------------------------------------------------
    model, device, compute = resolve_backend(CFG)
    _ok("konuşma modeli", f"{model} ({device}/{compute})")
    if device == "cpu" and model.startswith(("large", "medium")):
        _ok("model/cihaz uyumu",
            f"{model} CPU'da dikte için fazla yavaş — \"model\": \"small\"",
            good=False)
        problems += 1
    if load_model:
        try:
            from typer_engine.stt import warm
            t0 = time.time()
            warm()
            _ok("model yükleme", f"{time.time() - t0:.1f} sn")
        except Exception as e:
            _ok("model yükleme", f"başarısız: {str(e)[:70]}", good=False)
            problems += 1

    # --- mikrofon: sorma, ölç --------------------------------------------
    try:
        import sounddevice as sd
        _ok("mikrofon", sd.query_devices(kind="input")["name"])
        heard, note = _mic_test(
            3.0 if interactive else 1.0,
            "Bir şeyler söyle — mikrofon dinleniyor (3 saniye)"
            if interactive else None)
        if interactive:
            print()
        _ok("mikrofon sinyali", note, good=heard)
        if not heard and interactive:
            # Etkileşimsiz koşuda sessizlik bir sonuç değil, yalnızca
            # kimsenin konuşmamış olması. Sorun saymak yanlış alarm olur.
            problems += 1
    except Exception as e:
        _ok("mikrofon", f"açılamadı: {str(e)[:70]}", good=False)
        problems += 1

    # --- kısayol dinleyicisi: sorma, ölç ---------------------------------
    if interactive:
        heard, note = _key_test(CFG.get("hotkey", "ctrl+win"), hotkey_label)
        print()
        _ok("kısayol dinleyicisi", note, good=heard)
        if not heard:
            problems += 1

    print()
    if problems:
        print(f"  {problems} sorun bulundu.\n")
    else:
        print("  Her şey yerinde.\n")
    return 1 if problems else 0


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] in ("-v", "--version"):
        from typer_engine import __version__
        print(f"Typer {__version__}")
        return 0
    if argv and argv[0] == "doctor":
        return doctor("--load" in argv, "--auto" not in argv)
    from typer_engine.app import main as run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
