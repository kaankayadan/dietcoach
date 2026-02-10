"""
Türk Beslenme Koçu — Telegram Bot
Ana giriş noktası
"""
import asyncio
import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)
from config.settings import Settings
from src.handlers import BotHandlers
from src.database import Database
from src.claude_client import ClaudeClient
from src.scheduler import ReminderScheduler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def main():
    settings = Settings()
    
    # Veritabanı bağlantısı
    db = Database(settings.database_url)
    await db.connect()
    logger.info("✅ Veritabanı bağlantısı kuruldu")
    
    # Claude API client
    claude = ClaudeClient(
        api_key=settings.anthropic_api_key,
        system_prompt_path="prompts/system_prompt.md",
    )
    logger.info("✅ Claude API client hazır")
    
    # Telegram bot
    app = ApplicationBuilder().token(settings.telegram_token).build()
    
    # Handler'ları oluştur
    handlers = BotHandlers(db=db, claude=claude, settings=settings)
    
    # Komut handler'ları
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
    
    # Serbest metin handler (komut olmayan her mesaj)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handlers.handle_message,
    ))
    
    # Fotoğraf handler (yemek fotoğrafı)
    app.add_handler(MessageHandler(filters.PHOTO, handlers.handle_photo))
    
    # Hatırlatma scheduler
    scheduler = ReminderScheduler(db=db, app=app)
    scheduler.start()
    logger.info("✅ Hatırlatma scheduler başlatıldı")
    
    # Bot'u başlat
    logger.info("🥗 Beslenme Koçu Bot başlatılıyor...")
    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
