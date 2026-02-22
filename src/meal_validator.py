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

from src.food_database import BESIN_DB, STARCHY_FOODS, PROTEIN_SOURCES, BANNED_FOODS, IZINLI_EKMEKLER

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


def _is_banned_food(ad: str) -> bool:
    """
    Besin adının yasak listesinde olup olmadığını kontrol et.
    Tam eşleşme + alt-string eşleşme + ASCII normalizasyon ile kontrol eder.
    """
    ad_lower = ad.lower().strip()
    ad_ascii = _turkish_to_ascii(ad_lower)

    # Parantez içini temizle
    ad_clean = re.sub(r'\(.*?\)', '', ad_lower).strip()
    ad_clean_ascii = _turkish_to_ascii(ad_clean)

    for banned in BANNED_FOODS:
        banned_lower = banned.lower()
        banned_ascii = _turkish_to_ascii(banned_lower)
        # Tam eşleşme
        if banned_lower in (ad_lower, ad_clean, ad_ascii, ad_clean_ascii):
            return True
        # Alt-string: "peynirli poğaça" içinde "poğaça" var mı?
        if banned_lower in ad_lower or banned_ascii in ad_ascii:
            return True
    return False


def _is_unapproved_bread(ad: str) -> bool:
    """
    Ekmek türlerini kontrol et — sadece IZINLI_EKMEKLER kabul edilir.
    İzinsiz ekmek (beyaz ekmek, simit, bazlama vb.) uyarı üretir.
    """
    ad_lower = ad.lower().strip()
    ad_clean = re.sub(r'\(.*?\)', '', ad_lower).strip()

    # DB'de eşleşme bul
    db_match = _find_food_in_db(ad_clean) if 'ekmek' in ad_lower or 'simit' in ad_lower or 'bazlama' in ad_lower or 'lavaş' in ad_lower or 'lavas' in ad_lower else None
    if not db_match:
        return False

    db_key, db_entry = db_match
    kategori = db_entry.get("kategori", "")
    if kategori != "karbonhidrat":
        return False

    # Ekmek/hamur ürünü mü?
    ekmek_keywords = {"ekmek", "simit", "bazlama", "lavaş", "yufka", "pide ekmeği"}
    is_bread = any(kw in db_key for kw in ekmek_keywords)
    if not is_bread:
        return False

    # İzinli listede mi?
    if db_key in IZINLI_EKMEKLER:
        return False

    return True


# ASCII-normalized DB keys cache (lazy init)
_ASCII_DB_CACHE: dict = {}


def _get_ascii_db_cache() -> dict:
    """BESIN_DB anahtarlarının ASCII versiyonlarını döndür (cache)."""
    if not _ASCII_DB_CACHE:
        for db_key, db_val in BESIN_DB.items():
            ascii_key = _turkish_to_ascii(db_key)
            _ASCII_DB_CACHE[ascii_key] = (db_key, db_val)
    return _ASCII_DB_CACHE


