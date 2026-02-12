"""
Meal Validator Unit Tests — Programatik validasyonun doğru çalıştığını test eder.
"""
import pytest
from src.meal_validator import (
    parse_plan_json, remove_plan_json, validate_plan, format_validation_feedback,
    _find_food_in_db,
)


# ==========================================
# YARDIMCI FONKSİYONLAR
# ==========================================

def make_besin(ad, gram, protein, yag, karb, lif=0):
    """Test için besin dict'i oluştur — kaloriyi otomatik hesapla."""
    kalori = round((protein * 4) + (yag * 9) + (karb * 4))
    return {"ad": ad, "gram": gram, "protein": protein, "yag": yag, "karb": karb, "lif": lif, "kalori": kalori}


def make_ogun(tip, besinler, saat="12:00"):
    """Test için öğün dict'i oluştur — toplamları otomatik hesapla."""
    toplam = {
        "protein": round(sum(b["protein"] for b in besinler), 1),
        "yag": round(sum(b["yag"] for b in besinler), 1),
        "karb": round(sum(b["karb"] for b in besinler), 1),
        "lif": round(sum(b["lif"] for b in besinler), 1),
        "kalori": sum(b["kalori"] for b in besinler),
    }
    return {"tip": tip, "saat": saat, "besinler": besinler, "toplam": toplam}


def make_plan(ogunler, hedef=None):
    """Test için plan dict'i oluştur."""
    gun_toplam = {
        "protein": round(sum(o["toplam"]["protein"] for o in ogunler), 1),
        "yag": round(sum(o["toplam"]["yag"] for o in ogunler), 1),
        "karb": round(sum(o["toplam"]["karb"] for o in ogunler), 1),
        "lif": round(sum(o["toplam"]["lif"] for o in ogunler), 1),
        "kalori": sum(o["toplam"]["kalori"] for o in ogunler),
    }
    if not hedef:
        hedef = gun_toplam.copy()
    return {
        "gun": "2025-02-12",
        "gun_tipi": "dinlenme",
        "hedef": hedef,
        "ogunler": ogunler,
        "gun_toplam": gun_toplam,
    }


DEFAULT_USER = {
    "hedef_kalori": 2500,
    "protein_g": 130,
    "karbonhidrat_g": 350,
    "yag_g": 65,
    "lif_g": 30,
    "yagsiz_kutle_kg": 70,
    "kronik_hastaliklar": [],
}


# ==========================================
# PARSE TESTLERİ
# ==========================================

class TestParseJSON:
    def test_parse_valid_json(self):
        response = 'Plan:\n<!--PLAN_JSON:{"gun": "2025-02-12", "ogunler": []}-->\nGüzel plan!'
        result = parse_plan_json(response)
        assert result is not None
        assert result["gun"] == "2025-02-12"

    def test_parse_no_json(self):
        response = "Bu bir normal mesaj, JSON yok."
        result = parse_plan_json(response)
        assert result is None

    def test_parse_invalid_json(self):
        response = "<!--PLAN_JSON:{invalid json}-->"
        result = parse_plan_json(response)
        assert result is None

    def test_remove_plan_json(self):
        response = "Plan:\n<!--PLAN_JSON:{\"test\": true}-->\nSon satır."
        clean = remove_plan_json(response)
        assert "PLAN_JSON" not in clean
        assert "Plan:" in clean
        assert "Son satır." in clean


# ==========================================
# VALİDASYON TESTLERİ — BAŞARILI PLAN
# ==========================================

