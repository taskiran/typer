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
           yalnızca Music kısılır — pratikte suçluların ezici
           çoğunluğu. Sistem sesini komple kısmak daha bütün bir
           çözüm gibi görünür ama kendi bliplerimizi de yutar, ki o da
           tuşun işlemediği hissini verir.

SPOTIFY BİR İSTİSNADIR ve iki işletim sisteminde de susturulmaz,
DURAKLATILIR. Susturulmuş bir Spotify çalmaya devam eder: bir dakikalık
bir dikte, şarkının bir dakikasını yutar. Kayıt bitince müzik kaldığı
yerden devam eder.

ÇÖKME KURTARMASI. Sert bir kill atexit'i çalıştırmaz ve makineyi hiçbir
açıklama olmadan sessiz bırakır. O yüzden neyi sustuğumuz susturulmuş
olduğu sürece diske yazılır, ve bir sonraki açılış onu geri koyar.

DURAKLATMA DİSKE YAZILMAZ, ve bu bilinçlidir. Kalıntı bir susturma
sessizdir ve görünmezdir: makine sebepsiz susar, kullanıcı hangi
programın yaptığını bilemez. Kalıntı bir duraklatma ise Spotify'ın kendi
arayüzünde yazar; bir tık yeter. Karşılığında kurtarma şu demek olurdu:
Typer bir sonraki açılışında kendiliğinden PLAY gönderir — ve Typer
oturum açılışıyla başlar. Sessizliği geri almak en fazla normale döner;
duraklatmayı geri almak yoktan ses yaratır, üstelik saatler önce
dinlenen bir parçayı.
"""
import atexit
import json
import os
import subprocess
import sys
import threading
import time

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


# ------------------------------------------------- Spotify (Windows tarafı)
#
# Komut, Spotify'ın kendi penceresine WM_APPCOMMAND ile gider. Ölçüldü:
# 47 (PAUSE) ve 46 (PLAY) KATI komutlardır — 47 asla müzik başlatmaz,
# 46 asla durdurmaz. 14 (PLAY_PAUSE) bir geçiştir ve bu yüzden burada
# kullanılmaz: yanlış anda gönderilse kullanıcının kendi duraklattığı
# müziği çalmaya başlardı, ki bu yapılabilecek en kaba şey.
#
# TUZAK. Komut yanlış pencereye giderse Windows onu DefWindowProc
# üzerinden kabuğa devreder, kabuk da o an aktif olan medya oturumuna
# dağıtır: Explorer'a gönderilen bir PAUSE bile Spotify'ı durdurdu.
# Yani "bir şey durdu" komutun DOĞRU uygulamaya gittiğini kanıtlamaz.
# SendMessageTimeoutW'nin sonucu (sıfırdan farklı mı) bu iki yolu ayıran
# tek işarettir, ve "sonra devam ettirelim mi" kararının tamamı ona
# dayanır.
# Küresel medya tuşunun (keybd_event) reddedilme sebebi de budur:
# hedefsizdir, bir geçiştir ve ne olduğunu geri söylemez.

_WM_APPCOMMAND = 0x0319
_CMD_PLAY = 46
_CMD_PAUSE = 47
_SMTO_ABORTIFHUNG = 0x0002
_GW_OWNER = 4

# Spotify duraklıyken pencere başlığı bunlardan biridir.
_IDLE_TITLES = {"", "Spotify", "Spotify Premium", "Spotify Free"}

if _WINDOWS:
    import ctypes
    from ctypes import wintypes as _wt

    _u32 = ctypes.WinDLL("user32", use_last_error=True)
    _WNDENUMPROC = ctypes.WINFUNCTYPE(_wt.BOOL, _wt.HWND, _wt.LPARAM)
    # lpdwResult bir PDWORD_PTR'dir: 64 bitte 8 bayt. DWORD vermek
    # çalışıyor gibi görünür ve tamponun dışına yazar.
    _ULONG_PTR = ctypes.c_size_t

    _u32.EnumWindows.argtypes = [_WNDENUMPROC, _wt.LPARAM]
    _u32.EnumWindows.restype = _wt.BOOL
    _u32.GetWindowThreadProcessId.argtypes = [_wt.HWND, ctypes.POINTER(_wt.DWORD)]
    _u32.GetWindowThreadProcessId.restype = _wt.DWORD
    _u32.IsWindow.argtypes = [_wt.HWND]
    _u32.IsWindow.restype = _wt.BOOL
    _u32.IsWindowVisible.argtypes = [_wt.HWND]
    _u32.IsWindowVisible.restype = _wt.BOOL
    _u32.GetWindow.argtypes = [_wt.HWND, _wt.UINT]
    _u32.GetWindow.restype = _wt.HWND
    _u32.GetClassNameW.argtypes = [_wt.HWND, _wt.LPWSTR, ctypes.c_int]
    _u32.GetClassNameW.restype = ctypes.c_int
    _u32.GetWindowTextLengthW.argtypes = [_wt.HWND]
    _u32.GetWindowTextLengthW.restype = ctypes.c_int
    _u32.GetWindowTextW.argtypes = [_wt.HWND, _wt.LPWSTR, ctypes.c_int]
    _u32.GetWindowTextW.restype = ctypes.c_int
    _u32.SendMessageTimeoutW.argtypes = [_wt.HWND, _wt.UINT, _wt.WPARAM,
                                         _wt.LPARAM, _wt.UINT, _wt.UINT,
                                         ctypes.POINTER(_ULONG_PTR)]
    _u32.SendMessageTimeoutW.restype = _wt.LPARAM


def _idle(title: str) -> bool:
    """Başlık "müzik durmuş" diyor mu?

    Bilinen başlıkların listesi tek başına yetmez: Spotify başlığı bir
    gün yerelleştirirse ya da yeni bir plan adı çıkarsa, o başlık
    "çalıyor" sayılır ve müzik kalıcı olarak duraklı kalırdı. Biçimsel
    kural bunu kapatıyor — çalan bir Spotify HER ZAMAN "Sanatçı - Parça"
    yazar.
    """
    return title in _IDLE_TITLES or (
        title.startswith("Spotify") and " - " not in title)


def _window_title(hwnd) -> str:
    """Pencere başlığı. Başka sürecin penceresinde bile bloklamaz:
    Windows metni çekirdekten okur, WM_GETTEXT göndermez. Ölçüldü:
    0.005 ms, yanıt vermeyen bir uygulamada bile."""
    try:
        n = _u32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        _u32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value
    except Exception:
        return ""


def _spotify_window():
    """(hwnd, başlık, pid) — Spotify'ın ana penceresi. Yoksa (None, "", 0).

    Ölçülen maliyet: ~0.30 ms.

    Pencere sınıf ADIYLA değil, ANLAMIYLA seçilir: sahipsiz ve başlığı
    olan. Spotify bir düzine pencere açar (IME'ler, başlıksız CEF
    pencereleri, GDI+ kancası); `Chrome_WidgetWin_1` sınıfı ise bu
    makinede on ayrı uygulamada birden var, yani sınıf adına güvenmek
    komutu bambaşka bir uygulamaya gönderirdi. Sınıf yalnızca eşitliği
    bozmak için kullanılır.

    GÖRÜNÜRLÜK BİR GEREKLİLİK DEĞİL, TERCİHTİR. Tepsiye gizlenmiş
    (SW_HIDE) bir pencere komutu sorunsuz işliyor — ölçüldü. Görünür
    olmayı şart koşmak, "kapatınca tepsiye in" ayarını kullanan herkeste
    özelliği sessizce kapatırdı.

    Süreç listesi 400 küsur sürecin taranmasıyla değil ADAY
    PENCERELERDEN çıkarılır: psutil.process_iter 1.08 ms sürüyor, bu
    yol 0.30 ms.
    """
    if not _WINDOWS:
        return None, "", 0
    try:
        import psutil
    except Exception:
        return None, "", 0

    adaylar = []                       # (görünür, sınıf, hwnd, başlık, pid)
    isim = {}                          # pid -> süreç adı (pid başına tek sorgu)

    def _visit(hwnd, _):
        if _u32.GetWindow(hwnd, _GW_OWNER):
            return True                     # sahipli: IME, açılır kutu
        n = _u32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True                     # başlıksız: ana pencere değil
        pid = _wt.DWORD()
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        p = pid.value
        if p not in isim:
            try:
                isim[p] = (psutil.Process(p).name() or "").lower()
            except Exception:
                isim[p] = ""
        if isim[p] != "spotify.exe":
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        _u32.GetWindowTextW(hwnd, buf, n + 1)
        cls = ctypes.create_unicode_buffer(64)
        _u32.GetClassNameW(hwnd, cls, 64)
        adaylar.append((bool(_u32.IsWindowVisible(hwnd)), cls.value,
                        hwnd, buf.value, p))
        return True

    try:
        # Geri çağrıya referans TUTULMALI: çöp toplanırsa EnumWindows
        # serbest bırakılmış belleğe atlar.
        cb = _WNDENUMPROC(_visit)
        _u32.EnumWindows(cb, 0)
    except Exception:
        return None, "", 0
    if not adaylar:
        return None, "", 0
    adaylar.sort(key=lambda a: (not a[0], not a[1].startswith("Chrome_WidgetWin")))
    _, _, hwnd, title, pid = adaylar[0]
    return hwnd, title, pid


def _still_spotify(hwnd, pid) -> bool:
    """Tutamak hâlâ AYNI Spotify penceresi mi?

    Geri alırken pencere yeniden ARANMAZ: kullanıcı kayıt sırasında
    Spotify'ı tepsiye indirirse arama onu bulamaz ve müzik duraklı
    kalırdı. Tutamağı doğrulamak yeter — ve pencere tutamakları geri
    dönüştürüldüğü için pid ile süreç adı iki ayrı kapı olarak durur.
    """
    try:
        if not _u32.IsWindow(hwnd):
            return False
        import psutil
        p = _wt.DWORD()
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        return p.value == pid and \
            (psutil.Process(pid).name() or "").lower() == "spotify.exe"
    except Exception:
        return False


_uyarilan = set()


def _neden(ok: bool, res: int, err: int):
    """Başarısızlığın sebebini bir kez logla.

    Sessizce hiçbir şey olmaması, bu depoda her yerde reddedilen şey:
    duraklatma çalışmadığında kullanıcının elinde bir iz kalmalı.
    """
    if err == 5:
        k, m = "uipi", ("[silence] Spotify yükseltilmiş yetkiyle çalışıyor; "
                        "duraklatma komutu engellendi")
    elif err == 1460:
        k, m = "hung", "[silence] Spotify komuta yanıt vermedi (zaman aşımı)"
    elif ok and not res:
        k, m = "res0", ("[silence] duraklatma komutunu Spotify'ın penceresi "
                        "işlemedi")
    else:
        return
    if k not in _uyarilan:
        _uyarilan.add(k)
        log(m)


def _appcommand(hwnd, cmd, timeout_ms: int = 30) -> bool:
    """Komutu gönder ve Spotify'ın KENDİ penceresinin işlediğini doğrula.

    Sonuç SIFIRDAN FARKLI değilse komut ya hiç işlenmedi ya da kabuk
    üzerinden başka bir oynatıcıya sızdı; ikisinde de "duraklatmadık"
    sayılır. Ayrım sıfır/sıfır-değil: "== 1" yazmak, Spotify bir gün
    başka bir doğru değer döndürürse müziği kalıcı duraklı bırakırdı.

    SendMessageW kullanılmaz — Spotify'ın arayüz ipliği takılırsa
    süresiz bloklar. Sınırı koyan ZAMAN AŞIMININ KENDİSİDİR;
    SMTO_ABORTIFHUNG ölçülebilir bir katkı yapmıyor (takılmış pencerede
    bayraklı 92.6 ms, bayraksız 93.1 ms). Bu yüzden kayıt başlangıcında
    zaman aşımı 30 ms: normal durum 0.02-0.17 ms sürüyor, yani 150 kat
    pay var, ve bu yol mikrofon açılmadan ÖNCE koşuyor.
    """
    try:
        res = _ULONG_PTR()
        ctypes.set_last_error(0)
        ok = _u32.SendMessageTimeoutW(hwnd, _WM_APPCOMMAND, _wt.WPARAM(hwnd),
                                      _wt.LPARAM(cmd << 16), _SMTO_ABORTIFHUNG,
                                      timeout_ms, ctypes.byref(res))
        if ok and res.value != 0:
            return True
        _neden(bool(ok), res.value, ctypes.get_last_error())
        return False
    except Exception:
        return False


# ---------------------------------------------------------------- Windows

class _WindowsSilencer:
    def __init__(self):
        self._muted = []          # sustuğumuz SimpleAudioVolume tutamakları
        self._pids = []
        self._paused = None       # duraklattıysak (hwnd, pid)
        self._ticked = 0.0

    @property
    def active(self) -> bool:
        # Duraklatma da sayılmalı: hiçbir oturum susturulmamış ama
        # Spotify duraklatılmışsa, Silencer.end() zamanlayıcıyı hiç
        # kurmaz ve müzik sonsuza kadar duraklı kalırdı.
        return bool(self._muted) or self._paused is not None

    @property
    def paused(self) -> bool:
        return self._paused is not None

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
        if self._muted or self._paused:
            return                              # zaten sessiz
        try:
            from pycaw.pycaw import AudioUtilities
        except Exception:
            return                              # pycaw yok: işlemsiz
        try:
            sessions = AudioUtilities.GetAllSessions()
        except Exception:
            return
        ours = self._ours()

        # Spotify ÖNCE duraklatılır, sonra kalanlar susturulur.
        # Duraklatılmış bir Spotify zaten sessizdir; ikisini birden
        # yapmak, geri alınacak iki durum demek olurdu — ve yalnızca
        # biri tutarsa geriye "çalıyor ama susturulmuş" ya da "duraklı
        # ve susturulmuş" bir Spotify kalırdı.
        atla = self._pause_spotify(sessions) if CFG.get("pause_spotify", True) \
            else set()

        for s in sessions:
            proc = getattr(s, "Process", None)
            if proc is None:
                continue                        # sistem sesleri: dokunma
            try:
                if proc.pid in ours or proc.pid in atla:
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

    def _pause_spotify(self, sessions) -> set:
        """Spotify çalıyorsa duraklat. Susturma döngüsünün atlaması
        gereken pid kümesini döndürür (duraklatma tutmadıysa boş).

        Duraklatmak, susturmanın çözemediği bir şeyi çözer: susturulmuş
        müzik ilerlemeye devam eder.
        """
        try:
            hwnd, title, pid = _spotify_window()
            if not hwnd:
                return set()                    # Spotify kapalı: hiçbir şey yapma

            # İkinci tanık: WASAPI oturumu. Ama bu tanık YALNIZCA
            # varsayılan çıkış cihazını görür. Spotify başka bir cihaza
            # çalıyorsa (bu makinede iki aktif çıkış cihazı var)
            # oturum listede hiç yoktur — o yüzden "görülemiyorsa" veto
            # etmez, yalnızca "görülüp de sessizse" veto eder. Aksi
            # hâlde kulaklık takılıyken özellik sessizce ölürdü, üstelik
            # susturma da yapılamadığı için müzik doğrudan mikrofona
            # akardı.
            gorunen = calan = False
            spot = set()
            for s in sessions:
                proc = getattr(s, "Process", None)
                if proc is None:
                    continue
                try:
                    if (proc.name() or "").lower() != "spotify.exe":
                        continue
                    spot.add(proc.pid)
                    gorunen = True
                    if s.State == 1:
                        calan = True
                except Exception:
                    continue

            if _idle(title) or (gorunen and not calan):
                return set()
            if not _appcommand(hwnd, _CMD_PAUSE):
                return set()
            self._paused = (hwnd, pid)
            return spot
        except Exception:
            return set()                        # duraklatma en iyi çabadır

    def tick(self):
        """Kayıt sürerken düzenli çağrılır; içeride 250 ms'ye kısılır.

        Kullanıcı kayıt sırasında Spotify'da elle oynat'a basarsa müzik
        artık bizim değildir. Gerekçesi ince: kullanıcı oynat'a basıp
        SONRA tekrar duraklatırsa, kayıt bitiminde okunabilen hiçbir
        sinyal bu durumu "yalnızca biz duraklattık"tan ayırmaz — ve
        müziği biz başlatırdık. Kayıt boyunca bakmak, o ayrımı
        yapabildiğimiz tek an.
        """
        if not self._paused:
            return
        now = time.monotonic()
        if now - self._ticked < 0.25:
            return
        self._ticked = now
        hwnd, _pid = self._paused
        if not _idle(_window_title(hwnd)):
            self._paused = None                 # kullanıcı devraldı

    def restore(self):
        # ÖNCE ses, SONRA çalma. Ters sırada, iki adım arasında Spotify
        # "çalıyor ama susturulmuş" olur; süreç tam orada ölürse geriye
        # ilerleyen ama duyulmayan bir şarkı kalır — teşhisi en zor
        # arıza. Bu sırada ise geriye duraklatılmış, sesi yerinde bir
        # Spotify kalır: kullanıcı görür, bir tıkla düzeltir.
        for vol in self._muted:
            try:
                vol.SetMute(0, None)
            except Exception:
                pass
        self._muted = []
        self._pids = []
        _clear_state()

        paused, self._paused = self._paused, None
        if not paused:
            return
        hwnd, pid = paused
        # BU YOLA YENİ BİR COM NESNESİ KONULAMAZ. atexit LIFO çalışır ve
        # comtypes kendi kapanışını (CoUninitialize) bizden ÖNCE yazar:
        # çıkış anında GetAllSessions() "CoInitialize has not been
        # called" ile patlar. Elde tutulan arayüz işaretçileri ve ctypes
        # çalışmaya devam eder, yenisini YARATMAK çalışmaz. "Geri
        # alırken bir de State'e bakalım" diyen biri bu yolu sessizce
        # kırar.
        if _still_spotify(hwnd, pid) and _idle(_window_title(hwnd)):
            _appcommand(hwnd, _CMD_PLAY, timeout_ms=80)

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

_MAC_PLAYERS = ("Music",)          # Spotify kısılmaz, duraklatılır

# Kontrol ile eylem TEK betikte: ikisi ayrı `osascript` çağrısı olsaydı
# aradaki boşlukta Spotify kapanabilir ve ikinci çağrı onu BAŞLATIRDI.
_MAC_PAUSE = '''
tell application "System Events"
    if not ((name of processes) contains "Spotify") then return "absent"
end tell
tell application "Spotify"
    if player state is playing then
        set tid to id of current track
        set pos to player position
        pause
        return "paused|" & tid & "|" & (pos as string)
    end if
    return "idle"
end tell
'''


def _mac_resume(tid: str, pos: float) -> str:
    """Yalnızca BİZİM duraklattığımız parçayı, bıraktığımız yerden sürdür.

    Windows'ta imkânsız olan ayrım macOS'ta bedava: kullanıcı kayıt
    sırasında elle oynatıp sonra tekrar duraklattıysa parça ya da konum
    değişmiştir, ve müzik artık bizim değildir. Konumda iki saniyelik
    pay var — duraklatma ile okuma arasında geçen zaman.
    """
    return f'''
tell application "System Events"
    if not ((name of processes) contains "Spotify") then return "absent"
end tell
tell application "Spotify"
    if player state is not paused then return "busy"
    if (id of current track) is not "{tid}" then return "other"
    set p to player position
    if p > {pos + 2:.2f} or p < {pos - 2:.2f} then return "moved"
    play
    return "resumed"
end tell
'''


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
        self._paused = None        # duraklattıysak (parça kimliği, konum)

    @property
    def active(self) -> bool:
        # Duraklatma da sayılmalı: çoğu Mac'te Apple Music açık değildir,
        # yani _saved boş kalır — ve "aktif değil" denirse geri alma
        # zamanlayıcısı hiç kurulmaz, müzik sonsuza kadar duraklı kalır.
        return bool(self._saved) or self._paused is not None

    @property
    def paused(self) -> bool:
        return self._paused is not None

    def tick(self):
        # macOS'ta yoklamaya gerek yok: sürdürme, parça kimliği ve
        # konumla zaten korunuyor. Her 250 ms'de bir osascript süreci
        # doğurmak da pahalı olurdu.
        pass

    def silence(self):
        if self._saved or self._paused:
            return
        players = _MAC_PLAYERS
        if CFG.get("pause_spotify", True):
            # `player state` macOS'ta kesin bir cevaptır; Windows'taki
            # başlık + oturum durumu sezgiselliğine gerek yok.
            out = (_osa(_MAC_PAUSE) or "").split("|")
            if len(out) == 3 and out[0] == "paused" and '"' not in out[1]:
                try:
                    self._paused = (out[1], float(out[2]))
                except ValueError:
                    self._paused = None
        else:
            players = players + ("Spotify",)   # duraklatma kapalı: eski davranış
        for app in players:
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
        # Windows'taki sırayla aynı: önce ses, sonra çalma.
        for app, vol in self._saved.items():
            if _mac_running(app):
                _osa(f'tell application "{app}" to set sound volume to {vol}')
        self._saved = {}
        _clear_state()

        paused, self._paused = self._paused, None
        if paused:
            _osa(_mac_resume(*paused))

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
            # Susturma anlıktır, duraklatma değil: PLAY'den sonra ses
            # ~45 ms'de geri geliyor, PAUSE'tan sonra oturumun sönmesi
            # ~330 ms sürüyor. 0.15 sn susturma için doğru ama duraklatma
            # için kısa — arka arkaya iki kayıt arasında müzik bir
            # fade-in yapıp geri kapanırdı, ki bu gecikmenin var oluş
            # sebebi tam olarak onu önlemek. Duraklı kalmanın maliyeti
            # yok: şarkı ilerlemiyor.
            if getattr(_BACKEND, "paused", False):
                delay = max(delay, 0.4)
            self._timer = threading.Timer(delay, self._restore)
            self._timer.daemon = True
            self._timer.start()

    def _restore(self):
        with self._lock:
            if _BACKEND is not None:
                _BACKEND.restore()
            self._timer = None

    def tick(self):
        """Kayıt sürerken çağrılır. Arka uca "kullanıcı bu sırada
        oynatıcıya elle dokundu mu" diye baktırır; ucuzdur ve içeride
        kısılır."""
        if _BACKEND is not None:
            try:
                _BACKEND.tick()
            except Exception:
                pass

    def restore_now(self):
        """Kapanış yolları için eşzamanlı geri açma — gecikme zamanlayıcısı
        bir daemon ipliğidir ve süreçle birlikte ölür, ki bu da müziği
        kısık bırakır. Her çıkıştan önce çağır."""
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
        self._restore()
