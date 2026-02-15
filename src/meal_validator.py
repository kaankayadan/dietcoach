"""
Birleşik Yemek Planı Doğrulayıcı — macro_validator + food_database cross-check.

İş akışı:
1. Claude'un JSON planını parse et
2. Her besini food_database ile cross-check yap (gram varsa)
   → Yanlış değerleri otomatik düzelt (2. API çağrısı yok)
3. Öğün ve günlük toplamları yeniden hesapla
4. Kullanıcı hedefleriyle karşılaştır
5. Protein dağıtım/tekrar, nişastalı çakışma, sağlık kuralları kontrol et
6. Düzeltilmiş planı döndür
"""
import re
import json
import logging
from typing import Optional

from src.food_database import BESIN_DB, STARCHY_FOODS, PROTEIN_SOURCES

logger = logging.getLogger(__name__)

# ── Toleranslar ──────────────────────────────────────────────
TOLERANCE_PCT = 0.05          # Toplam doğrulama: ±%5
TOLERANCE_MIN = 3             # Küçük değerler için minimum 3 birim
FOOD_KCAL_TOLERANCE_PCT = 0.15
FOOD_KCAL_TOLERANCE_MIN = 15

# food_database cross-check
DB_MAKRO_TOLERANS = 3         # gram sapma (100g başına)
DB_KCAL_TOLERANS = 20         # kcal sapma (100g başına)

# Hedef sapma
KALORI_HEDEF_TOLERANS = 75    # kcal
MAKRO_HEDEF_TOLERANS = 15     # gram


# ── Yardımcı Fonksiyonlar ───────────────────────────────────

def _within_tolerance(calculated: float, stated: float) -> bool:
    """±%5 tolerans içinde mi?"""
    if calculated == 0 and stated == 0:
        return True
    threshold = max(abs(calculated) * TOLERANCE_PCT, TOLERANCE_MIN)
    return abs(calculated - stated) <= threshold


def _calc_kcal(p: float, y: float, k: float) -> float:
    return round(p * 4 + y * 9 + k * 4, 1)


def _find_food_in_db(ad: str) -> Optional[tuple]:
    """Besin adını food_database'de ara. Eşleşen (key, entry) döndür."""
    ad_lower = ad.lower().strip()

    # Parantez içini temizle: "Yumurta (2 adet, orta boy)" → "yumurta"
    ad_clean = re.sub(r'\(.*?\)', '', ad_lower).strip()

    # Gram/miktar bilgisini temizle: "tavuk göğsü 150g" → "tavuk göğsü"
    ad_clean = re.sub(r'\d+\s*g\b', '', ad_clean).strip()

    # 1. Tam eşleşme
    if ad_clean in BESIN_DB:
        return ad_clean, BESIN_DB[ad_clean]

    # 2. DB key besin adında geçiyor mu?
    best_match = None
    best_len = 0
    for db_key, db_val in BESIN_DB.items():
        if db_key in ad_clean or ad_clean in db_key:
            # En uzun eşleşmeyi tercih et (daha spesifik)
            if len(db_key) > best_len:
                best_match = (db_key, db_val)
                best_len = len(db_key)

    return best_match


# ── JSON Parse / Strip ──────────────────────────────────────

