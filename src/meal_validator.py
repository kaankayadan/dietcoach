"""
Birleşik Yemek Planı Doğrulayıcı — macro_validator + food_database cross-check.

İş akışı:
1. Claude'un JSON planını parse et
2. Her besini food_database ile cross-check yap (gram varsa)
   → Yanlış değerleri otomatik düzelt (2. API çağrısı yok)
3. Öğün ve günlük toplamları yeniden hesapla
4. Kullanıcı hedefleriyle karşılaştır — AŞIM VARSA GRAMAJLARI ÖLÇEKLE
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

# food_database cross-check — HER ZAMAN DB değerlerini kullan
DB_MAKRO_TOLERANS = 1.5       # gram sapma — sıkılaştırıldı (eskiden 3)
DB_KCAL_TOLERANS = 10         # kcal sapma — sıkılaştırıldı (eskiden 20)

# Hedef sapma (yüzde bazlı — kullanıcı hedefine göre)
KALORI_HEDEF_TOLERANS_PCT = 0.05   # ±%5
PROTEIN_HEDEF_TOLERANS_PCT = 0.10  # ±%10
MAKRO_HEDEF_TOLERANS_PCT = 0.10    # ±%10


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


# ── food_database ile kesin hesaplama ─────────────────────────

def _recalculate_besin_from_db(besin: dict) -> dict:
    """
    Bir besinin makro değerlerini food_database'den KESİN hesapla.
    DB'de varsa Claude'un değerlerini tamamen yok say, DB'den hesapla.
    DB'de yoksa Claude'un değerlerini koru.
    """
    ad = besin.get("ad", "?")
    gram = besin.get("gram", 0)
    rol = besin.get("rol", "")

    db_match = _find_food_in_db(ad)

    if db_match and gram > 0:
        db_key, db_entry = db_match
        carpan = gram / 100.0
        return {
            "ad": ad,
            "gram": gram,
            "rol": rol,
            "p": round(db_entry["protein"] * carpan, 1),
            "y": round(db_entry["yag"] * carpan, 1),
            "k": round(db_entry["karb"] * carpan, 1),
            "l": round(db_entry.get("lif", 0) * carpan, 1),
            "kcal": round(db_entry["kalori"] * carpan, 0),
            "_db_key": db_key,
        }
    else:
        # DB'de yok — Claude değerlerini koru
        return {
            "ad": ad,
            "gram": gram,
            "rol": rol,
            "p": besin.get("p", 0),
            "y": besin.get("y", 0),
            "k": besin.get("k", 0),
            "l": besin.get("l", 0),
            "kcal": besin.get("kcal", 0),
            "_db_key": None,
        }


def _scale_besin(besin: dict, new_gram: float) -> dict:
    """Bir besinin gramajını değiştirip makroları yeniden hesapla."""
    ad = besin.get("ad", "?")
    db_match = _find_food_in_db(ad)

    if db_match and new_gram > 0:
        db_key, db_entry = db_match
        carpan = new_gram / 100.0
        result = dict(besin)
        result["gram"] = round(new_gram, 0)
        result["p"] = round(db_entry["protein"] * carpan, 1)
        result["y"] = round(db_entry["yag"] * carpan, 1)
        result["k"] = round(db_entry["karb"] * carpan, 1)
        result["l"] = round(db_entry.get("lif", 0) * carpan, 1)
        result["kcal"] = round(db_entry["kalori"] * carpan, 0)
        return result
    else:
        # DB'de yoksa oranla ölçekle
        old_gram = besin.get("gram", 0)
        if old_gram <= 0:
            return dict(besin)
        ratio = new_gram / old_gram
        result = dict(besin)
        result["gram"] = round(new_gram, 0)
        result["p"] = round(besin["p"] * ratio, 1)
        result["y"] = round(besin["y"] * ratio, 1)
        result["k"] = round(besin["k"] * ratio, 1)
        result["l"] = round(besin["l"] * ratio, 1)
        result["kcal"] = round(besin["kcal"] * ratio, 0)
        return result


def _enforce_macro_targets(corrected_ogunler: list, user: dict) -> tuple:
    """
    Günlük makro toplamlarının hedefi aşmamasını ZORLA.
    Aşım varsa protein kaynaklarının gramajını orantılı küçült.

    Returns: (adjusted_ogunler, adjustments_log)
    """
    hedef_p = float(user.get("protein_g") or 0)
    hedef_y = float(user.get("yag_g") or 0)
    hedef_k = float(user.get("karbonhidrat_g") or 0)
    hedef_kcal = float(user.get("hedef_kalori") or 0)

    if not hedef_p or not hedef_y:
        return corrected_ogunler, []

    adjustments = []
    p_tolerans = hedef_p * PROTEIN_HEDEF_TOLERANS_PCT
    y_tolerans = hedef_y * MAKRO_HEDEF_TOLERANS_PCT

    # ── Protein aşımı düzeltme (iteratif) ──
    for iteration in range(3):  # max 3 iterasyon
        total_p = sum(b["p"] for o in corrected_ogunler for b in o.get("besinler", []))

        if total_p <= hedef_p + p_tolerans:
            break

        if iteration == 0:
            adjustments.append(
                f"Protein hedef aşımı: {total_p:.0f}g vs hedef {hedef_p:.0f}g — "
                f"gramajlar küçültülüyor ({total_p - hedef_p:.0f}g fazla)"
            )

        # Protein kaynağı olan besinleri bul
        protein_besinler = []
        for oi, ogun in enumerate(corrected_ogunler):
            for bi, besin in enumerate(ogun.get("besinler", [])):
                is_protein_source = False
                if besin.get("rol") == "protein":
                    is_protein_source = True
                else:
                    db_match = _find_food_in_db(besin.get("ad", ""))
                    if db_match:
                        _, db_entry = db_match
                        if db_entry.get("kategori") in ("protein", "sut_urunu"):
                            is_protein_source = True
                if is_protein_source and besin.get("p", 0) > 0 and besin.get("gram", 0) > 15:
                    protein_besinler.append((oi, bi, besin))

        if not protein_besinler:
            break

        # Protein-dışı kaynaklardan gelen proteini hesapla
        non_protein_p = total_p - sum(b["p"] for _, _, b in protein_besinler)
        # Protein kaynaklarından gelmesi gereken miktar
        target_from_protein_sources = max(0, hedef_p - non_protein_p)
        current_from_protein_sources = sum(b["p"] for _, _, b in protein_besinler)

        if current_from_protein_sources <= 0:
            break

        scale = target_from_protein_sources / current_from_protein_sources
        scale = max(0.3, min(scale, 1.0))  # min %30, max %100

        for oi, bi, besin in protein_besinler:
            old_gram = besin.get("gram", 0)
            if old_gram > 0:
                new_gram = round(old_gram * scale)
                new_gram = max(new_gram, 10)
                scaled = _scale_besin(besin, new_gram)
                corrected_ogunler[oi]["besinler"][bi] = scaled
                if old_gram != new_gram:
                    adjustments.append(
                        f"  {besin['ad']}: {old_gram:.0f}g → {new_gram:.0f}g"
                    )

    # ── Yağ aşımı düzeltme ──
    # Yeniden hesapla (protein düzeltmesi yağı da değiştirmiş olabilir)
    total_y = sum(b["y"] for o in corrected_ogunler for b in o.get("besinler", []))

    if total_y > hedef_y + y_tolerans:
        fazla_y = total_y - hedef_y
        adjustments.append(
            f"Yağ hedef aşımı: {total_y:.0f}g vs hedef {hedef_y:.0f}g — "
            f"yağ kaynakları küçültülüyor ({fazla_y:.0f}g fazla)"
        )

        # Yağ yoğun besinleri bul (zeytinyağı, tereyağı, kuruyemişler)
        yag_besinler = []
        for oi, ogun in enumerate(corrected_ogunler):
            for bi, besin in enumerate(ogun.get("besinler", [])):
                is_fat_source = False
                if besin.get("rol") == "yag":
                    is_fat_source = True
                else:
                    db_match = _find_food_in_db(besin.get("ad", ""))
                    if db_match:
                        _, db_entry = db_match
                        if db_entry.get("kategori") in ("yag", "kuruyemis"):
                            is_fat_source = True
                if is_fat_source and besin.get("y", 0) > 0:
                    yag_besinler.append((oi, bi, besin))

        if yag_besinler:
            current_fat_sum = sum(b["y"] for _, _, b in yag_besinler)
            if current_fat_sum > 0:
                needed_reduction = total_y - hedef_y
                scale = max(0.3, 1 - (needed_reduction / current_fat_sum))

                for oi, bi, besin in yag_besinler:
                    old_gram = besin.get("gram", 0)
                    if old_gram > 0:
                        new_gram = round(old_gram * scale)
                        new_gram = max(new_gram, 3)  # minimum 3g yağ
                        scaled = _scale_besin(besin, new_gram)
                        corrected_ogunler[oi]["besinler"][bi] = scaled
                        if old_gram != new_gram:
                            adjustments.append(
                                f"  {besin['ad']}: {old_gram:.0f}g → {new_gram:.0f}g"
                            )

    # Öğün toplamlarını yeniden hesapla
    for ogun in corrected_ogunler:
        op = sum(b["p"] for b in ogun.get("besinler", []))
        oy = sum(b["y"] for b in ogun.get("besinler", []))
        ok = sum(b["k"] for b in ogun.get("besinler", []))
        ol = sum(b["l"] for b in ogun.get("besinler", []))
        okcal = sum(b["kcal"] for b in ogun.get("besinler", []))
        ogun["toplam"] = {
            "p": round(op, 1), "y": round(oy, 1), "k": round(ok, 1),
            "l": round(ol, 1), "kcal": round(okcal, 0),
        }

    return corrected_ogunler, adjustments


# ── Ana Doğrulama ────────────────────────────────────────────

def validate_plan(plan_json: dict, user: dict, previous_plan: dict = None) -> dict:
    """
    Plan JSON'ını kapsamlı doğrula ve otomatik düzelt.

    KRİTİK: Her besin food_database'den KESİN hesaplanır.
    Claude'un verdiği makro değerleri yok sayılır — gramaj + DB kaynağı kullanılır.
    Makro hedefleri aşılmışsa gramajlar otomatik küçültülür.

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
            "db_corrections": [str]
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

    VALID_ROLES = {"protein", "karbonhidrat", "lif", "yag"}

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
            rol = besin.get("rol", "")

            # rol alanı kontrolü
            if rol and rol not in VALID_ROLES:
                warnings.append(
                    f"{ogun_adi}/{ad}: geçersiz rol '{rol}'"
                )

            # KRİTİK: food_database'den KESİN hesapla
            recalc = _recalculate_besin_from_db(besin)

            # Claude değerleriyle karşılaştır — fark varsa logla
            if recalc["_db_key"]:
                old_p = besin.get("p", 0)
                old_y = besin.get("y", 0)
                old_k = besin.get("k", 0)
                old_kcal = besin.get("kcal", 0)
                diffs = []
                if abs(old_p - recalc["p"]) > DB_MAKRO_TOLERANS:
                    diffs.append(f"P:{old_p}→{recalc['p']}g")
                if abs(old_y - recalc["y"]) > DB_MAKRO_TOLERANS:
                    diffs.append(f"Y:{old_y}→{recalc['y']}g")
                if abs(old_k - recalc["k"]) > DB_MAKRO_TOLERANS:
                    diffs.append(f"K:{old_k}→{recalc['k']}g")
                if abs(old_kcal - recalc["kcal"]) > DB_KCAL_TOLERANS:
                    diffs.append(f"kcal:{old_kcal}→{recalc['kcal']}")
                if diffs:
                    msg = f"{ad} ({gram}g) → DB ({recalc['_db_key']}): {', '.join(diffs)}"
                    db_corrections.append(msg)
                    logger.info(f"food_database düzeltme: {msg}")
            elif gram > 0:
                warnings.append(f"{ad} besin veritabanında yok — makro değerleri doğrulanamadı")

            # _db_key'i temizle
            corrected_besin = {k: v for k, v in recalc.items() if k != "_db_key"}
            if not corrected_besin.get("gram"):
                corrected_besin.pop("gram", None)
            if not corrected_besin.get("rol"):
                corrected_besin.pop("rol", None)
            corrected_besinler.append(corrected_besin)

            ogun_p += recalc["p"]
            ogun_y += recalc["y"]
            ogun_k += recalc["k"]
            ogun_l += recalc["l"]
            ogun_kcal += recalc["kcal"]

        # Protein dağıtım kontrolü
        ana_ogunler = ["kahvaltı", "öğle", "akşam"]
        if ogun_adi.lower() in ana_ogunler:
            if ogun_p < 15:
                warnings.append(f"{ogun_adi}: protein düşük ({ogun_p:.0f}g)")
            elif ogun_p > 50:
                warnings.append(f"{ogun_adi}: protein yüksek ({ogun_p:.0f}g)")

        # Nişastalı besin çakışması
        starchy_in_meal = []
        for besin in corrected_besinler:
            ad_lower = besin["ad"].lower()
            for starchy in STARCHY_FOODS:
                if starchy in ad_lower:
                    starchy_in_meal.append(starchy)
                    break
        if len(starchy_in_meal) >= 2:
            warnings.append(f"{ogun_adi}: birden fazla nişastalı besin ({', '.join(starchy_in_meal)})")

        # Alternatif malzeme kontrolü
        for alt in ogun.get("alternatifler", []):
            koy_str = alt.get("koy", "")
            koy_clean = re.sub(r'\d+\s*g\b', '', koy_str).strip()
            if koy_clean and not _find_food_in_db(koy_clean):
                warnings.append(f"{ogun_adi}: alternatif '{koy_str}' DB'de yok")

        corrected_ogun = {
            **ogun,
            "besinler": corrected_besinler,
            "toplam": {
                "p": round(ogun_p, 1),
                "y": round(ogun_y, 1),
                "k": round(ogun_k, 1),
                "l": round(ogun_l, 1),
                "kcal": round(ogun_kcal, 0),
            }
        }
        corrected_ogunler.append(corrected_ogun)

        gunluk_p += ogun_p
        gunluk_y += ogun_y
        gunluk_k += ogun_k
        gunluk_l += ogun_l
        gunluk_kcal += ogun_kcal

    # ── MAKRO HEDEF AŞIMI KONTROLÜ — gramajları ölçekle ──
    macro_adjustments = []
    if user:
        corrected_ogunler, macro_adjustments = _enforce_macro_targets(
            corrected_ogunler, user
        )
        if macro_adjustments:
            for adj in macro_adjustments:
                logger.info(f"Makro hedef düzeltme: {adj}")
                db_corrections.append(adj)

    # Günlük toplamları yeniden hesapla (düzeltmeler sonrası)
    gunluk_p = sum(b["p"] for o in corrected_ogunler for b in o.get("besinler", []))
    gunluk_y = sum(b["y"] for o in corrected_ogunler for b in o.get("besinler", []))
    gunluk_k = sum(b["k"] for o in corrected_ogunler for b in o.get("besinler", []))
    gunluk_l = sum(b["l"] for o in corrected_ogunler for b in o.get("besinler", []))
    gunluk_kcal = sum(b["kcal"] for o in corrected_ogunler for b in o.get("besinler", []))

    corrected_totals = {
        "p": round(gunluk_p, 1),
        "y": round(gunluk_y, 1),
        "k": round(gunluk_k, 1),
        "l": round(gunluk_l, 1),
        "kcal": round(gunluk_kcal, 0),
    }

    # ── Kullanıcı hedefleriyle son karşılaştırma (düzeltme sonrası) ──
    if user:
        hedef_kcal = user.get("hedef_kalori")
        hedef_p = user.get("protein_g")
        hedef_y = user.get("yag_g")
        hedef_l = user.get("lif_g")

        if hedef_kcal:
            kcal_tol = float(hedef_kcal) * KALORI_HEDEF_TOLERANS_PCT
            fark = gunluk_kcal - float(hedef_kcal)
            if abs(fark) > kcal_tol:
                yd = "yüksek" if fark > 0 else "düşük"
                warnings.append(f"Kalori hedeften {yd}: {gunluk_kcal:.0f} vs {hedef_kcal} kcal ({fark:+.0f})")

        if hedef_p:
            p_tol = float(hedef_p) * PROTEIN_HEDEF_TOLERANS_PCT
            fark_p = gunluk_p - float(hedef_p)
            if abs(fark_p) > p_tol:
                yd = "yüksek" if fark_p > 0 else "düşük"
                warnings.append(f"Protein hedeften {yd}: {gunluk_p:.0f}g vs {hedef_p}g ({fark_p:+.0f}g)")

        if hedef_y:
            y_tol = float(hedef_y) * MAKRO_HEDEF_TOLERANS_PCT
            fark_y = gunluk_y - float(hedef_y)
            if abs(fark_y) > y_tol:
                warnings.append(f"Yağ hedeften sapma: {gunluk_y:.0f}g vs {hedef_y}g")

        if hedef_l and gunluk_l < float(hedef_l) * 0.7:
            warnings.append(f"Lif yetersiz: {gunluk_l:.0f}g (hedef: {hedef_l}g)")

        # Protein tekrar kontrolü (aynı gün: öğle vs akşam)
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
            warnings.append(f"Öğle ve akşam aynı protein kaynağı: {', '.join(tekrar)}")

        # Ardışık gün protein tekrarı
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
                warnings.append(f"Dünkü planla aynı protein: {', '.join(ardisik_tekrar)}")

        # Sağlık kuralları
        hastaliklar = user.get("kronik_hastaliklar") or []
        hastalik_str = str(hastaliklar).lower()

        if "safra" in hastalik_str:
            if gunluk_y > 40:
                errors.append(f"Safra hastası — günlük yağ {gunluk_y:.0f}g (limit: 40g)")
            for ogun in corrected_ogunler:
                ogun_yag = ogun["toplam"]["y"]
                if ogun_yag > 12:
                    errors.append(f"Safra hastası — {ogun.get('ogun', '?')} yağ {ogun_yag:.0f}g (limit: 12g/öğün)")

        if "diyabet" in hastalik_str and hedef_kcal and hedef_kcal > 0:
            karb_orani = (gunluk_k * 4) / float(hedef_kcal) * 100
            if karb_orani > 42:
                warnings.append(f"Diyabet — karb oranı %{karb_orani:.0f} (ADA: ≤%40)")

        yagsiz_kutle = user.get("yagsiz_kutle_kg", 0)
        if yagsiz_kutle and gunluk_p > float(yagsiz_kutle) * 2.2:
            errors.append(f"Protein aşırı: {gunluk_p:.0f}g (ISSN üst sınır: LBM×2.2 = {float(yagsiz_kutle)*2.2:.0f}g)")

        if hedef_kcal and hedef_kcal > 0 and "safra" not in hastalik_str:
            yag_orani = (gunluk_y * 9) / float(hedef_kcal) * 100
            if yag_orani < 18:
                errors.append(f"Yağ oranı çok düşük: %{yag_orani:.0f} (minimum: %20)")

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

