#!/usr/bin/env python3
"""
Crypto Market Anomaly Detection System — Orchestrator

Ties all components together:
1. TurboQuant quantizer (d=128, b=2)
2. VectorStore (in-memory, 100K capacity)
3. Binance WebSocket data collector (with REST bootstrap)
4. Feature extractor (128-dim unit-norm vectors)
5. Anomaly detector (KNN distance-based)
6. FastAPI + WebSocket dashboard

Usage: python main.py
"""

import asyncio
import logging
import signal
import sys
import time

import uvicorn

from config import Config
from turboquant import TurboQuantMSE
from data_collector import BinanceCollector
from feature_extractor import FeatureExtractor
from vector_store import VectorStore
from anomaly_detector import AnomalyDetector
from dashboard import app, broadcast, set_stats_callback

# ─────────────────────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# ─────────────────────────────────────────────────────────────
# ANSI colors
# ─────────────────────────────────────────────────────────────

GREEN = "\033[92m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_banner():
    print(f"""
{CYAN}{BOLD}╔══════════════════════════════════════════════════╗
║       Crypto Anomaly Detection System            ║
║       TurboQuant-powered Vector Analysis         ║
╚══════════════════════════════════════════════════╝{RESET}
""")


# ─────────────────────────────────────────────────────────────
# Main application
# ─────────────────────────────────────────────────────────────

class Application:
    def __init__(self):
        self.config = Config()
        self.stop_event = asyncio.Event()
        self.start_time = time.time()
        self.candle_count = 0

        # Initialize components
        logger.info("Initializing TurboQuant (d=%d, b=%d)...", self.config.feature_dim, self.config.bit_width)
        self.quantizer = TurboQuantMSE(
            d=self.config.feature_dim,
            b=self.config.bit_width,
            seed=42,
        )

        logger.info("Initializing VectorStore (max=%d)...", self.config.max_vectors)
        self.vector_store = VectorStore(
            quantizer=self.quantizer,
            max_vectors=self.config.max_vectors,
        )

        self.feature_extractor = FeatureExtractor(self.config)
        self.anomaly_detector = AnomalyDetector(self.config, self.vector_store)

        # Data collector (initialized in run())
        self.collector = None

        # Dashboard stats callback
        set_stats_callback(self._get_stats)

    async def on_candle_close(self, symbol: str, candles: list) -> None:
        """Pipeline: extract → quantize → store → detect → broadcast."""
        t0 = time.perf_counter()

        # 1. Feature extraction
        vector = self.feature_extractor.extract(candles)
        if vector is None:
            return

        # 2. Record price for subsequent move tracking
        last_candle = candles[-1]
        self.vector_store.record_price(symbol, last_candle.timestamp, last_candle.close)

        # 3. Store (quantize internally)
        metadata = {
            "symbol": symbol,
            "price": last_candle.close,
            "volume": last_candle.volume,
            "timestamp": last_candle.timestamp,
        }
        self.vector_store.add(vector, metadata)
        self.candle_count += 1

        # 4. Detect anomaly
        result = self.anomaly_detector.detect(vector, metadata)

        # 5. Broadcast candle to dashboard
        await broadcast({
            "type": "candle",
            "symbol": symbol,
            "price": last_candle.close,
            "volume": last_candle.volume,
        })

        # 6. Broadcast anomaly if detected
        if result and result.alert_level != "normal":
            await broadcast({
                "type": "anomaly",
                **result.to_dict(),
            })

        # 7. Periodic status broadcast
        if self.candle_count % 10 == 0:
            await broadcast({
                "type": "status",
                "vector_count": self.vector_store.count,
            })

        elapsed_ms = (time.perf_counter() - t0) * 1000
        if self.candle_count % 50 == 0:
            logger.info(
                f"{GREEN}[PIPELINE]{RESET} {symbol.upper()} "
                f"${last_candle.close:,.2f} | "
                f"vectors={self.vector_store.count} | "
                f"pipeline={elapsed_ms:.1f}ms"
            )

    async def periodic_evict(self) -> None:
        """Evict old vectors every 5 minutes."""
        while not self.stop_event.is_set():
            try:
                await asyncio.sleep(300)
            except asyncio.CancelledError:
                break
            max_age = self.config.sliding_window_hours * 3600
            evicted = self.vector_store.evict_old(max_age)
            if evicted > 0:
                logger.info(f"Evicted {evicted} vectors older than {self.config.sliding_window_hours}h")

    async def periodic_status(self) -> None:
        """Log system status every 60 seconds."""
        while not self.stop_event.is_set():
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            stats = self.vector_store.get_stats()
            uptime = time.time() - self.start_time
            logger.info(
                f"Status: vectors={stats['stored_vectors']}, "
                f"candles_processed={self.candle_count}, "
                f"memory={stats['memory_codes_mb'] + stats['memory_cache_mb']:.1f}MB, "
                f"uptime={uptime/60:.0f}m"
            )

    def _get_stats(self) -> dict:
        """Stats callback for dashboard /stats endpoint."""
        return {
            "uptime_seconds": time.time() - self.start_time,
            "candles_processed": self.candle_count,
            "vector_store": self.vector_store.get_stats(),
            "anomaly_detector": self.anomaly_detector.get_stats(),
            "symbols": self.config.symbols,
        }

    async def run(self) -> None:
        """Start all components."""
        print_banner()

        logger.info(f"Symbols: {[s.upper() for s in self.config.symbols]}")
        logger.info(f"TurboQuant: d={self.config.feature_dim}, b={self.config.bit_width}")
        logger.info(f"Dashboard: http://{self.config.host}:{self.config.port}")

        # Setup signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._signal_handler)

        # Initialize collector
        self.collector = BinanceCollector(
            config=self.config,
            on_candle_close=self.on_candle_close,
            stop_event=self.stop_event,
        )

        # Bootstrap candle buffers via REST API
        try:
            await self.collector.bootstrap()
        except Exception as e:
            logger.warning(f"Bootstrap failed (will fill from WebSocket): {e}")

        # Record bootstrapped price history and trigger initial feature extraction
        for symbol in self.config.symbols:
            candles = self.collector.get_buffer(symbol)
            # Record all historical prices for subsequent move analysis
            for c in candles:
                self.vector_store.record_price(symbol, c.timestamp, c.close)
            if len(candles) >= self.config.window_size:
                try:
                    await self.on_candle_close(symbol, candles)
                except Exception as e:
                    logger.warning(f"Initial processing failed for {symbol}: {e}")

        initial_count = self.vector_store.count
        if initial_count > 0:
            logger.info(f"Bootstrapped {initial_count} vectors from historical data")

        # Start uvicorn server
        uvi_config = uvicorn.Config(
            app,
            host=self.config.host,
            port=self.config.port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(uvi_config)

        # Run all tasks concurrently
        logger.info("Starting all services...")
        try:
            await asyncio.gather(
                self.collector.run(),
                server.serve(),
                self.periodic_evict(),
                self.periodic_status(),
            )
        except asyncio.CancelledError:
            pass

        logger.info("Shutdown complete.")

    def _signal_handler(self):
        """Handle SIGINT/SIGTERM for graceful shutdown."""
        if not self.stop_event.is_set():
            logger.info("\nShutting down gracefully...")
            self.stop_event.set()
            # Cancel all tasks
            for task in asyncio.all_tasks():
                if task is not asyncio.current_task():
                    task.cancel()


def main():
    app_instance = Application()
    try:
        asyncio.run(app_instance.run())
    except KeyboardInterrupt:
        print(f"\n{CYAN}Goodbye!{RESET}")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
