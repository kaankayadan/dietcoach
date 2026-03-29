"""
Anomaly detection engine.

For each new feature vector:
1. Search nearest neighbors in the vector store
2. Compute average distance to top-K neighbors
3. Compare against historical distribution (mean ± σ)
4. If distance > mean + threshold*σ → anomaly
5. Report similar historical patterns and their subsequent price moves
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from config import Config
from vector_store import VectorStore

logger = logging.getLogger(__name__)

# ANSI color codes for console output
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


@dataclass
class SimilarPattern:
    """A historical pattern similar to the current one."""
    timestamp: float
    symbol: str
    price: float
    similarity: float  # inner product score


@dataclass
class AnomalyResult:
    """Result of anomaly detection for a single vector."""
    symbol: str
    timestamp: float
    price: float
    anomaly_score: float  # average distance to K neighbors
    sigma_level: float  # how many σ above mean
    threshold: float  # the σ threshold used
    alert_level: str  # "normal", "warning", "critical"
    similar_patterns: list[SimilarPattern] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "price": self.price,
            "anomaly_score": self.anomaly_score,
            "sigma_level": round(self.sigma_level, 2),
            "threshold": self.threshold,
            "alert_level": self.alert_level,
            "similar_patterns": [
                {
                    "timestamp": p.timestamp,
                    "symbol": p.symbol,
                    "price": p.price,
                    "similarity": round(p.similarity, 4),
                }
                for p in self.similar_patterns
            ],
        }


class AnomalyDetector:
    """Detects anomalies by comparing new vectors to historical patterns."""

    def __init__(self, config: Config, vector_store: VectorStore):
        self.config = config
        self.vector_store = vector_store

        # Rolling history of average distances (per symbol)
        self._distance_history: dict[str, deque[float]] = {}
        self._max_history = 1000  # keep last 1000 scores per symbol

        # Global distance history (across all symbols)
        self._global_history: deque[float] = deque(maxlen=5000)

    def detect(self, query_vector: np.ndarray, metadata: dict[str, Any]) -> AnomalyResult | None:
        """Run anomaly detection on a new feature vector.

        Args:
            query_vector: Shape (d,) unit-norm vector.
            metadata: Dict with symbol, price, volume, timestamp.

        Returns:
            AnomalyResult if detection ran (may or may not be anomalous),
            None if insufficient history.
        """
        symbol = metadata.get("symbol", "unknown")
        price = metadata.get("price", 0.0)
        timestamp = metadata.get("timestamp", time.time())

        # Check if we have enough history
        if self.vector_store.count < self.config.min_history:
            return None

        # Search nearest neighbors
        results = self.vector_store.search(
            query_vector,
            top_k=self.config.k_neighbors,
            exclude_recent=5,
        )

        if not results:
            return None

        # Average distance to K neighbors
        avg_distance = float(np.mean([r.distance for r in results]))

        # Update history
        if symbol not in self._distance_history:
            self._distance_history[symbol] = deque(maxlen=self._max_history)
        self._distance_history[symbol].append(avg_distance)
        self._global_history.append(avg_distance)

        # Compute sigma level
        history = list(self._global_history)
        if len(history) < 20:
            # Not enough history for reliable statistics
            return None

        hist_mean = float(np.mean(history))
        hist_std = float(np.std(history))

        if hist_std < 1e-10:
            sigma_level = 0.0
        else:
            sigma_level = (avg_distance - hist_mean) / hist_std

        # Determine alert level
        if sigma_level > self.config.sigma_threshold * 1.5:
            alert_level = "critical"
        elif sigma_level > self.config.sigma_threshold:
            alert_level = "warning"
        else:
            alert_level = "normal"

        # Build similar patterns list
        similar_patterns = [
            SimilarPattern(
                timestamp=r.metadata.get("timestamp", 0),
                symbol=r.metadata.get("symbol", ""),
                price=r.metadata.get("price", 0),
                similarity=r.score,
            )
            for r in results
        ]

        result = AnomalyResult(
            symbol=symbol,
            timestamp=timestamp,
            price=price,
            anomaly_score=avg_distance,
            sigma_level=sigma_level,
            threshold=self.config.sigma_threshold,
            alert_level=alert_level,
            similar_patterns=similar_patterns,
        )

        # Console logging for anomalies
        if alert_level != "normal":
            self._log_anomaly(result)

        return result

    def _log_anomaly(self, result: AnomalyResult) -> None:
        """Print colored anomaly alert to console."""
        color = RED if result.alert_level == "critical" else YELLOW
        level_tag = "CRITICAL" if result.alert_level == "critical" else "WARNING"

        print(
            f"\n{color}{BOLD}[{level_tag}] ANOMALY DETECTED{RESET}"
            f"\n{color}  Symbol:  {result.symbol.upper()}{RESET}"
            f"\n{color}  Price:   ${result.price:,.2f}{RESET}"
            f"\n{color}  Score:   {result.anomaly_score:.4f} "
            f"({result.sigma_level:.1f}σ above mean){RESET}"
            f"\n{color}  Time:    {time.strftime('%H:%M:%S', time.localtime(result.timestamp))}{RESET}"
        )

        if result.similar_patterns:
            print(f"{CYAN}  Similar patterns:{RESET}")
            for i, p in enumerate(result.similar_patterns[:3]):
                t = time.strftime("%Y-%m-%d %H:%M", time.localtime(p.timestamp))
                print(
                    f"{CYAN}    {i+1}. {p.symbol.upper()} @ ${p.price:,.2f} "
                    f"({t}) sim={p.similarity:.4f}{RESET}"
                )
        print()

    def get_stats(self) -> dict[str, Any]:
        """Return detector statistics."""
        stats = {
            "total_detections": len(self._global_history),
            "per_symbol": {},
        }
        for symbol, history in self._distance_history.items():
            h = list(history)
            stats["per_symbol"][symbol] = {
                "count": len(h),
                "mean_distance": float(np.mean(h)) if h else 0,
                "std_distance": float(np.std(h)) if h else 0,
            }
        return stats
