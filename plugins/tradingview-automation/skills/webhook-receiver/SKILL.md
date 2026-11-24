---
name: webhook-receiver
description: Build or review the server that receives TradingView webhook alerts - HTTPS on port 443, TradingView's source-IP allow-list, a shared secret inside the JSON body (TradingView cannot sign requests or set headers), payload validation, stale-alert and duplicate rejection, answering within TradingView's timeout, and handing work to a queue instead of placing orders inside the request. Includes a tested standard-library reference receiver. Use when writing a TradingView webhook endpoint in Python, Node, FastAPI, Flask, Express or a serverless function, when alerts "don't arrive", arrive twice or time out, or when securing an existing bot's webhook URL.
allowed-tools: Bash(python ${CLAUDE_SKILL_DIR}/scripts/tv_webhook_server.py *)
---

# TradingView webhook receiver

A TradingView webhook is an unauthenticated HTTP POST to a URL you typed into
an alert. Whoever learns that URL can send the same POST. Treat the endpoint
as a public, money-moving API. Facts checked November 2026; confirm in
TradingView's help centre before relying on them (see `reference.md`).

## What TradingView sends

| Property | Behaviour |
|---|---|
| Method / body | `POST`, body = the alert message after placeholder substitution |
| Content-Type | `application/json` if the body parses as JSON, otherwise `text/plain` |
| Ports | 80 and 443 only; any other port in the URL is not called |
| Source IPs | `52.89.214.238`, `34.212.75.30`, `54.218.53.128`, `52.32.178.7` (IPv4 only; IPv6 endpoints are not supported) |
| Timeout | 3 seconds; a slower response is cancelled |
| Retries | not documented: assume none, and check the "Webhook status" column in the alert log |
| Auth | none: no signature, no custom headers, no client certificate |
| Account | a paid plan (not Basic) and two-factor authentication on the account |

Consequences: the secret must travel **in the body** (TradingView's docs only
say to use a secure endpoint and never put login credentials in the message;
the body secret plus IP allow-list is this skill's design); the handler must
answer fast; and a failed delivery may be gone, so the bot must reconcile
against the broker instead of trusting that every alert arrived.

## Reference receiver

```bash
python ${CLAUDE_SKILL_DIR}/scripts/tv_webhook_server.py --self-test
TV_SECRET="$(python -c 'import secrets;print(secrets.token_urlsafe(24))')" \
  python ${CLAUDE_SKILL_DIR}/scripts/tv_webhook_server.py serve --port 8080 --queue signals.jsonl     # behind nginx/Caddy on 443
```

It checks, in order: source IP (before reading the body), Content-Length,
JSON object with no `NaN`/`Infinity`, secret (`hmac.compare_digest`),
required fields (`secret`, `symbol`, `action`, `timenow`), known action,
finite non-negative `qty`/`price`, alert age, duplicate payload; then appends
the signal to a JSON-lines queue and returns `200` immediately. Behind a
reverse proxy, pass `--trust-proxy 127.0.0.1` (the proxy's address):
`X-Forwarded-For` is honoured only from that address. It never places orders
and never logs bodies. Port it to your stack; keep the order of checks.

## Checklist for any receiver

1. **TLS on 443** through a reverse proxy (Caddy, nginx, a cloud load
   balancer). Plain HTTP on 80 sends the secret in clear text.
2. **IP allow-list** at the proxy or app. Behind a proxy, read the client IP
   from the proxy's header only when the TCP peer is your proxy; a client can
   send any `X-Forwarded-For` it likes.
3. **Secret in the body**, at least 16 random characters, compared in constant
   time, stored in an env var or secret manager. Strip it before logging or
   queueing. Rotate it if the alert text was ever shared or screenshotted.
4. **Validate the schema**: object, required fields, allowed actions, numeric
   fields parse as finite `Decimal` (Python's `json` accepts `NaN` unless you
   pass `parse_constant`), symbol on your allow-list. Reject everything else
   with `400`; never `eval` or forward raw text. Read at most a fixed number
   of bytes and reject a missing or negative `Content-Length`.
5. **Require a fresh timestamp**: include `"timenow":"{{timenow}}"`, reject
   alerts without it, and drop anything older than your strategy tolerates
   (default 120 s). `{{time}}` is the bar's open time, not the firing time.
6. **Deduplicate** on a hash of the whole payload (without the secret), kept
   for longer than the staleness window so a replay is either a duplicate or
   stale (in Redis or the database when you run more than one process). Do
   not dedupe on a bare `id`: a constant id would swallow the exit after the
   entry. Several alerts can fire on the same bar unless the alert is set
   to once per bar close, and a resent test or a second alert on the same
   condition looks identical to the first.
7. **Answer first, trade later**: enqueue and return `200` within milliseconds;
   a worker places the order (see `signal-to-order`). Broker calls take
   hundreds of milliseconds to seconds and would blow the timeout.
8. **Idempotent worker**: derive the broker's client order ID from the dedupe
   key so a replayed signal cannot open a second position.
9. **Observability**: log the decision (accepted / duplicate / rejected and
   why) with the dedupe key, never the body; alert yourself when no signal
   arrives during market hours if one was expected.
10. **Kill switch**: an env flag or database row the worker checks before
    every order.

## Hosting notes

- Serverless (AWS Lambda + API Gateway, Cloud Run, Vercel functions) works if
  cold starts stay under the timeout; keep the function tiny and push to a
  queue (SQS, Pub/Sub, a database table).
- Indian retail algo orders must come from the static IP registered with the
  broker (see `indian-broker-apis`), so the **worker** usually runs on a VPS
  with a fixed IP even when the receiver is serverless.
- Tunnels (ngrok, Cloudflare Tunnel) are fine for testing; use a stable domain
  for live alerts, because changing the URL means editing every alert.

## Testing

```bash
curl -s -X POST https://bot.example.com/tv -H 'Content-Type: application/json' \
  -d '{"secret":"...","symbol":"NSE:RELIANCE","action":"buy","qty":1,"timenow":"2026-11-24T09:15:00Z"}'
```

Send it twice (second must say duplicate), with a wrong secret (401), from a
non-TradingView IP (403), and with an old `timenow` (409). Then create a real
alert on a 1-minute chart with "Once per bar close" and watch the queue.

Lint the alert message itself with `tv-alert-design` before pasting it into
TradingView.
