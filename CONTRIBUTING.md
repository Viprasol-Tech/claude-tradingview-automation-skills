# Contributing

Thanks for helping traders automate TradingView without losing money to bugs. Fixes, new skills, better
checklists and corrections are all welcome.

## Ways to help

- **Fix a fact.** TradingView, broker APIs and SEBI rules change often (placeholders, IPs, limits, login flows). If a rule, limit
  or header is out of date, open a PR with a link to the official source.
- **Improve a skill.** Each skill is a folder in `plugins/tradingview-automation/skills/`
  with a `SKILL.md` (YAML frontmatter `name` + `description`, then instructions).
- **Add a skill.** Same layout. Keep `SKILL.md` under 500 lines; put long
  reference material in a separate file linked from it.
- **Improve the scripts** in `tv-alert-design/scripts`, `webhook-receiver/scripts` and `indian-broker-apis/scripts`.
  They must stay standard-library only and keep their `--self-test` passing.

## Before you open a PR

```bash
python tests/validate_repo.py
python plugins/tradingview-automation/skills/tv-alert-design/scripts/tv_alert_lint.py --self-test
python plugins/tradingview-automation/skills/webhook-receiver/scripts/tv_webhook_server.py --self-test
python plugins/tradingview-automation/skills/indian-broker-apis/scripts/nse_symbols.py --self-test
```

Code samples must run as written and use sandbox or paper accounts only; never
real API keys, access tokens, webhook secrets or client IDs.

## Ground rules

- Accuracy over volume: cite official docs for platform facts.
- Regulatory content is engineering guidance, not legal or tax advice; cite SEBI, NSE or the broker's official documentation.
- Never include real API keys, account numbers or personal data.
