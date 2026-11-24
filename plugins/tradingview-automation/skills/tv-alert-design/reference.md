# Sources (checked November 2026)

- Placeholders in alert messages: https://www.tradingview.com/support/solutions/43000531021-how-to-use-a-variable-value-in-alert/
- Strategy alerts and `{{strategy.*}}` placeholders: https://www.tradingview.com/support/solutions/43000481368-strategy-alerts/
- Pine alerts concepts (`alert()`, `alertcondition()`, frequencies): https://www.tradingview.com/pine-script-docs/concepts/alerts/
- Pine alerts FAQ (`alert()` does not process placeholders): https://www.tradingview.com/pine-script-docs/faq/alerts/
- Configuring alerts and frequencies: https://www.tradingview.com/support/solutions/43000763312-learn-how-to-configure-alerts/
- Frequency differences: https://www.tradingview.com/support/solutions/43000474415-differences-between-alert-frequencies/
- Alert introduction and expiry: https://www.tradingview.com/support/solutions/43000520149-introduction-to-tradingview-alerts/
- Open-ended alerts: https://www.tradingview.com/support/solutions/43000688759-i-upgraded-to-the-premium-plan-but-my-alerts-still-expiring-in-2-months/
- Active alert counts: https://www.tradingview.com/support/solutions/43000690941-how-to-get-more-active-alerts-per-subscription/ and https://www.tradingview.com/pricing/

## Placeholder list used by the linter

Text: `ticker`, `exchange`, `interval`, `time`, `timenow`, `syminfo.currency`,
`syminfo.basecurrency`, `strategy.order.action`, `strategy.order.id`,
`strategy.order.comment`, `strategy.market_position`,
`strategy.prev_market_position`.

Numeric: `open`, `high`, `low`, `close`, `volume`, `strategy.position_size`,
`strategy.order.contracts`, `strategy.order.price`,
`strategy.market_position_size`, `strategy.prev_market_position_size`,
`plot_0` to `plot_19`, `plot("Name")`.

Raw: `strategy.order.alert_message`.

The labels of the frequency options differ between TradingView's own pages
("Once per bar close" vs. "once per bar close"); the behaviour is what matters.
Plan limits change; check the pricing page before quoting them to a client.
