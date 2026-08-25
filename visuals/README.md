# Typer marka kiti

İşaret, logotype, kilitler, favicon ve uygulama simgesi matrisi, sosyal
görseller ve makine tarafından okunabilir markalar. Hepsi tek bir kaynaktan
(`_generator/art.js`) üretilir, o yüzden hiçbir dosya diğerinden ayrı düşmez.

Basılabilir kılavuz: [`Typer-Brand-Guide.pdf`](Typer-Brand-Guide.pdf).

---

## Hangi dosya nerede

| Yüzey | Kullanılacak dosya |
| --- | --- |
| Uygulama simgesi | `app-icons/icon.png` (512) |
| Tarayıcı favicon | `app-icons/favicon.ico` + `app-icons/favicon.svg` |
| iOS ana ekran | `app-icons/apple-touch-icon.png` (180) |
| Android / PWA | `app-icons/icon-maskable-512.png` + `app-icons/site.webmanifest` |
| Windows Başlat kutucukları | `app-icons/mstile-*.png` + `browserconfig.xml` |
| Safari sabitlenmiş sekme | `app-icons/safari-pinned-tab.svg` |
| Tepsi / menü çubuğu | `product/typer-tray-32.png` (beyaz, alfa şablon) |
| Kare işaret olmadan, yalnız kelime | `wordmark/typer-wordmark-standalone.svg` |
| Site ya da doküman başlığı (açık) | `lockups/typer-lockup-horizontal-light.svg` |
| Koyu yüzey başlığı | `lockups/typer-lockup-horizontal-dark.svg` |
| GitHub sosyal önizleme | `social/github-social-1280x640.png` |
| Bağlantı önizlemesi (OG) | `social/og-default.png` (1200x630) |
| Profil fotoğrafı | `social/avatar-1024.png` (640 / 400 de var) |
| WhatsApp Business | `social/avatar-640-whatsapp.png` |
| Üçüncü taraf / bilinmeyen çizici | `portable/*-outlined.svg` |

## Klasör haritası

```
visuals/
  README.md                 bu dosya
  brand-tokens.json         renkler, geometri, oranlar — makine okur
  Typer-Brand-Guide.pdf     basılabilir kılavuz
  mark/                     yalnız kare işaret (fayanslı ve fayanssız)
  wordmark/                 yalnız "typer" kelimesi
  lockups/                  işaret + kelime (yatay ve dikey, dört işlem)
  app-icons/                favicon + tüm platform simgeleri + manifest
  social/                   OG kartı, avatarlar
  product/                  ürünün içinde kullanılan tam çıktılar
  portable/                 çizgisi dolguya çevrilmiş sürümler
  _generator/               hepsini üreten betikler
```

## Dosya adlandırma

`typer-{bileşen}-{dizilim?}-{işlem}[-{boy}].{uzantı}`

- **bileşen**: `mark` | `wordmark` | `lockup`. Platform simgeleri
  (`favicon.ico`, `apple-touch-icon.png`, `mstile-150.png`) işletim
  sistemlerinin beklediği adları korur; onlar yeniden adlandırılmaz.
- **dizilim** (kilitlerde): `horizontal` | `vertical`.
- **işlem**: `acid` (siyah fayans, asit t) | `invert` (asit fayans, siyah t) |
  `paper` (açık gri fayans) | `bare-*` (fayanssız) | `light` / `dark`
  (kilitlerde, zemine göre) | `mono-ink` / `mono-paper` (tek renk) |
  `outlined` (taşınabilir).
- **boy**: PNG'lerde piksel. Kare olmayanlarda genişlik.

---

## Renk

