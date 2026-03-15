"""
Claude API Client — Her çağrıda kullanıcının güncel profilini ve tarif veritabanından
semantik olarak seçilmiş yemekleri context olarak gönderir.

RAG (Retrieval Augmented Generation) akışı:
1. Kullanıcı mesajı + profil bilgisi → embedding sorgusu oluşturulur
2. pgvector'dan en uygun tarifler çekilir (benzerlik + çeşitlilik)
3. Tarifler + kullanıcı context'i → Claude'a gönderilir
4. Claude gerçek tariflerden seçim yaparak daha tutarlı öneriler üretir
"""
import logging
from pathlib import Path
from datetime import date

from embeddings import embedder

logger = logging.getLogger(__name__)

# Her öğünün günlük kalori hedefinden alacağı pay (toplam 1.0)
# Normalizasyon, aktif öğün sayısına göre chat() içinde yapılır.
_RAW_OGUN_PAYLARI = {
    'kahvalti': 0.30,
    'ogle':     0.35,
    'aksam':    0.25,
    'ara_ogun': 0.10,
}


class ClaudeClient:
    def __init__(self, api_key: str, system_prompt_path: str):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.system_prompt = Path(system_prompt_path).read_text(encoding="utf-8")
        # Basit sorgular için ucuz model, plan oluşturma için güçlü model
        self.model_light = "claude-haiku-4-5-20251001"    # Besin sorgusu, kısa yanıt
        self.model_heavy = "claude-sonnet-4-5-20250929"   # Plan oluşturma, onboarding

    def _build_user_context(self, user: dict, recent_meals: list,
                            daily_summary: dict, weekly_summary: dict,
                            todays_plan: dict) -> str:
        """
        Kullanıcının güncel verilerini Claude'a gönderilecek context string'ine dönüştürür.
        Bu fonksiyon her mesajda çağrılır — Claude bu sayede kullanıcıyı 'tanır'.
        """
        if not user:
            return "Kullanıcı henüz kayıtlı değil."

        ctx_parts = []

        # -- Profil --
        ctx_parts.append(f"""## Kullanıcı Profili
İsim: {user.get('isim', 'Bilinmiyor')}
Yaş: {user.get('yas')} | Cinsiyet: {user.get('cinsiyet')}
Boy: {user.get('boy_cm')} cm | Kilo: {user.get('kilo_kg')} kg
Vücut Yağ Oranı: %{user.get('vucut_yag_orani')} | Yağsız Kütle: {user.get('yagsiz_kutle_kg')} kg
Aktivite: {user.get('aktivite_seviyesi')}
Hedef: {user.get('hedef_tip')} | Hedef Kilo: {user.get('hedef_kilo', 'Belirtilmedi')} kg
Mutfak Stili: {user.get('mutfak_stili')} | Öğün Düzeni: {user.get('ogun_duzeni')}
Sevilen: {', '.join(user.get('sevilen_yiyecekler', []) or [])}
Sevilmeyen: {', '.join(user.get('sevilmeyen_yiyecekler', []) or [])}""")

        # -- Sağlık --
        hastaliklar = user.get('kronik_hastaliklar') or []
        sindirim = user.get('sindirim_sorunlari') or []
        alerjiler = user.get('alerjiler') or []
        ilaclar = user.get('ilaclar') or []
        if hastaliklar or sindirim or alerjiler or ilaclar:
            ctx_parts.append(f"""## Sağlık Durumu
Kronik: {', '.join(hastaliklar) if hastaliklar else 'Yok'}
Sindirim: {', '.join(sindirim) if sindirim else 'Yok'}
Alerjiler: {', '.join(alerjiler) if alerjiler else 'Yok'}
İlaçlar: {ilaclar if ilaclar else 'Yok'}""")

        # -- Metabolik Değerler --
        if user.get('bmr'):
            ctx_parts.append(f"""## Metabolik Değerler
BMR: {user['bmr']} kcal | TDEE: {user['tdee']} kcal
Hedef Kalori: {user['hedef_kalori']} kcal
Protein: {user['protein_g']}g | Karb: {user['karbonhidrat_g']}g | Yağ: {user['yag_g']}g | Lif: {user['lif_g']}g""")

        # -- Bugünkü Plan --
        if todays_plan:
            ctx_parts.append(f"""## Bugünkü Plan
{todays_plan.get('plan_detay', 'Plan henüz oluşturulmadı')}""")

        # -- Son Öğün Kayıtları (bugün) --
        if recent_meals:
            meal_lines = []
            for m in recent_meals:
                meal_lines.append(
                    f"- {m['ogun_tipi']}: {m['aciklama']} "
                    f"({m['kalori']} kcal, P:{m['protein']}g K:{m['karbonhidrat']}g Y:{m['yag']}g)"
                )
            ctx_parts.append(f"""## Bugün Yenilenler
{chr(10).join(meal_lines)}""")

        # -- Günlük Özet --
        if daily_summary:
            ctx_parts.append(f"""## Günlük Durum
Planlanan: {daily_summary.get('planlanan_kalori')} kcal
Tüketilen: {daily_summary.get('tuketilen_kalori')} kcal
Sapma: {daily_summary.get('sapma_kalori')} kcal
Su: {daily_summary.get('su_litre', 0)} litre""")

        # -- Haftalık Özet --
        if weekly_summary:
            ctx_parts.append(f"""## Bu Hafta Özet
Uyum Oranı: %{weekly_summary.get('uyum_orani')}
Toplam Sapma: {weekly_summary.get('toplam_sapma')} kcal
Kilo Değişimi: {weekly_summary.get('kilo_degisimi', 'Tartılmadı')} kg
Telafi: {'Evet, günlük ' + str(weekly_summary.get('telafi_miktari_gunluk')) + ' kcal' if weekly_summary.get('telafi_uygulanacak') else 'Gerek yok'}""")

        # -- Onboarding durumu --
        step = user.get('onboarding_step', 0)
        if step > 0 and step < 99:
            ctx_parts.append(f"""## Onboarding Durumu
Mevcut adım: {step}/15
Toplanan veriler: {user.get('onboarding_data', {})}""")

        # -- Bugünün tarihi --
        ctx_parts.append(f"\n## Tarih: {date.today().isoformat()} ({self._gun_adi()})")

        return "\n\n".join(ctx_parts)

    def _format_plan_skeleton(self, selected_meals: dict, user: dict,
                              meal_factors: dict,
                              tamamlayicilar: dict = None) -> str:
        """
        Plan verisini Python'da tam olarak formatlar.
        Claude bu metne sadece giriş cümlesi ve pratik notlar ekler —
        tarif adı, malzeme veya makro değerlerine DOKUNMAZ.

        tamamlayicilar: {'ogle': recipe_dict, 'aksam': recipe_dict}
            — Karbonhidrat açığını kapatmak için seçilmiş yan yemekler.
        """
        ogun_sira = ['kahvalti', 'ara_ogun', 'ogle', 'aksam']
        ogun_meta = {
            'kahvalti': ('Kahvaltı',      '08:00'),
            'ara_ogun': ('Ara Öğün',      '11:00'),
            'ogle':     ('Öğle Yemeği',   '13:00'),
            'aksam':    ('Akşam Yemeği',  '19:00'),
        }

        hedef_kal  = float((user or {}).get('hedef_kalori') or 0)
        hedef_p    = float((user or {}).get('protein_g') or 0)
        hedef_k    = float((user or {}).get('karbonhidrat_g') or 0)
        hedef_y    = float((user or {}).get('yag_g') or 0)
        hedef_l    = float((user or {}).get('lif_g') or 0)

        gun_kal = gun_p = gun_k = gun_y = gun_l = 0.0
        sections = []
        tamamlayicilar = tamamlayicilar or {}

        for ogun_tipi in ogun_sira:
            r = selected_meals.get(ogun_tipi)
            if not r:
                continue
            ogun_adi, saat = ogun_meta[ogun_tipi]
            f = (meal_factors or {}).get(ogun_tipi, 1.0)

            kal = round(float(r.get('kalori') or 0) * f)
            p   = round(float(r.get('protein_g') or 0) * f, 1)
            k   = round(float(r.get('karbonhidrat_g') or 0) * f, 1)
            y   = round(float(r.get('yag_g') or 0) * f, 1)
            l   = round(float(r.get('lif_g') or 0) * f, 1)
            por = round(float(r.get('porsiyon_gram') or 0) * f)

            gun_kal += kal; gun_p += p; gun_k += k; gun_y += y; gun_l += l

            malzemeler = ', '.join(r.get('malzemeler') or [])
            aciklama   = r.get('aciklama') or ''

            section_lines = [
                f"### {ogun_adi} ({saat}) — {r['ad']}",
                f"**Malzemeler:** {malzemeler}",
                aciklama,
            ]

            # Tamamlayıcı yan yemek varsa ekle
            yan = tamamlayicilar.get(ogun_tipi)
            if yan:
                yan_kal = float(yan.get('kalori') or 0)
                yan_p   = float(yan.get('protein_g') or 0)
                yan_k   = float(yan.get('karbonhidrat_g') or 0)
                yan_y   = float(yan.get('yag_g') or 0)
                yan_l   = float(yan.get('lif_g') or 0)
                yan_por = float(yan.get('porsiyon_gram') or 0)
                gun_kal += yan_kal; gun_p += yan_p; gun_k += yan_k
                gun_y   += yan_y;   gun_l += yan_l
                section_lines.append(
                    f"**Yanında:** {yan['ad']} "
                    f"({round(yan_por)}g | +{round(yan_kal)} kcal | +K:{yan_k}g)"
                )

            section_lines.append(
                f"**Porsiyon: {por}g** | **{kal} kcal** | P: {p}g | K: {k}g | Y: {y}g | L: {l}g"
            )
            sections.append("\n".join(section_lines))

        gun_adi = self._gun_adi()
        header = (
            f"## PLAN — {gun_adi}, {date.today().strftime('%d %B')}\n"
            f"**Hedefler:** {hedef_kal:.0f} kcal | "
            f"P: {hedef_p:.0f}g | Y: {hedef_y:.0f}g | "
            f"K: {hedef_k:.0f}g | L: {hedef_l:.0f}g"
        )
        summary = (
            f"## GÜNLÜK ÖZET\n"
            f"**Toplam:** {round(gun_kal)} kcal | "
            f"P: {round(gun_p, 1)}g | Y: {round(gun_y, 1)}g | "
            f"K: {round(gun_k, 1)}g | L: {round(gun_l, 1)}g"
        )

        return "\n\n---\n\n".join([header] + sections + [summary])

    def _build_forced_plan_context(self, selected_meals: dict, user: dict = None,
                                    meal_factors: dict = None) -> str:
        """
        Python tarafından her öğün için SEÇİLMİŞ tek tarifi Claude'a iletir.
        Tüm makro hesapları Python'da yapılır; Claude sadece formatlar.

        selected_meals : {'kahvalti': recipe_dict, 'ogle': recipe_dict, ...}
        user           : Kullanıcı profili (hedef kalori/makrolar)
        meal_factors   : Öğün bazlı ölçekleme faktörleri {'kahvalti': 1.08, ...}
                         Verilmezse global faktör kullanılır.
        """
        if not selected_meals:
            return ""

        ogun_isimleri = {
            'kahvalti': 'Kahvaltı',
            'ogle': 'Öğle Yemeği',
            'aksam': 'Akşam Yemeği',
            'ara_ogun': 'Ara Öğün',
        }

        hedef_kalori = float((user or {}).get('hedef_kalori') or 0)
        hedef_protein = float((user or {}).get('protein_g') or 0)
        hedef_karb = float((user or {}).get('karbonhidrat_g') or 0)
        hedef_yag = float((user or {}).get('yag_g') or 0)

        # Global fallback faktörü (meal_factors verilmediyse)
        toplam_kalori_ham = sum(float(r.get('kalori') or 0) for r in selected_meals.values())
        if hedef_kalori > 0 and toplam_kalori_ham > 0 and not meal_factors:
            global_faktor = hedef_kalori / toplam_kalori_ham
        else:
            global_faktor = 1.0

        lines = [
            "## BUGÜNKÜ PLAN — ALGORİTMANIN SEÇTİĞİ TARİFLER",
            "**KESİNLİKLE UYULMASI GEREKEN KURALLAR:**\n"
            "1. Aşağıdaki tarifler Python tarafında algoritmik seçilmiştir — adları değiştirme, yeni tarif ekleme.\n"
            "2. Her öğün için **AYARLANMIŞ** kalori ve makro değerleri aşağıda verilmiştir — bu değerleri birebir kullan.\n"
            "3. **KESİNLİKLE kendi makro hesabı yapma.** Malzeme listesine bakarak hesaplama yapma. "
            "Veritabanındaki değerler doğrudur, direkt kullan.\n"
            f"4. Günlük hedef: {hedef_kalori:.0f} kcal | P:{hedef_protein:.0f}g | K:{hedef_karb:.0f}g | Y:{hedef_yag:.0f}g\n",
        ]

        # Ayarlanmış günlük toplamları birikimli hesapla
        gun_kalori = gun_protein = gun_karb = gun_yag = gun_lif = 0.0

        for ogun_tipi, r in selected_meals.items():
            ogun_adi = ogun_isimleri.get(ogun_tipi, ogun_tipi)
            faktor = (meal_factors or {}).get(ogun_tipi, global_faktor)

            kalori  = float(r.get('kalori') or 0)
            protein = float(r.get('protein_g') or 0)
            karb    = float(r.get('karbonhidrat_g') or 0)
            yag     = float(r.get('yag_g') or 0)
            lif     = float(r.get('lif_g') or 0)
            porsiyon = float(r.get('porsiyon_gram') or 0)

            adj_kal  = round(kalori  * faktor)
            adj_p    = round(protein * faktor, 1)
            adj_k    = round(karb    * faktor, 1)
            adj_y    = round(yag     * faktor, 1)
            adj_l    = round(lif     * faktor, 1)
            adj_por  = round(porsiyon * faktor)

            gun_kalori  += adj_kal
            gun_protein += adj_p
            gun_karb    += adj_k
            gun_yag     += adj_y
            gun_lif     += adj_l

            lines.append(
                f"### {ogun_adi}: {r['ad']}\n"
                f"- Porsiyon: **{adj_por}g**\n"
                f"- **{adj_kal} kcal** | P:{adj_p}g | K:{adj_k}g | Y:{adj_y}g | L:{adj_l}g\n"
                f"- Malzemeler: {', '.join(r.get('malzemeler', []))}\n"
                f"- {r.get('aciklama', '')}\n"
            )

        lines.append(
            f"## GÜNLÜK TOPLAM — BU DEĞERLERİ AYNEN KULLAN\n"
            f"**{round(gun_kalori)} kcal** | P:{round(gun_protein, 1)}g | "
            f"K:{round(gun_karb, 1)}g | Y:{round(gun_yag, 1)}g | L:{round(gun_lif, 1)}g\n"
            f"*(Hedef: {hedef_kalori:.0f} kcal | P:{hedef_protein:.0f}g | K:{hedef_karb:.0f}g | Y:{hedef_yag:.0f}g)*\n"
            f"⚠️ Yukarıdaki değerleri birebir kullan. Malzemelere bakarak kendi hesabını yapma."
        )

        return "\n".join(lines)

    def _build_recipe_context(self, recipes_by_meal: dict) -> str:
        """
        /alternatif isteklerinde öğün bazlı seçenekleri sunar.
        Claude bu listeden önerir — plan akışında kullanılmaz.
        recipes_by_meal: {'kahvalti': [...], 'ogle': [...], ...}
        """
        if not any(recipes_by_meal.values()):
            return ""

        meal_labels = {
            'kahvalti': 'KAHVALTI',
            'ogle': 'ÖĞLE',
            'aksam': 'AKŞAM',
            'ara_ogun': 'ARA ÖĞÜN',
        }

        lines = [
            "## TARİF ALTERNATİFLERİ (Semantik Arama Sonucu)",
            "**Bu listeden birini veya birkaçını öner — listede olmayan tarif üretme.**\n",
        ]

        for meal_key, label in meal_labels.items():
            recipes = recipes_by_meal.get(meal_key, [])
            if not recipes:
                continue
            lines.append(f"### {label} ALTERNATİFLERİ")
            for r in recipes:
                lines.append(
                    f"- **{r['ad']}** → "
                    f"{r.get('kalori')} kcal | "
                    f"P:{r.get('protein_g')}g K:{r.get('karbonhidrat_g')}g "
                    f"Y:{r.get('yag_g')}g L:{r.get('lif_g')}g "
                    f"({r.get('porsiyon_gram')}g porsiyon)"
                )
            lines.append("")

        return "\n".join(lines)

    def _gun_adi(self) -> str:
        gunler = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']
        return gunler[date.today().weekday()]

    def _select_tamamlayici(
        self,
        selected_meals: dict,
        meal_factors: dict,
        hedef_karb_f: float,
        tamamlayici_recipes: list,
    ) -> tuple:
        """
        Plan karbonhidrat açığını yan yemeklerle kapatır.

        Açık hedefin %10'undan büyükse öğle ve akşam öğününe birer
        tamamlayıcı eklenir. Toplam kalorileri korumak için tamamlayıcı
        kalorisi kadar ana yemek faktörü düşürülür.

        Returns:
            (tamamlayicilar, new_meal_factors)
            tamamlayicilar: {'ogle': recipe_dict, 'aksam': recipe_dict}
        """
        if not tamamlayici_recipes or not selected_meals:
            return {}, meal_factors

        mevcut_karb = sum(
            float(selected_meals[t].get('karbonhidrat_g', 0)) * meal_factors.get(t, 1.0)
            for t in selected_meals
        )
        karb_acigi = hedef_karb_f - mevcut_karb

        # Açık %10'dan küçükse tamamlayıcı gerekmez
        if karb_acigi < hedef_karb_f * 0.10:
            return {}, meal_factors

        tamamlayicilar = {}
        new_factors = dict(meal_factors)
        kalan_acik = karb_acigi

        for ogun in ['ogle', 'aksam']:
            if ogun not in selected_meals or kalan_acik <= 3:
                continue

            # Bu öğüne uygun tamamlayıcılar
            uygun = [
                t for t in tamamlayici_recipes
                if ogun in (t.get('ogun_tipleri') or [])
            ]
            if not uygun:
                continue

            # Kalan açığı tek seferde kapatacak en yakın tamamlayıcıyı seç.
            # "acik/2" hedefi yerine doğrudan kalan_acik'a en yakın olanı al —
            # bu sayede ikinci öğüne çok küçük bir açık bırakılmaz.
            best = min(uygun, key=lambda t: abs(
                float(t.get('karbonhidrat_g', 0)) - kalan_acik
            ))

            yan_kal = float(best.get('kalori', 0))
            yan_karb = float(best.get('karbonhidrat_g', 0))

            # Ana yemek faktörünü yan yemek kalorisi kadar düşür (toplam kalori koru)
            main_base_kal = float(selected_meals[ogun].get('kalori', 0))
            if main_base_kal > 0 and yan_kal > 0:
                current_main_kal = main_base_kal * new_factors.get(ogun, 1.0)
                new_main_kal = max(0, current_main_kal - yan_kal)
                new_factors[ogun] = max(self._FAKTOR_MIN, new_main_kal / main_base_kal)

            tamamlayicilar[ogun] = best
            kalan_acik -= yan_karb

        return tamamlayicilar, new_factors

    # Scaling sınırları — _macro_fit_score ile seçim döngüsü senkronize olmalı
    # 3.0× = sebze/çorba gibi düşük kalorili tariflerin büyük öğün slotlarını
    # doldurabilmesi için gerekli (180 kcal tarif × 2.67 = 480 kcal öğle hedefi).
    # Makro uyumsuzluğu zaten aşırı büyük tarifleri cezalandırır.
    _FAKTOR_MIN = 0.7
    _FAKTOR_MAX = 3.0

    def _macro_fit_score(self, recipe: dict,
                         hedef_kal: float, hedef_p: float,
                         hedef_k: float, hedef_y: float,
                         hedef_l: float = 0.0) -> float:
        """
        Tarifin bu öğüne düşen makro bütçeyle uyumunu 0–1 arası puanlar.

        İki katmanlı değerlendirme:
        1. Kapasite kontrolü — tarif maksimum ölçeklemeyle öğünün kalori
           bütçesinin en az %80'ine ulaşabilmeli.
        2. Makro uyumu — P/K/Y/L sapması (ağırlıklı).

        Ağırlıklar: P:0.35  K:0.30  Y:0.20  L:0.15
        Asimetrik:  protein overshoot → ×0.50 ceza (eskiden ×0.25)
                    lif overshoot     → ceza yok (fazla lif her zaman iyi)
        """
        r_kal = float(recipe.get('kalori') or 0)
        if r_kal == 0 or hedef_kal == 0:
            return 0.0

        # -- Kapasite faktörü (sürekli, 0–1 arası çarpan) --
        actual_kal = r_kal * min(self._FAKTOR_MAX, hedef_kal / r_kal)
        kapsama = actual_kal / hedef_kal
        capacity_factor = min(1.0, kapsama / 0.80)

        # -- Makro uyumu (gerçek capped ölçekleme) --
        actual_f = min(self._FAKTOR_MAX, hedef_kal / r_kal)
        r_p = float(recipe.get('protein_g') or 0) * actual_f
        r_k = float(recipe.get('karbonhidrat_g') or 0) * actual_f
        r_y = float(recipe.get('yag_g') or 0) * actual_f
        r_l = float(recipe.get('lif_g') or 0) * actual_f

        # Protein: undershoot → tam ceza, overshoot → %50 ceza
        if r_p < hedef_p:
            p_err = (hedef_p - r_p) / max(hedef_p, 1)
        else:
            p_err = (r_p - hedef_p) / max(hedef_p, 1) * 0.50

        k_err = abs(r_k - hedef_k) / max(hedef_k, 1)
        y_err = abs(r_y - hedef_y) / max(hedef_y, 1)

        # Lif: undershoot → tam ceza, overshoot → ceza yok
        if hedef_l > 0:
            l_err = max(0.0, (hedef_l - r_l) / hedef_l)
        else:
            l_err = 0.0

        # Ağırlıklı hata: P:0.35  K:0.30  Y:0.20  L:0.15
        weighted_err = 0.35 * p_err + 0.30 * k_err + 0.20 * y_err + 0.15 * l_err
        macro_score = max(0.0, 1.0 - weighted_err)

        # Karbonhidrat yeterliliği penaltısı
        if hedef_k > 0 and r_k < hedef_k * 0.25:
            carb_penalty = 0.5
        else:
            carb_penalty = 1.0

        return macro_score * capacity_factor * carb_penalty

    def _select_model(self, message: str, is_onboarding: bool) -> str:
        """Mesaj karmaşıklığına göre model seç — maliyet optimizasyonu."""
        heavy_triggers = [
            '/plan', '/haftalik', '/alternatif', 'plan oluştur', 'plan yap',
            'haftalık plan', 'diyet listesi', 'alternatif öner', 'yeni plan',
            'farklı plan', 'başka plan', 'değiştir planı', 'plan hazırla',
        ]
        if is_onboarding:
            return self.model_heavy
        for trigger in heavy_triggers:
            if trigger in message.lower():
                return self.model_heavy
        return self.model_light

    def _needs_recipe_search(self, message: str, is_onboarding: bool) -> bool:
        """Bu mesaj için tarif araması gerekiyor mu?"""
        if is_onboarding:
            return False
        triggers = [
            '/plan', '/haftalik', '/alternatif', 'plan oluştur', 'plan yap',
            'haftalık plan', 'diyet listesi', 'alternatif öner', 'ne yesem',
            'ne yiyeyim', 'yemek öner', 'tarif', 'öneri', 'menü',
            'kahvaltı öner', 'öğle öner', 'akşam öner', 'ara öğün',
            'yeni plan', 'farklı plan', 'başka plan', 'plan hazırla',
            'plan istiyorum', 'plan ver', 'günlük plan', 'beslenme planı',
            'alternatif', 'değiştir', 'farklı yemek', 'başka yemek',
        ]
        msg_lower = message.lower()
        return any(t in msg_lower for t in triggers)

    # Haftanın gününe göre dönen kategori vurgusu (0=Pzt … 6=Paz)
    _GUNLUK_ROTASYON = [
        "tavuk balık yüksek protein et",          # Pazartesi
        "baklagil mercimek nohut sebze",           # Salı
        "yumurta peynir süt ürünleri kahvaltılık", # Çarşamba
        "kırmızı et köfte ızgara protein",         # Perşembe
        "deniz ürünleri balık omega hafif",        # Cuma
        "tahıl pilav bulgur tam buğday lif",       # Cumartesi
        "zeytinyağlı sebze çorba geleneksel Türk", # Pazar
    ]

    # Öğün tipine göre spesifik arama terimleri
    _OGUN_QUERY_EK = {
        'kahvalti': "Türk kahvaltısı sabah peynir yumurta",
        'ara_ogun': "hafif ara öğün atıştırmalık porsiyon küçük",
        'ogle':     "öğle yemeği doyurucu ana yemek protein",
        'aksam':    "akşam yemeği hafif sindirimi kolay protein",
    }

    def _build_recipe_query(self, message: str, user: dict,
                             ogun_tipi: str = None) -> str:
        """
        Semantik arama için zenginleştirilmiş sorgu metni oluşturur.
        Her öğün tipi ve haftanın günü için farklı sorgu → çeşitlilik.
        """
        parts = [message]

        # Öğün tipine özgü terimler
        if ogun_tipi and ogun_tipi in self._OGUN_QUERY_EK:
            parts.append(self._OGUN_QUERY_EK[ogun_tipi])

        # Haftanın gününe göre kategori rotasyonu (çeşitlilik için)
        gun_index = date.today().weekday()
        parts.append(self._GUNLUK_ROTASYON[gun_index])

        # Kullanıcı hedefi
        hedef = user.get('hedef_tip', '')
        if hedef == 'kayip':
            parts.append("düşük kalorili diyet zayıflama")
        elif hedef == 'kazanim':
            parts.append("yüksek proteinli kas yapma")

        # Sağlık durumu
        hastaliklar = user.get('kronik_hastaliklar') or []
        for h in hastaliklar:
            if 'tiroid' in h.lower():
                parts.append("tiroid dostu")
            if 'diyabet' in h.lower():
                parts.append("düşük glisemik indeks")

        # Sevilen yiyecekler
        sevilen = user.get('sevilen_yiyecekler') or []
        if sevilen:
            parts.append(f"tercih: {', '.join(sevilen[:3])}")

        return " ".join(parts)

    async def chat(
        self,
        user_message: str,
        user: dict,
        recent_meals: list = None,
        daily_summary: dict = None,
        weekly_summary: dict = None,
        todays_plan: dict = None,
        conversation_history: list = None,
        db=None,  # Database instance — tarif araması için
    ) -> str:
        """
        Ana chat fonksiyonu. Her kullanıcı mesajında çağrılır.

        1. Kullanıcı context'ini oluşturur (profil, öğünler, plan, haftalık durum)
        2. Gerekirse pgvector'dan semantik tarif araması yapar (RAG)
        3. Tarif bağlamını + kullanıcı context'ini Claude'a gönderir
        4. Yanıtı döner
        """
        # Context oluştur
        user_context = self._build_user_context(
            user=user,
            recent_meals=recent_meals or [],
            daily_summary=daily_summary or {},
            weekly_summary=weekly_summary or {},
            todays_plan=todays_plan or {},
        )

        # RAG: Tarif araması gerekiyor mu?
        recipe_context = ""
        plan_response = None  # Plan akışında Python tarafından set edilir → erken dönüş
        is_onboarding = user.get('onboarding_step', 0) > 0 and user.get('onboarding_step', 0) < 99

        # Plan isteği: Python her öğün için 1 tarif seçer → Claude sadece formatlar
        # Alternatif/öneri: Claude listeden seçer
        plan_triggers = [
            '/plan', 'plan oluştur', 'plan yap', 'haftalık plan', 'diyet listesi',
            'günlük plan', 'beslenme planı', 'plan hazırla', 'plan istiyorum',
            'plan ver', 'yeni plan', 'farklı plan', 'başka plan',
        ]
        is_plan_request = any(t in user_message.lower() for t in plan_triggers)

        if db and self._needs_recipe_search(user_message, is_onboarding):
            try:
                query_text = self._build_recipe_query(user_message, user)
                query_vector = await embedder.async_embed(query_text)

                user_id = user.get('id')
                recent_recipe_ids = []
                blacklisted_ids = []
                if user_id:
                    recent_recipe_ids = await db.get_recently_used_recipe_ids(user_id, days=7)
                    blacklisted_ids = await db.get_blacklisted_recipe_ids(user_id)

                saglik_filtre = []
                hastaliklar = user.get('kronik_hastaliklar') or []
                if any('tiroid' in h.lower() for h in hastaliklar):
                    saglik_filtre.append('tiroid_dostu')
                if any('diyabet' in h.lower() for h in hastaliklar):
                    saglik_filtre.append('diyabet_dostu')

                max_kalori = None
                hedef_kalori = user.get('hedef_kalori')
                if hedef_kalori and user.get('hedef_tip') == 'kayip':
                    max_kalori = float(hedef_kalori) * 0.45

                common_kwargs = dict(
                    embedding=query_vector,
                    saglik_etiketleri=saglik_filtre if saglik_filtre else None,
                    exclude_recent_ids=recent_recipe_ids if recent_recipe_ids else None,
                    max_kalori=max_kalori,
                )

                if is_plan_request:
                    # Python her öğün için EN İYİ 1 tarifi seçer — Claude seçim yapmaz
                    ogun_duzeni = user.get('ogun_duzeni', '') or ''
                    ogun_tipleri = ['kahvalti', 'ogle', 'aksam']
                    if any(k in ogun_duzeni.lower() for k in ['ara', '4', '5', 'snack']):
                        ogun_tipleri.append('ara_ogun')

                    # Aktif öğünlere göre normalize edilmiş kalori payları
                    raw_toplam = sum(_RAW_OGUN_PAYLARI.get(t, 0.1) for t in ogun_tipleri)
                    ogun_paylari = {
                        t: _RAW_OGUN_PAYLARI.get(t, 0.1) / raw_toplam
                        for t in ogun_tipleri
                    }

                    hedef_kalori_f = float(user.get('hedef_kalori') or 0)
                    hedef_protein_f = float(user.get('protein_g') or 0)
                    hedef_karb_f = float(user.get('karbonhidrat_g') or 0)
                    hedef_yag_f = float(user.get('yag_g') or 0)

                    selected_meals = {}
                    meal_factors = {}
                    # Kara listeli ID'ler recent listesine eklenir — hiç gösterilmez
                    session_excluded = list(set(recent_recipe_ids) | set(blacklisted_ids))
                    # Seçilen protein kategorileri — tekrar önlemek için
                    # (ana_yemek_tavuk, ana_yemek_et, ana_yemek_balik)
                    _PROTEIN_KATS = {'ana_yemek_tavuk', 'ana_yemek_et', 'ana_yemek_balik'}
                    secilen_protein_kats: set = set()

                    for ogun_tipi in ogun_tipleri:
                        pay = ogun_paylari[ogun_tipi]
                        ogun_hedef_kal = hedef_kalori_f * pay
                        ogun_hedef_p   = hedef_protein_f * pay
                        ogun_hedef_k   = hedef_karb_f * pay
                        ogun_hedef_y   = hedef_yag_f * pay
                        ogun_hedef_l   = float(user.get('lif_g') or 0) * pay

                        # Per-slot max_kalori: bu slotta makul üst sınır
                        max_kalori_ogun = (
                            ogun_hedef_kal / self._FAKTOR_MIN
                            if ogun_hedef_kal > 0 else max_kalori
                        )

                        ogun_query = self._build_recipe_query(
                            user_message, user, ogun_tipi=ogun_tipi
                        )
                        ogun_vector = await embedder.async_embed(ogun_query)

                        results = await db.search_recipes(
                            ogun_tipi=ogun_tipi,
                            limit=12,
                            embedding=ogun_vector,
                            saglik_etiketleri=saglik_filtre if saglik_filtre else None,
                            exclude_recent_ids=session_excluded if session_excluded else None,
                            max_kalori=max_kalori_ogun,
                        )
                        if results:
                            # Protein kategorisi tekrarını önle: öğle/akşam arasında
                            # aynı protein kaynağı (tavuk/et/balık) seçilmesin.
                            # Filtrelenmiş havuz boşalırsa kısıtı kaldır.
                            if ogun_tipi in ('ogle', 'aksam') and secilen_protein_kats:
                                filtered = [
                                    r for r in results
                                    if r.get('kategori') not in secilen_protein_kats
                                ]
                                if filtered:
                                    results = filtered

                            chosen = max(results, key=lambda r: (
                                0.35 * float(r.get('benzerlik', 0)) +
                                0.65 * self._macro_fit_score(
                                    r, ogun_hedef_kal, ogun_hedef_p,
                                    ogun_hedef_k, ogun_hedef_y, ogun_hedef_l
                                )
                            ))
                            selected_meals[ogun_tipi] = chosen
                            session_excluded.append(chosen['tarif_id'])
                            if chosen.get('kategori') in _PROTEIN_KATS:
                                secilen_protein_kats.add(chosen['kategori'])

                            # Öğün bazlı ölçekleme faktörü [FAKTOR_MIN, FAKTOR_MAX]
                            r_kal = float(chosen.get('kalori') or 0)
                            if r_kal > 0 and ogun_hedef_kal > 0:
                                f = ogun_hedef_kal / r_kal
                                meal_factors[ogun_tipi] = max(
                                    self._FAKTOR_MIN, min(self._FAKTOR_MAX, f)
                                )
                            else:
                                meal_factors[ogun_tipi] = 1.0

                    # --- Plan toplam doğrulaması ---
                    # Tüm öğünler seçildikten sonra toplam kalori hedefin
                    # %95'inin altındaysa (FAKTOR_MAX sınırı sebebiyle), faktörleri
                    # orantılı artır.
                    if selected_meals and hedef_kalori_f > 0:
                        plan_kal_toplam = sum(
                            float(selected_meals[t].get('kalori', 0)) * meal_factors.get(t, 1.0)
                            for t in selected_meals
                        )
                        if plan_kal_toplam > 0 and plan_kal_toplam < hedef_kalori_f * 0.95:
                            boost = hedef_kalori_f / plan_kal_toplam
                            # Proteini zaten fazla olan öğünleri boostlama —
                            # bu sayede protein hedefin çok üstüne çıkmaz.
                            plan_p_toplam = sum(
                                float(selected_meals[t].get('protein_g', 0)) * meal_factors.get(t, 1.0)
                                for t in selected_meals
                            )
                            for t in list(meal_factors.keys()):
                                r = selected_meals[t]
                                ogune_dusen_p = float(r.get('protein_g', 0)) * meal_factors.get(t, 1.0)
                                ogune_dusen_p_hedef = hedef_protein_f * ogun_paylari.get(t, 0.25)
                                # Bu öğün protein hedefinin %115'ini aşıyorsa boost uygulama
                                if ogune_dusen_p > ogune_dusen_p_hedef * 1.15:
                                    continue
                                meal_factors[t] = min(
                                    self._FAKTOR_MAX,
                                    meal_factors[t] * boost
                                )

                    if selected_meals:
                        # Seçilen tarif ID'lerini ve plan iskeletini DB'ye kaydet.
                        # UPSERT ile yapılır — satır yoksa oluşturur.
                        # Bu sayede get_recently_used_recipe_ids() tarif_idler'den beslenebilir.
                        if user_id:
                            try:
                                from datetime import date as _date
                                plan_ids = [
                                    r.get('tarif_id') or r.get('id', '')
                                    for r in selected_meals.values()
                                ]
                                # plan_skeleton henüz oluşturulmadı, boş geçiyoruz;
                                # tamamlayıcı sonrası güncellenecek
                                await db.save_plan_recipe_ids(
                                    user_id, _date.today(),
                                    [pid for pid in plan_ids if pid],
                                )
                            except Exception as e:
                                logger.warning(f"Plan tarif ID'leri kaydedilemedi: {e}")

                        # Tamamlayıcı seçimi: karbonhidrat açığını kapat
                        tamamlayicilar = {}
                        if hedef_karb_f > 0:
                            try:
                                tamamlayici_recipes = await db.get_tamamlayici_recipes()
                                if tamamlayici_recipes:
                                    tamamlayicilar, meal_factors = self._select_tamamlayici(
                                        selected_meals, meal_factors,
                                        hedef_karb_f, tamamlayici_recipes,
                                    )
                                    if tamamlayicilar:
                                        logger.info(
                                            f"Tamamlayıcı eklendi: "
                                            f"{[v['ad'] for v in tamamlayicilar.values()]}"
                                        )
                            except Exception as e:
                                logger.warning(f"Tamamlayıcı seçimi başarısız: {e}")

                        plan_skeleton = self._format_plan_skeleton(
                            selected_meals, user, meal_factors, tamamlayicilar
                        )

                        # --- İki-parçalı mimari ---
                        # Parça 1: Python plan verisini oluşturdu (plan_skeleton)
                        # Parça 2: Claude'a SADECE tarif adları verilir, makro/kalori YOK
                        #          Claude: giriş cümlesi + her öğün için 1 ipucu + günlük notlar
                        isim = user.get('isim', 'arkadaş')
                        ogun_tr = {
                            'kahvalti': 'Kahvaltı', 'ara_ogun': 'Ara Öğün',
                            'ogle': 'Öğle', 'aksam': 'Akşam',
                        }
                        ogun_listesi = "\n".join(
                            f"- {ogun_tr.get(t, t)}: {r['ad']}"
                            for t, r in selected_meals.items()
                        )
                        personality_prompt = (
                            f"{isim} için {self._gun_adi()} planı seçildi:\n"
                            f"{ogun_listesi}\n\n"
                            f"Yaz (BAŞKA HİÇBİR ŞEY YAZMA — kalori/makro/malzeme listesi YAZMA):\n"
                            f"1. Kısa samimi giriş cümlesi (1 satır)\n"
                            f"2. Her öğün için birer satır hazırlık ipucu\n"
                            f"3. Günlük su + 2-3 madde pratik not"
                        )
                        pers_resp = self.client.messages.create(
                            model=self.model_light,
                            max_tokens=400,
                            system=self.system_prompt,
                            messages=[{"role": "user", "content": personality_prompt}],
                        ).content[0].text

                        plan_response = plan_skeleton + "\n\n" + pers_resp

                        # Plan metnini de DB'ye kaydet (plan_detay güncelle)
                        if user_id:
                            try:
                                from datetime import date as _date
                                await db.save_plan_recipe_ids(
                                    user_id, _date.today(),
                                    [r.get('tarif_id') or r.get('id', '')
                                     for r in selected_meals.values()],
                                    plan_text=plan_response,
                                )
                            except Exception as e:
                                logger.warning(f"Plan metni kaydedilemedi: {e}")

                        logger.info(
                            f"Plan RAG: {len(selected_meals)} öğün seçildi "
                            f"(Python formatladı, Claude kişiselleştirdi)"
                        )
                else:
                    # /alternatif, "ne yesem" vb. — Claude listeden önerir
                    recipes_by_meal = {
                        'kahvalti': await db.search_recipes(ogun_tipi='kahvalti', limit=3, **common_kwargs),
                        'ogle':     await db.search_recipes(ogun_tipi='ogle',     limit=3, **common_kwargs),
                        'aksam':    await db.search_recipes(ogun_tipi='aksam',    limit=3, **common_kwargs),
                        'ara_ogun': await db.search_recipes(ogun_tipi='ara_ogun', limit=3, **common_kwargs),
                    }
                    total = sum(len(v) for v in recipes_by_meal.values())
                    if total > 0:
                        recipe_context = "\n\n" + self._build_recipe_context(recipes_by_meal)
                        logger.info(f"Öneri RAG: {total} tarif bulundu")

            except Exception as e:
                logger.warning(f"Tarif araması başarısız (devam ediliyor): {e}")

        # Plan akışı: Python + kişiselleştirme hazır → ana Claude çağrısını atla
        if plan_response is not None:
            return plan_response

        # System prompt + kullanıcı context'i + tarif context'i
        full_system = f"{self.system_prompt}\n\n---\n\n{user_context}{recipe_context}"

        # Konuşma geçmişi (son 15 mesaj)
        messages = []
        if conversation_history:
            for msg in conversation_history[-15:]:
                messages.append({
                    "role": msg["rol"],
                    "content": msg["mesaj"],
                })

        # Mevcut mesajı ekle
        messages.append({"role": "user", "content": user_message})

        # Model seç
        model = self._select_model(user_message, is_onboarding)

        # Claude API çağrısı
        response = self.client.messages.create(
            model=model,
            max_tokens=3000,
            system=full_system,
            messages=messages,
        )

        return response.content[0].text
