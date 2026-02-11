"""
Besin Veritabanı — Yaygın Türk besinlerinin makro değerleri (100g başına).
Kaynaklar:
- TürkOMP (turkomp.tarimorman.gov.tr) — Türk besinleri birincil kaynak
- USDA FoodData Central (fdc.nal.usda.gov) — Uluslararası besinler

Bu veritabanı programatik validasyonda kullanılır.
Tüm değerler 100g PİŞMİŞ/HAZIR hali içindir (aksi belirtilmedikçe).
"""

# Her besin: 100g pişmiş/hazır hali
# Yapı: {"kalori": kcal, "protein": g, "yag": g, "karb": g, "lif": g}

BESIN_DB = {
    # ==========================================
    # PROTEİN KAYNAKLARI (pişmiş, 100g)
    # ==========================================
    # USDA #05062: Chicken, breast, without skin, roasted
    "tavuk göğsü": {"kalori": 165, "protein": 31, "yag": 3.6, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #05096: Chicken, thigh, without skin, roasted
    "tavuk but": {"kalori": 209, "protein": 26, "yag": 10.9, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #05224: Turkey, breast, without skin, roasted
    "hindi göğsü": {"kalori": 135, "protein": 30, "yag": 1, "karb": 0, "lif": 0, "kategori": "protein"},
    "hindi bonfile": {"kalori": 135, "protein": 30, "yag": 1, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #23557: Beef, ground, 80% lean, cooked
    "dana kıyma": {"kalori": 254, "protein": 26, "yag": 16, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #23232: Beef, tenderloin, roasted
    "dana bonfile": {"kalori": 217, "protein": 28, "yag": 11, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #23573: Beef, eye of round, roasted (yağsız parça)
    "dana biftek": {"kalori": 175, "protein": 30, "yag": 5.5, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #17224: Lamb, leg, roasted, lean
    "kuzu eti": {"kalori": 220, "protein": 30, "yag": 10, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #15086: Salmon, Atlantic, farmed, cooked
    "somon": {"kalori": 208, "protein": 20, "yag": 13, "karb": 0, "lif": 0, "kategori": "protein"},
    # TürkOMP #85: Levrek, yetiştirme, pişmiş
    "levrek": {"kalori": 124, "protein": 24, "yag": 2.6, "karb": 0, "lif": 0, "kategori": "protein"},
    # TürkOMP: Çipura, pişmiş
    "çipura": {"kalori": 135, "protein": 23, "yag": 4.5, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #15121: Tuna, canned in water, drained
    "ton balığı": {"kalori": 116, "protein": 25.5, "yag": 1, "karb": 0, "lif": 0, "kategori": "protein"},
    "ton balığı konserve": {"kalori": 116, "protein": 25.5, "yag": 1, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #15001: Tuna, fresh, cooked
    "ton balığı taze": {"kalori": 184, "protein": 30, "yag": 6.3, "karb": 0, "lif": 0, "kategori": "protein"},
    # TürkOMP #81: Hamsi, çiğ
    "hamsi": {"kalori": 131, "protein": 20, "yag": 5, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #15151: Shrimp, cooked
    "karides": {"kalori": 99, "protein": 24, "yag": 0.3, "karb": 0.2, "lif": 0, "kategori": "protein"},
    # USDA #01129: Egg, whole, cooked (100g)
    "yumurta": {"kalori": 155, "protein": 13, "yag": 11, "karb": 1.1, "lif": 0, "kategori": "protein", "porsiyon_g": 60, "porsiyon_ad": "1 adet"},
    # USDA #16427: Tofu, firm
    "tofu": {"kalori": 76, "protein": 8, "yag": 4.8, "karb": 1.9, "lif": 0.3, "kategori": "protein"},

    # ==========================================
    # SÜT ÜRÜNLERİ (100g)
    # ==========================================
    # TürkOMP #563: Edirne Beyaz Peyniri (tam yağ ~%55-60)
    "beyaz peynir": {"kalori": 289, "protein": 18, "yag": 23, "karb": 1.5, "lif": 0, "kategori": "sut_urunu"},
    # TürkOMP: Yarım yağlı beyaz peynir
    "beyaz peynir yarım yağlı": {"kalori": 210, "protein": 19, "yag": 14, "karb": 1.5, "lif": 0, "kategori": "sut_urunu"},
    # USDA #01025: Kaşar benzeri — semi-hard cheese
    "kaşar peynir": {"kalori": 350, "protein": 25, "yag": 27, "karb": 2, "lif": 0, "kategori": "sut_urunu"},
    # TürkOMP: Lor peyniri — yarım yağlı
    "lor peyniri": {"kalori": 98, "protein": 11, "yag": 4, "karb": 3.4, "lif": 0, "kategori": "sut_urunu"},
    # USDA: Cottage cheese, low fat (lor benzeri)
    "lor peyniri yağsız": {"kalori": 72, "protein": 12, "yag": 1, "karb": 3, "lif": 0, "kategori": "sut_urunu"},
    # USDA #01256: Feta cheese
    "feta peyniri": {"kalori": 264, "protein": 14, "yag": 21, "karb": 4, "lif": 0, "kategori": "sut_urunu"},
    # TürkOMP: Çökelek
    "çökelek": {"kalori": 72, "protein": 11, "yag": 1.5, "karb": 4, "lif": 0, "kategori": "sut_urunu"},
    # TürkOMP: Tulum peyniri
    "tulum peyniri": {"kalori": 300, "protein": 20, "yag": 24, "karb": 1, "lif": 0, "kategori": "sut_urunu"},
    # USDA: Mozzarella, part skim
    "mozzarella": {"kalori": 280, "protein": 28, "yag": 17, "karb": 3.1, "lif": 0, "kategori": "sut_urunu"},
    # USDA #01287: Greek yogurt, plain, nonfat — %2 yağ versiyonu
    "yunan yoğurdu": {"kalori": 73, "protein": 10, "yag": 2, "karb": 4, "lif": 0, "kategori": "sut_urunu"},
    # TürkOMP: Süzme yoğurt (%10 yağlı)
    "süzme yoğurt": {"kalori": 90, "protein": 6, "yag": 5, "karb": 5, "lif": 0, "kategori": "sut_urunu"},
    # TürkOMP: Süzme yoğurt (%0 yağ)
    "süzme yoğurt yağsız": {"kalori": 57, "protein": 10, "yag": 0.2, "karb": 4, "lif": 0, "kategori": "sut_urunu"},
    # USDA #01077: Milk, whole
    "süt": {"kalori": 60, "protein": 3.2, "yag": 3.2, "karb": 4.8, "lif": 0, "kategori": "sut_urunu"},
    # TürkOMP: Ayran
    "ayran": {"kalori": 35, "protein": 1.7, "yag": 1.5, "karb": 3.5, "lif": 0, "kategori": "sut_urunu"},
    # USDA: Kefir, plain
    "kefir": {"kalori": 63, "protein": 3.3, "yag": 3.5, "karb": 4.0, "lif": 0, "kategori": "sut_urunu"},

    # ==========================================
    # KARBONHİDRAT KAYNAKLARI (pişmiş, 100g)
    # ==========================================
    # USDA #20045: Rice, white, cooked
    "pirinç pilavı": {"kalori": 130, "protein": 2.7, "yag": 0.3, "karb": 28, "lif": 0.4, "kategori": "karbonhidrat"},
    # USDA: Brown rice, cooked
    "esmer pirinç": {"kalori": 123, "protein": 2.7, "yag": 1.0, "karb": 26, "lif": 1.6, "kategori": "karbonhidrat"},
    # TürkOMP #460: Bulgur pilavlık, pişmiş
    "bulgur pilavı": {"kalori": 83, "protein": 3, "yag": 0.2, "karb": 18.6, "lif": 4.5, "kategori": "karbonhidrat"},
    # USDA #20120: Pasta, cooked
    "makarna": {"kalori": 131, "protein": 5, "yag": 1.1, "karb": 25, "lif": 1.8, "kategori": "karbonhidrat"},
    # USDA: Whole wheat pasta, cooked
    "tam buğday makarna": {"kalori": 124, "protein": 5.3, "yag": 0.5, "karb": 26.5, "lif": 3.9, "kategori": "karbonhidrat"},
    # USDA #18075: Bread, whole wheat
    "tam buğday ekmek": {"kalori": 260, "protein": 10, "yag": 4, "karb": 48, "lif": 7, "kategori": "karbonhidrat", "porsiyon_g": 25, "porsiyon_ad": "1 dilim"},
    # TürkOMP #126: Ekmek, beyaz
    "beyaz ekmek": {"kalori": 265, "protein": 9, "yag": 3.2, "karb": 49, "lif": 2.7, "kategori": "karbonhidrat", "porsiyon_g": 25, "porsiyon_ad": "1 dilim"},
    # USDA #08120: Oatmeal, cooked
    "yulaf ezmesi": {"kalori": 68, "protein": 2.4, "yag": 1.4, "karb": 12, "lif": 1.7, "kategori": "karbonhidrat"},
    # USDA: Oats, dry (çiğ yulaf — smoothie için)
    "yulaf ezmesi kuru": {"kalori": 389, "protein": 13.2, "yag": 6.5, "karb": 67, "lif": 10.1, "kategori": "karbonhidrat"},
    # USDA #20137: Quinoa, cooked
    "kinoa": {"kalori": 120, "protein": 4.4, "yag": 1.9, "karb": 21.3, "lif": 2.8, "kategori": "karbonhidrat"},
    # USDA #11367: Potato, boiled
    "patates": {"kalori": 87, "protein": 1.9, "yag": 0.1, "karb": 20.1, "lif": 1.8, "kategori": "karbonhidrat"},
    # USDA #11508: Sweet potato, baked
    "tatlı patates": {"kalori": 90, "protein": 2.0, "yag": 0.1, "karb": 21, "lif": 3.3, "kategori": "karbonhidrat"},
    # TürkOMP: Kısır (bulgur salatası)
    "kısır": {"kalori": 135, "protein": 3, "yag": 4, "karb": 23, "lif": 5, "kategori": "karbonhidrat"},
    # USDA #16057: Chickpeas, cooked
    "nohut": {"kalori": 164, "protein": 8.9, "yag": 2.6, "karb": 27, "lif": 7.6, "kategori": "baklagil"},
    # USDA #16029: Kidney beans, cooked
    "kuru fasulye": {"kalori": 127, "protein": 8.7, "yag": 0.5, "karb": 22, "lif": 6.4, "kategori": "baklagil"},
    # USDA #16069: Lentils, cooked
    "mercimek": {"kalori": 116, "protein": 9, "yag": 0.4, "karb": 20, "lif": 7.9, "kategori": "baklagil"},
    # TürkOMP: Kırmızı mercimek çorbası
    "kırmızı mercimek çorbası": {"kalori": 56, "protein": 3.5, "yag": 1.5, "karb": 8, "lif": 2, "kategori": "baklagil"},
    # USDA: Granola, plain
    "granola": {"kalori": 450, "protein": 10, "yag": 20, "karb": 60, "lif": 5, "kategori": "karbonhidrat"},
    # USDA: Couscous, cooked
    "kuskus": {"kalori": 112, "protein": 3.8, "yag": 0.2, "karb": 23, "lif": 1.4, "kategori": "karbonhidrat"},

    # ==========================================
    # EKMEK ÇEŞİTLERİ (100g)
    # ==========================================
    # USDA: Flatbread/Lavash
    "lavaş ekmeği": {"kalori": 275, "protein": 9.1, "yag": 1.2, "karb": 56, "lif": 2.2, "kategori": "karbonhidrat", "porsiyon_g": 60, "porsiyon_ad": "1 adet"},
    # USDA: Whole wheat flatbread
    "tam buğday lavaş": {"kalori": 262, "protein": 10, "yag": 2.5, "karb": 50, "lif": 6.8, "kategori": "karbonhidrat", "porsiyon_g": 60, "porsiyon_ad": "1 adet"},
    # USDA #18364: Tortilla, flour
    "tortilla": {"kalori": 312, "protein": 8.3, "yag": 8.1, "karb": 52, "lif": 3.1, "kategori": "karbonhidrat", "porsiyon_g": 45, "porsiyon_ad": "1 adet"},
    # USDA: Pita bread, whole wheat
    "pide ekmeği": {"kalori": 266, "protein": 9.8, "yag": 1.7, "karb": 55, "lif": 6.1, "kategori": "karbonhidrat", "porsiyon_g": 60, "porsiyon_ad": "1 adet"},
    # USDA: Rice cake
    "pirinç patlağı": {"kalori": 387, "protein": 8, "yag": 2.8, "karb": 82, "lif": 1.2, "kategori": "karbonhidrat", "porsiyon_g": 9, "porsiyon_ad": "1 adet"},
    # USDA: All-purpose flour
    "un": {"kalori": 364, "protein": 10, "yag": 1, "karb": 76, "lif": 2.7, "kategori": "karbonhidrat"},
    # USDA: Pancake, plain
    "pankek": {"kalori": 227, "protein": 6.4, "yag": 10, "karb": 28, "lif": 1, "kategori": "karbonhidrat"},

    # ==========================================
    # SEBZELER (çiğ/pişmiş, 100g)
    # ==========================================
    # USDA #11091: Broccoli, cooked
    "brokoli": {"kalori": 35, "protein": 2.4, "yag": 0.4, "karb": 7.2, "lif": 3.3, "kategori": "sebze"},
    # USDA #11457: Spinach, raw
    "ıspanak": {"kalori": 23, "protein": 2.9, "yag": 0.4, "karb": 3.6, "lif": 2.2, "kategori": "sebze"},
    # USDA #11458: Spinach, cooked
    "ıspanak pişmiş": {"kalori": 23, "protein": 3.0, "yag": 0.3, "karb": 3.8, "lif": 2.4, "kategori": "sebze"},
    # USDA #11529: Tomato, raw
    "domates": {"kalori": 18, "protein": 0.9, "yag": 0.2, "karb": 3.9, "lif": 1.2, "kategori": "sebze"},
    # USDA #11205: Cucumber, raw
    "salatalık": {"kalori": 15, "protein": 0.7, "yag": 0.1, "karb": 3.6, "lif": 0.5, "kategori": "sebze"},
    # USDA #11333: Bell pepper, green, raw
    "biber": {"kalori": 31, "protein": 1, "yag": 0.3, "karb": 6, "lif": 2.1, "kategori": "sebze"},
    # USDA #11821: Red bell pepper, raw
    "kırmızı biber": {"kalori": 31, "protein": 1, "yag": 0.3, "karb": 6, "lif": 2.1, "kategori": "sebze"},
    # USDA #11282: Onion, raw
    "soğan": {"kalori": 40, "protein": 1.1, "yag": 0.1, "karb": 9.3, "lif": 1.7, "kategori": "sebze"},
    # USDA #11124: Carrot, raw
    "havuç": {"kalori": 41, "protein": 0.9, "yag": 0.2, "karb": 9.6, "lif": 2.8, "kategori": "sebze"},
    # USDA #11477: Zucchini, raw
    "kabak": {"kalori": 17, "protein": 1.2, "yag": 0.3, "karb": 3.1, "lif": 1, "kategori": "sebze"},
    # USDA #11209: Eggplant, cooked
    "patlıcan": {"kalori": 25, "protein": 1, "yag": 0.2, "karb": 6, "lif": 3, "kategori": "sebze"},
    # USDA #11135: Cauliflower, raw
    "karnabahar": {"kalori": 25, "protein": 1.9, "yag": 0.3, "karb": 5, "lif": 2, "kategori": "sebze"},
    # USDA: Lettuce, green leaf
    "yeşil salata": {"kalori": 15, "protein": 1.4, "yag": 0.2, "karb": 2.9, "lif": 1.3, "kategori": "sebze"},
    # USDA #09037: Avocado, raw
    "avokado": {"kalori": 160, "protein": 2, "yag": 15, "karb": 8.5, "lif": 6.7, "kategori": "sebze"},
    # USDA #11167: Corn, sweet, cooked
    "mısır": {"kalori": 96, "protein": 3.4, "yag": 1.5, "karb": 21, "lif": 2.4, "kategori": "sebze"},
    # USDA #11052: Green beans, cooked
    "yeşil fasulye": {"kalori": 35, "protein": 1.9, "yag": 0.3, "karb": 7.1, "lif": 3.2, "kategori": "sebze"},
    # USDA: Cabbage, raw
    "lahana": {"kalori": 25, "protein": 1.3, "yag": 0.1, "karb": 5.8, "lif": 2.5, "kategori": "sebze"},
    # USDA #11260: Mushroom, white, raw
    "mantar": {"kalori": 22, "protein": 3.1, "yag": 0.3, "karb": 3.3, "lif": 1, "kategori": "sebze"},
    # USDA: Celery, raw
    "kereviz": {"kalori": 16, "protein": 0.7, "yag": 0.2, "karb": 3, "lif": 1.6, "kategori": "sebze"},
    # USDA: Artichoke, cooked
    "enginar": {"kalori": 47, "protein": 3.3, "yag": 0.2, "karb": 10.5, "lif": 5.4, "kategori": "sebze"},
    # USDA: Leek, raw
    "pırasa": {"kalori": 61, "protein": 1.5, "yag": 0.3, "karb": 14, "lif": 1.8, "kategori": "sebze"},

    # ==========================================
    # MEYVELER (çiğ, 100g)
    # ==========================================
    # USDA #09003: Apple, raw
    "elma": {"kalori": 52, "protein": 0.3, "yag": 0.2, "karb": 14, "lif": 2.4, "kategori": "meyve"},
    # USDA #09040: Banana, raw
    "muz": {"kalori": 89, "protein": 1.1, "yag": 0.3, "karb": 23, "lif": 2.6, "kategori": "meyve"},
    # USDA #09200: Orange, raw
    "portakal": {"kalori": 47, "protein": 0.9, "yag": 0.1, "karb": 12, "lif": 2.4, "kategori": "meyve"},
    # USDA #09316: Strawberry, raw
    "çilek": {"kalori": 32, "protein": 0.7, "yag": 0.3, "karb": 7.7, "lif": 2, "kategori": "meyve"},
    # USDA #09302: Raspberry, raw
    "ahududu": {"kalori": 52, "protein": 1.2, "yag": 0.7, "karb": 12, "lif": 6.5, "kategori": "meyve"},
    # USDA #09050: Blueberry, raw
    "yaban mersini": {"kalori": 57, "protein": 0.7, "yag": 0.3, "karb": 14.5, "lif": 2.4, "kategori": "meyve"},
    # USDA #09148: Kiwi, raw
    "kivi": {"kalori": 61, "protein": 1.1, "yag": 0.5, "karb": 15, "lif": 3, "kategori": "meyve"},
    # USDA #09132: Grape, raw
    "üzüm": {"kalori": 69, "protein": 0.7, "yag": 0.2, "karb": 18, "lif": 0.9, "kategori": "meyve"},
    # USDA #09094: Fig, raw
    "incir": {"kalori": 74, "protein": 0.8, "yag": 0.3, "karb": 19, "lif": 2.9, "kategori": "meyve"},
    # USDA #09252: Pear, raw
    "armut": {"kalori": 57, "protein": 0.4, "yag": 0.1, "karb": 15, "lif": 3.1, "kategori": "meyve"},
    # USDA #09236: Peach, raw
    "şeftali": {"kalori": 39, "protein": 0.9, "yag": 0.3, "karb": 10, "lif": 1.5, "kategori": "meyve"},
    # USDA #09326: Watermelon, raw
    "karpuz": {"kalori": 30, "protein": 0.6, "yag": 0.2, "karb": 7.6, "lif": 0.4, "kategori": "meyve"},
    # USDA #09070: Cherry, sweet, raw
    "kiraz": {"kalori": 63, "protein": 1.1, "yag": 0.2, "karb": 16, "lif": 2.1, "kategori": "meyve"},
    # USDA #09266: Pineapple, raw
    "ananas": {"kalori": 50, "protein": 0.5, "yag": 0.1, "karb": 13, "lif": 1.4, "kategori": "meyve"},
    # USDA #09176: Mango, raw
    "mango": {"kalori": 60, "protein": 0.8, "yag": 0.4, "karb": 15, "lif": 1.6, "kategori": "meyve"},
    # USDA #09286: Pomegranate, raw
    "nar": {"kalori": 83, "protein": 1.7, "yag": 1.2, "karb": 19, "lif": 4, "kategori": "meyve"},
    # USDA: Melon, cantaloupe
    "kavun": {"kalori": 34, "protein": 0.8, "yag": 0.2, "karb": 8.2, "lif": 0.9, "kategori": "meyve"},

    # ==========================================
    # KURU MEYVELER (100g)
    # ==========================================
    # USDA #09032: Dried apricot
    "kuru kayısı": {"kalori": 241, "protein": 3.4, "yag": 0.5, "karb": 63, "lif": 7.3, "kategori": "kuru_meyve"},
    # USDA #09094: Dried fig
    "kuru incir": {"kalori": 249, "protein": 3.3, "yag": 0.9, "karb": 64, "lif": 9.8, "kategori": "kuru_meyve"},
    # USDA #09421: Dates, deglet noor
    "hurma": {"kalori": 277, "protein": 1.8, "yag": 0.2, "karb": 75, "lif": 7, "kategori": "kuru_meyve"},
    # USDA #09299: Raisins
    "kuru üzüm": {"kalori": 299, "protein": 3.1, "yag": 0.5, "karb": 79, "lif": 3.7, "kategori": "kuru_meyve"},

    # ==========================================
    # YAĞLAR VE KURUYEMİŞLER (100g)
    # ==========================================
    # USDA #04053: Olive oil
    "zeytinyağı": {"kalori": 884, "protein": 0, "yag": 100, "karb": 0, "lif": 0, "kategori": "yag", "porsiyon_g": 14, "porsiyon_ad": "1 yemek kaşığı"},
    # USDA #01001: Butter, salted
    "tereyağı": {"kalori": 717, "protein": 0.9, "yag": 81, "karb": 0.1, "lif": 0, "kategori": "yag", "porsiyon_g": 10, "porsiyon_ad": "1 tatlı kaşığı"},
    # USDA: Coconut oil
    "hindistan cevizi yağı": {"kalori": 862, "protein": 0, "yag": 100, "karb": 0, "lif": 0, "kategori": "yag", "porsiyon_g": 14, "porsiyon_ad": "1 yemek kaşığı"},
    # USDA #12061: Almonds
    "badem": {"kalori": 579, "protein": 21, "yag": 50, "karb": 22, "lif": 12.5, "kategori": "kuruyemis"},
    # USDA #12155: Walnuts
    "ceviz": {"kalori": 654, "protein": 15, "yag": 65, "karb": 14, "lif": 6.7, "kategori": "kuruyemis"},
    # USDA #12120: Hazelnuts
    "fındık": {"kalori": 628, "protein": 15, "yag": 61, "karb": 17, "lif": 9.7, "kategori": "kuruyemis"},
    # USDA #16090: Peanuts, roasted
    "yer fıstığı": {"kalori": 567, "protein": 26, "yag": 49, "karb": 16, "lif": 8.5, "kategori": "kuruyemis"},
    # USDA #16098: Peanut butter
    "fıstık ezmesi": {"kalori": 588, "protein": 25, "yag": 50, "karb": 20, "lif": 6, "kategori": "kuruyemis"},
    # USDA #12087: Cashews
    "kaju": {"kalori": 553, "protein": 18, "yag": 44, "karb": 30, "lif": 3.3, "kategori": "kuruyemis"},
    # USDA #12151: Pistachios
    "antep fıstığı": {"kalori": 560, "protein": 20, "yag": 45, "karb": 28, "lif": 10, "kategori": "kuruyemis"},
    # USDA #12036: Sunflower seeds
    "ay çekirdeği": {"kalori": 584, "protein": 21, "yag": 51, "karb": 20, "lif": 8.6, "kategori": "kuruyemis"},
    # USDA #12220: Pumpkin seeds
    "kabak çekirdeği": {"kalori": 559, "protein": 30, "yag": 49, "karb": 11, "lif": 6, "kategori": "kuruyemis"},
    # USDA #12006: Chia seeds
    "chia tohumu": {"kalori": 486, "protein": 17, "yag": 31, "karb": 42, "lif": 34, "kategori": "kuruyemis"},
    # USDA #12220: Flaxseed
    "keten tohumu": {"kalori": 534, "protein": 18, "yag": 42, "karb": 29, "lif": 27, "kategori": "kuruyemis"},

    # ==========================================
    # ET İŞLENMİŞ (pişmiş, 100g)
    # ==========================================
    "tavuk döner": {"kalori": 175, "protein": 28, "yag": 6, "karb": 2, "lif": 0, "kategori": "protein"},
    # TürkOMP: Köfte (ızgara, dana)
    "köfte": {"kalori": 235, "protein": 22, "yag": 15, "karb": 3, "lif": 0.5, "kategori": "protein"},
    # TürkOMP: Sucuk
    "sucuk": {"kalori": 452, "protein": 19, "yag": 40, "karb": 4, "lif": 0, "kategori": "protein"},
    # TürkOMP: Pastırma
    "pastırma": {"kalori": 174, "protein": 33, "yag": 4, "karb": 1, "lif": 0, "kategori": "protein"},

    # ==========================================
    # DİĞER (100g)
    # ==========================================
    # USDA #19296: Honey
    "bal": {"kalori": 304, "protein": 0.3, "yag": 0, "karb": 82, "lif": 0.2, "kategori": "tatlandirici", "porsiyon_g": 21, "porsiyon_ad": "1 yemek kaşığı"},
    # TürkOMP #638: Tahin, Konya
    "tahin": {"kalori": 595, "protein": 17, "yag": 54, "karb": 21, "lif": 9.3, "kategori": "diger"},
    # USDA #16158: Hummus
    "humus": {"kalori": 166, "protein": 7.9, "yag": 9.6, "karb": 14.3, "lif": 6, "kategori": "diger"},
    # USDA #09195: Olives
    "zeytin": {"kalori": 115, "protein": 0.8, "yag": 11, "karb": 6, "lif": 3.2, "kategori": "diger"},
    # USDA: Rice paper
    "pirinç kağıdı": {"kalori": 319, "protein": 0.8, "yag": 0.1, "karb": 80, "lif": 0, "kategori": "diger", "porsiyon_g": 10, "porsiyon_ad": "1 adet"},
    # USDA: Whey protein powder (generic)
    "protein tozu": {"kalori": 400, "protein": 80, "yag": 5, "karb": 10, "lif": 0, "kategori": "supplement", "porsiyon_g": 30, "porsiyon_ad": "1 ölçek"},
    # USDA #19904: Dark chocolate (70-85% cacao)
    "bitter çikolata": {"kalori": 598, "protein": 7.8, "yag": 43, "karb": 46, "lif": 11, "kategori": "diger"},
    # USDA: Pekmez (grape molasses, similar to molasses)
    "pekmez": {"kalori": 293, "protein": 0.1, "yag": 0, "karb": 77, "lif": 0, "kategori": "tatlandirici", "porsiyon_g": 20, "porsiyon_ad": "1 yemek kaşığı"},
}

# Karbonhidrat kategorisindeki besinler — aynı öğünde 2+ olmamalı
STARCHY_FOODS = {
    "pirinç pilavı", "esmer pirinç", "bulgur pilavı", "makarna",
    "tam buğday makarna", "patates", "tatlı patates", "kısır", "kinoa",
    "nohut", "kuru fasulye", "mercimek", "kuskus",
}

# Protein kaynakları — tekrar kontrolü için
PROTEIN_SOURCES = {
    "tavuk göğsü": "tavuk",
    "tavuk but": "tavuk",
    "tavuk döner": "tavuk",
    "hindi göğsü": "hindi",
    "hindi bonfile": "hindi",
    "dana kıyma": "kırmızı et",
    "dana bonfile": "kırmızı et",
    "dana biftek": "kırmızı et",
    "kuzu eti": "kırmızı et",
    "köfte": "kırmızı et",
    "sucuk": "kırmızı et",
    "pastırma": "kırmızı et",
    "somon": "balık",
    "levrek": "balık",
    "çipura": "balık",
    "ton balığı": "balık",
    "ton balığı konserve": "balık",
    "ton balığı taze": "balık",
    "hamsi": "balık",
    "karides": "deniz ürünü",
    "yumurta": "yumurta",
    "tofu": "tofu",
    "nohut": "baklagil",
    "kuru fasulye": "baklagil",
    "mercimek": "baklagil",
}
