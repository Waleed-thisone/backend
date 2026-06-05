# BTC Alert Flutter App — UI Build Plan

## Overview

A Flutter mobile app that connects to the **BTC Alert Backend** (FastAPI on Render/local). The app lets users:

1. Monitor **BTC price movement** and get alerted on sharp moves
2. View and manage **Bybit grid bots** (spot + futures, any symbol)
3. See **USDT balance** and configure **per-type stop/restart thresholds**

The backend handles all Bybit API calls, bot stop/restart logic, and price polling. Flutter is **UI + polling only** — no Bybit keys on the device.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Flutter App                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │  Home    │  │  Bots    │  │ Balance  │  │Settings │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘ │
│       │             │             │              │      │
│       └─────────────┴─────────────┴──────────────┘      │
│                         │                               │
│                   ApiService (http)                     │
└─────────────────────────┼───────────────────────────────┘
                          │ REST (JSON)
                          ▼
┌─────────────────────────────────────────────────────────┐
│              BTC Alert Backend (FastAPI)                │
│  Binance price  │  Bybit bots  │  SQLite  │  Scheduler │
└─────────────────────────────────────────────────────────┘
```

---

## Backend API Reference (Source of Truth)

Base URL stored in app settings (default: `http://localhost:8000` dev, Render URL prod).

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Connection check, scheduler status |
| GET/HEAD | `/status` | BTC price + alert state |
| GET | `/bots` | Watchlist bots (saved in backend DB) |
| GET | `/bots/available` | All bots on Bybit account (picker) |
| POST | `/bots/add` | Add bot to watchlist |
| DELETE | `/bots/{bot_id}` | Remove from watchlist |
| GET | `/balance` | Live USDT balance |
| GET | `/settings` | Stop/restart thresholds per bot type |
| POST | `/settings` | Update thresholds for one bot type |

### Response shapes

**GET `/status`** — price alert (poll every 30–60s on Home):

```json
{
  "current_price": 67420.0,
  "price_12h_ago": 64900.0,
  "pct_change": 3.88,
  "direction": "UP",
  "alert": true,
  "updated_at": "2024-01-15T14:30:00+00:00"
}
```

If data not ready yet:

```json
{ "message": "Price data not yet available, please wait a moment and try again" }
```

**GET `/health`**:

```json
{
  "status": "ok",
  "scheduler_running": true,
  "state_available": true,
  "bybit_configured": true,
  "db_ready": true,
  "supported_bot_types": ["spot_grid", "futures_grid"]
}
```

**GET `/bots`** and bot objects:

```json
{
  "bots": [{
    "id": "123456789",
    "bot_type": "spot_grid",
    "symbol": "ETHUSDT",
    "status": "active",
    "lower_price": 3000.0,
    "upper_price": 3500.0,
    "grid_num": 10,
    "total_profit": 42.5,
    "investment": 500.0,
    "entry_price": null,
    "stop_loss": null,
    "take_profit": null,
    "added_at": "2024-01-15T10:00:00+00:00",
    "last_synced": "2024-01-15T14:30:00+00:00"
  }]
}
```

**GET `/bots/available`** — same fields + `"in_watchlist": false`

**POST `/bots/add`** body:

```json
{ "bot_id": "123456789", "bot_type": "spot_grid" }
```

`bot_type`: `"spot_grid"` | `"futures_grid"`

**GET `/balance`**:

```json
{ "total_balance": 1234.56, "currency": "USDT" }
```

**GET `/settings`**:

```json
{
  "spot_grid": {
    "stop_threshold_pct": 3.0,
    "restart_threshold_pct": 2.0,
    "bots_stopped_for_alert": false
  },
  "futures_grid": {
    "stop_threshold_pct": 5.0,
    "restart_threshold_pct": 3.0,
    "bots_stopped_for_alert": false
  }
}
```

**POST `/settings`** body (updates one type at a time):

```json
{
  "bot_type": "futures_grid",
  "stop_threshold_pct": 6.0,
  "restart_threshold_pct": 3.5
}
```

Validation: `restart_threshold_pct` must be **less than** `stop_threshold_pct`.

---

## Design Direction

### Visual identity

Trading/fintech aesthetic — clean, dark-first, high contrast numbers.