# ── Yaygın besin eşanlamlıları (alias → DB key) ──────────────────────
# Claude sık kullanır ama DB'de farklı isimle var olan besinler
FOOD_ALIASES = {
    # Sebze
    "taze fasulye": "yeşil fasulye",
    # Kümes
    "tavuk": "tavuk göğsü",
    "tavuk parçalı": "tavuk göğsü",
    "tavuk parça": "tavuk göğsü",
    "tavuk eti": "tavuk göğsü",
    "hindi": "hindi göğsü",
    "hindi eti": "hindi göğsü",
    # Kırmızı et
    "dana eti": "dana kuşbaşı",
    "et": "dana kuşbaşı",
    "kuşbaşı": "dana kuşbaşı",
    "kıyma": "dana kıyma",
    # Balık
    "balık": "levrek",
    # Karb — Ekmek türleri
    # DİKKAT: "ekmek" tek başına beyaz ekmek alias'ı, ama "tam tahıllı ekmek" vb.
    # daha uzun alias olduğu için öncelik kazanır (en uzun eşleşme kuralı).
    "ekmek": "beyaz ekmek",
    "tam tahıllı ekmek": "tam buğday ekmek",
    "tam tahıllı ekşi mayalı ekmek": "tam buğday ekmek",
    "tam tahilli eksi mayali ekmek": "tam buğday ekmek",
    "ekşi mayalı ekmek": "tam buğday ekmek",
    "eksi mayali ekmek": "tam buğday ekmek",
    "tam buğday ekmeği": "tam buğday ekmek",
    "tam tahıllı": "tam buğday ekmek",
    "kepek ekmek": "kepekli ekmek",
    "kepek ekmeği": "kepekli ekmek",
    "siyah ekmek": "çavdar ekmeği",
    "esmer ekmek": "çavdar ekmeği",
    # Karb — Diğer
    "pirinç": "pirinç pilavı",
    "pirinc": "pirinç pilavı",
    "pilav": "pirinç pilavı",
    "bulgur": "bulgur pilavı",
    "sade bulgur pilavı": "bulgur pilavı",
    "sade bulgur pilavi": "bulgur pilavı",
    # Baklagil
    "fasulye": "kuru fasulye",
    # Çorba
    "çorba": "kırmızı mercimek çorbası",
    "mercimek çorbası": "kırmızı mercimek çorbası",
    "mercimek corbasi": "kırmızı mercimek çorbası",
    "kirmizi mercimek corbasi": "kırmızı mercimek çorbası",
    "tavuklu çorba": "tavuklu sebze çorbası",
    "tavuk çorbası": "tavuklu sebze çorbası",
    "sebze çorbası": "ezogelin çorbası",
    "düğün çorba": "düğün çorbası",
    # Salata
    "salata": "yeşil salata",
    "karışık salata": "yeşil salata",
    "yeşillik": "yeşil salata",
    "yesil salata": "yeşil salata",
    "çoban salata": "çoban salatası",
    # Süt ürünleri
    "sade yoğurt": "yoğurt",
    "sade yogurt": "yoğurt",
    "yogurt": "yoğurt",
    # Yağ
    "zeytinyagi": "zeytinyağı",
}

# ASCII versiyonları da ekle
_FOOD_ALIASES_ASCII = {}
for k, v in FOOD_ALIASES.items():
    _FOOD_ALIASES_ASCII[_turkish_to_ascii(k)] = v


