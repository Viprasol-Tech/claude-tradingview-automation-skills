---
name: tv-alert-design
description: Design TradingView alerts that a bot can trust - alert() vs alertcondition() vs strategy order-fill alerts, alert frequency and bar-close timing so signals do not repaint, the {{placeholder}} variables ({{ticker}}, {{close}}, {{timenow}}, {{strategy.order.action}}, {{strategy.order.contracts}}, {{strategy.order.alert_message}}, plot values), and a JSON message format with a secret, symbol, action, size and timestamp. Includes a linter that renders a template with sample values and catches invalid JSON, unquoted text placeholders, NaN plots and missing secrets. Use when writing Pine alert code or an alert message for a webhook bot, when a webhook receives malformed JSON, or when alerts fire on signals that later disappear.
allowed-tools: Bash(python ${CLAUDE_SKILL_DIR}/scripts/tv_alert_lint.py *)
---

# TradingView alert design

The alert is the contract between a chart and a bot. Get three things right:
**when** it fires (no repainting), **what** it says (valid JSON with every
field the bot needs), and **who** can send it (a secret). Facts checked
November 2026; see `reference.md` for sources.

## Lint every message before pasting it

```bash
L=${CLAUDE_SKILL_DIR}/scripts/tv_alert_lint.py
python $L --show --message '{"secret":"...","symbol":"{{exchange}}:{{ticker}}","action":"{{strategy.order.action}}","qty":{{strategy.order.contracts}},"timenow":"{{timenow}}"}'
python $L alert.txt
```

Exit code 1 means the webhook would receive something it must reject.

## Three ways to fire an alert

| Source | Set up | Best for |
|---|---|---|
| `alert(message, freq)` in an indicator or strategy | one alert per script: "Any alert() function call" | dynamic messages built in Pine (`str.tostring`) |
| `alertcondition(cond, title, message)` | one alert per condition, chosen in the dialog | indicators only, global scope, `const string` message |
| Strategy order fills | alert on the strategy, "Order fills" | bots that mirror a backtested strategy; uses `{{strategy.order.*}}` |

**`alert()` does not process placeholders.** `{{close}}` inside an `alert()`
message arrives literally; build the text in Pine with `str.tostring()` and
concatenation. Placeholders work in `alertcondition()` messages, in strategy
order-fill messages and in the alert dialog's message field.

For strategies, pass a per-order message with
`strategy.entry(..., alert_message = json)` (also `strategy.exit`,
`strategy.order`, `strategy.close`) and set the alert message to just
`{{strategy.order.alert_message}}`; it is empty for orders without one. Then
lint each `alert_message` string. Give every order its own message:
`{{strategy.order.action}}` is `sell` both when a long is closed and when a
short is opened, so the bot cannot tell them apart from the action alone.

## Timing: stop repainting signals

- `alert.freq_once_per_bar_close` (or "Once per bar close" in the dialog) fires
  only when the bar is confirmed. Use it unless the strategy is designed for
  intrabar entries.
- "Once per bar" and `freq_all` fire on the live, unconfirmed bar: the
  condition can be true at 10:14:30 and false at the close, so the bot trades a
  signal the chart no longer shows.
- `request.security()` from a higher timeframe must use
  `lookahead = barmerge.lookahead_on` with `[1]` offsets (or the confirmed
  value) to avoid future data in history and different behaviour live.
- Strategies: `calc_on_every_tick = false` and `process_orders_on_close`
  chosen deliberately; order-fill alerts fire when the simulated order fills,
  which with default settings is the **next bar's open**.
- An alert keeps a snapshot of the script, its inputs, the symbol and the
  timeframe it was created with. After editing the Pine code or inputs,
  delete and recreate the alert.
- Alerts only fire on real-time bars, never on history. A runtime error in
  the script stops it, and its alerts stop firing.
- In a strategy without `calc_on_every_tick = true`, every `alert()` call
  behaves as once per bar close.

## Message format

