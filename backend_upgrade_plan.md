# BTC Alert Backend — Upgrade Plan (Bybit Bot Management)

## What's Changing

The existing backend already does:
- Fetches BTC price every 5 minutes from Binance
- Saves price + alert state to `state.json`
- Exposes `GET /status`

We are adding:
- SQLite database to store bots, earnings, balance, settings
- Bybit API integration to fetch bot data and control bots
- Auto stop/restart logic based on configurable thresholds
- New endpoints for Flutter app to manage bots and settings

---

## Upgraded Architecture

```
APScheduler (every 5 min)
    │
    ├── Fetch BTC price (Binance) → save to state.json (existing)
    │
    └── Fetch all bot data from Bybit API → save to SQLite
            │
            ├── pct_change > stop_threshold?
            │       └── YES → stop all configured bots via Bybit API
            │
            └── alert active + pct_change < restart_threshold?
                        └── YES → restart stopped bots via Bybit API

Flutter app
    └── GET /bots          → list all bots with status + earnings
    └── GET /balance       → total Bybit account balance
    └── GET /status        → price + alert state (existing)
    └── GET /settings      → current thresholds
    └── POST /settings     → update thresholds
    └── POST /bots/add     → add bot ID to watch list
    └── DELETE /bots/{id}  → remove bot from watch list
```

---

## New Folder Structure

Add these files to the existing project:

```
btc-alert-backend/
├── main.py               # MODIFY — add new routes
├── scheduler.py          # MODIFY — add bot sync + stop/restart logic
├── binance_client.py     # unchanged
├── storage.py            # unchanged (still used for state.json)
├── database.py           # NEW — SQLite setup, tables, queries
├── bybit_client.py       # NEW — Bybit API calls
├── bot_manager.py        # NEW — stop/restart logic
├── models.py             # MODIFY — add new request/response models
├── requirements.txt      # MODIFY — add new dependencies
├── .env                  # MODIFY — add Bybit API credentials
└── state.json            # unchanged
```

---

## New Dependencies (add to `requirements.txt`)

```
pybit
sqlalchemy
```

- `pybit` — official Bybit Python SDK
- `sqlalchemy` — ORM for SQLite

---

## Updated Environment Variables (`.env`)

Add these to existing `.env`:

```
BYBIT_API_KEY=your_api_key_here
BYBIT_API_SECRET=your_api_secret_here
BYBIT_TESTNET=false
DEFAULT_STOP_THRESHOLD_PCT=3.0
DEFAULT_RESTART_THRESHOLD_PCT=2.0
```

---

## Database Schema (`database.py`)

Three tables:

### `bots` table
Stores the grid bots user wants to track and control:
```
id              TEXT PRIMARY KEY    — Bybit bot ID
symbol          TEXT                — e.g. BTCUSDT
status          TEXT                — active / stopped / unknown
lower_price     REAL                — grid lower bound
upper_price     REAL                — grid upper bound
total_profit    REAL                — total earnings from Bybit
investment      REAL                — amount invested in bot
added_at        TEXT                — when user added this bot
last_synced     TEXT                — last time data was fetched from Bybit
```

### `settings` table
Single row, stores user configurable thresholds:
```
id                      INTEGER PRIMARY KEY  — always 1
stop_threshold_pct      REAL                 — default 3.0
restart_threshold_pct   REAL                 — default 2.0
```

### `balance_snapshots` table
Stores periodic balance readings for tracking growth:
```
id              INTEGER PRIMARY KEY AUTOINCREMENT
total_balance   REAL
timestamp       TEXT
```

Functions to implement:
- `init_db()` — create tables if not exist, insert default settings row
- `get_all_bots()` → list of bot dicts
- `upsert_bot(bot_data: dict)` → insert or update bot
- `add_bot_id(bot_id: str)` → add bot to watchlist
- `remove_bot_id(bot_id: str)` → remove bot from watchlist
- `get_settings()` → returns settings dict
- `update_settings(stop_pct, restart_pct)` → update thresholds
- `save_balance_snapshot(balance: float)` → append new snapshot

---

## Bybit Integration (`bybit_client.py`)

Use `pybit` SDK with `HTTP` session.

Functions:

**`get_bot_details(bot_id: str) → dict`**
- Call Bybit Grid Trading API to fetch single bot info
- Return: status, profit, investment, lower/upper price

