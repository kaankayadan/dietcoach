"""
Yemek Planı Validatörü — Claude'un ürettiği planları programatik olarak doğrular.
Kontroller:
1. Makro matematik: (P×4) + (Y×9) + (K×4) ≈ kcal?
2. Öğün toplamı = besinlerin toplamı mı?
3. Günlük toplam ≈ hedef? (±tolerans) — HEM plan JSON'daki hedef HEM kullanıcı profili hedefi
4. Protein eşit dağıtım kontrolü
5. Protein tekrarı kontrolü (aynı gün, ardışık günler)
6. Öğün mantığı (aynı öğünde 2+ nişastalı besin)
7. Sağlık kuralları (safra: yağ limiti vs.)
8. Besin değeri doğrulama — food_database ile cross-check
"""
import json
import re
import logging
from typing import Optional
from src.food_database import STARCHY_FOODS, PROTEIN_SOURCES, BESIN_DB

logger = logging.getLogger(__name__)

# Toleranslar
KALORI_TOLERANS_BESIN = 25      # Besin başına kcal toleransı
KALORI_TOLERANS_OGUN = 40       # Öğün toplamı toleransı
KALORI_TOLERANS_GUN = 75        # Günlük toplam vs hedef toleransı
MAKRO_TOLERANS_GUN = 15         # Günlük makro toleransı (gram)
MAKRO_TOLERANS_OGUN = 5         # Öğün içi toplama toleransı (gram)

# Besin değeri cross-check toleransları (100g başına)
BESIN_DEGER_TOLERANS_KCAL = 20  # Besin DB'den kcal sapma toleransı (sıkı)
BESIN_DEGER_TOLERANS_MAKRO = 3  # Besin DB'den makro sapma toleransı (gram, sıkı)


def _find_food_in_db(ad: str) -> Optional[dict]:
    """Besin adını food_database'de ara. Kısmi eşleşme destekler."""
    ad_lower = ad.lower().strip()

    # Tam eşleşme
    if ad_lower in BESIN_DB:
        return BESIN_DB[ad_lower]

    # Kısmi eşleşme: DB key besin adında geçiyorsa
    for db_key, db_val in BESIN_DB.items():
        if db_key in ad_lower or ad_lower in db_key:
            return db_val

    return None


