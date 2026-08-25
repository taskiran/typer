/* Logotype'ı bir kez üretir: harfleri fonttan okur, eğimi geometriye
 * işler, tek bir dolgu yoluna çevirip `wordmark.js` dosyasına yazar.
 *
 *   node visuals/_generator/mkwordmark.js <font.ttf> [--slant 12]
 *       [--track -0.015] [--markfill 0.72] [--marknudge 0]
 *
 * Bundan sonra font dosyasına bir daha gerek yoktur — ne derlemede, ne
 * çalışma anında, ne de depoda. Kelimeyi değiştirmek ya da eğimi
 * ayarlamak isteyen fontu eline alıp bu komutu tekrar çalıştırır.
 *
 * Eğim neden transform ile verilmiyor: `skewX` bir dönüşüm olarak
 * uygulanırsa yalnızca görüntü eğilir; yol verisi dik kalır ve dosyayı
 * açan herkes eğimi ayrıca taşımak zorunda kalır. Geometriye işlenince
 * yol neyse o olur.
 */
const fs = require("fs");
const path = require("path");
const ttf = require("./ttf");
const { flatten } = require("./outline");

const argv = process.argv.slice(2);
const FONT = argv[0];
const arg = (name, def) => {
  const i = argv.indexOf("--" + name);
  return i < 0 ? def : parseFloat(argv[i + 1]);
};
if (!FONT) {
  console.error("kullanım: node mkwordmark.js <font.ttf> [--slant 12] [--track -0.015]");
  process.exit(1);
}

const WORD = "typer";
const BOX = 32;                            // işaretin koordinat uzayı
const SLANT = arg("slant", 12);            // derece
const TRACK = arg("track", -0.015);        // em cinsinden harf aralığı
const MARKFILL = arg("markfill", 0.72);    // t'nin fayansı doldurma oranı
const NUDGE = arg("marknudge", 0);         // optik merkezleme payı (birim)
const EM = 100;                            // çalışma birimi: 1 em = 100

const f = ttf.open(FONT);
const s = EM / f.unitsPerEm;
const tan = Math.tan((SLANT * Math.PI) / 180);

let pen = 0;
let d = "";
for (const ch of WORD) {
  const at = pen;
  // font birimi (y yukarı) -> çalışma birimi (y aşağı), eğim dahil
  d += f.path(ch, (x, y) => [(x + at) * s + y * s * tan, -y * s]);
  pen += f.advance(f.gid(ch)) + TRACK * f.unitsPerEm;
}

// Yolun gerçek sınırı: eğri örneklemesiyle, kontrol noktalarıyla değil
// (kontrol noktaları eğrinin dışında kalır ve kutuyu şişirir).
let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
for (const run of flatten(d)) {
  for (const [x, y] of run) {
    if (x < x1) x1 = x;
    if (y < y1) y1 = y;
    if (x > x2) x2 = x;
    if (y > y2) y2 = y;
  }
}
const r3 = (n) => Math.round(n * 1000) / 1000;
const bbox = { x1: r3(x1), y1: r3(y1), x2: r3(x2), y2: r3(y2) };

/* Tipografik ölçüler. Kilit hizalaması bunlara dayanır: bir kelimeyi
 * sınır kutusunun ortasından hizalamak, altında kuyruk (y, p) olduğu
 * için onu optik olarak YUKARI kaçırır. Doğru referans x-yüksekliği
 * bandıdır — gözün "kelimenin gövdesi" saydığı yer. */
const topOf = (ch) => {
  let t = Infinity;
  for (const c of f.contours(ch)) for (const pt of c) if (-pt.y * s < t) t = -pt.y * s;
  return t;
};
const metrics = {
  baseline: 0,                     // yolun kendi koordinatında taban çizgisi
  xHeight: r3(-topOf("e")),        // yuvarlak harf birazcık taşar, o da doğru
  ascender: r3(-topOf("t")),
  descender: r3(bbox.y2),
};

/* ---------------------------------------------------------- KARE İŞARET
 * İşaretin harfi, kelimenin t'siyle AYNI YOLDUR — aynı fonttan, aynı
 * eğimle, aynı anda üretilir. Ayrı çizilseydi bir gün biri kelimeyi
 * güncelleyip işareti unuturdu; burada ayrışması imkânsız.
 *
 * Tek fark yerleşim: harf fayansın içine sığacak şekilde ölçeklenip
 * optik merkeze oturtulur. Ölçek "birebir aynı harf" iddiasını bozmaz,
 * biçim aynı biçimdir.
 */