class TestValidPlan:
    def test_correct_plan_passes(self):
        """Matematiksel olarak doğru plan validasyondan geçmeli."""
        # Değerler BESIN_DB'den orantılı hesaplanmış (gram/100 × DB değeri)
        ogunler = [
            make_ogun("kahvalti", [
                # Yumurta 120g: DB 155kcal, P:13, Y:11, K:1.1 per 100g → ×1.2
                make_besin("Yumurta", 120, 15.6, 13.2, 1.3, 0),
                # Tam buğday ekmek 50g: DB 260kcal, P:10, Y:4, K:48 per 100g → ×0.5
                make_besin("Tam buğday ekmek", 50, 5, 2, 24, 3.5),
                # Beyaz peynir 30g: DB 289kcal, P:18, Y:23, K:1.5 per 100g → ×0.3
                make_besin("Beyaz peynir", 30, 5.4, 6.9, 0.45, 0),
            ]),
            make_ogun("ogle", [
                # Tavuk göğsü 200g: DB 165kcal, P:31, Y:3.6, K:0 per 100g → ×2
                make_besin("Tavuk göğsü", 200, 62, 7.2, 0, 0),
                # Pirinç pilavı 150g: DB 130kcal, P:2.7, Y:0.3, K:28 per 100g → ×1.5
                make_besin("Pirinç pilavı", 150, 4.05, 0.45, 42, 0.6),
                # Salata (yeşil salata) 150g: DB 15kcal, P:1.4, Y:0.2, K:2.9 per 100g → ×1.5
                make_besin("Yeşil salata", 150, 2.1, 0.3, 4.35, 1.95),
            ]),
            make_ogun("aksam", [
                # Somon 180g: DB 208kcal, P:20, Y:13, K:0 per 100g → ×1.8
                make_besin("Somon", 180, 36, 23.4, 0, 0),
                # Kinoa 120g: DB 120kcal, P:4.4, Y:1.9, K:21.3 per 100g → ×1.2
                make_besin("Kinoa", 120, 5.28, 2.28, 25.56, 3.36),
                # Brokoli 150g: DB 35kcal, P:2.4, Y:0.4, K:7.2 per 100g → ×1.5
                make_besin("Brokoli", 150, 3.6, 0.6, 10.8, 4.95),
            ]),
        ]
        plan = make_plan(ogunler)
        # Kullanıcı hedeflerini planın gerçek toplamlarına yakın ayarla
        totals = plan["gun_toplam"]
        matching_user = {
            **DEFAULT_USER,
            "hedef_kalori": totals["kalori"],
            "protein_g": totals["protein"],
            "karbonhidrat_g": totals["karb"],
            "yag_g": totals["yag"],
            "lif_g": totals["lif"],
        }
        result = validate_plan(plan, matching_user)
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_corrected_totals_calculated(self):
        """Doğrulanmış toplamlar hesaplanmalı."""
        ogunler = [
            make_ogun("kahvalti", [make_besin("Test", 100, 20, 10, 30, 5)]),
        ]
        plan = make_plan(ogunler)
        result = validate_plan(plan, DEFAULT_USER)
        totals = result["corrected_totals"]
        assert totals is not None
        assert totals["protein"] == 20
        assert totals["yag"] == 10
        assert totals["karb"] == 30


# ==========================================
# VALİDASYON TESTLERİ — MAKRO MATEMATİK HATASI
# ==========================================

class TestMacroMath:
    def test_calorie_mismatch_detected(self):
        """Besinin makro-kalori uyumsuzluğu tespit edilmeli."""
        ogunler = [
            make_ogun("kahvalti", [{
                "ad": "Yanlış kalori",
                "gram": 100,
                "protein": 20,
                "yag": 10,
                "karb": 30,
                "lif": 0,
                "kalori": 500,  # Doğrusu: (20*4)+(10*9)+(30*4) = 290
            }]),
        ]
        # Toplam da düzelt
        ogunler[0]["toplam"] = {"protein": 20, "yag": 10, "karb": 30, "lif": 0, "kalori": 500}
        plan = make_plan(ogunler)
        result = validate_plan(plan, DEFAULT_USER)
        assert not result["valid"]
        math_errors = [e for e in result["errors"] if e["tip"] == "makro_matematik"]
        assert len(math_errors) > 0


# ==========================================
# VALİDASYON TESTLERİ — PROTEİN TEKRARI
# ==========================================

