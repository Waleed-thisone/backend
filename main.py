import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

import bybit_client
import database
import scheduler
import storage
from models import (
    AvailableBotResponse,
    AvailableBotsListResponse,
    BalanceResponse,
    BotAddRequest,
    BotResponse,
    BotsListResponse,
    SettingsResponse,
    SettingsUpdateRequest,
)

load_dotenv()

API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")
PUBLIC_PATHS = {"/health", "/status"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    scheduler.start_scheduler()
    await scheduler.update_price_state()
    yield
    scheduler.stop_scheduler()


app = FastAPI(title="BTC Alert Backend", lifespan=lifespan)


@app.middleware("http")
async def require_api_token(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    if not API_AUTH_TOKEN:
        return JSONResponse(
            status_code=503,
            content={"detail": "API authentication is not configured"},
        )

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid authorization header"},
        )

    token = auth_header.removeprefix("Bearer ").strip()
    if token != API_AUTH_TOKEN:
        return JSONResponse(status_code=401, content={"detail": "Invalid token"})

    return await call_next(request)


@app.get("/health")
async def health():
    try:
        return {
            "status": "ok",
            "scheduler_running": scheduler.scheduler.running,
            "state_available": storage.load() is not None,
            "bybit_configured": bybit_client.is_configured(),
            "db_ready": True,
            "supported_bot_types": list(bybit_client.BOT_TYPES),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.api_route("/status", methods=["GET", "HEAD"])
async def status():
    try:
        data = storage.load()
        if not data:
            return JSONResponse(
                content={
                    "message": "Price data not yet available, please wait a moment and try again"
                }
            )
        return JSONResponse(content=data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/bots", response_model=BotsListResponse)
async def list_bots():
    try:
        bots = database.get_all_bots()
        return BotsListResponse(bots=bots)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/bots/available", response_model=AvailableBotsListResponse)
async def list_available_bots():
    if not bybit_client.is_configured():
        raise HTTPException(status_code=503, detail="Bybit API credentials are not configured")

    try:
        bybit_bots = await bybit_client.get_all_active_bots()
        watchlist_ids = {bot["id"] for bot in database.get_all_bots()}
        return AvailableBotsListResponse(
            bots=[
                AvailableBotResponse(
                    **bot,
                    in_watchlist=bot["id"] in watchlist_ids,
                )
                for bot in bybit_bots
            ]
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/bots/add", response_model=BotResponse)
async def add_bot(body: BotAddRequest):
    if not bybit_client.is_configured():
        raise HTTPException(status_code=503, detail="Bybit API credentials are not configured")

    existing = database.get_bot(body.bot_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Bot {body.bot_id} is already in the watchlist")

    try:
        bot = await bybit_client.get_bot_details(body.bot_id, body.bot_type)
        saved = database.upsert_bot(bot)
        return BotResponse(**saved)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        message = str(exc).lower()
        status_code = 404 if "not found" in message else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/bots/{bot_id}")
async def remove_bot(bot_id: str):
    try:
        database.remove_bot_id(bot_id)
        return {"ok": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/balance", response_model=BalanceResponse)
async def balance():
    if not bybit_client.is_configured():
        raise HTTPException(status_code=503, detail="Bybit API credentials are not configured")

    try:
        total_balance = await bybit_client.get_account_balance()
        return BalanceResponse(total_balance=total_balance)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/settings", response_model=SettingsResponse)
async def get_settings():
    try:
        settings = database.get_settings()
        return SettingsResponse(**settings)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/settings", response_model=SettingsResponse)
async def update_settings(body: SettingsUpdateRequest):
    try:
        settings = database.update_settings(
            body.bot_type,
            body.stop_threshold_pct,
            body.restart_threshold_pct,
        )
        return SettingsResponse(**settings)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
