/*
 * Sayfa ile uygulama arasındaki tek köprü.
 *
 * Sayfa kum havuzunda kalır — node yok, fs yok, kendine ait bir pano yok.
 * Ana süreçten itilen durumu alır ve karşılığında tam olarak bir şey
 * isteyebilir: kartı kapat, isteğe bağlı olarak metni kopyalayarak.
 */
'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('typer', {
  // ana süreç -> sayfa: güncel durum
  onState: (fn) => ipcRenderer.on('typer:state', (_e, s) => fn(s)),
  // sayfa -> ana süreç: kart kapatıldı (copy true ise metin panoya)
  dismiss: (copy) => ipcRenderer.send('typer:dismiss', !!copy),
});
