"""
Tarif İndexleme Scripti — Tek seferlik çalıştırılır.

Bu script:
1. recipes.json dosyasındaki tarifleri okur
2. Her tarifi paraphrase-multilingual-MiniLM-L12-v2 modeliyle vektörleştirir
3. Vektörleri PostgreSQL'deki tarifler tablosuna yazar
4. Vektör indeksi oluşturur (IVFFlat)

Kullanım:
    python index_recipes.py

Gereksinimler:
    - PostgreSQL'de pgvector extension'ı kurulu olmalı
    - tarifler tablosu oluşturulmuş olmalı (schema.sql çalıştırılmış)
    - sentence-transformers kurulu olmalı: pip install sentence-transformers
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

from embeddings import embedder, recipe_to_text

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def index_recipes(database_url: str, recipes_path: str = "recipes.json"):
    """Tarifleri vektörleştirir ve veritabanına yazar."""

    # Tarifleri oku
    recipes_file = Path(recipes_path)
    if not recipes_file.exists():
        logger.error(f"❌ Tarif dosyası bulunamadı: {recipes_path}")
        sys.exit(1)

    with open(recipes_file, encoding="utf-8") as f:
        recipes = json.load(f)

    logger.info(f"📖 {len(recipes)} tarif okundu")

    # Embedding metinleri hazırla
    texts = [recipe_to_text(r) for r in recipes]

    # Toplu vektörleştirme (daha hızlı)
    logger.info("🔢 Vektörleştirme başlıyor... (ilk çalıştırmada model indirilir ~120MB)")
    vectors = embedder.embed_batch(texts)
    logger.info(f"✅ {len(vectors)} tarif vektörleştirildi")

    # Veritabanına bağlan
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3)

    # pgvector extension'ını etkinleştir
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        logger.info("✅ pgvector extension aktif")

    # Tarifleri ve vektörleri kaydet
    inserted = 0
    updated = 0

    async with pool.acquire() as conn:
        for recipe, vector, text in zip(recipes, vectors, texts):
            # Vector'ü pgvector formatına dönüştür
            vector_str = "[" + ",".join(f"{v:.8f}" for v in vector) + "]"

            result = await conn.execute(
                """
                INSERT INTO tarifler (
                    tarif_id, ad, kategori, malzemeler, porsiyon_gram,
                    kalori, protein_g, karbonhidrat_g, yag_g, lif_g,
                    saglik_etiketler, ogun_tipleri, pismesi_dk, zorluk,
                    aciklama, tam_metin, embedding
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8, $9, $10,
                    $11, $12, $13, $14,
                    $15, $16, $17::vector
                )
                ON CONFLICT (tarif_id) DO UPDATE SET
                    ad = EXCLUDED.ad,
                    kategori = EXCLUDED.kategori,
                    malzemeler = EXCLUDED.malzemeler,
                    porsiyon_gram = EXCLUDED.porsiyon_gram,
                    kalori = EXCLUDED.kalori,
                    protein_g = EXCLUDED.protein_g,
                    karbonhidrat_g = EXCLUDED.karbonhidrat_g,
                    yag_g = EXCLUDED.yag_g,
                    lif_g = EXCLUDED.lif_g,
                    saglik_etiketler = EXCLUDED.saglik_etiketler,
                    ogun_tipleri = EXCLUDED.ogun_tipleri,
                    pismesi_dk = EXCLUDED.pismesi_dk,
                    zorluk = EXCLUDED.zorluk,
                    aciklama = EXCLUDED.aciklama,
                    tam_metin = EXCLUDED.tam_metin,
                    embedding = EXCLUDED.embedding
                """,
                recipe["id"],
                recipe["ad"],
                recipe.get("kategori"),
                recipe.get("malzemeler", []),
                recipe.get("porsiyon_gram"),
                recipe.get("kalori"),
                recipe.get("protein_g"),
                recipe.get("karbonhidrat_g"),
                recipe.get("yag_g"),
                recipe.get("lif_g"),
                recipe.get("saglik_etiketler", []),
                recipe.get("ogun_tipleri", []),
                recipe.get("pismesi_dk"),
                recipe.get("zorluk"),
                recipe.get("aciklama"),
                text,
                vector_str,
            )

            if "UPDATE" in result:
                updated += 1
            else:
                inserted += 1

    logger.info(f"✅ Veritabanı güncellendi: {inserted} yeni, {updated} güncellendi")

    # IVFFlat vektör indeksi oluştur (hızlı arama için)
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM tarifler")
        if count >= 10:
            try:
                await conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_tarifler_embedding
                    ON tarifler USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 10)
                    """
                )
                logger.info("✅ IVFFlat vektör indeksi oluşturuldu")
            except Exception as e:
                logger.warning(f"⚠️  Vektör indeksi oluşturulamadı (normal, IVFFlat için min. satır gerekir): {e}")
        else:
            logger.info(f"ℹ️  Şu an {count} tarif var, indeks oluşturmak için daha fazla tarif gerekiyor")

    await pool.close()

    # Özet
    logger.info("\n" + "="*50)
    logger.info(f"🎉 İndexleme tamamlandı!")
    logger.info(f"   Toplam tarif: {len(recipes)}")
    logger.info(f"   Embedding boyutu: 384")
    logger.info(f"   Model: paraphrase-multilingual-MiniLM-L12-v2")
    logger.info("="*50)
    logger.info("\nArtık bot yemek planı oluştururken gerçek tarif veritabanından")
    logger.info("semantik arama yaparak öneride bulunabilecek! 🥗")


if __name__ == "__main__":
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("❌ DATABASE_URL environment variable tanımlı değil")
        logger.error("   .env dosyasına DATABASE_URL ekleyin veya export edin")
        sys.exit(1)

    asyncio.run(index_recipes(database_url))
