---
name: crypto-mt5-bridges
description: Bridge TradingView alerts to crypto exchanges and MetaTrader 5 - a Python worker that signs exchange orders (Binance, Bybit, OKX) from the webhook queue, and three ways to drive MT5 (an EA polling your server with WebRequest from OnTimer, an EA socket client, or the Windows-only MetaTrader5 Python package with order_send) - plus broker symbol suffixes, filling modes, retcodes, and why indicators and the Strategy Tester cannot make web requests. Use when connecting TradingView to Binance/Bybit/OKX or to an MT4/MT5 broker account, when WebRequest returns -1 or error 4014, or when an MT5 bridge places the wrong volume or symbol.
---

# Crypto and MT5 bridges

TradingView talks HTTP; exchanges and MetaTrader do not take TradingView's
webhook directly. The bridge is always: **receiver** (see `webhook-receiver`)
then **queue** then **an executor** for the venue. Facts checked
November 2026; sources in `reference.md`.

## Crypto exchanges

The executor is the `signal-to-order` worker with an exchange client:

- Sign with the exchange's scheme (HMAC-SHA256 query signing on Binance,
  `X-BAPI-*` headers on Bybit v5, `OK-ACCESS-*` on OKX); details and pitfalls
  are in the `exchange-api-auth` skill of claude-crypto-bot-skills.
- Round price and quantity to `tickSize`/`stepSize` with Decimal before
  sending (`order-precision`), and set a deterministic client order ID
  (`newClientOrderId`, `orderLinkId`, `clOrdId`) from the alert's dedupe key.
- API keys: trade permission only, **no withdrawals**, IP-restricted to the
  worker's server.
- TradingView perpetual tickers end in `.P` (`BINANCE:BTCUSDT.P`); map them to
  the futures API and the spot ticker to the spot API explicitly. Sending a
  perp signal to spot (or the reverse) is a classic bridge bug.
- Use the exchange's testnet first; testnet and mainnet have different base
  URLs and keys.

## MetaTrader 5: three designs

| Design | How | Good for | Limits |
|---|---|---|---|
| **EA polls your server** | EA calls `WebRequest()` from `OnTimer()` (e.g. every 1 s) to `GET /signals?since=...`, executes with `CTrade`, then acknowledges | most retail bridges; works with any MT5 broker; no inbound port on the PC | URL must be in Tools, Options, Expert Advisors allow-list; `WebRequest` blocks the EA thread; 1-2 s latency |
| **EA socket client** | `SocketCreate` / `SocketConnect` (+ `SocketTls*`) to your server, read signals | lower latency streams | client only (no listening sockets), address must be allow-listed, max 128 sockets per program |
| **Python `MetaTrader5` package** | Python worker on the same Windows machine calls `initialize()`, `order_send()` | teams that prefer Python, multi-account desks | **Windows x64 only**; a terminal must be installed, running and logged in, with Algo Trading enabled |

Rules for all three:

- `WebRequest` and sockets work only in **Expert Advisors and scripts**: an
  indicator gets error **4014**, and neither works in the Strategy Tester.
- `WebRequest` returns the HTTP status, or **-1** on failure; call
  `GetLastError()`. The usual cause of -1 is a URL missing from the allow-list.
- Ports follow the scheme (80 for http, 443 for https); use HTTPS and keep a
  shared secret in the request.
- MT5 must stay running: use a Windows VPS near the broker's server; disable
  sleep and auto-updates during market hours.

### Executing in MQL5

```mq5
#include <Trade/Trade.mqh>
CTrade trade;

bool OpenFromSignal(string sym, bool buy, double volume, double sl_points)
{
   if(!SymbolSelect(sym, true)) return false;                       // symbol must be in Market Watch
   double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   int vdigits = (int)MathMax(0, MathCeil(-MathLog10(step) - 1e-9));
   volume = NormalizeDouble(MathFloor(volume / step + 1e-9) * step, vdigits); // round DOWN to the step
   if(volume < vmin || volume > vmax) return false;
   double point = SymbolInfoDouble(sym, SYMBOL_POINT);
   double price = buy ? SymbolInfoDouble(sym, SYMBOL_ASK) : SymbolInfoDouble(sym, SYMBOL_BID);
   double sl = buy ? price - sl_points * point : price + sl_points * point;
   sl = NormalizeDouble(sl, (int)SymbolInfoInteger(sym, SYMBOL_DIGITS));
   trade.SetExpertMagicNumber(240611);
   trade.SetDeviationInPoints(20);
   bool ok = buy ? trade.Buy(volume, sym, 0, sl) : trade.Sell(volume, sym, 0, sl);
   uint rc = trade.ResultRetcode();
   if(!ok || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_PLACED))
   {
      PrintFormat("order failed %s rc=%u %s", sym, rc, trade.ResultRetcodeDescription());
      return false;
   }
   return true;
}
```

Use the `mql5-ea-builder` and `mql5-ea-reviewer` skills (claude-trading-skills)
for the full EA: stops level, spread filter, margin check, daily loss limit.

### Executing from Python

```python
import MetaTrader5 as mt5
from decimal import Decimal, ROUND_DOWN

assert mt5.initialize(), mt5.last_error()          # terminal must be running and logged in
sym = resolve_symbol("XAUUSD")                      # see suffixes below
mt5.symbol_select(sym, True)
info, tick = mt5.symbol_info(sym), mt5.symbol_info_tick(sym)
step = Decimal(str(info.volume_step))
vol = float((Decimal("0.37") / step).to_integral_value(ROUND_DOWN) * step)
req = {
    "action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": vol, "type": mt5.ORDER_TYPE_BUY,
    "price": tick.ask, "sl": round(tick.ask - 5.0, info.digits), "deviation": 20,
    "magic": 240611, "comment": "tv:" + dedupe_key[:20],
    "type_time": mt5.ORDER_TIME_GTC, "type_filling": pick_filling(info),
}
res = mt5.order_send(req)
if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
    raise RuntimeError(f"order_send failed: {None if res is None else res.retcode} {mt5.last_error()}")
```

- **Filling mode:** brokers accept different modes (`ORDER_FILLING_FOK`,
  `IOC`, `RETURN`). Read `symbol_info(sym).filling_mode` and pick an allowed
  one; "Unsupported filling mode" (retcode 10030) is the most common first
  error.
- Success is `TRADE_RETCODE_DONE` (10009); also handle requotes (10004),
  invalid stops (10016), market closed (10018) and no money (10019).
- `order_send` is synchronous but not idempotent: before retrying after a
  timeout, look for a position or deal with your `magic` and `comment`.

## Broker symbol suffixes

The same instrument has different names per broker: `EURUSD`, `EURUSD.m`,
`EURUSDm`, `XAUUSD.r`, `GOLD`, `US30` vs `DJ30`. TradingView sends its own
names (`OANDA:XAUUSD`, `FX:EURUSD`). Map explicitly per broker account, or
resolve once at start-up with `mt5.symbols_get("*EURUSD*")` (MQL5:
`SymbolsTotal` / `SymbolName`) and fail closed if there is not exactly one
tradable match. Contract sizes differ too (gold 100 oz on one broker, 1 oz on
another), so size from `SYMBOL_TRADE_TICK_VALUE` and tick size, never from a
hard-coded lot value.

## MT4

MT4 has `WebRequest` but no native sockets or Python package. Use the
polling-EA design; many brokers now offer MT5, which is easier to automate.
