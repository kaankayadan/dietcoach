# Yemek Veritabanı & Scraper Sistemi - Uygulama Planı

## Genel Mimari

```
Scraper Pipeline:
  [Recipe Sites] → Scraper → [Raw Recipes] → Ingredient Parser → [Ingredients]
                                                     ↓
                                            [TurKomp/USDA API]
                                                     ↓
                                            [Nutrition Data]
                                                     ↓
                                         [PostgreSQL Food DB]
```

---

## Faz 1: Veritabanı Şeması (Yeni tablolar)

### Yeni Tablolar:

1. **besinler** - Temel besin veritabanı (malzemeler)
   - id, isim, kategori (sebze/meyve/et/baklagil/tahil/süt_ürünü/yağ/baharat...)
   - porsiyon_birimi (g/ml/adet/dilim...), porsiyon_miktari
   - kalori, protein, karbonhidrat, yag, lif (100g başına)
   - kaynak (turkomp/usda/manual), kaynak_id
   - created_at, updated_at

2. **tarifler** - Scrape edilen tarifler
   - id, isim, slug, kaynak_site, kaynak_url
   - kategori (kahvalti/ana_yemek/ara_ogun/tatli/salata/corba/icecek...)
   - porsiyon_sayisi, hazirlik_suresi_dk, pisirme_suresi_dk
   - toplam_kalori, toplam_protein, toplam_karbonhidrat, toplam_yag, toplam_lif (porsiyon başına)
   - diyet_uygunluk JSONB (glutensiz, laktozsuz, vegan, vejetaryen, dusuk_karbonhidrat...)
   - mevsim TEXT[] (ilkbahar, yaz, sonbahar, kis)
   - zorluk (kolay/orta/zor)
   - resim_url, aciklama
   - onay_durumu (bekliyor/onaylandi/reddedildi)
   - created_at

3. **tarif_malzemeleri** - Tarif ↔ Besin ilişkisi
   - id, tarif_id (FK), besin_id (FK)
   - miktar, birim (g/ml/adet/yemek_kasigi/cay_kasigi/bardak...)
   - miktar_gram (normalize edilmiş gram cinsinden)
   - kalori, protein, karbonhidrat, yag, lif (bu miktar için hesaplanmış)

4. **besin_alternatifleri** - Besin ikame tablosu
   - id, besin_id, alternatif_besin_id, oran (ör: 100g tavuk = 120g hindi)

---

## Faz 2: Besin Veritabanı Altyapısı

### TurKomp Entegrasyonu
- TurKomp (Türk Gıda Kompozisyon Veritabanı) web sitesinden veri çekme
- http://www.turkomp.gov.tr/ sitesinden besin değerlerini scrape etme
- ~2000+ Türk gıdası için makro ve mikro besin değerleri

### USDA FoodData Central API (Fallback)
- API Key ile erişim: https://fdc.nal.usda.gov/api-guide
- TurKomp'ta bulunamayan besinler için USDA kullanılacak
- Ücretsiz API, günlük 1000 istek limiti

### Birim Dönüşüm Sistemi
- Türk mutfağına özel birim tablosu:
  - 1 yemek kaşığı = 15ml (sıvılar), ~10-15g (katılar, besin tipine göre değişir)
  - 1 çay kaşığı = 5ml
  - 1 su bardağı = 200ml
  - 1 çay bardağı = 100ml
  - 1 kahve fincanı = 65ml
  - 1 avuç = ~30g (kuruyemiş), ~15g (yeşillik)
  - adet bazlı: 1 yumurta = ~60g, 1 domates (orta) = ~150g vb.

---

## Faz 3: Scraper Sistemi

### Hedef Siteler:

1. **Nefis Yemek Tarifleri** (nefisyemektarifleri.com)
   - Türkiye'nin en büyük tarif sitesi
   - Yapılandırılmış tarif verileri (schema.org/Recipe)
   - Kategoriler: çorbalar, ana yemekler, salatalar, tatlılar vb.

2. **Yemek.com**
   - Profesyonel tarifler
   - İyi yapılandırılmış veri

3. **Lezzet.com.tr**
   - Hürriyet'in yemek platformu
   - Diyetisyen onaylı tarifler bölümü

4. **Instagram** (Alternatif yaklaşım)
   - Instagram API çok kısıtlı, doğrudan scraping TOS'a aykırı
   - **Alternatif:** Popüler diyetisyen influencer'ların blog/web sitelerini scrape etme
   - Dilara Koçak, Ayşe Tuğba Şengel gibi diyetisyenlerin kendi sitelerindeki tarifler
   - Manuel olarak Instagram post'larından tarif girişi için admin panel

### Scraper Mimarisi:

