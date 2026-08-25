# Typer — SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Bertan Taskiran. Derived from backtalk,
# Copyright (C) 2026 Jared Rhodenizer.
"""Döngü — tuşa bas, konuş, tekrar bas, kelimeler imlecine düşsün."""
import sys
import threading
import time

from typer_engine import blips, focus, meter, paste, single
from typer_engine.bus import emit, log
from typer_engine.config import CFG
from typer_engine.hotkey import Hotkey, describe, warn_if_blocked
from typer_engine.silence import Silencer
from typer_engine.stt import BACKEND, record, warm

_METER_INTERVAL = 1 / 30      # saniyede 30 kare 60fps'lik bir ölçere yeter


class Typer:
    def __init__(self):
        key = CFG.get("hotkey") or "ctrl+win"
        toggle = (CFG.get("mode") or "toggle") == "toggle"
        self._max_s = float(CFG.get("max_seconds", 180))
        self._last_meter = 0.0

        warn_if_blocked()
        self.hotkey = Hotkey(key, toggle=toggle)
        self.silencer = Silencer()

        emit("idle")
        # Kısayolun BU işletim sistemindeki okunuşunu arayüze bildir, ki
        # tepsi "ctrl+win" yerine Mac'te "Ctrl + Command" yazabilsin.
        # Arayüz "ready"i pencereye iletmez, yalnızca etiketi alır.
        emit("ready", text=f"{describe(key)}  "
                           f"[{'toggle' if toggle else 'hold'}]")
        log(f"[typer] hazır — {describe(key)} "
            f"({'toggle' if toggle else 'hold'})")

        # Model arka planda ısıtılır: ilk basış yükleme bedelini ödemesin.
        # İlk indirme large-v3 için ~1.5 GB ve dakikalar sürebilir, o
        # yüzden burası bloklamaz — tuş o sırada da basılabilir, yalnızca
        # ilk çeviri model gelene kadar bekler.
        threading.Thread(target=self._warm, daemon=True).start()
        threading.Thread(target=self._watch_input, daemon=True).start()

    def _warm(self):
        try:
            warm()
            log(f"[typer] konuşma modeli: {BACKEND['model']} "
                f"({BACKEND['device']}/{BACKEND['compute']})")
        except Exception as e:
            log(f"[typer] model yüklenemedi: {e!r}")
            emit("error", text="Konuşma modeli yüklenemedi. "
                               "logs/engine.log dosyasına bak.")

    def _watch_input(self):
        """İzin kontrolü "verildi" dese bile dinleyici sağır olabilir.

        Yalnızca Windows DIŞINDA çalışır: orada kuresel dinleyici kutudan
        çıktığı gibi çalışır ve klavyeye bir dakika dokunmamış birine
        "engelleniyor olabilir" demek yanlış alarmdan başka bir şey
        değildir. Engellenmenin gerçek bir olasılık olduğu yerlerde ise
        bu satır, sessizce hiçbir şey olmamasının tek açıklamasıdır.
        """
        if sys.platform == "win32":
            return
        time.sleep(60)
        if not self.hotkey.saw_input:
            log("[typer] bir dakikadır hiçbir tuş olayı görülmedi. "
                "Klavyeye dokunduysan kısayol dinleyicisi işletim sistemi "
                "tarafından engelleniyor demektir (macOS: Girdi İzleme "
                "izni; Linux: input grubu ya da X11 oturumu).")

    # --------------------------------------------------------- geri aramalar

    def _on_frame(self, mono):
        """Kare başına ölçer beslemesi. Kısıtlıdır: arayüz değerler
        arasında yumuşatma yapıyor, saniyede ~30'dan fazlası yalnızca
        boru trafiği satın alır."""
        # Kayıt sürerken oynatıcıyı yokla: kullanıcı bu sırada Spotify'da
        # elle oynat'a bastıysa müzik artık bizim değildir ve kayıt
        # bitince ona dokunmamalıyız. İçeride 250 ms'ye kısılıyor,
        # kısıtlamadan ÖNCE çağrılıyor ki ölçer kısıtı onu da yutmasın.
        self.silencer.tick()
        now = time.time()
        if now - self._last_meter < _METER_INTERVAL:
            return
        self._last_meter = now
        emit("listening", meter.level(mono), bands=meter.spectrum(mono))

    def _on_stop(self):
        """Mikrofon şimdi kapandı: ölçer sussun, kapanış blibi ŞİMDİ çalsın.

        Kapsül burada KAPANMAZ, "çeviriyor"a geçer. Uzun bir diktede
        çeviri saniyeler sürüyor ve kapsülün o an yok olması, kelimelerin
        kaybolduğu izlenimini veriyordu — tuş işledi mi işlemedi mi belli
        değil. Artık işaret ve bir yükleniyor halkası kalıyor; kapsül
        metin yapıştırıldığında kapanıyor.

        Blip yine ŞİMDİ çalar, çevirinin sonunda değil: kaydın bittiği an
        odur, ve sesi geciktirmek tuşu ölü hissettirir.
        """
        emit("thinking")
        blips.end()

    # ---------------------------------------------------------------- döngü

    def run(self):
        while True:
            try:
                self.hotkey.wait_press()
                self._capture()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                log(f"[typer] hata: {e!r}")
                emit("idle")

    def _capture(self):
        blips.start()                    # mikrofon açılmadan ÖNCE biter
        emit("listening", 0.0)
        meter.reset()                    # ölçer her kayıtta yeniden ayarlanır
        started = time.time()
        try:
            # Susturma try'ın İÇİNDE: dışarıda kalırsa buradan çıkan bir
            # istisna `finally: silencer.end()` satırını hiç çalıştırmaz
            # ve her şey susturulmuş, Spotify duraklamış kalır — bir
            # sonraki başarılı kayda kadar.
            self.silencer.start()        # önce odayı sustur
            text = record(self.hotkey.is_held, max_s=self._max_s,
                          on_frame=self._on_frame, on_stop=self._on_stop)
        finally:
            self.silencer.end()
            # EMNİYET SINIRI TUZAĞI: toggle kipinde kayıt max_seconds'a
            # çarparak biterse tuş hâlâ "basılı" sayılır, ve bir sonraki
            # basış onu yalnızca kapatır — kullanıcıya kısayol bir kez
            # ölmüş gibi görünür. Her kayıttan sonra durumu sıfırlamak
            # bunu imkânsız kılar; normal akışta zaten işlemsizdir.
            if time.time() - started >= self._max_s:
                log(f"[typer] {self._max_s:.0f} sn sınırına çarpıldı — "
                    f"kayıt kapatıldı")
            self.hotkey.stop()

        if not text:
            emit("idle")
            return
        log(f"[typer] {text}")

        # HER ZAMAN yapıştır, odak kontrolü ne düşünürse düşünsün. Hiçbir
        # şeyin kabul etmediği bir yere yapıştırmak bedavadır; kontrol
        # yanıldığı için YAPIŞTIRMAMAK ise kullanıcıya cümlesine mal olur
        # — ve sahada yanıldı: WhatsApp mesaj kutusu WinUI kabuğunun
        # içindeki bir Chromium girdisidir ve yazılabilir olduğunu
        # bildirmez, yani dikte hiçbir şey yapmıyordu.
        #
        # Odak kontrolü yapıştırmadan SONRA koşar, çünkü yapıştırmak odağı
        # değiştirmez ve macOS'ta bu kontrol bir osascript süreci demektir:
        # sonraya almak kelimelerin ekrana ~300 ms daha erken düşmesini
        # sağlar. Kontrol yalnızca kartı GÖSTERİP göstermeyeceğine karar
        # verir, asla yazılıp yazılmayacağına.
        paste.send(text, self.hotkey)
        kind = focus.kind()
        log(f"[typer] odak: {kind}")

        if kind == focus.NOWHERE:
            # Gerçekten yazacak yer yok. Kelimeleri kartta tut.
            emit("preview", 0.0, text)
        else:
            # Boştayken de metni taşı: yapıştırmanın hiçbir yere düşmediği
            # ortaya çıkarsa tepsi menüsü onu geri verebilsin.
            emit("idle", 0.0, text)

    def shutdown(self):
        self.silencer.restore_now()
        emit("idle")


def main():
    # Model belleğe girmeden ÖNCE: ikinci bir motor, ilkinin üstüne
    # birkaç gigabaytlık bir model daha yükler ve aynı kısayolu dinleyip
    # her basışta iki mikrofon birden açmaya çalışır.
    if not single.claim():
        log("[typer] başka bir Typer motoru zaten çalışıyor — bu kopya "
            "çıkıyor. (Öyle olmadığını düşünüyorsan görev yöneticisinde "
            "'typer_engine' geçen python süreçlerine bak.)")
        return

    app = Typer()
    # Arayüz sert bir şekilde ölürse biz de inelim — ama önce sustuğumuz
    # uygulamaları geri açarak. Sessiz kalmış bir makine, hangi programın
    # yaptığı belli olmadığı için teşhis edilmesi en zor arızalardan biri.
    single.watch_parent(on_death=app.shutdown)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()
        log("[typer] kapandı")