| Token | Hex | Rolü |
| --- | --- | --- |
| `ink` | `#0A0A0A` | siyah — ana yüzey, ana metin |
| `acid` | `#D2F53C` | asit yeşili — tek vurgu |
| `paper` | `#F4F4F1` | çok açık gri — açık yüzey |
| `moss` | `#5A7300` | asitin açık zeminde okunan hâli (AA, 4.90) |
| `ink-raise` | `#1E1E1C` | koyu yüzeyde bir üst kat |
| `acid-hi` | `#E6FF7A` | koyu zeminde parlak uç |
| `line` | `#E4E4DE` | açık zeminde ayraç |
| `mute` | `#6E6E66` | açık zeminde ikincil metin (AA, 4.66) |
| `mist` | `#A9A9A1` | koyu zeminde ikincil metin (8.37) |

**Tek kural:** açık zeminde asit yeşiliyle yazı yazılmaz — beyaz üzerinde
kontrastı 1.13'tür. Orada asit yalnızca dolgu, vurgu şeridi ya da grafik
öğedir; metin gerekiyorsa `moss` kullanılır. Koyu zeminde asit rahat okunur
(15.90).

## Tipografi

**İşaret ve kelime aynı harftir.** Kare işaretteki `t`, logotype'ın ilk
harfinin ta kendisidir: aynı font, aynı eğim, aynı yol verisi, tek bir
üretimde çıkar. Ayrı çizilselerdi bir gün biri güncellenir, diğeri
unutulurdu; burada ayrışmaları imkânsız.

Harfler [Modern Sans Serif 7](http://www.styleseven.com/) (Style-7)
fontundan bir kez okunup 12 derece eğimle vektör yoluna çevrilmiştir
(harf aralığı -0.015 em).

### Yatay kilidin tek kuralı

Kelimenin **gövdesi** (x-yüksekliği bandı) fayansla **birebir aynı
yüksekliktedir**. `t`'nin çıkıntısı ile `y` ve `p`'nin kuyrukları o bandın
dışında kalır ve fayansın üstüne/altına bilerek taşar. Yan yana
durduklarında göz iki ayrı yükseklik görmez: harflerin omuzları fayansın
üst kenarıyla, tabanları alt kenarıyla aynı hizada oturur. Ölçek buradan
hesaplanır, göz kararıyla değil.

### Kelime tek başınayken

Kare işaret kullanılmadığında kelime **siyah zeminde asit yeşilidir**
(`wordmark/typer-wordmark-standalone.svg`). Kendi zeminini yanında
taşıması hem markanın enerjisini koruyor hem de okunaklılığı garanti
ediyor: açık zeminde asit yeşili metnin kontrastı 1.13 iken siyah zeminde
15.9.

**Hiçbir asset bir font dosyasına bağlı değildir.** Teslim edilen
dosyaların içinde `<text>`, `font-family` ya da gömülü font yoktur; font
dosyasının kendisi de bu depoda taşınmaz. Bir logonun biçimi, onu açan
kişinin makinesinde hangi fontun kurulu olduğuna bağlı olamaz. Kelime
yeniden dizilmez, "benzer bir fontla" yazılmaz — logotype artık bir
vektördür, bir metin değil.

**Künye.** Modern Sans Serif 7 ücretsiz yazılımda kullanılabilir ve
karşılığında künyede kredi ister; Typer bunu README'sinde veriyor. Typer
bir gün ticari bir ürüne dönerse fontun ticari lisansı alınmalıdır.

## Yapılmaz

- Eğmek, esnetmek, en-boy oranını değiştirmek. Yalnızca eşit ölçekleme.
- İşaretin ya da kelimenin rengini marka dışı bir renge çevirmek.
- Gölge, parlama, bevel, kontur eklemek.
- Açık zeminde asit yeşili metin.
- İşaretin içine başka bir şey koymak (mikrofon, dalga, nokta, çerçeve).
- İşaretin boşluğuna yazı ya da başka bir logo sokmak.

## Yeniden üretme

```bash
npm run brand          # SVG + PNG + ICO
npm run brand:guide    # PDF kılavuz
```

Ayrıntı için [`_generator/README.md`](_generator/README.md). Bir eğriyi
değiştirmek için `_generator/art.js` düzenlenir; başka hiçbir dosyaya
dokunulmaz.
