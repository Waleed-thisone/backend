from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

import scheduler
import storage

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start_scheduler()
    await scheduler.update_price_state()
    yield
    scheduler.stop_scheduler()


app = FastAPI(title="BTC Alert Backend", lifespan=lifespan, debug=True)


@app.get("/health")
async def health():
    try:
        return {
            "status": "ok",
            "scheduler_running": scheduler.scheduler.running,
            "state_available": storage.load() is not None,
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
