import asyncio
import logging
import os
from typing import Any, Dict, List, Literal, Optional

from pybit.exceptions import FailedRequestError, InvalidRequestError
from pybit.unified_trading import HTTP

logger = logging.getLogger(__name__)

BotType = Literal["spot_grid", "futures_grid"]
BOT_TYPES: List[BotType] = ["spot_grid", "futures_grid"]

ACTIVE_STATUSES = {"running", "active", "new"}
STOPPED_STATUSES = {"cancelled", "completed", "cancelling", "stopped", "closed"}

BOT_API: Dict[BotType, Dict[str, Any]] = {
    "spot_grid": {
        "detail": ("GET", "/v5/grid/query-grid-detail", {"botId": "{bot_id}"}),
        "close": ("POST", "/v5/grid/close-grid", {"botId": "{bot_id}"}),
        "create": ("POST", "/v5/grid/create-grid", None),
        "list_category": "UTA_SPOT",
    },
    "futures_grid": {
        "detail": ("GET", "/v5/fgridbot/detail", {"botId": "{bot_id}"}),
        "close": ("POST", "/v5/fgridbot/close", {"botId": "{bot_id}"}),
        "create": ("POST", "/v5/fgridbot/create", None),
        "list_category": "UTA_USDT",
    },
}

_session: Optional[HTTP] = None


def is_configured() -> bool:
    return bool(os.getenv("BYBIT_API_KEY") and os.getenv("BYBIT_API_SECRET"))


def validate_bot_type(bot_type: str) -> BotType:
    if bot_type not in BOT_TYPES:
        raise ValueError(f"bot_type must be one of: {', '.join(BOT_TYPES)}")
    return bot_type  # type: ignore[return-value]


def _get_session() -> HTTP:
    global _session
    if _session is None:
        if not is_configured():
            raise RuntimeError("BYBIT_API_KEY and BYBIT_API_SECRET must be set")
        _session = HTTP(
            testnet=os.getenv("BYBIT_TESTNET", "false").lower() == "true",
            api_key=os.getenv("BYBIT_API_KEY"),
            api_secret=os.getenv("BYBIT_API_SECRET"),
        )
    return _session


def _path(route: str) -> str:
    session = _get_session()
    return f"{session.endpoint}{route}"


def _check_response(response: Dict[str, Any]) -> Dict[str, Any]:
    ret_code = response.get("retCode", response.get("ret_code"))
    if ret_code not in (0, "0", None):
        ret_msg = response.get("retMsg", response.get("ret_msg", "Unknown Bybit error"))
        raise RuntimeError(f"Bybit API error {ret_code}: {ret_msg}")
    return response.get("result") or {}


