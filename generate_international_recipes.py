"""
Uluslararası Trend Tarif Generator — Claude Subagent'ları

Her kategori için ayrı bir Claude API çağrısı yaparak iyi bilinen,
trend uluslararası tarifleri gerçekçi makrolarla üretir.

Çıktı: international_recipes.json
Sonra integrate_recipes.py veya doğrudan recipes.json'a merge edilebilir.

Kullanım:
    python generate_international_recipes.py
    python generate_international_recipes.py --merge  # recipes.json ile birleştir
"""
import json
import re
import sys
import argparse
import logging
from pathlib import Path

import anthropic

from validate_recipes import validate

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Üretilecek tarif kategorileri ve prompt'ları
# Her "görev" bağımsız bir Claude çağrısıdır → paralel subagent mantığı
RECIPE_TASKS = [
    {
        "task_id": "intl_kahvalti_trend",
        "kategori": "kahvalti",
        "ogun_tipleri": ["kahvalti"],
        "description": "Trend uluslararası kahvaltılar",
        "count": 25,
        "prompt_hint": """
Aşağıdaki dünyaca ünlü, sosyal medyada trend olan ve beslenme açısından iyi bilinen kahvaltıları listele.
Örnekler (bunlarla sınırlı kalma, daha fazla üret):
- Açaí Bowl (Brezilyalı smoothie bowl)
- Smoothie Bowl (Mango, çilek, yaban mersini vb.)
- Avocado Toast (avokado ezmeli tam tahıllı ekmek)
- Overnight Oats (gecelik yulaf, chia tohumu)
- Chia Pudding (chia tohumlu sütlü puding)
- Shakshuka (Orta Doğu domates yumurtalı)
- Greek Yogurt Parfait (Yunan yoğurdu granola meyve)
- Egg White Omelette (beyaz omlet sebzeli)
- Protein Pancakes (protein tozu yulaf unlu pankek)
- Acai Smoothie Bowl
- Bircher Muesli (İsviçre tarzı yulaf)
- Turkish-style menemen (uluslararası versiyon)
- Veggie Breakfast Burrito
- Smoked Salmon Bagel
- Breakfast Quinoa Bowl
""",
    },
    {
        "task_id": "intl_ara_ogun_trend",
        "kategori": "ara_ogun",
        "ogun_tipleri": ["ara_ogun"],
        "description": "Trend uluslararası ara öğünler",
        "count": 20,
        "prompt_hint": """
Dünyaca bilinen, sağlıklı ve trend ara öğünleri listele.
Örnekler:
- Energy Balls (yulaf, fıstık ezmesi, bal)
- Protein Bites (protein tozlu enerji topları)
- Edamame (japon soya fasulyesi)
- Rice Cakes with Almond Butter (pirinç keki + badem ezmesi)
- Hummus with Veggie Sticks (sebzeli humus)
- Greek Yogurt with Berries (meyveli Yunan yoğurdu)
- Trail Mix (kuruyemiş karışımı)
- Apple with Peanut Butter (elma + fıstık ezmesi)
- Cottage Cheese with Fruit
- Protein Bar (ev yapımı)
- Roasted Chickpeas (fırında nohut)
- Guacamole with Corn Chips
- Hard-Boiled Eggs (haşlanmış yumurta)
- Banana with Almond Butter
- Veggie Chips (sebze cipsi)
""",
    },
    {
        "task_id": "intl_ogle_trend",
        "kategori": "ana_yemek_tavuk",
        "ogun_tipleri": ["ogle", "aksam"],
        "description": "Trend uluslararası öğle yemekleri — tavuk/vejetaryen",
        "count": 25,
        "prompt_hint": """
Dünyaca ünlü ve sağlıklı öğle yemeklerini listele. Tavuk ağırlıklı veya vejetaryen.
Örnekler:
- Buddha Bowl (tahıl + sebze + sos)
- Poke Bowl (Japon ton balığı pirinç kasesi)
- Mediterranean Chicken Wrap (Akdeniz tavuk dürüm)
- Falafel Plate (nohut köftesi + humus + salata)
- Grain Bowl (quinoa + sebze + avokado)
- Thai Chicken Salad (Tayland usulü tavuk salatası)
- Asian Noodle Salad (Asya tarzı noodle salatası)
- Mexican Chicken Bowl (Meksika usulü pirinç + fasulye + tavuk)
- Teriyaki Chicken Rice Bowl
- Greek Chicken Souvlaki Plate
- Nicoise Salad (Fransız ton balıklı salata)
- Vietnamese Spring Rolls (Vietnamlı taze börek)
- Caprese Salad with Grilled Chicken
- Lentil Mediterranean Bowl
- Chickpea Shawarma Bowl
""",
    },
    {
        "task_id": "intl_ogle_balik",
        "kategori": "ana_yemek_balik",
        "ogun_tipleri": ["ogle", "aksam"],
        "description": "Trend uluslararası balık/deniz ürünleri yemekleri",
        "count": 20,
        "prompt_hint": """
Dünyaca bilinen sağlıklı balık ve deniz ürünleri yemeklerini listele.
Örnekler:
- Teriyaki Salmon (Japon teriyaki sosu ile somon)
- Salmon Poke Bowl
- Grilled Sea Bass Mediterranean Style
- Tuna Nicoise Salad
- Miso Glazed Cod (miso soslu morina)
- Shrimp Stir Fry (karides sote)
- Tuna Avocado Stack
- Baked Lemon Herb Salmon
- Shrimp Tacos (karides takosu)
- Seared Tuna with Sesame Noodles
- Thai Fish Curry (Tayland balık körisi)
- Grilled Tilapia with Mango Salsa
- Shrimp and Quinoa Bowl
- Mediterranean Baked Fish
- Salmon Teriyaki Rice Bowl
""",
    },
    {
        "task_id": "intl_aksam_trend",
        "kategori": "ana_yemek_et",
        "ogun_tipleri": ["aksam"],
        "description": "Trend uluslararası akşam yemekleri",
        "count": 20,
        "prompt_hint": """
Dünyaca bilinen sağlıklı akşam yemeklerini listele.
Örnekler:
- Chicken Stir-Fry (tavuk sote Asya usulü)
- Pasta Primavera (sebzeli İtalyan makarnası)
- Greek Moussaka (Yunan patlıcan + kıyma)
- Thai Green Curry (Tayland yeşil körisi)
- Japanese Ramen (sağlıklı versiyon)
- Korean Bibimbap (Kore pilav kasesi)
- Moroccan Lamb Tagine (Fas kuzu güveci)
- Turkish-Inspired Chicken Kebab
- Beef and Broccoli Stir Fry
- Pad Thai (az yağlı)
- Indian Chicken Tikka Masala (light)
- Mexican Black Bean Enchiladas
- Italian Chicken Cacciatore
- French Poulet Rôti (fırın tavuk)
- Lemon Herb Roasted Chicken
""",
    },
    {
        "task_id": "intl_salata_trend",
        "kategori": "salata",
        "ogun_tipleri": ["ogle", "aksam"],
        "description": "Trend uluslararası salatalar",
        "count": 15,
        "prompt_hint": """
Dünyaca bilinen trend salatalar:
- Caesar Salad (klasik + tavuk)
- Kale and Quinoa Salad
- Greek Salad (Yunan salatası)
- Caprese Salad (domates mozarella fesleğen)
- Thai Papaya Salad
- Fattoush Salad (Lübnan usulü)
- Watermelon Feta Mint Salad
- Asian Sesame Noodle Salad
- Moroccan Carrot Salad
- Mediterranean Chickpea Salad
- Cobb Salad
- Beet and Goat Cheese Salad
- Waldorf Salad
- Nicoise Salad
- Israeli Couscous Salad
""",
    },
]