def _word_boundary_contains(haystack: str, needle: str) -> bool:
    """
    needle, haystack içinde KELIME SINIRINDA mı geçiyor?
    "zeytin" in "zeytinyağlı taze fasulye" → False (kelime sınırı yok)
    "taze fasulye" in "zeytinyağlı taze fasulye" → True
    "yoğurt" in "süzme yoğurt yağsız" → True
    """
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            return False
        before_ok = (idx == 0) or (haystack[idx - 1] == ' ')
        end_idx = idx + len(needle)
        after_ok = (end_idx == len(haystack)) or (haystack[end_idx] == ' ')
        if before_ok and after_ok:
            return True
        start = idx + 1


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

    # 1d. Alias eşleşme (tam) — "tavuk" → "tavuk göğsü"
    if ad_clean in FOOD_ALIASES:
        target = FOOD_ALIASES[ad_clean]
        if target in BESIN_DB:
            return target, BESIN_DB[target]
    if ad_ascii in _FOOD_ALIASES_ASCII:
        target = _FOOD_ALIASES_ASCII[ad_ascii]
        if target in BESIN_DB:
            return target, BESIN_DB[target]

    # 1e. Alias kelime sınırı eşleşme — "zeytinyağlı taze fasulye" → "taze fasulye" alias bulur
    # En uzun alias eşleşmesini tercih et
    best_alias = None
    best_alias_len = 0
    for alias_key, alias_target in FOOD_ALIASES.items():
        if len(alias_key) > best_alias_len and _word_boundary_contains(ad_clean, alias_key):
            best_alias = alias_target
            best_alias_len = len(alias_key)
    for alias_key, alias_target in _FOOD_ALIASES_ASCII.items():
        if len(alias_key) > best_alias_len and _word_boundary_contains(ad_ascii, alias_key):
            best_alias = alias_target
            best_alias_len = len(alias_key)
    if best_alias and best_alias in BESIN_DB:
        return best_alias, BESIN_DB[best_alias]

    # 2. DB key besin adında geçiyor mu? (kelime sınırı kontrolü ile)
    # "zeytin" in "zeytinyağlı" → False (kelime sınırı yok)
    # "yoğurt" in "süzme yoğurt yağsız" → True (kelime sınırı var)
    best_match = None
    best_len = 0
    candidates = {ad_clean}
    if desuffixed != ad_clean:
        candidates.add(desuffixed)

    for db_key, db_val in BESIN_DB.items():
        db_key_ascii = _turkish_to_ascii(db_key)
        for cand in candidates:
            cand_ascii = _turkish_to_ascii(cand)
            if (_word_boundary_contains(cand, db_key) or
                    _word_boundary_contains(db_key, cand) or
                    _word_boundary_contains(cand_ascii, db_key_ascii) or
                    _word_boundary_contains(db_key_ascii, cand_ascii)):
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
      - "3 yemek kaşığı zeytinyağı" (gram yok → otomatik hesapla)
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
                # Kaşık bazlı ölçüm: "3 yemek kaşığı zeytinyağı" → 3 × 14g = 42g
                spoon_match = re.search(
                    r'(\d+)\s*(?:yemek\s+kaşığı|yemek\s+kasigi|yk)\b', part_lower
                )
                if spoon_match:
                    spoon_count = int(spoon_match.group(1))
                    # Hangi besin olduğunu bul ve porsiyon_g kullan
                    spoon_clean = re.sub(
                        r'\d+\s*(?:yemek\s+kaşığı|yemek\s+kasigi|yk)\s*', '', part_lower
                    ).strip(' -,.()>')
                    spoon_db = _find_food_in_db(spoon_clean)
                    if spoon_db:
                        db_key, db_entry = spoon_db
                        porsiyon_g = db_entry.get("porsiyon_g", 14)  # varsayılan 14g (1 yk)
                        gram = spoon_count * porsiyon_g
                    else:
                        gram = spoon_count * 14  # varsayılan: 1 yk ≈ 14g
                else:
                    # Çay kaşığı: "1 çk zeytinyağı" → 1 × 5g
                    tsp_match = re.search(
                        r'(\d+)\s*(?:çay\s+kaşığı|cay\s+kasigi|tatlı\s+kaşığı|tatli\s+kasigi|çk|ck|tk)\b',
                        part_lower,
                    )
                    if tsp_match:
                        tsp_count = int(tsp_match.group(1))
                        tsp_clean = re.sub(
                            r'\d+\s*(?:çay\s+kaşığı|cay\s+kasigi|tatlı\s+kaşığı|tatli\s+kasigi|çk|ck|tk)\s*',
                            '', part_lower,
                        ).strip(' -,.()>')
                        tsp_db = _find_food_in_db(tsp_clean)
                        if tsp_db:
                            db_key, db_entry = tsp_db
                            gram = tsp_count * 5  # 1 çk/tk ≈ 5g
                        else:
                            continue
                    else:
                        continue
        else:
            gram = float(gram_match.group(1))
        if gram <= 0:
            continue

        # Parantez içi, emoji, ve format karakterlerini temizle
        # DİKKAT: "kuru", "yağsız" gibi kelimeler hem yemek hazırlama hem de
        # besin adı olabilir (kuru fasulye, süzme yoğurt yağsız).
        # Bu yüzden ÖNCE hafif temizlik ile DB'de ara, bulamazsa
        # agresif temizlik ile tekrar dene.

        # Hafif temizlik: sadece format karakterleri ve sayıları temizle
        light_clean = re.sub(r'\([^)]*\)', '', part_lower)   # parantez içi (tam çift)
        light_clean = re.sub(r'[()]', '', light_clean)         # kalan tek parantezler
        light_clean = re.sub(r'\*+', '', light_clean)          # bold yıldızlar
        light_clean = re.sub(r'[→>]', '', light_clean)          # oklar
        light_clean = re.sub(r'\d+\s*(?:g|ml)\b', '', light_clean)  # gram veya ml
        # Kaşık/adet/dilim ölçü birimleri (Türkçe + ASCII)
        light_clean = re.sub(r'\d+\s*(adet|dilim|porsiyon|kase|su\s+bardağı|su\s+bardagi|'
                              r'bardak|corba\s+kasigi|çorba\s+kaşığı|'
                              r'yemek\s+kaşığı|yemek\s+kasigi|'
                              r'çay\s+kaşığı|cay\s+kasigi|'
                              r'tatlı\s+kaşığı|tatli\s+kasigi|'
                              r'yk|çk|ck|tk)\s*',
                              '', light_clean)
        # Rol etiketlerini temizle: "Protein:", "Yag:", "Lif:", "Karb:", "Yan:"
        light_clean = re.sub(r'^(protein|yag|yağ|lif|karb|karbonhidrat|yan)\s*:\s*',
                              '', light_clean)
        light_clean = light_clean.strip(' -,.')

        # Önce hafif temizlik ile dene (kuru fasulye, süzme yoğurt yağsız korunur)
        db_result = _find_food_in_db(light_clean)

        if not db_result:
            # Agresif temizlik: pişirme yöntemleri ve tanımlayıcıları da temizle
            aggressive_clean = re.sub(
                r'(ızgara|izgara|haşlama|haslama|fırında|firinda|buharda|'
                r'pişmiş|pismis|çiğ|kuru|sade|bol\s+limonlu|limonlu|'
                r'pişirme|rendel\w+|yağsız|yagsiz|yarım\s+yağlı|yarim\s+yagli|'
                r'tam\s+yağlı|tam\s+yagli|didik|sebze)',
                '', light_clean,
            )
            aggressive_clean = aggressive_clean.strip(' -,.')
            if aggressive_clean and aggressive_clean != light_clean:
                db_result = _find_food_in_db(aggressive_clean)

        if not db_result:
            # Temizlenmemiş orijinal metin ile de dene
            db_result = _find_food_in_db(part_lower)
        if db_result:
            # Yasak besin kontrolü
            if _is_banned_food(db_result[0]):
                logger.warning(f"Yasak besin fallback parse'da engellendi: {db_result[0]}")
                continue
            results.append((db_result[0], gram))

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

        # Öğün başlığı mı? Çeşitli formatlar:
        # "### KAHVALTI", "KAHVALTI (08:30) — 420 kcal",
        # "**KAHVALTI (08:30)**", "KAHVALTI (08:30)"
        is_header = ('###' in line or '—' in line_lower or '---' in line_stripped)
        # Öğün anahtar kelimesi ile başlayan/içeren satırlar da başlık olabilir
        # (Malzeme/makro satırlarını hariç tut — ">" veya "P:" içermemeli)
        if not is_header:
            has_meal_keyword = any(kw in line_lower for kw, _ in _MEAL_KEYWORDS)
            not_ingredient = ('>' not in line and '→' not in line and
                              not line_stripped.startswith('-') and
                              'P:' not in line)
            if has_meal_keyword and not_ingredient:
                is_header = True
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

        # Malzeme satırı mı? ("→", ">", "-" ile başlar ve gram/ml/kaşığı değeri içerir)
        if not in_ingredient_section:
            continue
        if not ('→' in line or '>' in line or line_stripped.startswith('-')):
            continue
        # gram, ml, veya kaşığı ölçüm birimi olmalı
        has_measure = ('g' in line_lower or 'ml' in line_lower or
                       'kaşığı' in line_lower or 'kasigi' in line_lower or
                       'yk' in line_lower)
        if not has_measure:
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


