# Marka kiti jeneratörü

`visuals/` altındaki her şey buradan çıkar. Elle çizilmiş tek bir dosya yok:
işaretin ve kelimenin eğrileri `art.js` içinde yaşar, geri kalan her asset
onlardan türetilir. Bir eğriyi değiştirip `node build.js` demek, favicon'dan
sosyal karta kadar hepsini yeniden üretir — böylece assetler birbirinden
ayrı düşemez.

## Çalıştırma

```bash
node visuals/_generator/build.js          # SVG + PNG + ICO, hepsi
node visuals/_generator/build.js --svg    # yalnız SVG (hızlı deneme)
```

Marka kılavuzu (PDF) ayrı bir adım, çünkü üretilmiş assetlerin kendisini
sayfaya koyar:

```bash
./node_modules/.bin/electron visuals/_generator/guide.js
```

## Bağımlılık yok

Kit `sharp`, `resvg`, `opentype.js` ya da bir font dosyası istemez. Depoda
zaten kurulu olan tek şeyi kullanır: **Electron**. Chromium SVG'yi
tarayıcıların çizdiği gibi çizer, ki assetlerin gideceği yer de zaten orası.

| Dosya | İşi |
| --- | --- |
| `art.js` | İşaretin eğrileri, marka renkleri, kelimenin bağlanması. **Tek doğruluk kaynağı.** |
| `wordmark.js` | ÜRETİLMİŞ: "typer" kelimesinin vektör yolu. Elle düzenlenmez. |
| `mkwordmark.js` | Kelimeyi fonttan bir kez okuyup `wordmark.js`'i yazar. |
| `ttf.js` | Minik TrueType okuyucu (cmap/loca/glyf/hmtx). |
| `build.js` | Bütün klasör ağacını üretir; PNG işlerini toplayıp rasterleyiciye verir. |
| `raster.js` | SVG → PNG. Electron'un gizli, saydam bir penceresiyle. |
| `ico.js` | PNG gömülü `.ico` yazar (16 + 32 + 48). |
| `outline.js` | Çizgiyi dolguya çevirir — `portable/` sürümleri için. |
| `guide.js` | Basılabilir marka kılavuzunu (A4 PDF) üretir. |
| `diff.js` | İki PNG'yi piksel piksel karşılaştırır (regresyon kontrolü). |

## Rasterleyicinin iki tuzağı

Bu ikisi tekrar tekrar bulunmasın diye yazılı:

1. **`offscreen: true` kullanılmaz.** Ekran dışı pencerede `capturePage`
   sonsuza kadar bekliyor. Doğru bileşim: `show: false` + `transparent: true`.
2. **Pencere her iş için yeniden yaratılmaz.** Saydam bir pencereyi yok edip
   yenisini açmak Chromium'un ağ servisini düşürüyor ve sıradaki `data:`
   yüklemesi `ERR_FAILED` veriyordu — 16 px'lik favicon çıkıp 32 px'lik
   çıkmamasının sebebi buydu. Tek pencere açılır, her iş için yeniden
   boyutlandırılır.

## Çizgi neden dolguya çevriliyor

`stroke-width` SVG'nin çekirdeğinde, ama üçüncü tarafların bazı boru hatları
(kesim makineleri, eski içe aktarıcılar, bazı e-posta işleyicileri) çizgiyi
ya yok sayıyor ya kalınlığını bozuyor. Bir logonun kalınlığı başkasının
eline kalamaz, o yüzden `portable/` altında yalnız dolgudan oluşan bir sürüm
duruyor.

Dönüştürücü kavis ötelemesi yapmaz: eğri noktalara ayrılır, her parça bir
dörtgene, her ek yeri bir daireye çevrilir, hepsi aynı dönüş yönünde tek bir
`fill-rule="nonzero"` yolunda birleşir. Yuvarlak uç ve yuvarlak ek yeri
bedava gelir. Sonuç, çizgili sürümle piksel piksel karşılaştırıldı: fark
yalnızca siluetin bir piksellik kenar yumuşatmasında.

## Kelime fonttan gelir, ama font hiçbir yere gitmez

İşaret elle çizilmiştir. Kelime **Modern Sans Serif 7**'den okunur, ama
yalnızca BİR KEZ ve yalnızca burada:

```bash
node visuals/_generator/mkwordmark.js <font.ttf> --slant 12 --track -0.015
```

Bu komut `wordmark.js`'i yazar ve iş biter. Font dosyası ne depoda durur,
ne derlemede gerekir, ne de bir çıktının içinde taşınır — teslim edilen
hiçbir asset içinde `<text>`, `font-family` ya da gömülü font yoktur.
Sebebi ikili: bir logonun biçimi karşı tarafta hangi fontun kurulu
olduğuna bağlı olamaz, ve fontun lisansı onu bir kuruluma dahil etmeyi
ücretli kılıyor. (Marka kılavuzunun gövde metni bunun dışında — o bir
belge, asset değil.)

`ttf.js` neden var: fontu yola çevirmek için `opentype.js` kurmak
gerekirdi, o da kiti bir pakete bağlardı. Gereken kadarı — cmap biçim 4,
loca, glyf, hmtx — iki yüz satır. Doğruluğu gözle değil ölçüyle kanıtlandı:
çıkan yollar, Chromium'un aynı fontu aynı boyda dizdiği görüntüyle piksel
piksel karşılaştırıldı; fark yalnızca konturun bir piksellik kenar
yumuşatmasında kaldı (`diff.js`).

Eğim (12 derece) `skewX` ile DEĞİL, koordinatlara işlenerek verilir. Bir
dönüşüm olarak bırakılsaydı yol verisi dik kalır ve dosyayı açan herkes
eğimi ayrıca taşımak zorunda kalırdı.
