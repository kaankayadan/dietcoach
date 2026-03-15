"""
Tarif makro doğrulama scripti.
Mevcut ve yeni eklenen tariflerin tutarlılığını kontrol eder.

Kurallar:
  1. Kalori tutarlılığı : |kal - (P*4 + K*4 + Y*9)| <= kal * tolerans
  2. Gram başı kalori  : min_kcal_g <= kal/porsiyon_gram <= max_kcal_g
  3. Protein üst sınır : P <= porsiyon_gram * 0.45
  4. Lif tutarlılığı   : L <= K
  5. Lif makul         : L <= 30 (tek öğün)
  6. Negatif değer yok : P, K, Y, L >= 0
  7. Zorunlu alanlar   : id, ad, kategori, kalori, protein_g, karbonhidrat_g, yag_g

Kategori bazlı toleranslar:
  - Çorba/sıvı/icecek: min kcal/g 0.2 (yüksek su içeriği)
  - Meyve/süt ürünleri: kalori toleransı %15 (fiber & organik asit düzeltmesi)
  - Kuruyemiş: max kcal/g 7.0
"""
import json
import sys

# Kategori bazlı eşikler (yoksa _DEFAULT kullanılır)
_CAT_RULES: dict = {
    "corba":        {"min_kcal_g": 0.20, "tol": 0.10},
    "icecek":       {"min_kcal_g": 0.20, "tol": 0.15},
    "ara_ogun":     {"min_kcal_g": 0.30, "max_kcal_g": 7.0, "tol": 0.12},  # kuruyemis
    "yogurtlu":     {"min_kcal_g": 0.30, "tol": 0.15},
    "tamamlayici":  {"min_kcal_g": 0.30, "tol": 0.15},   # meyve/ekmek
    "salata":       {"min_kcal_g": 0.25, "tol": 0.10},
    "sebze_yemegi": {"min_kcal_g": 0.30, "tol": 0.10},   # brokoli gibi dusuk yogunluk
}
_DEFAULT = {"min_kcal_g": 0.50, "max_kcal_g": 5.5, "tol": 0.08}


def _rules(kategori: str) -> dict:
    base = dict(_DEFAULT)
    base.update(_CAT_RULES.get(kategori, {}))
    return base


def validate(recipe: dict) -> list:
    errors = []
    kat = recipe.get("kategori", "")
    rules = _rules(kat)

    # Zorunlu alanlar
    for field in ["id", "ad", "kategori", "kalori", "protein_g", "karbonhidrat_g", "yag_g"]:
        if recipe.get(field) is None:
            errors.append(f"Eksik alan: {field}")

    kal = float(recipe.get("kalori") or 0)
    p   = float(recipe.get("protein_g") or 0)
    k   = float(recipe.get("karbonhidrat_g") or 0)
    y   = float(recipe.get("yag_g") or 0)
    l   = float(recipe.get("lif_g") or 0)
    por = float(recipe.get("porsiyon_gram") or 0)

    # Negatif değer yok
    for name, val in [("kalori", kal), ("protein_g", p), ("karbonhidrat_g", k),
                      ("yag_g", y), ("lif_g", l), ("porsiyon_gram", por)]:
        if val < 0:
            errors.append(f"{name} negatif olamaz ({val})")

    if kal == 0:
        errors.append("kalori sıfır")
        return errors

    # 1. Kalori tutarlılığı
    expected = p * 4 + k * 4 + y * 9
    tol = rules["tol"]
    if abs(kal - expected) > kal * tol:
        errors.append(
            f"Kalori tutarsız: {kal} kcal, beklenen ≈ {expected:.1f} "
            f"(P:{p}x4 + K:{k}x4 + Y:{y}x9) — fark:{abs(kal-expected):.1f} "
            f"(tolerans %{int(tol*100)})"
        )

    # 2. Gram başı kalori
    if por > 0:
        ratio = kal / por
        min_g = rules["min_kcal_g"]
        max_g = rules.get("max_kcal_g", _DEFAULT["max_kcal_g"])
        if ratio < min_g or ratio > max_g:
            errors.append(
                f"Gram basi kalori anormal: {ratio:.2f} kcal/g "
                f"(beklenen {min_g}-{max_g}, kategori:{kat})"
            )

        # 3. Protein üst sınır
        if p > por * 0.45:
            errors.append(f"Protein cok yuksek: {p}g (porsiyon {por}g)")

    # 4. Lif tutarlılığı
    if l > k + 0.5:
        errors.append(f"Lif karbdan fazla olamaz: L:{l}g > K:{k}g")
    if l > 30:
        errors.append(f"Lif degeri anormal yuksek: {l}g")

    return errors


def main(path: str = "recipes.json") -> int:
    with open(path, encoding="utf-8") as f:
        recipes = json.load(f)

    print(f"Toplam tarif: {len(recipes)}\n")

    # Kategori dağılımı
    cats = {}
    for r in recipes:
        c = r.get("kategori", "?")
        cats[c] = cats.get(c, 0) + 1
    print("── Kategori dagilimi ──────────────────────")
    for c, n in sorted(cats.items(), key=lambda x: -x[1]):
        bar = "#" * n
        print(f"  {c:<25} {n:>3}  {bar}")

    # Makro validasyon
    print("\n── Makro dogrulama ────────────────────────")
    all_ok = True
    err_count = 0
    for r in recipes:
        errs = validate(r)
        if errs:
            all_ok = False
            err_count += 1
            print(f"\n  x [{r.get('id','?')}] {r.get('ad','?')}")
            for e in errs:
                print(f"      -> {e}")

    if all_ok:
        print("  Tum tarifler gecti OK")
    else:
        print(f"\n  Toplam hatali tarif: {err_count}")

    # Makro istatistikleri
    print("\n── Makro istatistikleri ───────────────────")
    def stats(vals):
        if not vals:
            return "-"
        return f"ort:{sum(vals)/len(vals):.1f}  min:{min(vals):.1f}  max:{max(vals):.1f}"

    non_tam = [r for r in recipes if r.get("kategori") != "tamamlayici"]
    print(f"  Kalori  : {stats([float(r.get('kalori', 0)) for r in non_tam])}")
    print(f"  Protein : {stats([float(r.get('protein_g', 0)) for r in non_tam])}")
    print(f"  Karb    : {stats([float(r.get('karbonhidrat_g', 0)) for r in non_tam])}")
    print(f"  Yag     : {stats([float(r.get('yag_g', 0)) for r in non_tam])}")
    print(f"  Lif     : {stats([float(r.get('lif_g', 0)) for r in non_tam])}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "recipes.json"
    sys.exit(main(path))
