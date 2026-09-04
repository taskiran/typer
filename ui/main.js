/*
 * Typer — masaüstü arayüzü.
 *
 * Bu süreç iki iş yapar ve üçüncüsünü yapmaz.
 *
 *   1. Motoru kendi çocuğu olarak başlatır ve hayatta tutar. Kullanıcının
 *      bir terminal açması, bir .bat dosyasına çift tıklaması ya da
 *      herhangi bir komut ezberlemesi gerekmez.
 *   2. Motorun stdout'undan gelen durum satırlarını okuyup kapsülü çizer.
 *
 * Yapmadığı şey: kısayolu dinlemek, mikrofonu açmak, metni yapıştırmak.
 * Hepsi motorun işi. Arayüz kapansa bile dikte çalışmaya devam eder —
 * sadece görünmez olur. Bu ayrım kasten böyle: ekranda bir şey çizmek,
 * çalışan bir diktenin ön koşulu olmamalı.
 *
 * Pencere yalnızca konuşurken ya da metin bir yere düşemediğinde
 * görünür. Boşta tamamen gizlidir — görev çubuğunda girdisi, çerçevesi
 * ve gölgesi yoktur, tıklamaları geçirir.
 */
'use strict';

const { app, BrowserWindow, Tray, Menu, screen, nativeImage, shell,
        ipcMain, clipboard } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

// Her şeyden önce adlandırılır: bu ad Windows başlangıç girdisine ve
// Görev Yöneticisi etiketine geçer. Varsayılan "electron.app.Electron"dur,
// ve altı ay sonra kendi makinende bulmak istemeyeceğin şey tam olarak
// açıklanamayan bir başlangıç girdisidir.
app.setName('Typer');

const UI_DIR = __dirname;
const ROOT = path.resolve(UI_DIR, '..');
const ENGINE_DIR = path.join(ROOT, 'engine');
const LOG_DIR = path.join(ROOT, 'logs');
const CONFIG_PATH = path.join(ROOT, 'typer.json');
const IS_MAC = process.platform === 'darwin';
const IS_WIN = process.platform === 'win32';

const UI_DEFAULTS = {
  start_at_login: true,
  // Motoru başlatan komut. null ise sırayla uv ve sistem Python'u denenir.
  // Elle vermek istersen dizi olarak: ["/yol/python", "-m", "typer_engine"]
  engine_command: null,
};

function readJSON(p) {
  try {
    // UTF-8 BOM JSON.parse için geçersizdir ve yazan taraf bir gün onu
    // ekleyecektir — bir Windows aracı, bir düzenleyici, bir elle
    // düzeltme. Sessizce boşa düşmektense soy.
    return JSON.parse(fs.readFileSync(p, 'utf8').replace(/^﻿/, ''));
  } catch (e) {
    return null;
  }
}

// İLK ÇALIŞTIRMA: kişisel ayar dosyası depoda değil (kimsenin kendi
// kısayolu başkasının deposuna düşmesin diye), o yüzden örnekten
// kopyalanarak açılır. Bu, tepside "Ayarları aç" diyen birinin karşısına
// gerçek bir dosya çıkmasını garanti eder — varsayılanlar zaten aynı,
// ama düzenlenecek bir şey olması başka.
if (!fs.existsSync(CONFIG_PATH)) {
  try {
    const example = path.join(ROOT, 'typer.example.json');
    if (fs.existsSync(example)) fs.copyFileSync(example, CONFIG_PATH);
  } catch (e) {
    log(`typer.json oluşturulamadı: ${e.message}`);
  }
}

const CFG = Object.assign({}, UI_DEFAULTS, readJSON(CONFIG_PATH) || {});

/* Hata ayıklama bayrakları:
 *   --no-engine   motoru başlatma (zaten elle çalıştırdıysan)
 *   --shot <png>  pencereyi yakala ve çık
 */
const ARGV = process.argv.slice(1);
const flag = (n) => ARGV.includes('--' + n);
const flagVal = (n) => { const i = ARGV.indexOf('--' + n); return i >= 0 ? ARGV[i + 1] : null; };
const SHOT = flagVal('shot');
const CAPTURE = !!SHOT;

