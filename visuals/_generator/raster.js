/* Typer marka kiti — SVG'yi PNG'ye çeviren tek araç.
 *
 * Neden Electron: bu depoda zaten var. sharp ya da resvg kurmak marka
 * kitini ağa ve ikili paketlere bağlar; oysa `npm install` Chromium'u
 * zaten indirdi. Chromium SVG'yi tarayıcıların çizdiği gibi çizer, ki
 * bu assetlerin gideceği yer de orası.
 *
 *   electron raster.js isler.json
 *
 * isler.json: [{ "svg": "<mutlak yol>", "out": "<mutlak yol>",
 *                "w": 512, "h": 512, "bg": "#0A0A0A" | null }]
 *
 * Yollar C:/... biçiminde olmalı (git-bash'in /c/... biçimini Node
 * Windows'ta açamaz).
 */
const { app, BrowserWindow } = require("electron");
const fs = require("fs");
const path = require("path");

app.disableHardwareAcceleration();
app.commandLine.appendSwitch("force-device-scale-factor", "1");
app.commandLine.appendSwitch("force-color-profile", "srgb");
app.commandLine.appendSwitch("disable-background-timer-throttling");
app.commandLine.appendSwitch("disable-renderer-backgrounding");

const JOBS = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function page(svg, w, h, bg) {
  // SVG dosyanın kendi width/height'ına değil, İSTENEN piksele
  // ölçeklenir: tek bir kaynak bütün boyutları besler.
  const body = svg.replace(/<svg([^>]*?)>/, (m, attrs) =>
    `<svg${attrs.replace(/\s(width|height)="[^"]*"/g, "")} width="${w}" height="${h}">`);
  return `<!doctype html><meta charset="utf-8"><style>
    html,body{margin:0;padding:0;width:${w}px;height:${h}px;overflow:hidden;
      background:${bg || "transparent"};}
    svg{display:block;}
  </style>${body}`;
}

app.whenReady().then(async () => {
  // TEK pencere, her iş için yeniden boyutlandırılıyor. Her işe yeni bir
  // saydam pencere açıp yok etmek Chromium'un ağ servisini düşürüyor ve
  // sonraki data: yüklemesi ERR_FAILED veriyor — 16 px'lik favicon çıkıp
  // 32 px'lik çıkmamasının sebebi buydu.
  const win = new BrowserWindow({
    show: false, frame: false,
    transparent: true, backgroundColor: "#00000000",
    webPreferences: { backgroundThrottling: false },
  });

  let failed = 0;
  for (const [i, job] of JOBS.entries()) {
    const svg = fs.readFileSync(job.svg, "utf8");
    const w = Math.round(job.w);
    const h = Math.round(job.h || job.w);
    const html = "data:text/html;charset=utf-8," +
      encodeURIComponent(page(svg, w, h, job.bg) + `<!--${i}-->`);

    let png = null;
    for (let deneme = 1; deneme <= 3 && !png; deneme++) {
      try {
        win.setContentSize(w, h);
        await sleep(20);              // boyut önce otursun, sonra çiz
        await win.loadURL(html);
        await sleep(60);              // bir kare bekle: aksi hâlde boş yüzey
        png = (await win.webContents.capturePage()).toPNG();
      } catch (e) {
        console.error(`  ! ${path.basename(job.out)} deneme ${deneme}: ${e.message}`);
        await sleep(250);
      }
    }
    if (!png) { failed++; continue; }
    fs.mkdirSync(path.dirname(job.out), { recursive: true });
    fs.writeFileSync(job.out, png);
    console.log(`${path.basename(job.out)}  ${w}x${h}`);
  }

  win.destroy();
  if (failed) console.error(`${failed} iş çizilemedi`);
  // Sessiz başarısızlık olmasın: çağıran betik çıkış koduna bakabilsin.
  app.exit(failed ? 1 : 0);
});
