/* Typer marka kitini üreten betik.
 *
 *   node visuals/_generator/build.js          her şeyi üret
 *   node visuals/_generator/build.js --svg    yalnız SVG (hızlı deneme)
 *
 * Her asset tek bir geometriden (art.js) türer, o yüzden favicon ile
 * sosyal kart aynı eğriyi çizer. PNG'ler Electron'un Chromium'uyla
 * rasterlenir (raster.js), .ico elle yazılır (ico.js), taşınabilir
 * sürümlerde çizgi dolguya çevrilir (outline.js). Dışarıdan hiçbir
 * paket gerekmez.
 */
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const { C, MARK, WORDMARK, markPaths, wordmarkPaths } = require("./art");
const { outlineSVG } = require("./outline");
const { writeIco } = require("./ico");

const ROOT = path.resolve(__dirname, "..");          // visuals/
const SVG_ONLY = process.argv.includes("--svg");
const jobs = [];
let nSvg = 0;

function put(rel, text) {
  const p = path.join(ROOT, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, text.trim() + "\n", "utf8");
  nSvg++;
  return p;
}
function raster(svgRel, outRel, w, h, bg) {
  jobs.push({
    svg: path.join(ROOT, svgRel), out: path.join(ROOT, outRel),
    w, h: h || w, bg: bg || null,
  });
}
const doc = (vb, w, h, body) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${vb}" width="${w}" height="${h}">${body}</svg>`;
const bodyOf = (s) => s.replace(/<svg[^>]*>|<\/svg>/g, "");

/* ---------------------------------------------------------------- işaret */

const B = MARK.bbox;
const BW = B.x2 - B.x1, BH = B.y2 - B.y1;
const tile = (fill, r) =>
  `<rect width="32" height="32" rx="${r === undefined ? MARK.tileRadius : r}" fill="${fill}"/>`;

/** Fayanslı kare işaret. */
const markTile = (tileFill, tColor, r) =>
  doc("0 0 32 32", 32, 32, tile(tileFill, r) + markPaths(tColor));

/** Fayanssız işaret: viewBox harfin gerçek sınırına oturur, kare kalır. */
function markBare(color, pad = 2.2) {
  const x = B.x1 - pad, y = B.y1 - pad;
  const w = BW + pad * 2, h = BH + pad * 2;
  const s = Math.max(w, h);
  const vb = `${(x - (s - w) / 2).toFixed(3)} ${(y - (s - h) / 2).toFixed(3)} ${s.toFixed(3)} ${s.toFixed(3)}`;
  return doc(vb, 512, 512, markPaths(color));
}

/** Köşesiz, tam taşan kare — avatar ve maskable simgeler için. Harf
 *  güvenli alana sığsın diye küçültülür. */
function markBleed(bg, tColor, scale = 0.62) {
  const k = (32 * scale) / Math.max(BW, BH);
  const cx = (B.x1 + B.x2) / 2, cy = (B.y1 + B.y2) / 2;
  const tx = 16 - cx * k, ty = 16 - cy * k;
  return doc("0 0 32 32", 32, 32,
    `<rect width="32" height="32" fill="${bg}"/>` +
    `<g transform="translate(${tx.toFixed(3)} ${ty.toFixed(3)}) scale(${k.toFixed(4)})">${markPaths(tColor)}</g>`);
}

/* -------------------------------------------------------------- logotype */

const W = WORDMARK.bbox;
const WW = W.x2 - W.x1, WH = W.y2 - W.y1;

function wordmark(color, pad = 2) {
  return doc(
    `${W.x1 - pad} ${W.y1 - pad} ${WW + pad * 2} ${WH + pad * 2}`,
    Math.round((WW + pad * 2) * 8), Math.round((WH + pad * 2) * 8),
    wordmarkPaths(color));
}

/* --------------------------------------------------------------- kilitler
 *
 * Hizalama kelimenin SINIR KUTUSUNA göre değil TİPOGRAFİK ÖLÇÜLERİNE
 * göre yapılır: "typer" kelimesinin altında iki kuyruk (y, p), üstünde
 * bir çıkıntı (t) var ve göz bunları "kelimenin gövdesi" saymıyor.
 */
