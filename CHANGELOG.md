# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-24

### Added
- `tradingview-automation` Claude Code plugin with 6 skills: `tv-alert-design`,
  `webhook-receiver`, `signal-to-order`, `indian-broker-apis`,
  `crypto-mt5-bridges`, `tradingview-charts`.
- `tv_alert_lint.py`: renders an alert message with sample placeholder values
  and reports invalid JSON, unquoted text placeholders, NaN plots, unknown
  placeholders and missing secrets.
- `tv_webhook_server.py`: standard-library reference receiver with IP
  allow-list, body secret, schema, staleness and duplicate checks and a
  JSON-lines queue.
- `nse_symbols.py`: NSE Tuesday expiries with holiday roll-back, and exact
  contract resolution from a broker instrument dump for `NIFTY1!` and
  TradingView option tickers.
- Facts checked against TradingView, SEBI, NSE, Zerodha, Angel One, Dhan,
  Upstox and MetaQuotes documentation in November 2026.