def extract_mealplan_json(response: str) -> Optional[dict]:
    """Claude yanıtından <!--MEALPLAN_JSON:{...}--> bloğunu çıkar."""
    pattern = r'<!--MEALPLAN_JSON:(.*?)-->'
    match = re.search(pattern, response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError as e:
            logger.warning(f"MEALPLAN_JSON parse hatası: {e}")
            return None
    return None


def strip_mealplan_json(response: str) -> str:
    """Yanıttan gizli JSON bloğunu temizle."""
    cleaned = re.sub(r'<!--MEALPLAN_JSON:.*?-->', '', response, flags=re.DOTALL)
    cleaned = re.sub(r'<!--MEALPLAN_JSON:.*$', '', cleaned, flags=re.DOTALL)
    return cleaned.strip()


# ── Ana Doğrulama ────────────────────────────────────────────

def validate_plan(plan_json: dict, user: dict, previous_plan: dict = None) -> dict:
    """
    Plan JSON'ını kapsamlı doğrula ve otomatik düzelt.

    Args:
        plan_json: Claude'un ürettiği plan (p/y/k/l/kcal format)
        user: Kullanıcı profil dict'i (hedef_kalori, protein_g, vs.)
        previous_plan: Önceki günün planı (protein tekrar kontrolü)

    Returns:
        {
            "valid": bool,
            "errors": [str],
            "warnings": [str],
            "corrected_plan": {"ogunler": [...], "gunluk_toplam": {...}},
            "corrected_totals": {...},
            "db_corrections": [str]   # food_database'den yapılan düzeltmeler
        }
    """
    errors = []
    warnings = []
    db_corrections = []

    ogunler = plan_json.get("ogunler", [])
    if not ogunler:
        return {
            "valid": False,
            "errors": ["Plan öğün içermiyor"],
            "warnings": [],
            "corrected_plan": None,
            "corrected_totals": None,
            "db_corrections": [],
        }

    corrected_ogunler = []
    gunluk_p = 0
    gunluk_y = 0
    gunluk_k = 0
    gunluk_l = 0
    gunluk_kcal = 0

    for ogun in ogunler:
        besinler = ogun.get("besinler", [])
        ogun_adi = ogun.get("ogun", "?")
        corrected_besinler = []

        ogun_p = 0
        ogun_y = 0
        ogun_k = 0
        ogun_l = 0
        ogun_kcal = 0

        for besin in besinler:
            ad = besin.get("ad", "?")
            gram = besin.get("gram", 0)
            b_p = besin.get("p", 0)
            b_y = besin.get("y", 0)
            b_k = besin.get("k", 0)
            b_l = besin.get("l", 0)
            b_kcal = besin.get("kcal", 0)

            # ── food_database cross-check ──
            db_match = _find_food_in_db(ad)

            if db_match and gram > 0:
                db_key, db_entry = db_match
                carpan = gram / 100.0

                db_p = round(db_entry["protein"] * carpan, 1)
                db_y = round(db_entry["yag"] * carpan, 1)
                db_k = round(db_entry["karb"] * carpan, 1)
                db_l = round(db_entry.get("lif", 0) * carpan, 1)
                db_kcal = round(db_entry["kalori"] * carpan, 0)

                # Sapma var mı?
                corrections_made = []
                tolerans_carpan = max(carpan, 0.5)  # min 50g tolerans tabanı

                if abs(b_p - db_p) > DB_MAKRO_TOLERANS * tolerans_carpan:
                    corrections_made.append(f"P: {b_p}→{db_p}g")
                    b_p = db_p
                if abs(b_y - db_y) > DB_MAKRO_TOLERANS * tolerans_carpan:
                    corrections_made.append(f"Y: {b_y}→{db_y}g")
                    b_y = db_y
                if abs(b_k - db_k) > DB_MAKRO_TOLERANS * tolerans_carpan:
                    corrections_made.append(f"K: {b_k}→{db_k}g")
                    b_k = db_k
                if abs(b_l - db_l) > DB_MAKRO_TOLERANS * tolerans_carpan:
                    b_l = db_l
                if abs(b_kcal - db_kcal) > DB_KCAL_TOLERANS * tolerans_carpan:
                    corrections_made.append(f"kcal: {b_kcal}→{db_kcal}")
                    b_kcal = db_kcal

                if corrections_made:
                    correction_msg = f"{ad} ({gram}g) → DB ({db_key}): {', '.join(corrections_made)}"
                    db_corrections.append(correction_msg)
                    logger.info(f"food_database düzeltme: {correction_msg}")

            elif not db_match and gram > 0:
                # DB'de yok — Claude değerine güveniyoruz ama logluyoruz
                logger.debug(f"food_database'de bulunamadı: {ad}")

            # ── Makro→kcal tutarlılık kontrolü ──
            expected_kcal = _calc_kcal(b_p, b_y, b_k)
            if abs(expected_kcal - b_kcal) > max(b_kcal * FOOD_KCAL_TOLERANCE_PCT, FOOD_KCAL_TOLERANCE_MIN):
                errors.append(
                    f"{ogun_adi}/{ad}: makro→kcal uyumsuz "
                    f"(yazılan {b_kcal} vs hesaplanan {expected_kcal})"
                )

            corrected_besin = {
                "ad": ad,
                "p": b_p,
                "y": b_y,
                "k": b_k,
                "l": b_l,
                "kcal": b_kcal,
            }
            if gram > 0:
                corrected_besin["gram"] = gram
            corrected_besinler.append(corrected_besin)

            ogun_p += b_p
            ogun_y += b_y
            ogun_k += b_k
            ogun_l += b_l
            ogun_kcal += b_kcal

        # ── Öğün toplam doğrulama ──
        stated = ogun.get("toplam", {})
        diffs = []
        if not _within_tolerance(ogun_p, stated.get("p", 0)):
            diffs.append(f"P: {stated.get('p', 0)}→{ogun_p:.1f}")
        if not _within_tolerance(ogun_y, stated.get("y", 0)):
            diffs.append(f"Y: {stated.get('y', 0)}→{ogun_y:.1f}")
        if not _within_tolerance(ogun_k, stated.get("k", 0)):
            diffs.append(f"K: {stated.get('k', 0)}→{ogun_k:.1f}")
        if not _within_tolerance(ogun_kcal, stated.get("kcal", 0)):
            diffs.append(f"kcal: {stated.get('kcal', 0)}→{ogun_kcal:.1f}")
        if diffs:
            errors.append(f"{ogun_adi} toplam hatası: {', '.join(diffs)}")

        # ── Protein dağıtım kontrolü ──
        ana_ogunler = ["kahvaltı", "öğle", "akşam"]
        if ogun_adi.lower() in ana_ogunler:
            if ogun_p < 20:
                warnings.append(
                    f"{ogun_adi} öğününde protein düşük: {ogun_p:.0f}g (min 25g önerilen)"
                )
            elif ogun_p > 50:
                warnings.append(
                    f"{ogun_adi} öğününde protein yüksek: {ogun_p:.0f}g (max 45g önerilen)"
                )

        # ── Nişastalı besin çakışması ──
        starchy_in_meal = []
        for besin in corrected_besinler:
            ad_lower = besin["ad"].lower()
            for starchy in STARCHY_FOODS:
                if starchy in ad_lower:
                    starchy_in_meal.append(starchy)
                    break
        if len(starchy_in_meal) >= 2:
            warnings.append(
                f"{ogun_adi} öğününde birden fazla nişastalı besin: {', '.join(starchy_in_meal)}"
            )

        # Düzeltilmiş öğün
        corrected_ogun = {
            **ogun,
            "besinler": corrected_besinler,
            "toplam": {
                "p": round(ogun_p, 1),
                "y": round(ogun_y, 1),
                "k": round(ogun_k, 1),
                "l": round(ogun_l, 1),
                "kcal": round(ogun_kcal, 1),
            }
        }
        corrected_ogunler.append(corrected_ogun)

        gunluk_p += ogun_p
        gunluk_y += ogun_y
        gunluk_k += ogun_k
        gunluk_l += ogun_l
        gunluk_kcal += ogun_kcal

    # ── Günlük toplam doğrulama ──
    stated_gunluk = plan_json.get("gunluk_toplam", {})
    daily_diffs = []
    if not _within_tolerance(gunluk_p, stated_gunluk.get("p", 0)):
        daily_diffs.append(f"P: {stated_gunluk.get('p', 0)}→{gunluk_p:.1f}")
    if not _within_tolerance(gunluk_y, stated_gunluk.get("y", 0)):
        daily_diffs.append(f"Y: {stated_gunluk.get('y', 0)}→{gunluk_y:.1f}")
    if not _within_tolerance(gunluk_k, stated_gunluk.get("k", 0)):
        daily_diffs.append(f"K: {stated_gunluk.get('k', 0)}→{gunluk_k:.1f}")
    if not _within_tolerance(gunluk_kcal, stated_gunluk.get("kcal", 0)):
        daily_diffs.append(f"kcal: {stated_gunluk.get('kcal', 0)}→{gunluk_kcal:.1f}")
    if daily_diffs:
        errors.append(f"Günlük toplam hatası: {', '.join(daily_diffs)}")

    corrected_totals = {
        "p": round(gunluk_p, 1),
        "y": round(gunluk_y, 1),
        "k": round(gunluk_k, 1),
        "l": round(gunluk_l, 1),
        "kcal": round(gunluk_kcal, 1),
    }

    # ── Kullanıcı hedefleriyle karşılaştır ──
    if user:
        hedef_kcal = user.get("hedef_kalori")
        hedef_p = user.get("protein_g")
        hedef_y = user.get("yag_g")
        hedef_k = user.get("karbonhidrat_g")
        hedef_l = user.get("lif_g")

        if hedef_kcal and abs(gunluk_kcal - hedef_kcal) > KALORI_HEDEF_TOLERANS:
            fark = gunluk_kcal - hedef_kcal
            yuksek_dusuk = "yüksek" if fark > 0 else "düşük"
            errors.append(
                f"Günlük kalori hedeften {yuksek_dusuk}: "
                f"{gunluk_kcal:.0f} vs hedef {hedef_kcal} kcal (fark: {fark:+.0f})"
            )
        if hedef_p and abs(gunluk_p - hedef_p) > MAKRO_HEDEF_TOLERANS:
            errors.append(
                f"Günlük protein hedeften sapma: {gunluk_p:.0f}g vs hedef {hedef_p}g"
            )
        if hedef_y and abs(gunluk_y - hedef_y) > MAKRO_HEDEF_TOLERANS:
            errors.append(
                f"Günlük yağ hedeften sapma: {gunluk_y:.0f}g vs hedef {hedef_y}g"
            )
        if hedef_l and gunluk_l < hedef_l * 0.7:
            warnings.append(
                f"Lif yetersiz: {gunluk_l:.0f}g (hedef: {hedef_l}g)"
            )

        # ── Protein tekrar kontrolü (aynı gün: öğle vs akşam) ──
        ogun_proteinleri = {}
        for ogun in corrected_ogunler:
            ogun_tip = ogun.get("ogun", "").lower()
            if ogun_tip not in ("öğle", "akşam", "ogle", "aksam"):
                continue
            for besin in ogun.get("besinler", []):
                ad_lower = besin["ad"].lower()
                for kaynak_ad, kaynak_grup in PROTEIN_SOURCES.items():
                    if kaynak_ad in ad_lower:
                        ogun_proteinleri.setdefault(ogun_tip, set()).add(kaynak_grup)
                        break

        ogle_prot = ogun_proteinleri.get("öğle", set()) | ogun_proteinleri.get("ogle", set())
        aksam_prot = ogun_proteinleri.get("akşam", set()) | ogun_proteinleri.get("aksam", set())
        tekrar = ogle_prot & aksam_prot
        if tekrar:
            warnings.append(
                f"Öğle ve akşam aynı protein kaynağı: {', '.join(tekrar)}"
            )

        # ── Ardışık gün protein tekrarı ──
        if previous_plan:
            prev_proteins = set()
            for ogun in previous_plan.get("ogunler", []):
                for besin in ogun.get("besinler", []):
                    ad_lower = besin.get("ad", "").lower()
                    for kaynak_ad, kaynak_grup in PROTEIN_SOURCES.items():
                        if kaynak_ad in ad_lower:
                            prev_proteins.add(kaynak_grup)
                            break
            current_proteins = ogle_prot | aksam_prot
            ardisik_tekrar = prev_proteins & current_proteins
            if ardisik_tekrar:
                warnings.append(
                    f"Dünkü planla aynı protein: {', '.join(ardisik_tekrar)}"
                )

        # ── Sağlık kuralları ──
        hastaliklar = user.get("kronik_hastaliklar") or []
        hastalik_str = str(hastaliklar).lower()

        # Safra
        if "safra" in hastalik_str:
            if gunluk_y > 40:
                errors.append(
                    f"Safra hastası — günlük yağ {gunluk_y:.0f}g (limit: 40g)"
                )
            for ogun in corrected_ogunler:
                ogun_yag = ogun["toplam"]["y"]
                if ogun_yag > 12:
                    errors.append(
                        f"Safra hastası — {ogun.get('ogun', '?')} yağ {ogun_yag:.0f}g (limit: 12g/öğün)"
                    )

        # Diyabet
        if "diyabet" in hastalik_str and hedef_kcal and hedef_kcal > 0:
            karb_orani = (gunluk_k * 4) / hedef_kcal * 100
            if karb_orani > 42:
                warnings.append(
                    f"Diyabet — karb oranı %{karb_orani:.0f} (ADA önerisi: ≤%40)"
                )

        # Protein üst sınır
        yagsiz_kutle = user.get("yagsiz_kutle_kg", 0)
        if yagsiz_kutle and gunluk_p > float(yagsiz_kutle) * 2.2:
            errors.append(
                f"Protein aşırı: {gunluk_p:.0f}g (ISSN üst sınır: LBM×2.2 = {float(yagsiz_kutle)*2.2:.0f}g)"
            )

        # Yağ alt sınır (%20 minimum)
        if hedef_kcal and hedef_kcal > 0 and "safra" not in hastalik_str:
            yag_orani = (gunluk_y * 9) / hedef_kcal * 100
            if yag_orani < 18:
                errors.append(
                    f"Yağ oranı çok düşük: %{yag_orani:.0f} (minimum: %20)"
                )

    corrected_plan = {
        "ogunler": corrected_ogunler,
        "gunluk_toplam": corrected_totals,
    }

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "corrected_plan": corrected_plan,
        "corrected_totals": corrected_totals,
        "db_corrections": db_corrections,
    }