const GAP_H = 0.30;                    // yatay kilitte ara / işaret kenarı
const XH_V = 0.42, GAP_V = 0.26;       // dikey kilit

const M = WORDMARK.metrics;

/** Kelimeyi TABAN ÇİZGİSİNDEN yerleştirir: (x, taban), k ölçeğiyle. */
function wordAt(x, baseline, k, color) {
  return {
    svg: `<g transform="translate(${(x - W.x1 * k).toFixed(3)} ${baseline.toFixed(3)}) ` +
      `scale(${k.toFixed(5)})">${wordmarkPaths(color)}</g>`,
    top: baseline + W.y1 * k,          // t'nin tepesi (fayansın üstüne taşar)
    bottom: baseline + W.y2 * k,       // y ve p'nin kuyruğu (altına taşar)
    width: WW * k,
  };
}

/* Yatay kilidin tek kuralı: kelimenin GÖVDESİ fayansla aynı yükseklikte.
 *
 * Gövde = x-yüksekliği bandı; t'nin çıkıntısı ve y ile p'nin kuyrukları
 * onun dışında kalır ve fayansın üstüne/altına bilerek taşar. Böylece
 * yan yana durduklarında göz iki ayrı yükseklik görmez: harflerin
 * omuzları fayansın üst kenarıyla, tabanları alt kenarıyla aynı hizada
 * oturur. Ölçek buradan çıkar, göz kararıyla değil. */
function lockupH({ markBody, wordColor, pad = 2.4 }) {
  const S = 32;
  const k = S / M.xHeight;             // x-yüksekliği bandı = fayans kenarı
  const gap = S * GAP_H;
  const w = wordAt(S + gap, S, k, wordColor);   // taban çizgisi fayansın altı
  const totalW = S + gap + w.width;
  const y1 = Math.min(0, w.top), y2 = Math.max(S, w.bottom);
  const vb = `${-pad} ${(y1 - pad).toFixed(3)} ${(totalW + pad * 2).toFixed(3)} ` +
    `${(y2 - y1 + pad * 2).toFixed(3)}`;
  return doc(vb, Math.round((totalW + pad * 2) * 8),
    Math.round((y2 - y1 + pad * 2) * 8), markBody + w.svg);
}

/* Dikey kilitte aynı kural işlemez: kelime fayansın ALTINDA durduğu için
   ortak bir yükseklik yok, ve x-yüksekliğini fayansa eşitlemek kelimeyi
   işaretin beş katı genişliğe çıkarırdı. Burada ölçü genişlik dengesi. */
function lockupV({ markBody, wordColor, pad = 2.4 }) {
  const S = 32;
  const k = (S * XH_V) / M.xHeight;
  const gap = S * GAP_V;
  const probe = wordAt(0, 0, k, wordColor);
  const wW = probe.width;
  const totalW = Math.max(S, wW);
  const mx = (totalW - S) / 2;
  const w = wordAt((totalW - wW) / 2, S + gap - probe.top, k, wordColor);
  const body = `<g transform="translate(${mx.toFixed(3)} 0)">${markBody}</g>` + w.svg;
  const vb = `${-pad} ${-pad} ${(totalW + pad * 2).toFixed(3)} ${(w.bottom + pad * 2).toFixed(3)}`;
  return doc(vb, Math.round((totalW + pad * 2) * 8),
    Math.round((w.bottom + pad * 2) * 8), body);
}

/* Kelime TEK BAŞINA kullanıldığında (kare işaret yokken) varsayılan hâli
   siyah zeminde asit yeşilidir. Açık zeminde asitle yazı okunmuyor
   (kontrast 1.13), siyah zeminde ise 15.9 — yani kelimenin kendi zemini
   yanında gelmesi hem markanın enerjisini taşıyor hem de okunaklılığı
   garanti ediyor. */
