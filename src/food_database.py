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
    # PROTEİN KAYNAKLARI — KÜMES (pişmiş, 100g)
    # ==========================================
    # USDA #05062: Chicken, breast, without skin, roasted
    "tavuk göğsü": {"kalori": 165, "protein": 31, "yag": 3.6, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #05096: Chicken, thigh, without skin, roasted
    "tavuk but": {"kalori": 209, "protein": 26, "yag": 10.9, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA: Chicken, drumstick, roasted
    "tavuk baget": {"kalori": 172, "protein": 28, "yag": 5.7, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #05224: Turkey, breast, without skin, roasted
    "hindi göğsü": {"kalori": 135, "protein": 30, "yag": 1, "karb": 0, "lif": 0, "kategori": "protein"},
    "hindi bonfile": {"kalori": 135, "protein": 30, "yag": 1, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA: Turkey, thigh, roasted
    "hindi but": {"kalori": 170, "protein": 28, "yag": 6, "karb": 0, "lif": 0, "kategori": "protein"},
    # ==========================================
    # PROTEİN KAYNAKLARI — KIRMIZI ET (pişmiş, 100g)
    # ==========================================
    # USDA #23557: Beef, ground, 80% lean, cooked
    "dana kıyma": {"kalori": 254, "protein": 26, "yag": 16, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #23232: Beef, tenderloin, roasted
    "dana bonfile": {"kalori": 217, "protein": 28, "yag": 11, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #23573: Beef, eye of round, roasted (yağsız parça)
    "dana biftek": {"kalori": 175, "protein": 30, "yag": 5.5, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA: Beef, chuck, lean, braised
    "dana kuşbaşı": {"kalori": 195, "protein": 29, "yag": 8, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #17224: Lamb, leg, roasted, lean
    "kuzu eti": {"kalori": 220, "protein": 30, "yag": 10, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA: Lamb, loin chop, lean, cooked
    "kuzu pirzola": {"kalori": 240, "protein": 28, "yag": 14, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA: Beef liver, cooked
    "ciğer": {"kalori": 175, "protein": 26, "yag": 5, "karb": 4, "lif": 0, "kategori": "protein"},
    # ==========================================
    # PROTEİN KAYNAKLARI — BALIK & DENİZ ÜRÜNLERİ (pişmiş, 100g)
    # ==========================================
    # USDA #15086: Salmon, Atlantic, farmed, cooked
    "somon": {"kalori": 208, "protein": 20, "yag": 13, "karb": 0, "lif": 0, "kategori": "protein"},
    # TürkOMP #85: Levrek, yetiştirme, pişmiş
    "levrek": {"kalori": 124, "protein": 24, "yag": 2.6, "karb": 0, "lif": 0, "kategori": "protein"},
    # TürkOMP: Çipura, pişmiş
    "çipura": {"kalori": 135, "protein": 23, "yag": 4.5, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA: Rainbow trout, cooked
    "alabalık": {"kalori": 119, "protein": 20.5, "yag": 3.5, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA: Whiting, cooked
    "mezgit": {"kalori": 90, "protein": 19, "yag": 1.3, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA: Sardine, canned in oil, drained
    "sardalya": {"kalori": 208, "protein": 25, "yag": 11, "karb": 0, "lif": 0, "kategori": "protein"},
    # TürkOMP: Palamut, pişmiş
    "palamut": {"kalori": 158, "protein": 26, "yag": 5.3, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA: Bluefish, cooked
    "lüfer": {"kalori": 159, "protein": 26, "yag": 5.4, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA: Jack mackerel, cooked
    "istavrit": {"kalori": 134, "protein": 24, "yag": 3.5, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #15121: Tuna, canned in water, drained
    "ton balığı": {"kalori": 116, "protein": 25.5, "yag": 1, "karb": 0, "lif": 0, "kategori": "protein"},
    "ton balığı konserve": {"kalori": 116, "protein": 25.5, "yag": 1, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #15001: Tuna, fresh, cooked
    "ton balığı taze": {"kalori": 184, "protein": 30, "yag": 6.3, "karb": 0, "lif": 0, "kategori": "protein"},
    # TürkOMP #81: Hamsi, çiğ
    "hamsi": {"kalori": 131, "protein": 20, "yag": 5, "karb": 0, "lif": 0, "kategori": "protein"},
    # USDA #15151: Shrimp, cooked
    "karides": {"kalori": 99, "protein": 24, "yag": 0.3, "karb": 0.2, "lif": 0, "kategori": "protein"},
    # USDA: Mussel, cooked
    "midye": {"kalori": 172, "protein": 24, "yag": 4.5, "karb": 7.4, "lif": 0, "kategori": "protein"},
    # USDA: Squid, cooked
    "kalamar": {"kalori": 175, "protein": 18, "yag": 7.5, "karb": 7.8, "lif": 0, "kategori": "protein"},
    # ==========================================
    # PROTEİN KAYNAKLARI — DİĞER (100g)
    # ==========================================
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
    # TürkOMP: Taze kaşar peyniri
    "taze kaşar": {"kalori": 313, "protein": 23, "yag": 24, "karb": 1.5, "lif": 0, "kategori": "sut_urunu"},
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
    # USDA: Halloumi cheese
    "hellim": {"kalori": 321, "protein": 25, "yag": 25, "karb": 1.7, "lif": 0, "kategori": "sut_urunu"},
    # TürkOMP: Van otlu peyniri
    "otlu peynir": {"kalori": 280, "protein": 18, "yag": 22, "karb": 2, "lif": 0, "kategori": "sut_urunu"},
    # USDA: Goat cheese, semi-soft
    "keçi peyniri": {"kalori": 364, "protein": 22, "yag": 30, "karb": 1, "lif": 0, "kategori": "sut_urunu"},
    # TürkOMP: Yoğurt, tam yağlı
    "yoğurt": {"kalori": 63, "protein": 3.5, "yag": 3.3, "karb": 4.7, "lif": 0, "kategori": "sut_urunu"},
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
    # TürkOMP: Kepekli ekmek
    "kepekli ekmek": {"kalori": 248, "protein": 10, "yag": 3.4, "karb": 44, "lif": 6, "kategori": "karbonhidrat", "porsiyon_g": 25, "porsiyon_ad": "1 dilim"},
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
    # USDA: Couscous, cooked
    "kuskus": {"kalori": 112, "protein": 3.8, "yag": 0.2, "karb": 23, "lif": 1.4, "kategori": "karbonhidrat"},
    # USDA: Vermicelli, cooked
    "şehriye": {"kalori": 138, "protein": 4.5, "yag": 0.7, "karb": 28, "lif": 1, "kategori": "karbonhidrat"},
    # USDA: Orzo, cooked
    "arpa şehriye": {"kalori": 125, "protein": 4, "yag": 0.5, "karb": 26, "lif": 1.2, "kategori": "karbonhidrat"},
    # USDA: Granola, plain
    "granola": {"kalori": 450, "protein": 10, "yag": 20, "karb": 60, "lif": 5, "kategori": "karbonhidrat"},
    # ==========================================
    # BAKLAGİLLER (pişmiş, 100g)
    # ==========================================
    # USDA #16057: Chickpeas, cooked
    "nohut": {"kalori": 164, "protein": 8.9, "yag": 2.6, "karb": 27, "lif": 7.6, "kategori": "baklagil"},
    # USDA #16029: Kidney beans, cooked
    "kuru fasulye": {"kalori": 127, "protein": 8.7, "yag": 0.5, "karb": 22, "lif": 6.4, "kategori": "baklagil"},
    # USDA #16069: Lentils, cooked
    "mercimek": {"kalori": 116, "protein": 9, "yag": 0.4, "karb": 20, "lif": 7.9, "kategori": "baklagil"},
    # TürkOMP: Kırmızı mercimek çorbası
    "kırmızı mercimek çorbası": {"kalori": 56, "protein": 3.5, "yag": 1.5, "karb": 8, "lif": 2, "kategori": "baklagil"},
    # USDA: Green peas, cooked
    "bezelye": {"kalori": 84, "protein": 5.4, "yag": 0.4, "karb": 15.6, "lif": 5.7, "kategori": "baklagil"},
    # USDA: Pinto beans, cooked (barbunya)
    "barbunya": {"kalori": 143, "protein": 9, "yag": 0.7, "karb": 26, "lif": 9, "kategori": "baklagil"},
    # USDA: Fava beans, cooked
    "bakla": {"kalori": 88, "protein": 7.6, "yag": 0.4, "karb": 12.4, "lif": 5.4, "kategori": "baklagil"},
    # USDA: Black-eyed peas, cooked
    "kuru börülce": {"kalori": 116, "protein": 7.7, "yag": 0.5, "karb": 21, "lif": 6.5, "kategori": "baklagil"},
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
    # TürkOMP: Bazlama
    "bazlama": {"kalori": 265, "protein": 8, "yag": 3, "karb": 51, "lif": 2, "kategori": "karbonhidrat", "porsiyon_g": 100, "porsiyon_ad": "1 adet"},
    # TürkOMP: Yufka
    "yufka": {"kalori": 290, "protein": 8.5, "yag": 1.5, "karb": 62, "lif": 1.8, "kategori": "karbonhidrat", "porsiyon_g": 50, "porsiyon_ad": "1 yaprak"},
    # USDA: Rye bread
    "çavdar ekmeği": {"kalori": 259, "protein": 8.5, "yag": 3.3, "karb": 48, "lif": 5.8, "kategori": "karbonhidrat", "porsiyon_g": 30, "porsiyon_ad": "1 dilim"},
    # USDA: Cornbread
    "mısır ekmeği": {"kalori": 261, "protein": 6.7, "yag": 7.1, "karb": 44, "lif": 2.4, "kategori": "karbonhidrat", "porsiyon_g": 60, "porsiyon_ad": "1 dilim"},
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
    # USDA: Spring onion / green onion
    "taze soğan": {"kalori": 32, "protein": 1.8, "yag": 0.2, "karb": 7.3, "lif": 2.6, "kategori": "sebze"},
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
    # USDA: Red cabbage, raw
    "kırmızı lahana": {"kalori": 31, "protein": 1.4, "yag": 0.2, "karb": 7.4, "lif": 2.1, "kategori": "sebze"},
    # USDA #11260: Mushroom, white, raw
    "mantar": {"kalori": 22, "protein": 3.1, "yag": 0.3, "karb": 3.3, "lif": 1, "kategori": "sebze"},
    # USDA: Celery, raw
    "kereviz": {"kalori": 16, "protein": 0.7, "yag": 0.2, "karb": 3, "lif": 1.6, "kategori": "sebze"},
    # USDA: Artichoke, cooked
    "enginar": {"kalori": 47, "protein": 3.3, "yag": 0.2, "karb": 10.5, "lif": 5.4, "kategori": "sebze"},
    # USDA: Leek, raw
    "pırasa": {"kalori": 61, "protein": 1.5, "yag": 0.3, "karb": 14, "lif": 1.8, "kategori": "sebze"},
    # USDA: Okra, cooked
    "bamya": {"kalori": 33, "protein": 1.9, "yag": 0.2, "karb": 7, "lif": 3.2, "kategori": "sebze"},
    # USDA: Purslane, raw
    "semizotu": {"kalori": 20, "protein": 2, "yag": 0.4, "karb": 3.4, "lif": 1, "kategori": "sebze"},
    # USDA: Swiss chard, raw
    "pazı": {"kalori": 19, "protein": 1.8, "yag": 0.2, "karb": 3.7, "lif": 1.6, "kategori": "sebze"},
    # USDA: Radish, raw
    "turp": {"kalori": 16, "protein": 0.7, "yag": 0.1, "karb": 3.4, "lif": 1.6, "kategori": "sebze"},
    # USDA: Asparagus, cooked
    "kuşkonmaz": {"kalori": 20, "protein": 2.2, "yag": 0.1, "karb": 3.9, "lif": 2.1, "kategori": "sebze"},
    # USDA: Beet, cooked
    "pancar": {"kalori": 44, "protein": 1.7, "yag": 0.2, "karb": 10, "lif": 2.8, "kategori": "sebze"},
    # USDA: Brussels sprouts, cooked
    "brüksel lahanası": {"kalori": 36, "protein": 2.6, "yag": 0.5, "karb": 7.1, "lif": 2.6, "kategori": "sebze"},
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
    # USDA: Plum, raw
    "erik": {"kalori": 46, "protein": 0.7, "yag": 0.3, "karb": 11, "lif": 1.4, "kategori": "meyve"},
    # USDA: Apricot, raw
    "kayısı": {"kalori": 48, "protein": 1.4, "yag": 0.4, "karb": 11, "lif": 2, "kategori": "meyve"},
    # USDA: Sour cherry, raw
    "vişne": {"kalori": 50, "protein": 1, "yag": 0.3, "karb": 12, "lif": 1.6, "kategori": "meyve"},
    # USDA: Grapefruit, raw
    "greyfurt": {"kalori": 42, "protein": 0.8, "yag": 0.1, "karb": 11, "lif": 1.6, "kategori": "meyve"},
    # USDA: Tangerine, raw
    "mandalina": {"kalori": 53, "protein": 0.8, "yag": 0.3, "karb": 13, "lif": 1.8, "kategori": "meyve"},
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
    # USDA: Prune (dried plum)
    "kuru erik": {"kalori": 240, "protein": 2.2, "yag": 0.4, "karb": 64, "lif": 7.1, "kategori": "kuru_meyve"},
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
    # USDA: Almond butter
    "badem ezmesi": {"kalori": 614, "protein": 21, "yag": 56, "karb": 19, "lif": 4, "kategori": "kuruyemis"},
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
    # USDA: Sesame seeds
    "susam": {"kalori": 573, "protein": 18, "yag": 50, "karb": 23, "lif": 12, "kategori": "kuruyemis"},
    # ==========================================
    # İŞLENMİŞ ET / ŞARKÜTÜRE (100g)
    # ==========================================
    # TürkOMP: Sucuk
    "sucuk": {"kalori": 452, "protein": 19, "yag": 40, "karb": 4, "lif": 0, "kategori": "protein"},
    # TürkOMP: Pastırma
    "pastırma": {"kalori": 174, "protein": 33, "yag": 4, "karb": 1, "lif": 0, "kategori": "protein"},
    # Hindi füme (deli meat)
    "hindi füme": {"kalori": 104, "protein": 18, "yag": 2.5, "karb": 2, "lif": 0, "kategori": "protein", "porsiyon_g": 30, "porsiyon_ad": "2 dilim"},
    # Tavuk füme (deli meat)
    "tavuk füme": {"kalori": 110, "protein": 17, "yag": 3.5, "karb": 2.5, "lif": 0, "kategori": "protein", "porsiyon_g": 30, "porsiyon_ad": "2 dilim"},
    # ==========================================
    # SÜT ÜRÜNLERİ EK (100g)
    # ==========================================
    # TürkOMP: Labne
    "labne": {"kalori": 130, "protein": 5, "yag": 10, "karb": 5, "lif": 0, "kategori": "sut_urunu"},
    # TürkOMP: Cacık
    "cacık": {"kalori": 40, "protein": 2.5, "yag": 2, "karb": 3, "lif": 0.3, "kategori": "sut_urunu"},
    # TürkOMP: Kaymak
    "kaymak": {"kalori": 350, "protein": 2, "yag": 37, "karb": 2, "lif": 0, "kategori": "sut_urunu"},
    # ==========================================
    # EKMEK EK ÇEŞİTLERİ (100g)
    # ==========================================
    # TürkOMP: Simit
    "simit": {"kalori": 310, "protein": 10, "yag": 4, "karb": 58, "lif": 2.5, "kategori": "karbonhidrat", "porsiyon_g": 120, "porsiyon_ad": "1 adet"},
    # TürkOMP: Erişte (pişmiş)
    "erişte": {"kalori": 140, "protein": 5, "yag": 2, "karb": 26, "lif": 1.5, "kategori": "karbonhidrat"},
    # ==========================================
    # ÇORBALAR (100g hazır porsiyon)
    # ==========================================
    # TürkOMP: Tarhana çorbası
    "tarhana çorbası": {"kalori": 40, "protein": 1.5, "yag": 1, "karb": 7, "lif": 0.5, "kategori": "corba"},
    # TürkOMP: Ezogelin çorbası
    "ezogelin çorbası": {"kalori": 45, "protein": 2, "yag": 1.5, "karb": 7, "lif": 1.5, "kategori": "corba"},
    # TürkOMP: Yayla çorbası
    "yayla çorbası": {"kalori": 35, "protein": 1.5, "yag": 1.5, "karb": 4, "lif": 0.3, "kategori": "corba"},
    # TürkOMP: Domates çorbası
    "domates çorbası": {"kalori": 30, "protein": 0.8, "yag": 1, "karb": 5, "lif": 0.7, "kategori": "corba"},
    # USDA: Chicken broth with meat
    "tavuk suyu çorba": {"kalori": 25, "protein": 3, "yag": 1, "karb": 1, "lif": 0, "kategori": "corba"},
    # ==========================================
    # YEŞİLLİK & BAHARAT (100g)
    # ==========================================
    # USDA: Parsley, fresh
    "maydanoz": {"kalori": 36, "protein": 3, "yag": 0.8, "karb": 6.3, "lif": 3.3, "kategori": "sebze"},
    # USDA: Dill, fresh
    "dereotu": {"kalori": 43, "protein": 3.5, "yag": 1.1, "karb": 7, "lif": 2.1, "kategori": "sebze"},
    # USDA: Arugula, raw
    "roka": {"kalori": 25, "protein": 2.6, "yag": 0.7, "karb": 3.7, "lif": 1.6, "kategori": "sebze"},
    # USDA: Mint, fresh
    "nane": {"kalori": 44, "protein": 3.3, "yag": 0.7, "karb": 8.4, "lif": 6.8, "kategori": "sebze"},
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
    # ==========================================
    # İÇECEKLER (100ml)
    # ==========================================
    # USDA: Orange juice, fresh
    "portakal suyu": {"kalori": 45, "protein": 0.7, "yag": 0.2, "karb": 10.4, "lif": 0.2, "kategori": "icecek"},
    # USDA: Apple juice
    "elma suyu": {"kalori": 46, "protein": 0.1, "yag": 0.1, "karb": 11.3, "lif": 0.1, "kategori": "icecek"},
    # USDA: Milk, skim/nonfat
    "yağsız süt": {"kalori": 34, "protein": 3.4, "yag": 0.1, "karb": 5, "lif": 0, "kategori": "sut_urunu"},
    # ==========================================
    # EK BESİNLER (100g)
    # ==========================================
    # USDA: Smoothie base — banana + yogurt style
    "smoothie": {"kalori": 75, "protein": 3, "yag": 1.5, "karb": 14, "lif": 1, "kategori": "icecek"},
    # USDA: Cream cheese
    "krem peynir": {"kalori": 342, "protein": 6, "yag": 34, "karb": 4, "lif": 0, "kategori": "sut_urunu"},
    # USDA: Ricotta cheese, part skim
    "ricotta": {"kalori": 138, "protein": 11, "yag": 8, "karb": 5, "lif": 0, "kategori": "sut_urunu"},
    # USDA: Energy/protein ball (date+nut based, generic)
    "energy ball": {"kalori": 390, "protein": 10, "yag": 18, "karb": 50, "lif": 5, "kategori": "diger", "porsiyon_g": 30, "porsiyon_ad": "1 adet"},
    # USDA: Reçel / jam
    "reçel": {"kalori": 250, "protein": 0.4, "yag": 0.1, "karb": 65, "lif": 0.6, "kategori": "tatlandirici", "porsiyon_g": 20, "porsiyon_ad": "1 yemek kaşığı"},
}
# Karbonhidrat kategorisindeki besinler — aynı öğünde 2+ olmamalı
STARCHY_FOODS = {
    "pirinç pilavı", "esmer pirinç", "bulgur pilavı", "makarna",
    "tam buğday makarna", "patates", "tatlı patates", "kısır", "kinoa",
    "nohut", "kuru fasulye", "mercimek", "kuskus", "erişte",
    "şehriye", "arpa şehriye", "bezelye", "barbunya", "bakla", "kuru börülce",
}
# Protein kaynakları — tekrar kontrolü için
PROTEIN_SOURCES = {
    "tavuk göğsü": "tavuk",
    "tavuk but": "tavuk",
    "tavuk baget": "tavuk",
    "tavuk füme": "tavuk",
    "hindi göğsü": "hindi",
    "hindi bonfile": "hindi",
    "hindi but": "hindi",
    "hindi füme": "hindi",
    "dana kıyma": "kırmızı et",
    "dana bonfile": "kırmızı et",
    "dana biftek": "kırmızı et",
    "dana kuşbaşı": "kırmızı et",
    "kuzu eti": "kırmızı et",
    "kuzu pirzola": "kırmızı et",
    "ciğer": "sakatat",
    "sucuk": "kırmızı et",
    "pastırma": "kırmızı et",
    "somon": "balık",
    "levrek": "balık",
    "çipura": "balık",
    "alabalık": "balık",
    "mezgit": "balık",
    "sardalya": "balık",
    "palamut": "balık",
    "lüfer": "balık",
    "istavrit": "balık",
    "ton balığı": "balık",
    "ton balığı konserve": "balık",
    "ton balığı taze": "balık",
    "hamsi": "balık",
    "karides": "deniz ürünü",
    "midye": "deniz ürünü",
    "kalamar": "deniz ürünü",
    "yumurta": "yumurta",
    "tofu": "tofu",
    "nohut": "baklagil",
    "kuru fasulye": "baklagil",
    "mercimek": "baklagil",
    "bezelye": "baklagil",
    "barbunya": "baklagil",
    "bakla": "baklagil",
    "kuru börülce": "baklagil",
}

# ==========================================
# İLHAM TARİFLERİ — Makro değeri taşımaz, sadece hazırlama fikri
# Kullanıcıya bağlayıcı değil, AI coach'un önerebileceği fikirler
# ==========================================
ILHAM_TARIFLERI = {
    "kahvalti": [
        {"ad": "Sebzeli Omlet", "malzemeler": ["yumurta", "domates", "biber", "maydanoz", "zeytinyağı"]},
        {"ad": "Peynirli Tost", "malzemeler": ["tam buğday ekmek", "beyaz peynir", "domates"]},
        {"ad": "Yulaf Bowl", "malzemeler": ["yulaf ezmesi", "süt", "muz", "badem", "bal"]},
        {"ad": "Haşlanmış Yumurta Tabağı", "malzemeler": ["yumurta", "beyaz peynir", "domates", "salatalık", "zeytin"]},
        {"ad": "Lor Peynirli Kahvaltı", "malzemeler": ["lor peyniri", "tam buğday ekmek", "domates", "ceviz", "bal"]},
        {"ad": "Avokadolu Tost", "malzemeler": ["tam buğday ekmek", "avokado", "yumurta", "kırmızı biber"]},
        {"ad": "Yoğurtlu Kahvaltı", "malzemeler": ["süzme yoğurt", "yulaf ezmesi kuru", "çilek", "bal", "ceviz"]},
        {"ad": "Sahanda Yumurta", "malzemeler": ["yumurta", "tereyağı", "domates", "biber"]},
        {"ad": "Menemen", "malzemeler": ["yumurta", "domates", "biber", "soğan", "zeytinyağı"]},
        {"ad": "Sucuklu Yumurta", "malzemeler": ["yumurta", "sucuk", "domates"]},
        {"ad": "Çılbır", "malzemeler": ["yumurta", "yoğurt", "tereyağı", "kırmızı biber"]},
        {"ad": "Peynir Tabağı", "malzemeler": ["beyaz peynir", "kaşar peynir", "zeytin", "domates", "salatalık", "tam buğday ekmek"]},
        {"ad": "Kaşarlı Tost", "malzemeler": ["tam buğday ekmek", "kaşar peynir", "domates"]},
        {"ad": "Tahinli Pekmezli Kahvaltı", "malzemeler": ["tahin", "pekmez", "tam buğday ekmek", "beyaz peynir"]},
        {"ad": "Çökelekli Kahvaltı", "malzemeler": ["çökelek", "tam buğday ekmek", "domates", "zeytinyağı", "ceviz"]},
        {"ad": "Simit Kahvaltı", "malzemeler": ["simit", "beyaz peynir", "domates", "çay"]},
        {"ad": "Pastırmalı Yumurta", "malzemeler": ["yumurta", "pastırma", "domates"]},
        {"ad": "Bazlama Kahvaltı", "malzemeler": ["bazlama", "lor peyniri", "bal", "ceviz"]},
    ],
    "ara_ogun": [
        {"ad": "Meyveli Yoğurt", "malzemeler": ["süzme yoğurt", "çilek", "badem"]},
        {"ad": "Protein Smoothie", "malzemeler": ["protein tozu", "muz", "süt", "fıstık ezmesi"]},
        {"ad": "Kuruyemiş Mix", "malzemeler": ["badem", "ceviz", "kuru kayısı"]},
        {"ad": "Elma + Fıstık Ezmesi", "malzemeler": ["elma", "fıstık ezmesi"]},
        {"ad": "Lor Peynirli Atıştırmalık", "malzemeler": ["lor peyniri", "domates", "ceviz"]},
        {"ad": "Muzlu Yulaf", "malzemeler": ["muz", "yulaf ezmesi kuru", "süt", "chia tohumu"]},
        {"ad": "Humus + Sebze", "malzemeler": ["humus", "havuç", "salatalık"]},
        {"ad": "Yoğurt + Bal + Ceviz", "malzemeler": ["yoğurt", "bal", "ceviz"]},
        {"ad": "Fındıklı Yoğurt", "malzemeler": ["süzme yoğurt", "fındık", "bal"]},
        {"ad": "Kuru Meyve Tabağı", "malzemeler": ["kuru kayısı", "kuru incir", "badem"]},
        {"ad": "Muz + Badem Ezmesi", "malzemeler": ["muz", "badem ezmesi"]},
        {"ad": "Pirinç Patlağı + Peynir", "malzemeler": ["pirinç patlağı", "lor peyniri", "domates"]},
        {"ad": "Meyve Salatası", "malzemeler": ["elma", "portakal", "kivi", "nar"]},
        {"ad": "Energy Ball", "malzemeler": ["hurma", "badem", "yulaf ezmesi kuru", "chia tohumu"]},
        {"ad": "Ayran + Peynir", "malzemeler": ["ayran", "beyaz peynir", "salatalık"]},
        {"ad": "Çikolatalı Muz", "malzemeler": ["muz", "bitter çikolata", "fındık"]},
        {"ad": "Havuç Çubukları + Humus", "malzemeler": ["havuç", "humus"]},
        {"ad": "Antep Fıstıklı Yoğurt", "malzemeler": ["süzme yoğurt", "antep fıstığı", "bal"]},
    ],
    "ana_ogun": [
        {"ad": "Izgara Tavuk + Pilav + Salata", "malzemeler": ["tavuk göğsü", "bulgur pilavı", "yeşil salata", "domates", "zeytinyağı"]},
        {"ad": "Somon + Patates + Brokoli", "malzemeler": ["somon", "patates", "brokoli", "zeytinyağı"]},
        {"ad": "Köfte + Bulgur", "malzemeler": ["dana kıyma", "bulgur pilavı", "yeşil salata", "domates"]},
        {"ad": "Tavuk Salata Bowl", "malzemeler": ["tavuk göğsü", "kinoa", "ıspanak", "avokado", "domates"]},
        {"ad": "Balık + Sebze Sote", "malzemeler": ["levrek", "kabak", "havuç", "biber", "zeytinyağı"]},
        {"ad": "Mercimek + Pirinç + Yoğurt", "malzemeler": ["mercimek", "pirinç pilavı", "yoğurt"]},
        {"ad": "Hindi + Makarna + Sebze", "malzemeler": ["hindi göğsü", "tam buğday makarna", "brokoli", "zeytinyağı"]},
        {"ad": "Nohut Yemeği + Pirinç", "malzemeler": ["nohut", "pirinç pilavı", "yeşil salata"]},
        {"ad": "Ton Balıklı Salata", "malzemeler": ["ton balığı konserve", "yeşil salata", "mısır", "domates", "zeytinyağı"]},
        {"ad": "Patlıcan Musakka + Pilav", "malzemeler": ["patlıcan", "dana kıyma", "pirinç pilavı", "yoğurt"]},
        {"ad": "Fırında Tavuk But + Sebze", "malzemeler": ["tavuk but", "patates", "havuç", "biber", "zeytinyağı"]},
        {"ad": "Karnıyarık", "malzemeler": ["patlıcan", "dana kıyma", "domates", "biber", "pirinç pilavı"]},
        {"ad": "Etli Nohut", "malzemeler": ["dana kuşbaşı", "nohut", "domates", "pirinç pilavı"]},
        {"ad": "Etli Bezelye", "malzemeler": ["dana kuşbaşı", "bezelye", "patates", "domates"]},
        {"ad": "Zeytinyağlı Fasulye", "malzemeler": ["yeşil fasulye", "domates", "soğan", "zeytinyağı", "tam buğday ekmek"]},
        {"ad": "Fırında Somon + Sebze", "malzemeler": ["somon", "brokoli", "havuç", "zeytinyağı"]},
        {"ad": "Tavuk Şiş + Bulgur", "malzemeler": ["tavuk göğsü", "bulgur pilavı", "biber", "soğan", "domates"]},
        {"ad": "Mercimek Köftesi + Salata", "malzemeler": ["mercimek", "bulgur pilavı", "yeşil salata", "domates", "nar"]},
        {"ad": "Barbunya Pilaki", "malzemeler": ["barbunya", "soğan", "havuç", "domates", "zeytinyağı"]},
        {"ad": "Fırında Köfte + Patates", "malzemeler": ["dana kıyma", "patates", "domates", "biber"]},
        {"ad": "Kabak Mücver", "malzemeler": ["kabak", "yumurta", "un", "beyaz peynir", "dereotu"]},
        {"ad": "Karnabahar Graten", "malzemeler": ["karnabahar", "kaşar peynir", "süt", "yumurta"]},
        {"ad": "Alabalık + Pilav", "malzemeler": ["alabalık", "pirinç pilavı", "yeşil salata", "zeytinyağı"]},
        {"ad": "Mantarlı Tavuk Sote", "malzemeler": ["tavuk göğsü", "mantar", "biber", "soğan", "zeytinyağı"]},
        {"ad": "Sebzeli Hindi Güveç", "malzemeler": ["hindi but", "kabak", "patlıcan", "biber", "domates"]},
        {"ad": "Kuru Fasulye + Pirinç", "malzemeler": ["kuru fasulye", "pirinç pilavı", "turşu", "soğan"]},
        {"ad": "İmam Bayıldı", "malzemeler": ["patlıcan", "domates", "soğan", "biber", "zeytinyağı"]},
        {"ad": "Ispanaklı Yumurta + Ekmek", "malzemeler": ["ıspanak", "yumurta", "soğan", "tam buğday ekmek"]},
        {"ad": "Çipura + Salata", "malzemeler": ["çipura", "yeşil salata", "domates", "zeytinyağı", "tam buğday ekmek"]},
        {"ad": "Bamya Yemeği + Pilav", "malzemeler": ["bamya", "domates", "soğan", "zeytinyağı", "bulgur pilavı"]},
        {"ad": "Pırasa Yemeği + Yoğurt", "malzemeler": ["pırasa", "havuç", "pirinç pilavı", "yoğurt", "zeytinyağı"]},
        {"ad": "Enginar Zeytinyağlı", "malzemeler": ["enginar", "havuç", "bezelye", "zeytinyağı", "tam buğday ekmek"]},
        {"ad": "Palamut Izgara + Salata", "malzemeler": ["palamut", "roka", "domates", "soğan", "zeytinyağı"]},
        {"ad": "Semizotu Yemeği", "malzemeler": ["semizotu", "yoğurt", "pirinç pilavı", "zeytinyağı"]},
    ],
}