class TestProteinRepetition:
    def test_same_day_protein_repetition(self):
        """Aynı gün öğle ve akşamda aynı protein kaynağı hata vermeli."""
        ogunler = [
            make_ogun("ogle", [
                make_besin("Tavuk göğsü", 200, 62, 7, 0, 0),
                make_besin("Pirinç pilavı", 150, 4, 0.5, 42, 0.6),
            ]),
            make_ogun("aksam", [
                make_besin("Tavuk but", 200, 52, 22, 0, 0),  # Yine tavuk!
                make_besin("Makarna", 150, 7.5, 1.6, 37.5, 2.7),
            ]),
        ]
        plan = make_plan(ogunler)
        result = validate_plan(plan, DEFAULT_USER)
        protein_errors = [e for e in result["errors"] if e["tip"] == "protein_tekrar"]
        assert len(protein_errors) > 0
        assert "tavuk" in protein_errors[0]["mesaj"].lower()

    def test_different_proteins_ok(self):
        """Farklı protein kaynakları hata vermemeli."""
        ogunler = [
            make_ogun("ogle", [
                make_besin("Tavuk göğsü", 200, 62, 7, 0, 0),
                make_besin("Pirinç pilavı", 150, 4, 0.5, 42, 0.6),
            ]),
            make_ogun("aksam", [
                make_besin("Somon", 180, 36, 23, 0, 0),
                make_besin("Kinoa", 120, 5, 2, 26, 3.4),
            ]),
        ]
        plan = make_plan(ogunler)
        result = validate_plan(plan, DEFAULT_USER)
        protein_errors = [e for e in result["errors"] if e["tip"] == "protein_tekrar"]
        assert len(protein_errors) == 0


# ==========================================
# VALİDASYON TESTLERİ — ÖĞÜN MANTIĞI
# ==========================================

class TestMealLogic:
    def test_double_starchy_detected(self):
        """Aynı öğünde 2 nişastalı besin tespit edilmeli."""
        ogunler = [
            make_ogun("ogle", [
                make_besin("Tavuk göğsü", 200, 62, 7, 0, 0),
                make_besin("Pirinç pilavı", 150, 4, 0.5, 42, 0.6),
                make_besin("Kısır", 80, 2.4, 3.2, 18.4, 4),  # Pilav + Kısır!
            ]),
        ]
        plan = make_plan(ogunler)
        result = validate_plan(plan, DEFAULT_USER)
        logic_errors = [e for e in result["errors"] if e["tip"] == "ogun_mantik"]
        assert len(logic_errors) > 0

    def test_single_starchy_ok(self):
        """Tek nişastalı besin hata vermemeli."""
        ogunler = [
            make_ogun("ogle", [
                make_besin("Tavuk göğsü", 200, 62, 7, 0, 0),
                make_besin("Pirinç pilavı", 150, 4, 0.5, 42, 0.6),
                make_besin("Brokoli", 150, 3.6, 0.6, 10.8, 5),
            ]),
        ]
        plan = make_plan(ogunler)
        result = validate_plan(plan, DEFAULT_USER)
        logic_errors = [e for e in result["errors"] if e["tip"] == "ogun_mantik"]
        assert len(logic_errors) == 0


# ==========================================
# VALİDASYON TESTLERİ — SAĞLIK KURALLARI
# ==========================================

