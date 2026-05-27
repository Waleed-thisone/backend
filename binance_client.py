import logging
from typing import Tuple

import httpx

logger = logging.getLogger(__name__)

BINANCE_KLINES_URL = "https://api.binance.us/api/v3/klines"


async def get_prices() -> Tuple[float, float]:
    params = {
        "symbol": "BTCUSDT",
        "interval": "1m",
        "limit": 720,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(BINANCE_KLINES_URL, params=params)
            response.raise_for_status()
            klines = response.json()

        price_now = float(klines[-1][4])
        price_12h_ago = float(klines[0][4])
        return price_now, price_12h_ago
    except httpx.HTTPError as exc:
        logger.exception("Binance API request failed")
        raise RuntimeError(f"Binance API request failed: {exc}") from exc
    except (IndexError, ValueError, KeyError, TypeError) as exc:
        logger.exception("Failed to parse Binance response")
        raise RuntimeError(f"Invalid Binance response: {exc}") from exc
