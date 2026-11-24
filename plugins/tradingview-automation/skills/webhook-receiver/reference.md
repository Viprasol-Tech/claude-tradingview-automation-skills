# Sources (checked November 2026)

- Webhook alerts (POST body, Content-Type, 2FA, source IPs, IPv6, 3-second timeout): https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/
- Ports 80 and 443 only: https://www.tradingview.com/support/solutions/43000529314-i-cannot-send-webhook-to-a-url-with-a-port-number/
- Webhooks for paid plans (launch post): https://www.tradingview.com/blog/en/webhooks-for-alerts-now-available-14054/
- Plans: https://www.tradingview.com/pricing/

Not documented by TradingView: whether failed webhooks are retried. Assume
they are not, and watch the alert log's "Webhook status" column.

The source IP list has changed before. If alerts suddenly get `403` from the
allow-list, compare the rejected address with the current list on the
webhook page before widening the allow-list.
