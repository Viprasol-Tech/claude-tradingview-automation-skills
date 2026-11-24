---
name: indian-broker-apis
description: Execute TradingView signals on Indian brokers under SEBI's retail algo framework (fully applicable from 1 April 2026) - static IP registration, the 10 orders-per-second threshold, algo IDs, daily 2FA logins and mandatory market protection - with Zerodha Kite Connect (request_token checksum, 6 AM token expiry, Personal vs Connect plans, rate limits, tag, instruments dump), Angel One SmartAPI (TOTP login, headers, scrip master), Dhan v2 and Upstox v3. Includes a tested NSE expiry calculator (Tuesday expiries) and contract resolver for NIFTY1! and option tickers. Use when building or fixing an NSE/BSE/F&O trading bot, a TradingView-to-Zerodha/Angel/Dhan/Upstox bridge, or when orders are rejected for IP, token, market protection or rate-limit reasons.
allowed-tools: Bash(python ${CLAUDE_SKILL_DIR}/scripts/nse_symbols.py *)
---

# Indian broker APIs for TradingView bots

Facts checked November 2026 from SEBI, NSE and broker documentation; sources
and the points we could not confirm are in `reference.md`. Broker rules are
changing quickly under the new framework: re-check the broker's API
announcements before a client go-live.

## SEBI retail algo framework (what changed for API traders)

