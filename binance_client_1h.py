import logging
from typing import Tuple

import httpx

logger = logging.getLogger(__name__)

BINANCE_KLINES_URL = "https://api.binance.us/api/v3/klines"


async def get_prices() -> Tuple[float, float]:
    """Return (current_price, price_1h_ago) using 1-hour candles."""
    params = {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "limit": 2,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(BINANCE_KLINES_URL, params=params)
            response.raise_for_status()
            klines = response.json()

        if len(klines) < 2:
            raise RuntimeError("Binance returned fewer than 2 hourly klines")

        price_now = float(klines[-1][4])
        price_1h_ago = float(klines[0][4])
        return price_now, price_1h_ago
    except httpx.HTTPError as exc:
        logger.exception("Binance 1h API request failed")
        raise RuntimeError(f"Binance 1h API request failed: {exc}") from exc
    except (IndexError, ValueError, KeyError, TypeError) as exc:
        logger.exception("Failed to parse Binance 1h response")
        raise RuntimeError(f"Invalid Binance 1h response: {exc}") from exc
