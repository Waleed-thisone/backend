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


async def _handle_bot_type(pct_change: float, bot_type: str, alert_active: bool) -> None:
    settings = database.get_settings_for_type(bot_type)
    bots = [bot for bot in database.get_all_bots() if bot["bot_type"] == bot_type]
    abs_change = abs(pct_change)
    stop_threshold = settings["stop_threshold_pct"]
    restart_threshold = settings["restart_threshold_pct"]
    bots_stopped_for_alert = settings.get("bots_stopped_for_alert", False)

    if abs_change > stop_threshold:
        stopped_any = False
        for bot in bots:
            if bot["status"] != "active":
                continue
            success = await bybit_client.stop_bot(bot["id"], bot["bot_type"])
            if success:
                database.upsert_bot({**bot, "status": "stopped"})
                stopped_any = True
        if stopped_any:
            database.set_bots_stopped_for_alert(bot_type, True)
        return

    if alert_active and bots_stopped_for_alert and abs_change < restart_threshold:
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

        database.set_bots_stopped_for_alert(bot_type, False)


async def check_and_act(pct_change: float) -> None:
    if not bybit_client.is_configured():
        return

    state = storage.load()
    alert_active = bool(state and state.get("alert"))

    for bot_type in bybit_client.BOT_TYPES:
        try:
            await _handle_bot_type(pct_change, bot_type, alert_active)
        except Exception:
            logger.exception("Stop/restart check failed for %s bots", bot_type)
