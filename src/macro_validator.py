"""
Makro Doğrulayıcı — Claude'un yemek planlarındaki aritmetik hatalarını yakalar ve düzeltir.

Claude plan üretirken gizli bir JSON bloğu ekler:
<!--MEALPLAN_JSON:{...}-->

Bu modül:
1. JSON'ı parse eder
2. Öğün başı toplamları doğrular (±%5 tolerans)
3. Günlük toplamları doğrular
4. Kullanıcının makro hedeflerine uyumu kontrol eder
5. Hata varsa Python tarafında düzeltir (2. API çağrısı yapmadan)
"""
import re
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ±%5 tolerans, minimum 3g/kcal (küçük değerler için)
TOLERANCE_PCT = 0.05
TOLERANCE_MIN = 3

# Besin bazında makro→kcal tutarlılık toleransı (%15 veya 15 kcal)
FOOD_KCAL_TOLERANCE_PCT = 0.15
FOOD_KCAL_TOLERANCE_MIN = 15


def _within_tolerance(calculated: float, stated: float) -> bool:
    """±%5 tolerans içinde mi? Küçük değerler için minimum 3 birim."""
    if calculated == 0 and stated == 0:
        return True
    threshold = max(abs(calculated) * TOLERANCE_PCT, TOLERANCE_MIN)
    return abs(calculated - stated) <= threshold


def _food_kcal_ok(calculated_kcal: float, stated_kcal: float) -> bool:
    """Besin bazında makro→kcal tutarlı mı? ±%15 veya 15 kcal."""
    if calculated_kcal == 0 and stated_kcal == 0:
        return True
    threshold = max(abs(calculated_kcal) * FOOD_KCAL_TOLERANCE_PCT, FOOD_KCAL_TOLERANCE_MIN)
    return abs(calculated_kcal - stated_kcal) <= threshold


def extract_mealplan_json(response: str) -> Optional[dict]:
    """Claude yanıtından gizli MEALPLAN_JSON bloğunu çıkar."""
    # Önce tam blok dene (açılış + kapanış)
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
    """Yanıttan gizli JSON bloğunu temizle — tam veya yarıda kalmış."""
    # Tam blok: <!--MEALPLAN_JSON:...-->
    cleaned = re.sub(r'<!--MEALPLAN_JSON:.*?-->', '', response, flags=re.DOTALL)
    # Yarıda kalmış blok: <!--MEALPLAN_JSON:... (kapanış --> yok)
    cleaned = re.sub(r'<!--MEALPLAN_JSON:.*$', '', cleaned, flags=re.DOTALL)
    return cleaned.strip()


def _calc_kcal(p: float, y: float, k: float) -> float:
    """Makrolardan kalori hesapla: protein 4, yağ 9, karb 4 kcal/g."""
    return round(p * 4 + y * 9 + k * 4, 1)


def validate_plan(plan_json: dict, user_targets: dict = None) -> dict:
    """
    Plan JSON'ını doğrula. ±%5 toleransla.

    Returns:
    {
        "valid": True/False,
        "errors": [...],         # Tolerans dışı hatalar (sadece loglama için)
        "warnings": [...],       # Hedef sapma uyarıları
        "corrected_plan": {...}, # Python'un hesapladığı doğru toplamlarla plan
        "corrected_totals": {...}
    }
    """
    errors = []
    warnings = []
    ogunler = plan_json.get("ogunler", [])

    corrected_ogunler = []
    gunluk_p = 0
    gunluk_y = 0
    gunluk_k = 0
    gunluk_l = 0
    gunluk_kcal = 0

    for ogun in ogunler:
        besinler = ogun.get("besinler", [])
        ogun_adi = ogun.get("ogun", "?")

        # Besinlerden toplamı hesapla
        calc_p = sum(b.get("p", 0) for b in besinler)
        calc_y = sum(b.get("y", 0) for b in besinler)
        calc_k = sum(b.get("k", 0) for b in besinler)
        calc_l = sum(b.get("l", 0) for b in besinler)
        calc_kcal = sum(b.get("kcal", 0) for b in besinler)

        # Claude'un yazdığı toplam
        stated = ogun.get("toplam", {})

        # ±%5 toleransla kontrol
        diffs = []
        if not _within_tolerance(calc_p, stated.get("p", 0)):
            diffs.append(f"P: {stated.get('p', 0)}→{calc_p:.1f}")
        if not _within_tolerance(calc_y, stated.get("y", 0)):
            diffs.append(f"Y: {stated.get('y', 0)}→{calc_y:.1f}")
        if not _within_tolerance(calc_k, stated.get("k", 0)):
            diffs.append(f"K: {stated.get('k', 0)}→{calc_k:.1f}")
        if not _within_tolerance(calc_kcal, stated.get("kcal", 0)):
            diffs.append(f"kcal: {stated.get('kcal', 0)}→{calc_kcal:.1f}")

        if diffs:
            errors.append(f"{ogun_adi} toplam hatası: {', '.join(diffs)}")

        # Besin bazında kalori doğrula (makro → kcal tutarlılığı)
        for b in besinler:
            expected_kcal = _calc_kcal(b.get("p", 0), b.get("y", 0), b.get("k", 0))
            if not _food_kcal_ok(expected_kcal, b.get("kcal", 0)):
                errors.append(
                    f"{ogun_adi}/{b.get('ad', '?')}: makro→kcal uyumsuz "
                    f"(yazılan {b.get('kcal')} vs hesaplanan {expected_kcal})"
                )

        # Düzeltilmiş öğün (her zaman Python hesaplı)
        corrected_ogun = {
            **ogun,
            "toplam": {
                "p": round(calc_p, 1),
                "y": round(calc_y, 1),
                "k": round(calc_k, 1),
                "l": round(calc_l, 1),
                "kcal": round(calc_kcal, 1),
            }
        }
        corrected_ogunler.append(corrected_ogun)

        gunluk_p += calc_p
        gunluk_y += calc_y
        gunluk_k += calc_k
        gunluk_l += calc_l
        gunluk_kcal += calc_kcal

    # Günlük toplam doğrulaması
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

    # Kullanıcı hedefleriyle karşılaştır
    if user_targets:
        hedef_p = user_targets.get("protein_g")
        hedef_y = user_targets.get("yag_g")
        hedef_k = user_targets.get("karbonhidrat_g")
        hedef_l = user_targets.get("lif_g")
        hedef_kcal = user_targets.get("hedef_kalori")

        if hedef_p and abs(gunluk_p - hedef_p) > hedef_p * 0.10:
            fark_p = gunluk_p - hedef_p
            warnings.append(f"Protein hedeften sapma: {gunluk_p:.0f}g vs hedef {hedef_p}g (fark: {fark_p:+.0f}g, %{abs(fark_p)/hedef_p*100:.0f})")
        if hedef_y and abs(gunluk_y - hedef_y) > hedef_y * 0.10:
            warnings.append(f"Yağ hedeften sapma: {gunluk_y:.0f}g vs hedef {hedef_y}g")
        if hedef_kcal and abs(gunluk_kcal - hedef_kcal) > hedef_kcal * 0.05:
            warnings.append(f"Kalori hedeften sapma: {gunluk_kcal:.0f} vs hedef {hedef_kcal} kcal")
        if hedef_l and gunluk_l < hedef_l * 0.8:
            warnings.append(f"Lif yetersiz: {gunluk_l:.0f}g vs min {hedef_l}g")

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
    }