class TestHealthRules:
    def test_gallbladder_fat_limit(self):
        """Safra hastası — günlük yağ 40g üstüyse hata vermeli (Cochrane: 25-40g/gün)."""
        user = {**DEFAULT_USER, "kronik_hastaliklar": ["safra kesesi"]}
        ogunler = [
            make_ogun("kahvalti", [make_besin("Yağlı yemek", 200, 20, 12, 30, 2)]),
            make_ogun("ogle", [make_besin("Yağlı yemek 2", 200, 25, 12, 40, 3)]),
            make_ogun("aksam", [make_besin("Yağlı yemek 3", 200, 20, 12, 35, 2)]),
            make_ogun("ara_ogun_1", [make_besin("Ara öğün", 100, 5, 10, 20, 1)]),
        ]
        plan = make_plan(ogunler)
        result = validate_plan(plan, user)
        health_errors = [e for e in result["errors"] if e["tip"] == "saglik_kural"]
        assert len(health_errors) > 0

    def test_gallbladder_per_meal_fat(self):
        """Safra hastası — öğün başına 12g üstü yağ hata vermeli (klinik rehber)."""
        user = {**DEFAULT_USER, "kronik_hastaliklar": ["safra"]}
        ogunler = [
            make_ogun("kahvalti", [make_besin("Çok yağlı", 100, 10, 18, 20, 1)]),
        ]
        plan = make_plan(ogunler)
        result = validate_plan(plan, user)
        health_errors = [e for e in result["errors"] if e["tip"] == "saglik_kural"]
        assert any("öğün" in e["mesaj"] for e in health_errors)

    def test_protein_upper_limit(self):
        """Protein LBM × 2.2 üstüyse hata vermeli."""
        user = {**DEFAULT_USER, "yagsiz_kutle_kg": 60}  # Max ~132g
        ogunler = [
            make_ogun("kahvalti", [make_besin("Protein fazla", 300, 50, 5, 30, 2)]),
            make_ogun("ogle", [make_besin("Protein fazla 2", 300, 55, 5, 30, 2)]),
            make_ogun("aksam", [make_besin("Protein fazla 3", 300, 50, 5, 30, 2)]),
        ]
        plan = make_plan(ogunler)
        result = validate_plan(plan, user)
        protein_errors = [e for e in result["errors"] if e["tip"] == "protein_asiri"]
        assert len(protein_errors) > 0


# ==========================================
# VALİDASYON TESTLERİ — GÜN TOPLAMI
# ==========================================

class TestDailyTotal:
    def test_total_exceeds_target(self):
        """Günlük toplam hedeften çok sapınca hata vermeli."""
        hedef = {"kalori": 2000, "protein": 130, "yag": 60, "karb": 250, "lif": 30}
        ogunler = [
            make_ogun("kahvalti", [make_besin("Çok kalori", 500, 50, 30, 80, 5)]),
            make_ogun("ogle", [make_besin("Çok kalori 2", 500, 50, 30, 80, 5)]),
            make_ogun("aksam", [make_besin("Çok kalori 3", 500, 50, 30, 80, 5)]),
        ]
        plan = make_plan(ogunler, hedef=hedef)
        result = validate_plan(plan, DEFAULT_USER)
        total_errors = [e for e in result["errors"] if e["tip"] == "gun_toplam"]
        assert len(total_errors) > 0


# ==========================================
# FEEDBACK FORMAT TESTİ
# ==========================================

class TestFeedback:
    def test_feedback_format(self):
        """Feedback formatı doğru oluşturulmalı."""
        result = {
            "valid": False,
            "errors": [{"tip": "test", "mesaj": "Test hatası", "ogun": None, "besin": None, "duzeltme": "Düzelt"}],
            "warnings": [{"tip": "test", "mesaj": "Test uyarısı"}],
            "corrected_totals": {"kalori": 2000, "protein": 130, "yag": 60, "karb": 250, "lif": 30},
        }
        feedback = format_validation_feedback(result)
        assert "HATA" in feedback
        assert "Test hatası" in feedback
        assert "Test uyarısı" in feedback
        assert "Düzelt" in feedback

    def test_no_feedback_when_valid(self):
        """Geçerli plan için feedback boş olmalı."""
        result = {"valid": True, "errors": [], "warnings": [], "corrected_totals": None}
        feedback = format_validation_feedback(result)
        assert feedback == ""


# ==========================================
# ARDIŞIK GÜN KONTROLÜ
# ==========================================

