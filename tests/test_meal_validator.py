"""
Meal Validator Unit Tests — Programatik validasyonun doğru çalıştığını test eder.
"""
import pytest
from src.meal_validator import (
    parse_plan_json, remove_plan_json, validate_plan, format_validation_feedback
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
        ogunler = [
            make_ogun("kahvalti", [
                make_besin("Yumurta", 120, 13, 11, 1, 0),
                make_besin("Tam buğday ekmek", 50, 5, 2, 24, 3.5),
                make_besin("Beyaz peynir", 30, 5, 6, 0, 0),
            ]),
            make_ogun("ogle", [
                make_besin("Tavuk göğsü", 200, 62, 7.2, 0, 0),
                make_besin("Pirinç pilavı", 150, 4, 0.5, 42, 0.6),
                make_besin("Salata", 150, 2, 5, 6, 3),
            ]),
            make_ogun("aksam", [
                make_besin("Somon", 180, 36, 23, 0, 0),
                make_besin("Kinoa", 120, 5, 2, 26, 3.4),
                make_besin("Brokoli", 150, 3.6, 0.6, 10.8, 5),
            ]),
        ]
        plan = make_plan(ogunler)
        result = validate_plan(plan, DEFAULT_USER)
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
        """Safra hastası — günlük yağ 50g üstüyse hata vermeli."""
        user = {**DEFAULT_USER, "kronik_hastaliklar": ["safra kesesi"]}
        ogunler = [
            make_ogun("kahvalti", [make_besin("Yağlı yemek", 200, 20, 20, 30, 2)]),
            make_ogun("ogle", [make_besin("Yağlı yemek 2", 200, 25, 20, 40, 3)]),
            make_ogun("aksam", [make_besin("Yağlı yemek 3", 200, 20, 15, 35, 2)]),
        ]
        plan = make_plan(ogunler)
        result = validate_plan(plan, user)
        health_errors = [e for e in result["errors"] if e["tip"] == "saglik_kural"]
        assert len(health_errors) > 0

    def test_gallbladder_per_meal_fat(self):
        """Safra hastası — öğün başına 15g üstü yağ hata vermeli."""
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