def parse_plan_json(response: str) -> Optional[dict]:
    """Claude yanıtından <!--PLAN_JSON:{...}--> bloğunu parse et."""
    pattern = r'<!--PLAN_JSON:(.*?)-->'
    match = re.search(pattern, response, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as e:
        logger.warning(f"Plan JSON parse hatası: {e}")
        return None


def remove_plan_json(response: str) -> str:
    """Yanıttan PLAN_JSON metadata'sını temizle."""
    return re.sub(r'<!--PLAN_JSON:.*?-->', '', response, flags=re.DOTALL).strip()


def validate_plan(plan_json: dict, user: dict, previous_plan: Optional[dict] = None) -> dict:
    """
    Planı tüm kurallara göre doğrula.

    Args:
        plan_json: Claude'dan gelen yapılandırılmış plan
        user: Kullanıcı profili (hedef makrolar, sağlık durumu vs.)
        previous_plan: Bir önceki günün planı (protein tekrar kontrolü için)

    Returns:
        {
            "valid": bool,
            "errors": [{"tip": str, "mesaj": str, "ogun": str|None, "besin": str|None}],
            "warnings": [{"tip": str, "mesaj": str}],
            "corrected_totals": {"kalori": float, "protein": float, "yag": float, "karb": float, "lif": float}
        }
    """
    errors = []
    warnings = []

    ogunler = plan_json.get("ogunler", [])
    if not ogunler:
        return {"valid": False, "errors": [{"tip": "yapısal", "mesaj": "Plan öğün içermiyor", "ogun": None, "besin": None}], "warnings": [], "corrected_totals": None}

    gun_toplam = {"kalori": 0, "protein": 0, "yag": 0, "karb": 0, "lif": 0}

    for ogun in ogunler:
        ogun_tip = ogun.get("tip", "bilinmeyen")
        besinler = ogun.get("besinler", [])
        ogun_bildirilen = ogun.get("toplam", {})

        # -- 1. Her besinin makro-kalori tutarlılığı --
        ogun_hesaplanan = {"kalori": 0, "protein": 0, "yag": 0, "karb": 0, "lif": 0}

        for besin in besinler:
            p = besin.get("protein", 0)
            y = besin.get("yag", 0)
            k = besin.get("karb", 0)
            bildirilen_kcal = besin.get("kalori", 0)
            hesaplanan_kcal = (p * 4) + (y * 9) + (k * 4)

            fark = abs(hesaplanan_kcal - bildirilen_kcal)
            if fark > KALORI_TOLERANS_BESIN:
                errors.append({
                    "tip": "makro_matematik",
                    "mesaj": f"'{besin.get('ad', '?')}' kalori tutarsız: bildirilen {bildirilen_kcal} kcal, hesaplanan (P{p}×4+Y{y}×9+K{k}×4) = {hesaplanan_kcal:.0f} kcal (fark: {fark:.0f})",
                    "ogun": ogun_tip,
                    "besin": besin.get("ad"),
                    "duzeltme": f"Kalori {hesaplanan_kcal:.0f} olmalı veya makrolar düzeltilmeli"
                })

            # Hesaplanan değerleri kullan (bildirilen değil)
            ogun_hesaplanan["kalori"] += hesaplanan_kcal
            ogun_hesaplanan["protein"] += p
            ogun_hesaplanan["yag"] += y
            ogun_hesaplanan["karb"] += k
            ogun_hesaplanan["lif"] += besin.get("lif", 0)

        # -- 2. Öğün toplamı = besinlerin toplamı mı? --
        for makro in ["protein", "yag", "karb", "lif"]:
            bildirilen = ogun_bildirilen.get(makro, 0)
            hesaplanan = ogun_hesaplanan[makro]
            if abs(bildirilen - hesaplanan) > MAKRO_TOLERANS_OGUN:
                errors.append({
                    "tip": "ogun_toplam",
                    "mesaj": f"{ogun_tip} öğünü {makro} toplamı tutarsız: bildirilen {bildirilen}g, besinlerin toplamı {hesaplanan:.1f}g",
                    "ogun": ogun_tip,
                    "besin": None,
                    "duzeltme": f"{makro} toplamı {hesaplanan:.1f}g olmalı"
                })

        bildirilen_kcal_ogun = ogun_bildirilen.get("kalori", 0)
        if abs(bildirilen_kcal_ogun - ogun_hesaplanan["kalori"]) > KALORI_TOLERANS_OGUN:
            errors.append({
                "tip": "ogun_toplam",
                "mesaj": f"{ogun_tip} öğünü kalori toplamı tutarsız: bildirilen {bildirilen_kcal_ogun} kcal, hesaplanan {ogun_hesaplanan['kalori']:.0f} kcal",
                "ogun": ogun_tip,
                "besin": None,
                "duzeltme": f"Kalori toplamı {ogun_hesaplanan['kalori']:.0f} olmalı"
            })

        # -- 3. Protein dağıtım kontrolü --
        ana_ogunler = ["kahvalti", "ogle", "aksam"]
        if ogun_tip in ana_ogunler:
            if ogun_hesaplanan["protein"] < 20:
                warnings.append({
                    "tip": "protein_dagitim",
                    "mesaj": f"{ogun_tip} öğününde protein çok düşük: {ogun_hesaplanan['protein']:.1f}g (min 25g önerilen)"
                })
            elif ogun_hesaplanan["protein"] > 50:
                warnings.append({
                    "tip": "protein_dagitim",
                    "mesaj": f"{ogun_tip} öğününde protein çok yüksek: {ogun_hesaplanan['protein']:.1f}g (max 45g önerilen)"
                })

        # -- 4. Aynı öğünde çakışan nişastalı besinler --
        starchy_in_meal = []
        for besin in besinler:
            ad = besin.get("ad", "").lower()
            for starchy in STARCHY_FOODS:
                if starchy in ad:
                    starchy_in_meal.append(starchy)
                    break

        if len(starchy_in_meal) >= 2:
            errors.append({
                "tip": "ogun_mantik",
                "mesaj": f"{ogun_tip} öğününde birden fazla nişastalı besin var: {', '.join(starchy_in_meal)}. Birini kaldır veya değiştir.",
                "ogun": ogun_tip,
                "besin": None,
                "duzeltme": f"'{starchy_in_meal[1]}' yerine sebze garnitürü veya salata koy"
            })

        # Gün toplamına ekle
        for key in gun_toplam:
            gun_toplam[key] += ogun_hesaplanan[key]

    # -- 5. Günlük toplam vs hedef kontrolü (plan JSON hedefi) --
    hedef = plan_json.get("hedef", {})
    if hedef:
        for makro, hedef_key in [("kalori", "kalori"), ("protein", "protein"), ("yag", "yag"), ("karb", "karb")]:
            hedef_val = hedef.get(hedef_key, 0)
            gercek_val = gun_toplam[makro]
            tolerans = KALORI_TOLERANS_GUN if makro == "kalori" else MAKRO_TOLERANS_GUN
            fark = gercek_val - hedef_val
            if abs(fark) > tolerans:
                yuksek_dusuk = "yüksek" if fark > 0 else "düşük"
                errors.append({
                    "tip": "gun_toplam",
                    "mesaj": f"Günlük {makro} hedeften çok {yuksek_dusuk}: hedef {hedef_val}, gerçek {gercek_val:.0f} (fark: {fark:+.0f})",
                    "ogun": None,
                    "besin": None,
                    "duzeltme": f"Günlük {makro} toplamını {hedef_val} ±{tolerans} aralığına getir"
                })

    # -- 5b. Kullanıcı profili hedefleriyle karşılaştırma (asıl doğru hedefler) --
    profil_hedefleri = {
        "kalori": user.get("hedef_kalori", 0),
        "protein": user.get("protein_g", 0),
        "yag": user.get("yag_g", 0),
        "karb": user.get("karbonhidrat_g", 0),
    }

    # Sadece profilde hedefler varsa kontrol et
    if profil_hedefleri["kalori"] > 0:
        for makro, profil_val in profil_hedefleri.items():
            if profil_val <= 0:
                continue
            gercek_val = gun_toplam[makro]
            tolerans = KALORI_TOLERANS_GUN if makro == "kalori" else MAKRO_TOLERANS_GUN
            fark = gercek_val - profil_val
            if abs(fark) > tolerans:
                yuksek_dusuk = "yüksek" if fark > 0 else "düşük"
                errors.append({
                    "tip": "profil_hedef_sapma",
                    "mesaj": f"Günlük {makro} kullanıcı profil hedefinden çok {yuksek_dusuk}: profil hedef {profil_val}, gerçek {gercek_val:.0f} (fark: {fark:+.0f})",
                    "ogun": None,
                    "besin": None,
                    "duzeltme": f"Kullanıcının profil hedefi {makro}={profil_val}. Günlük toplamı {profil_val} ±{tolerans} aralığına getir"
                })

    # Lif kontrolü
    hedef_lif = hedef.get("lif", 0) or user.get("lif_g", 0)
    if hedef_lif and gun_toplam["lif"] < hedef_lif * 0.7:
        warnings.append({
            "tip": "lif_eksik",
            "mesaj": f"Günlük lif çok düşük: {gun_toplam['lif']:.0f}g (hedef: {hedef_lif}g). Daha fazla sebze, baklagil veya tam tahıl ekle."
        })

    # -- 6. Protein tekrarı kontrolü (aynı gün) --
    ogun_proteinleri = {}
    for ogun in ogunler:
        ogun_tip = ogun.get("tip", "")
        if ogun_tip not in ("ogle", "aksam"):
            continue
        for besin in ogun.get("besinler", []):
            ad = besin.get("ad", "").lower()
            for kaynak_ad, kaynak_grup in PROTEIN_SOURCES.items():
                if kaynak_ad in ad:
                    ogun_proteinleri.setdefault(ogun_tip, set()).add(kaynak_grup)
                    break

    ogle_protein = ogun_proteinleri.get("ogle", set())
    aksam_protein = ogun_proteinleri.get("aksam", set())
    tekrar = ogle_protein & aksam_protein
    if tekrar:
        errors.append({
            "tip": "protein_tekrar",
            "mesaj": f"Öğle ve akşam yemeğinde aynı protein kaynağı kullanılmış: {', '.join(tekrar)}",
            "ogun": None,
            "besin": None,
            "duzeltme": "Akşam yemeğinde farklı bir protein kaynağı kullan"
        })

    # -- 7. Ardışık gün protein tekrarı --
    if previous_plan:
        prev_ogunler = previous_plan.get("ogunler", [])
        for meal_type in ("ogle", "aksam"):
            prev_proteins = set()
            for ogun in prev_ogunler:
                if ogun.get("tip") == meal_type:
                    for besin in ogun.get("besinler", []):
                        ad = besin.get("ad", "").lower()
                        for kaynak_ad, kaynak_grup in PROTEIN_SOURCES.items():
                            if kaynak_ad in ad:
                                prev_proteins.add(kaynak_grup)
                                break

            current_proteins = ogun_proteinleri.get(meal_type, set())
            tekrar = prev_proteins & current_proteins
            if tekrar:
                meal_label = "öğle" if meal_type == "ogle" else "akşam"
                warnings.append({
                    "tip": "ardisik_gun_tekrar",
                    "mesaj": f"Dünkü {meal_label} yemeğiyle aynı protein: {', '.join(tekrar)}. Mümkünse değiştir."
                })

    # -- 8. Sağlık kuralları --
    hastaliklar = user.get("kronik_hastaliklar") or []

    # Safra kontrolü (Cochrane, Kaiser Permanente, CUH klinik rehberi: 25-40g/gün)
    if "safra" in str(hastaliklar).lower():
        SAFRA_GUNLUK_YAG_LIMIT = 40  # Cochrane evidence range: 25-40g/gün
        SAFRA_OGUN_YAG_LIMIT = 12    # Büyük yağ bolüsü semptom tetikler
        if gun_toplam["yag"] > SAFRA_GUNLUK_YAG_LIMIT:
            errors.append({
                "tip": "saglik_kural",
                "mesaj": f"Safra hastası — günlük yağ limiti {SAFRA_GUNLUK_YAG_LIMIT}g, planda {gun_toplam['yag']:.0f}g var (Cochrane/Kaiser rehberi: 25-40g/gün)",
                "ogun": None, "besin": None,
                "duzeltme": f"Toplam yağı {SAFRA_GUNLUK_YAG_LIMIT}g altına düşür. Yağsız pişirme yöntemleri kullan."
            })
        for ogun in ogunler:
            ogun_yag = sum(b.get("yag", 0) for b in ogun.get("besinler", []))
            if ogun_yag > SAFRA_OGUN_YAG_LIMIT:
                errors.append({
                    "tip": "saglik_kural",
                    "mesaj": f"Safra hastası — {ogun.get('tip', '?')} öğününde yağ {ogun_yag:.0f}g (limit: {SAFRA_OGUN_YAG_LIMIT}g/öğün)",
                    "ogun": ogun.get("tip"), "besin": None,
                    "duzeltme": f"Bu öğündeki yağı {SAFRA_OGUN_YAG_LIMIT}g altına düşür"
                })

    # Diyabet kontrolü (ADA klinik pratiği: karb ≤%40)
    if "diyabet" in str(hastaliklar).lower():
        hedef_kcal = hedef.get("kalori", 0)
        if hedef_kcal > 0:
            karb_kcal_orani = (gun_toplam["karb"] * 4) / hedef_kcal * 100
            if karb_kcal_orani > 42:
                warnings.append({
                    "tip": "saglik_kural",
                    "mesaj": f"Diyabet — karbonhidrat oranı %{karb_kcal_orani:.0f} (ADA önerisi: ≤%40)"
                })

    # Protein üst sınır kontrolü (ISSN 2017: genel antrenman 1.4-2.0 g/kg BW, üst sınır 2.2 g/kg FFM)
    yagsiz_kutle = user.get("yagsiz_kutle_kg", 0)
    if yagsiz_kutle and gun_toplam["protein"] > float(yagsiz_kutle) * 2.2:
        errors.append({
            "tip": "protein_asiri",
            "mesaj": f"Protein aşırı yüksek: {gun_toplam['protein']:.0f}g (ISSN üst sınır: LBM {yagsiz_kutle}kg × 2.2 = {float(yagsiz_kutle)*2.2:.0f}g)",
            "ogun": None, "besin": None,
            "duzeltme": f"Proteini {float(yagsiz_kutle)*2.2:.0f}g altına düşür"
        })

    # Yağ alt sınır kontrolü (EFSA 2010: minimum %20, ACSM: %15-20 altına düşürme)
    hedef_kcal = hedef.get("kalori", 0) or user.get("hedef_kalori", 0)
    if hedef_kcal > 0 and "safra" not in str(hastaliklar).lower():
        yag_kcal_orani = (gun_toplam["yag"] * 9) / hedef_kcal * 100
        if yag_kcal_orani < 18:
            errors.append({
                "tip": "yag_yetersiz",
                "mesaj": f"Yağ oranı çok düşük: %{yag_kcal_orani:.0f} (EFSA/ACSM minimum: %20). Hormonal fonksiyon için yağ artır.",
                "ogun": None, "besin": None,
                "duzeltme": f"Yağ oranını en az %20'ye çıkar → minimum {hedef_kcal * 0.20 / 9:.0f}g yağ"
            })

    # Karbonhidrat g/kg üst sınır kontrolü (ACSM 2016: hafif aktivite 3-5 g/kg)
    kilo = user.get("kilo_kg", 0)
    if kilo and gun_toplam["karb"] > 0:
        karb_per_kg = gun_toplam["karb"] / float(kilo)
        if karb_per_kg > 5:
            errors.append({
                "tip": "karb_asiri",
                "mesaj": f"Karbonhidrat aşırı yüksek: {gun_toplam['karb']:.0f}g = {karb_per_kg:.1f} g/kg (ACSM hafif aktivite limiti: 3-5 g/kg)",
                "ogun": None, "besin": None,
                "duzeltme": f"Karbonhidratı {float(kilo)*5:.0f}g altına düşür veya yağ oranını artır"
            })
        elif karb_per_kg > 4:
            warnings.append({
                "tip": "karb_yuksek",
                "mesaj": f"Karbonhidrat yüksek: {gun_toplam['karb']:.0f}g = {karb_per_kg:.1f} g/kg (ACSM hafif aktivite: 3-5 g/kg aralığının üst sınırına yakın)"
            })

    # -- 9. Besin değeri cross-check (food_database ile) --
    for ogun in ogunler:
        for besin in ogun.get("besinler", []):
            ad = besin.get("ad", "").lower()
            gram = besin.get("gram", 0)
            if gram <= 0:
                continue

            # Besin DB'de eşleşme ara
            db_entry = _find_food_in_db(ad)
            if not db_entry:
                # Bilinmeyen besin — uyar (veritabanındaki besinleri kullanması gerekli)
                warnings.append({
                    "tip": "besin_bulunamadi",
                    "mesaj": f"'{besin.get('ad', '?')}' besin veritabanında bulunamadı. Lütfen veritabanındaki bilinen bir besinle değiştir."
                })
                continue

            # 100g başına normalize et ve karşılaştır
            carpan = gram / 100.0
            for makro, db_key in [("protein", "protein"), ("yag", "yag"), ("karb", "karb")]:
                beklenen = db_entry[db_key] * carpan
                bildirilen = besin.get(makro, 0)
                fark = abs(bildirilen - beklenen)

                # Sıkı tolerans: mutlak fark > 2g VE yüzdelik sapma > %30
                tolerans = max(BESIN_DEGER_TOLERANS_MAKRO * carpan, 2)
                if fark > tolerans:
                    errors.append({
                        "tip": "besin_deger_sapma",
                        "mesaj": f"'{besin.get('ad', '?')}' ({gram}g) {makro} değeri YANLIŞ: bildirilen {bildirilen}g, veritabanına göre doğrusu ~{beklenen:.1f}g (fark: {fark:.1f}g)",
                        "ogun": ogun.get("tip"),
                        "besin": besin.get("ad"),
                        "duzeltme": f"{makro} değerini {beklenen:.1f}g olarak düzelt"
                    })

            # Kalori cross-check
            beklenen_kcal = db_entry["kalori"] * carpan
            bildirilen_kcal = besin.get("kalori", 0)
            kcal_fark = abs(bildirilen_kcal - beklenen_kcal)
            kcal_tolerans = max(BESIN_DEGER_TOLERANS_KCAL * carpan, 10)
            if kcal_fark > kcal_tolerans:
                errors.append({
                    "tip": "besin_deger_sapma",
                    "mesaj": f"'{besin.get('ad', '?')}' ({gram}g) kalori YANLIŞ: bildirilen {bildirilen_kcal} kcal, veritabanına göre doğrusu ~{beklenen_kcal:.0f} kcal (fark: {kcal_fark:.0f})",
                    "ogun": ogun.get("tip"),
                    "besin": besin.get("ad"),
                    "duzeltme": f"Kalori değerini {beklenen_kcal:.0f} kcal olarak düzelt"
                })

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "corrected_totals": {
            "kalori": round(gun_toplam["kalori"]),
            "protein": round(gun_toplam["protein"]),
            "yag": round(gun_toplam["yag"]),
            "karb": round(gun_toplam["karb"]),
            "lif": round(gun_toplam["lif"]),
        }
    }


