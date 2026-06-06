# Flutter Task: Add Bearer Token Auth for Protected Backend Routes

Use this prompt in Cursor on the **Flutter app laptop**. The backend (FastAPI on Render/local) now requires authentication on all routes except `/health`.

---

## Background

The BTC Alert backend exposes REST JSON endpoints for BTC price alerts, Bybit grid bot management, balance, and settings. Previously every route was public — anyone with the Render URL could read balance or add/remove bots.

**Change already deployed on backend:** HTTP middleware validates a shared Bearer token before any protected route runs.

---

## Auth Rules (backend behavior)

| Route | Auth required? |
|-------|----------------|
| `GET /health` | **No** — use for connection test only |
| `GET /status` | **Yes** |
| `GET /bots` | **Yes** |
| `GET /bots/available` | **Yes** |
| `POST /bots/add` | **Yes** |
| `DELETE /bots/{bot_id}` | **Yes** |
| `GET /balance` | **Yes** |
| `GET /settings` | **Yes** |
| `POST /settings` | **Yes** |

### Request header (all protected routes)

```
Authorization: Bearer <API_AUTH_TOKEN>
Content-Type: application/json   // for POST bodies
```

### Error responses

| Status | Meaning | Flutter action |
|--------|---------|----------------|
| `401` | Missing/wrong token | Show "Invalid API token" in Settings; block data screens |
| `503` + `"API authentication is not configured"` | Backend missing `API_AUTH_TOKEN` env | Show server misconfiguration message |
| `503` + `"Bybit API credentials are not configured"` | Balance/bots need Bybit keys on server | Show "Bybit not configured on server" |
| `502` | Bybit upstream error | Show retry + error detail |

401/503 error body shape (FastAPI):

```json
{ "detail": "Invalid token" }
```

---

## Token storage (Flutter)

1. Add a new setting: **API Token** (secure text field, obscured like a password).
2. Store in `shared_preferences` alongside existing **Backend URL**.
3. Load both on app startup into your config/provider layer.
4. **Do not hardcode the token in source code** — user enters it once in Settings.

The token value lives in:
- Backend `.env` → `API_AUTH_TOKEN=...`
- Render dashboard → Environment → `API_AUTH_TOKEN`

Copy the same value into the Flutter app Settings screen.

---

## Required code changes

### 1. Extend API config

File pattern: `lib/config/api_config.dart` (or equivalent)

Add:
- `String? apiAuthToken`
- `Future<void> saveApiAuthToken(String token)`
- `Future<void> loadConfig()` — load base URL + token together

### 2. Centralize headers in ApiService

Every HTTP call must include auth **except** `GET /health`.

```dart
Map<String, String> _headers({bool includeAuth = true}) {
  final headers = <String, String>{
    'Content-Type': 'application/json',
  };
  if (includeAuth) {
    final token = apiConfig.apiAuthToken?.trim();
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
  }
  return headers;
}
```

Example — health check (no auth):

```dart
Future<HealthResponse> getHealth() async {
  final uri = Uri.parse('${baseUrl}/health');
  final response = await http.get(uri, headers: _headers(includeAuth: false));
  // ...
}
```

Example — protected route:

```dart
Future<BalanceResponse> getBalance() async {
  final uri = Uri.parse('${baseUrl}/balance');
  final response = await http.get(uri, headers: _headers());
  if (response.statusCode == 401) {
    throw ApiAuthException('Invalid or missing API token');
  }
  // parse JSON...
}
```

Apply the same pattern to **all** endpoints listed in the auth table above.

### 3. Settings screen UI

Add below the Backend URL field:

```
┌─────────────────────────────────────┐
│ Backend URL                         │
│ [https://your-app.onrender.com   ]  │
│                                     │
│ API Token                           │
│ [••••••••••••••••••••••••••••••]  │  ← obscured TextField
│                                     │
│ [Test Connection]                   │  ← GET /health (no token)
│ [Save]                              │
└─────────────────────────────────────┘
```

