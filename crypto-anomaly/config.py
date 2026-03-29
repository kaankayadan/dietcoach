from dataclasses import dataclass, field


@dataclass
class Config:
    # Symbols (lowercase for Binance stream names)
    symbols: list[str] = field(default_factory=lambda: [
        "btcusdt", "ethusdt", "solusdt", "adausdt",
        "xrpusdt", "dotusdt", "avaxusdt", "maticusdt",
        "linkusdt", "atomusdt", "uniusdt", "ltcusdt",
    ])
    kline_interval: str = "1m"

    # Feature extraction
    window_size: int = 60
    feature_dim: int = 128
    rolling_windows: list[int] = field(default_factory=lambda: [5, 10, 20])

    # TurboQuant
    bit_width: int = 2

    # Vector store
    max_vectors: int = 100_000
    sliding_window_hours: int = 24

    # Anomaly detection
    k_neighbors: int = 10
    sigma_threshold: float = 2.0
    min_history: int = 100

    # Dashboard
    host: str = "0.0.0.0"
    port: int = 8765

    # Binance
    ws_base_url: str = "wss://stream.binance.com:9443"
    rest_base_url: str = "https://api.binance.com"
