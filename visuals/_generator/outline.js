/* Çizgiyi (stroke) dolguya (fill) çeviren dönüştürücü — bağımlılıksız.
 *
 * Neden gerek var: `stroke-width` SVG'nin çekirdeğinde olsa da, üçüncü
 * tarafların bazı boru hatları (kesim makineleri, eski içe aktarıcılar,
 * bazı e-posta işleyicileri) çizgiyi ya yok sayar ya kalınlığını
 * bozar. Bir logonun kalınlığının başkasının eline kalması olmaz.
 * Bu yüzden `portable/` altına yalnız dolgudan oluşan bir sürüm konur.
 *
 * Nasıl: kavisler noktalara ayrılır; her parça bir dörtgene, her ek yeri
 * ve her uç bir daireye çevrilir. Hepsi TEK bir path'in alt yolları
 * olarak, aynı dönüş yönünde yazılır — `fill-rule: nonzero` üst üste
 * binen aynı yönlü şekilleri birleştirir. Kavis ötelemesi (offset)
 * yapmaya, dolayısıyla kendi kendini kesen kavislerle uğraşmaya gerek
 * kalmaz. Yuvarlak uç ve yuvarlak ek yeri bedava gelir.
 */

const SAMPLES = 22;            // kavis başına parça (yeterince pürüzsüz)
const EPS = 0.01;              // parçalar arası görünmez bindirme payı

function bez(p0, p1, p2, p3, t) {
  const u = 1 - t;
  return [
    u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
    u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1],
  ];
}

/* Bir path'in `d`sini nokta dizisine açar. Desteklenen komutlar:
   M L C Q Z (mutlak ve göreli). Logo yollarında bunlardan fazlası yok. */
function flatten(d) {
  const toks = d.match(/[MmLlCcQqZzHhVv]|-?\d*\.?\d+(?:e[-+]?\d+)?/gi) || [];
  const runs = [];
  let cur = null, pt = [0, 0], start = [0, 0], cmd = null, i = 0;
  const num = () => parseFloat(toks[i++]);
  const push = (p) => { if (cur) cur.push(p); };
  while (i < toks.length) {
    const t = toks[i];
    if (/[MmLlCcQqZzHhVv]/.test(t)) { cmd = t; i++; }
    const rel = cmd === cmd.toLowerCase();
    const R = (p) => (rel ? [pt[0] + p[0], pt[1] + p[1]] : p);
    switch (cmd.toUpperCase()) {
      case "M": {
        pt = R([num(), num()]); start = pt;
        cur = [pt]; runs.push(cur);
        cmd = rel ? "l" : "L";         // M'den sonraki sayılar L'dir
        break;
      }
      case "L": { pt = R([num(), num()]); push(pt); break; }
      case "H": { pt = [rel ? pt[0] + num() : num(), pt[1]]; push(pt); break; }
      case "V": { pt = [pt[0], rel ? pt[1] + num() : num()]; push(pt); break; }
      case "C": {
        const c1 = R([num(), num()]), c2 = R([num(), num()]), p3 = R([num(), num()]);
        for (let s = 1; s <= SAMPLES; s++) push(bez(pt, c1, c2, p3, s / SAMPLES));
        pt = p3; break;
      }
      case "Q": {
        const q = R([num(), num()]), p2 = R([num(), num()]);
        // Karesel -> kübik, tek formül.
        const c1 = [pt[0] + (2 / 3) * (q[0] - pt[0]), pt[1] + (2 / 3) * (q[1] - pt[1])];
        const c2 = [p2[0] + (2 / 3) * (q[0] - p2[0]), p2[1] + (2 / 3) * (q[1] - p2[1])];
        for (let s = 1; s <= SAMPLES; s++) push(bez(pt, c1, c2, p2, s / SAMPLES));
        pt = p2; break;
      }
      case "Z": { push(start); pt = start; i++; break; }
      default: i++;
    }
  }
  return runs.filter((r) => r.length > 0);
}

const f = (n) => (Math.round(n * 1000) / 1000).toString();

/* Yönü sabit bir dörtgen: parçanın kendi yönüne göre kurulduğu için
   parça hangi yöne giderse gitsin dönüş yönü aynı kalır. */
function quad(a, b, r) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len = Math.hypot(dx, dy);
  if (len < 1e-9) return "";
  const ux = dx / len, uy = dy / len;
  const nx = -uy * r, ny = ux * r;
  // Parcalar uc uca DEGIL, bindirmeli eklenir. Tam uc uca gelen iki
  // kenar kenar yumusatmadan otur: her ikisi de yarim saydam kalir ve
  // aralarinda sac teli kalinliginda koyu bir cizgi gorunur. EPS bunu
  // gorunmez bir bindirmeyle yok eder.
  const ax = a[0] - ux * EPS, ay = a[1] - uy * EPS;
  const bx = b[0] + ux * EPS, by = b[1] + uy * EPS;
  return `M${f(ax + nx)} ${f(ay + ny)}L${f(bx + nx)} ${f(by + ny)}` +
         `L${f(bx - nx)} ${f(by - ny)}L${f(ax - nx)} ${f(ay - ny)}Z`;
}

/* Dörtgenlerle AYNI dönüş yönünde daire (sweep=0). Ters yön nonzero
   altında delik açar; test sayfası bunu gözle doğruluyor. */
function disc(c, r) {
  return `M${f(c[0] - r)} ${f(c[1])}` +
         `A${f(r)} ${f(r)} 0 1 0 ${f(c[0] + r)} ${f(c[1])}` +
         `A${f(r)} ${f(r)} 0 1 0 ${f(c[0] - r)} ${f(c[1])}Z`;
}

/** Bir stroke'lu path'in `d`sini, aynı görüntüyü veren dolgu `d`sine çevirir.
 *  Yalnızca yuvarlak uç + yuvarlak ek yeri (logo çizgilerinin tamamı öyle). */
function strokeToFill(d, width) {
  const r = width / 2;
  const out = [];
  for (const run of flatten(d)) {
    if (run.length === 1) { out.push(disc(run[0], r)); continue; }
    for (let i = 0; i < run.length - 1; i++) out.push(quad(run[i], run[i + 1], r));
    for (const p of run) out.push(disc(p, r));   // ek yerleri + iki uç
  }
  return out.join("");
}

/** Bir SVG metnindeki her <path stroke=... stroke-width=...> öğesini
 *  dolgu path'ine çevirir. fill="none" olanlara dokunur, dolgulu
 *  olanları (kaligrafik yollar) olduğu gibi bırakır. */
function outlineSVG(svg) {
  return svg.replace(/<path\b[^>]*\/>/g, (tag) => {
    const stroke = /\sstroke="([^"]+)"/.exec(tag);
    const sw = /\sstroke-width="([^"]+)"/.exec(tag);
    const dm = /\sd="([^"]+)"/.exec(tag);
    if (!stroke || !sw || !dm || stroke[1] === "none") return tag;
    const d = strokeToFill(dm[1], parseFloat(sw[1]));
    return `<path d="${d}" fill="${stroke[1]}" fill-rule="nonzero"/>`;
  });
}

module.exports = { strokeToFill, outlineSVG, flatten };
