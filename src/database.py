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
    
    # Claude'un gönderebileceği alan adı varyasyonları → DB'deki doğru alan adı
    _FIELD_ALIASES = {
        "ad": "isim", "name": "isim",
        "yaş": "yas", "age": "yas",
        "gender": "cinsiyet",
        "boy": "boy_cm", "height": "boy_cm",
        "kilo": "kilo_kg", "weight": "kilo_kg", "agirlik": "kilo_kg",
        "vyo": "vucut_yag_orani", "vucut_yag": "vucut_yag_orani", "yag_orani": "vucut_yag_orani",
        "bel_cevresi": "bel_cevresi_cm", "bel": "bel_cevresi_cm",
        "yagsiz_kutle": "yagsiz_kutle_kg", "lbm": "yagsiz_kutle_kg",
        "aktivite": "aktivite_seviyesi",
        "hastaliklar": "kronik_hastaliklar", "kronik": "kronik_hastaliklar",
        "sindirim": "sindirim_sorunlari",
        "alerji": "alerjiler",
        "ilac": "ilaclar",
        "hedef": "hedef_tip",
        "mutfak": "mutfak_stili",
        "sevilen": "sevilen_yiyecekler",
        "sevilmeyen": "sevilmeyen_yiyecekler",
        "ogun": "ogun_duzeni",
    }

    def _normalize_profile_data(self, data: dict) -> dict:
        """Alan adı varyasyonlarını standart DB alan adlarına dönüştür."""
        normalized = {}
        for key, value in data.items():
            canonical = self._FIELD_ALIASES.get(key, key)
            # Zaten standart isimle bir değer varsa onu koruyoruz
            if canonical not in normalized or normalized[canonical] is None:
                normalized[canonical] = value
        return normalized

    async def complete_onboarding(self, telegram_id: int, profile_data: dict):
        """
        Onboarding tamamlandığında tüm profil verilerini kaydet.
        profile_data içinde hesaplanmış BMR, TDEE, makrolar da olacak.
        Alan adı normalize edilir (boy → boy_cm, kilo → kilo_kg, vb.).
        """
        d = self._normalize_profile_data(profile_data)

        # Sayısal alanları güvenli şekilde cast et
        def _num(key, typ=float):
            val = d.get(key)
            if val is None:
                return None
            try:
                return typ(val)
            except (ValueError, TypeError):
                return None

        # Liste alanlarını güvenli şekilde cast et
        def _list(key):
            val = d.get(key)
            if val is None:
                return None
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                return [val] if val.strip() else None
            return None

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
                onboarding_step = 99, onboarding_data = $35, updated_at = NOW()
               WHERE telegram_id = $1""",
            telegram_id,
            d.get('isim'), _num('yas', int),
            d.get('cinsiyet'), _num('boy_cm'),
            _num('kilo_kg'), _num('vucut_yag_orani'),
            _num('yagsiz_kutle_kg'), _num('bel_cevresi_cm'),
            d.get('vyo_yontemi'), d.get('aktivite_seviyesi'),
            _list('kronik_hastaliklar'), _list('sindirim_sorunlari'),
            _list('alerjiler'), json.dumps(d.get('ilaclar', []), ensure_ascii=False),
            d.get('hedef_tip'), _num('hedef_kilo'),
            d.get('agresiflik'), d.get('mutfak_stili'),
            _list('sevilen_yiyecekler'), _list('sevilmeyen_yiyecekler'),
            d.get('ogun_duzeni'), d.get('if_penceresi'),
            _num('bmr'), _num('neat'),
            _num('tef'), _num('eat_gunluk'),
            _num('tdee'), _num('hedef_kalori'),
            _num('protein_g'), _num('karbonhidrat_g'),
            _num('yag_g'), _num('lif_g'),
            _num('su_hedefi_litre'),
            json.dumps(d, ensure_ascii=False),  # Tüm veriyi onboarding_data'da da sakla (fallback)
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

    async def get_yesterday_plan(self, user_id: int) -> Optional[dict]:
        """Dünkü planı getir — ardışık gün protein tekrar kontrolü için."""
        row = await self.pool.fetchrow(
            "SELECT * FROM gunluk_plan WHERE user_id = $1 AND tarih = $2",
            user_id, date.today() - timedelta(days=1),
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
    
    # ==========================================
    # ABONELİK İŞLEMLERİ
    # ==========================================

    async def check_subscription(self, telegram_id: int) -> dict:
        """Kullanıcının abonelik durumunu kontrol et."""
        user = await self.get_user(telegram_id)
        if not user:
            return {"aktif": False, "durum": "kayitsiz"}

        durum = user.get("abonelik_durumu", "trial")
        bitis = user.get("abonelik_bitis")

        # Trial kullanıcılar: onboarding'e izin ver ama sonrasında ödeme iste
        if durum == "trial":
            return {"aktif": True, "durum": "trial", "bitis": None}

        # Aktif abonelik: bitiş tarihini kontrol et
        if durum == "aktif":
            if bitis and bitis < date.today():
                # Abonelik süresi dolmuş — pasife al
                await self.pool.execute(
                    "UPDATE users SET abonelik_durumu = 'pasif', updated_at = NOW() WHERE telegram_id = $1",
                    telegram_id,
                )
                return {"aktif": False, "durum": "suresi_dolmus", "bitis": bitis}
            return {"aktif": True, "durum": "aktif", "bitis": bitis}

        # Pasif
        return {"aktif": False, "durum": "pasif", "bitis": bitis}

    async def activate_subscription(self, telegram_id: int, plan_tipi: str) -> date:
        """Aboneliği aktifle — ödeme başarılı olduğunda çağrılır."""
        sure_gun = {"aylik": 30, "3aylik": 90, "yillik": 365}
        gun = sure_gun.get(plan_tipi, 30)

        user = await self.get_user(telegram_id)
        bugun = date.today()

        # Mevcut abonelik varsa üstüne ekle
        mevcut_bitis = user.get("abonelik_bitis") if user else None
        if mevcut_bitis and mevcut_bitis > bugun:
            baslangic = mevcut_bitis
        else:
            baslangic = bugun

        bitis = baslangic + timedelta(days=gun)

        await self.pool.execute(
            """UPDATE users SET abonelik_durumu = 'aktif', abonelik_bitis = $2, updated_at = NOW()
               WHERE telegram_id = $1""",
            telegram_id, bitis,
        )
        return bitis

    async def save_payment(self, telegram_id: int, user_id: int, tutar: float,
                           plan_tipi: str, odeme_durumu: str,
                           iyzico_payment_id: str = None) -> int:
        """Ödeme kaydı oluştur."""
        baslangic = date.today()
        sure_gun = {"aylik": 30, "3aylik": 90, "yillik": 365}
        bitis = baslangic + timedelta(days=sure_gun.get(plan_tipi, 30))

        row = await self.pool.fetchrow(
            """INSERT INTO odemeler (user_id, telegram_id, tutar, odeme_durumu, plan_tipi,
                   baslangic_tarihi, bitis_tarihi, iyzico_payment_id)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               RETURNING id""",
            user_id, telegram_id, tutar, odeme_durumu, plan_tipi,
            baslangic, bitis, iyzico_payment_id,
        )
        return row["id"]

    async def get_weight_history(self, user_id: int, limit: int = 12) -> list:
        rows = await self.pool.fetch(
            """SELECT tarih, kilo_kg FROM kilo_gecmisi 
               WHERE user_id = $1 ORDER BY tarih DESC LIMIT $2""",
            user_id, limit,
        )
        return [dict(r) for r in reversed(rows)]