// Arayüzün konsolu yok — yanlış davrandığında nedenini söyleyebilecek
// tek yer bu dosya.
function log(msg) {
  try {
    fs.mkdirSync(LOG_DIR, { recursive: true });
    fs.appendFileSync(path.join(LOG_DIR, 'ui.log'),
      `${new Date().toISOString()}  ${msg}\n`);
  } catch (_) {}
}

/* ------------------------------------------------------------------ */
/* motor                                                               */
/* ------------------------------------------------------------------ */

const PREFIX = '@TYPER ';

let engine = null;
let engineAlive = false;
// Motorun BU isletim sisteminde okudugu kisayol ('Ctrl + Command' gibi).
// Motor 'ready' ile bildirene kadar ham ayar degeri gosterilir.
let hotkeyLabel = CFG.hotkey || 'ctrl+win';
let restartTimer = null;
let candidates = [];
let candidateIndex = 0;
let lockedCommand = null;      // beş saniye yaşayan ilk komut

function engineCandidates() {
  if (Array.isArray(CFG.engine_command) && CFG.engine_command.length) {
    return [CFG.engine_command];
  }
  const out = [];
  // uv kendini ~/.local/bin'e kurar, ve oturumla başlatılan bir sürecin
  // PATH'inde orası mutlaka olmaz. Önce tam yolu dene.
  const uvLocal = path.join(app.getPath('home'), '.local', 'bin',
                            IS_WIN ? 'uv.exe' : 'uv');
  if (fs.existsSync(uvLocal)) out.push([uvLocal, 'run', 'python', '-m', 'typer_engine']);
  out.push(['uv', 'run', 'python', '-m', 'typer_engine']);
  // uv yoksa: sanal ortamı kullanıcı kendi kurmuş olabilir.
  out.push([IS_WIN ? 'py' : 'python3', '-u', '-m', 'typer_engine']);
  return out;
}

function startEngine() {
  if (flag('no-engine')) { engineAlive = true; return; }
  if (engine) return;

  if (!candidates.length) { candidates = engineCandidates(); candidateIndex = 0; }
  const cmd = lockedCommand || candidates[candidateIndex];
  if (!cmd) {
    log('motor başlatılamadı: denenecek komut kalmadı');
    refreshTray('motor başlatılamadı — logs/ui.log');
    return;
  }

  fs.mkdirSync(LOG_DIR, { recursive: true });
  // stdout protokol kanalıdır ve boruda kalır. stderr insan içindir ve
  // doğrudan günlüğe akar — bağımlılıkların yığın izleri de dahil.
  const errFd = fs.openSync(path.join(LOG_DIR, 'engine.log'), 'a');

  const started = Date.now();
  log(`motor başlatılıyor: ${cmd.join(' ')}`);
  let p;
  try {
    p = spawn(cmd[0], cmd.slice(1), {
      cwd: ENGINE_DIR,
      env: childEnv(),
      windowsHide: true,             // oturum açılışında konsol parlaması yok
      // POSIX'te kendi süreç grubunu alsın, ki çıkarken TÜM ağacı
      // öldürebilelim: `uv run python` iki süreçtir ve yalnızca üsttekini
      // öldürmek mikrofonu ve kısayolu ayakta bırakır.
      detached: !IS_WIN,
      // stdin bir BORU, ve icine hicbir sey yazilmiyor. Tek isi
      // olmek: bu surec oldugunde boru kapanir, motor da EOF'u
      // gorup kendini indirir. Windows'ta cocuk surecler
      // ebeveynleriyle birlikte olmez, ve arayuzu gorev
      // yoneticisinden kapatmak modeli ve kisayolu elinde tutan
      // gorunmez bir motor birakirdi.
      stdio: ['pipe', 'pipe', errFd],
    });
  } catch (e) {
    log(`spawn hatası: ${e.message}`);
    advanceCandidate();
    return;
  }

  engine = p;
  engineAlive = true;
  refreshTray();

  let buf = '';
  p.stdout.on('data', (chunk) => {
    buf += chunk.toString('utf8');
    let nl;
    while ((nl = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, nl).trimEnd();
      buf = buf.slice(nl + 1);
      if (line.startsWith(PREFIX)) {
        try { onState(JSON.parse(line.slice(PREFIX.length))); }
        catch (e) { log(`bozuk durum satırı: ${line.slice(0, 120)}`); }
      } else if (line) {
        // Ön eki olmayan her şey bir bağımlılığın çıktısıdır.
        log(`motor: ${line.slice(0, 300)}`);
      }
    }
    if (buf.length > 1 << 16) buf = '';       // savunma: yarım kalan çöp
  });

  p.on('error', (e) => { log(`motor hatası: ${e.message}`); });

  p.on('exit', (code, signal) => {
    engine = null;
    engineAlive = false;
    const lived = Date.now() - started;
    log(`motor çıktı (kod ${code}, sinyal ${signal}, ${lived} ms yaşadı)`);
    try { fs.closeSync(errFd); } catch (_) {}
    if (app.isQuitting) return;

    if (!lockedCommand && lived < 5000) {
      // Bu komut hiç tutunamadı — muhtemelen yanlış yorumlayıcı.
      advanceCandidate();
      return;
    }
    lockedCommand = lockedCommand || cmd;
    // Çalışan bir komut sonradan öldüyse bu bir çökmedir: geri getir.
    // Anında değil — sıkı bir döngü hem CPU'yu hem günlüğü yer.
    setState('idle');
    refreshTray('motor çöktü — yeniden başlatılıyor');
    if (restartTimer) clearTimeout(restartTimer);
    restartTimer = setTimeout(() => { restartTimer = null; startEngine(); }, 3000);
  });

  // Beş saniye yaşadıysa doğru komut budur; bir daha sıradakilere düşme.
  setTimeout(() => { if (engine === p) lockedCommand = cmd; }, 5000);
}

