/* Minik bir TrueType okuyucu — harfleri vektör yoluna çevirir.
 *
 * Neden var: logotype bir yazı tipiyle DİZİLMİYOR, harfleri bir kez
 * yola çevrilip `art.js` içine gömülüyor. Böylece
 *   - teslim edilen hiçbir asset bir font dosyasına bağlı kalmaz
 *     (karşı tarafta font kurulu değilse logo bozulmaz),
 *   - font dosyasının kendisi depoda ve dağıtılan hiçbir şeyin içinde
 *     taşınmaz, ki lisans açısından doğru olan da budur.
 *
 * Neden `opentype.js` değil: kit hiçbir pakete bağlı değil ve bu iş,
 * gereken kadarıyla, iki yüz satır. Okunan tablolar: head, maxp, cmap
 * (biçim 4), loca, glyf, hhea, hmtx.
 *
 * Doğrulaması gözle değil ölçüyle yapıldı: çıkan yollar, Chromium'un
 * aynı fontu aynı boyda dizdiği görüntüyle piksel piksel
 * karşılaştırıldı (bkz. diff.js).
 */
const fs = require("fs");

function tables(buf) {
  const n = buf.readUInt16BE(4);
  const t = {};
  for (let i = 0; i < n; i++) {
    const at = 12 + i * 16;
    t[buf.toString("ascii", at, at + 4)] = {
      off: buf.readUInt32BE(at + 8),
      len: buf.readUInt32BE(at + 12),
    };
  }
  return t;
}

/** cmap biçim 4: BMP karakterleri -> glif numarası. */
function charmap(buf, t) {
  const c = t.cmap;
  if (!c) throw new Error("cmap tablosu yok");
  const n = buf.readUInt16BE(c.off + 2);
  let sub = 0;
  for (let i = 0; i < n; i++) {
    const at = c.off + 4 + i * 8;
    const plat = buf.readUInt16BE(at), enc = buf.readUInt16BE(at + 2);
    const off = c.off + buf.readUInt32BE(at + 4);
    // Windows/Unicode BMP tercih edilir; yoksa eldeki ilk biçim 4.
    if ((plat === 3 && (enc === 1 || enc === 0)) || (plat === 0 && !sub)) {
      if (buf.readUInt16BE(off) === 4) sub = off;
    }
  }
  if (!sub) throw new Error("biçim 4 cmap alt tablosu yok");

  const segX2 = buf.readUInt16BE(sub + 6);
  const seg = segX2 / 2;
  const end = sub + 14, start = end + segX2 + 2;
  const delta = start + segX2, range = delta + segX2;
  const map = new Map();
  for (let i = 0; i < seg; i++) {
    const e = buf.readUInt16BE(end + i * 2);
    const s = buf.readUInt16BE(start + i * 2);
    const d = buf.readInt16BE(delta + i * 2);
    const r = buf.readUInt16BE(range + i * 2);
    if (s === 0xffff) continue;
    for (let ch = s; ch <= e && ch !== 0x10000; ch++) {
      let g;
      if (r === 0) g = (ch + d) & 0xffff;
      else {
        const at = range + i * 2 + r + (ch - s) * 2;
        g = buf.readUInt16BE(at);
        if (g) g = (g + d) & 0xffff;
      }
      if (g) map.set(ch, g);
    }
  }
  return map;
}