# ── Porsiyon-Gram Tutarlılık Kontrolü ─────────────────────────

def _fix_portion_gram_mismatch(besin: dict) -> tuple:
    """
    Claude'un "N adet X (Yg)" yazmasındaki gram tutarsızlığını düzelt.

    Örnek: "5 adet ceviz (10g)" → 5 × 4g = 20g olmalı, 10g değil.
    Eğer besin adında "N adet" veya "N " + besin_adı geçiyorsa ve
    DB'de porsiyon_g varsa, gram değerini düzelt.

    Returns: (corrected_gram, correction_msg or None)
    """
    ad = besin.get("ad", "")
    gram = besin.get("gram", 0)
    if not ad or gram <= 0:
        return gram, None

    db_match = _find_food_in_db(ad)
    if not db_match:
        return gram, None

    db_key, db_entry = db_match
    porsiyon_g = db_entry.get("porsiyon_g")
    if not porsiyon_g or porsiyon_g <= 0:
        return gram, None

    # JSON "ad" alanından adet bilgisi çıkar
    # "5 adet ceviz" → 5, "Ceviz" → None, "2 yumurta" → 2
    adet_match = re.search(r'(\d+)\s*(?:adet\s+)?', ad.lower())
    if not adet_match:
        return gram, None

    adet = int(adet_match.group(1))
    if adet <= 0 or adet > 20:  # mantıksız adet
        return gram, None

    expected_gram = round(adet * porsiyon_g)
    tolerance = max(expected_gram * 0.25, 5)  # %25 veya 5g tolerans

    if abs(gram - expected_gram) > tolerance:
        msg = (
            f"{ad}: {adet} adet × {porsiyon_g}g = {expected_gram}g olmalı, "
            f"Claude {gram:.0f}g yazmış → {expected_gram}g olarak düzeltildi"
        )
        logger.info(f"Porsiyon-gram düzeltme: {msg}")
        return expected_gram, msg

    return gram, None


