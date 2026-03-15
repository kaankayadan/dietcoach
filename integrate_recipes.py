#!/usr/bin/env python3
"""
Agent tarafından üretilen tarifleri recipes.json'a entegre eder.
"""
import json
import re
import unicodedata
import sys
from pathlib import Path

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def normalize_id(s: str) -> str:
    """Turkish string → snake_case ASCII id."""
    # Map Turkish chars manually (equal length pairs)
    tr_from = "çğışöüÇĞIŞÖÜ"
    tr_to   = "cgisouCGISOu"  # 12 chars each
    assert len(tr_from) == len(tr_to), f"{len(tr_from)} vs {len(tr_to)}"
    tr_map = str.maketrans(tr_from, tr_to)
    s = s.translate(tr_map)
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^a-z0-9_]', '_', s.lower())
    s = re.sub(r'_+', '_', s).strip('_')
    return s


OGUN_FIX = {
    "sabah":        "kahvalti",
    "öğle":         "ogle",
    "aksam":        "aksam",
    "ara_ogun_yani": "ara_ogun",
    "ana_ogun_yanı": "ara_ogun",
    "ana_ogun_yani": "ara_ogun",
    "tamamlayici":  "tamamlayici",
    "kahvalti":     "kahvalti",
    "ogle":         "ogle",
    "ara_ogun":     "ara_ogun",
}

VALID_OGUNLER = {"kahvalti", "ogle", "aksam", "ara_ogun", "tamamlayici"}


def fix_ogun(ogun_list: list) -> list:
    result = []
    for o in ogun_list:
        o_norm = o.strip().lower()
        o_norm = normalize_id(o_norm)
        mapped = OGUN_FIX.get(o_norm, o_norm)
        if mapped in VALID_OGUNLER:
            result.append(mapped)
    return list(dict.fromkeys(result))  # deduplicate preserving order


def auto_fix_kalori(recipe: dict) -> dict:
    """If calorie deviates >8%, set kalori = P*4+K*4+Y*9 (rounded)."""
    p = float(recipe.get("protein_g") or 0)
    k = float(recipe.get("karbonhidrat_g") or 0)
    y = float(recipe.get("yag_g") or 0)
    kal = float(recipe.get("kalori") or 0)
    expected = p * 4 + k * 4 + y * 9
    if kal > 0 and abs(kal - expected) > kal * 0.08:
        recipe = dict(recipe)
        recipe["kalori"] = round(expected)
    return recipe


# ------------------------------------------------------------------
# Parse agent output files (JSONL format)
# ------------------------------------------------------------------

def parse_output_file(path: str) -> list:
    """Extract recipe JSON arrays from an agent JSONL output file."""
    recipes = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "assistant":
                continue
            msg = obj.get("message", {})
            content = msg.get("content", [])
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    # Find JSON arrays in text
                    for m in re.finditer(r'\[\s*\{', text):
                        start = m.start()
                        # Find matching closing bracket
                        depth = 0
                        end = start
                        for i, c in enumerate(text[start:]):
                            if c == '[':
                                depth += 1
                            elif c == ']':
                                depth -= 1
                                if depth == 0:
                                    end = start + i + 1
                                    break
                        if end > start:
                            try:
                                arr = json.loads(text[start:end])
                                if isinstance(arr, list) and arr:
                                    recipes.extend(arr)
                            except json.JSONDecodeError:
                                pass
    return recipes


# ------------------------------------------------------------------
# Main integration logic
# ------------------------------------------------------------------

