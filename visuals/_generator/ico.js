/* PNG gömülü .ico yazıcı — bağımlılıksız.
 *
 * Bir .ico aslında bir dizin ve arkasına yapıştırılmış görüntülerdir.
 * Vista'dan beri her Windows ve her tarayıcı, gömülü görüntünün doğrudan
 * PNG olmasını kabul eder; BMP + AND maskesi yazmaya gerek yok.
 */
const fs = require("fs");

const HEADER = 6;
const ENTRY = 16;

/** pngs: [{ size: 16, buf: <Buffer> }, ...]  ->  Buffer */
function ico(pngs) {
  const imgs = [...pngs].sort((a, b) => a.size - b.size);
  const dir = Buffer.alloc(HEADER + ENTRY * imgs.length);
  dir.writeUInt16LE(0, 0);              // ayrılmış
  dir.writeUInt16LE(1, 2);              // tip: 1 = simge
  dir.writeUInt16LE(imgs.length, 4);
  let offset = dir.length;
  imgs.forEach((img, i) => {
    const at = HEADER + i * ENTRY;
    // 256 piksel tek bayta sığmaz; biçim onu 0 olarak yazar.
    dir.writeUInt8(img.size >= 256 ? 0 : img.size, at);
    dir.writeUInt8(img.size >= 256 ? 0 : img.size, at + 1);
    dir.writeUInt8(0, at + 2);          // palet yok
    dir.writeUInt8(0, at + 3);          // ayrılmış
    dir.writeUInt16LE(1, at + 4);       // düzlem
    dir.writeUInt16LE(32, at + 6);      // bit/piksel
    dir.writeUInt32LE(img.buf.length, at + 8);
    dir.writeUInt32LE(offset, at + 12);
    offset += img.buf.length;
  });
  return Buffer.concat([dir, ...imgs.map((i) => i.buf)]);
}

function writeIco(out, files) {
  const pngs = files.map((f) => ({ size: f.size, buf: fs.readFileSync(f.path) }));
  fs.writeFileSync(out, ico(pngs));
  return out;
}

module.exports = { ico, writeIco };
