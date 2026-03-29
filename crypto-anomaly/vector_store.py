"""
In-memory vector store with TurboQuant compression.

- Pre-allocated ring buffer for O(1) inserts
- Cached decoded matrix for fast brute-force NN search
- 24-hour sliding window eviction
- Metadata storage alongside each vector
"""

import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from turboquant import TurboQuantMSE

logger = logging.getLogger(__name__)

# Intervals (in minutes) for subsequent move tracking
SUBSEQUENT_INTERVALS = [5, 15, 60]


@dataclass
class SubsequentMove:
    """Price movement after a pattern was observed."""
    interval_minutes: int
    price_at_pattern: float
    price_after: float
    pct_change: float  # percentage change


@dataclass
class SearchResult:
    """Result from a nearest-neighbor search."""
    index: int
    score: float  # inner product (higher = more similar)
    distance: float  # L2 distance (lower = more similar)
    metadata: dict[str, Any]
    subsequent_moves: list[SubsequentMove] = field(default_factory=list)


class VectorStore:
    """In-memory quantized vector store with brute-force NN search."""

    def __init__(self, quantizer: TurboQuantMSE, max_vectors: int = 100_000):
        self.quantizer = quantizer
        self.max_vectors = max_vectors
        self.d = quantizer.d

        # Pre-allocated storage
        self._codes = np.zeros((max_vectors, self.d), dtype=np.uint8)
        self._timestamps = np.zeros(max_vectors, dtype=np.float64)
        self._valid = np.zeros(max_vectors, dtype=bool)
        self._metadata: list[dict[str, Any] | None] = [None] * max_vectors

        # Ring buffer state
        self._write_ptr = 0
        self._count = 0

        # Cached decoded vectors for fast search
        self._decoded_cache = np.zeros((max_vectors, self.d), dtype=np.float64)
        self._cache_dirty = np.ones(max_vectors, dtype=bool)

        # Price history per symbol: {symbol: [(timestamp, price), ...]}
        # Used to compute subsequent price moves for historical patterns
        self._price_history: dict[str, list[tuple[float, float]]] = defaultdict(list)
        self._max_price_history = 10_000  # per symbol

    @property
    def count(self) -> int:
        """Number of valid vectors in the store."""
        return int(np.sum(self._valid))

    def add(self, vector: np.ndarray, metadata: dict[str, Any]) -> int:
        """Quantize and store a vector with metadata.

        Args:
            vector: Shape (d,) unit-norm vector.
            metadata: Dict with keys like symbol, price, volume, timestamp.

        Returns:
            Index where the vector was stored.
        """
        idx = self._write_ptr

        # Encode
        indices = self.quantizer.encode(vector)
        self._codes[idx] = indices
        self._timestamps[idx] = metadata.get("timestamp", time.time())
        self._valid[idx] = True
        self._metadata[idx] = metadata

        # Update decoded cache for this entry
        self._decoded_cache[idx] = self.quantizer.decode(indices)
        self._cache_dirty[idx] = False

        # Advance ring buffer
        self._write_ptr = (self._write_ptr + 1) % self.max_vectors
        self._count = min(self._count + 1, self.max_vectors)

        return idx

    def search(self, query_vector: np.ndarray, top_k: int = 10,
               exclude_symbol: str | None = None,
               exclude_recent: int = 0) -> list[SearchResult]:
        """Find the top-k most similar vectors.

        Uses inner product on decoded (dequantized) vectors.
        Since all vectors are unit-norm, IP and L2 distance are equivalent:
        distance = 2 - 2 * inner_product.

        Args:
            query_vector: Shape (d,) unit-norm query vector.
            top_k: Number of results to return.
            exclude_symbol: Optionally exclude vectors from this symbol.
            exclude_recent: Skip the N most recently added vectors.

        Returns:
            List of SearchResult sorted by descending similarity.
        """
        valid_mask = self._valid.copy()

        # Exclude recent entries
        if exclude_recent > 0:
            for i in range(exclude_recent):
                idx = (self._write_ptr - 1 - i) % self.max_vectors
                if idx >= 0:
                    valid_mask[idx] = False

        valid_indices = np.where(valid_mask)[0]
        if len(valid_indices) == 0:
            return []

        # Refresh any dirty cache entries (shouldn't happen normally)
        dirty = self._cache_dirty[valid_indices]
        if np.any(dirty):
            dirty_idx = valid_indices[dirty]
            self._decoded_cache[dirty_idx] = self.quantizer.decode_batch(
                self._codes[dirty_idx]
            ) if len(dirty_idx) > 1 else self.quantizer.decode(self._codes[dirty_idx[0]])
            self._cache_dirty[dirty_idx] = False

        # Compute inner products: decoded_vectors @ query
        decoded = self._decoded_cache[valid_indices]  # (n_valid, d)
        scores = decoded @ query_vector  # (n_valid,)

        # Filter by symbol if needed
        if exclude_symbol:
            symbol_mask = np.array([
                self._metadata[i] is not None and self._metadata[i].get("symbol") != exclude_symbol
                for i in valid_indices
            ])
            if not np.any(symbol_mask):
                # All same symbol — don't filter
                symbol_mask = np.ones(len(valid_indices), dtype=bool)
            scores_filtered = scores.copy()
            scores_filtered[~symbol_mask] = -np.inf
        else:
            scores_filtered = scores

        # Get top-k
        k = min(top_k, len(valid_indices))
        top_indices = np.argpartition(scores_filtered, -k)[-k:]
        top_indices = top_indices[np.argsort(scores_filtered[top_indices])[::-1]]

        results = []
        for local_idx in top_indices:
            global_idx = valid_indices[local_idx]
            ip = float(scores[local_idx])
            dist = 2.0 - 2.0 * ip
            meta = self._metadata[global_idx] or {}

            # Look up subsequent price moves for this historical pattern
            sub_moves = self._get_subsequent_moves(
                symbol=meta.get("symbol", ""),
                pattern_timestamp=meta.get("timestamp", 0),
                pattern_price=meta.get("price", 0),
            )

            results.append(SearchResult(
                index=int(global_idx),
                score=ip,
                distance=max(0.0, dist),
                metadata=meta,
                subsequent_moves=sub_moves,
            ))

        return results

    def get_anomaly_score(self, query_vector: np.ndarray, k: int = 10,
                          exclude_recent: int = 5) -> float:
        """Compute anomaly score: average distance to k nearest neighbors.

        Higher score = more anomalous (further from known patterns).

        Args:
            query_vector: Shape (d,) unit-norm vector.
            k: Number of neighbors.
            exclude_recent: Skip recent entries to avoid self-matching.

        Returns:
            Average L2 distance to k nearest neighbors. 0.0 if insufficient data.
        """
        results = self.search(query_vector, top_k=k, exclude_recent=exclude_recent)
        if not results:
            return 0.0
        return float(np.mean([r.distance for r in results]))

    def evict_old(self, max_age_seconds: float) -> int:
        """Remove vectors older than max_age_seconds.

        Args:
            max_age_seconds: Maximum age in seconds.

        Returns:
            Number of evicted vectors.
        """
        now = time.time()
        cutoff = now - max_age_seconds
        old_mask = (self._timestamps < cutoff) & self._valid
        evicted = int(np.sum(old_mask))

        if evicted > 0:
            self._valid[old_mask] = False
            self._cache_dirty[old_mask] = True
            logger.debug(f"Evicted {evicted} old vectors (>{max_age_seconds/3600:.1f}h)")

        return evicted

    def record_price(self, symbol: str, timestamp: float, price: float) -> None:
        """Record a price point for subsequent move analysis.

        Call this on every candle close to build price history.
        """
        history = self._price_history[symbol]
        history.append((timestamp, price))
        # Trim old entries
        if len(history) > self._max_price_history:
            self._price_history[symbol] = history[-self._max_price_history:]

    def _get_subsequent_moves(self, symbol: str, pattern_timestamp: float,
                               pattern_price: float) -> list[SubsequentMove]:
        """Look up what happened to price after a historical pattern.

        For each interval in SUBSEQUENT_INTERVALS, find the closest price
        point after pattern_timestamp + interval and compute % change.
        """
        history = self._price_history.get(symbol, [])
        if not history or pattern_price <= 0:
            return []

        moves = []
        for interval_min in SUBSEQUENT_INTERVALS:
            target_ts = pattern_timestamp + interval_min * 60

            # Binary search for closest timestamp >= target_ts
            best_price = None
            best_diff = float("inf")
            for ts, price in history:
                if ts >= target_ts:
                    diff = ts - target_ts
                    if diff < best_diff:
                        best_diff = diff
                        best_price = price
                    if diff > 300:  # stop if we're >5min past target
                        break

            if best_price is not None and best_diff < interval_min * 60:
                pct = ((best_price - pattern_price) / pattern_price) * 100
                moves.append(SubsequentMove(
                    interval_minutes=interval_min,
                    price_at_pattern=pattern_price,
                    price_after=best_price,
                    pct_change=round(pct, 4),
                ))

        return moves

    def get_stats(self) -> dict[str, Any]:
        """Return store statistics."""
        valid_count = self.count
        return {
            "total_capacity": self.max_vectors,
            "stored_vectors": valid_count,
            "utilization": valid_count / self.max_vectors,
            "memory_codes_mb": self._codes.nbytes / 1e6,
            "memory_cache_mb": self._decoded_cache.nbytes / 1e6,
            "price_history_entries": sum(len(v) for v in self._price_history.values()),
        }
