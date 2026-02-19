"""
Telegram Bot Handler'ları — Her mesajda:
1. Kullanıcıyı DB'den çek
2. Güncel context'i topla (profil, öğünler, plan, haftalık durum)
3. Claude'a gönder
4. Yanıtı kullanıcıya ilet
5. Onboarding metadata varsa parse et ve DB güncelle
"""
import re
import json
import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.database import Database
from src.claude_client import ClaudeClient
from src.meal_validator import strip_mealplan_json
from src.target_calculator import calculate_user_targets

logger = logging.getLogger(__name__)

# Alan adı normalizasyonu — Claude bazen farklı isimler kullanabilir
FIELD_ALIASES = {
    "boy": "boy_cm",
    "kilo": "kilo_kg",
    "vücut_yağ_oranı": "vucut_yag_orani",
    "vucut_yag": "vucut_yag_orani",
    "vyo": "vucut_yag_orani",
    "aktivite": "aktivite_seviyesi",
    "hedef": "hedef_tip",
    "hastalik": "kronik_hastaliklar",
    "hastaliklar": "kronik_hastaliklar",
    "saglik": "kronik_hastaliklar",
    "sindirim": "sindirim_sorunlari",
    "alerji": "alerjiler",
    "ilac": "ilaclar",
    "mutfak": "mutfak_stili",
    "sevilen": "sevilen_yiyecekler",
    "sevilmeyen": "sevilmeyen_yiyecekler",
    "ogun": "ogun_duzeni",
}

# DB'de TEXT[] olan alanlar — list olmalı
ARRAY_FIELDS = [
    "kronik_hastaliklar",
    "sindirim_sorunlari",
    "alerjiler",
    "sevilen_yiyecekler",
    "sevilmeyen_yiyecekler",
]

# DB'de numeric olan alanlar
NUMERIC_FIELDS = {
    "boy_cm": float,
    "kilo_kg": float,
    "vucut_yag_orani": float,
    "hedef_kilo": float,
    "bel_cevresi_cm": float,
    "yas": int,
}

# Profil alanları — mevcut profil ile merge için
PROFILE_FIELDS = [
    "isim", "yas", "cinsiyet", "boy_cm", "kilo_kg",
    "vucut_yag_orani", "yagsiz_kutle_kg", "bel_cevresi_cm",
    "vyo_yontemi", "aktivite_seviyesi",
    "kronik_hastaliklar", "sindirim_sorunlari", "alerjiler", "ilaclar",
    "hedef_tip", "hedef_kilo", "agresiflik",
    "mutfak_stili", "sevilen_yiyecekler", "sevilmeyen_yiyecekler",
    "ogun_duzeni", "if_penceresi",
]

# Telegram mesaj limiti
MAX_MSG_LENGTH = 4096