def _pick_value(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def _to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    return float(value)


def _to_int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    return int(float(value))


def _map_status(raw_status: Any) -> str:
    status = str(raw_status or "unknown").strip().lower()
    if status in ACTIVE_STATUSES:
        return "active"
    if status in STOPPED_STATUSES:
        return "stopped"
    return "unknown"


def _normalize_bot_detail(
    result: Dict[str, Any],
    bot_type: BotType,
    bot_id: Optional[str] = None,
) -> Dict[str, Any]:
    data = result
    if "list" in result and isinstance(result["list"], list) and result["list"]:
        data = result["list"][0]
    elif "gridBot" in result and isinstance(result["gridBot"], dict):
        data = result["gridBot"]

    resolved_id = str(_pick_value(data, "botId", "bot_id", "id", default=bot_id or ""))
    entry_price = _pick_value(data, "entryPrice", "entry_price")
    stop_loss = _pick_value(data, "stopLoss", "stop_loss")
    take_profit = _pick_value(data, "takeProfit", "take_profit")

    return {
        "id": resolved_id,
        "bot_type": bot_type,
        "symbol": str(_pick_value(data, "symbol", default="")).upper(),
        "status": _map_status(_pick_value(data, "status", "botStatus", "bot_status")),
        "lower_price": _to_float(_pick_value(data, "minPrice", "lowerPrice", "lower_price")),
        "upper_price": _to_float(_pick_value(data, "maxPrice", "upperPrice", "upper_price")),
        "grid_num": _to_int(_pick_value(data, "gridNum", "grid_num", "grids")),
        "total_profit": _to_float(
            _pick_value(data, "totalProfit", "total_profit", "profit", "cumRealisedPnl")
        ),
        "investment": _to_float(
            _pick_value(
                data,
                "investment",
                "quoteInvestment",
                "investmentAmount",
                "initQuoteAmount",
                "initMargin",
            )
        ),
        "entry_price": _to_float(entry_price) if entry_price not in (None, "") else None,
        "stop_loss": _to_float(stop_loss) if stop_loss not in (None, "") else None,
        "take_profit": _to_float(take_profit) if take_profit not in (None, "") else None,
    }


def _request(method: str, route: str, query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    session = _get_session()
    try:
        response = session._submit_request(
            method=method,
            path=_path(route),
            query=query or {},
            auth=True,
        )
        return _check_response(response)
    except (FailedRequestError, InvalidRequestError) as exc:
        logger.exception("Bybit request failed for %s %s", method, route)
        raise RuntimeError(str(exc)) from exc


async def _run_sync(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _format_query(template: Dict[str, str], bot_id: str) -> Dict[str, str]:
    return {key: value.format(bot_id=bot_id) for key, value in template.items()}


async def get_bot_details(bot_id: str, bot_type: str) -> Dict[str, Any]:
    bot_type = validate_bot_type(bot_type)
    method, route, query_template = BOT_API[bot_type]["detail"]
    result = await _run_sync(
        _request,
        method,
        route,
        _format_query(query_template, str(bot_id)),
    )
    bot = _normalize_bot_detail(result, bot_type, bot_id=str(bot_id))
    if not bot["id"]:
        raise RuntimeError(f"Invalid bot details returned for bot_id={bot_id}")
    if not bot["symbol"]:
        raise RuntimeError(f"Bot {bot_id} is missing a symbol in Bybit response")
    return bot


async def _list_bots_for_type(bot_type: BotType) -> List[Dict[str, Any]]:
    list_category = BOT_API[bot_type]["list_category"]
    try:
        result = await _run_sync(
            _request,
            "GET",
            "/v5/strategy/list",
            {"category": list_category, "limit": 50},
        )
    except RuntimeError:
        logger.exception("Failed to list %s bots from Bybit", bot_type)
        return []

    rows = result.get("list") or []
    bots: List[Dict[str, Any]] = []
    for row in rows:
        row_bot_id = _pick_value(row, "strategyId", "botId", "id")
        if not row_bot_id:
            continue
        try:
            bots.append(await get_bot_details(str(row_bot_id), bot_type))
        except Exception:
            normalized = _normalize_bot_detail(row, bot_type, bot_id=str(row_bot_id))
            if normalized["symbol"]:
                bots.append(normalized)
    return bots


async def get_all_active_bots() -> List[Dict[str, Any]]:
    bots: List[Dict[str, Any]] = []
    for bot_type in BOT_TYPES:
        bots.extend(await _list_bots_for_type(bot_type))
    return bots


async def stop_bot(bot_id: str, bot_type: str) -> bool:
    bot_type = validate_bot_type(bot_type)
    method, route, query_template = BOT_API[bot_type]["close"]
    try:
        await _run_sync(
            _request,
            method,
            route,
            _format_query(query_template, str(bot_id)),
        )
        return True
    except RuntimeError as exc:
        message = str(exc).lower()
        if "405" in message or "cannot be cancelled" in message or "cancelling" in message:
            return True
        logger.exception("Failed to stop %s bot %s", bot_type, bot_id)
        return False


async def restart_bot(bot: Dict[str, Any]) -> Optional[str]:
    bot_type = validate_bot_type(bot.get("bot_type", "spot_grid"))
    required_fields = ("lower_price", "upper_price", "grid_num", "investment")
    for field in required_fields:
        if not bot.get(field):
            logger.error("Cannot restart %s bot %s: missing %s", bot_type, bot.get("id"), field)
            return None

    symbol = bot.get("symbol")
    if not symbol:
        logger.error("Cannot restart %s bot %s: missing symbol", bot_type, bot.get("id"))
        return None

    payload: Dict[str, Any] = {
        "symbol": symbol,
        "gridNum": int(bot["grid_num"]),
        "minPrice": str(bot["lower_price"]),
        "maxPrice": str(bot["upper_price"]),
        "investment": str(bot["investment"]),
    }
    if bot.get("entry_price"):
        payload["entryPrice"] = str(bot["entry_price"])
    if bot.get("stop_loss"):
        payload["stopLoss"] = str(bot["stop_loss"])
    if bot.get("take_profit"):
        payload["takeProfit"] = str(bot["take_profit"])

    _, route, _ = BOT_API[bot_type]["create"]
    try:
        result = await _run_sync(_request, "POST", route, payload)
        new_bot_id = _pick_value(result, "botId", "bot_id", "id")
        if new_bot_id:
            return str(new_bot_id)
        logger.error("Bybit create succeeded but no bot ID returned: %s", result)
        return None
    except Exception:
        logger.exception("Failed to restart %s bot %s", bot_type, bot.get("id"))
        return None


async def get_account_balance() -> float:
    result = await _run_sync(
        _request,
        "GET",
        "/v5/account/wallet-balance",
        {"accountType": "UNIFIED"},
    )
    accounts = result.get("list") or []
    if not accounts:
        return 0.0

    total = 0.0
    for account in accounts:
        for coin in account.get("coin") or []:
            if str(coin.get("coin", "")).upper() == "USDT":
                total += _to_float(coin.get("walletBalance", coin.get("equity")))
    return round(total, 2)