const tRaw = f.path("t", (x, y) => [x * s + y * s * tan, -y * s]);
let tb = { x1: Infinity, y1: Infinity, x2: -Infinity, y2: -Infinity };
for (const run of flatten(tRaw)) {
  for (const [x, y] of run) {
    if (x < tb.x1) tb.x1 = x;
    if (y < tb.y1) tb.y1 = y;
    if (x > tb.x2) tb.x2 = x;
    if (y > tb.y2) tb.y2 = y;
  }
}
const tk = (BOX * MARKFILL) / Math.max(tb.x2 - tb.x1, tb.y2 - tb.y1);
const tcx = (tb.x1 + tb.x2) / 2, tcy = (tb.y1 + tb.y2) / 2;
const tdx = BOX / 2 - tcx * tk + NUDGE, tdy = BOX / 2 - tcy * tk;

/** M/L/Q/C/Z yollarındaki her koordinat çiftini taşır ve ölçekler. */
function place(d, k, dx, dy) {
  const parts = d.match(/[MLQCZ]|-?\d*\.?\d+/g) || [];
  let out = "", i = 0, isim = null;
  const say = () => parseFloat(parts[i++]);
  while (i < parts.length) {
    if (/[MLQCZ]/.test(parts[i])) { isim = parts[i++]; out += isim; if (isim === "Z") continue; }
    const n = { M: 1, L: 1, Q: 2, C: 3 }[isim] || 1;
    const xy = [];
    for (let j = 0; j < n; j++) {
      const x = say() * k + dx, y = say() * k + dy;
      xy.push(`${Math.round(x * 1000) / 1000} ${Math.round(y * 1000) / 1000}`);
    }
    out += xy.join(" ");
    // Aynı komut arka arkaya sayı alabilir; komut adı tekrar yazılmaz.
    if (i < parts.length && !/[MLQCZ]/.test(parts[i])) out += " ";
  }
  return out;
}
const markD = place(tRaw, tk, tdx, tdy);
const markBox = {
  x1: r3((tb.x1 - tcx) * tk + BOX / 2 + NUDGE),
  y1: r3((tb.y1 - tcy) * tk + BOX / 2),
  x2: r3((tb.x2 - tcx) * tk + BOX / 2 + NUDGE),
  y2: r3((tb.y2 - tcy) * tk + BOX / 2),
};

const out = path.join(__dirname, "wordmark.js");
fs.writeFileSync(out, `/* ÜRETİLMİŞ DOSYA — elle düzenlenmez.
 *
 * "typer" logotype'ı: harfler ${path.basename(FONT)} fontundan okunup
 * ${SLANT} derece eğimle vektör yoluna çevrildi (harf aralığı ${TRACK} em).
 * Font: Modern Sans Serif 7, Style-7 (styleseven.com). Ücretsiz
 * yazılımda kullanımı serbest, künyede kredi ister.
 *
 * Buradan sonra font dosyasına gerek yoktur: teslim edilen hiçbir asset
 * bir fonta bağlı değildir ve font hiçbir çıktının içinde taşınmaz.
 *
 * Yeniden üretmek için (font dosyası elde olmalı):
 *   node visuals/_generator/mkwordmark.js <font.ttf> --slant ${SLANT} --track ${TRACK}
 */
module.exports = {
  kind: "fill",
  slant: ${SLANT},
  track: ${TRACK},
  bbox: ${JSON.stringify(bbox)},
  metrics: ${JSON.stringify(metrics)},
  d: "${d}",
  // Kare işaret: kelimenin t'sinin ta kendisi, ${BOX}x${BOX} kutusuna
  // yerleştirilmiş hâli (doluluk ${MARKFILL}).
  mark: {
    fill: ${MARKFILL},
    box: ${BOX},
    bbox: ${JSON.stringify(markBox)},
    d: "${markD}",
  },
};
`, "utf8");

console.log(`yazıldı: ${out}`);
console.log(`  yol ${d.length} bayt, sınır ${JSON.stringify(bbox)}`);
console.log(`  en/boy ${((bbox.x2 - bbox.x1) / (bbox.y2 - bbox.y1)).toFixed(3)}`);
console.log(`  ölçüler ${JSON.stringify(metrics)}`);
console.log(`  işaret ${markD.length} bayt, sınır ${JSON.stringify(markBox)}`);