def patch_ingredient_grams(response_text: str, original_plan: dict, corrected_plan: dict) -> str:
    """
    Makro hedef düzeltmesi sonucu gramajı değişen malzemelerin
    görünen metindeki gramajlarını da güncelle.

    Örnek: "3 yumurta (180g)" → "2 yumurta (120g)" gibi değişiklikleri uygular.
    """
    text = response_text
    orig_ogunler = original_plan.get("ogunler", [])
    corr_ogunler = corrected_plan.get("ogunler", [])

    for oi, (orig_ogun, corr_ogun) in enumerate(zip(orig_ogunler, corr_ogunler)):
        orig_besinler = orig_ogun.get("besinler", [])
        corr_besinler = corr_ogun.get("besinler", [])

        for bi, (orig_b, corr_b) in enumerate(zip(orig_besinler, corr_besinler)):
            orig_gram = orig_b.get("gram", 0)
            corr_gram = corr_b.get("gram", 0)

            if orig_gram != corr_gram and orig_gram > 0 and corr_gram > 0:
                ad = orig_b.get("ad", "")

                # "180g" → "120g" gibi gramaj değişikliklerini yakala
                # Çeşitli formatlar: "180g", "(180g)", "180 g"
                pattern_gram = rf'(\b{int(orig_gram)})\s*g\b'
                replacement_gram = f'{int(corr_gram)}g'

                # Sadece bu besinle ilgili satırdaki gramajı değiştir
                # Besin adının geçtiği bölgeyi bul ve orada değiştir
                ad_lower = ad.lower()
                lines = text.split('\n')
                for li, line in enumerate(lines):
                    if ad_lower in line.lower():
                        new_line = re.sub(pattern_gram, replacement_gram, line, count=1)
                        if new_line != line:
                            lines[li] = new_line
                            break
                text = '\n'.join(lines)

                # Porsiyon sayısını da güncelle (ör: "3 yumurta" → "2 yumurta")
                db_match = _find_food_in_db(ad)
                if db_match:
                    _, db_entry = db_match
                    porsiyon_g = db_entry.get("porsiyon_g")
                    if porsiyon_g and porsiyon_g > 0:
                        orig_adet = round(orig_gram / porsiyon_g)
                        corr_adet = round(corr_gram / porsiyon_g)
                        if orig_adet != corr_adet and orig_adet > 0:
                            pattern_adet = rf'\b{orig_adet}\s+{re.escape(ad.lower())}'
                            replacement_adet = f'{corr_adet} {ad.lower()}'
                            text = re.sub(pattern_adet, replacement_adet, text, count=1, flags=re.IGNORECASE)

    return text


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

    Birden fazla format varyantını destekler:
    - "P: 26g | Y: 20g | K: 48g | Lif: 6g | ~450 kcal"
    - "**Makro:** P: 26g | Y: 20g | K: 48g | Lif: 6g | ~450 kcal"
    - "P: 26g | Y: 20g | K: 48g | L: 6g | ~450 kcal"

    Düzeltmeler:
    - finditer + reverse replace ile her öğün makro satırını DOĞRU sırada düzeltir
    - Başlık kalorilerini de günceller (ör: "— 440 kcal")
    - Emoji variation selector'ları tolere eden günlük toplam regex'i
    """
    text = response_text
    ogunler = corrected_plan.get("ogunler", [])
    gt = corrected_plan.get("gunluk_toplam", {})

    if not gt:
        return text

    # ── 1. Per-meal macro lines ──────────────────────────────────
    # Pattern: [optional **Makro:**] P: Xg | Y: Xg | K: Xg | L/Lif: Xg | [~]XXX kcal
    # Group 1: prefix (ör: "**Makro:** ")
    meal_macro_pattern = (
        r'((?:\*\*)?(?:Makro:?\s*)?(?:\*\*)?\s*)'
        r'P:\s*[\d.]+\s*g?\s*\|\s*Y:\s*[\d.]+\s*g?\s*\|\s*K:\s*[\d.]+\s*g?\s*\|\s*'
        r'(?:Lif|L):\s*[\d.]+\s*g?\s*\|\s*~?[\d.,]+\s*kcal'
    )

    matches = list(re.finditer(meal_macro_pattern, text))

    # Sondan başa doğru değiştir — pozisyon kayması olmasın
    for i in range(min(len(matches), len(ogunler)) - 1, -1, -1):
        t = ogunler[i]["toplam"]
        m = matches[i]
        prefix = m.group(1)  # "**Makro:** " prefix'ini koru
        replacement = (
            f'{prefix}P: {t["p"]:.0f}g | Y: {t["y"]:.0f}g | K: {t["k"]:.0f}g | '
            f'L: {t["l"]:.0f}g | {t["kcal"]:.0f} kcal'
        )
        text = text[:m.start()] + replacement + text[m.end():]

    logger.debug(f"patch_response_totals: {len(matches)} makro satırı, {len(ogunler)} öğün eşleşti")

    # ── 2. Header calories (ör: "— 440 kcal") ───────────────────
    header_pattern = r'—\s*~?[\d.,]+\s*kcal'
    header_matches = list(re.finditer(header_pattern, text))

    for i in range(min(len(header_matches), len(ogunler)) - 1, -1, -1):
        t = ogunler[i]["toplam"]
        m = header_matches[i]
        replacement = f'— {t["kcal"]:.0f} kcal'
        text = text[:m.start()] + replacement + text[m.end():]

    logger.debug(f"patch_response_totals: {len(header_matches)} başlık kalorisi güncellendi")

    # ── 3. Daily total line ──────────────────────────────────────
    # Format: "XXX kcal | P: XXg [emoji/any] | Y: XXg ... | K: XXg ... | L: XXg ..."
    # [^\|\n]* emoji variation selector'ları ve diğer karakterleri tolere eder
    pattern_daily = (
        r'[\d.,]+\s*kcal\s*\|\s*P:\s*[\d.]+\s*g?\s*[^\|\n]*\|\s*'
        r'Y:\s*[\d.]+\s*g?\s*[^\|\n]*\|\s*K:\s*[\d.]+\s*g?\s*[^\|\n]*\|\s*'
        r'(?:Lif|L):\s*[\d.]+\s*g?'
    )
    replacement_daily = (
        f'{gt["kcal"]:.0f} kcal | P: {gt["p"]:.0f}g | Y: {gt["y"]:.0f}g | '
        f'K: {gt["k"]:.0f}g | L: {gt["l"]:.0f}g'
    )
    text, daily_count = re.subn(pattern_daily, replacement_daily, text)
    logger.debug(f"patch_response_totals: günlük toplam {daily_count} kez güncellendi")

    # "**Kalori:** XXX kcal" formatı
    text = re.sub(r'(\*\*Kalori:\*\*)\s*[\d.,]+\s*kcal', f'**Kalori:** {gt["kcal"]:.0f} kcal', text)
    text = re.sub(r'(\*\*Protein:\*\*)\s*[\d.,]+\s*g', f'**Protein:** {gt["p"]:.0f}g', text)
    text = re.sub(r'(\*\*Yağ:\*\*)\s*[\d.,]+\s*g', f'**Yağ:** {gt["y"]:.0f}g', text)
    text = re.sub(r'(\*\*Karb:\*\*)\s*[\d.,]+\s*g', f'**Karb:** {gt["k"]:.0f}g', text)
    text = re.sub(r'(\*\*Lif:\*\*)\s*[\d.,]+\s*g', f'**Lif:** {gt["l"]:.0f}g', text)

    return text
