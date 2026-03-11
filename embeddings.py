"""
Lokal Embedding Modülü — sentence-transformers ile Türkçe destekli vektörleştirme.
Model: paraphrase-multilingual-MiniLM-L12-v2 (~120MB, 384 boyut, CPU uyumlu)

Yemek tarifleri bu modülle vektörleştirilir ve pgvector'da saklanır.
Kullanıcı sorguları da aynı modelle vektörleştirilip semantik arama yapılır.
"""
import asyncio
import logging
from functools import lru_cache
from typing import List

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


class RecipeEmbedder:
    """
    Singleton embedding sınıfı — model bir kez yüklenir, tüm çağrılarda paylaşılır.
    sentence-transformers yükü ağır olduğu için ilk kullanımda lazy loading yapılır.
    """
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load_model(self):
        """Model ilk kez kullanıldığında yüklenir."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Embedding modeli yükleniyor: {MODEL_NAME}")
                self._model = SentenceTransformer(MODEL_NAME)
                logger.info("✅ Embedding modeli hazır")
            except ImportError:
                raise ImportError(
                    "sentence-transformers yüklü değil. "
                    "Lütfen çalıştırın: pip install sentence-transformers"
                )

    def embed(self, text: str) -> List[float]:
        """Tek bir metni vektörleştirir. Liste olarak döner (pgvector uyumlu)."""
        self._load_model()
        vector = self._model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Çoklu metni toplu olarak vektörleştirir (indexleme için verimli)."""
        self._load_model()
        vectors = self._model.encode(texts, normalize_embeddings=True, batch_size=32)
        return [v.tolist() for v in vectors]

    async def async_embed(self, text: str) -> List[float]:
        """
        Async wrapper — bot'un event loop'unu bloklamadan embedding oluşturur.
        CPU-bound işlem olduğu için thread executor'da çalışır.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed, text)


def recipe_to_text(recipe: dict) -> str:
    """
    Tarifi embedding için tek bir string'e dönüştürür.
    Semantik arama kalitesi bu text'in zenginliğine bağlıdır.
    """
    parts = [
        recipe["ad"],
        recipe.get("kategori", ""),
        "Malzemeler: " + ", ".join(recipe.get("malzemeler", [])),
        "Sağlık özellikleri: " + ", ".join(recipe.get("saglik_etiketler", [])),
        f"Öğün tipi: {', '.join(recipe.get('ogun_tipleri', []))}",
        recipe.get("aciklama", ""),
        f"Kalori: {recipe.get('kalori')} kcal",
        f"Protein: {recipe.get('protein_g')}g, Karbonhidrat: {recipe.get('karbonhidrat_g')}g, Yağ: {recipe.get('yag_g')}g, Lif: {recipe.get('lif_g')}g",
    ]
    return " | ".join(filter(None, parts))


# Global singleton instance
embedder = RecipeEmbedder()
