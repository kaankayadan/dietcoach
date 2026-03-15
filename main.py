"""
Türk Beslenme Koçu — Telegram Bot
Ana giriş noktası
"""
import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)
from settings import Settings
from handlers import BotHandlers
from database import Database
from claude_client import ClaudeClient
from scheduler import ReminderScheduler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    settings = Settings()
    db = Database(settings.database_url)
    claude = ClaudeClient(
        api_key=settings.anthropic_api_key,
        system_prompt_path="system_prompt.md",
    )

    async def post_init(app):
        await db.connect()
        logger.info("✅ Veritabanı bağlantısı kuruldu")
        scheduler = ReminderScheduler(db=db, app=app)
        scheduler.start()
        logger.info("✅ Hatırlatma scheduler başlatıldı")

    async def post_shutdown(app):
        await db.close()

    handlers = BotHandlers(db=db, claude=claude, settings=settings)

    app = (
        ApplicationBuilder()
        .token(settings.telegram_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("baslat", handlers.cmd_baslat))
    app.add_handler(CommandHandler("start", handlers.cmd_baslat))
    app.add_handler(CommandHandler("profil", handlers.cmd_profil))
    app.add_handler(CommandHandler("plan", handlers.cmd_plan))
    app.add_handler(CommandHandler("yedim", handlers.cmd_yedim))
    app.add_handler(CommandHandler("durum", handlers.cmd_durum))
    app.add_handler(CommandHandler("hafta", handlers.cmd_hafta))
    app.add_handler(CommandHandler("alternatif", handlers.cmd_alternatif))
    app.add_handler(CommandHandler("besin", handlers.cmd_besin))
    app.add_handler(CommandHandler("su", handlers.cmd_su))
    app.add_handler(CommandHandler("guncelle", handlers.cmd_guncelle))
    app.add_handler(CommandHandler("hedef", handlers.cmd_hedef))
    app.add_handler(CommandHandler("yardim", handlers.cmd_yardim))
    app.add_handler(CommandHandler("begenmiyorum", handlers.cmd_begenmiyorum))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handlers.handle_message,
    ))
    app.add_handler(MessageHandler(filters.PHOTO, handlers.handle_photo))

    logger.info("🥗 Beslenme Koçu Bot başlatılıyor...")
    app.run_polling()


if __name__ == "__main__":
    main()