# ── Özet ve Patch ────────────────────────────────────────────

def build_correction_summary(result: dict) -> str:
    """Doğrulama sonucunu okunabilir Türkçe özete çevir."""
    lines = []

    if result["db_corrections"]:
        lines.append("Besin değeri düzeltmeleri (food_database):")
        for c in result["db_corrections"]:
            lines.append(f"  - {c}")

    if result["errors"]:
        lines.append("Aritmetik/hedef düzeltmeleri:")
        for e in result["errors"]:
            lines.append(f"  - {e}")

    if result["warnings"]:
        lines.append("\nUyarılar:")
        for w in result["warnings"]:
            lines.append(f"  - {w}")

    t = result["corrected_totals"]
    lines.append(f"\nDoğrulanmış Günlük Toplam:")
    lines.append(
        f"Kalori: {t['kcal']:.0f} kcal | P: {t['p']:.0f}g | "
        f"Y: {t['y']:.0f}g | K: {t['k']:.0f}g | L: {t['l']:.0f}g"
    )

    return "\n".join(lines)


def patch_response_totals(response_text: str, corrected_plan: dict) -> str:
    """
    Claude'un yanıtındaki öğün ve günlük toplamları Python'un hesapladığı
    doğru değerlerle değiştir. 2. API çağrısı yapmadan düzeltme.
    """
    text = response_text

    # Her öğün için toplamı düzelt
    for ogun in corrected_plan.get("ogunler", []):
        t = ogun["toplam"]
        pattern = (
            r'(\*\*Öğün toplamı?\s*→\s*)'
            r'P:\s*[\d.]+g\s*\|\s*Y:\s*[\d.]+g\s*\|\s*K:\s*[\d.]+g\s*\|\s*L:\s*[\d.]+g\s*\|\s*[\d.]+ kcal\*\*'
        )
        replacement = (
            f'**Öğün toplamı → '
            f'P: {t["p"]:.1f}g | Y: {t["y"]:.1f}g | K: {t["k"]:.1f}g | L: {t["l"]:.1f}g | {t["kcal"]:.0f} kcal**'
        )
        text = re.sub(pattern, replacement, text, count=1)

    # Günlük toplam bölümünü düzelt
    gt = corrected_plan.get("gunluk_toplam", {})
    text = re.sub(r'(\*\*Kalori:\*\*)\s*[\d.,]+ kcal', f'**Kalori:** {gt["kcal"]:.0f} kcal', text)
    text = re.sub(r'(\*\*Protein:\*\*)\s*[\d.,]+g', f'**Protein:** {gt["p"]:.1f}g', text)
    text = re.sub(r'(\*\*Yağ:\*\*)\s*[\d.,]+g', f'**Yağ:** {gt["y"]:.1f}g', text)
    text = re.sub(r'(\*\*Karb:\*\*)\s*[\d.,]+g', f'**Karb:** {gt["k"]:.1f}g', text)
    text = re.sub(r'(\*\*Lif:\*\*)\s*[\d.,]+g', f'**Lif:** {gt["l"]:.1f}g', text)

    return text
