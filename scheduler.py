import logging
import os
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import binance_client
import bot_manager
import storage

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

INTERVAL_MINUTES = int(os.getenv("PRICE_CHECK_INTERVAL_MINUTES", "5"))
ALERT_THRESHOLD_PCT = float(os.getenv("ALERT_THRESHOLD_PCT", "3.0"))


async def update_price_state() -> None:
    pct_change = None

    try:
        price_now, price_12h_ago = await binance_client.get_prices()
        pct_change = ((price_now - price_12h_ago) / price_12h_ago) * 100
        direction = "UP" if pct_change >= 0 else "DOWN"

        storage.save(
            {
                "current_price": price_now,
                "price_12h_ago": price_12h_ago,
                "pct_change": round(pct_change, 2),
                "direction": direction,
                "alert": abs(pct_change) > ALERT_THRESHOLD_PCT,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception:
        logger.exception("Scheduled Binance price update failed")
        return

    try:
        await bot_manager.sync_watchlist_bots()
    except Exception:
        logger.exception("Scheduled bot sync failed")

    try:
        await bot_manager.sync_account_balance()
    except Exception:
        logger.exception("Scheduled balance sync failed")

    if pct_change is not None:
        try:
            await bot_manager.check_and_act(pct_change)
        except Exception:
            logger.exception("Scheduled bot stop/restart check failed")


def start_scheduler() -> None:
    scheduler.add_job(
        update_price_state,
        "interval",
        minutes=INTERVAL_MINUTES,
        id="price_check",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