function advanceCandidate() {
  candidateIndex += 1;
  if (candidateIndex >= candidates.length) {
    log('hiçbir motor komutu çalışmadı — logs/engine.log dosyasına bak');
    refreshTray('motor başlatılamadı');
    return;
  }
  setTimeout(startEngine, 200);
}

function childEnv() {
  const env = Object.assign({}, process.env);
  const extra = path.join(app.getPath('home'), '.local', 'bin');
  if (!(env.PATH || '').split(path.delimiter).includes(extra)) {
    env.PATH = extra + path.delimiter + (env.PATH || '');
  }
  // Python'un stdout'u boruya bağlıyken blok tamponlamasını kapat, yoksa
  // ölçer verisi 4 KB'lık paketler hâlinde ve saniyeler geç gelir.
  env.PYTHONUNBUFFERED = '1';
  // Motora stdin'i bir ebeveyn-olum sinyali olarak izlemesini soyler.
  // Elle terminalden calistirilan bir motor bunu gormez ve stdin'i
  // klavye olarak birakir, ki dogrusu odur.
  env.TYPER_PARENT_PIPE = '1';
  return env;
}

function killEngine() {
  const p = engine;
  engine = null;
  if (!p) return;
  try {
    if (IS_WIN) {
      // `uv run python` iki süreçtir; /T ağacın tamamını alır.
      spawn('taskkill', ['/pid', String(p.pid), '/T', '/F'], { windowsHide: true });
    } else {
      process.kill(-p.pid, 'SIGTERM');       // süreç grubunun tamamı
    }
  } catch (_) {
    try { p.kill('SIGTERM'); } catch (__) {}
  }
}

/* ------------------------------------------------------------------ */
/* pencere                                                             */
/* ------------------------------------------------------------------ */

const BOUNDS = {
  listening: { width: 260, height: 78 },
  card: { width: 440, height: 240 },
};
const HIDE_DELAY_MS = 340;      // kapsülün kapanma animasyonu kadar

