"""
Kullanıcı Hedef Hesaplayıcı — Onboarding verilerinden BMR, TDEE, makro hedeflerini hesaplar.

Tüm formüller prompts/system_prompt.md ile senkron:
- BMR: Katch-McArdle (VYO varsa) veya Mifflin-St Jeor
- TDEE: BMR + NEAT + TEF + EAT
- Protein: LBM bazında, hedef tipine göre 1.6-2.0 g/kg
- Yağ: Standart kilo × 1.0, safra → kilo × 0.6
- Karbonhidrat: Kalan kaloriyi doldur
"""
import logging

logger = logging.getLogger(__name__)


def _safe_float(val, default=0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=0) -> int:
    if val is None:
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def calculate_user_targets(data: dict) -> dict:
    """
    Onboarding verisinden BMR, TDEE, makro hedeflerini deterministik hesapla.

    Args:
        data: Onboarding sürecinde toplanan veriler (kilo_kg, boy_cm, yas, cinsiyet, ...)

    Returns:
        Hesaplanmış hedefler dict'i. Eksik veri varsa boş dict döner.
    """
    kilo = _safe_float(data.get("kilo_kg"))
    boy = _safe_float(data.get("boy_cm"))
    yas = _safe_int(data.get("yas"))
    cinsiyet = str(data.get("cinsiyet", "")).lower().strip()
    vyo = _safe_float(data.get("vucut_yag_orani"))
    aktivite = str(data.get("aktivite_seviyesi", "")).lower().strip()
    hedef_tip = str(data.get("hedef_tip", "koruma")).lower().strip()
    agresiflik = str(data.get("agresiflik", "dengeli")).lower().strip()

    if not kilo or not boy or not yas:
        logger.warning(
            f"Hedef hesaplama: eksik veri (kilo={kilo}, boy={boy}, yas={yas})"
        )
        return {}

    # ── LBM (Yağsız Kütle) ──
    lbm = None
    if vyo and vyo > 0:
        lbm = kilo * (1 - vyo / 100)

    # ── BMR ──
    if lbm:
        # Katch-McArdle
        bmr = 370 + (21.6 * lbm)
    else:
        # Mifflin-St Jeor
        if cinsiyet in ("erkek", "male", "e"):
            bmr = (10 * kilo) + (6.25 * boy) - (5 * yas) + 5
        else:
            bmr = (10 * kilo) + (6.25 * boy) - (5 * yas) - 161

    # ── NEAT ──
    neat_map = {
        "masa_basi": 0.20,
        "masa başı": 0.20,
        "sedanter": 0.20,
        "hafif_aktif": 0.35,
        "hafif aktif": 0.35,
        "aktif": 0.50,
        "cok_aktif": 0.65,
        "çok_aktif": 0.65,
        "çok aktif": 0.65,
    }
    neat_factor = 0.20
    for key, val in neat_map.items():
        if key in aktivite:
            neat_factor = val
            break
    neat = bmr * neat_factor

    # ── TEF ──
    tef = bmr * 0.10

    # ── EAT (basitleştirilmiş) ──
    eat = 0.0
    # Aktivite bilgileri varsa MET hesabı
    akt_bilgi = data.get("aktivite_bilgileri")
    if isinstance(akt_bilgi, dict):
        met = _safe_float(akt_bilgi.get("met", akt_bilgi.get("met_degeri")))
        siklik = _safe_int(akt_bilgi.get("siklik", akt_bilgi.get("haftalik_siklik")))
        sure_dk = _safe_int(akt_bilgi.get("sure_dk", akt_bilgi.get("sure")))
        if met > 0 and siklik > 0 and sure_dk > 0:
            sure_saat = sure_dk / 60.0
            eat = (met * kilo * sure_saat * siklik) / 7.0

    # ── TDEE ──
    tdee = bmr + neat + tef + eat

    # ── Hedef Kalori ──
    kayip = any(k in hedef_tip for k in ("kayıp", "kayip", "ver", "loss", "azalt"))
    kazanim = any(
        k in hedef_tip for k in ("kazanım", "kazanim", "al", "bulk", "artır", "artir")
    )

    if kayip:
        if any(
            a in agresiflik for a in ("agresif", "hızlı", "hizli", "yüksek", "yuksek")
        ):
            hedef_kalori = tdee * 0.75
        elif any(
            a in agresiflik for a in ("yavaş", "yavas", "düşük", "dusuk", "az")
        ):
            hedef_kalori = tdee * 0.85
        else:
            hedef_kalori = tdee * 0.80
    elif kazanim:
        if any(a in agresiflik for a in ("agresif", "hızlı", "hizli")):
            hedef_kalori = tdee * 1.20
        elif any(a in agresiflik for a in ("yavaş", "yavas")):
            hedef_kalori = tdee * 1.10
        else:
            hedef_kalori = tdee * 1.15
    else:
        hedef_kalori = tdee

    # Minimum kalori sınırı
    if cinsiyet in ("erkek", "male", "e"):
        hedef_kalori = max(hedef_kalori, 1500)
    else:
        hedef_kalori = max(hedef_kalori, 1200)

    # ── Protein (LBM bazında) ──
    hastaliklar = str(data.get("kronik_hastaliklar", "")).lower()

    if lbm:
        if kayip or kazanim:
            protein_g = lbm * 2.0
        else:
            protein_g = lbm * 1.6
    else:
        if kayip or kazanim:
            protein_g = kilo * 1.6
        else:
            protein_g = kilo * 1.2

    # Protein kcal sınırı: max %35
    if protein_g * 4 > hedef_kalori * 0.35:
        protein_g = (hedef_kalori * 0.35) / 4

    # Böbrek sorunu
    if "böbrek" in hastaliklar or "bobrek" in hastaliklar:
        protein_g = min(protein_g, kilo * 0.8)

    # ── Yağ ──
    if "safra" in hastaliklar:
        yag_g = min(kilo * 0.6, 40)
    else:
        yag_g = kilo * 1.0

    # ── Karbonhidrat ──
    kalan_kcal = hedef_kalori - (protein_g * 4) - (yag_g * 9)
    karbonhidrat_g = max(kalan_kcal / 4, 50)

    # Diyabet: max %40 karb
    if "diyabet" in hastaliklar:
        max_karb_g = (hedef_kalori * 0.40) / 4
        karbonhidrat_g = min(karbonhidrat_g, max_karb_g)

    # ── Lif ──
    if cinsiyet in ("erkek", "male", "e"):
        lif_g = max(30, round(14 * hedef_kalori / 1000))
    else:
        lif_g = max(25, round(14 * hedef_kalori / 1000))

    # ── Su Hedefi ──
    su_hedefi_litre = round(kilo * 0.033, 1)

    result = {
        "bmr": round(bmr, 1),
        "neat": round(neat, 1),
        "tef": round(tef, 1),
        "eat_gunluk": round(eat, 1),
        "tdee": round(tdee, 1),
        "hedef_kalori": round(hedef_kalori, 1),
        "protein_g": round(protein_g, 1),
        "karbonhidrat_g": round(karbonhidrat_g, 1),
        "yag_g": round(yag_g, 1),
        "lif_g": round(lif_g, 1),
        "su_hedefi_litre": su_hedefi_litre,
    }

    if lbm:
        result["yagsiz_kutle_kg"] = round(lbm, 1)

    logger.info(
        f"Hedef hesaplama tamamlandı: BMR={result['bmr']} → TDEE={result['tdee']} → "
        f"Hedef={result['hedef_kalori']} kcal | "
        f"P:{result['protein_g']}g K:{result['karbonhidrat_g']}g Y:{result['yag_g']}g L:{result['lif_g']}g"
    )

    return result