The SEBI circular of 4 February 2025 ("Safer participation of retail investors
in algorithmic trading"), after extensions, applies fully from **1 April 2026**.

| Rule | What it means for your code |
|---|---|
| Static IP | Register a primary (and optional secondary) IPv4/IPv6 with the broker. **Order place / modify / cancel** from any other IP is rejected; quotes, WebSockets, order book and positions work from anywhere. The IP can be changed about once a week and shared only with immediate family by declaration. |
| 10 orders per second | Per client, per exchange segment. Above it the strategy must be registered with the exchange through the broker (and gets its own algo ID); unregistered orders above the threshold are rejected. Slices you send as separate orders count (how exchange iceberg orders count: check with the broker). |
| Algo ID tagging | The broker tags every API order with an exchange algo ID (a generic ID for unregistered self-built algos under the threshold). Upstox exposes an `X-Algo-Name` header for registered algos. |
| No open APIs | OAuth/2FA logins; expect one full login per trading day and no long-lived trading tokens. |
| Market protection | MARKET and SL-M orders need a non-zero market protection (Zerodha rejects `market_protection=0` for API orders); some brokers convert MARKET to protected limit orders or block MARKET/IOC for algos. |
| Black-box vendors | Selling an algo whose logic is not disclosed requires SEBI Research Analyst registration and broker empanelment. Your own code on your own account does not. |

Practical setup: run the **order worker** on a VPS with a fixed public IP
(check its egress IP with `curl -4 ifconfig.me` and `curl -6 ifconfig.me`; an
IPv6 route can silently differ from the IPv4 you registered). The TradingView
webhook receiver can live elsewhere.

## Zerodha Kite Connect

- **Plans:** Personal (free) can place orders, GTT and read the portfolio, but
  has no live WebSocket or historical data; Connect (₹500 a month per app)
  adds both.
- **Login, every day:** redirect the user to
  `https://kite.zerodha.com/connect/login?v=3&api_key=...`; Kite redirects back
  with `request_token` (valid for minutes). Exchange it:
  `POST /session/token` with `checksum = SHA-256(api_key + request_token + api_secret)`.
  The `access_token` expires at **6 AM the next day** or on logout.
  Kite has no headless login; scripting the web login with the password and
  TOTP may breach the broker's terms. Plan a once-a-day human login.
- **Orders:** `POST /orders/{variety}` (`regular`, `amo`, `co`, `iceberg`,
  `auction`); `order_type` MARKET/LIMIT/SL/SL-M; `product` CNC/NRML/MIS/MTF;
  `validity` DAY/IOC/TTL; `market_protection` 1-100 or -1 (auto) for MARKET
  and SL-M; `tag` up to 20 alphanumeric characters (use it for your
  idempotency key).
- **Limits:** quote 1 req/s, historical 3 req/s, orders 10 req/s, other
  endpoints 10 req/s; 400 orders a minute, 5,000 a day, 25 modifications per
  order. HTTP 429 means slow down, not retry immediately.
- **Instruments:** `GET /instruments/NFO` returns a daily gzipped CSV
  (instrument_token, tradingsymbol, name, expiry, strike, tick_size, lot_size,
  instrument_type, segment, exchange). Download it each morning after 08:30
  and key on `exchange + tradingsymbol`: tokens of expired contracts are reused.
- **WebSocket:** `wss://ws.kite.trade?api_key=...&access_token=...`; modes
  `ltp`, `quote`, `full` (with depth); up to 3,000 instruments per connection
  and 3 connections per API key.
- **Static IP:** Developer Console, Profile, IP whitelist; applies to the
  whole account, not per app.

## Angel One SmartAPI

- Base `https://apiconnect.angelone.in`. Login
  `POST /rest/auth/angelbroking/user/v1/loginByPassword` with `clientcode`,
  `password` (the PIN) and `totp` (from the TOTP secret, e.g. `pyotp`) returns
  `jwtToken`, `refreshToken` and `feedToken`; refresh with
  `/rest/auth/angelbroking/jwt/v1/generateTokens`.
- Headers on every call: `X-PrivateKey` (API key), `X-UserType: USER`,
  `X-SourceID: WEB`, `X-ClientLocalIP`, `X-ClientPublicIP`, `X-MACAddress`,
  `Authorization: Bearer <jwt>`.
- Place order: `POST /rest/secure/angelbroking/order/v1/placeOrder` with
  `variety`, `tradingsymbol` (e.g. `SBIN-EQ`), `symboltoken`, `transactiontype`,
  `exchange`, `ordertype`, `producttype`, `duration`, `price`, `quantity`.
  Check the official SDK for the current enum values.
- Instruments: the `OpenAPIScripMaster.json` file (tens of MB). Tokens repeat
  across segments, so always filter by `symbol` **and** `exch_seg`. Cache it;
  it has had outages.
- Static IP is registered per app in the SmartAPI dashboard.

## Dhan v2 and Upstox v3

- **Dhan:** base `https://api.dhan.co/v2/`, header `access-token`, plus
  `dhanClientId` in order bodies. Tokens from the web console last 24 hours
  (renewable); an API key/secret consent flow also exists. Static IP via
  `/v2/ip/setIP` and `/v2/ip/modifyIP` (once every 7 days). Order limits:
  10/s, 250/min, 1,000/h, 7,000/day; data 5/s; quotes 1/s. Instruments are
  `security_id`s from the scrip-master CSV.
- **Upstox:** OAuth2 (`/v2/login/authorization/dialog`, then
  `/v2/login/authorization/token`; the code is single-use). The access token
  expires at 3:30 AM next day, with no refresh token; the 1-year "Analytics
  Token" is read-only. Orders: `POST https://api-hft.upstox.com/v3/order/place`
  with `instrument_token` (an instrument key like `NSE_FO|43919`), `product`
  I/D/MTF, `tag` (up to 40 characters), `slice` (auto-split above freeze
  quantity) and `market_protection`. Orders 10/s unregistered (50/s
  registered). Static IP via `/user/ip`; changing it invalidates the token.

## Symbols, lots and expiries

```bash
python ${CLAUDE_SKILL_DIR}/scripts/nse_symbols.py expiry --month 2026-12 --holidays nse_holidays_2026.txt
python ${CLAUDE_SKILL_DIR}/scripts/nse_symbols.py resolve instruments_nfo.csv --name NIFTY --type FUT --front --roll-days 2   # NSE:NIFTY1! -> future to trade
python ${CLAUDE_SKILL_DIR}/scripts/nse_symbols.py resolve instruments_nfo.csv --tv NSE:NIFTY261229C26000           # TradingView option -> broker contract
```

- **Expiries (from September 2025):** NSE index and stock derivatives expire
  on **Tuesday**. NIFTY has weekly contracts every Tuesday and a monthly on the
  last Tuesday; BANKNIFTY and stock F&O are monthly. A holiday moves expiry to
  the previous trading day. The script needs NSE's holiday list; it never
  guesses holidays.
- **TradingView tickers:** options are `NAME + YYMMDD + C/P + STRIKE`
  (`NSE:NIFTY261229C26000`); `NSE:NIFTY1!` is a continuous future and not
  tradable. Resolve either to a real contract from the broker's dump, and roll
  the future before its expiry deliberately: `--roll-days 2` skips contracts
  expiring within 2 days. Stock F&O held into expiry is physically settled.
- **Never build broker symbols by string formatting.** Zerodha's weekly option
  format (`NIFTY` + YY + month code + DD + strike + CE/PE) differs from its
  monthly format (`NIFTY26DEC26000CE`), and brokers differ from each other.
  Filter the dump by name, instrument type, expiry and strike.
- **Lot sizes** change by NSE circular (NIFTY 65 and BANKNIFTY 30 from the
  January 2026 contracts). Read `lot_size` from the dump every day; quantity
  must be a multiple of it.
- **Freeze quantity:** orders above the exchange freeze limit are rejected;
  slice them (Upstox `slice`, Zerodha iceberg) and remember slices count
  towards 10 orders a second.
- **Sessions:** equity and F&O 09:15-15:30 IST; intraday (MIS) positions are
  auto squared off by the broker before the close, at a time set by the
  broker. Do not send entries after your broker's cut-off.

## Checklist before going live

1. Worker egress IP equals the registered static IP (IPv4 and IPv6).
2. Daily login flow works and alerts a human if the token is missing by 09:00.
3. Order rate is throttled below 10/s per segment, including retries and
   slices.
4. MARKET and SL-M orders carry `market_protection`; or use limit orders.
5. Instruments refreshed today; symbol mapping fails closed.
6. Product type (MIS/CNC/NRML) matches the strategy's holding period.
7. Paper-traded through at least one weekly expiry and one rollover.
