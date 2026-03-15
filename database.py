"""
Veritabanı İşlemleri — Kullanıcı profili, öğün kayıtları, takip verileri.
Her API çağrısından önce buradan güncel veriler çekilir ve Claude'a context olarak verilir.
"""
import asyncpg
import json
from datetime import date, timedelta
from typing import Optional


class Database:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(self.database_url, min_size=2, max_size=10)
    
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    # ==========================================
    # KULLANICI İŞLEMLERİ
    # ==========================================
    
    async def get_user(self, telegram_id: int) -> Optional[dict]:
        """Kullanıcı profilini getir — her mesajda çağrılır."""
        row = await self.pool.fetchrow(
            "SELECT * FROM users WHERE telegram_id = $1", telegram_id
        )
        if row:
            return dict(row)
        return None
    
    async def create_user(self, telegram_id: int) -> dict:
        """Yeni kullanıcı oluştur — /baslat komutunda."""
        row = await self.pool.fetchrow(
            """INSERT INTO users (telegram_id, onboarding_step, onboarding_data)
               VALUES ($1, 1, '{}')
               ON CONFLICT (telegram_id) DO UPDATE SET onboarding_step = 1, onboarding_data = '{}'
               RETURNING *""",
            telegram_id,
        )
        return dict(row)
    
    async def update_onboarding(self, telegram_id: int, step: int, data: dict):
        """Onboarding adımını güncelle — her onboarding yanıtında."""
        await self.pool.execute(
            """UPDATE users 
               SET onboarding_step = $2, onboarding_data = $3, updated_at = NOW()
               WHERE telegram_id = $1""",
            telegram_id, step, json.dumps(data, ensure_ascii=False),
        )
    
    async def complete_onboarding(self, telegram_id: int, profile_data: dict):
        """
        Onboarding tamamlandığında tüm profil verilerini kaydet.
        profile_data içinde hesaplanmış BMR, TDEE, makrolar da olacak.
        """
        await self.pool.execute(
            """UPDATE users SET
                isim = $2, yas = $3, cinsiyet = $4, boy_cm = $5, kilo_kg = $6,
                vucut_yag_orani = $7, yagsiz_kutle_kg = $8, bel_cevresi_cm = $9,
                vyo_yontemi = $10, aktivite_seviyesi = $11,
                kronik_hastaliklar = $12, sindirim_sorunlari = $13, alerjiler = $14,
                ilaclar = $15,
                hedef_tip = $16, hedef_kilo = $17, agresiflik = $18,
                mutfak_stili = $19, sevilen_yiyecekler = $20, sevilmeyen_yiyecekler = $21,
                ogun_duzeni = $22, if_penceresi = $23,
                bmr = $24, neat = $25, tef = $26, eat_gunluk = $27, tdee = $28,
                hedef_kalori = $29,
                protein_g = $30, karbonhidrat_g = $31, yag_g = $32, lif_g = $33,
                su_hedefi_litre = $34,
                onboarding_step = 99, updated_at = NOW()
               WHERE telegram_id = $1""",
            telegram_id,
            profile_data.get('isim'), profile_data.get('yas'),
            profile_data.get('cinsiyet'), profile_data.get('boy_cm'),
            profile_data.get('kilo_kg'), profile_data.get('vucut_yag_orani'),
            profile_data.get('yagsiz_kutle_kg'), profile_data.get('bel_cevresi_cm'),
            profile_data.get('vyo_yontemi'), profile_data.get('aktivite_seviyesi'),
            profile_data.get('kronik_hastaliklar'), profile_data.get('sindirim_sorunlari'),
            profile_data.get('alerjiler'), json.dumps(profile_data.get('ilaclar', []), ensure_ascii=False),
            profile_data.get('hedef_tip'), profile_data.get('hedef_kilo'),
            profile_data.get('agresiflik'), profile_data.get('mutfak_stili'),
            profile_data.get('sevilen_yiyecekler'), profile_data.get('sevilmeyen_yiyecekler'),
            profile_data.get('ogun_duzeni'), profile_data.get('if_penceresi'),
            profile_data.get('bmr'), profile_data.get('neat'),
            profile_data.get('tef'), profile_data.get('eat_gunluk'),
            profile_data.get('tdee'), profile_data.get('hedef_kalori'),
            profile_data.get('protein_g'), profile_data.get('karbonhidrat_g'),
            profile_data.get('yag_g'), profile_data.get('lif_g'),
            profile_data.get('su_hedefi_litre'),
        )
    
    async def update_user_weight(self, telegram_id: int, kilo: float):
        """Haftalık tartım kaydı."""
        user = await self.get_user(telegram_id)
        if user:
            await self.pool.execute(
                "UPDATE users SET kilo_kg = $2, son_tartim_tarihi = $3, updated_at = NOW() WHERE telegram_id = $1",
                telegram_id, kilo, date.today(),
            )
            await self.pool.execute(
                "INSERT INTO kilo_gecmisi (user_id, tarih, kilo_kg) VALUES ($1, $2, $3)",
                user['id'], date.today(), kilo,
            )
    
    # ==========================================
    # AKTİVİTE İŞLEMLERİ
    # ==========================================
    
    async def save_activities(self, user_id: int, activities: list):
        """Aktivite bilgilerini kaydet."""
        await self.pool.execute("DELETE FROM aktiviteler WHERE user_id = $1", user_id)
        for act in activities:
            await self.pool.execute(
                """INSERT INTO aktiviteler (user_id, aktivite_tipi, haftalik_siklik, gunler, saat, sure_dk, met_degeri)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                user_id, act['tip'], act['siklik'], act.get('gunler', []),
                act.get('saat'), act.get('sure_dk'), act.get('met', 5.0),
            )
    
    async def get_activities(self, user_id: int) -> list:
        rows = await self.pool.fetch(
            "SELECT * FROM aktiviteler WHERE user_id = $1", user_id
        )
        return [dict(r) for r in rows]
    
    # ==========================================
    # ÖĞÜN KAYITLARI
    # ==========================================
    
    async def save_meal(self, user_id: int, meal_data: dict):
        """Kullanıcının yediğini kaydet."""
        await self.pool.execute(
            """INSERT INTO ogun_kayitlari (user_id, tarih, ogun_tipi, aciklama, plan_uyumu,
                   kalori, protein, karbonhidrat, yag, lif)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
            user_id, meal_data.get('tarih', date.today()),
            meal_data.get('ogun_tipi', 'belirtilmedi'),
            meal_data['aciklama'],
            meal_data.get('plan_uyumu', 'farkli'),
            meal_data.get('kalori'), meal_data.get('protein'),
            meal_data.get('karbonhidrat'), meal_data.get('yag'),
            meal_data.get('lif'),
        )
    
    async def get_todays_meals(self, user_id: int) -> list:
        """Bugünkü öğün kayıtlarını getir — her mesajda context için."""
        rows = await self.pool.fetch(
            """SELECT * FROM ogun_kayitlari 
               WHERE user_id = $1 AND tarih = $2 
               ORDER BY created_at""",
            user_id, date.today(),
        )
        return [dict(r) for r in rows]
    
    # ==========================================
    # PLAN İŞLEMLERİ
    # ==========================================
    
    async def save_daily_plan(self, user_id: int, plan_date: date, plan_detail: dict, total_cal: float):
        await self.pool.execute(
            """INSERT INTO gunluk_plan (user_id, tarih, plan_detay, toplam_kalori)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (user_id, tarih) DO UPDATE SET plan_detay = $3, toplam_kalori = $4""",
            user_id, plan_date, json.dumps(plan_detail, ensure_ascii=False), total_cal,
        )
    
    async def get_todays_plan(self, user_id: int) -> Optional[dict]:
        row = await self.pool.fetchrow(
            "SELECT * FROM gunluk_plan WHERE user_id = $1 AND tarih = $2",
            user_id, date.today(),
        )
        return dict(row) if row else None
    
    # ==========================================
    # GÜNLÜK VE HAFTALIK ÖZET
    # ==========================================
    
    async def get_daily_summary(self, user_id: int, target_date: date = None) -> Optional[dict]:
        target_date = target_date or date.today()
        row = await self.pool.fetchrow(
            "SELECT * FROM gunluk_ozet WHERE user_id = $1 AND tarih = $2",
            user_id, target_date,
        )
        return dict(row) if row else None
    
    async def get_weekly_summary(self, user_id: int) -> Optional[dict]:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        row = await self.pool.fetchrow(
            "SELECT * FROM haftalik_ozet WHERE user_id = $1 AND hafta_baslangic = $2",
            user_id, week_start,
        )
        return dict(row) if row else None
    
    async def save_daily_summary(self, user_id: int, summary: dict):
        await self.pool.execute(
            """INSERT INTO gunluk_ozet (user_id, tarih, planlanan_kalori, tuketilen_kalori,
                   sapma_kalori, planlanan_protein, tuketilen_protein,
                   planlanan_karbonhidrat, tuketilen_karbonhidrat,
                   planlanan_yag, tuketilen_yag, su_litre, uyum_puani, notlar)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
               ON CONFLICT (user_id, tarih) DO UPDATE SET
                   tuketilen_kalori = $4, sapma_kalori = $5,
                   tuketilen_protein = $7, tuketilen_karbonhidrat = $9,
                   tuketilen_yag = $11, su_litre = $12, uyum_puani = $13, notlar = $14""",
            user_id, summary.get('tarih', date.today()),
            summary.get('planlanan_kalori'), summary.get('tuketilen_kalori'),
            summary.get('sapma_kalori'),
            summary.get('planlanan_protein'), summary.get('tuketilen_protein'),
            summary.get('planlanan_karbonhidrat'), summary.get('tuketilen_karbonhidrat'),
            summary.get('planlanan_yag'), summary.get('tuketilen_yag'),
            summary.get('su_litre', 0), summary.get('uyum_puani'),
            summary.get('notlar'),
        )
    
    # ==========================================
    # KONUŞMA GEÇMİŞİ
    # ==========================================
    
    async def save_message(self, user_id: int, role: str, message: str):
        """Her mesajı kaydet — conversation history için."""
        await self.pool.execute(
            "INSERT INTO konusma_gecmisi (user_id, rol, mesaj) VALUES ($1, $2, $3)",
            user_id, role, message,
        )
    
    async def get_conversation_history(self, user_id: int, limit: int = 15) -> list:
        """Son N mesajı getir — Claude'a context olarak gönderilir."""
        rows = await self.pool.fetch(
            """SELECT rol, mesaj FROM konusma_gecmisi 
               WHERE user_id = $1 
               ORDER BY created_at DESC LIMIT $2""",
            user_id, limit,
        )
        return [dict(r) for r in reversed(rows)]
    
    # ==========================================
    # KİLO GEÇMİŞİ
    # ==========================================

    async def get_weight_history(self, user_id: int, limit: int = 12) -> list:
        rows = await self.pool.fetch(
            """SELECT tarih, kilo_kg FROM kilo_gecmisi
               WHERE user_id = $1 ORDER BY tarih DESC LIMIT $2""",
            user_id, limit,
        )
        return [dict(r) for r in reversed(rows)]

    # ==========================================
    # TARİF ARAMA (pgvector semantik arama)
    # ==========================================

    async def search_recipes(
        self,
        embedding: list,
        limit: int = 8,
        ogun_tipi: str = None,
        saglik_etiketleri: list = None,
        exclude_recent_ids: list = None,
        max_kalori: float = None,
        min_protein: float = None,
    ) -> list:
        """
        Kullanıcı sorgusuna semantik olarak en yakın tarifleri bulur.

        Çeşitlilik mekanizması:
        - exclude_recent_ids: Son 7 günde önerilen tarif ID'leri hariç tutulur
        - Sonuçlar benzerlik skoru + çeşitlilik ağırlığıyla sıralanır

        Args:
            embedding: Sorgu vektörü (384 boyutlu)
            limit: Dönecek tarif sayısı
            ogun_tipi: 'kahvalti', 'ogle', 'aksam', 'ara_ogun' filtresi
            saglik_etiketleri: Dahil edilmesi gereken sağlık etiketleri
            exclude_recent_ids: Son 7 günde kullanılan tarif ID'leri (çeşitlilik için)
            max_kalori: Maksimum kalori filtresi
            min_protein: Minimum protein filtresi
        """
        # Temel sorgu — önce recent_ids hariç ara, sonuç yoksa hepsini ara
        for exclude in [exclude_recent_ids or [], []]:
            vector_str = "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"

            # Dinamik WHERE koşulları
            conditions = ["embedding IS NOT NULL"]
            params = [vector_str]
            param_idx = 2

            if ogun_tipi:
                conditions.append(f"${param_idx} = ANY(ogun_tipleri)")
                params.append(ogun_tipi)
                param_idx += 1

            if saglik_etiketleri:
                # En az bir etiket eşleşmesi yeterli (OR mantığı)
                conditions.append(f"saglik_etiketler && ${param_idx}::text[]")
                params.append(saglik_etiketleri)
                param_idx += 1

            if max_kalori:
                conditions.append(f"kalori <= ${param_idx}")
                params.append(max_kalori)
                param_idx += 1

            if min_protein:
                conditions.append(f"protein_g >= ${param_idx}")
                params.append(min_protein)
                param_idx += 1

            if exclude:
                conditions.append(f"tarif_id != ALL(${param_idx}::text[])")
                params.append(exclude)
                param_idx += 1

            where_clause = " AND ".join(conditions)

            query = f"""
                SELECT
                    tarif_id, ad, kategori, malzemeler,
                    porsiyon_gram, kalori, protein_g, karbonhidrat_g, yag_g, lif_g,
                    saglik_etiketler, ogun_tipleri, pismesi_dk, zorluk, aciklama,
                    1 - (embedding <=> $1::vector) AS benzerlik
                FROM tarifler
                WHERE {where_clause}
                ORDER BY embedding <=> $1::vector
                LIMIT ${param_idx}
            """
            params.append(limit)

            rows = await self.pool.fetch(query, *params)
            results = [dict(r) for r in rows]

            if results:
                return results

        return []

    async def get_recently_used_recipe_ids(self, user_id: int, days: int = 7) -> list:
        """
        Son N günde kullanıcıya önerilen ve/veya yediği tarif ID'lerini döner.
        Çeşitlilik için bu ID'ler plan seçiminde exclude listesine eklenir.

        İki kaynaktan beslenilir:
        1. gunluk_plan.tarif_idler — plan oluşturulduğunda direkt kaydedilen ID'ler
        2. ogun_kayitlari — kullanıcının /yedim ile kaydettiği öğünler (fuzzy match)
        """
        # 1. Planlarda kullanılan tarif ID'leri (kesin eşleşme)
        plan_rows = await self.pool.fetch(
            """
            SELECT COALESCE(tarif_idler, '{}') AS ids
            FROM gunluk_plan
            WHERE user_id = $1
              AND tarih >= (CURRENT_DATE - ($2 * INTERVAL '1 day'))::date
            """,
            user_id, days,
        )
        plan_ids = set()
        for row in plan_rows:
            plan_ids.update(row["ids"] or [])

        # 2. Yenilen öğünlerden fuzzy eşleşme (yedim kaydı varsa)
        meal_rows = await self.pool.fetch(
            """
            SELECT DISTINCT t.tarif_id
            FROM ogun_kayitlari ok
            JOIN tarifler t ON (
                ok.aciklama ILIKE '%' || t.ad || '%'
                OR t.ad ILIKE '%' || split_part(ok.aciklama, ' ', 1) || '%'
            )
            WHERE ok.user_id = $1
              AND ok.tarih >= (CURRENT_DATE - ($2 * INTERVAL '1 day'))::date
            """,
            user_id, days,
        )
        meal_ids = {r["tarif_id"] for r in meal_rows}

        return list(plan_ids | meal_ids)

    # ==========================================
    # TARİF KARA LİSTESİ
    # ==========================================

    async def add_to_blacklist(self, user_id: int, tarif_id: str):
        """Tarifi kara listeye ekle — bir daha önerilmez."""
        await self.pool.execute(
            """INSERT INTO tarif_kara_liste (user_id, tarif_id)
               VALUES ($1, $2) ON CONFLICT DO NOTHING""",
            user_id, tarif_id,
        )

    async def get_blacklisted_recipe_ids(self, user_id: int) -> list:
        """Kullanıcının kara listedeki tüm tarif ID'lerini döner."""
        rows = await self.pool.fetch(
            "SELECT tarif_id FROM tarif_kara_liste WHERE user_id = $1",
            user_id,
        )
        return [r["tarif_id"] for r in rows]

    async def save_plan_recipe_ids(self, user_id: int, plan_date, tarif_ids: list,
                                    plan_text: str = ""):
        """Plan seçiminde kullanılan tarif ID'lerini günlük plana kaydet.
        Satır yoksa oluşturur (UPSERT), varsa tarif_idler + plan_detay günceller."""
        import json as _json
        await self.pool.execute(
            """INSERT INTO gunluk_plan (user_id, tarih, plan_detay, toplam_kalori, tarif_idler)
               VALUES ($1, $2, $3::jsonb, 0, $4)
               ON CONFLICT (user_id, tarih) DO UPDATE
               SET tarif_idler = EXCLUDED.tarif_idler,
                   plan_detay  = CASE
                       WHEN EXCLUDED.plan_detay::text != '{}'
                       THEN EXCLUDED.plan_detay
                       ELSE gunluk_plan.plan_detay
                   END""",
            user_id, plan_date,
            _json.dumps({"plan_text": plan_text} if plan_text else {}),
            tarif_ids,
        )

    async def get_tamamlayici_recipes(self) -> list:
        """
        Tüm tamamlayıcı (yan yemek) tariflerini döner.
        Plan karbonhidrat açığını kapatmak için kullanılır.
        Karbonhidrattan büyüğe sıralı döner (seçim algoritması için optimal).
        """
        rows = await self.pool.fetch(
            """
            SELECT tarif_id, ad, kategori, malzemeler,
                   porsiyon_gram, kalori, protein_g, karbonhidrat_g, yag_g, lif_g,
                   saglik_etiketler, ogun_tipleri, pismesi_dk, zorluk, aciklama
            FROM tarifler
            WHERE kategori = 'tamamlayici'
            ORDER BY karbonhidrat_g DESC
            """,
        )
        return [dict(r) for r in rows]

    async def get_recipes_by_category(self, kategori: str, limit: int = 5) -> list:
        """Belirli kategoriden rastgele tarif getir (vektör araması olmadan fallback)."""
        rows = await self.pool.fetch(
            """
            SELECT tarif_id, ad, kategori, kalori, protein_g, karbonhidrat_g, yag_g, lif_g,
                   saglik_etiketler, ogun_tipleri, aciklama
            FROM tarifler
            WHERE kategori = $1
            ORDER BY RANDOM()
            LIMIT $2
            """,
            kategori, limit,
        )
        return [dict(r) for r in rows]