```python
scraper/
├── __init__.py
├── base_scraper.py        # Abstract base class
├── nefis_yemek.py         # nefisyemektarifleri.com scraper
├── yemek_com.py           # yemek.com scraper
├── lezzet.py              # lezzet.com.tr scraper
├── nutrition/
│   ├── __init__.py
│   ├── turkomp.py         # TurKomp veri çekici
│   ├── usda.py            # USDA API client
│   └── matcher.py         # Besin adı → veritabanı eşleştirici
├── parser/
│   ├── __init__.py
│   └── ingredient_parser.py  # Malzeme satırını parse etme (miktar + birim + besin)
├── utils/
│   ├── __init__.py
│   └── unit_converter.py  # Birim dönüşüm sistemi
└── runner.py              # Ana çalıştırıcı / orchestrator
```

### Teknolojiler:
- **httpx** - Async HTTP client (requests yerine, async uyumlu)
- **beautifulsoup4** - HTML parsing
- **lxml** - Hızlı XML/HTML parser
- **Anthropic Claude API** - Malzeme parsing & eşleştirme (mevcut API key kullanılacak)

### Scraping Stratejisi:
1. Her site için rate limiting (2-3 saniye arası bekleme)
2. User-Agent rotation
3. robots.txt'ye saygı
4. Sayfa bazlı ilerleme kaydı (kaldığı yerden devam)
5. Hata durumunda retry (3 deneme)

---

## Faz 4: Malzeme Parsing Pipeline

### Adım 1: Ham Tarif Scrape
```
"1 su bardağı bulgur, 2 adet soğan, 3 yemek kaşığı zeytinyağı, tuz, karabiber"
```

### Adım 2: Malzeme Satırlarına Bölme
```
["1 su bardağı bulgur", "2 adet soğan", "3 yemek kaşığı zeytinyağı", "tuz", "karabiber"]
```

### Adım 3: Her Satırı Parse Etme (Claude AI ile)
```json
{"miktar": 1, "birim": "su_bardagi", "besin": "bulgur"}
{"miktar": 2, "birim": "adet", "besin": "soğan"}
{"miktar": 3, "birim": "yemek_kasigi", "besin": "zeytinyağı"}
{"miktar": null, "birim": null, "besin": "tuz"}  // göz ardı edilebilir miktarlar
```

### Adım 4: Birim → Gram Dönüşümü
```
1 su bardağı bulgur = 170g
2 adet soğan = 300g (150g/adet)
3 yemek kaşığı zeytinyağı = 39g (13g/kaşık)
```

### Adım 5: TurKomp/USDA Eşleştirme
```
bulgur → TurKomp ID: 1234 → 100g: 342kcal, 12.3g protein, ...
soğan → TurKomp ID: 567 → 100g: 40kcal, 1.1g protein, ...
```

### Adım 6: Porsiyon Başına Hesaplama
```
Toplam makrolar / porsiyon sayısı = porsiyon başına makrolar
```

---

## Faz 5: Uygulama Adımları (Sıralı)

### Adım 1: Veritabanı şeması oluşturma
- schema.sql'e yeni tabloları ekleme
- Migration script

### Adım 2: TurKomp besin veritabanını oluşturma
- turkomp.gov.tr'den temel besinleri scrape etme
- ~500 temel Türk gıdası için makro değerler
- besinler tablosuna kaydetme

### Adım 3: USDA API client
- FoodData Central API entegrasyonu
- Fallback mekanizması

### Adım 4: Birim dönüşüm sistemi
- Türk mutfağına özel birimler
- Besin bazlı gram dönüşümleri

### Adım 5: Malzeme parser
- Claude API ile akıllı parsing
- Regex tabanlı basit parsing (API maliyetini düşürmek için)

### Adım 6: Site scraper'ları
- nefisyemektarifleri.com scraper
- yemek.com scraper
- lezzet.com.tr scraper

### Adım 7: Runner / Orchestrator
- Tüm pipeline'ı birleştiren ana script
- İlerleme takibi, hata yönetimi
- CLI arayüzü (hangi siteyi scrape et, kaç tarif, vb.)

### Adım 8: Docker entegrasyonu
- docker-compose.yml'e scraper service ekleme
- Scraper'ı periyodik çalıştırma (cron/scheduler)

---

## Teknik Notlar

- **Rate Limiting:** Her site için farklı rate limit (robots.txt'ye uygun)
- **Veri Kalitesi:** onay_durumu alanı ile admin onayı mekanizması
- **Duplikasyon:** kaynak_url unique constraint ile tekrar scrape önleme
- **Claude API Maliyeti:** Malzeme parsing için Haiku kullanılacak (düşük maliyet)
- **Scraper ayrı service:** Ana bot'tan bağımsız çalışacak, sadece DB paylaşımı
