"""
Hatırlatma Sistemi — Öğün saatlerinde bildirim, gün sonu takip, haftalık tartım.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from database import Database

logger = logging.getLogger(__name__)


class ReminderScheduler:
    def __init__(self, db: Database, app):
        self.db = db
        self.app = app
        self.scheduler = AsyncIOScheduler()
    
    def start(self):
        # Gün sonu takip hatırlatması — her gün 21:00
        self.scheduler.add_job(
            self._daily_tracking_reminder,
            CronTrigger(hour=21, minute=0),
            id="daily_tracking",
        )
        
        # Haftalık tartım hatırlatması — her Pazartesi 08:00
        self.scheduler.add_job(
            self._weekly_weigh_reminder,
            CronTrigger(day_of_week="mon", hour=8, minute=0),
            id="weekly_weigh",
        )
        
        # Su hatırlatması — her 3 saatte bir (09:00-21:00 arası)
        self.scheduler.add_job(
            self._water_reminder,
            CronTrigger(hour="9,12,15,18", minute=0),
            id="water_reminder",
        )
        
        self.scheduler.start()
        logger.info("⏰ Scheduler başlatıldı: günlük takip, haftalık tartım, su hatırlatması")
    
    async def _send_to_user(self, telegram_id: int, text: str):
        """Kullanıcıya direkt mesaj gönder."""
        try:
            await self.app.bot.send_message(chat_id=telegram_id, text=text)
        except Exception as e:
            logger.error(f"Mesaj gönderilemedi {telegram_id}: {e}")
    
    async def _get_active_users(self) -> list:
        """Onboarding'i tamamlamış aktif kullanıcıları getir."""
        rows = await self.db.pool.fetch(
            "SELECT telegram_id FROM users WHERE onboarding_step = 99 AND abonelik_durumu != 'pasif'"
        )
        return [r["telegram_id"] for r in rows]
    
    async def _daily_tracking_reminder(self):
        """Gün sonu: bugün ne yedin?"""
        users = await self._get_active_users()
        for tid in users:
            await self._send_to_user(tid, 
                "📊 Günün nasıl geçti?\n"
                "Bugün yediklerini kaydetmeyi unutma!\n"
                "/yedim komutuyla bildirebilirsin veya direkt yaz 😊"
            )
    
    async def _weekly_weigh_reminder(self):
        """Pazartesi sabahı: haftalık tartım."""
        users = await self._get_active_users()
        for tid in users:
            await self._send_to_user(tid,
                "⚖️ Haftalık tartım günü!\n"
                "Sabah aç karnına tartılıp kilonu paylaşır mısın?\n"
                "Örnek: \"78.5 kg\" yazman yeterli 📈"
            )
    
    async def _water_reminder(self):
        """Su hatırlatması."""
        users = await self._get_active_users()
        for tid in users:
            await self._send_to_user(tid, "💧 Su içmeyi unutma!")