function wordPlate(bg, color, padX = 0.55, padY = 0.42) {
  const xh = M.xHeight;
  const px = xh * padX, py = xh * padY;
  const x = W.x1 - px, y = W.y1 - py;
  const w = WW + px * 2, h = (W.y2 - W.y1) + py * 2;
  const r = xh * 0.34;
  return doc(`${x.toFixed(2)} ${y.toFixed(2)} ${w.toFixed(2)} ${h.toFixed(2)}`,
    Math.round(w * 4), Math.round(h * 4),
    `<rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${w.toFixed(2)}" ` +
    `height="${h.toFixed(2)}" rx="${r.toFixed(2)}" fill="${bg}"/>` +
    wordmarkPaths(color));
}

/* =========================================================== ÜRETİM ==== */

// ---- mark/
put("mark/typer-mark-acid.svg", markTile(C.ink, C.acid));
put("mark/typer-mark-invert.svg", markTile(C.acid, C.ink));
put("mark/typer-mark-paper.svg", markTile(C.paper, C.ink));
put("mark/typer-mark-bare-ink.svg", markBare(C.ink));
put("mark/typer-mark-bare-acid.svg", markBare(C.acid));
put("mark/typer-mark-bare-paper.svg", markBare(C.paper));
for (const s of [32, 48, 64, 128, 256, 512, 1024]) {
  raster("mark/typer-mark-acid.svg", `mark/typer-mark-acid-${s}.png`, s);
}
for (const s of [128, 512]) {
  raster("mark/typer-mark-bare-acid.svg", `mark/typer-mark-bare-acid-${s}.png`, s);
}

// ---- wordmark/
// Kare işaret kullanılmadığında kullanılacak olan: kendi siyah zemini
// üstünde asit yeşili kelime.
put("wordmark/typer-wordmark-standalone.svg", wordPlate(C.ink, C.acid));
{
  const vb = /viewBox="([^"]+)"/.exec(wordPlate(C.ink, C.acid))[1].split(" ").map(Number);
  for (const w of [512, 1024]) {
    raster("wordmark/typer-wordmark-standalone.svg",
      `wordmark/typer-wordmark-standalone-${w}.png`, w, Math.round(w * vb[3] / vb[2]));
  }
}
put("wordmark/typer-wordmark-ink.svg", wordmark(C.ink));
put("wordmark/typer-wordmark-paper.svg", wordmark(C.paper));
put("wordmark/typer-wordmark-acid.svg", wordmark(C.acid));
const wAspect = (WH + 4) / (WW + 4);
for (const w of [512, 1024]) {
  raster("wordmark/typer-wordmark-ink.svg", `wordmark/typer-wordmark-ink-${w}.png`, w, Math.round(w * wAspect));
  raster("wordmark/typer-wordmark-paper.svg", `wordmark/typer-wordmark-paper-${w}.png`, w, Math.round(w * wAspect), C.ink);
}

// ---- lockups/
const LOCK = {
  light: { markBody: bodyOf(markTile(C.ink, C.acid)), wordColor: C.ink },
  dark: { markBody: bodyOf(markTile(C.acid, C.ink)), wordColor: C.paper },
  "mono-ink": { markBody: markPaths(C.ink), wordColor: C.ink },
  "mono-paper": { markBody: markPaths(C.paper), wordColor: C.paper },
};
for (const [name, o] of Object.entries(LOCK)) {
  put(`lockups/typer-lockup-horizontal-${name}.svg`, lockupH(o));
  put(`lockups/typer-lockup-vertical-${name}.svg`, lockupV(o));
}
{
  const vbOf = (svg) => /viewBox="([^"]+)"/.exec(svg)[1].split(" ").map(Number);
  const h = vbOf(lockupH(LOCK.light));
  for (const w of [512, 1024]) {
    raster("lockups/typer-lockup-horizontal-light.svg",
      `lockups/typer-lockup-horizontal-light-${w}.png`, w, Math.round(w * (h[3] / h[2])));
    raster("lockups/typer-lockup-horizontal-dark.svg",
      `lockups/typer-lockup-horizontal-dark-${w}.png`, w, Math.round(w * (h[3] / h[2])), C.ink);
  }
  const v = vbOf(lockupV(LOCK.light));
  raster("lockups/typer-lockup-vertical-light.svg",
    "lockups/typer-lockup-vertical-light-512.png", 512, Math.round(512 * (v[3] / v[2])));
}

