/* Typer markasının GEOMETRİSİ — tek doğruluk kaynağı.
 *
 * İşaret ve kelime AYNI harften gelir: kare işaretteki "t", kelimenin
 * ilk harfinin ta kendisidir — aynı font, aynı eğim, aynı yol verisi,
 * tek bir üretimde çıkar (bkz. wordmark.js ve mkwordmark.js). Ayrı
 * çizilselerdi bir gün biri güncellenir, diğeri unutulurdu.
 *
 * Hiçbir çıktı bir font dosyasına bağlı değildir: harfler bir kez yola
 * çevrildi. Bir logonun biçimi, onu açan kişinin makinesinde hangi
 * fontun kurulu olduğuna bağlı olamaz.
 *
 * Bir şeyi değiştirmek için: renkler burada, harfler `mkwordmark.js`
 * ile yeniden üretilir. Sonra `npm run brand`.
 */
const WORDMARK = require("./wordmark");

// --------------------------------------------------------------- renkler
const C = {
  ink: "#0A0A0A",
  inkRaise: "#1E1E1C",
  acid: "#D2F53C",
  acidHi: "#E6FF7A",
  moss: "#5A7300",
  paper: "#F4F4F1",
  line: "#E4E4DE",
  mute: "#6E6E66",
  mist: "#A9A9A1",
  white: "#FFFFFF",
};

/* ---------------------------------------------------------------- İŞARET
 * Kare işaret: 32x32 uzayda, fayansın içine optik olarak oturtulmuş
 * "t". Fayans 0,0–32,32.
 */
const MARK = {
  box: WORDMARK.mark.box,
  tileRadius: 9,                    // fayans köşe yarıçapı (kenarın %28'i)
  fill: WORDMARK.mark.fill,         // harfin fayansı doldurma oranı
  d: WORDMARK.mark.d,
  bbox: WORDMARK.mark.bbox,
};

// İkisi de DOLGUDUR: harfin dış hattı. Çizgi kalınlığı diye bir şey yok,
// biçim harfin kendisinden gelir.
const markPaths = (color) => `<path d="${MARK.d}" fill="${color}"/>`;
const wordmarkPaths = (color) => `<path d="${WORDMARK.d}" fill="${color}"/>`;

module.exports = { C, MARK, WORDMARK, markPaths, wordmarkPaths };
