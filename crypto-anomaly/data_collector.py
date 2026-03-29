from __future__ import annotations

"""
Binance WebSocket data collector for real-time kline (candlestick) data.

Uses public endpoints — no API key required.
- Combined stream WebSocket for all symbols on a single connection
- REST API bootstrap to pre-fill candle buffers (avoids cold start)
- Auto-reconnect with exponential backoff
"""

import asyncio
import json
import logging
import time
from collections import deque
from typing import Any, Callable, Coroutine

import aiohttp
import websockets

from config import Config

logger = logging.getLogger(__name__)


class Candle:
    """Lightweight candle (OHLCV) representation."""
    __slots__ = ("timestamp", "open", "high", "low", "close", "volume", "trades", "symbol")

    def __init__(self, timestamp: float, open_: float, high: float, low: float,
                 close: float, volume: float, trades: int, symbol: str):
        self.timestamp = timestamp
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.trades = trades
        self.symbol = symbol

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "trades": self.trades,
            "symbol": self.symbol,
        }


# Type for the candle-close callback
CandleCallback = Callable[[str, list[Candle]], Coroutine[Any, Any, None]]


class BinanceCollector:
    """Collects real-time kline data from Binance WebSocket streams."""

    def __init__(self, config: Config, on_candle_close: CandleCallback,
                 stop_event: asyncio.Event | None = None):
        self.config = config
        self.on_candle_close = on_candle_close
        self.stop_event = stop_event or asyncio.Event()

        # Per-symbol candle buffers
        self._buffers: dict[str, deque[Candle]] = {
            s: deque(maxlen=config.window_size)
            for s in config.symbols
        }

        # Build combined stream URL
        streams = "/".join(f"{s}@kline_{config.kline_interval}" for s in config.symbols)
        self._ws_url = f"{config.ws_base_url}/stream?streams={streams}"

    async def bootstrap(self) -> None:
        """Pre-fill candle buffers via Binance REST API."""
        logger.info("Bootstrapping candle buffers via REST API...")
        async with aiohttp.ClientSession() as session:
            tasks = [self._fetch_historical(session, symbol) for symbol in self.config.symbols]
            await asyncio.gather(*tasks, return_exceptions=True)

        filled = {s: len(b) for s, b in self._buffers.items()}
        logger.info(f"Bootstrap complete: {filled}")

    async def _fetch_historical(self, session: aiohttp.ClientSession, symbol: str) -> None:
        """Fetch historical klines for one symbol."""
        url = f"{self.config.rest_base_url}/api/v3/klines"
        params = {
            "symbol": symbol.upper(),
            "interval": self.config.kline_interval,
            "limit": self.config.window_size,
        }
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning(f"REST API error for {symbol}: {resp.status}")
                    return
                data = await resp.json()

            for k in data:
                candle = Candle(
                    timestamp=k[0] / 1000.0,
                    open_=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5]),
                    trades=int(k[8]),
                    symbol=symbol,
                )
                self._buffers[symbol].append(candle)

            logger.info(f"  {symbol}: {len(self._buffers[symbol])} candles loaded")
        except Exception as e:
            logger.warning(f"Failed to bootstrap {symbol}: {e}")

    async def run(self) -> None:
        """Main WebSocket loop with auto-reconnect."""
        backoff = 1.0
        max_backoff = 30.0

        while not self.stop_event.is_set():
            try:
                logger.info(f"Connecting to Binance WebSocket...")
                async with websockets.connect(self._ws_url, ping_interval=20, ping_timeout=10) as ws:
                    logger.info(f"Connected. Listening to {len(self.config.symbols)} symbols.")
                    backoff = 1.0  # Reset backoff on successful connection

                    while not self.stop_event.is_set():
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=30)
                        except asyncio.TimeoutError:
                            continue

                        await self._handle_message(raw)

            except (websockets.ConnectionClosed, ConnectionError, OSError) as e:
                if self.stop_event.is_set():
                    break
                logger.warning(f"WebSocket disconnected: {e}. Reconnecting in {backoff:.0f}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
            except Exception as e:
                if self.stop_event.is_set():
                    break
                logger.error(f"Unexpected error: {e}. Reconnecting in {backoff:.0f}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

        logger.info("Data collector stopped.")

    async def _handle_message(self, raw: str) -> None:
        """Parse a WebSocket message and process closed candles."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        # Combined stream format: {"stream": "...", "data": {...}}
        data = msg.get("data", msg)
        if "k" not in data:
            return

        k = data["k"]
        symbol = k["s"].lower()
        is_closed = k["x"]

        if not is_closed:
            return

        if symbol not in self._buffers:
            return

        candle = Candle(
            timestamp=k["t"] / 1000.0,
            open_=float(k["o"]),
            high=float(k["h"]),
            low=float(k["l"]),
            close=float(k["c"]),
            volume=float(k["v"]),
            trades=int(k["n"]),
            symbol=symbol,
        )

        self._buffers[symbol].append(candle)

        # Only trigger callback when we have enough candles
        if len(self._buffers[symbol]) >= self.config.window_size:
            candles = list(self._buffers[symbol])
            try:
                await self.on_candle_close(symbol, candles)
            except Exception as e:
                logger.error(f"Callback error for {symbol}: {e}")

    def get_buffer(self, symbol: str) -> list[Candle]:
        """Get current candle buffer for a symbol."""
        return list(self._buffers.get(symbol, []))