# Makro hesaplama için kılavuz
MACRO_GUIDE = """
ÖNEMLİ: Her tarif için gerçekçi ve tutarlı makro değerleri ver.
Kalori tutarlılık kuralı: kalori ≈ (protein × 4) + (karbonhidrat × 4) + (yağ × 9)
Tolerans: ±%10 (fark 15 kcal'i geçmesin)

Gerçekçi referans değerler:
- Tavuk göğsü 100g: ~165 kcal, 31g protein, 0g karb, 3.6g yağ
- Somon 100g: ~208 kcal, 20g protein, 0g karb, 13g yağ
- Ton balığı konserve 100g: ~132 kcal, 29g protein, 0g karb, 1g yağ
- Yulaf 100g kuru: ~389 kcal, 17g protein, 66g karb, 7g yağ
- Quinoa 100g pişmiş: ~120 kcal, 4g protein, 21g karb, 2g yağ
- Avokado 100g: ~160 kcal, 2g protein, 9g karb, 15g yağ
- Nohut 100g pişmiş: ~164 kcal, 9g protein, 27g karb, 3g yağ
- Fıstık ezmesi 30g: ~188 kcal, 8g protein, 6g karb, 16g yağ
- Yunan yoğurdu 100g: ~59 kcal, 10g protein, 4g karb, 0g yağ
- Zeytinyağı 10g: ~88 kcal, 0g protein, 0g karb, 10g yağ
- Pirinç 100g pişmiş: ~130 kcal, 2.7g protein, 28g karb, 0.3g yağ
- Makarna 100g pişmiş: ~158 kcal, 6g protein, 31g karb, 1g yağ
"""

