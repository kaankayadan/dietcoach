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
                              meal_factors: dict) -> str:
        """
        Plan verisini Python'da tam olarak formatlar.
        Claude bu metne sadece giriş cümlesi ve pratik notlar ekler —
        tarif adı, malzeme veya makro değerlerine DOKUNMAZ.
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

            sections.append(
                f"### {ogun_adi} ({saat}) — {r['ad']}\n"
                f"**Malzemeler:** {malzemeler}\n"
                f"{aciklama}\n"
                f"**{kal} kcal** | P: {p}g | K: {k}g | Y: {y}g | L: {l}g"
            )

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

    # Scaling sınırları — _macro_fit_score ile seçim döngüsü senkronize olmalı
    _FAKTOR_MIN = 0.7
    _FAKTOR_MAX = 1.5

    def _macro_fit_score(self, recipe: dict,
                         hedef_kal: float, hedef_p: float,
                         hedef_k: float, hedef_y: float) -> float:
        """
        Tarifin bu öğüne düşen makro bütçeyle uyumunu 0–1 arası puanlar.

        İki katmanlı değerlendirme:
        1. Kapasite kontrolü — tarif maksimum ölçeklemeyle (1.5×) öğünün
           kalori bütçesinin en az %80'ine ulaşabilmeli. Ulaşamazsa skor
           sıfıra yaklaşır (ayran gibi içeceklerin ana öğün slotunu işgal
           etmesi önlenir).
        2. Makro uyumu — hipotetik ölçekleme sonrası P/K/Y sapması.
        """
        r_kal = float(recipe.get('kalori') or 0)
        if r_kal == 0 or hedef_kal == 0:
            return 0.0

        # -- Kapasite faktörü (sürekli, 0–1 arası çarpan) --
        # Tarif maksimum ölçeklemeyle hedef kalorinin ne kadarına ulaşabiliyor?
        actual_kal = r_kal * min(self._FAKTOR_MAX, hedef_kal / r_kal)
        kapsama = actual_kal / hedef_kal  # 1.0 = tam bütçe, <1 = eksik
        # 0.80 eşiğine kadar tam kredi, altında orantılı düşüş
        capacity_factor = min(1.0, kapsama / 0.80)

        # -- Makro uyumu (hipotetik tam ölçekleme) --
        f = hedef_kal / r_kal
        r_p = float(recipe.get('protein_g') or 0) * f
        r_k = float(recipe.get('karbonhidrat_g') or 0) * f
        r_y = float(recipe.get('yag_g') or 0) * f

        p_err = abs(r_p - hedef_p) / max(hedef_p, 1)
        k_err = abs(r_k - hedef_k) / max(hedef_k, 1)
        y_err = abs(r_y - hedef_y) / max(hedef_y, 1)

        # Protein ve karb daha kritik (P:0.35, K:0.35, Y:0.30)
        weighted_err = 0.35 * p_err + 0.35 * k_err + 0.30 * y_err
        macro_score = max(0.0, 1.0 - weighted_err)

        # Kapasite × makro uyumu: düşük kapasiteli TARİF aynı zamanda
        # kötü makrolarla geliyorsa (K:0 gibi) çok düşük skor alır
        return macro_score * capacity_factor

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

    def _build_recipe_query(self, message: str, user: dict) -> str:
        """
        Semantik arama için zenginleştirilmiş sorgu metni oluşturur.
        Kullanıcının sağlık durumu, hedefi ve mesajı birleştirilir.
        """
        parts = [message]

        # Kullanıcı hedefi
        hedef = user.get('hedef_tip', '')
        if hedef == 'kayip':
            parts.append("düşük kalorili diyet yemek zayıflama")
        elif hedef == 'kazanim':
            parts.append("yüksek proteinli kas yapma öğün")

        # Sağlık durumu
        hastaliklar = user.get('kronik_hastaliklar') or []
        for h in hastaliklar:
            if 'tiroid' in h.lower():
                parts.append("tiroid dostu yemek")
            if 'diyabet' in h.lower():
                parts.append("diyabet düşük glisemik indeks")

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
                if user_id:
                    recent_recipe_ids = await db.get_recently_used_recipe_ids(user_id, days=7)

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
                    session_excluded = list(recent_recipe_ids)

                    for ogun_tipi in ogun_tipleri:
                        pay = ogun_paylari[ogun_tipi]
                        ogun_hedef_kal = hedef_kalori_f * pay
                        ogun_hedef_p   = hedef_protein_f * pay
                        ogun_hedef_k   = hedef_karb_f * pay
                        ogun_hedef_y   = hedef_yag_f * pay

                        results = await db.search_recipes(
                            ogun_tipi=ogun_tipi,
                            limit=8,  # Daha geniş havuz → daha iyi makro seçimi
                            embedding=query_vector,
                            saglik_etiketleri=saglik_filtre if saglik_filtre else None,
                            exclude_recent_ids=session_excluded if session_excluded else None,
                            max_kalori=max_kalori,
                        )
                        if results:
                            # Bileşik skor: semantik benzerlik (0.5) + makro uyumu (0.5)
                            chosen = max(results, key=lambda r: (
                                0.5 * float(r.get('benzerlik', 0)) +
                                0.5 * self._macro_fit_score(
                                    r, ogun_hedef_kal, ogun_hedef_p, ogun_hedef_k, ogun_hedef_y
                                )
                            ))
                            selected_meals[ogun_tipi] = chosen
                            session_excluded.append(chosen['tarif_id'])

                            # Öğün bazlı ölçekleme faktörü ([0.7, 1.5] aralığında kısıtlı)
                            r_kal = float(chosen.get('kalori') or 0)
                            if r_kal > 0 and ogun_hedef_kal > 0:
                                f = ogun_hedef_kal / r_kal
                                meal_factors[ogun_tipi] = max(0.7, min(1.5, f))
                            else:
                                meal_factors[ogun_tipi] = 1.0

                    if selected_meals:
                        plan_skeleton = self._format_plan_skeleton(
                            selected_meals, user, meal_factors
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