def _enforce_minimum_portion(besin: dict) -> tuple:
    """
    Minimum porsiyon kurallarını uygula (plan_reference.md ile uyumlu).

    Kurallar:
    - Et/balık: min 100g, maks 180g
    - Yoğurt: min 100g, maks 200g
    - Peynir: min 20g, maks 50g
    - Baklagil: min 80g, maks 200g
    - Yumurta: 60g katları olmalı (1=60g, 2=120g, 3=180g)

    Returns: (corrected_besin, correction_msg or None)
    """
    ad = besin.get("ad", "")
    gram = besin.get("gram", 0)
    if not ad or gram <= 0:
        return besin, None

    db_match = _find_food_in_db(ad)
    if not db_match:
        return besin, None

    db_key, db_entry = db_match
    kategori = db_entry.get("kategori", "")

    # Yumurta özel kuralı: 60g katları olmalı
    if db_key == "yumurta":
        if gram % 60 != 0:
            # En yakın 60g katına yuvarla (en az 60g)
            adet = max(1, round(gram / 60))
            new_gram = adet * 60
            msg = (
                f"{ad}: yumurta {gram:.0f}g → {new_gram:.0f}g "
                f"({adet} adet × 60g) olarak düzeltildi"
            )
            logger.info(f"Minimum porsiyon: {msg}")
            besin = dict(besin)
            besin["gram"] = new_gram
            return besin, msg
        return besin, None

    # Et/balık: min 80g, maks 180g
    if kategori == "protein" and db_key not in ("yumurta", "tofu"):
        new_gram = gram
        if gram < 80 and gram >= 30:  # 30g altı bilinçli küçük parça olabilir
            new_gram = 80
        elif gram > 180:
            new_gram = 180
        if new_gram != gram:
            msg = (
                f"{ad}: {gram:.0f}g → {new_gram:.0f}g "
                f"(et/balık porsiyon sınırı: 80-180g)"
            )
            logger.info(f"Minimum porsiyon: {msg}")
            besin = dict(besin)
            besin["gram"] = new_gram
            return besin, msg

    # Yoğurt: min 100g, maks 200g (peynirler hariç)
    if kategori == "sut_urunu":
        is_yogurt = any(k in db_key for k in ("yoğurt", "yogurt", "kefir", "ayran", "cacık"))
        is_peynir = any(k in db_key for k in ("peynir", "kaşar", "lor", "çökelek", "tulum", "feta", "hellim", "mozzarella", "ricotta", "labne"))

        if is_yogurt:
            new_gram = gram
            if gram < 100 and gram >= 30:
                new_gram = 100
            elif gram > 200:
                new_gram = 200
            if new_gram != gram:
                msg = (
                    f"{ad}: {gram:.0f}g → {new_gram:.0f}g "
                    f"(yoğurt porsiyon sınırı: 100-200g)"
                )
                logger.info(f"Minimum porsiyon: {msg}")
                besin = dict(besin)
                besin["gram"] = new_gram
                return besin, msg

        elif is_peynir:
            new_gram = gram
            if gram < 20 and gram >= 5:
                new_gram = 20
            elif gram > 50:
                new_gram = 50
            if new_gram != gram:
                msg = (
                    f"{ad}: {gram:.0f}g → {new_gram:.0f}g "
                    f"(peynir porsiyon sınırı: 20-50g)"
                )
                logger.info(f"Minimum porsiyon: {msg}")
                besin = dict(besin)
                besin["gram"] = new_gram
                return besin, msg

    # Baklagil: min 80g, maks 200g
    if kategori == "baklagil":
        new_gram = gram
        if gram < 80 and gram >= 30:
            new_gram = 80
        elif gram > 200:
            new_gram = 200
        if new_gram != gram:
            msg = (
                f"{ad}: {gram:.0f}g → {new_gram:.0f}g "
                f"(baklagil porsiyon sınırı: 80-200g)"
            )
            logger.info(f"Minimum porsiyon: {msg}")
            besin = dict(besin)
            besin["gram"] = new_gram
            return besin, msg

    return besin, None


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

    logger.info(
        f"Makro enforcement başlıyor: hedef P:{hedef_p:.0f}g Y:{hedef_y:.0f}g "
        f"K:{hedef_k:.0f}g {hedef_kcal:.0f}kcal"
    )

    if not hedef_p or not hedef_y:
        logger.warning(
            f"Makro enforcement ATLANIYYOR: protein_g={user.get('protein_g')!r} "
            f"yag_g={user.get('yag_g')!r} — hedefler eksik!"
        )
        return corrected_ogunler, []

    adjustments = []
    p_tolerans = hedef_p * PROTEIN_HEDEF_TOLERANS_PCT
    y_tolerans = hedef_y * MAKRO_HEDEF_TOLERANS_PCT

    # Kategori bazlı minimum porsiyonlar (gram) — düşük hedefli kullanıcılar için
    MIN_PORTION = {
        "protein": 80,      # Et, balık: min 80g, maks 180g
        "sut_urunu": 80,    # Yoğurt: min 100g, peynir: min 20g (ayrı kontrol)
        "baklagil": 80,     # Nohut, mercimek: min 80g
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
                scale = max(0.4, min(scale, 1.0))  # min %40, max %100

                for oi, bi, besin, kategori, min_gram in protein_besinler:
                    old_gram = besin.get("gram", 0)
                    if old_gram > 0:
                        new_gram = round(old_gram * scale)
                        # Gerçekçi minimum porsiyonu koru.
                        # Et/balık (kategori=protein): HER ZAMAN minimum uygula
                        # (60g somon diye bir şey yok — Claude hatası)
                        # Süt ürünü/baklagil: sadece orijinal porsiyon minimumun
                        # üzerindeyse uygula (30g peynir bilinçli bir seçim)
                        if kategori == "protein":
                            new_gram = max(new_gram, min_gram)
                        elif old_gram >= min_gram:
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

        # Yağ yoğun besinleri bul — önce saf yağ/kuruyemiş, sonra yağ yoğun süt ürünleri
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
                        kat = db_entry.get("kategori", "")
                        if kat in ("yag", "kuruyemis"):
                            is_fat_source = True
                        # Yağ oranı yüksek süt ürünleri de hedefle (kefir, yoğurt)
                        elif kat == "sut_urunu" and besin.get("y", 0) > 3:
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

    # ── Kalori dengeleme (karbonhidrat/yağ ölçekleme) ──
    # Protein ve yağ düzeltildikten sonra kalori hedefini kontrol et.
    # Karbonhidrat ve yağ kaynaklarını ölçekleyerek kalori dengesini sağla.
    if hedef_kcal > 0:
        total_kcal_now = sum(
            b["kcal"] for o in corrected_ogunler for b in o.get("besinler", [])
        )

        # Kalori %10'dan fazla DÜŞÜK → porsiyon büyüt
        if total_kcal_now < hedef_kcal * 0.90:
            deficit_kcal = hedef_kcal - total_kcal_now
            adjustments.append(
                f"Kalori düşük: {total_kcal_now:.0f} vs hedef {hedef_kcal:.0f} kcal "
                f"({deficit_kcal:.0f} kcal eksik) — porsiyonlar büyütülüyor"
            )

            # Büyütülebilir besinleri bul (protein kaynakları hariç — zaten ayarlandı)
            # Yağ hedefin üstündeyse yağ/kuruyemiş büyütme!
            total_y_now = sum(
                b["y"] for o in corrected_ogunler for b in o.get("besinler", [])
            )
            yag_asmis = total_y_now >= hedef_y

            scalable = []
            SCALE_UP_MAX = {
                "karbonhidrat": 300, "baklagil": 250,
                "meyve": 200,
            }
            if not yag_asmis:
                SCALE_UP_MAX["yag"] = 25
                SCALE_UP_MAX["kuruyemis"] = 40
            for oi, ogun in enumerate(corrected_ogunler):
                for bi, besin in enumerate(ogun.get("besinler", [])):
                    if besin.get("gram", 0) <= 0:
                        continue
                    db_match = _find_food_in_db(besin.get("ad", ""))
                    if not db_match:
                        continue
                    _, db_entry = db_match
                    kategori = db_entry.get("kategori", "")
                    if kategori in SCALE_UP_MAX:
                        scalable.append(
                            (oi, bi, besin, kategori, SCALE_UP_MAX[kategori])
                        )

            if scalable:
                current_scalable_kcal = sum(
                    b["kcal"] for _, _, b, _, _ in scalable
                )
                if current_scalable_kcal > 0:
                    raw_scale = 1 + (deficit_kcal / current_scalable_kcal)
                    scale = min(raw_scale, 2.0)  # Maks 2x büyütme

                    for oi, bi, besin, kategori, max_g in scalable:
                        old_gram = besin.get("gram", 0)
                        new_gram = round(old_gram * scale)
                        new_gram = min(new_gram, max_g)
                        if new_gram > old_gram:
                            scaled = _scale_besin(besin, new_gram)
                            corrected_ogunler[oi]["besinler"][bi] = scaled
                            adjustments.append(
                                f"  {besin['ad']}: {old_gram:.0f}g → "
                                f"{new_gram:.0f}g"
                            )

                # Log: kalan eksiklik
                new_total = sum(
                    b["kcal"] for o in corrected_ogunler
                    for b in o.get("besinler", [])
                )
                if new_total < hedef_kcal * 0.90:
                    adjustments.append(
                        f"  ⚠ Porsiyon sınırlarıyla kalori {new_total:.0f} kcal "
                        f"(hedef {hedef_kcal:.0f}) — maks porsiyon sınırları korundu"
                    )

        # Kalori %10'dan fazla YÜKSEK → tüm küçültülebilir porsiyonları küçült
        elif total_kcal_now > hedef_kcal * 1.10:
            surplus_kcal = total_kcal_now - hedef_kcal
            adjustments.append(
                f"Kalori yüksek: {total_kcal_now:.0f} vs hedef {hedef_kcal:.0f} kcal "
                f"({surplus_kcal:.0f} kcal fazla) — porsiyonlar küçültülüyor"
            )

            # Tüm küçültülebilir besinleri bul (protein hariç — zaten ayarlandı)
            SCALE_DOWN_MIN = {
                "karbonhidrat": 50, "baklagil": 50,
                "meyve": 80, "sut_urunu": 50,
                "yag": 3, "kuruyemis": 5,
                "sebze": 80,
            }
            scalable_besinler = []
            for oi, ogun in enumerate(corrected_ogunler):
                for bi, besin in enumerate(ogun.get("besinler", [])):
                    if besin.get("gram", 0) <= 20:
                        continue
                    db_match = _find_food_in_db(besin.get("ad", ""))
                    if db_match:
                        _, db_entry = db_match
                        kat = db_entry.get("kategori", "")
                        if kat in SCALE_DOWN_MIN:
                            scalable_besinler.append(
                                (oi, bi, besin, kat, SCALE_DOWN_MIN[kat])
                            )

            if scalable_besinler:
                current_kcal = sum(b["kcal"] for _, _, b, _, _ in scalable_besinler)
                if current_kcal > 0:
                    scale = max(1 - (surplus_kcal / current_kcal), 0.4)
                    for oi, bi, besin, kat, min_g in scalable_besinler:
                        old_gram = besin.get("gram", 0)
                        new_gram = round(old_gram * scale)
                        new_gram = max(new_gram, min_g)
                        if new_gram < old_gram:
                            scaled = _scale_besin(besin, new_gram)
                            corrected_ogunler[oi]["besinler"][bi] = scaled
                            adjustments.append(
                                f"  {besin['ad']}: {old_gram:.0f}g → "
                                f"{new_gram:.0f}g"
                            )

    # ── Son çare: global ölçekleme ──
    # Tüm bireysel düzeltmelerden sonra hâlâ %15'ten fazla aşım varsa
    # TÜM besinleri orantılı küçült (protein dahil)
    if hedef_kcal > 0:
        final_kcal = sum(
            b["kcal"] for o in corrected_ogunler for b in o.get("besinler", [])
        )
        if final_kcal > hedef_kcal * 1.15:
            global_scale = hedef_kcal / final_kcal
            # Çok agresif olma — en fazla %30 küçültme
            global_scale = max(global_scale, 0.7)
            adjustments.append(
                f"Global ölçekleme: {final_kcal:.0f} → ~{final_kcal * global_scale:.0f} kcal "
                f"(×{global_scale:.2f})"
            )
            for ogun in corrected_ogunler:
                for bi, besin in enumerate(ogun.get("besinler", [])):
                    old_gram = besin.get("gram", 0)
                    if old_gram > 10:
                        new_gram = round(old_gram * global_scale)
                        new_gram = max(new_gram, 10)
                        if new_gram != old_gram:
                            ogun["besinler"][bi] = _scale_besin(besin, new_gram)

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

            # YASAK BESİN KONTROLÜ — plandan çıkar
            if _is_banned_food(ad):
                errors.append(
                    f"{ogun_adi}/{ad}: YASAK BESİN — diyet planında kullanılamaz"
                )
                logger.warning(f"Yasak besin tespit edildi ve çıkarıldı: {ad} ({ogun_adi})")
                continue  # Bu besini plana dahil etme

            # rol alanı kontrolü
            if rol and rol not in VALID_ROLES:
                warnings.append(
                    f"{ogun_adi}/{ad}: geçersiz rol '{rol}'"
                )

            # Porsiyon-gram tutarlılık kontrolü
            # "5 adet ceviz (10g)" → 5 × 4g = 20g olmalı
            corrected_gram, portion_msg = _fix_portion_gram_mismatch(besin)
            if portion_msg:
                db_corrections.append(portion_msg)
                besin = dict(besin)
                besin["gram"] = corrected_gram

            # Minimum porsiyon kontrolü — plan_reference.md kuralları
            # Et/balık: min 100g, maks 180g | Yoğurt: min 100g | Peynir: min 20g
            # Baklagil: min 80g | Yumurta: 60g katları
            besin, min_msg = _enforce_minimum_portion(besin)
            if min_msg:
                db_corrections.append(min_msg)

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

            # İzinsiz ekmek kontrolü
            if _is_unapproved_bread(ad):
                warnings.append(
                    f"{ogun_adi}/{ad}: İzinsiz ekmek türü — sadece tam tahıllı/ekşi mayalı ekmek kullanılmalı"
                )

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
    logger.info(
        f"DB düzeltme sonrası toplamlar: P:{gunluk_p:.0f}g Y:{gunluk_y:.0f}g "
        f"K:{gunluk_k:.0f}g {gunluk_kcal:.0f}kcal — "
        f"user keys: {sorted(k for k in (user or {}) if user.get(k) is not None)}"
    )
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
    # İki farklı format desteklenir:
    # Format A (kcal önce): "XXX kcal [✅] | P: XXg | Y: XXg | K: XXg | L: XXg"
    # Format B (kcal sonda): "P: XXg | Y: XXg | K: XXg | L: XXg | XXX kcal"
    daily_count = 0

    # Format A: kcal | P | Y | K | L
    pattern_daily_a = (
        r'[\d.,]+\s*kcal[^\n|]*\|\s*P:\s*[\d.]+\s*g?[^\|\n]*\|\s*'
        r'Y:\s*[\d.]+\s*g?[^\|\n]*\|\s*K:\s*[\d.]+\s*g?[^\|\n]*\|\s*'
        r'(?:Lif|L):\s*[\d.]+\s*g?[^\n]*'
    )
    replacement_daily_a = (
        f'{gt["kcal"]:.0f} kcal | P: {gt["p"]:.0f}g | Y: {gt["y"]:.0f}g | '
        f'K: {gt["k"]:.0f}g | L: {gt["l"]:.0f}g'
    )
    text, count_a = re.subn(pattern_daily_a, replacement_daily_a, text)
    daily_count += count_a

    # Format B: P | Y | K | L | kcal — günlük toplam satırında kullanılır
    # Per-meal satırları da bu formatta ama onlar zaten yukarıda düzeltildi.
    if daily_count == 0:
        # Per-meal satırlar zaten düzeltildi, kalan eşleşme(ler) günlük toplamlar.
        # meal_macro_pattern ile eşleşen ama per-meal olarak düzeltilmemiş satırları bul.
        remaining_matches = list(re.finditer(meal_macro_pattern, text))
        # İlk N eşleşme per-meal (zaten düzeltildi), gerisi günlük toplam
        if len(remaining_matches) > len(ogunler):
            for m in reversed(remaining_matches[len(ogunler):]):
                # Prefix'i koru (başındaki \s* newline yakalayabilir)
                prefix = m.group(1) if m.group(1) else ''
                replacement = (
                    f'{prefix}P: {gt["p"]:.0f}g | Y: {gt["y"]:.0f}g | K: {gt["k"]:.0f}g | '
                    f'L: {gt["l"]:.0f}g | {gt["kcal"]:.0f} kcal'
                )
                text = text[:m.start()] + replacement + text[m.end():]
                daily_count += 1

    logger.debug(f"patch_response_totals: günlük toplam {daily_count} kez güncellendi")

    # "**Kalori:** XXX kcal" formatı
    text = re.sub(r'(\*\*Kalori:\*\*)\s*[\d.,]+\s*kcal', f'**Kalori:** {gt["kcal"]:.0f} kcal', text)
    text = re.sub(r'(\*\*Protein:\*\*)\s*[\d.,]+\s*g', f'**Protein:** {gt["p"]:.0f}g', text)
    text = re.sub(r'(\*\*Yağ:\*\*)\s*[\d.,]+\s*g', f'**Yağ:** {gt["y"]:.0f}g', text)
    text = re.sub(r'(\*\*Karb:\*\*)\s*[\d.,]+\s*g', f'**Karb:** {gt["k"]:.0f}g', text)
    text = re.sub(r'(\*\*Lif:\*\*)\s*[\d.,]+\s*g', f'**Lif:** {gt["l"]:.0f}g', text)

    return text
