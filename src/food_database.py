"""
Besin Veritabanı — Yaygın Türk besinlerinin makro değerleri (100g başına).
TürkOMP ve USDA referans alınarak hazırlanmıştır.
Bu veritabanı programatik validasyonda kullanılır.
"""

# Her besin: 100g pişmiş/hazır hali
# Yapı: {"kalori": kcal, "protein": g, "yag": g, "karb": g, "lif": g}

BESIN_DB = {
    # ==========================================
    # PROTEİN KAYNAKLARI
    # ==========================================
    "tavuk göğsü": {"kalori": 165, "protein": 31, "yag": 3.6, "karb": 0, "lif": 0, "kategori": "protein"},
    "tavuk but": {"kalori": 209, "protein": 26, "yag": 10.9, "karb": 0, "lif": 0, "kategori": "protein"},
    "hindi göğsü": {"kalori": 135, "protein": 30, "yag": 1, "karb": 0, "lif": 0, "kategori": "protein"},
    "hindi bonfile": {"kalori": 135, "protein": 30, "yag": 1, "karb": 0, "lif": 0, "kategori": "protein"},
    "dana kıyma": {"kalori": 250, "protein": 26, "yag": 15, "karb": 0, "lif": 0, "kategori": "protein"},
    "dana bonfile": {"kalori": 217, "protein": 28, "yag": 11, "karb": 0, "lif": 0, "kategori": "protein"},
    "kuzu eti": {"kalori": 282, "protein": 25, "yag": 20, "karb": 0, "lif": 0, "kategori": "protein"},
    "somon": {"kalori": 208, "protein": 20, "yag": 13, "karb": 0, "lif": 0, "kategori": "protein"},
    "levrek": {"kalori": 124, "protein": 23.6, "yag": 2.6, "karb": 0, "lif": 0, "kategori": "protein"},
    "çipura": {"kalori": 135, "protein": 23, "yag": 4.5, "karb": 0, "lif": 0, "kategori": "protein"},
    "ton balığı": {"kalori": 116, "protein": 25.5, "yag": 1, "karb": 0, "lif": 0, "kategori": "protein"},
    "ton balığı konserve": {"kalori": 116, "protein": 25.5, "yag": 1, "karb": 0, "lif": 0, "kategori": "protein"},
    "hamsi": {"kalori": 131, "protein": 20, "yag": 5, "karb": 0, "lif": 0, "kategori": "protein"},
    "karides": {"kalori": 99, "protein": 24, "yag": 0.3, "karb": 0.2, "lif": 0, "kategori": "protein"},
    "yumurta": {"kalori": 155, "protein": 13, "yag": 11, "karb": 1.1, "lif": 0, "kategori": "protein", "porsiyon_g": 60, "porsiyon_ad": "1 adet"},
    "tofu": {"kalori": 76, "protein": 8, "yag": 4.8, "karb": 1.9, "lif": 0.3, "kategori": "protein"},

    # ==========================================
    # SÜT ÜRÜNLERİ
    # ==========================================
    "beyaz peynir": {"kalori": 250, "protein": 17, "yag": 20, "karb": 0, "lif": 0, "kategori": "sut_urunu"},
    "kaşar peynir": {"kalori": 350, "protein": 25, "yag": 27, "karb": 2, "lif": 0, "kategori": "sut_urunu"},
    "lor peyniri": {"kalori": 98, "protein": 11, "yag": 4, "karb": 3.4, "lif": 0, "kategori": "sut_urunu"},
    "yunan yoğurdu": {"kalori": 73, "protein": 10, "yag": 2, "karb": 4, "lif": 0, "kategori": "sut_urunu"},
    "süzme yoğurt": {"kalori": 90, "protein": 6, "yag": 5, "karb": 5, "lif": 0, "kategori": "sut_urunu"},
    "süzme yoğurt yağsız": {"kalori": 57, "protein": 10, "yag": 0.2, "karb": 4, "lif": 0, "kategori": "sut_urunu"},
    "süt": {"kalori": 60, "protein": 3.2, "yag": 3.2, "karb": 4.8, "lif": 0, "kategori": "sut_urunu"},
    "ayran": {"kalori": 35, "protein": 1.7, "yag": 1.5, "karb": 3.5, "lif": 0, "kategori": "sut_urunu"},

    # ==========================================
    # KARBONHİDRAT KAYNAKLARI
    # ==========================================
    "pirinç pilavı": {"kalori": 130, "protein": 2.7, "yag": 0.3, "karb": 28, "lif": 0.4, "kategori": "karbonhidrat"},
    "bulgur pilavı": {"kalori": 83, "protein": 3, "yag": 0.2, "karb": 18.6, "lif": 4.5, "kategori": "karbonhidrat"},
    "makarna": {"kalori": 131, "protein": 5, "yag": 1.1, "karb": 25, "lif": 1.8, "kategori": "karbonhidrat"},
    "tam buğday makarna": {"kalori": 124, "protein": 5.3, "yag": 0.5, "karb": 26.5, "lif": 3.9, "kategori": "karbonhidrat"},
    "tam buğday ekmek": {"kalori": 260, "protein": 10, "yag": 4, "karb": 48, "lif": 7, "kategori": "karbonhidrat", "porsiyon_g": 25, "porsiyon_ad": "1 dilim"},
    "beyaz ekmek": {"kalori": 265, "protein": 9, "yag": 3.2, "karb": 49, "lif": 2.7, "kategori": "karbonhidrat", "porsiyon_g": 25, "porsiyon_ad": "1 dilim"},
    "yulaf ezmesi": {"kalori": 68, "protein": 2.4, "yag": 1.4, "karb": 12, "lif": 1.7, "kategori": "karbonhidrat"},
    "kinoa": {"kalori": 120, "protein": 4.4, "yag": 1.9, "karb": 21.3, "lif": 2.8, "kategori": "karbonhidrat"},
    "patates": {"kalori": 87, "protein": 1.9, "yag": 0.1, "karb": 20.1, "lif": 1.8, "kategori": "karbonhidrat"},
    "tatlı patates": {"kalori": 86, "protein": 1.6, "yag": 0.1, "karb": 20, "lif": 3, "kategori": "karbonhidrat"},
    "kısır": {"kalori": 135, "protein": 3, "yag": 4, "karb": 23, "lif": 5, "kategori": "karbonhidrat"},
    "nohut": {"kalori": 164, "protein": 8.9, "yag": 2.6, "karb": 27, "lif": 7.6, "kategori": "baklagil"},
    "kuru fasulye": {"kalori": 127, "protein": 8.7, "yag": 0.5, "karb": 22, "lif": 6.4, "kategori": "baklagil"},
    "mercimek": {"kalori": 116, "protein": 9, "yag": 0.4, "karb": 20, "lif": 7.9, "kategori": "baklagil"},
    "kırmızı mercimek çorbası": {"kalori": 56, "protein": 3.5, "yag": 1.5, "karb": 8, "lif": 2, "kategori": "baklagil"},
    "granola": {"kalori": 450, "protein": 10, "yag": 20, "karb": 60, "lif": 5, "kategori": "karbonhidrat"},

    # ==========================================
    # SEBZELER
    # ==========================================
    "brokoli": {"kalori": 35, "protein": 2.4, "yag": 0.4, "karb": 7.2, "lif": 3.3, "kategori": "sebze"},
    "ıspanak": {"kalori": 23, "protein": 2.9, "yag": 0.4, "karb": 3.6, "lif": 2.2, "kategori": "sebze"},
    "domates": {"kalori": 18, "protein": 0.9, "yag": 0.2, "karb": 3.9, "lif": 1.2, "kategori": "sebze"},
    "salatalık": {"kalori": 15, "protein": 0.7, "yag": 0.1, "karb": 3.6, "lif": 0.5, "kategori": "sebze"},
    "biber": {"kalori": 31, "protein": 1, "yag": 0.3, "karb": 6, "lif": 2.1, "kategori": "sebze"},
    "soğan": {"kalori": 40, "protein": 1.1, "yag": 0.1, "karb": 9.3, "lif": 1.7, "kategori": "sebze"},
    "havuç": {"kalori": 41, "protein": 0.9, "yag": 0.2, "karb": 9.6, "lif": 2.8, "kategori": "sebze"},
    "kabak": {"kalori": 17, "protein": 1.2, "yag": 0.3, "karb": 3.1, "lif": 1, "kategori": "sebze"},
    "patlıcan": {"kalori": 25, "protein": 1, "yag": 0.2, "karb": 6, "lif": 3, "kategori": "sebze"},
    "karnabahar": {"kalori": 25, "protein": 1.9, "yag": 0.3, "karb": 5, "lif": 2, "kategori": "sebze"},
    "yeşil salata": {"kalori": 15, "protein": 1.4, "yag": 0.2, "karb": 2.9, "lif": 1.3, "kategori": "sebze"},
    "avokado": {"kalori": 160, "protein": 2, "yag": 15, "karb": 8.5, "lif": 6.7, "kategori": "sebze"},
    "mısır": {"kalori": 86, "protein": 3.3, "yag": 1.4, "karb": 19, "lif": 2.7, "kategori": "sebze"},

    # ==========================================
    # MEYVELER
    # ==========================================
    "elma": {"kalori": 52, "protein": 0.3, "yag": 0.2, "karb": 14, "lif": 2.4, "kategori": "meyve"},
    "muz": {"kalori": 89, "protein": 1.1, "yag": 0.3, "karb": 23, "lif": 2.6, "kategori": "meyve"},
    "portakal": {"kalori": 47, "protein": 0.9, "yag": 0.1, "karb": 12, "lif": 2.4, "kategori": "meyve"},
    "çilek": {"kalori": 32, "protein": 0.7, "yag": 0.3, "karb": 7.7, "lif": 2, "kategori": "meyve"},
    "ahududu": {"kalori": 52, "protein": 1.2, "yag": 0.7, "karb": 12, "lif": 6.5, "kategori": "meyve"},
    "yaban mersini": {"kalori": 57, "protein": 0.7, "yag": 0.3, "karb": 14.5, "lif": 2.4, "kategori": "meyve"},
    "kivi": {"kalori": 61, "protein": 1.1, "yag": 0.5, "karb": 15, "lif": 3, "kategori": "meyve"},
    "üzüm": {"kalori": 69, "protein": 0.7, "yag": 0.2, "karb": 18, "lif": 0.9, "kategori": "meyve"},
    "kuru üzüm": {"kalori": 299, "protein": 3.1, "yag": 0.5, "karb": 79, "lif": 3.7, "kategori": "meyve"},
    "hurma": {"kalori": 277, "protein": 1.8, "yag": 0.2, "karb": 75, "lif": 7, "kategori": "meyve"},
    "incir": {"kalori": 74, "protein": 0.8, "yag": 0.3, "karb": 19, "lif": 2.9, "kategori": "meyve"},
    "armut": {"kalori": 57, "protein": 0.4, "yag": 0.1, "karb": 15, "lif": 3.1, "kategori": "meyve"},
    "şeftali": {"kalori": 39, "protein": 0.9, "yag": 0.3, "karb": 10, "lif": 1.5, "kategori": "meyve"},

    # ==========================================
    # YAĞLAR VE KURUYEMİŞLER
    # ==========================================
    "zeytinyağı": {"kalori": 884, "protein": 0, "yag": 100, "karb": 0, "lif": 0, "kategori": "yag", "porsiyon_g": 14, "porsiyon_ad": "1 yemek kaşığı"},
    "tereyağı": {"kalori": 717, "protein": 0.9, "yag": 81, "karb": 0.1, "lif": 0, "kategori": "yag", "porsiyon_g": 10, "porsiyon_ad": "1 tatlı kaşığı"},
    "badem": {"kalori": 579, "protein": 21, "yag": 50, "karb": 22, "lif": 12.5, "kategori": "kuruyemis"},
    "ceviz": {"kalori": 654, "protein": 15, "yag": 65, "karb": 14, "lif": 6.7, "kategori": "kuruyemis"},
    "fındık": {"kalori": 628, "protein": 15, "yag": 61, "karb": 17, "lif": 9.7, "kategori": "kuruyemis"},
    "yer fıstığı": {"kalori": 567, "protein": 26, "yag": 49, "karb": 16, "lif": 8.5, "kategori": "kuruyemis"},
    "fıstık ezmesi": {"kalori": 588, "protein": 25, "yag": 50, "karb": 20, "lif": 6, "kategori": "kuruyemis"},

    # ==========================================
    # KURU MEYVELER
    # ==========================================
    "kuru kayısı": {"kalori": 241, "protein": 3.4, "yag": 0.5, "karb": 63, "lif": 7.3, "kategori": "kuru_meyve"},
    "kuru üzüm": {"kalori": 299, "protein": 3.1, "yag": 0.5, "karb": 79, "lif": 3.7, "kategori": "kuru_meyve"},
    "hurma": {"kalori": 277, "protein": 1.8, "yag": 0.2, "karb": 75, "lif": 7, "kategori": "kuru_meyve"},
    "kuru incir": {"kalori": 249, "protein": 3.3, "yag": 0.9, "karb": 64, "lif": 9.8, "kategori": "kuru_meyve"},

    # ==========================================
    # EKMEK ÇEŞİTLERİ
    # ==========================================
    "lavaş ekmeği": {"kalori": 275, "protein": 9.1, "yag": 1.2, "karb": 56, "lif": 2.2, "kategori": "karbonhidrat", "porsiyon_g": 60, "porsiyon_ad": "1 adet"},
    "tam buğday lavaş": {"kalori": 262, "protein": 10, "yag": 2.5, "karb": 50, "lif": 6.8, "kategori": "karbonhidrat", "porsiyon_g": 60, "porsiyon_ad": "1 adet"},
    "tortilla": {"kalori": 312, "protein": 8.3, "yag": 8.1, "karb": 52, "lif": 3.1, "kategori": "karbonhidrat", "porsiyon_g": 45, "porsiyon_ad": "1 adet"},

    # ==========================================
    # PEYNİR ÇEŞİTLERİ
    # ==========================================
    "feta peyniri": {"kalori": 264, "protein": 14, "yag": 21, "karb": 4, "lif": 0, "kategori": "sut_urunu"},
    "çökelek": {"kalori": 72, "protein": 11, "yag": 1.5, "karb": 4, "lif": 0, "kategori": "sut_urunu"},
    "tulum peyniri": {"kalori": 300, "protein": 20, "yag": 24, "karb": 1, "lif": 0, "kategori": "sut_urunu"},

    # ==========================================
    # ET İŞLENMİŞ
    # ==========================================
    "tavuk döner": {"kalori": 175, "protein": 28, "yag": 6, "karb": 2, "lif": 0, "kategori": "protein"},
    "köfte": {"kalori": 235, "protein": 22, "yag": 15, "karb": 3, "lif": 0.5, "kategori": "protein"},

    # ==========================================
    # DİĞER
    # ==========================================
    "bal": {"kalori": 304, "protein": 0.3, "yag": 0, "karb": 82, "lif": 0.2, "kategori": "tatlandirici", "porsiyon_g": 21, "porsiyon_ad": "1 yemek kaşığı"},
    "tahin": {"kalori": 595, "protein": 17, "yag": 54, "karb": 21, "lif": 9.3, "kategori": "diger"},
    "humus": {"kalori": 166, "protein": 7.9, "yag": 9.6, "karb": 14.3, "lif": 6, "kategori": "diger"},
    "zeytin": {"kalori": 115, "protein": 0.8, "yag": 11, "karb": 6, "lif": 3.2, "kategori": "diger"},
    "pirinç kağıdı": {"kalori": 319, "protein": 0.8, "yag": 0.1, "karb": 80, "lif": 0, "kategori": "diger", "porsiyon_g": 10, "porsiyon_ad": "1 adet"},
    "protein tozu": {"kalori": 400, "protein": 80, "yag": 5, "karb": 10, "lif": 0, "kategori": "supplement", "porsiyon_g": 30, "porsiyon_ad": "1 ölçek"},
    "un": {"kalori": 364, "protein": 10, "yag": 1, "karb": 76, "lif": 2.7, "kategori": "karbonhidrat"},
    "pankek": {"kalori": 227, "protein": 6.4, "yag": 10, "karb": 28, "lif": 1, "kategori": "karbonhidrat"},
}

# Karbonhidrat kategorisindeki besinler — aynı öğünde 2+ olmamalı
STARCHY_FOODS = {
    "pirinç pilavı", "bulgur pilavı", "makarna", "tam buğday makarna",
    "patates", "tatlı patates", "kısır", "kinoa", "nohut", "kuru fasulye",
    "mercimek",
}

# Protein kaynakları — tekrar kontrolü için
PROTEIN_SOURCES = {
    "tavuk göğsü": "tavuk",
    "tavuk but": "tavuk",
    "hindi göğsü": "hindi",
    "hindi bonfile": "hindi",
    "dana kıyma": "kırmızı et",
    "dana bonfile": "kırmızı et",
    "kuzu eti": "kırmızı et",
    "somon": "balık",
    "levrek": "balık",
    "çipura": "balık",
    "ton balığı": "balık",
    "ton balığı konserve": "balık",
    "hamsi": "balık",
    "karides": "deniz ürünü",
    "yumurta": "yumurta",
    "tofu": "tofu",
    "nohut": "baklagil",
    "kuru fasulye": "baklagil",
    "mercimek": "baklagil",
    "tavuk döner": "tavuk",
    "köfte": "kırmızı et",
}
