/* Basılabilir marka kılavuzunu üretir: visuals/Typer-Brand-Guide.pdf
 *
 *   electron visuals/_generator/guide.js
 *
 * Önce build.js koşmuş olmalı — kılavuz üretilmiş assetlerin kendisini
 * gösterir, ayrı bir çizim yapmaz. Böylece kılavuzdaki logo ile klasördeki
 * logo aynı olmak zorunda kalır.
 *
 * Sayfa metni işletim sisteminin arayüz fontuyla dizilir. Bu bir BELGE,
 * asset değil; assetlerin hiçbirinde font yok.
 */
const { app, BrowserWindow } = require("electron");
const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");
const { C, MARK, WORDMARK } = require("./art");

const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "Typer-Brand-Guide.pdf");
const HTML = path.join(__dirname, "_guide.html");

const tokens = () => {
  try { return JSON.parse(fs.readFileSync(path.join(ROOT, "brand-tokens.json"), "utf8")); }
  catch { return null; }
};

const swatch = (name, hex, role) => `
  <div class="sw">
    <div class="chip" style="background:${hex}"></div>
    <div class="swtxt"><b>${name}</b><code>${hex}</code><span>${role}</span></div>
  </div>`;

function html() {
  const t = tokens();
  const cs = (t && t.contrast) || {};
  // Oranlar kılavuza ELLE yazılmaz: üretilmiş tokenlardan okunur,
  // yoksa belge ile assetler sessizce ayrışır.
  const L = (t && t.lockup) || {};
  return `<!doctype html><meta charset="utf-8"><base href="${pathToFileURL(ROOT).href}/"><title>Typer Marka Kılavuzu</title>
<style>
  @page { size: A4; margin: 16mm 14mm; }
  * { box-sizing: border-box; }
  body { margin:0; font: 10.5pt/1.55 "Segoe UI", system-ui, sans-serif;
         color:${C.ink}; background:#fff; -webkit-print-color-adjust:exact;
         print-color-adjust:exact; }
  h1 { font-size:30pt; letter-spacing:-.02em; margin:0 0 6pt; }
  h2 { font-size:15pt; margin:0 0 8pt; letter-spacing:-.01em; }
  h3 { font-size:10.5pt; margin:14pt 0 4pt; text-transform:uppercase;
       letter-spacing:.10em; color:${C.mute}; }
  p  { margin:0 0 8pt; max-width:52em; }
  code { font:9.5pt/1.4 Consolas, monospace; color:${C.mute}; }
  .page { page-break-after: always; }
  .page:last-child { page-break-after: auto; }
  .cover { background:${C.ink}; color:${C.paper}; margin:-16mm -14mm 0;
           padding:38mm 14mm 20mm; height:262mm; }
  .cover img { width:118mm; display:block; margin-bottom:14mm; }
  .cover .lede { font-size:13pt; color:${C.mist}; max-width:34em; }
  .cover .rule { height:3pt; width:34mm; background:${C.acid}; margin:10mm 0; }
  .grid { display:grid; gap:8mm; }
  .g2 { grid-template-columns:1fr 1fr; }
  .g3 { grid-template-columns:repeat(3,1fr); }
  .g4 { grid-template-columns:repeat(4,1fr); }
  .box { border:1px solid ${C.line}; border-radius:6pt; padding:7mm;
         display:flex; align-items:center; justify-content:center; }
  .box.dark { background:${C.ink}; border-color:${C.ink}; }
  .box img { max-width:100%; }
  .grid.g4 .box img, .grid.g3 .box img { width:26mm; height:auto; }
  .cap { font-size:8.5pt; color:${C.mute}; margin-top:3pt; text-align:center; }
  .sw { display:flex; gap:4mm; align-items:center; margin-bottom:4mm; }
  .chip { width:16mm; height:16mm; border-radius:4pt; border:1px solid ${C.line}; flex:none; }
  .swtxt b { display:block; }
  .swtxt code { display:block; }
  .swtxt span { font-size:9pt; color:${C.mute}; }
  table { border-collapse:collapse; width:100%; font-size:9.5pt; }
  td, th { border-bottom:1px solid ${C.line}; padding:3.6pt 0; text-align:left;
           vertical-align:top; }
  th { color:${C.mute}; font-weight:600; font-size:8.5pt;
       text-transform:uppercase; letter-spacing:.08em; }
  .sizes { display:flex; align-items:flex-end; gap:9mm; }
  .sizes figure { margin:0; text-align:center; }
  .sizes img { display:block; margin:0 auto 3pt; image-rendering:auto; }
  .dont img, .do img { width:26mm; }
  .dont .box { border-color:#e6c4c4; }
  .mark-x { color:#b3261e; font-weight:600; font-size:9pt; }
  .mark-o { color:${C.moss}; font-weight:600; font-size:9pt; }
  .clear { position:relative; }
  .clear { overflow:hidden; }
  .clear .halo { position:absolute; inset:5mm; outline:1.5px dashed ${C.acid};
                 outline-offset:0; }
</style>

<!-- ---------------------------------------------------------- kapak -->
<section class="page cover">
  <img src="lockups/typer-lockup-horizontal-dark-1024.png" alt="typer">
  <div class="rule"></div>
  <div class="lede">Marka kılavuzu — işaret, logotype, renk ve kullanım.
    Bir tuşa bas, konuş, yazı imlecinin olduğu yere düşsün.</div>
  <div style="margin-top:auto;padding-top:24mm;color:${C.mute};font-size:9pt">
    Bu belge <code>visuals/_generator</code> tarafından üretildi.
    Elle düzenlenmez; <code>node build.js</code> sonra
    <code>electron guide.js</code> ile yenilenir.
  </div>
</section>

<!-- --------------------------------------------------------- işaret -->
<section class="page">
  <h1>İşaret</h1>
  <p>Kare işaret tek bir şeydir: eğik, küçük bir <b>t</b>. Çerçeve yok,
     mikrofon yok, dalga yok. Uygulama simgesi, favicon ve tepsi simgesi
     hep budur.</p>
  <p><b>Bu t, logotype'ın t'sinin ta kendisidir</b> — aynı font, aynı eğim,
     aynı yol verisi, tek bir üretimde çıkar. Ayrı çizilselerdi bir gün
     biri güncellenir, diğeri unutulurdu.</p>

  <h3>Ana kullanım</h3>
  <div class="grid g4">
    <div><div class="box"><img src="mark/typer-mark-acid-512.png"></div>
      <div class="cap">siyah fayans, asit t — varsayılan</div></div>
    <div><div class="box"><img src="mark/typer-mark-invert.svg"></div>
      <div class="cap">asit fayans, siyah t</div></div>
    <div><div class="box"><img src="mark/typer-mark-paper.svg"></div>
      <div class="cap">açık gri fayans</div></div>
    <div><div class="box dark"><img src="mark/typer-mark-bare-acid-512.png"></div>
      <div class="cap">fayanssız, koyu zeminde</div></div>
  </div>

  <h3>Küçük boyda</h3>
  <p>İşaret 16 pikselde de <b>t</b> olarak okunur; alt kanca leke olmaz,
     çapraz çizgi kaybolmaz. Alt sınır 16 px'tir.</p>
  <div class="sizes">
    ${[16, 20, 24, 32, 48, 64].map((s) => `
      <figure><img src="app-icons/favicon-${s}.png"
        style="width:${s}px;height:${s}px"><figcaption class="cap">${s}px</figcaption></figure>`).join("")}
  </div>

  <h3>Boşluk</h3>
  <p>İşaretin dört yanında, kenarının en az <b>%25</b>'i kadar boşluk kalır.
     Bu alanın içine yazı, çizgi ya da başka bir logo girmez.</p>
  <div class="grid g3">
    <div><div class="box clear"><span class="halo"></span>
      <img src="mark/typer-mark-acid-256.png" style="width:26mm"></div></div>
    <div style="grid-column:span 2">
      <table>
        <tr><th>Ölçü</th><th>Değer</th></tr>
        <tr><td>Koordinat uzayı</td><td><code>0 0 ${MARK.box} ${MARK.box}</code></td></tr>
        <tr><td>Fayans köşe yarıçapı</td><td><code>${MARK.tileRadius}</code> (%${Math.round(MARK.tileRadius / MARK.box * 100)})</td></tr>
        <tr><td>Harfin doluluğu</td><td><code>${MARK.fill}</code> (fayans kenarına oranla)</td></tr>
        <tr><td>Biçim</td><td>dolgu — logotype'ın t'siyle birebir aynı yol</td></tr>
        <tr><td>En küçük boy</td><td>16 px</td></tr>
      </table>
    </div>
  </div>
</section>

<!-- ---------------------------------------------------------- renk -->
<section class="page">
  <h1>Renk</h1>
  <p>Üç renk: siyah, asit yeşili ve çok açık gri. Asit tek vurgudur; her
     yerde kullanılmaz, bir şeyin canlı olduğunu söylemek için kullanılır.</p>
  <div class="grid g2">
    <div>
      ${swatch("ink", C.ink, "siyah — ana yüzey ve ana metin")}
      ${swatch("acid", C.acid, "asit yeşili — tek vurgu")}
      ${swatch("paper", C.paper, "çok açık gri — açık yüzey")}
      ${swatch("moss", C.moss, "asitin açık zeminde okunan hâli")}
    </div>
    <div>
      ${swatch("ink-raise", C.inkRaise, "koyu yüzeyde bir üst kat")}
      ${swatch("acid-hi", C.acidHi, "koyu zeminde parlak uç")}
      ${swatch("line", C.line, "açık zeminde ayraç")}
      ${swatch("mute", C.mute, "açık zeminde ikincil metin")}
      ${swatch("mist", C.mist, "koyu zeminde ikincil metin")}
    </div>
  </div>

  <h3>Kontrast</h3>
  <table>
    <tr><th>Çift</th><th>Oran</th><th>Ne demek</th></tr>
    <tr><td>ink / paper</td><td>${cs["ink / paper"] || "17.97"}</td><td>ana metin, her boyda geçer</td></tr>
    <tr><td>acid / ink</td><td>${cs["acid / ink"] || "15.90"}</td><td>koyu zeminde asit rahat okunur</td></tr>
    <tr><td>mist / ink</td><td>${cs["mist / ink"] || "8.37"}</td><td>koyu zeminde ikincil metin</td></tr>
    <tr><td>moss / paper</td><td>${cs["moss / paper"] || "4.90"}</td><td>açık zeminde asit gerekiyorsa bu</td></tr>
    <tr><td>mute / paper</td><td>${cs["mute / paper"] || "4.66"}</td><td>açık zeminde ikincil metin</td></tr>
    <tr><td>acid / paper</td><td>1.13</td><td><b>metin olarak kullanılamaz</b></td></tr>
  </table>
  <p style="margin-top:8pt"><b>Kural.</b> Açık zeminde asit yeşili yazı yazılmaz.
     Asit orada yalnızca dolgu, altı çizili vurgu ya da grafik öğe olur;
     metin gerekiyorsa <code>moss</code> kullanılır.</p>
</section>

<!-- ------------------------------------------------------ logotype -->
<section class="page">
  <h1>Logotype</h1>
  <p>Kelime <b>Modern Sans Serif 7</b> (Style-7) fontundan bir kez okunup
     ${WORDMARK.slant} derece eğimle vektör yoluna çevrildi; eğim işaretin
     eğimiyle aynıdır. Artık bir metin değil bir vektördür: hiçbir asset
     font dosyasına bağlı değil, font hiçbir çıktının içinde taşınmıyor ve
     kelime her yerde birebir aynı çıkıyor. Yeniden dizilmez, "benzer bir
     fontla" yazılmaz.</p>
  <p style="color:${C.mute};font-size:9pt">Font ücretsiz yazılımda
     kullanılabilir ve künyede kredi ister; ticari kullanım lisans
     gerektirir.</p>
  <div class="box" style="padding:12mm"><img src="wordmark/typer-wordmark-ink-1024.png" style="width:120mm"></div>
  <div class="cap">açık zeminde siyah</div>
  <div class="box dark" style="padding:12mm;margin-top:6mm"><img src="wordmark/typer-wordmark-paper-1024.png" style="width:120mm"></div>
  <div class="cap">koyu zeminde açık gri</div>

  <h3>Tek başına kelime</h3>
  <p>Kare işaret kullanılmadığında kelime <b>siyah zeminde asit
     yeşilidir</b>. Kendi zeminini yanında taşır: açık zeminde asit
     yeşili metnin kontrastı 1.13, siyah zeminde 15.9.</p>
  <div class="box dark" style="padding:10mm">
    <img src="wordmark/typer-wordmark-standalone-1024.png" style="width:110mm">
  </div>

  <h3>Kilit</h3>
  <p>Kelime <b>sınır kutusundan değil çıkıntı yüksekliğinden</b> ölçeklenir:
     t'sinin tepesi işaret kenarının <b>%${Math.round(L.ascenderRatio * 100)}</b>'sı
     kadardır. Aralık işaret kenarının <b>%${Math.round(L.gapRatio * 100)}</b>'sı.
     Dikey kilitte kelime %${Math.round(L.stackedAscenderRatio * 100)},
     ara %${Math.round(L.stackedGapRatio * 100)}.</p>
  <p style="color:${C.mute};font-size:9pt">Dikeyde hizalama x-yüksekliği
     bandının ortasından yapılır. Kelimenin altında iki kuyruk (y, p) var;
     sınır kutusunun ortasından hizalamak kelimeyi optik olarak yukarı
     kaçırıyor, çünkü göz kuyrukları "kelimenin gövdesi" saymıyor.</p>
  <div class="grid g2">
    <div><div class="box"><img src="lockups/typer-lockup-horizontal-light-1024.png"></div>
      <div class="cap">yatay, açık zemin</div></div>
    <div><div class="box dark"><img src="lockups/typer-lockup-horizontal-dark-1024.png"></div>
      <div class="cap">yatay, koyu zemin</div></div>
    <div><div class="box"><img src="lockups/typer-lockup-vertical-light-512.png" style="max-height:52mm"></div>
      <div class="cap">dikey, açık zemin</div></div>
    <div><div class="box"><img src="portable/typer-lockup-horizontal-outlined.svg"></div>
      <div class="cap">taşınabilir sürüm (çizgi yok, yalnız dolgu)</div></div>
  </div>
</section>

<!-- ------------------------------------------------------ kullanım -->
<section class="page">
  <h1>Kullanım</h1>
  <h3 class="mark-o">Yapılır</h3>
  <div class="grid g4 do">
    <div><div class="box"><img src="mark/typer-mark-acid-256.png"></div>
      <div class="cap">açık zeminde siyah fayans</div></div>
    <div><div class="box dark"><img src="mark/typer-mark-bare-acid-128.png"></div>
      <div class="cap">koyu zeminde fayansı at</div></div>
    <div><div class="box"><img src="mark/typer-mark-invert.svg"></div>
      <div class="cap">vurgu gerekiyorsa ters</div></div>
    <div><div class="box"><img src="portable/typer-mark-bare-outlined.svg"></div>
      <div class="cap">tek renk baskı</div></div>
  </div>

  <h3 class="mark-x">Yapılmaz</h3>
  <div class="grid g4 dont">
    <div><div class="box"><img src="mark/typer-mark-acid-256.png" style="transform:skewX(-14deg)"></div>
      <div class="cap">eğme, esnetme, oranını bozma</div></div>
    <div><div class="box"><img src="mark/typer-mark-acid-256.png" style="filter:hue-rotate(180deg)"></div>
      <div class="cap">rengini değiştirme</div></div>
    <div><div class="box"><img src="mark/typer-mark-acid-256.png" style="filter:drop-shadow(0 3mm 2mm rgba(0,0,0,.55))"></div>
      <div class="cap">gölge, parlama, bevel ekleme</div></div>
    <div><div class="box dark"><img src="mark/typer-mark-acid-256.png" style="opacity:.35"></div>
      <div class="cap">saydamlaştırma, filigranlaştırma</div></div>
  </div>

  <h3>Dosya haritası</h3>
  <table>
    <tr><th>Nerede</th><th>Hangi dosya</th></tr>
    <tr><td>Uygulama simgesi</td><td><code>app-icons/icon.png</code></td></tr>
    <tr><td>Tarayıcı favicon</td><td><code>app-icons/favicon.ico</code> + <code>favicon.svg</code></td></tr>
    <tr><td>iOS ana ekran</td><td><code>app-icons/apple-touch-icon.png</code></td></tr>
    <tr><td>Android / PWA</td><td><code>app-icons/icon-maskable-512.png</code> + <code>site.webmanifest</code></td></tr>
    <tr><td>Tepsi / menü çubuğu</td><td><code>product/typer-tray-32.png</code> (beyaz, alfa şablon)</td></tr>
    <tr><td>GitHub sosyal önizleme</td><td><code>social/github-social-1280x640.png</code></td></tr>
    <tr><td>Bağlantı önizlemesi</td><td><code>social/og-default.png</code></td></tr>
    <tr><td>Profil fotoğrafı</td><td><code>social/avatar-1024.png</code></td></tr>
    <tr><td>Site / doküman başlığı</td><td><code>lockups/typer-lockup-horizontal-light.svg</code></td></tr>
    <tr><td>Koyu yüzey başlığı</td><td><code>lockups/typer-lockup-horizontal-dark.svg</code></td></tr>
    <tr><td>Üçüncü taraf / bilinmeyen çizici</td><td><code>portable/*-outlined.svg</code></td></tr>
  </table>
</section>`;
}

app.disableHardwareAcceleration();
app.whenReady().then(async () => {
  fs.writeFileSync(HTML, html(), "utf8");
  const win = new BrowserWindow({ show: false, width: 900, height: 1200 });
  await win.loadFile(HTML);
  // Yazı tipleri ve görseller otursun.
  await new Promise((r) => setTimeout(r, 700));
  const pdf = await win.webContents.printToPDF({
    pageSize: "A4", printBackground: true, margins: { marginType: "none" },
  });
  fs.writeFileSync(OUT, pdf);
  console.log(`yazıldı: ${OUT}  (${Math.round(pdf.length / 1024)} KB)`);
  app.exit(0);
});
