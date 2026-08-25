/* Iki PNG'yi piksel piksel karsilastirir — kit icin regresyon araci.
 *
 *   electron visuals/_generator/diff.js a.png b.png [x] [fark-haritasi.png]
 *
 * Ciktisi: en buyuk fark, ortalama fark, 8'in uzerinde farkli piksel sayisi.
 * Cizgili sürüm ile dolguya cevrilmis sürümün ayni ciktigini dogrulamak,
 * ya da bir geometri degisikliginin baska bir asseti bozup bozmadigini
 * gormek icin. Fark haritasi verilirse farkli pikseller kirmizi yazilir.
 */
const { app, BrowserWindow } = require("electron");
const fs = require("fs"), path = require("path");
app.disableHardwareAcceleration();
const [A, B] = process.argv.slice(2);
const b64 = (f) => "data:image/png;base64," + fs.readFileSync(f).toString("base64");
app.whenReady().then(async () => {
  const win = new BrowserWindow({ show: false, webPreferences: { offscreen: false } });
  const html = `<!doctype html><body><script>
    window.run = () => new Promise((res) => {
      const a = new Image(), b = new Image();
      let n = 0;
      const go = () => { if (++n < 2) return;
        const c = document.createElement("canvas");
        c.width = a.width; c.height = a.height;
        const x = c.getContext("2d", { willReadFrequently: true });
        x.drawImage(a, 0, 0); const pa = x.getImageData(0,0,c.width,c.height).data;
        x.clearRect(0,0,c.width,c.height); x.drawImage(b, 0, 0);
        const pb = x.getImageData(0,0,c.width,c.height).data;
        let max = 0, sum = 0, over8 = 0;
        for (let i = 0; i < pa.length; i += 4) {
          // alfa ile carpilmis fark: seffaf pikseller rengi bozmasin
          const aa = pa[i+3]/255, ab = pb[i+3]/255;
          const d = Math.max(
            Math.abs(pa[i]*aa - pb[i]*ab), Math.abs(pa[i+1]*aa - pb[i+1]*ab),
            Math.abs(pa[i+2]*aa - pb[i+2]*ab), Math.abs(pa[i+3] - pb[i+3]));
          if (d > max) max = d; sum += d; if (d > 8) over8++;
        }
        // fark haritasi: farkli olan piksel kirmizi, aynilar soluk
        const out = x.createImageData(c.width, c.height);
        for (let i = 0; i < pa.length; i += 4) {
          const aa = pa[i+3]/255, ab = pb[i+3]/255;
          const d = Math.max(
            Math.abs(pa[i]*aa - pb[i]*ab), Math.abs(pa[i+1]*aa - pb[i+1]*ab),
            Math.abs(pa[i+2]*aa - pb[i+2]*ab), Math.abs(pa[i+3] - pb[i+3]));
          out.data[i] = d > 8 ? 255 : 20; out.data[i+1] = d > 8 ? 0 : 20;
          out.data[i+2] = 0; out.data[i+3] = 255;
        }
        x.putImageData(out, 0, 0);
        res({ max, mean: +(sum/(pa.length/4)).toFixed(3), over8,
              px: pa.length/4, w: a.width, h: a.height, map: c.toDataURL() });
      };
      a.onload = go; b.onload = go; a.src = ${JSON.stringify(b64(A))}; b.src = ${JSON.stringify(b64(B))};
    });
  </script></body>`;
  await win.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(html));
  const r = await win.webContents.executeJavaScript("window.run()");
  if (r.map && process.argv[5]) {
    fs.writeFileSync(process.argv[5], Buffer.from(r.map.split(",")[1], "base64"));
    delete r.map;
  } else delete r.map;
  console.log(JSON.stringify(r));
  app.exit(0);
});