| Token | Value | Usage |
|-------|-------|-------|
| Background | `#0D1117` | Scaffold, app bg |
| Surface | `#161B22` | Cards, bottom nav |
| Surface elevated | `#21262D` | Modals, sheets |
| Primary | `#F7931A` | BTC accent, CTAs |
| Up / profit | `#3FB950` | Positive %, active bots |
| Down / loss | `#F85149` | Negative %, alerts |
| Warning | `#D29922` | Alert banner |
| Text primary | `#F0F6FC` | Headlines, prices |
| Text secondary | `#8B949E` | Labels, timestamps |
| Border | `#30363D` | Card outlines |

### Typography

Use **Inter** or **SF Pro** system font.

| Style | Size | Weight | Use |
|-------|------|--------|-----|
| Display | 32sp | Bold | BTC price on Home |
| Title | 20sp | SemiBold | Screen titles |
| Body | 14sp | Regular | Descriptions |
| Label | 12sp | Medium | Field labels |
| Mono | 14sp | Medium | Bot IDs, percentages |

### Components to build once, reuse everywhere

- `AppCard` — rounded 16px, surface bg, subtle border
- `StatChip` — small pill: `+3.88%`, `ACTIVE`, `SPOT`
- `DirectionBadge` — 🚀 UP / 📉 DOWN
- `BotTypeBadge` — Spot Grid / Futures Grid
- `StatusDot` — green (active), gray (stopped), amber (unknown)
- `LoadingShimmer` — skeleton for cards while fetching
- `ErrorBanner` — retry button + message
- `EmptyState` — icon + title + action (e.g. "Add your first bot")

### Motion

- Pull-to-refresh on Home, Bots, Balance
- Subtle fade-in when price updates (avoid jarring number jumps)
- Alert pulse animation on Home when `alert: true`
- Bottom sheet slide for Add Bot picker

---

## App Structure

```
lib/
├── main.dart
├── app.dart                    # MaterialApp, theme, routes
├── config/
│   └── api_config.dart         # base URL from shared_preferences
├── theme/
│   ├── app_colors.dart
│   ├── app_text_styles.dart
│   └── app_theme.dart
├── models/
│   ├── price_status.dart
│   ├── bot.dart
│   ├── available_bot.dart
│   ├── balance.dart
│   ├── settings.dart
│   └── health.dart
├── services/
│   └── api_service.dart        # all HTTP calls
├── providers/                  # or bloc/ — pick one pattern
│   ├── home_provider.dart
│   ├── bots_provider.dart
│   ├── balance_provider.dart
│   └── settings_provider.dart
├── widgets/
│   ├── app_card.dart
│   ├── stat_chip.dart
│   ├── bot_tile.dart
│   ├── price_header.dart
│   └── ...
└── screens/
    ├── shell_screen.dart       # bottom nav wrapper
    ├── home_screen.dart
    ├── bots_screen.dart
    ├── add_bot_sheet.dart
    ├── balance_screen.dart
    └── settings_screen.dart
```

---

## Navigation

Bottom navigation bar (4 tabs):

| Tab | Icon | Screen |
|-----|------|--------|
| Home | `show_chart` | BTC price + alert |
| Bots | `smart_toy` | Watchlist + add/remove |
| Balance | `account_balance_wallet` | USDT total |
| Settings | `tune` | Thresholds + backend URL |

Use `IndexedStack` or `go_router` shell route to preserve tab state.

---

## Screen-by-Screen Spec

### 1. Home Screen

**Purpose:** Show BTC price, 12h change, alert state. Ring/notify when `alert: true`.

**Layout (top → bottom):**

```
┌─────────────────────────────────────┐
│  BTC Alert              [refresh]   │
├─────────────────────────────────────┤
│  ┌─────────────────────────────┐   │
│  │  ALERT BANNER (if alert)    │   │  ← pulsing amber/red strip
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │      $67,420                │   │  ← Display size, mono
│  │   🚀 UP  +3.88%  (12h)      │   │
│  │   12h ago: $64,900          │   │
│  │   Updated 2 min ago         │   │
│  └─────────────────────────────┘   │
│  ┌──────────┐  ┌──────────┐       │
│  │ Active   │  │ Stopped  │       │  ← quick stats from GET /bots
│  │   3      │  │   1      │       │
│  └──────────┘  └──────────┘       │
└─────────────────────────────────────┘
```

**Data:** `GET /status` + `GET /bots` (for bot count summary)

**Polling:** every **30 seconds** while app is foreground

**Alert behavior when `alert: true`:**

- Show full-width banner: "Sharp BTC move detected"
- Play short notification sound (optional: `audioplayers` package)
- Optional: local notification via `flutter_local_notifications` if app backgrounded
- Do **not** spam — only trigger sound when `alert` transitions `false → true`

