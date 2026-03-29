from __future__ import annotations

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
from vector_store import VectorStore, SUBSEQUENT_INTERVALS

logger = logging.getLogger(__name__)

# ANSI color codes for console output
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


@dataclass
class SubsequentMoveInfo:
    """Price movement after a pattern, for display."""
    interval_minutes: int
    price_at_pattern: float
    price_after: float
    pct_change: float


@dataclass
class TrendSummary:
    """Aggregated trend analysis from similar patterns' subsequent moves."""
    interval_minutes: int
    num_patterns: int  # how many patterns had data for this interval
    num_bullish: int  # positive moves
    num_bearish: int  # negative moves
    avg_pct_change: float
    median_pct_change: float
    bullish_pct: float  # percentage of bullish outcomes
    direction: str  # "BULLISH", "BEARISH", "NEUTRAL"


@dataclass
class SimilarPattern:
    """A historical pattern similar to the current one."""
    timestamp: float
    symbol: str
    price: float
    similarity: float  # inner product score
    subsequent_moves: list[SubsequentMoveInfo] = field(default_factory=list)


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
    trend_summaries: list[TrendSummary] = field(default_factory=list)

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
                    "subsequent_moves": [
                        {
                            "interval_minutes": m.interval_minutes,
                            "price_at_pattern": m.price_at_pattern,
                            "price_after": m.price_after,
                            "pct_change": m.pct_change,
                        }
                        for m in p.subsequent_moves
                    ],
                }
                for p in self.similar_patterns
            ],
            "trend_summaries": [
                {
                    "interval_minutes": t.interval_minutes,
                    "num_patterns": t.num_patterns,
                    "num_bullish": t.num_bullish,
                    "num_bearish": t.num_bearish,
                    "avg_pct_change": round(t.avg_pct_change, 4),
                    "median_pct_change": round(t.median_pct_change, 4),
                    "bullish_pct": round(t.bullish_pct, 1),
                    "direction": t.direction,
                }
                for t in self.trend_summaries
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

        # Build similar patterns list with subsequent moves
        similar_patterns = []
        for r in results:
            sub_moves = [
                SubsequentMoveInfo(
                    interval_minutes=m.interval_minutes,
                    price_at_pattern=m.price_at_pattern,
                    price_after=m.price_after,
                    pct_change=m.pct_change,
                )
                for m in r.subsequent_moves
            ]
            similar_patterns.append(SimilarPattern(
                timestamp=r.metadata.get("timestamp", 0),
                symbol=r.metadata.get("symbol", ""),
                price=r.metadata.get("price", 0),
                similarity=r.score,
                subsequent_moves=sub_moves,
            ))

        # Build trend summaries per interval
        trend_summaries = self._compute_trend_summaries(similar_patterns)

        result = AnomalyResult(
            symbol=symbol,
            timestamp=timestamp,
            price=price,
            anomaly_score=avg_distance,
            sigma_level=sigma_level,
            threshold=self.config.sigma_threshold,
            alert_level=alert_level,
            similar_patterns=similar_patterns,
            trend_summaries=trend_summaries,
        )

        # Console logging for anomalies
        if alert_level != "normal":
            self._log_anomaly(result)

        return result

    @staticmethod
    def _compute_trend_summaries(patterns: list[SimilarPattern]) -> list[TrendSummary]:
        """Aggregate subsequent moves across all similar patterns."""
        summaries = []

        for interval in SUBSEQUENT_INTERVALS:
            changes = []
            for p in patterns:
                for m in p.subsequent_moves:
                    if m.interval_minutes == interval:
                        changes.append(m.pct_change)

            if not changes:
                continue

            arr = np.array(changes)
            num_bullish = int(np.sum(arr > 0))
            num_bearish = int(np.sum(arr < 0))
            total = len(changes)
            bullish_pct = (num_bullish / total) * 100 if total > 0 else 50.0

            if bullish_pct >= 65:
                direction = "BULLISH"
            elif bullish_pct <= 35:
                direction = "BEARISH"
            else:
                direction = "NEUTRAL"

            summaries.append(TrendSummary(
                interval_minutes=interval,
                num_patterns=total,
                num_bullish=num_bullish,
                num_bearish=num_bearish,
                avg_pct_change=float(np.mean(arr)),
                median_pct_change=float(np.median(arr)),
                bullish_pct=bullish_pct,
                direction=direction,
            ))

        return summaries

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
                moves_str = ""
                if p.subsequent_moves:
                    moves_str = " → " + ", ".join(
                        f"{m.interval_minutes}m:{m.pct_change:+.2f}%"
                        for m in p.subsequent_moves
                    )
                print(
                    f"{CYAN}    {i+1}. {p.symbol.upper()} @ ${p.price:,.2f} "
                    f"({t}) sim={p.similarity:.4f}{moves_str}{RESET}"
                )

        if result.trend_summaries:
            print(f"{BOLD}  Trend Analysis (from similar patterns):{RESET}")
            for t in result.trend_summaries:
                dir_color = GREEN if t.direction == "BULLISH" else (RED if t.direction == "BEARISH" else YELLOW)
                print(
                    f"  {dir_color}  {t.interval_minutes}m: {t.direction} "
                    f"({t.num_bullish}/{t.num_patterns} bullish = {t.bullish_pct:.0f}%) "
                    f"avg={t.avg_pct_change:+.3f}% med={t.median_pct_change:+.3f}%{RESET}"
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
