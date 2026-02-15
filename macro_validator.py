"""
Makro Doğrulayıcı — Claude'un yemek planlarındaki aritmetik hatalarını yakalar ve düzeltir.

Claude plan üretirken gizli bir JSON bloğu ekler:
<!--MEALPLAN_JSON:{...}-->

Bu modül:
1. JSON'ı parse eder
2. Öğün başı toplamları doğrular
3. Günlük toplamları doğrular
4. Kullanıcının makro hedeflerine uyumu kontrol eder
5. Hata varsa düzeltilmiş metin üretir
"""
import re
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Kabul edilebilir yuvarlama toleransı (gram/kcal)
TOLERANCE = 3


def extract_mealplan_json(response: str) -> Optional[dict]:
    """Claude yanıtından gizli MEALPLAN_JSON bloğunu çıkar."""
    pattern = r'<!--MEALPLAN_JSON:(.*?)-->'
    match = re.search(pattern, response, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1).strip())
    except json.JSONDecodeError as e:
        logger.warning(f"MEALPLAN_JSON parse hatası: {e}")
        return None


def strip_mealplan_json(response: str) -> str:
    """Yanıttan gizli JSON bloğunu temizle (kullanıcıya gösterme)."""
    return re.sub(r'<!--MEALPLAN_JSON:.*?-->', '', response, flags=re.DOTALL).strip()


def _calc_kcal(p: float, y: float, k: float) -> float:
    """Makrolardan kalori hesapla: protein 4, yağ 9, karb 4 kcal/g."""
    return round(p * 4 + y * 9 + k * 4, 1)


def validate_plan(plan_json: dict, user_targets: dict = None) -> dict:
    """
    Plan JSON'ını doğrula.

    plan_json formatı:
    {
        "ogunler": [
            {
                "ogun": "kahvaltı",
                "saat": "07:30",
                "besinler": [
                    {"ad": "Yumurta (2 adet)", "p": 12, "y": 10, "k": 1.2, "l": 0, "kcal": 143},
                    ...
                ],
                "toplam": {"p": 26, "y": 22, "k": 66, "l": 6, "kcal": 579}
            },
            ...
        ],
        "gunluk_toplam": {"p": 135, "y": 40, "k": 500, "l": 30, "kcal": 3024}
    }

    user_targets formatı:
    {"protein_g": 132, "yag_g": 40, "karbonhidrat_g": 500, "lif_g": 30, "hedef_kalori": 3024}

    Returns:
    {
        "valid": True/False,
        "errors": [...],
        "warnings": [...],
        "corrected_plan": {...},  # düzeltilmiş plan
        "corrected_totals": {...}  # düzeltilmiş günlük toplam
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
        stated_p = stated.get("p", 0)
        stated_y = stated.get("y", 0)
        stated_k = stated.get("k", 0)
        stated_l = stated.get("l", 0)
        stated_kcal = stated.get("kcal", 0)

        # Farkları kontrol et
        diffs = []
        if abs(calc_p - stated_p) > TOLERANCE:
            diffs.append(f"P: {stated_p}→{calc_p:.1f}")
        if abs(calc_y - stated_y) > TOLERANCE:
            diffs.append(f"Y: {stated_y}→{calc_y:.1f}")
        if abs(calc_k - stated_k) > TOLERANCE:
            diffs.append(f"K: {stated_k}→{calc_k:.1f}")
        if abs(calc_kcal - stated_kcal) > TOLERANCE:
            diffs.append(f"kcal: {stated_kcal}→{calc_kcal:.1f}")

        if diffs:
            errors.append(f"{ogun_adi} toplam hatası: {', '.join(diffs)}")

        # Besin bazında kalori doğrula (makro → kcal tutarlılığı)
        for b in besinler:
            expected_kcal = _calc_kcal(b.get("p", 0), b.get("y", 0), b.get("k", 0))
            if abs(expected_kcal - b.get("kcal", 0)) > 15:
                errors.append(
                    f"{ogun_adi}/{b.get('ad', '?')}: makro→kcal uyumsuz "
                    f"(yazılan {b.get('kcal')} vs hesaplanan {expected_kcal})"
                )

        # Düzeltilmiş öğün
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
    if abs(gunluk_p - stated_gunluk.get("p", 0)) > TOLERANCE:
        daily_diffs.append(f"P: {stated_gunluk.get('p', 0)}→{gunluk_p:.1f}")
    if abs(gunluk_y - stated_gunluk.get("y", 0)) > TOLERANCE:
        daily_diffs.append(f"Y: {stated_gunluk.get('y', 0)}→{gunluk_y:.1f}")
    if abs(gunluk_k - stated_gunluk.get("k", 0)) > TOLERANCE:
        daily_diffs.append(f"K: {stated_gunluk.get('k', 0)}→{gunluk_k:.1f}")
    if abs(gunluk_kcal - stated_gunluk.get("kcal", 0)) > TOLERANCE:
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
            warnings.append(f"Protein hedeften sapma: {gunluk_p:.0f}g vs hedef {hedef_p}g")
        if hedef_y and abs(gunluk_y - hedef_y) > hedef_y * 0.15:
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
        lines.append("⚠️ Aritmetik düzeltmeler yapıldı:")
        for e in result["errors"]:
            lines.append(f"  • {e}")

    if result["warnings"]:
        lines.append("\n📊 Hedef uyarıları:")
        for w in result["warnings"]:
            lines.append(f"  • {w}")

    t = result["corrected_totals"]
    lines.append(f"\n✅ Doğrulanmış Günlük Toplam:")
    lines.append(f"Kalori: {t['kcal']:.0f} kcal | P: {t['p']:.0f}g | Y: {t['y']:.0f}g | K: {t['k']:.0f}g | L: {t['l']:.0f}g")

    return "\n".join(lines)


def format_corrected_plan(corrected_plan: dict) -> str:
    """Düzeltilmiş planı kullanıcıya gösterilecek formatta biçimlendir."""
    lines = []

    for ogun in corrected_plan["ogunler"]:
        t = ogun["toplam"]
        lines.append(f"\n🍽️ {ogun.get('ogun', '').upper()} ({ogun.get('saat', '')})")

        for b in ogun.get("besinler", []):
            lines.append(f"  • {b['ad']}  —  P:{b['p']}g Y:{b['y']}g K:{b['k']}g | {b['kcal']} kcal")

        lines.append(f"  → Öğün: P:{t['p']:.0f}g | Y:{t['y']:.0f}g | K:{t['k']:.0f}g | L:{t['l']:.0f}g | {t['kcal']:.0f} kcal")

    t = corrected_plan["gunluk_toplam"]
    lines.append(f"\n{'='*40}")
    lines.append(f"📊 GÜNLÜK TOPLAM")
    lines.append(f"Kalori: {t['kcal']:.0f} kcal")
    lines.append(f"Protein: {t['p']:.0f}g | Yağ: {t['y']:.0f}g | Karb: {t['k']:.0f}g | Lif: {t['l']:.0f}g")

    return "\n".join(lines)