**Empty / loading:**

- Shimmer on price card while first fetch
- If `message` key in response → show "Waiting for price data…" with spinner

---

### 2. Bots Screen

**Purpose:** Manage watchlist; add from Bybit account.

**Layout:**

```
┌─────────────────────────────────────┐
│  My Bots              [+ Add Bot]   │
├─────────────────────────────────────┤
│  Filter: [All] [Spot] [Futures]     │  ← optional chips
├─────────────────────────────────────┤
│  ┌─────────────────────────────┐   │
│  │ ETHUSDT  · Spot  · ● Active │   │
│  │ Profit: +$42.50             │   │
│  │ Range: $3,000 – $3,500      │   │
│  │ Invested: $500        [🗑]   │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │ BTCUSDT · Futures · ○ Stop  │   │
│  │ ...                         │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

**Data:** `GET /bots` — refresh on pull + every **60s**

**Bot tile shows:**

- Symbol (large), bot type badge, status dot
- `total_profit` (green if ≥ 0, red if < 0)
- Price range, investment
- Swipe-to-delete or trash icon → confirm dialog → `DELETE /bots/{id}`

**Add Bot flow (bottom sheet):**

1. Tap **[+ Add Bot]**
2. `GET /bots/available` — show loading list
3. List item: symbol, type, status, profit, `in_watchlist` badge if already added
4. Tap row → confirm → `POST /bots/add` with `bot_id` + `bot_type`
5. On success: close sheet, refresh watchlist, snackbar "Bot added"
6. Disable/grey out rows where `in_watchlist: true`

**Empty state:** "No bots yet" + button to open Add Bot sheet

---

### 3. Balance Screen

**Purpose:** Show total USDT on Bybit.

**Layout:**

```
┌─────────────────────────────────────┐
│  Balance                            │
├─────────────────────────────────────┤
│  ┌─────────────────────────────┐   │
│  │   Total Balance             │   │
│  │   $1,234.56 USDT            │   │  ← large mono
│  │   Live from Bybit           │   │
│  └─────────────────────────────┘   │
│  Note: Backend syncs balance         │
│  every 5 minutes automatically.      │
└─────────────────────────────────────┘
```

**Data:** `GET /balance` — refresh on pull + on tab focus

**Error 503:** "Bybit not configured on server" — show info card, not crash

---

### 4. Settings Screen

**Purpose:** Configure stop/restart thresholds per bot type; set backend URL.

**Layout:**

```
┌─────────────────────────────────────┐
│  Settings                           │
├─────────────────────────────────────┤
│  Backend URL                        │
│  [https://your-app.onrender.com  ]  │  ← TextField, saved locally
│  [Test Connection]                  │  ← calls GET /health
├─────────────────────────────────────┤
│  Spot Grid Bots                     │
│  Stop when BTC moves:  [3.0] %      │
│  Restart when below:   [2.0] %      │
│  [Save Spot Settings]               │
│  ⚠ Bots paused by alert: Yes/No     │  ← read-only from GET /settings
├─────────────────────────────────────┤
│  Futures Grid Bots                  │
│  Stop when BTC moves:  [5.0] %      │
│  Restart when below:   [3.0] %      │
│  [Save Futures Settings]            │
└─────────────────────────────────────┘
```

**Data:** `GET /settings` on load; `POST /settings` per section on save

**Validation (client-side, match backend):**

- Stop > Restart
- Both between 0 and 100
- Show error under fields before submit

**Explain thresholds in helper text:**

> "When BTC 12h change exceeds Stop %, all active bots of this type are stopped on Bybit. They restart when the alert clears and change falls below Restart %."

---

## State Management

**Recommendation:** `provider` + `ChangeNotifier` (simple, fits MVP)

| Provider | Responsibility |
|----------|----------------|
| `ApiConfigProvider` | Base URL from SharedPreferences |
| `HomeProvider` | Price status, alert edge detection |
| `BotsProvider` | Watchlist + available bots |
| `BalanceProvider` | USDT balance |
| `SettingsProvider` | Thresholds load/save |

Alternative: `riverpod` or `bloc` if you prefer — keep `ApiService` separate either way.

---

## ApiService Implementation

Single class, all endpoints:

```dart
class ApiService {
  ApiService(this.baseUrl);
  final String baseUrl;

  Future<PriceStatus> getStatus();
  Future<HealthStatus> getHealth();
  Future<List<Bot>> getBots();
  Future<List<AvailableBot>> getAvailableBots();
  Future<Bot> addBot(String botId, String botType);
  Future<void> removeBot(String botId);
  Future<Balance> getBalance();
  Future<AppSettings> getSettings();
  Future<AppSettings> updateSettings(String botType, double stop, double restart);
}
```

Use `http` or `dio`. Handle:

- `409` on duplicate add → show "Already in watchlist"
- `404` on add → show "Bot not found on Bybit"
- `422` on settings → show validation message
- `502/503` → show "Backend or Bybit unavailable"
- Network timeout → retry snackbar

Parse JSON with `json_serializable` or manual `fromJson` factories matching backend field names exactly.

---

## Local Storage (SharedPreferences)

| Key | Purpose |
|-----|---------|
| `backend_url` | API base URL |
| `last_alert_state` | bool — detect false→true transition for sound |
| `alert_sound_enabled` | user toggle (Settings) |

Bybit API keys stay **on the server only** — never in Flutter.

---

## Dependencies (`pubspec.yaml`)

```yaml
dependencies:
  flutter:
    sdk: flutter
  http: ^1.2.0              # or dio: ^5.4.0
  provider: ^6.1.0
  shared_preferences: ^2.2.0
  intl: ^0.19.0             # currency / date formatting
  google_fonts: ^6.1.0      # Inter
  flutter_local_notifications: ^17.0.0   # optional background alerts
  audioplayers: ^6.0.0      # optional alert sound

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^4.0.0
```

---

## Platform Notes

### Android

- `INTERNET` permission in `AndroidManifest.xml`
- For local notifications: notification channel + permissions (Android 13+)
- Cleartext HTTP only for local dev — use HTTPS on Render for production

### iOS

- `NSAppTransportSecurity` exception only for localhost dev
- Notification permissions prompt on first alert

### Backend URL

- **Dev:** `http://10.0.2.2:8000` (Android emulator) or `http://127.0.0.1:8000` (iOS sim)
- **Prod:** `https://your-service.onrender.com`

---

## Polling Strategy Summary

| Screen | Endpoint(s) | Interval |
|--------|-------------|----------|
| Home | `/status`, `/bots` | 30s foreground |
| Bots | `/bots` | 60s + pull-to-refresh |
| Balance | `/balance` | On tab open + pull |
| Settings | `/settings` | On tab open only |

Pause polling when app is in background (use `WidgetsBindingObserver`).

---

## MVP Build Order

Build in this sequence — each step is testable against a running backend:

1. [ ] Project scaffold + theme + `ApiService` + backend URL setting
2. [ ] Models + JSON parsing (unit test with sample JSON)
3. [ ] Settings screen + health check button
4. [ ] Home screen + `/status` polling + alert banner
5. [ ] Bots screen + watchlist tiles + delete
6. [ ] Add Bot bottom sheet + `/bots/available` + `/bots/add`
7. [ ] Balance screen
8. [ ] Settings thresholds save (`POST /settings`)
9. [ ] Alert sound / local notification (optional polish)
10. [ ] Error states, empty states, pull-to-refresh everywhere

---

## Testing Checklist

- [ ] Wrong backend URL → friendly error on Settings health check
- [ ] `/status` message response → loading state, not crash
- [ ] `alert: true` → banner visible; `false` → hidden
- [ ] Add bot from available list → appears in watchlist
- [ ] Add duplicate → 409 handled
- [ ] Delete bot → removed from list
- [ ] Save settings with stop ≤ restart → validation error
- [ ] Spot vs futures badges render correctly
- [ ] App works on Render HTTPS URL (production)

---

## Out of Scope (V1)

- User login / auth
- Direct Bybit API from Flutter
- Per-bot custom thresholds (backend uses per-type only)
- Balance history chart (backend stores snapshots but no history API yet)
- Push notifications via FCM (local notifications only for MVP)
- iPad / tablet layouts
- Multiple backend profiles

---

## Future Enhancements

- FCM push when backend stops/restarts bots
- `GET /balance/history` when backend adds it
- Widget / home screen widget showing BTC price
- Biometric lock on app open
- Light theme toggle

---

## Quick Reference: User Flows

**First launch**

Settings → enter Render URL → Test Connection → Home

**Add a bot**

Bots → Add Bot → pick from Bybit list → confirm → watchlist updates

**When BTC spikes**

Home banner turns on → bots auto-stop on server → Bots tab shows "Stopped" → when volatility calms, server restarts them → status returns to "Active"

**Tune aggression**

Settings → Spot: stop 4% / restart 2% → Save → Futures: stop 6% / restart 3% → Save
