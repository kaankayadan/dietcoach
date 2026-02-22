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


def _turkish_to_ascii(text: str) -> str:
    """
    Türkçe özel karakterleri ASCII eşlenikleriyle değiştir.
    "süzme yoğurt yağsız" → "suzme yogurt yagsiz"
    Claude bazen ASCII Türkçe kullanır, DB ise doğru Türkçe.
    """
    table = str.maketrans({
        'ğ': 'g', 'Ğ': 'G',
        'ş': 's', 'Ş': 'S',
        'ç': 'c', 'Ç': 'C',
        'ö': 'o', 'Ö': 'O',
        'ü': 'u', 'Ü': 'U',
        'ı': 'i', 'İ': 'I',
    })
    return text.translate(table)


# ASCII-normalized DB keys cache (lazy init)
_ASCII_DB_CACHE: dict = {}


def _get_ascii_db_cache() -> dict:
    """BESIN_DB anahtarlarının ASCII versiyonlarını döndür (cache)."""
    if not _ASCII_DB_CACHE:
        for db_key, db_val in BESIN_DB.items():
            ascii_key = _turkish_to_ascii(db_key)
            _ASCII_DB_CACHE[ascii_key] = (db_key, db_val)
    return _ASCII_DB_CACHE


def _turkish_desuffix(text: str) -> str:
    """
    Türkçe ünsüz yumuşaması ters çevirimi.
    ekmeği → ekmek, yoğurdu → yoğurt, çorbası → çorba
    Böylece DB'deki yalın hallerle eşleşme sağlanır.
    """
    # Ünsüz yumuşaması: k→ğ, t→d, p→b, ç→c
    # Ters çevir: son kelimede ğ+ünlü → k, d+ünlü → t, vb.
    mutations = [
        ('ğı', 'k'), ('ği', 'k'), ('ğu', 'k'), ('ğü', 'k'),
        ('du', 't'), ('dü', 't'), ('dı', 't'), ('di', 't'),
        ('bu', 'p'), ('bü', 'p'), ('bı', 'p'), ('bi', 'p'),
        ('cu', 'ç'), ('cü', 'ç'), ('cı', 'ç'), ('ci', 'ç'),
    ]
    words = text.split()
    if not words:
        return text

    last = words[-1]
    for suffix, replacement in mutations:
        if last.endswith(suffix):
            words[-1] = last[:-len(suffix)] + replacement
            return ' '.join(words)

    # Basit ek kaldırma: -sı, -si, -ası, -esi (iyelik)
    possessive = [
        'ası', 'esi', 'sı', 'si', 'su', 'sü',
        'ı', 'i', 'u', 'ü',
    ]
    for suf in possessive:
        if last.endswith(suf) and len(last) > len(suf) + 2:
            candidate = last[:-len(suf)]
            words[-1] = candidate
            joined = ' '.join(words)
            if joined in BESIN_DB:
                return joined
            words[-1] = last  # geri al

    return text


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

    # 1b. Türkçe ünsüz yumuşaması ters çevirimi ile tam eşleşme
    desuffixed = _turkish_desuffix(ad_clean)
    if desuffixed != ad_clean and desuffixed in BESIN_DB:
        return desuffixed, BESIN_DB[desuffixed]

    # 1c. ASCII normalizasyon ile tam eşleşme
    # Claude bazen "suzme yogurt yagsiz" yazar, DB'de "süzme yoğurt yağsız" var
    ascii_cache = _get_ascii_db_cache()
    ad_ascii = _turkish_to_ascii(ad_clean)
    if ad_ascii in ascii_cache:
        return ascii_cache[ad_ascii]

    # Desuffix sonucu da ASCII ile dene
    desuffixed_ascii = _turkish_to_ascii(desuffixed) if desuffixed != ad_clean else None
    if desuffixed_ascii and desuffixed_ascii in ascii_cache:
        return ascii_cache[desuffixed_ascii]

    # 2. DB key besin adında geçiyor mu? (her iki yönde kontrol)
    # Hem orijinal (Türkçe karakter) hem ASCII normalizasyonla dene
    best_match = None
    best_len = 0
    candidates = {ad_clean}
    if desuffixed != ad_clean:
        candidates.add(desuffixed)

    for db_key, db_val in BESIN_DB.items():
        db_key_ascii = _turkish_to_ascii(db_key)
        for cand in candidates:
            cand_ascii = _turkish_to_ascii(cand)
            # Hem orijinal hem ASCII versiyonlarda karşılaştır
            if (db_key in cand or cand in db_key or
                    db_key_ascii in cand_ascii or cand_ascii in db_key_ascii):
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