def main():
    output_files = [
        "/tmp/claude-0/-home-user-dietcoach/14f7bd3b-e47c-42ce-ad5a-52ec29719538/tasks/ad8263b3abcfdb96b.output",  # kahvaltı
        "/tmp/claude-0/-home-user-dietcoach/14f7bd3b-e47c-42ce-ad5a-52ec29719538/tasks/adafd0aefd0ef0898.output",  # balık
        "/tmp/claude-0/-home-user-dietcoach/14f7bd3b-e47c-42ce-ad5a-52ec29719538/tasks/adf8ba0a354464a9b.output",  # tavuk/et
        "/tmp/claude-0/-home-user-dietcoach/14f7bd3b-e47c-42ce-ad5a-52ec29719538/tasks/a1bd4547123ae3519.output",  # çorba/salata
        "/tmp/claude-0/-home-user-dietcoach/14f7bd3b-e47c-42ce-ad5a-52ec29719538/tasks/a888f6cc14b901289.output",  # sebze/baklagil
        "/tmp/claude-0/-home-user-dietcoach/14f7bd3b-e47c-42ce-ad5a-52ec29719538/tasks/a22bcf591ab15b779.output",  # ara öğün/yogurtlu
    ]

    # Load existing recipes
    with open("/home/user/dietcoach/recipes.json", encoding="utf-8") as f:
        existing = json.load(f)

    existing_ids = {r.get("id", r.get("tarif_id", "")) for r in existing}
    existing_names = {r.get("ad", "").strip().lower() for r in existing}
    print(f"Mevcut tarif: {len(existing)}")

    # Parse all agent outputs
    all_new = []
    for path in output_files:
        if not Path(path).exists():
            print(f"UYARI: Dosya bulunamadı: {path}")
            continue
        batch = parse_output_file(path)
        print(f"  {Path(path).stem}: {len(batch)} tarif okundu")
        all_new.extend(batch)

    print(f"\nToplam ham tarif: {len(all_new)}")

    # Normalize, fix and deduplicate
    seen_ids = set(existing_ids)
    seen_names = set(existing_names)
    valid_new = []
    skipped = []

    for r in all_new:
        # Determine name
        ad = str(r.get("ad", "")).strip()
        if not ad:
            skipped.append((r, "ad eksik"))
            continue

        # Generate/fix id
        raw_id = r.get("id") or r.get("tarif_id") or normalize_id(ad)
        r_id = normalize_id(str(raw_id))

        # Normalize ogun_tipleri
        ogun = r.get("ogun_tipleri", [])
        if isinstance(ogun, str):
            ogun = [ogun]
        r["ogun_tipleri"] = fix_ogun(ogun)

        # Ensure kategori exists
        if not r.get("kategori"):
            skipped.append((r, "kategori eksik"))
            continue

        # Auto-fix kalori
        r = auto_fix_kalori(r)
        r["id"] = r_id
        r.pop("tarif_id", None)

        # Duplicate check
        if r_id in seen_ids:
            skipped.append((r, f"id çakışıyor: {r_id}"))
            continue
        if ad.lower() in seen_names:
            skipped.append((r, f"ad çakışıyor: {ad}"))
            continue

        seen_ids.add(r_id)
        seen_names.add(ad.lower())
        valid_new.append(r)

    print(f"Geçerli yeni tarif: {len(valid_new)}")
    print(f"Atlanan: {len(skipped)}")
    if skipped:
        for r, reason in skipped[:20]:
            print(f"  - {r.get('ad','?')}: {reason}")

    if not valid_new:
        print("\nEklenecek tarif yok, çıkılıyor.")
        return 1

    # Validate new recipes using validate_recipes logic
    sys.path.insert(0, "/home/user/dietcoach")
    from validate_recipes import validate

    errors_count = 0
    final_new = []
    for r in valid_new:
        errs = validate(r)
        if errs:
            errors_count += 1
            # Still add but print warnings
            print(f"  UYARI [{r['id']}] {r.get('ad','?')}: {'; '.join(errs)}")
        final_new.append(r)

    print(f"\nDoğrulama: {errors_count} uyarılı tarif ({len(final_new)} toplam ekleniyor)")

    # Merge and save
    merged = existing + final_new
    with open("/home/user/dietcoach/recipes.json", "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"\nKaydedildi: {len(merged)} toplam tarif (önceki: {len(existing)}, yeni: {len(final_new)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