// ---- app-icons/
put("app-icons/favicon.svg", markTile(C.ink, C.acid));
put("app-icons/icon.svg", markTile(C.ink, C.acid));
put("app-icons/icon-maskable.svg", markBleed(C.ink, C.acid, 0.60));
// iOS köşeyi kendisi yuvarlar; yuvarlak köşeli bir PNG verirsek köşe iki
// kez yuvarlanır ve simge içeri büzülür.
put("app-icons/apple-touch.svg", markTile(C.ink, C.acid, 0));
put("app-icons/safari-pinned-tab.svg",
  markBare("#000000").replace(/width="\d+" height="\d+"/, 'width="16" height="16"'));
// 16/32/48 .ico'ya girer; 20/24/64 kilavuzun kucuk boy seridi ve
// yuksek DPI tarayici sekmeleri icin.
for (const s of [16, 20, 24, 32, 48, 64]) raster("app-icons/favicon.svg", `app-icons/favicon-${s}.png`, s);
for (const s of [192, 512]) raster("app-icons/icon.svg", `app-icons/icon-${s}.png`, s);
raster("app-icons/icon.svg", "app-icons/icon.png", 512);
for (const s of [192, 512]) raster("app-icons/icon-maskable.svg", `app-icons/icon-maskable-${s}.png`, s);
raster("app-icons/apple-touch.svg", "app-icons/apple-touch-icon.png", 180);
for (const s of [120, 152, 167]) raster("app-icons/apple-touch.svg", `app-icons/apple-touch-icon-${s}.png`, s);
for (const s of [70, 150, 310]) raster("app-icons/icon.svg", `app-icons/mstile-${s}.png`, s);
raster("app-icons/icon.svg", "app-icons/mstile-310x150.png", 310, 150);

put("app-icons/site.webmanifest", JSON.stringify({
  name: "Typer",
  short_name: "Typer",
  description: "Bir tuşa bas, konuş, yazı imlecinin olduğu yere düşsün.",
  icons: [
    { src: "icon-192.png", sizes: "192x192", type: "image/png" },
    { src: "icon-512.png", sizes: "512x512", type: "image/png" },
    { src: "icon-maskable-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
    { src: "icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
  ],
  theme_color: C.ink,
  background_color: C.ink,
  display: "standalone",
}, null, 2));

put("app-icons/browserconfig.xml", [
  '<?xml version="1.0" encoding="utf-8"?>',
  "<browserconfig><msapplication><tile>",
  '  <square70x70logo src="mstile-70.png"/>',
  '  <square150x150logo src="mstile-150.png"/>',
  '  <wide310x150logo src="mstile-310x150.png"/>',
  '  <square310x310logo src="mstile-310.png"/>',
  `  <TileColor>${C.ink}</TileColor>`,
  "</tile></msapplication></browserconfig>",
].join("\n"));

put("app-icons/head-snippet.html", [
  "<!-- Typer — favicon ve uygulama simgeleri -->",
  '<link rel="icon" href="/favicon.ico" sizes="any">',
  '<link rel="icon" href="/favicon.svg" type="image/svg+xml">',
  '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
  `<link rel="mask-icon" href="/safari-pinned-tab.svg" color="${C.acid}">`,
  '<link rel="manifest" href="/site.webmanifest">',
  `<meta name="theme-color" content="${C.ink}">`,
  `<meta name="msapplication-TileColor" content="${C.ink}">`,
  '<meta name="msapplication-config" content="/browserconfig.xml">',
].join("\n"));

// ---- social/
put("social/avatar.svg", markBleed(C.ink, C.acid, 0.60));
for (const s of [1024, 640, 400]) raster("social/avatar.svg", `social/avatar-${s}.png`, s);
raster("social/avatar.svg", "social/avatar-640-whatsapp.png", 640);
{
  // OG kartı: siyah zeminde ortalanmış yatay kilit. Metin yok — metin bir
  // font demek, font da kitin dışına bağımlılık demek.
  const lock = lockupH(LOCK.dark);
  const vb = /viewBox="([^"]+)"/.exec(lock)[1].split(" ").map(Number);
  const targetW = 620, k = targetW / vb[2];
  const card = (w, h) => doc(`0 0 ${w} ${h}`, w, h,
    `<rect width="${w}" height="${h}" fill="${C.ink}"/>` +
    `<g transform="translate(${((w - targetW) / 2 - vb[0] * k).toFixed(2)} ${((h - vb[3] * k) / 2 - vb[1] * k).toFixed(2)}) scale(${k.toFixed(4)})">` +
    `${bodyOf(lock)}</g>`);
  put("social/og-default.svg", card(1200, 630));
  raster("social/og-default.svg", "social/og-default.png", 1200, 630, C.ink);
  put("social/github-social.svg", card(1280, 640));
  raster("social/github-social.svg", "social/github-social-1280x640.png", 1280, 640, C.ink);
}