RECIPE_FORMAT = """
JSON array döndür. Her tarif şu alanlara sahip olmalı:
{
  "id": "snake_case_ingilizce_id",
  "ad": "Türkçe veya Orijinal İsim (örn: 'Açaí Bowl', 'Teriyaki Somon')",
  "kategori": "kahvalti|ana_yemek_tavuk|ana_yemek_balik|ana_yemek_et|salata|corba|ara_ogun",
  "malzemeler": ["malzeme1", "malzeme2", ...],
  "porsiyon_gram": 300,
  "kalori": 380,
  "protein_g": 25.0,
  "karbonhidrat_g": 35.0,
  "yag_g": 12.0,
  "lif_g": 6.0,
  "saglik_etiketler": ["yüksek_protein", "glütensiz", "düşük_karbonhidrat", "omega3_zengin", ...],
  "ogun_tipleri": ["kahvalti"],
  "pismesi_dk": 15,
  "zorluk": "kolay",
  "aciklama": "Kısa Türkçe açıklama (1-2 cümle)"
}

Kalori kontrolü: kalori = round(protein*4 + karbonhidrat*4 + yağ*9)
"""


def _extract_json_array(text: str) -> list:
    """Claude yanıtından JSON array'i çıkar."""
    # ```json ... ``` bloğu varsa al
    m = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # Direkt [ ... ] array
    m = re.search(r'\[.*\]', text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError("JSON array bulunamadı")


def _normalize_id(text: str) -> str:
    """Tarif adından slug ID üret."""
    import unicodedata
    tr_map = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosucgiosu')
    text = text.lower().translate(tr_map)
    text = unicodedata.normalize('NFKD', text)
    text = re.sub(r'[^a-z0-9\s_]', '', text)
    text = re.sub(r'\s+', '_', text.strip())
    return text[:60]


def _fix_calories(recipe: dict) -> dict:
    """Kalori değerini makrolardan hesapla (tutarsızsa düzelt)."""
    p = float(recipe.get('protein_g') or 0)
    k = float(recipe.get('karbonhidrat_g') or 0)
    y = float(recipe.get('yag_g') or 0)
    expected = round(p * 4 + k * 4 + y * 9)
    actual = float(recipe.get('kalori') or 0)
    if actual == 0 or abs(actual - expected) > actual * 0.10:
        recipe['kalori'] = expected
    return recipe


def run_recipe_task(client: anthropic.Anthropic, task: dict) -> list:
    """Tek bir kategori görevi için Claude'u çağır, tarifleri döndür."""
    prompt = f"""Sen uzman bir diyetisyen ve dünya mutfağı uzmanısın.

{task['description']} üret. Tam olarak {task['count']} tarif istiyorum.

Kapsam:
{task['prompt_hint']}

{MACRO_GUIDE}

{RECIPE_FORMAT}

Kategori: {task['kategori']}
Öğün tipleri: {json.dumps(task['ogun_tipleri'], ensure_ascii=False)}

SADECE JSON array döndür, başka açıklama yazma."""

    logger.info(f"  Görev çalıştırılıyor: {task['task_id']} ({task['count']} tarif)...")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text
    recipes = _extract_json_array(raw)
    logger.info(f"  {len(recipes)} tarif alındı")
    return recipes


def validate_and_fix(recipes: list, task: dict) -> tuple[list, list]:
    """Tarifleri doğrula, geçerlileri döndür, hatalıları raporla."""
    valid = []
    errors = []

    for r in recipes:
        # ID normalizasyonu
        if not r.get('id'):
            r['id'] = _normalize_id(r.get('ad', 'recipe'))
        else:
            r['id'] = _normalize_id(r['id'])

        # Kategori zorla
        if not r.get('kategori'):
            r['kategori'] = task['kategori']

        # Öğün tipleri zorla
        if not r.get('ogun_tipleri'):
            r['ogun_tipleri'] = task['ogun_tipleri']

        # Kalori düzelt
        r = _fix_calories(r)

        # Validasyon
        errs = validate(r)
        if errs:
            errors.append({'id': r.get('id'), 'ad': r.get('ad'), 'errors': errs})
        else:
            valid.append(r)

    return valid, errors


def merge_with_existing(new_recipes: list, existing_path: str = "recipes.json") -> int:
    """Yeni tarifleri recipes.json'a ekle (duplicate ID'leri atla)."""
    path = Path(existing_path)
    if not path.exists():
        logger.error(f"{existing_path} bulunamadı")
        return 0

    with open(path, encoding='utf-8') as f:
        existing = json.load(f)

    existing_ids = {r.get('id') for r in existing}
    existing_names = {r.get('ad', '').lower() for r in existing}

    added = 0
    for r in new_recipes:
        rid = r.get('id', '')
        rname = r.get('ad', '').lower()
        if rid in existing_ids or rname in existing_names:
            logger.debug(f"  Atlandı (duplicate): {r.get('ad')}")
            continue
        existing.append(r)
        existing_ids.add(rid)
        existing_names.add(rname)
        added += 1

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    logger.info(f"recipes.json güncellendi: {added} yeni tarif eklendi (toplam: {len(existing)})")
    return added


def main():
    parser = argparse.ArgumentParser(description="Uluslararası trend tarif generator")
    parser.add_argument('--merge', action='store_true',
                        help="Oluşturulan tarifleri recipes.json ile birleştir")
    parser.add_argument('--output', default='international_recipes.json',
                        help="Çıktı dosyası (varsayılan: international_recipes.json)")
    parser.add_argument('--tasks', nargs='+',
                        help="Sadece belirli görev ID'lerini çalıştır")
    args = parser.parse_args()

    import os
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        # settings.py'den almayı dene
        try:
            from settings import Settings
            s = Settings()
            api_key = s.anthropic_api_key
        except Exception:
            pass
    if not api_key:
        logger.error("ANTHROPIC_API_KEY bulunamadı")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    tasks = RECIPE_TASKS
    if args.tasks:
        tasks = [t for t in tasks if t['task_id'] in args.tasks]
        if not tasks:
            logger.error(f"Geçerli görev bulunamadı: {args.tasks}")
            sys.exit(1)

    all_valid = []
    all_errors = []

    for task in tasks:
        logger.info(f"\n=== {task['task_id']} ===")
        try:
            recipes = run_recipe_task(client, task)
            valid, errors = validate_and_fix(recipes, task)
            logger.info(f"  Geçerli: {len(valid)} | Hatalı: {len(errors)}")
            if errors:
                for e in errors:
                    logger.warning(f"  HATA [{e['id']}]: {e['errors']}")
            all_valid.extend(valid)
            all_errors.extend(errors)
        except Exception as e:
            logger.error(f"  Görev başarısız: {e}")

    # Çıktı dosyasına yaz
    output_path = Path(args.output)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_valid, f, ensure_ascii=False, indent=2)
    logger.info(f"\nToplam {len(all_valid)} geçerli tarif → {output_path}")
    if all_errors:
        logger.warning(f"Toplam {len(all_errors)} hatalı tarif atlandı")

    # Merge
    if args.merge:
        logger.info("\nrecipes.json ile birleştiriliyor...")
        merge_with_existing(all_valid)

    return 0


if __name__ == '__main__':
    sys.exit(main())
