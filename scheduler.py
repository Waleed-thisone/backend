import logging
import os
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import binance_client
import binance_client_1h
import bot_manager
import storage

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

INTERVAL_MINUTES = int(os.getenv("PRICE_CHECK_INTERVAL_MINUTES", "5"))
ALERT_THRESHOLD_PCT = float(os.getenv("ALERT_THRESHOLD_PCT", "3.0"))


def _pct_change(price_now: float, price_before: float) -> float:
    return ((price_now - price_before) / price_before) * 100


async def update_price_state() -> None:
    pct_change_12h = None
    pct_change_1h = None
    state = storage.load() or {}

    try:
        price_now, price_12h_ago = await binance_client.get_prices()
        pct_change_12h = round(_pct_change(price_now, price_12h_ago), 2)
        state.update(
            {
                "current_price": price_now,
                "price_12h_ago": price_12h_ago,
                "pct_change": pct_change_12h,
                "direction": "UP" if pct_change_12h >= 0 else "DOWN",
                "alert": abs(pct_change_12h) > ALERT_THRESHOLD_PCT,
            }
        )
    except Exception:
        logger.exception("Scheduled Binance 12h price update failed")
        return

    try:
        price_now_1h, price_1h_ago = await binance_client_1h.get_prices()
        pct_change_1h = round(_pct_change(price_now_1h, price_1h_ago), 2)
        state.update(
            {
                "price_1h_ago": price_1h_ago,
                "pct_change_1h": pct_change_1h,
                "direction_1h": "UP" if pct_change_1h >= 0 else "DOWN",
            }
        )
    except Exception:
        logger.exception("Scheduled Binance 1h price update failed")
        pct_change_1h = None
        for key in ("price_1h_ago", "pct_change_1h", "direction_1h"):
            state.pop(key, None)

    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    storage.save(state)

    try:
        await bot_manager.sync_watchlist_bots()
    except Exception:
        logger.exception("Scheduled bot sync failed")

    try:
        await bot_manager.sync_account_balance()
    except Exception:
        logger.exception("Scheduled balance sync failed")

    try:
        await bot_manager.check_and_act(
            pct_change_12h=pct_change_12h,
            pct_change_1h=pct_change_1h,
        )
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