let win = null;
let state = 'idle';
let lastText = '';
let lastTs = 0;
let doneTs = 0;                 // kullanıcının işini bitirdiği kart
let hideTimer = null;

function place(shape) {
  const wa = screen.getPrimaryDisplay().workArea;   // görev çubuğu hariç
  const { width, height } = BOUNDS[shape] || BOUNDS.listening;
  return {
    x: Math.round(wa.x + (wa.width - width) / 2),
    y: Math.round(wa.y + wa.height - height),
    width, height,
  };
}

function createWindow() {
  win = new BrowserWindow({
    ...place('listening'),
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: false,
    alwaysOnTop: true,
    skipTaskbar: true,          // Windows/Linux; Mac'te dock gizlenir
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    focusable: false,           // yazdığın alandan odağı asla çalmaz
    show: false,
    webPreferences: {
      preload: path.join(UI_DIR, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  // Tıklamaları geçirir: kapsül bir süstür, yolunda duran bir şey değil.
  // Kart mouse'u kabul etmek zorunda (bir düğmesi var) ve kapsüle geri
  // döndüğü anda tıklamaları yutmayı bırakmak zorunda.
  win.setIgnoreMouseEvents(true, { forward: true });
  // Normal "her zaman üstte" pencerelerin de üstünde: tam ekran bir
  // uygulama bunu gömemesin.
  win.setAlwaysOnTop(true, 'screen-saver');
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  // ÇİZİCİ ÖLÜRSE pencere yaşamaya devam eder ama içine kimse çizmez:
  // geriye saydam bir dikdörtgen kalır. Kapsül hiç görünmez, üstelik
  // durum satırları sorunsuzmuş gibi akmaya devam eder — yani arıza
  // loglara "her şey yolunda" diye yazılır. Motorun çökünce yeniden
  // başlatılması zaten var; arayüzün yoktu.
  let cokme = 0;
  win.webContents.on('render-process-gone', (_e, detay) => {
    cokme++;
    log(`kapsül çizicisi öldü (${detay && detay.reason}) — ${cokme}. kez`);
    if (win && !win.isDestroyed() && cokme <= 3) {
      win.reload();
    } else {
      // Israrla ölüyorsa pencerenin kendisi bozulmuştur; baştan kur.
      try { if (win && !win.isDestroyed()) win.destroy(); } catch (e) {}
      win = null;
      cokme = 0;
      createWindow();
      const geri = state;
      state = 'idle';               // setState'in değişimi görmesi için
      win.webContents.once('did-finish-load', () => setState(geri));
    }
  });
  win.on('unresponsive', () => log('kapsül yanıt vermiyor'));

  win.loadFile(path.join(UI_DIR, 'pill.html'));
}

function onState(s) {
  const next = s.state || 'idle';

  // "ready" pencereye ait değil: motorun kendi kısayol okumasını taşır,
  // tepsi etiketi için. Kapsülü açmamalı.
  if (next === 'ready') {
    hotkeyLabel = s.text || hotkeyLabel;
    refreshTray();
    return;
  }

  if (s.text) { lastText = s.text; lastTs = s.ts || 0; }
  setState(next === 'preview' && s.ts && s.ts === doneTs ? 'idle' : next, s);
}

function setState(next, payload) {
  if (!win || win.isDestroyed()) return;

  if (next !== state) {
    state = next;
    if (next === 'idle') {
      if (hideTimer) clearTimeout(hideTimer);
      hideTimer = setTimeout(() => {
        hideTimer = null;
        if (state === 'idle' && win && !win.isDestroyed()) win.hide();
      }, HIDE_DELAY_MS);          // kapsül önce kapansın, sonra pencere gitsin
    } else {
      if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
      const card = next === 'preview' || next === 'error';
      win.setBounds(place(card ? 'card' : 'listening'));
      win.setIgnoreMouseEvents(!card, { forward: true });
      if (!win.isVisible()) win.showInactive();   // asla odak almaz
      // "EN ÜSTTE"Yİ HER GÖSTERİMDE YENİDEN UYGULA.
      //
      // Ölçüldü, tahmin değil: kapsül gizliyken kullanıcı bir uygulamaya
      // tıklayınca o pencere öne alınır; kapsül tekrar açıldığında
      // `showInactive` onu ESKİ z-yerinde geri açar, "her zaman üstte"
      // bandının tepesine taşımaz. Sonuç, z-sırası yürünerek görüldü:
      // WS_EX_TOPMOST biti pencerenin üzerinde dururken bile Excel,
      // Chrome, WhatsApp ve Discord kapsülün ÜSTÜNDE kalıyordu.
      //
      // Bayrağa bakmak bu arızayı gizler: `isAlwaysOnTop()` true der ve
      // pencere yine altta durur. Bandı bırakıp yeniden almak onu
      // gerçekten tepeye koyar; `moveTop` da bandın içinde en öne alır.
      //
      // Masaüstünde sorun görünmezdi, çünkü orada kapsülün üstünde
      // zaten hiçbir pencere olmuyor — arızanın "sadece uygulamalarda"
      // ortaya çıkmasının sebebi buydu.
      win.setAlwaysOnTop(false);
      win.setAlwaysOnTop(true, 'screen-saver');
      win.moveTop();
    }
    // Log GÖSTERDİKTEN SONRA yazılır. Önce yazılsaydı `görünür` her
    // seferinde false çıkardı ve bu satır, teşhis etmesi için var olduğu
    // arızanın ta kendisini uydururdu. "durum listening" tek başına da
    // yalan söyleyebiliyor: ana süreç mesajı alır, pencere yerindedir,
    // ve ekranda hiçbir şey yoktur — o yüzden pencerenin gerçek hâli de
    // yazılıyor.
    log(next === 'idle' ? 'durum idle' : (() => {
      const b = win.getBounds();
      return `durum ${next}  pencere ${b.width}x${b.height} @${b.x},${b.y} ` +
        `görünür=${win.isVisible()} ` +
        `çizici=${win.webContents.isCrashed() ? 'ÖLÜ' : 'canlı'}`;
    })());
    refreshTray();
  }
  win.webContents.send('typer:state', payload || { state: next });
}

ipcMain.on('typer:dismiss', (_e, copy) => {
  if (copy && lastText) clipboard.writeText(lastText);
  doneTs = lastTs;              // bu kartın işi bitti
  log(copy ? 'kart kopyalandı' : 'kart kapatıldı');
  // Hemen gitsin: metin panoya düştükten sonra kartın başka işi yok ve
  // beklemesi tıklamayı karşılıksız hissettirir. Sayfa zaten kapanma
  // animasyonuna başladı, bu süre yalnızca onu bekliyor.
  setTimeout(() => {
    if (win && !win.isDestroyed()) {
      win.setIgnoreMouseEvents(true, { forward: true });
      win.hide();
    }
    state = 'idle';
    refreshTray();
  }, 280);
});

/* ------------------------------------------------------------------ */
/* tepsi                                                               */
/* ------------------------------------------------------------------ */

let tray = null;

function trayIcon() {
  // İKİ DOSYA, çünkü iki işletim sisteminin kuralı farklı. İkisi de
  // marka kitinden üretilir (npm run brand), elle çizilmez.
  //
  //   icon.png           asit fayans üstüne siyah harf — Windows
  //                      tepsisi renkleri olduğu gibi çizer, ve simge
  //                      kendi zeminini taşıdığı için görev çubuğunun
  //                      teması ne olursa olsun aynı güçle okunur.
  //   icon-template.png  çıplak harf, opak — macOS menü çubuğu ŞABLON
  //                      görüntü ister: rengi yok sayar, yalnızca alfa
  //                      kanalına bakıp temasından boyar. Oraya fayans
  //                      göndermek dolu bir kare demek olurdu.
  const p = path.join(UI_DIR, IS_MAC ? 'icon-template.png' : 'icon.png');
  const yedek = path.join(UI_DIR, 'icon.png');
  const yol = fs.existsSync(p) ? p : yedek;
  if (!fs.existsSync(yol)) return nativeImage.createEmpty();
  let img = nativeImage.createFromPath(yol);
  if (img.isEmpty()) return nativeImage.createEmpty();
  if (IS_MAC) {
    img = img.resize({ width: 18, height: 18 });
    img.setTemplateImage(true);
  }
  return img;
}

const LABELS = {
  idle: 'boşta', listening: 'dinliyor', thinking: 'çeviriyor',
  preview: 'metin bekliyor', error: 'hata',
};

function refreshTray(note) {
  if (!tray) return;
  const bits = [
    `Typer — ${LABELS[state] || state}`,
    `motor: ${engineAlive ? 'çalışıyor' : 'durdu'}`,
  ];
  if (note) bits.push(note);
  tray.setToolTip(bits.join('\n'));
  tray.setContextMenu(buildMenu());
}

function buildMenu() {
  // Windows'ta iki mekanizma var (kayıt defteri + başlangıç kısayolu);
  // kutucuk ikisinden birine bakar, çünkü açık olması için biri yeter.
  const acilista = autoStartOn();

  return Menu.buildFromTemplate([
    { label: `Typer — ${LABELS[state] || state}`, enabled: false },
    { label: `Kısayol: ${hotkeyLabel}`, enabled: false },
    { type: 'separator' },
    {
      label: 'Son metni kopyala',
      enabled: !!lastText,
      click: () => { clipboard.writeText(lastText); log('son metin tepsiden kopyalandı'); },
    },
    { label: 'Ayarları aç (typer.json)', click: () => shell.openPath(CONFIG_PATH) },
    { label: 'Günlükleri aç', click: () => shell.openPath(LOG_DIR) },
    { type: 'separator' },
    {
      label: 'Motoru yeniden başlat',
      click: () => {
        lockedCommand = null; candidates = []; candidateIndex = 0;
        killEngine();
        setTimeout(startEngine, 1200);
      },
    },
    {
      label: IS_MAC ? 'Açılışta başlat' : 'Windows ile başlat',
      type: 'checkbox',
      checked: acilista,
      click: (item) => { setAutoStart(item.checked); refreshTray(); },
    },
    { type: 'separator' },
    { label: "Typer'dan çık", click: () => { app.isQuitting = true; app.quit(); } },
  ]);
}

/** Windows Başlangıç klasöründeki kısayolun tam yolu. */
function startupLink() {
  return path.join(app.getPath('appData'), 'Microsoft', 'Windows',
                   'Start Menu', 'Programs', 'Startup', 'Typer.lnk');
}

/** Açılışta başlatma AÇIK mı? İki mekanizmadan biri yeterli. */
function autoStartOn() {
  try {
    if (IS_WIN && fs.existsSync(startupLink())) return true;
  } catch (_) {}
  try {
    return !!app.getLoginItemSettings({ name: 'Typer' }).openAtLogin;
  } catch (_) { return false; }
}

function setAutoStart(on) {
  if (IS_MAC) {
    // macOS'ta `name`, `path` ve `args` yok sayılır; işletim sistemi
    // uygulamanın kendi paketini kaydeder. openAsHidden, açılışta
    // pencerenin göze batmamasını sağlar.
    app.setLoginItemSettings({ openAtLogin: !!on, openAsHidden: true });
    return;
  }
  // HKCU\...\CurrentVersion\Run altındaki değer adı. Windows bunu
  // app.setName()'den DEĞİL, buradaki `name`den alır — onsuz girdi
  // "electron.app.Electron" olarak düşer, ki bu görür görmez silmek
  // isteyeceğin bir şeye benzer. Geliştirme kipinde uygulama
  // "electron.exe <dizin>" diye başlatılır, o yüzden dizin argüman olarak
  // taşınmak zorunda.
  app.setLoginItemSettings({
    openAtLogin: !!on,
    name: 'Typer',
    path: process.execPath,
    args: app.isPackaged ? [] : [ROOT],
  });

  if (!IS_WIN) return;

  // BAŞLANGIÇ KLASÖRÜ, kayıt defterine EK OLARAK.
  //
  // Ölçüldü: Run girdisi yerinde dururken (anahtarın son yazılması
  // açılıştan bir gün önceydi) Windows onu açılışta ÇALIŞTIRMADI.
  // Kabuğun kendi günlüğü (Shell-Core/Operational, olay 9707) o
  // açılışta dokuz komutu tek tek sayıyor ve Typer onların arasında
  // yok; 208 olayın hiçbirinde "electron" geçmiyor. Typer, Windows'un
  // başlangıç girdilerini onayladığı StartupApproved listesinde de hiç
  // görünmüyor — çalışan her uygulamanın orada bir kaydı varken.
  //
  // Sebebini Windows tarafında kesin olarak belirleyemedim, o yüzden
  // tek mekanizmaya güvenmiyorum. Kısayol ikinci bir yol açar ve
  // ikisinin birden çalışması zararsızdır: tek kopya kilidi ikinciyi
  // sessizce kapatır (bkz. requestSingleInstanceLock).
  //
  // Kısayolun bir yan faydası da görünürlük: kullanıcı onu klasörde
  // görür ve isterse siler. Kayıt defteri girdisi görünmez.
  try {
    const lnk = startupLink();
    if (on) {
      fs.mkdirSync(path.dirname(lnk), { recursive: true });
      const ico = path.join(ROOT, 'visuals', 'app-icons', 'favicon.ico');
      shell.writeShortcutLink(lnk, 'create', {
        target: process.execPath,
        args: app.isPackaged ? '' : `"${ROOT}"`,
        cwd: ROOT,
        description: 'Typer — bir tuşa bas, konuş, yazı imlecine düşsün',
        ...(fs.existsSync(ico) ? { icon: ico, iconIndex: 0 } : {}),
      });
      log(`başlangıç kısayolu yazıldı: ${lnk}`);
    } else if (fs.existsSync(lnk)) {
      fs.unlinkSync(lnk);
      log('başlangıç kısayolu silindi');
    }
  } catch (e) {
    log(`başlangıç kısayolu yazılamadı: ${e.message}`);
  }
}

/* ------------------------------------------------------------------ */
/* yaşam döngüsü                                                       */
/* ------------------------------------------------------------------ */

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    // İkinci bir kopya açmaya çalışmak, "çalışıyor mu?" sorusunun en sık
    // sorulma biçimi. Tepsiyi tazele ve orada olduğunu göster.
    refreshTray();
  });

  app.whenReady().then(() => {
    // Mac'te dock simgesi olmasın: Typer bir pencere uygulaması değil,
    // menü çubuğunda yaşayan bir araç. (skipTaskbar Mac'te dock'u
    // etkilemez, bunu yapan tek şey budur.)
    if (IS_MAC && app.dock && !CAPTURE) app.dock.hide();

    createWindow();
    tray = new Tray(trayIcon());
    refreshTray();
    startEngine();

    // Bir yakalama koşusu başlangıç girdisine DOKUNMAZ — ne ekler ne
    // siler. Buraya false geçmek "atla" demek değil "SİL" demektir, ve
    // bu, her ekran görüntüsünün kullanıcının otomatik başlatmasını
    // sessizce kaldırmasına yol açmıştı.
    if (!CAPTURE) setAutoStart(CFG.start_at_login);

    if (SHOT) {
      setTimeout(async () => {
        try {
          win.showInactive();
          await new Promise((r) => setTimeout(r, 1200));
          fs.writeFileSync(SHOT, (await win.capturePage()).toPNG());
          console.log('[typer] yakalandı -> ' + SHOT);
        } catch (e) { console.error('[typer] yakalama başarısız: ' + e.message); }
        app.isQuitting = true; app.quit();
      }, 2500);
    }
  });

  // Pencerenin kendini gizlemesi normal işleyiştir, çıkma sebebi değil.
  app.on('window-all-closed', (e) => { if (e && e.preventDefault) e.preventDefault(); });
  app.on('before-quit', () => { app.isQuitting = true; killEngine(); });
  process.on('exit', killEngine);
}