class TestConsecutiveDays:
    def test_consecutive_day_protein_warning(self):
        """Ardışık günlerde aynı protein kaynağı uyarı vermeli."""
        previous_plan = {
            "ogunler": [
                make_ogun("ogle", [make_besin("Tavuk göğsü", 200, 62, 7, 0, 0)]),
                make_ogun("aksam", [make_besin("Somon", 180, 36, 23, 0, 0)]),
            ]
        }
        ogunler = [
            make_ogun("ogle", [
                make_besin("Tavuk göğsü", 200, 62, 7, 0, 0),  # Dün de öğle tavuktu
                make_besin("Bulgur pilavı", 150, 4.5, 0.3, 28, 6.8),
            ]),
            make_ogun("aksam", [
                make_besin("Dana bonfile", 180, 50, 20, 0, 0),
                make_besin("Patates", 200, 3.8, 0.2, 40, 3.6),
            ]),
        ]
        plan = make_plan(ogunler)
        result = validate_plan(plan, DEFAULT_USER, previous_plan)
        day_warnings = [w for w in result["warnings"] if w["tip"] == "ardisik_gun_tekrar"]
        assert len(day_warnings) > 0
        assert "tavuk" in day_warnings[0]["mesaj"].lower()


# ==========================================
# KULLANICI PROFİL HEDEFİ KONTROL TESTLERİ
# ==========================================

class TestProfileTargetValidation:
    def test_protein_exceeds_profile_target(self):
        """Protein kullanıcı profil hedefinden fazlaysa hata vermeli."""
        user = {**DEFAULT_USER, "protein_g": 132, "hedef_kalori": 2656, "karbonhidrat_g": 386, "yag_g": 65}
        ogunler = [
            make_ogun("kahvalti", [make_besin("Yüksek protein", 200, 55, 10, 40, 3)]),
            make_ogun("ogle", [make_besin("Yüksek protein 2", 200, 55, 10, 40, 3)]),
            make_ogun("aksam", [make_besin("Yüksek protein 3", 200, 55, 10, 40, 3)]),
        ]
        plan = make_plan(ogunler, hedef={"kalori": 2656, "protein": 132, "yag": 65, "karb": 386, "lif": 37})
        result = validate_plan(plan, user)
        # Protein 165g vs hedef 132g → +33g sapma
        profil_errors = [e for e in result["errors"] if e["tip"] == "profil_hedef_sapma" and "protein" in e["mesaj"]]
        assert len(profil_errors) > 0

    def test_carb_below_profile_target(self):
        """Karbonhidrat profil hedefinden çok düşükse hata vermeli."""
        user = {**DEFAULT_USER, "protein_g": 132, "hedef_kalori": 2656, "karbonhidrat_g": 386, "yag_g": 65}
        ogunler = [
            make_ogun("kahvalti", [make_besin("Düşük karb", 200, 30, 15, 50, 3)]),
            make_ogun("ogle", [make_besin("Düşük karb 2", 200, 30, 15, 50, 3)]),
            make_ogun("aksam", [make_besin("Düşük karb 3", 200, 30, 15, 50, 3)]),
        ]
        plan = make_plan(ogunler, hedef={"kalori": 2656, "protein": 132, "yag": 65, "karb": 386, "lif": 37})
        result = validate_plan(plan, user)
        # Karb 150g vs hedef 386g → -236g sapma
        profil_errors = [e for e in result["errors"] if e["tip"] == "profil_hedef_sapma" and "karb" in e["mesaj"]]
        assert len(profil_errors) > 0

    def test_plan_matching_profile_passes(self):
        """Profil hedeflerine uyan plan hata vermemeli."""
        user = {**DEFAULT_USER, "protein_g": 130, "hedef_kalori": 2500, "karbonhidrat_g": 350, "yag_g": 65}
        ogunler = [
            make_ogun("kahvalti", [make_besin("Dengeli 1", 200, 43, 22, 117, 5)]),
            make_ogun("ogle", [make_besin("Dengeli 2", 300, 44, 22, 117, 5)]),
            make_ogun("aksam", [make_besin("Dengeli 3", 300, 43, 21, 116, 5)]),
        ]
        plan = make_plan(ogunler, hedef={"kalori": 2500, "protein": 130, "yag": 65, "karb": 350, "lif": 30})
        result = validate_plan(plan, user)
        profil_errors = [e for e in result["errors"] if e["tip"] == "profil_hedef_sapma"]
        assert len(profil_errors) == 0