def format_validation_feedback(result: dict) -> str:
    """Validasyon sonuçlarını Claude'a geri gönderilecek feedback formatına çevir."""
    if result["valid"] and not result["warnings"]:
        return ""

    lines = []

    if result["errors"]:
        lines.append("## PLAN VALİDASYON HATALARI (DÜZELTİLMESİ ZORUNLU):")
        for i, err in enumerate(result["errors"], 1):
            lines.append(f"{i}. [{err['tip']}] {err['mesaj']}")
            if err.get("duzeltme"):
                lines.append(f"   → Düzeltme: {err['duzeltme']}")

    if result["warnings"]:
        lines.append("\n## UYARILAR (mümkünse düzelt):")
        for w in result["warnings"]:
            lines.append(f"- [{w['tip']}] {w['mesaj']}")

    corrected = result.get("corrected_totals")
    if corrected:
        lines.append(f"\n## PROGRAMATIK HESAPLANAN GERÇEK TOPLAMLAR:")
        lines.append(f"Kalori: {corrected['kalori']} | Protein: {corrected['protein']}g | Yağ: {corrected['yag']}g | Karb: {corrected['karb']}g | Lif: {corrected['lif']}g")

    lines.append("\nLütfen yukarıdaki hataları düzelt ve planı tekrar oluştur. Aynı JSON formatını kullan.")

    return "\n".join(lines)