// ---- product/
// Tepsi / menü çubuğu simgesi: saf beyaz, saydam zemin. macOS menü çubuğu
// yalnızca ALFA kanalına bakar (şablon görüntü), Windows tepsisi rengi
// olduğu gibi çizer; beyaz ikisini tek dosyayla karşılar.
put("product/typer-tray.svg", markBare(C.white, 3.0));
for (const s of [16, 20, 24, 32, 48, 64]) raster("product/typer-tray.svg", `product/typer-tray-${s}.png`, s);
put("product/typer-mark-on-dark.svg", markBare(C.acid, 2.2));

// ÜRÜNÜN İÇİNE YAZILANLAR. Arayüz hiçbir markayı elle çizmez, hepsini
// buradan alır — harf burada değişince kapsüldeki de, tepsideki de
// değişir. Ayrı çizilselerdi biri gün gelir güncellenir, öteki unutulur.
{
  const hedef = path.resolve(ROOT, "..", "ui", "mark.svg");
  fs.writeFileSync(hedef, markTile(C.acid, C.ink).trim() + "\n", "utf8");
  console.log("  ui/mark.svg  (kapsülün solundaki işaret)");
}

// TEPSİ SİMGESİ — iki işletim sistemi, iki dosya, çünkü kuralları farklı.
//
//   Windows  renkli pikselleri olduğu gibi çizer. Fayanslı işaret HEM
//            koyu HEM açık görev çubuğunda okunur: koyuda fayans zemine
//            karışır ve asit t havada durur, açıkta fayansın kendisi
//            görünür. Tek renk beyaz bir harf açık temada kaybolur —
//            eski simgenin sorunu buydu, iki zeminde de ölçüldü.
//   macOS    ŞABLON görüntü ister: rengi tamamen yok sayar, yalnızca
//            ALFA kanalına bakıp menü çubuğunun temasından boyar. Oraya
//            fayans göndermek kocaman dolu bir kare demek olurdu, o
//            yüzden çıplak harf gider.
raster("mark/typer-mark-acid.svg", "../ui/icon.png", 32);
raster("product/typer-tray.svg", "../ui/icon-template.png", 36);