/** Bir glifin konturları: [[{x,y,on}, ...], ...] (font birimi, y yukarı). */
function contours(buf, t, loca, gid) {
  const from = loca[gid], to = loca[gid + 1];
  if (to <= from) return [];                    // boşluk gibi boş glif
  let p = t.glyf.off + from;
  const nc = buf.readInt16BE(p);
  p += 10;                                      // sayı + sınır kutusu
  if (nc < 0) throw new Error(`bileşik glif (${gid}) desteklenmiyor`);

  const ends = [];
  for (let i = 0; i < nc; i++) { ends.push(buf.readUInt16BE(p)); p += 2; }
  const npt = ends[nc - 1] + 1;
  p += 2 + buf.readUInt16BE(p);                 // hinting yönergeleri atlanır

  const flags = [];
  while (flags.length < npt) {
    const f = buf.readUInt8(p++);
    flags.push(f);
    if (f & 8) { let r = buf.readUInt8(p++); while (r-- > 0) flags.push(f); }
  }
  const coord = (shortBit, sameBit) => {
    const out = [];
    let v = 0;
    for (const f of flags) {
      if (f & shortBit) {
        const d = buf.readUInt8(p++);
        v += (f & sameBit) ? d : -d;
      } else if (!(f & sameBit)) {
        v += buf.readInt16BE(p); p += 2;
      }
      out.push(v);
    }
    return out;
  };
  const xs = coord(2, 16), ys = coord(4, 32);

  const out = [];
  let s = 0;
  for (const e of ends) {
    const pts = [];
    for (let i = s; i <= e; i++) pts.push({ x: xs[i], y: ys[i], on: !!(flags[i] & 1) });
    out.push(pts);
    s = e + 1;
  }
  return out;
}

/* Konturu SVG yoluna çevirir. TrueType karesel (quadratic) çalışır ve
   ard arda iki kontrol noktası varsa aralarında ÖRTÜK bir eğri noktası
   vardır — aşağıdaki orta nokta hesabı o kuralı uyguluyor. */
function toPath(cs, map, f = (n) => Math.round(n * 100) / 100) {
  let d = "";
  for (const pts of cs) {
    if (!pts.length) continue;
    // Yol bir EĞRİ noktasından başlamalı; hepsi kontrolse örtük orta
    // noktadan başlanır.
    let i0 = pts.findIndex((p) => p.on);
    let startPt;
    if (i0 < 0) {
      i0 = 0;
      startPt = { x: (pts[0].x + pts[pts.length - 1].x) / 2,
                  y: (pts[0].y + pts[pts.length - 1].y) / 2 };
    } else startPt = pts[i0];

    const P = (p) => map(p.x, p.y).map(f).join(" ");
    d += `M${P(startPt)}`;
    let ctrl = null;
    for (let k = 1; k <= pts.length; k++) {
      const p = pts[(i0 + k) % pts.length];
      if (p.on) {
        d += ctrl ? `Q${P(ctrl)} ${P(p)}` : `L${P(p)}`;
        ctrl = null;
      } else if (ctrl) {
        const mid = { x: (ctrl.x + p.x) / 2, y: (ctrl.y + p.y) / 2 };
        d += `Q${P(ctrl)} ${P(mid)}`;
        ctrl = p;
      } else ctrl = p;
    }
    d += ctrl ? `Q${P(ctrl)} ${P(startPt)}Z` : "Z";
  }
  return d;
}

/** Dosyayı aç ve gereken her şeyi hazırla. */
function open(file) {
  const buf = fs.readFileSync(file);
  const t = tables(buf);
  for (const need of ["head", "maxp", "cmap", "loca", "glyf", "hhea", "hmtx"]) {
    if (!t[need]) throw new Error(`${need} tablosu yok`);
  }
  const unitsPerEm = buf.readUInt16BE(t.head.off + 18);
  const longLoca = buf.readInt16BE(t.head.off + 50) === 1;
  const numGlyphs = buf.readUInt16BE(t.maxp.off + 4);
  const numHM = buf.readUInt16BE(t.hhea.off + 34);

  const loca = [];
  for (let i = 0; i <= numGlyphs; i++) {
    loca.push(longLoca ? buf.readUInt32BE(t.loca.off + i * 4)
                       : buf.readUInt16BE(t.loca.off + i * 2) * 2);
  }
  const cmap = charmap(buf, t);
  const advance = (gid) => buf.readUInt16BE(
    t.hmtx.off + Math.min(gid, numHM - 1) * 4);

  return {
    unitsPerEm,
    gid: (ch) => cmap.get(ch.codePointAt(0)),
    advance,
    /** Bir harfin yolu. map(x, y) -> [x', y'] ile dönüştürülür. */
    path: (ch, map) => toPath(contours(buf, t, loca, cmap.get(ch.codePointAt(0))), map),
    contours: (ch) => contours(buf, t, loca, cmap.get(ch.codePointAt(0))),
  };
}

module.exports = { open };
