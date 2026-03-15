#!/usr/bin/env python3
"""
7 günlük plan simülasyonu — tarif çeşitliliği testi.
Plan algoritmasını taklit ederek her gün 3 ana öğün seçer ve
kaç tarifin kaç kez tekrar ettiğini raporlar.
"""
import json
import random
from collections import Counter

# ------------------------------------------------------------------
# Scoring (simplified clone of claude_client._macro_fit_score)
# ------------------------------------------------------------------

def macro_fit_score(recipe: dict, hedef: dict) -> float:
    p = float(recipe.get("protein_g") or 0)
    k = float(recipe.get("karbonhidrat_g") or 0)
    y = float(recipe.get("yag_g") or 0)
    kal = float(recipe.get("kalori") or 1)

    hp = hedef.get("protein_g", 0)
    hk = hedef.get("karbonhidrat_g", 0)
    hy = hedef.get("yag_g", 0)
    hkal = max(hedef.get("kalori", 1), 1)

    def dev(actual, target):
        if target == 0:
            return 0.0
        return abs(actual - target) / target

    p_score = max(0, 1 - dev(p, hp))
    k_score = max(0, 1 - dev(k, hk))
    y_score = max(0, 1 - dev(y, hy))

    return 0.40 * p_score + 0.35 * k_score + 0.25 * y_score


def pick_meal(candidates: list, hedef: dict, used_today: set, used_week: dict,
              top_n: int = 5) -> dict:
    """Score + exclude today's picks; penalise recent week repeats."""
    scored = []
    for r in candidates:
        rid = r.get("id")
        if rid in used_today:
            continue
        score = macro_fit_score(r, hedef)
        # Penalise recipes used in last 3 days
        repeat_count = used_week.get(rid, 0)
        score *= max(0.1, 1.0 - 0.25 * repeat_count)
        scored.append((score, r))

    scored.sort(key=lambda x: -x[0])
    pool = scored[:top_n]
    if not pool:
        pool = scored[:1]
    if not pool:
        return None
    # Weighted random from top_n
    weights = [s for s, _ in pool]
    total = sum(weights) or 1
    pick = random.choices([r for _, r in pool], weights=[w / total for w in weights])[0]
    return pick


# ------------------------------------------------------------------
# Simulate 7 days
# ------------------------------------------------------------------

def simulate(recipes: list, days: int = 7, seed: int = 42) -> None:
    random.seed(seed)

    # Example user targets (2000 kcal, 40/30/30 macro split)
    ogun_targets = {
        "kahvalti": {"kalori": 400, "protein_g": 20, "karbonhidrat_g": 45, "yag_g": 13},
        "ogle":     {"kalori": 650, "protein_g": 35, "karbonhidrat_g": 70, "yag_g": 20},
        "aksam":    {"kalori": 600, "protein_g": 35, "karbonhidrat_g": 55, "yag_g": 20},
    }

    # Bucket recipes by meal type
    def buckets(ogun_tip: str) -> list:
        return [r for r in recipes if ogun_tip in (r.get("ogun_tipleri") or [])
                or r.get("kategori") == ogun_tip]

    kahvalti_pool = buckets("kahvalti")
    ogle_pool = [r for r in recipes if "ogle" in (r.get("ogun_tipleri") or [])
                 or r.get("kategori") in ("ana_yemek_tavuk", "ana_yemek_et",
                                           "ana_yemek_balik", "sebze_yemegi",
                                           "baklagil", "ogle")]
    aksam_pool = [r for r in recipes if "aksam" in (r.get("ogun_tipleri") or [])
                  or r.get("kategori") in ("ana_yemek_tavuk", "ana_yemek_et",
                                            "ana_yemek_balik", "sebze_yemegi",
                                            "baklagil", "aksam")]

    print(f"Havuz büyüklükleri  → kahvaltı:{len(kahvalti_pool)}  "
          f"öğle:{len(ogle_pool)}  akşam:{len(aksam_pool)}")
    print()

    week_counter: Counter = Counter()   # id → total uses over week
    daily_usage: dict = {}              # day → {ogun: recipe}
    repeat_ids: list = []

    for day in range(1, days + 1):
        used_today: set = set()
        week_past3 = {rid: week_counter[rid] for rid in week_counter}

        day_meals = {}
        for ogun, pool in [("kahvalti", kahvalti_pool),
                            ("ogle", ogle_pool),
                            ("aksam", aksam_pool)]:
            pick = pick_meal(pool, ogun_targets[ogun], used_today, week_past3)
            if pick:
                rid = pick["id"]
                day_meals[ogun] = pick
                used_today.add(rid)
                week_counter[rid] += 1
                if week_counter[rid] > 1:
                    repeat_ids.append(rid)

        daily_usage[day] = day_meals
        kal = sum(float(r.get("kalori", 0)) for r in day_meals.values())
        print(f"Gün {day}  ({kal:.0f} kcal)")
        for ogun in ("kahvalti", "ogle", "aksam"):
            r = day_meals.get(ogun)
            if r:
                print(f"  {ogun:<10} {r.get('ad','?')[:45]:<46} [{r['id']}]")

    # Summary
    print("\n── Çeşitlilik raporu ───────────────────────────────────────")
    total_slots = days * 3
    unique_recipes = len(week_counter)
    repeated = {rid: cnt for rid, cnt in week_counter.items() if cnt > 1}

    print(f"  Toplam öğün        : {total_slots}")
    print(f"  Benzersiz tarif    : {unique_recipes}")
    print(f"  Tekrar eden tarif  : {len(repeated)}")
    if repeated:
        print("  Tekrarlar:")
        for rid, cnt in sorted(repeated.items(), key=lambda x: -x[1]):
            ad = next((r.get("ad") for r in recipes if r.get("id") == rid), rid)
            print(f"    {rid:<40} {cnt}x  — {ad}")

    diversity_score = unique_recipes / total_slots * 100
    print(f"\n  Çeşitlilik skoru   : {diversity_score:.0f}%  "
          f"({'İYİ' if diversity_score >= 80 else 'ORTA' if diversity_score >= 60 else 'DÜŞÜK'})")


if __name__ == "__main__":
    with open("/home/user/dietcoach/recipes.json", encoding="utf-8") as f:
        recipes = json.load(f)
    simulate(recipes)