```json
{
  "secret": "at-least-16-random-characters",
  "id": "{{strategy.order.id}}",
  "symbol": "{{exchange}}:{{ticker}}",
  "action": "{{strategy.order.action}}",
  "qty": {{strategy.order.contracts}},
  "price": {{close}},
  "position": "{{strategy.market_position}}",
  "timenow": "{{timenow}}",
  "tf": "{{interval}}"
}
```

Rules the linter enforces:

- Text placeholders (`{{ticker}}`, `{{exchange}}`, `{{interval}}`,
  `{{timenow}}`, `{{strategy.order.action}}`, `{{strategy.market_position}}`)
  must sit **inside quotes**.
- Numeric placeholders (`{{close}}`, `{{volume}}`,
  `{{strategy.order.contracts}}`) may be bare numbers. Plot values
  (`{{plot_0}}` to `{{plot_19}}`, `{{plot("ATR")}}`) can render as `NaN` on
  bars where the series is `na`: bare, that is invalid JSON; quoted, it
  arrives as the string `"NaN"`. Wrap the plot in `nz()` in Pine and check the
  value is finite on the server. Only the first 20 plots are reachable.
- `{{time}}` is the bar's open time and `{{timenow}}` the firing time, both
  UTC as `yyyy-MM-ddTHH:mm:ssZ`. Use `{{timenow}}` for staleness checks.
- Delayed-data symbols arrive with a `_DL`/`_DLY` suffix on `{{ticker}}`;
  strip or reject it on the server.
- A misspelled placeholder is sent literally (`"{{tickr}}"`); the bot then
  sees a symbol called `{{tickr}}`.
- Include `secret` (16+ random characters), `symbol`, `action` and
  `timenow` - the field names the bundled receiver requires - to
  authenticate, route, and reject stale or replayed alerts.
- Send the **target position** (`{{strategy.market_position}}` and size), not
  only "buy"/"sell". A bot that missed one alert can still converge to the
  right position on the next one.

## Pine snippet: confirmed-bar JSON alert

```pine
//@version=6
indicator("EMA cross alert", overlay = true)
secret = input.string("", "Webhook secret")
fast = ta.ema(close, 20)
slow = ta.ema(close, 50)
longSig = ta.crossover(fast, slow)
if longSig and barstate.isconfirmed
    msg = '{"secret":"' + secret + '","symbol":"' + syminfo.tickerid +
          '","action":"buy","price":' + str.tostring(close) +
          ',"timenow":"' + str.format_time(timenow, "yyyy-MM-dd'T'HH:mm:ss'Z'", "UTC") + '"}'
    alert(msg, alert.freq_once_per_bar_close)
```

The snippet compiles on TradingView's Pine v6 compiler.

Where the secret lives depends on the alert type:

- **`alert()`**: the message comes entirely from Pine, and the dialog has no
  message field for it. Read the secret from an `input.string` and set it in
  the indicator's settings before creating the alert; the alert keeps a
  snapshot of the inputs. Never hard-code it in source, and do not share the
  chart layout (it carries the inputs).
- **`alertcondition()` and strategy order fills**: put the secret in the
  alert dialog's message, for example
  `{"secret":"...","timenow":"{{timenow}}","order":{{strategy.order.alert_message}}}`
  with each `alert_message` itself a JSON object without a secret.

## Operating alerts

- Each plan has a cap on active alerts (technical alerts: 0 on Basic, 20 on
  Essential, 100 on Plus, 400 on Premium, 1,000 on Ultimate in November 2026),
  and webhooks need a paid plan with two-factor authentication.
- Alerts expire (2 months as standard; open-ended on Premium and Ultimate) and
  all are disabled when the subscription ends. Note the expiry date and
  monitor for silence.
- If more than 15 alerts trigger within three minutes, TradingView halts the
  alert. Throttle in Pine or use once per bar close.
- Keep a test alert on a 1-minute chart pointed at a staging receiver; it is
  the cheapest end-to-end check after any change.
