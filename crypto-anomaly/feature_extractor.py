"""
Feature extraction: converts a window of candles into a d=128
unit-norm vector suitable for TurboQuant quantization.

Pure NumPy implementation — no external TA libraries.

Feature composition (128 dimensions):
  Log returns (20) + Volume profile (20) + Rolling std w=5 (15) +
  Rolling std w=10 (15) + Rolling std w=20 (10) + RSI(14) (14) +
  MACD-like (10) + Price range (10) + Trade intensity (10) +
  Candle body ratio (4) = 128
"""

import numpy as np

from config import Config


class FeatureExtractor:
    """Extracts fixed-size feature vectors from candle sequences."""

    def __init__(self, config: Config):
        self.config = config
        self.feature_dim = config.feature_dim  # 128

    def extract(self, candles: list) -> np.ndarray | None:
        """Extract a d=128 unit-norm feature vector from candle data.

        Args:
            candles: List of Candle objects (at least window_size items).

        Returns:
            Shape (128,) unit-norm vector, or None if data is degenerate.
        """
        n = len(candles)
        if n < 2:
            return None

        # Extract raw arrays
        closes = np.array([c.close for c in candles], dtype=np.float64)
        highs = np.array([c.high for c in candles], dtype=np.float64)
        lows = np.array([c.low for c in candles], dtype=np.float64)
        opens = np.array([c.open for c in candles], dtype=np.float64)
        volumes = np.array([c.volume for c in candles], dtype=np.float64)
        trades = np.array([c.trades for c in candles], dtype=np.float64)

        features = []

        # 1. Log returns (last 20) — 20 dims
        log_returns = np.diff(np.log(np.maximum(closes, 1e-10)))
        features.append(self._take_last(log_returns, 20))

        # 2. Normalized volume profile (last 20) — 20 dims
        vol_mean = np.mean(volumes) + 1e-10
        norm_vol = volumes / vol_mean
        features.append(self._take_last(norm_vol, 20))

        # 3. Rolling std w=5 of returns (last 15) — 15 dims
        features.append(self._take_last(self._rolling_std(log_returns, 5), 15))

        # 4. Rolling std w=10 of returns (last 15) — 15 dims
        features.append(self._take_last(self._rolling_std(log_returns, 10), 15))

        # 5. Rolling std w=20 of returns (last 10) — 10 dims
        features.append(self._take_last(self._rolling_std(log_returns, 20), 10))

        # 6. RSI(14) rescaled to [-1, 1] (last 14) — 14 dims
        rsi = self._rsi(closes, 14)
        rsi_scaled = (rsi - 50.0) / 50.0  # Map [0,100] → [-1,1]
        features.append(self._take_last(rsi_scaled, 14))

        # 7. MACD-like: EMA(12) - EMA(26) normalized (last 10) — 10 dims
        macd = self._macd(closes)
        features.append(self._take_last(macd, 10))

        # 8. Price range (high-low)/close (last 10) — 10 dims
        price_range = (highs - lows) / np.maximum(closes, 1e-10)
        features.append(self._take_last(price_range, 10))

        # 9. Normalized trade count (last 10) — 10 dims
        trade_mean = np.mean(trades) + 1e-10
        norm_trades = trades / trade_mean
        features.append(self._take_last(norm_trades, 10))

        # 10. Candle body ratio (close-open)/(high-low) (last 4) — 4 dims
        hl_range = highs - lows
        body = closes - opens
        body_ratio = np.where(hl_range > 1e-10, body / hl_range, 0.0)
        features.append(self._take_last(body_ratio, 4))

        # Concatenate all features
        vector = np.concatenate(features)

        # Ensure exactly feature_dim dimensions
        if len(vector) < self.feature_dim:
            vector = np.pad(vector, (0, self.feature_dim - len(vector)))
        elif len(vector) > self.feature_dim:
            vector = vector[:self.feature_dim]

        # Replace any NaN/inf with 0
        vector = np.nan_to_num(vector, nan=0.0, posinf=0.0, neginf=0.0)

        # L2 normalize to unit norm
        norm = np.linalg.norm(vector)
        if norm < 1e-10:
            return None
        vector /= norm

        return vector

    @staticmethod
    def _take_last(arr: np.ndarray, n: int) -> np.ndarray:
        """Take last n elements, zero-pad if shorter."""
        if len(arr) >= n:
            return arr[-n:]
        result = np.zeros(n)
        result[n - len(arr):] = arr
        return result

    @staticmethod
    def _rolling_std(arr: np.ndarray, window: int) -> np.ndarray:
        """Rolling standard deviation using cumulative sums."""
        if len(arr) < window:
            return np.zeros(1)

        n = len(arr)
        result = np.empty(n - window + 1)
        for i in range(n - window + 1):
            result[i] = np.std(arr[i:i + window])
        return result

    @staticmethod
    def _rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
        """Relative Strength Index using exponential moving average."""
        if len(closes) < period + 1:
            return np.full(1, 50.0)

        deltas = np.diff(closes)
        gains = np.maximum(deltas, 0)
        losses = np.maximum(-deltas, 0)

        # EMA-based RSI
        alpha = 1.0 / period
        avg_gain = np.empty(len(deltas))
        avg_loss = np.empty(len(deltas))

        avg_gain[0] = np.mean(gains[:period])
        avg_loss[0] = np.mean(losses[:period])

        for i in range(1, len(deltas)):
            avg_gain[i] = avg_gain[i - 1] * (1 - alpha) + gains[i] * alpha
            avg_loss[i] = avg_loss[i - 1] * (1 - alpha) + losses[i] * alpha

        rs = avg_gain / np.maximum(avg_loss, 1e-10)
        rsi = 100.0 - 100.0 / (1.0 + rs)
        return rsi

    @staticmethod
    def _macd(closes: np.ndarray, fast: int = 12, slow: int = 26) -> np.ndarray:
        """MACD-like indicator: EMA(fast) - EMA(slow), normalized by price."""
        if len(closes) < slow:
            return np.zeros(1)

        def ema(data, period):
            alpha = 2.0 / (period + 1)
            result = np.empty_like(data)
            result[0] = data[0]
            for i in range(1, len(data)):
                result[i] = result[i - 1] * (1 - alpha) + data[i] * alpha
            return result

        ema_fast = ema(closes, fast)
        ema_slow = ema(closes, slow)
        macd_line = (ema_fast - ema_slow) / np.maximum(closes, 1e-10)
        return macd_line
