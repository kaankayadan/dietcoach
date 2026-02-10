# 🥗 Türk Beslenme Koçu — Telegram Bot

Yapay zeka destekli, Türk mutfağına özel kişiselleştirilmiş beslenme koçu Telegram botu.

## Mimari

```
Telegram Kullanıcı
      │
      ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Telegram    │────▶│  Bot Handler │────▶│  Claude API │
│  Bot API     │◀────│  (Python)    │◀────│  (Anthropic)│
└─────────────┘     └──────┬───────┘     └─────────────┘
                           │
                    ┌──────▼───────┐
                    │  PostgreSQL  │
                    │  (Kullanıcı  │
                    │   profiller, │
                    │   takip,     │
                    │   öğünler)   │
                    └──────────────┘
```

## Tech Stack

- **Python 3.11+**
- **python-telegram-bot** — Telegram bot framework
- **anthropic** — Claude API SDK
- **asyncpg** — Async PostgreSQL driver
- **APScheduler** — Hatırlatma scheduler

## Kurulum

```bash
# 1. Repo'yu klonla
git clone <repo-url>
cd beslenme-kocu-bot

# 2. Virtual environment
python -m venv venv
source venv/bin/activate

# 3. Dependencies
pip install -r requirements.txt

# 4. Environment variables
cp .env.example .env
# .env dosyasını düzenle: TELEGRAM_TOKEN, ANTHROPIC_API_KEY, DATABASE_URL

# 5. Veritabanı oluştur
psql -f sql/schema.sql

# 6. Çalıştır
python src/main.py
```

## Dosya Yapısı

```
beslenme-kocu-bot/
├── src/
│   ├── main.py              # Entry point, bot başlatma
│   ├── handlers.py          # Telegram komut ve mesaj handler'ları
│   ├── claude_client.py     # Claude API wrapper
│   ├── database.py          # DB işlemleri (profil, öğün, takip)
│   ├── calculations.py      # BMR, TDEE, makro hesaplamaları
│   ├── scheduler.py         # Hatırlatma sistemi
│   └── models.py            # Pydantic data modelleri
├── prompts/
│   └── system_prompt.md     # Claude system prompt (beslenme koçu kişiliği + kurallar)
├── sql/
│   └── schema.sql           # PostgreSQL şeması
├── config/
│   └── settings.py          # Ayarlar
├── .env.example
├── requirements.txt
└── README.md
```

## Komutlar

| Komut | Açıklama |
|-------|----------|
| `/baslat` | Onboarding başlat |
| `/profil` | Profil kartını göster |
| `/plan` | Günlük planı göster |
| `/yedim` | Öğün kaydet |
| `/durum` | Günlük uyum durumu |
| `/hafta` | Haftalık rapor |
| `/alternatif` | Öğün alternatifi |
| `/besin` | Besin değeri sorgula |
| `/su` | Su kaydı |

Ayrıca serbest metin de desteklenir — kullanıcı doğal dilde yazabilir.
