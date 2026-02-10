"""Uygulama ayarları — .env dosyasından okunur."""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    database_url: str = os.getenv("DATABASE_URL", "postgresql://localhost/beslenme_kocu")
    
    # Ödeme (opsiyonel)
    iyzico_api_key: str = os.getenv("IYZICO_API_KEY", "")
    iyzico_secret_key: str = os.getenv("IYZICO_SECRET_KEY", "")
