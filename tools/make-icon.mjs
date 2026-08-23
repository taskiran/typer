/*
 * Typer'ın işareti — kapsülün içindeki ekolayzerin küçültülmüş hâli.
 *
 * node tools/make-icon.mjs   ->  ui/icon.png
 *
 * Neden bir betik ve neden elle çizilmiş bir PNG değil: simge iki farklı
 * yerde, iki farklı kuralla kullanılıyor. Windows tepsisi renkli pikselleri
 * olduğu gibi çizer; macOS menü çubuğu ise ŞABLON görüntü ister ve yalnızca
 * ALFA kanalına bakar, rengi tamamen yok sayar. Çubukları tam opak beyaz
 * çizmek ikisini de tek dosyayla karşılar: Windows'ta beyaz görünür,
 * Mac'te menü çubuğunun kendi rengine bürünür (koyu temada beyaz, açık
 * temada siyah). Simgeyi değiştirmek isteyen BARS dizisini değiştirsin.
 */
import { deflateSync } from 'node:zlib';
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, '..', 'ui', 'icon.png');

const SIZE = 32;
// Yedi çubuk, ortadan yükselen. Değerler tam yüksekliğin oranı.
const BARS = [0.30, 0.55, 0.85, 1.0, 0.85, 0.55, 0.30];

function render() {
  const px = new Uint8Array(SIZE * SIZE * 4);        // RGBA, hepsi şeffaf
  const gap = 1;
  const bw = 3;
  const total = BARS.length * bw + (BARS.length - 1) * gap;
  const x0 = Math.round((SIZE - total) / 2);
  const maxH = SIZE - 6;

  BARS.forEach((v, i) => {
    const h = Math.max(3, Math.round(v * maxH));
    const x = x0 + i * (bw + gap);
    const y = Math.round((SIZE - h) / 2);
    for (let yy = y; yy < y + h; yy++) {
      for (let xx = x; xx < x + bw; xx++) {
        // Uçlardaki tek pikseli yumuşat, ki çubuklar 16px'e küçüldüğünde
        // testere dişi gibi durmasın.
        const edge = (yy === y || yy === y + h - 1) ? 190 : 255;
        const o = (yy * SIZE + xx) * 4;
        px[o] = px[o + 1] = px[o + 2] = 255;
        px[o + 3] = edge;
      }
    }
  });
  return px;
}

// --- asgari PNG kodlayıcı (RGBA, filtresiz) -----------------------------

const CRC_TABLE = (() => {
  const t = new Int32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c;
  }
  return t;
})();

function crc32(buf) {
  let c = ~0;
  for (const b of buf) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return ~c >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

function png(width, height, rgba) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;        // bit derinliği
  ihdr[9] = 6;        // renk tipi: RGBA
  // 10..12: sıkıştırma, filtre, dokuma — hepsi 0

  // Her tarama satırı bir filtre baytıyla başlar; 0 = filtre yok.
  const raw = Buffer.alloc(height * (width * 4 + 1));
  for (let y = 0; y < height; y++) {
    raw[y * (width * 4 + 1)] = 0;
    Buffer.from(rgba.buffer, y * width * 4, width * 4)
      .copy(raw, y * (width * 4 + 1) + 1);
  }

  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

mkdirSync(dirname(OUT), { recursive: true });
writeFileSync(OUT, png(SIZE, SIZE, render()));
console.log(`yazıldı: ${OUT}  (${SIZE}x${SIZE})`);
