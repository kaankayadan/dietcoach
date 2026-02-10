"""Uygulama ayarları — .env dosyasından okunur."""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    database_url: str = os.getenv("DATABASE_URL", "postgresql://localhost/beslenme_kocu")
    
    # Admin — ödeme olmadan tam erişim
    admin_ids: list = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

    # Ödeme
    iyzico_api_key: str = os.getenv("IYZICO_API_KEY", "")
    iyzico_secret_key: str = os.getenv("IYZICO_SECRET_KEY", "")
    payment_url: str = os.getenv("PAYMENT_URL", "https://yourdomain.com/odeme")