# ==========================================
# BESİN DEĞERİ CROSS-CHECK TESTLERİ
# ==========================================

class TestFoodDatabaseCrossCheck:
    def test_find_food_exact_match(self):
        """Tam eşleşme bulunmalı."""
        result = _find_food_in_db("tavuk göğsü")
        assert result is not None
        assert result["protein"] == 31

    def test_find_food_partial_match(self):
        """Kısmi eşleşme bulunmalı."""
        result = _find_food_in_db("ızgara tavuk göğsü")
        assert result is not None
        assert result["protein"] == 31

    def test_find_food_no_match(self):
        """Eşleşme yoksa None dönmeli."""
        result = _find_food_in_db("bilinmeyen bir yemek xyz")
        assert result is None

    def test_carb_per_kg_upper_bound(self):
        """Karbonhidrat 5 g/kg üstüyse hata vermeli (ACSM 2016)."""
        user = {**DEFAULT_USER, "kilo_kg": 80}
        ogunler = [
            make_ogun("kahvalti", [make_besin("Yüksek karb 1", 300, 20, 10, 150, 5)]),
            make_ogun("ogle", [make_besin("Yüksek karb 2", 300, 30, 10, 150, 5)]),
            make_ogun("aksam", [make_besin("Yüksek karb 3", 300, 20, 10, 150, 5)]),
        ]
        plan = make_plan(ogunler)
        result = validate_plan(plan, user)
        # 450g karb / 80kg = 5.6 g/kg > 5 g/kg limit
        karb_errors = [e for e in result["errors"] if e["tip"] == "karb_asiri"]
        assert len(karb_errors) > 0

    def test_fat_too_low_flagged(self):
        """Yağ %18 altıysa hata vermeli (EFSA/ACSM)."""
        user = {**DEFAULT_USER, "hedef_kalori": 2500}
        ogunler = [
            # Toplam yağ = 15g → %5.4 kalori → çok düşük
            make_ogun("kahvalti", [make_besin("Düşük yağ 1", 200, 40, 5, 100, 5)]),
            make_ogun("ogle", [make_besin("Düşük yağ 2", 300, 40, 5, 100, 5)]),
            make_ogun("aksam", [make_besin("Düşük yağ 3", 300, 40, 5, 100, 5)]),
        ]
        plan = make_plan(ogunler, hedef={"kalori": 2500, "protein": 120, "yag": 15, "karb": 300, "lif": 30})
        result = validate_plan(plan, user)
        fat_errors = [e for e in result["errors"] if e["tip"] == "yag_yetersiz"]
        assert len(fat_errors) > 0

    def test_wildly_wrong_macro_flagged(self):
        """Besin DB'den çok sapan makro değerleri HATA vermeli (sıkı kontrol)."""
        user = {**DEFAULT_USER}
        ogunler = [
            make_ogun("ogle", [{
                "ad": "Tavuk göğsü",
                "gram": 200,
                "protein": 62,  # Doğru: 31g/100g × 2 = 62g ✓
                "yag": 7.2,     # Doğru: 3.6g/100g × 2 = 7.2g ✓
                "karb": 0,
                "lif": 0,
                "kalori": round((62*4)+(7.2*9)+(0*4)),
            }, {
                "ad": "Pirinç pilavı",
                "gram": 150,
                "protein": 15,  # Yanlış! Doğrusu: 2.7g/100g × 1.5 = 4.05g
                "yag": 0.5,
                "karb": 42,
                "lif": 0.6,
                "kalori": round((15*4)+(0.5*9)+(42*4)),
            }]),
        ]
        plan = make_plan(ogunler)
        result = validate_plan(plan, user)
        # Artık sıkı kontrol: DB sapmaları error olarak döner
        db_errors = [e for e in result["errors"] if e["tip"] == "besin_deger_sapma" and "pirinç" in e["mesaj"].lower()]
        assert len(db_errors) > 0
        assert not result["valid"]  # Plan reddedilmeli