**Test Connection** should:
1. Call `GET /health` without auth
2. If 200 → show "Server reachable"
3. Optionally call `GET /settings` with token → if 200 show "Token valid", if 401 show "Token invalid"

### 4. Global auth error handling

In providers (`StatusProvider`, `BotsProvider`, `BalanceProvider`, etc.):

- On `401` from any protected call → set error state like `"Check API token in Settings"`
- Do not silently show empty data when auth failed

Optional: redirect user to Settings tab on first 401.

### 5. POST/DELETE requests

```dart
await http.post(
  Uri.parse('$baseUrl/bots/add'),
  headers: _headers(),
  body: jsonEncode({'bot_id': id, 'bot_type': type}),
);

await http.delete(
  Uri.parse('$baseUrl/bots/$botId'),
  headers: _headers(),
);
```

---

## Endpoint reference (unchanged JSON shapes)

Base URL: user-configured (dev: `http://localhost:8000`, prod: Render URL)

### GET `/health` — no auth

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

### GET `/status` — auth required

Success:

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

Not ready yet:

```json
{ "message": "Price data not yet available, please wait a moment and try again" }
```

### GET `/balance` — auth required

```json
{ "total_balance": 1234.56, "currency": "USDT" }
```

**Note:** `0.0` is a valid response — it means Bybit unified wallet USDT balance is zero, not a broken endpoint.

### GET `/settings` — auth required

```json
{
  "spot_grid": {
    "stop_threshold_pct": 3.0,
    "restart_threshold_pct": 2.0,
    "bots_stopped_for_alert": false
  },
  "futures_grid": {
    "stop_threshold_pct": 2.0,
    "restart_threshold_pct": 2.0,
    "bots_stopped_for_alert": false
  }
}
```

### POST `/settings` — auth required

Body:

```json
{
  "bot_type": "futures_grid",
  "stop_threshold_pct": 2.0,
  "restart_threshold_pct": 2.0
}
```

---

## Checklist for Cursor on Flutter laptop

- [ ] Add `apiAuthToken` to config + SharedPreferences
- [ ] Add obscured token field on Settings screen
- [ ] Add `Authorization: Bearer ...` header in ApiService for all routes except `/health`
- [ ] Handle `401` with clear user message (not empty UI)
- [ ] Update "Test Connection" to validate token via `GET /settings`
- [ ] Verify Home, Bots, Balance, Settings tabs all work with token saved
- [ ] Verify `/health` still works without token

---

## Manual test commands (curl)

Replace `BASE` and `TOKEN`:

```bash
# Public — should return 200
curl -s "$BASE/health"

# Protected without token — should return 401
curl -s "$BASE/balance"

# Protected with token — should return 200
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/balance"
```

---

## Balance endpoint troubleshooting

If balance shows `$0.00` or `0.0`:

1. **Not blocked by Bybit** — if the API key lacked access, you'd get `502` with an error message, not `200`.
2. **`401`** — Flutter is not sending the token (auth issue, not Bybit).
3. **`503`** — Bybit keys missing on Render (`BYBIT_API_KEY`, `BYBIT_API_SECRET`).
4. **`200` with `total_balance: 0.0`** — Bybit unified account genuinely has 0 USDT free balance. Funds locked inside grid bots may not appear as wallet USDT. Deposit USDT to the **Unified Trading Account** on Bybit to see a non-zero value.
5. **Render env** — ensure same Bybit keys as local `.env`.

Backend reads balance via Bybit `GET /v5/account/wallet-balance?accountType=UNIFIED&coin=USDT`.

---

## Do NOT change on Flutter

- No Bybit API keys on device
- No direct Binance calls
- Backend URL + API token only

---

## Related backend files (for reference only — do not edit on Flutter laptop)

- `main.py` — auth middleware, `API_AUTH_TOKEN`, `PUBLIC_PATHS = {"/health"}`
- `.env` — `API_AUTH_TOKEN=...` (gitignored)
- Render → Environment → add `API_AUTH_TOKEN` when deploying