**`get_all_active_bots() → list`**
- Fetch all active spot grid bots from Bybit
- Filter by symbol BTCUSDT

**`stop_bot(bot_id: str) → bool`**
- Call Bybit API to cancel/stop the grid bot
- Return True if successful

**`restart_bot(bot_id: str) → bool`**
- Restart a previously stopped grid bot
- Note: Bybit may require recreating the bot with same parameters — handle this case

**`get_account_balance() → float`**
- Fetch total USDT balance from Bybit spot wallet
- Return total balance as float

---

## Bot Manager (`bot_manager.py`)

This is the brain — decides when to stop and restart.

```python
async def check_and_act(pct_change: float):
    settings = database.get_settings()
    state = storage.load()
    bots = database.get_all_bots()

    abs_change = abs(pct_change)

    # Stop condition
    if abs_change > settings["stop_threshold_pct"]:
        for bot in bots:
            if bot["status"] == "active":
                success = await bybit_client.stop_bot(bot["id"])
                if success:
                    database.upsert_bot({**bot, "status": "stopped"})

    # Restart condition
    elif abs_change < settings["restart_threshold_pct"]:
        for bot in bots:
            if bot["status"] == "stopped":
                success = await bybit_client.restart_bot(bot["id"])
                if success:
                    database.upsert_bot({**bot, "status": "active"})
```

---

## Updated Scheduler (`scheduler.py`)

Add to the existing 5-minute tick — after price fetch:

1. Call `bybit_client.get_all_active_bots()` → sync to database
2. Call `bybit_client.get_account_balance()` → save snapshot
3. Call `bot_manager.check_and_act(pct_change)`

---

## New Routes (`main.py`)

Add these routes:

```
GET /bots
    → database.get_all_bots()
    → returns list of all tracked bots with status, profit, investment

POST /bots/add
    body: { "bot_id": "123456" }
    → validates bot exists on Bybit via bybit_client.get_bot_details()
    → adds to database
    → returns bot details

DELETE /bots/{bot_id}
    → removes bot from database watchlist

GET /balance
    → bybit_client.get_account_balance()
    → returns { "total_balance": 1234.56, "currency": "USDT" }

GET /settings
    → database.get_settings()
    → returns { "stop_threshold_pct": 3.0, "restart_threshold_pct": 2.0 }

POST /settings
    body: { "stop_threshold_pct": 4.0, "restart_threshold_pct": 2.0 }
    → database.update_settings()
    → returns updated settings
```

---

## Bybit API Key Setup (Manual — Do Before Running)

1. Log into Bybit → Account & Security → API Management
2. Create new API key:
   - Name: `btc-alert-backend`
   - Permissions: **Read** + **Trade** (needed to stop/start bots)
   - IP restriction: add your Render server IP for security
3. Copy API Key and Secret into `.env`
4. Never commit `.env` to GitHub — already in `.gitignore`

---

## Updated Render Deployment

After upgrading:
1. Add `BYBIT_API_KEY` and `BYBIT_API_SECRET` to Render environment variables
2. Add `BYBIT_TESTNET=false`
3. SQLite database file (`btc_alert.db`) will be created automatically on first run
4. Push to GitHub → Render auto-deploys

> Note: Render free tier has ephemeral storage — SQLite file resets on redeploy.
> To persist data, either upgrade to Render paid tier or switch to PostgreSQL later.
> For MVP this is acceptable — bot list and settings just need to be re-added after redeploy.

---

## MVP Checklist

- [ ] `database.py` — tables + all query functions
- [ ] `bybit_client.py` — get bots, stop bot, restart bot, get balance
- [ ] `bot_manager.py` — stop/restart logic
- [ ] `scheduler.py` — add bot sync + balance snapshot + bot_manager call
- [ ] `main.py` — add 5 new routes
- [ ] `models.py` — add new request/response models
- [ ] `.env` — add Bybit credentials
- [ ] `requirements.txt` — add pybit, sqlalchemy
- [ ] Test: add a bot via POST /bots/add, check GET /bots returns it
- [ ] Test: GET /balance returns real Bybit balance
- [ ] Test: manually trigger stop via bot_manager, confirm bot stops on Bybit

---

## Out of Scope (Future)

- Multiple trading pairs
- Profit/loss chart history in Flutter
- Push notifications for bot stop/restart events
- PostgreSQL migration for persistent storage
- Authentication