def build_correction_summary(result: dict) -> str:
    """Doğrulama sonucunu okunabilir Türkçe özete çevir."""
    lines = []

    if result["errors"]:
        lines.append("Aritmetik düzeltmeler yapıldı:")
        for e in result["errors"]:
            lines.append(f"  - {e}")

    if result["warnings"]:
        lines.append("\nHedef uyarıları:")
        for w in result["warnings"]:
            lines.append(f"  - {w}")

    t = result["corrected_totals"]
    lines.append(f"\nDoğrulanmış Günlük Toplam:")
    lines.append(f"Kalori: {t['kcal']:.0f} kcal | P: {t['p']:.0f}g | Y: {t['y']:.0f}g | K: {t['k']:.0f}g | L: {t['l']:.0f}g")

    return "\n".join(lines)


def patch_response_totals(response_text: str, corrected_plan: dict) -> str:
    """
    Claude'un yanıtındaki öğün ve günlük toplamları Python'un hesapladığı
    doğru değerlerle değiştir. 2. API çağrısı yapmadan düzeltme.

    Strateji: "Öğün toplamı →" satırlarını ve "GÜNLÜK TOPLAM" bölümünü
    regex ile bulup Python değerleriyle değiştir.
    """
    text = response_text

    # Her öğün için toplamı düzelt
    for ogun in corrected_plan.get("ogunler", []):
        t = ogun["toplam"]
        ogun_adi = ogun.get("ogun", "")

        # "Öğün toplamı → P: XXg | Y: XXg | K: XXg | L: XXg | XXX kcal" formatını bul/değiştir
        # Farklı formatları yakala
        pattern = (
            r'(\*\*Öğün toplamı?\s*→\s*)'
            r'P:\s*[\d.]+g\s*\|\s*Y:\s*[\d.]+g\s*\|\s*K:\s*[\d.]+g\s*\|\s*L:\s*[\d.]+g\s*\|\s*[\d.]+ kcal\*\*'
        )
        replacement = (
            f'**Öğün toplamı → '
            f'P: {t["p"]:.1f}g | Y: {t["y"]:.1f}g | K: {t["k"]:.1f}g | L: {t["l"]:.1f}g | {t["kcal"]:.0f} kcal**'
        )
        # Sadece ilk eşleşmeyi değiştir (sırayla öğünlere uygulanacak)
        text = re.sub(pattern, replacement, text, count=1)

    # Günlük toplam bölümünü düzelt
    gt = corrected_plan.get("gunluk_toplam", {})

    # "Kalori: XXXX kcal" formatını değiştir
    text = re.sub(
        r'(\*\*Kalori:\*\*)\s*[\d.,]+ kcal',
        f'**Kalori:** {gt["kcal"]:.0f} kcal',
        text
    )
    # "Protein: XXXg" formatını değiştir
    text = re.sub(
        r'(\*\*Protein:\*\*)\s*[\d.,]+g',
        f'**Protein:** {gt["p"]:.1f}g',
        text
    )
    # "Yağ: XXg"
    text = re.sub(
        r'(\*\*Yağ:\*\*)\s*[\d.,]+g',
        f'**Yağ:** {gt["y"]:.1f}g',
        text
    )
    # "Karb: XXXg"
    text = re.sub(
        r'(\*\*Karb:\*\*)\s*[\d.,]+g',
        f'**Karb:** {gt["k"]:.1f}g',
        text
    )
    # "Lif: XXg"
    text = re.sub(
        r'(\*\*Lif:\*\*)\s*[\d.,]+g',
        f'**Lif:** {gt["l"]:.1f}g',
        text
    )

    return text
