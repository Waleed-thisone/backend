# BTC Alert Backend — Cursor Build Plan

## What This Does

Every 5 minutes:
1. Fetch current BTC price from Binance
2. Compare with price from 12 hours ago
3. Calculate % change
4. Store the result

Flutter app reads the result whenever it wants. That's it.

---

## Architecture

```
APScheduler (every 5 min)
    │
    ▼
Binance API → get current price
    │
    ▼
Compare with price 12h ago → calculate % change
    │
    ▼
Save result to state.json

Flutter polls GET /status → reads the saved result
```

---

## Folder Structure

```
btc-alert-backend/
├── main.py            # FastAPI app + single route
├── scheduler.py       # Every 5 min: fetch price, compare, save result
├── binance_client.py  # Fetch BTC price from Binance
├── storage.py         # Read/write state.json
├── requirements.txt
└── .env
```

---

## Dependencies (`requirements.txt`)

```
fastapi
uvicorn
apscheduler
httpx
python-dotenv
```

---

## `state.json` Shape

This is the only file the backend writes to and the Flutter app reads from.

```json
{
  "current_price": 67420.0,
  "price_12h_ago": 64900.0,
  "pct_change": 3.88,
  "direction": "UP",
  "alert": true,
  "updated_at": "2024-01-15T14:30:00"
}
```

- `alert` is `true` if `abs(pct_change) > 3.0`, otherwise `false`
- `direction` is `"UP"` or `"DOWN"`
- Flutter reads `alert` — if true, it rings. Simple.

---

## File-by-File Guide

### `binance_client.py`
- `GET https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=720`
- `limit=720` = 720 one-minute candles = last 12 hours (no API key needed)
- Return two values:
  - `price_now` — close price of the last candle
  - `price_12h_ago` — close price of the first candle

### `storage.py`
- `save(data: dict)` — write dict to `state.json`
- `load()` — read and return `state.json` as dict, return `None` if file doesn't exist

### `scheduler.py`
- `AsyncIOScheduler`, runs every 5 minutes, starts on FastAPI startup
- On each tick:
  1. Call `binance_client` → get `price_now`, `price_12h_ago`
  2. `pct_change = ((price_now - price_12h_ago) / price_12h_ago) * 100`
  3. Build result dict (see `state.json` shape above)
  4. Call `storage.save(result)`

### `main.py`
- One route only:

```
GET /status
  → calls storage.load()
  → returns state.json contents as JSON
```

- Register scheduler start on `startup`, stop on `shutdown`

---

## Deployment

- Platform: Railway or Render (free tier)
- Start command: `uvicorn main:app --host 0.0.0.0 --port 8000`

---

## MVP Checklist

- [ ] `binance_client.py` — fetch klines, return two prices
- [ ] `storage.py` — save and load state.json
- [ ] `scheduler.py` — 5-minute job, calculate and save result
- [ ] `main.py` — GET /status route + scheduler wired up
- [ ] Test: run locally, wait 5 min, hit /status, confirm result updates
