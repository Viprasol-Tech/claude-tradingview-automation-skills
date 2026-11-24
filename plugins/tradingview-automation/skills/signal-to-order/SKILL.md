---
name: signal-to-order
description: Turn a TradingView signal into a broker order safely - the worker between the webhook queue and the broker - target-position logic instead of blind buy/sell, idempotent client order IDs from the alert's dedupe key, symbol mapping (TradingView ticker to broker instrument), sizing from risk with lot and tick rounding, pre-trade risk checks, market-hours and kill-switch gates, order-type choice, partial fills, reconciliation against broker positions, and a paper-trading mode. Use when writing or reviewing the code that executes TradingView alerts on any broker or exchange, or when a bot doubled a position, missed an exit or traded the wrong contract.
---

# Signal to order

The webhook receiver only says "a valid signal arrived". This worker decides
what, if anything, to send to the broker. Most expensive bot failures happen
here: doubled positions, an exit that opened a reverse position, a futures
order on last month's contract.

## The loop

```text
for each signal in queue (oldest first, one symbol at a time):
    if kill_switch or outside session or signal too old: mark skipped; continue
    instrument = map_symbol(signal.symbol)            # explicit table, fail closed
    target     = target_position(signal)              # e.g. +10, 0, -10
    current    = broker.position(instrument)          # ask the broker, not your memory
    delta      = target - current
    if delta == 0: mark done; continue
    qty        = round_to_lot(abs(delta), instrument) # never round up
    check risk limits (max qty, max notional, max orders/min, daily loss)
    order_id   = client_id(signal.dedupe_key, leg)    # deterministic -> idempotent
    place order; record (signal, order_id, status)
    poll / listen for fills; handle partials, rejects, timeouts
    reconcile: broker position == target? else alert a human
```

## Target position beats buy/sell

A "buy" alert is ambiguous: open a long, close a short, or add? And
`{{strategy.order.action}}` is `sell` both for closing a long and opening a
short. Send the **target**:

```json
{"secret":"...","symbol":"NSE:RELIANCE","action":"{{strategy.order.action}}",
 "position":"{{strategy.market_position}}","size":{{strategy.market_position_size}},"timenow":"{{timenow}}"}
```

`position` long/short/flat plus `size` gives the target; the worker trades
the difference from the broker's actual position. A missed or duplicated
alert then self-corrects on the next one instead of compounding.

## Idempotency

- Client order ID = hash of the signal's dedupe key plus leg number, trimmed
  to the broker's length and character rules (Zerodha `tag` is up to 20
  characters; exchange client IDs are often 32-36). Before resending after a
  timeout, **query by that ID**; never place a second order with a new ID
  until you know the first one does not exist.
- Process one symbol's signals serially (a per-symbol lock or a single worker),
  or two signals race on the same "current position".

## Symbol mapping

- Keep an explicit table: `NSE:RELIANCE -> NSE/RELIANCE (instrument token ...)`,
  `NSE:NIFTY1! -> NFO NIFTY<current expiry>FUT`, `BINANCE:BTCUSDT.P -> BTCUSDT
  perp`, `OANDA:XAUUSD -> XAUUSD.m on the MT5 broker`. Reject unknown symbols.
- TradingView continuous futures (`1!`, `2!`) are not tradable instruments.
  Resolve them to a real contract, and roll before expiry deliberately (see
  `indian-broker-apis` for NSE expiries).
- Refresh broker instrument lists daily; tokens and lot sizes change.

## Sizing and rounding

- Size from risk (account equity x risk % / stop distance), then round **down**
  to the lot size or quantity step and check the minimum; prices to the tick in
  the safe direction. For the maths and exchange filters use
  `position-sizing` (claude-trading-skills) and `order-precision`
  (claude-crypto-bot-skills).
- F&O quantities are multiples of the lot size; crypto quantities multiples of
  `stepSize`; MT5 volumes multiples of `SYMBOL_VOLUME_STEP`.

## Order type

- Market orders on illiquid symbols slip badly; many Indian brokers convert
  market orders to limit orders with a protection band, and some exchanges
  reject market orders on far-month or illiquid contracts. Prefer a
  **marketable limit** (best bid/ask plus a few ticks) with a time-out.
- Attach the stop at the broker (bracket/OCO/stop order) when supported, so the
  position is protected if your server dies. Otherwise place the stop as soon
  as the entry fills, and alert if it fails.
- Respect product type (Indian brokers: intraday `MIS` vs delivery `CNC` vs
  `NRML` for F&O carry) and the broker's auto square-off time.

## Risk gates (fail closed)

Max position per symbol, max total exposure, max orders per minute, daily loss
limit (persisted, not in memory), allowed symbols, trading hours, and a kill
switch. Any gate failing means **no order** plus an alert to a human.

## Reconciliation

- After every order and on a timer, compare broker positions and open orders
  with the targets. Differences are incidents: alert, do not auto-fix by
  sending more orders in a loop.
- On start-up, load positions and open orders from the broker before
  processing the queue.
- Keep an append-only journal: signal received, decision, order sent, broker
  response, fills. It is the only way to explain a bad day.

## Paper mode first

Run the same worker against the broker's sandbox or a paper adapter that fills
at the next tick, for at least a few sessions. Compare paper fills with the
TradingView strategy's trade list; differences show slippage, missed alerts
and timing bugs before real money does.
