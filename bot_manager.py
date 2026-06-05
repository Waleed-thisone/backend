import logging

import bybit_client
import database
import storage

logger = logging.getLogger(__name__)


async def sync_watchlist_bots() -> None:
    if not bybit_client.is_configured():
        return

    for bot in database.get_all_bots():
        try:
            details = await bybit_client.get_bot_details(bot["id"], bot["bot_type"])
            database.upsert_bot(details)
        except Exception:
            logger.exception("Failed to sync %s bot %s from Bybit", bot.get("bot_type"), bot["id"])


async def sync_account_balance() -> None:
    if not bybit_client.is_configured():
        return

    try:
        balance = await bybit_client.get_account_balance()
        database.save_balance_snapshot(balance)
    except Exception:
        logger.exception("Failed to sync account balance from Bybit")


async def _stop_active_bots(bots: list, bot_type: str) -> bool:
    stopped_any = False
    for bot in bots:
        if bot["status"] != "active":
            continue
        success = await bybit_client.stop_bot(bot["id"], bot["bot_type"])
        if success:
            database.upsert_bot({**bot, "status": "stopped"})
            stopped_any = True
    return stopped_any


async def _restart_stopped_bots(bots: list, bot_type: str) -> None:
    for bot in bots:
        if bot["status"] != "stopped":
            continue
        new_bot_id = await bybit_client.restart_bot(bot)
        if not new_bot_id:
            continue

        restarted_bot = await bybit_client.get_bot_details(new_bot_id, bot["bot_type"])
        if new_bot_id != bot["id"]:
            database.replace_bot_id(bot["id"], new_bot_id, restarted_bot)
        else:
            database.upsert_bot(restarted_bot)


async def _handle_spot_grid(pct_change: float, alert_active: bool) -> None:
    """Stop on high volatility; restart when market calms after an alert."""
    settings = database.get_settings_for_type("spot_grid")
    bots = [bot for bot in database.get_all_bots() if bot["bot_type"] == "spot_grid"]
    abs_change = abs(pct_change)
    stop_threshold = settings["stop_threshold_pct"]
    restart_threshold = settings["restart_threshold_pct"]
    bots_stopped = settings.get("bots_stopped_for_alert", False)

    if abs_change > stop_threshold:
        if await _stop_active_bots(bots, "spot_grid"):
            database.set_bots_stopped_for_alert("spot_grid", True)
        return

    if alert_active and bots_stopped and abs_change < restart_threshold:
        await _restart_stopped_bots(bots, "spot_grid")
        database.set_bots_stopped_for_alert("spot_grid", False)


async def _handle_futures_grid(pct_change: float) -> None:
    """Stop in low volatility (sideways chop); restart when trend is strong."""
    settings = database.get_settings_for_type("futures_grid")
    bots = [bot for bot in database.get_all_bots() if bot["bot_type"] == "futures_grid"]
    abs_change = abs(pct_change)
    stop_below_pct = settings["stop_threshold_pct"]
    start_above_pct = settings["restart_threshold_pct"]
    bots_stopped = settings.get("bots_stopped_for_alert", False)

    if abs_change < stop_below_pct:
        if await _stop_active_bots(bots, "futures_grid"):
            database.set_bots_stopped_for_alert("futures_grid", True)
        return

    if abs_change > start_above_pct and bots_stopped:
        await _restart_stopped_bots(bots, "futures_grid")
        database.set_bots_stopped_for_alert("futures_grid", False)


async def check_and_act(pct_change: float) -> None:
    if not bybit_client.is_configured():
        return

    state = storage.load()
    alert_active = bool(state and state.get("alert"))

    try:
        await _handle_spot_grid(pct_change, alert_active)
    except Exception:
        logger.exception("Stop/restart check failed for spot_grid bots")

    try:
        await _handle_futures_grid(pct_change)
    except Exception:
        logger.exception("Stop/restart check failed for futures_grid bots")