// ---- brand-tokens.json
// Elle yazılmaz: art.js'ten türer, yani dosya asla geometriyle çelişemez.
put("brand-tokens.json", JSON.stringify({
  name: "Typer",
  tagline: "Bir tuşa bas, konuş, yazı imlecinin olduğu yere düşsün.",
  colors: C,
  contrast: {
    "acid / ink": 15.9,
    "ink / paper": 17.97,
    "moss / paper": 4.9,
    "mute / paper": 4.66,
    "mist / ink": 8.37,
    note: "acid açık zeminde METİN olarak kullanılmaz (1.13). Açık zeminde " +
      "asit gerektiğinde moss kullanılır.",
  },
  typography: {
    mark: "Elle çizilmiş bezier yolları.",
    logotype: "Modern Sans Serif 7 (Style-7, styleseven.com), " +
      WORDMARK.slant + " derece eğimle vektör yoluna çevrildi, harf aralığı " +
      WORDMARK.track + " em.",
    credit: "Ücretsiz yazılımda kullanım künyede kredi ister; " +
      "ticari kullanım için lisans gerekir.",
    fontDependency: "YOK — font hiçbir çıktının içinde taşınmaz, " +
      "harfler bir kez yola çevrildi.",
    ui: "Ürün arayüzü işletim sisteminin kendi arayüz fontunu kullanır.",
  },
  mark: {
    coordinateSpace: `0 0 ${MARK.box} ${MARK.box}`,
    tileRadius: MARK.tileRadius,
    fill: MARK.fill,
    bbox: MARK.bbox,
    note: "Kare işaretteki t, logotype'ın t'siyle aynı yoldur — aynı " +
      "fonttan, aynı eğimle, tek üretimde çıkar.",
  },
  wordmark: {
    bbox: WORDMARK.bbox,
    metrics: WORDMARK.metrics,
    slant: WORDMARK.slant,
    track: WORDMARK.track,
  },
  lockup: {
    note: "Yatay kilitte kelimenin x-yüksekliği bandı fayansla BİREBİR " +
      "aynı yüksekliktedir; t'nin çıkıntısı ile y ve p'nin kuyrukları " +
      "bilerek dışarı taşar.",
    xHeightEqualsMark: true,
    gapRatio: GAP_H,
    stackedXHeightRatio: XH_V,
    stackedGapRatio: GAP_V,
  },
  clearSpace: "İşaret kenarının 0.25'i kadar, dört yandan.",
  minSize: { markPx: 16, lockupWidthPx: 132 },
}, null, 2));

// ---- portable/  (çizgi yok, yalnızca dolgu)
put("portable/typer-mark-outlined.svg", outlineSVG(markTile(C.ink, C.acid)));
put("portable/typer-mark-bare-outlined.svg", outlineSVG(markBare(C.ink)));
put("portable/typer-wordmark-outlined.svg", outlineSVG(wordmark(C.ink)));
put("portable/typer-lockup-horizontal-outlined.svg", outlineSVG(lockupH(LOCK.light)));

/* ------------------------------------------------------------ rasterleme */

if (SVG_ONLY) {
  console.log(`${nSvg} SVG yazıldı (PNG atlandı: --svg)`);
  process.exit(0);
}

const jobsFile = path.join(__dirname, "_jobs-build.json");
fs.writeFileSync(jobsFile, JSON.stringify(jobs));
const electron = require("electron");
console.log(`${nSvg} SVG yazıldı; ${jobs.length} PNG rasterleniyor...`);
const r = spawnSync(electron, [path.join(__dirname, "raster.js"), jobsFile], {
  stdio: ["ignore", "pipe", "pipe"], encoding: "utf8",
});
const noise = /GPU process|Network service|DevTools|Electron Security|^\s*$/;
for (const line of (r.stdout || "").split("\n")) {
  if (line && !noise.test(line)) process.stdout.write("  " + line + "\n");
}
for (const line of (r.stderr || "").split("\n")) {
  if (line && !noise.test(line)) process.stderr.write("  ! " + line + "\n");
}
if (r.status !== 0) {
  console.error("rasterleme başarısız");
  process.exit(1);
}
fs.unlinkSync(jobsFile);

// ---- favicon.ico (16 + 32 + 48 gömülü PNG)
writeIco(path.join(ROOT, "app-icons/favicon.ico"),
  [16, 32, 48].map((s) => ({ size: s, path: path.join(ROOT, `app-icons/favicon-${s}.png`) })));
console.log("  favicon.ico  16+32+48");

console.log("bitti.");