# ── Fallback: Görünür metinden plan çıkarma ───────────────────

# Öğün başlıkları — metinde aranacak
_MEAL_KEYWORDS = [
    ("kahvaltı", "kahvalti"),
    ("kahvalti", "kahvalti"),
    ("ara öğün", "ara_ogun"),
    ("ara ogun", "ara_ogun"),
    ("öğle yemeği", "ogle"),
    ("öğle", "ogle"),
    ("ogle", "ogle"),
    ("akşam yemeği", "aksam"),
    ("akşam", "aksam"),
    ("aksam", "aksam"),
]


def _extract_foods_from_line(line: str) -> list:
    """
    Bir malzeme satırından (gram, besin_adı) çiftlerini çıkar.
    Desteklenen formatlar:
      - "1 yumurta (40g) + 12g beyaz peynir"
      - "170g tavuk göğsü (ızgara)"
      - "2 dilim kepekli ekmek (60g)"
      - "7 adet zeytin (24g)"
      - "1 yemek kaşığı zeytinyağı (10g)"
      - "1 kase mercimek çorbası (250ml)"
    """
    results = []
    # "+" ile ayrılmış parçaları işle
    parts = re.split(r'\+', line)

    for part in parts:
        part_lower = part.lower().strip()
        if not part_lower:
            continue

        # Gram değeri bul: "(40g)", "40g", "40 g"
        gram_match = re.search(r'(\d+)\s*g\b', part_lower)
        if not gram_match:
            # ml desteği: çorbalar için ml ≈ g (su bazlı)
            ml_match = re.search(r'(\d+)\s*ml\b', part_lower)
            if ml_match:
                gram = float(ml_match.group(1))
            else:
                continue
        else:
            gram = float(gram_match.group(1))
        if gram <= 0:
            continue

        # Parantez içi, emoji, ve format karakterlerini temizle
        clean = re.sub(r'\([^)]*\)', '', part_lower)  # parantez içi
        clean = re.sub(r'\*+', '', clean)               # bold yıldızlar
        clean = re.sub(r'[→>]', '', clean)               # oklar
        clean = re.sub(r'\d+\s*(?:g|ml)\b', '', clean)   # gram veya ml
        clean = re.sub(r'\d+\s*(adet|dilim|porsiyon|kase|su\s+bardağı|bardak|'
                        r'yemek\s+kaşığı|çay\s+kaşığı|yk|çk)\s*', '', clean)
        clean = re.sub(r'(ızgara|haşlama|fırında|buharda|pişmiş|çiğ|kuru|'
                        r'pişirme|rendel\w+|yağsız|yarım\s+yağlı|tam\s+yağlı)', '', clean)
        clean = clean.strip(' -,.')

        # DB'den en iyi eşleşmeyi bul
        # _find_food_in_db: tam eşleşme > Türkçe desuffix > çift yönlü substring
        # Her zaman en uzun (en spesifik) eşleşmeyi seçer
        best_key = None
        db_result = _find_food_in_db(clean)
        if not db_result:
            # Temizlenmemiş orijinal metin ile de dene
            db_result = _find_food_in_db(part_lower)
        if db_result:
            best_key = db_result[0]

        if best_key:
            results.append((best_key, gram))

    return results


def response_has_meal_structure(text: str) -> bool:
    """
    Claude'un yanıtının yemek planı yapısı içerip içermediğini kontrol et.
    Birden fazla öğün başlığı varsa plan yanıtıdır.
    """
    text_lower = text.lower()
    meal_keywords = [
        'kahvaltı', 'kahvalti',
        'öğle yemeği', 'öğle', 'ogle',
        'akşam yemeği', 'akşam', 'aksam',
        'ara öğün', 'ara ogun',
    ]
    found = set()
    for kw in meal_keywords:
        if kw in text_lower:
            # Normalize to base meal type
            if 'kahvalt' in kw:
                found.add('kahvalti')
            elif 'öğle' in kw or 'ogle' in kw:
                found.add('ogle')
            elif 'akşam' in kw or 'aksam' in kw:
                found.add('aksam')
            elif 'ara' in kw:
                found.add('ara')
    return len(found) >= 3


