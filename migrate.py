"""
Veritabanı migration scripti — yeni özellikler için şema değişiklikleri.
VPS'de bir kez çalıştırılır: python migrate.py
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

MIGRATIONS = [
    # Migration 1: Tarif kara listesi
    """
    CREATE TABLE IF NOT EXISTS tarif_kara_liste (
        id SERIAL PRIMARY KEY,
        user_id INT REFERENCES users(id) ON DELETE CASCADE,
        tarif_id VARCHAR(100) NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(user_id, tarif_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_kara_liste_user ON tarif_kara_liste(user_id)",

    # Migration 2: Günlük plana tarif ID'leri sütunu ekle (haftalık çeşitlilik için)
    "ALTER TABLE gunluk_plan ADD COLUMN IF NOT EXISTS tarif_idler TEXT[] DEFAULT '{}'",
]


async def main():
    url = os.getenv("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL tanımlı değil")
        return

    conn = await asyncpg.connect(url)
    print("✅ DB bağlantısı kuruldu")

    for i, sql in enumerate(MIGRATIONS, 1):
        try:
            await conn.execute(sql.strip())
            print(f"  [{i}/{len(MIGRATIONS)}] OK: {sql.strip()[:60]}...")
        except Exception as e:
            print(f"  [{i}/{len(MIGRATIONS)}] HATA: {e}")

    await conn.close()
    print("\n✅ Migration tamamlandı")


if __name__ == "__main__":
    asyncio.run(main())
