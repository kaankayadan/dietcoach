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

    def _build_recipe_context(self, recipes: list) -> str:
        """
        Semantik aramadan gelen tarifleri Claude'a okunabilir formatta sunar.
        Claude bu listedeki tariflerden seçerek öneri yapacak.
        """
        if not recipes:
            return ""

        lines = ["## Tarif Veritabanından Öneriler (Semantik Arama Sonucu)"]
        lines.append("*Aşağıdaki tarifler kullanıcının profiline ve isteğine göre seçilmiştir.*")
        lines.append("*Yemek planı oluştururken bu tariflerden seçim yapabilirsin.*\n")

        for i, r in enumerate(recipes, 1):
            lines.append(
                f"**{i}. {r['ad']}** ({r.get('kategori', '')})\n"
                f"   Porsiyon: {r.get('porsiyon_gram')}g | "
                f"Kalori: {r.get('kalori')} kcal | "
                f"Protein: {r.get('protein_g')}g | "
                f"Karb: {r.get('karbonhidrat_g')}g | "
                f"Yağ: {r.get('yag_g')}g | "
                f"Lif: {r.get('lif_g')}g\n"
                f"   Malzemeler: {', '.join(r.get('malzemeler', []))}\n"
                f"   {r.get('aciklama', '')}"
            )

        lines.append(
            "\n*ÖNEMLİ: Yemek planı oluştururken ÖNCE bu listeden seç. "
            "Listede uygun tarif yoksa yeni tarif ekleyebilirsin, ancak listedeki "
            "tarifler önceliklidir. Listeden seçtiğin tarifin porsiyon, kalori ve makro "
            "değerlerini değiştirme — veritabanındaki değerleri kullan.*"
        )

        return "\n".join(lines)

    def _gun_adi(self) -> str:
        gunler = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']
        return gunler[date.today().weekday()]

    def _select_model(self, message: str, is_onboarding: bool) -> str:
        """Mesaj karmaşıklığına göre model seç — maliyet optimizasyonu."""
        heavy_triggers = [
            '/plan', '/haftalik', 'plan oluştur', 'plan yap', 'haftalık plan',
            'diyet listesi', '/alternatif', 'alternatif öner',
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
        is_onboarding = user.get('onboarding_step', 0) > 0 and user.get('onboarding_step', 0) < 99

        if db and self._needs_recipe_search(user_message, is_onboarding):
            try:
                # Arama sorgusunu oluştur
                query_text = self._build_recipe_query(user_message, user)

                # Sorguyu vektörleştir (async, event loop'u bloklamaz)
                query_vector = await embedder.async_embed(query_text)

                # Son 7 günde kullanılan tarifleri hariç tut (çeşitlilik)
                user_id = user.get('id')
                recent_recipe_ids = []
                if user_id:
                    recent_recipe_ids = await db.get_recently_used_recipe_ids(user_id, days=7)

                # Kullanıcıya özel filtreler
                saglik_filtre = []
                hastaliklar = user.get('kronik_hastaliklar') or []
                if any('tiroid' in h.lower() for h in hastaliklar):
                    saglik_filtre.append('tiroid_dostu')
                if any('diyabet' in h.lower() for h in hastaliklar):
                    saglik_filtre.append('diyabet_dostu')

                # Maksimum kalori filtresi (diyet hedefli kullanıcılar için)
                max_kalori = None
                hedef_kalori = user.get('hedef_kalori')
                if hedef_kalori and user.get('hedef_tip') == 'kayip':
                    # Tek öğün için hedef kalorinin ~%40'ı sınır olabilir
                    max_kalori = float(hedef_kalori) * 0.45

                # Semantik arama
                recipes = await db.search_recipes(
                    embedding=query_vector,
                    limit=8,
                    saglik_etiketleri=saglik_filtre if saglik_filtre else None,
                    exclude_recent_ids=recent_recipe_ids if recent_recipe_ids else None,
                    max_kalori=max_kalori,
                )

                if recipes:
                    recipe_context = "\n\n" + self._build_recipe_context(recipes)
                    logger.info(f"RAG: {len(recipes)} tarif bulundu, context'e eklendi")

            except Exception as e:
                logger.warning(f"Tarif araması başarısız (devam ediliyor): {e}")

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
            max_tokens=2000,
            system=full_system,
            messages=messages,
        )

        return response.content[0].text
