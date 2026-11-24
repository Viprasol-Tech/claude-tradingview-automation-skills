# Security policy

## Reporting a vulnerability

Please report security problems privately through
[GitHub security advisories](https://github.com/Viprasol-Tech/claude-tradingview-automation-skills/security/advisories/new)
or by email to [support@viprasol.com](mailto:support@viprasol.com). Do not open a public issue.
We aim to reply within 3 working days.

## Scope

- The bundled scripts. `tv_alert_lint.py` and `nse_symbols.py` read local
  files or arguments and make no network calls. `tv_webhook_server.py` is a
  reference HTTP receiver: it binds to 127.0.0.1 by default, never places
  orders, never logs request bodies, and runs no shell commands. Bypasses of
  its secret, IP, size, staleness or duplicate checks are in scope.
- Skill instructions that could lead an assistant to weaken account safety:
  unauthenticated webhooks, withdrawal-enabled keys, unbounded retries,
  missing stops or risk limits.

## Keep secrets out of chats

These skills never need your keys or funds. Never paste broker or exchange API keys,
access tokens, webhook secrets or TOTP seeds into an issue, pull request or
chat. Use synthetic data and sandbox keys. If a key has been
exposed, rotate it with your provider immediately.