class BotHandlers:
    def __init__(self, db: Database, claude: ClaudeClient, settings):
        self.db = db
        self.claude = claude
        self.settings = settings

    async def _get_full_context(self, telegram_id: int) -> dict:
        """Kullanıcının tüm güncel verilerini topla — her mesajda çağrılır."""
        user = await self.db.get_user(telegram_id)
        if not user:
            return {"user": None}

        user_id = user["id"]
        return {
            "user": user,
            "recent_meals": await self.db.get_todays_meals(user_id),
            "daily_summary": await self.db.get_daily_summary(user_id),
            "weekly_summary": await self.db.get_weekly_summary(user_id),
            "todays_plan": await self.db.get_todays_plan(user_id),
            "conversation_history": await self.db.get_conversation_history(user_id),
            "weekly_meals": await self.db.get_weekly_meals(user_id),
            "weekly_water": await self.db.get_weekly_water(user_id),
            "todays_water": await self.db.get_todays_water(user_id),
        }

    async def _send_to_claude(self, update: Update, message: str):
        """Mesajı Claude'a gönder, yanıtı kullanıcıya ilet."""
        telegram_id = update.effective_user.id
        ctx = await self._get_full_context(telegram_id)

        if not ctx["user"]:
            await update.message.reply_text(
                "Henüz kayıtlı değilsin! /baslat yazarak başlayabilirsin 🌟"
            )
            return

        # Claude'a gönder
        response = await self.claude.chat(
            user_message=message,
            user=ctx["user"],
            recent_meals=ctx["recent_meals"],
            daily_summary=ctx["daily_summary"],
            weekly_summary=ctx["weekly_summary"],
            todays_plan=ctx["todays_plan"],
            conversation_history=ctx["conversation_history"],
            weekly_meals=ctx["weekly_meals"],
            weekly_water=ctx["weekly_water"],
            todays_water=ctx["todays_water"],
        )

        # Onboarding metadata parse et (kullanıcıya görünmez)
        response_clean = await self._parse_onboarding_metadata(
            telegram_id, ctx["user"], response
        )

        # MEALPLAN_JSON bloğunu temizle (kullanıcıya görünmez)
        response_clean = strip_mealplan_json(response_clean)

        # Mesajları kaydet
        user_id = ctx["user"]["id"]
        await self.db.save_message(user_id, "user", message)
        await self.db.save_message(user_id, "assistant", response_clean)

        # Telegram'a gönder (uzun mesajları böl)
        await self._send_long_message(update, response_clean)

    def _normalize_data(self, data: dict) -> dict:
        """Array ve numeric alanları DB'ye uygun tipe dönüştür."""
        # Array alanları: string → list
        for field in ARRAY_FIELDS:
            val = data.get(field)
            if isinstance(val, str):
                data[field] = [v.strip() for v in val.split(",") if v.strip()]
            elif val is not None and not isinstance(val, list):
                data[field] = [str(val)]

        # Numeric alanları: string → int/float
        for field, type_fn in NUMERIC_FIELDS.items():
            val = data.get(field)
            if val is not None:
                try:
                    data[field] = type_fn(float(val))
                except (ValueError, TypeError):
                    pass

        return data

    async def _save_profile(self, telegram_id: int, user: dict, new_data: dict):
        """
        Profil kaydet — mevcut kullanıcı verilerini koru, sadece yeni değerleri üstüne yaz.
        Hedefleri yeniden hesapla ve DB'ye kaydet.
        """
        # Mevcut profil verilerini DB sütunlarından al (source of truth)
        existing = {}
        for field in PROFILE_FIELDS:
            val = user.get(field)
            if val is not None:
                existing[field] = val

        # Yeni veriyi mevcut verinin üstüne yaz
        merged = {**existing, **new_data}

        # Normalize et
        merged = self._normalize_data(merged)

        # BMR / TDEE / Makro hedeflerini Python'da hesapla
        targets = calculate_user_targets(merged)
        if targets:
            merged.update(targets)
            logger.info(
                f"Profil kaydedildi — hedefler: "
                f"TDEE={targets.get('tdee')} → Hedef={targets.get('hedef_kalori')} kcal | "
                f"P:{targets.get('protein_g')}g K:{targets.get('karbonhidrat_g')}g "
                f"Y:{targets.get('yag_g')}g"
            )
        else:
            logger.warning("Profil kaydedildi ama hedef hesaplanamadı — eksik veri")

        await self.db.complete_onboarding(telegram_id, merged)

    async def _parse_onboarding_metadata(self, telegram_id: int, user: dict, response: str) -> str:
        """
        Claude'un yanıtındaki onboarding metadata'sını parse et.
        Format: <!--ONBOARDING:{"step": 3, "field": "cinsiyet", "value": "erkek", "valid": true}-->

        Hem yeni onboarding (/baslat) hem profil güncelleme (/guncelle) için çalışır.
        - Yeni kullanıcı: veriyi biriktirir, step 15'te complete_onboarding çağırır
        - Mevcut kullanıcı (step=99): her metadata'da hemen profili günceller
        """
        pattern = r'<!--ONBOARDING:(.*?)-->'
        matches = re.findall(pattern, response)

        if not matches:
            return response

        # Mevcut onboarding verisini bir kez yükle (loop dışında — multi-field bug fix)
        onboarding_data = json.loads(user.get("onboarding_data") or "{}")
        latest_step = user.get("onboarding_step", 0)
        is_existing_user = latest_step == 99
        should_complete = False
        fields_updated = []

        for match in matches:
            try:
                meta = json.loads(match)
                if meta.get("valid") and "field" in meta:
                    # Alan adını normalize et
                    field = meta["field"]
                    field = FIELD_ALIASES.get(field, field)

                    onboarding_data[field] = meta["value"]
                    fields_updated.append(field)

                    step = meta.get("step", latest_step)
                    if not is_existing_user:
                        latest_step = max(latest_step, step + 1)

                    if step + 1 > 15 or meta.get("complete"):
                        should_complete = True
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Onboarding metadata parse hatası: {e}")

        if not fields_updated:
            clean = re.sub(pattern, '', response).strip()
            return clean

        if is_existing_user:
            # ── Mevcut kullanıcı (profil güncelleme) ──
            # Her metadata'da hemen profili güncelle — merge ile
            logger.info(f"Profil güncelleme: {', '.join(fields_updated)}")
            await self._save_profile(telegram_id, user, onboarding_data)

        elif should_complete:
            # ── Yeni kullanıcı — onboarding tamamlandı ──
            logger.info(f"Yeni kullanıcı onboarding tamamlandı")
            merged = self._normalize_data(onboarding_data)
            targets = calculate_user_targets(merged)
            if targets:
                merged.update(targets)
                logger.info(
                    f"Hedefler hesaplandı: TDEE={targets.get('tdee')} → "
                    f"Hedef={targets.get('hedef_kalori')} kcal"
                )
            else:
                logger.warning("Hedef hesaplanamadı — eksik veri olabilir")
            await self.db.complete_onboarding(telegram_id, merged)

        else:
            # ── Yeni kullanıcı — onboarding devam ediyor ──
            await self.db.update_onboarding(
                telegram_id, latest_step, onboarding_data
            )

        # Metadata'yı yanıttan temizle
        clean = re.sub(pattern, '', response).strip()
        return clean

    async def _send_long_message(self, update: Update, text: str):
        """Telegram 4096 karakter limitine göre mesajı böl."""
        if len(text) <= MAX_MSG_LENGTH:
            await update.message.reply_text(text)
        else:
            parts = [text[i:i+MAX_MSG_LENGTH] for i in range(0, len(text), MAX_MSG_LENGTH)]
            for part in parts:
                await update.message.reply_text(part)

    # ==========================================
    # KOMUT HANDLER'LARI
    # ==========================================

    async def cmd_baslat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Onboarding başlat."""
        telegram_id = update.effective_user.id
        user = await self.db.get_user(telegram_id)

        if user and user["onboarding_step"] == 99:
            await update.message.reply_text(
                "Zaten kayıtlısın! Profil bilgilerini güncellemek istersen /guncelle yazabilirsin 😊"
            )
            return

        await self.db.create_user(telegram_id)
        await self._send_to_claude(update, "/baslat — Yeni kullanıcı onboarding başlat")

    async def cmd_profil(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._send_to_claude(update, "/profil — Profil kartımı göster")

    async def cmd_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._send_to_claude(update, "/plan — Bugünkü beslenme planımı göster veya oluştur")

    async def cmd_yedim(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = " ".join(context.args) if context.args else ""
        if text:
            await self._send_to_claude(update, f"/yedim {text}")
        else:
            await update.message.reply_text(
                "Ne yediğini yaz! Örnek: /yedim 1 kase mercimek çorbası + 1 dilim ekmek"
            )

    async def cmd_durum(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._send_to_claude(update, "/durum — Bugünkü uyum durumumu göster")

    async def cmd_hafta(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._send_to_claude(update, "/hafta — Haftalık özet raporumu göster")

    async def cmd_alternatif(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = " ".join(context.args) if context.args else "bir sonraki öğün"
        await self._send_to_claude(update, f"/alternatif — {text} için alternatif öner")

    async def cmd_besin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = " ".join(context.args) if context.args else ""
        if text:
            await self._send_to_claude(update, f"/besin — {text} besin değerlerini göster")
        else:
            await update.message.reply_text("Hangi besini sorgulamak istiyorsun? Örnek: /besin tavuk göğsü")

    async def cmd_su(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = " ".join(context.args) if context.args else "1"
        telegram_id = update.effective_user.id
        user = await self.db.get_user(telegram_id)
        if user:
            try:
                bardak = int(text)
            except ValueError:
                bardak = 1
            for _ in range(max(1, min(bardak, 20))):
                await self.db.save_water(user["id"], 200)
        await self._send_to_claude(update, f"/su — {text} bardak su içtim")

    async def cmd_guncelle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._send_to_claude(update, "/guncelle — Profil bilgilerimi güncellemek istiyorum")

    async def cmd_hedef(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._send_to_claude(update, "/hedef — İlerleme raporumu göster")

    async def cmd_yardim(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """🥗 *Beslenme Koçu Komutları*

/baslat — Yeni kayıt ve onboarding
/profil — Profil kartını göster
/plan — Günlük beslenme planı
/yedim [ne yediğin] — Öğün kaydet
/durum — Günlük uyum durumu
/hafta — Haftalık rapor
/alternatif [öğün] — Alternatif öner
/besin [besin adı] — Besin değeri sorgula
/su [bardak] — Su kaydı
/guncelle — Profil güncelle
/hedef — İlerleme raporu

💬 Komut kullanmadan da yazabilirsin!
"Öğlen ne yesem?" veya "100g pirinçte ne kadar kalori var?" gibi."""
        await update.message.reply_text(help_text, parse_mode="Markdown")

    # ==========================================
    # SERBEST METİN VE FOTOĞRAF
    # ==========================================

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Komut olmayan her metin mesajı Claude'a gönder."""
        await self._send_to_claude(update, update.message.text)

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Yemek fotoğrafı — şimdilik caption'ı kullan."""
        caption = update.message.caption or "Yemek fotoğrafı gönderildi"
        await self._send_to_claude(
            update,
            f"[Yemek fotoğrafı gönderildi] {caption} — Bu yemeğin besin değerlerini tahmin et."
        )