def fallback_extract_plan_from_text(response_text: str) -> Optional[dict]:
    """
    JSON blok yoksa görünür metinden malzeme+gram çıkarıp
    food_database yapısında plan dict oluştur.

    Bu plan daha sonra validate_plan() ile aynı pipeline'dan geçer:
    food_database cross-check, makro hedef enforcement, patching.
    """
    lines = response_text.split('\n')
    ogunler = []
    current_ogun_name = None
    current_besinler = []
    in_ingredient_section = False

    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()

        # Öğün başlığı mı? (### KAHVALTI, ### ARA ÖĞÜN, vs.)
        is_header = ('###' in line or '—' in line_lower or '---' in line_stripped)
        if is_header:
            for keyword, ogun_key in _MEAL_KEYWORDS:
                if keyword in line_lower:
                    # Önceki öğünü kaydet
                    if current_ogun_name and current_besinler:
                        ogunler.append({
                            "ogun": current_ogun_name,
                            "besinler": current_besinler,
                            "toplam": {"p": 0, "y": 0, "k": 0, "l": 0, "kcal": 0},
                        })
                    current_ogun_name = ogun_key
                    current_besinler = []
                    in_ingredient_section = False
                    break

        if not current_ogun_name:
            continue

        # "Malzemelerin" bölümünü tespit et
        if 'malzeme' in line_lower:
            in_ingredient_section = True
            continue

        # "Ne yapabilirsin", "Alternatif", "Makro" satırlarında malzeme bölümü biter
        if any(k in line_lower for k in ['ne yapabilirsin', 'alternatif', 'makro:', 'p:', '💡', '🔄']):
            in_ingredient_section = False
            continue

        # Malzeme satırı mı? ("→", ">", "-" ile başlar ve gram değeri içerir)
        if not in_ingredient_section:
            continue
        if not ('→' in line or '>' in line or line_stripped.startswith('-')):
            continue
        if 'g' not in line_lower:
            continue

        # Malzemeleri çıkar
        foods = _extract_foods_from_line(line)
        for db_key, gram in foods:
            db_entry = BESIN_DB[db_key]
            kategori = db_entry.get("kategori", "")
            # Rol: kategori → rol mapping
            rol_map = {
                "protein": "protein", "sut_urunu": "protein",
                "karbonhidrat": "karbonhidrat", "baklagil": "karbonhidrat",
                "sebze": "lif", "meyve": "lif", "kuru_meyve": "karbonhidrat",
                "yag": "yag", "kuruyemis": "yag",
            }
            rol = rol_map.get(kategori, "")

            current_besinler.append({
                "ad": db_key.title(),
                "gram": gram,
                "rol": rol,
                "p": 0, "y": 0, "k": 0, "l": 0, "kcal": 0,
            })

    # Son öğünü kaydet
    if current_ogun_name and current_besinler:
        ogunler.append({
            "ogun": current_ogun_name,
            "besinler": current_besinler,
            "toplam": {"p": 0, "y": 0, "k": 0, "l": 0, "kcal": 0},
        })

    if not ogunler:
        logger.warning("fallback_extract: Metinden hiç öğün çıkarılamadı")
        return None

    total_foods = sum(len(o["besinler"]) for o in ogunler)
    logger.info(
        f"fallback_extract: {len(ogunler)} öğün, {total_foods} besin metinden çıkarıldı"
    )

    return {
        "ogunler": ogunler,
        "gunluk_toplam": {"p": 0, "y": 0, "k": 0, "l": 0, "kcal": 0},
    }


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
    Aşım varsa protein kaynaklarının gramajını AKILLI şekilde küçült:
    - Gerçekçi minimum porsiyonları koru (et: 80g, süt ürünü: 80g)
    - Baklagilleri de protein kaynağı olarak say
    - Tüm kaynakları aynı oranda küçültmek yerine, en büyük aşım kaynağını
      öncelikle küçült
    - Minimum porsiyonun altına asla düşme

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

    # Kategori bazlı minimum porsiyonlar (gram)
    MIN_PORTION = {
        "protein": 80,      # Et, balık, yumurta: min 80g
        "sut_urunu": 80,    # Yoğurt, peynir: min 80g
        "baklagil": 60,     # Nohut, mercimek: min 60g
    }

    # ── Protein aşımı düzeltme ──
    total_p = sum(b["p"] for o in corrected_ogunler for b in o.get("besinler", []))

    if total_p > hedef_p + p_tolerans:
        adjustments.append(
            f"Protein hedef aşımı: {total_p:.0f}g vs hedef {hedef_p:.0f}g — "
            f"gramajlar küçültülüyor ({total_p - hedef_p:.0f}g fazla)"
        )

        # Protein kaynağı olan besinleri bul (baklagiller dahil)
        protein_besinler = []
        for oi, ogun in enumerate(corrected_ogunler):
            for bi, besin in enumerate(ogun.get("besinler", [])):
                is_protein_source = False
                kategori = ""
                if besin.get("rol") == "protein":
                    is_protein_source = True
                db_match = _find_food_in_db(besin.get("ad", ""))
                if db_match:
                    _, db_entry = db_match
                    kategori = db_entry.get("kategori", "")
                    if kategori in ("protein", "sut_urunu", "baklagil"):
                        is_protein_source = True
                if is_protein_source and besin.get("p", 0) > 0 and besin.get("gram", 0) > 15:
                    min_gram = MIN_PORTION.get(kategori, 30)
                    protein_besinler.append((oi, bi, besin, kategori, min_gram))

        if protein_besinler:
            # Protein kaynaklarını protein yoğunluğuna göre sırala (en yoğun ilk)
            # Böylece en çok protein veren kaynaklar önce küçültülür
            protein_besinler.sort(
                key=lambda x: x[2].get("p", 0) / max(x[2].get("gram", 1), 1),
                reverse=True,
            )

            # Hedef protein: protein kaynaklarından gelmesi gereken miktar
            non_protein_p = total_p - sum(b["p"] for _, _, b, _, _ in protein_besinler)
            target_from_sources = max(0, hedef_p - non_protein_p)
            current_from_sources = sum(b["p"] for _, _, b, _, _ in protein_besinler)

            if current_from_sources > 0 and target_from_sources < current_from_sources:
                # Oransal ölçekleme — ama minimum porsiyonlara saygı göster
                scale = target_from_sources / current_from_sources
                scale = max(0.5, min(scale, 1.0))  # min %50, max %100

                for oi, bi, besin, kategori, min_gram in protein_besinler:
                    old_gram = besin.get("gram", 0)
                    if old_gram > 0:
                        new_gram = round(old_gram * scale)
                        # Gerçekçi minimum porsiyonu koru — ama sadece orijinal
                        # porsiyon zaten minimumun üzerindeyse. Küçük porsiyonları
                        # (ör: 30g peynir) zorlama, bu bilinçli bir seçim olabilir.
                        if old_gram >= min_gram:
                            new_gram = max(new_gram, min_gram)
                        scaled = _scale_besin(besin, new_gram)
                        corrected_ogunler[oi]["besinler"][bi] = scaled
                        if old_gram != new_gram:
                            adjustments.append(
                                f"  {besin['ad']}: {old_gram:.0f}g → {new_gram:.0f}g"
                            )

                # Minimum porsiyonlar nedeniyle hâlâ aşım varsa → kabul et, log'la
                new_total_p = sum(
                    b["p"] for o in corrected_ogunler for b in o.get("besinler", [])
                )
                if new_total_p > hedef_p + p_tolerans:
                    adjustments.append(
                        f"  ⚠ Gerçekçi porsiyonlarla protein {new_total_p:.0f}g "
                        f"(hedef {hedef_p:.0f}g) — minimum porsiyonlar korundu"
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
                scale = max(0.5, 1 - (needed_reduction / current_fat_sum))

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
                        orig_adet = max(1, round(orig_gram / porsiyon_g))
                        corr_adet = max(1, round(corr_gram / porsiyon_g))
                        if orig_adet != corr_adet:
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
