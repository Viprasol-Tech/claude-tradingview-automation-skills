# Sources (checked November 2026)

## SEBI and NSE

- SEBI circular, 4 Feb 2025, "Safer participation of retail investors in algorithmic trading": https://www.sebi.gov.in/legal/circulars/feb-2025/safer-participation-of-retail-investors-in-algorithmic-trading_91614.html
- Timeline extension to full applicability from 1 Apr 2026 (30 Sep 2025): https://www.sebi.gov.in/legal/circulars/sep-2025/extension-of-timeline-for-implementation-of-sebi-circular-dated-february-04-2025-on-safer-participation-of-retail-investors-in-algorithmic-trading-_96979.html
- NSE retail algo FAQ: https://nsearchives.nseindia.com/web/sites/default/files/inline-files/FAQ_Retail_Algo_03112025_NSE.pdf
- NSE implementation standards explained by Zerodha: https://zerodha.com/z-connect/general/a-comprehensive-overview-of-nses-circular-on-the-new-retail-algo-trading-framework
- NIFTY contract specifications and Tuesday expiry: https://www.nseindia.com/static/products-services/equity-derivatives-nifty50
- Lot size revision (NSE/FAOP/70616): https://zerodha.com/marketintel/bulletin/429705/revision-in-lot-size-of-index-derivative-contracts-from-december-30-2025

## Brokers

- Kite Connect login flow: https://kite.trade/docs/connect/v3/user/
- Kite orders: https://kite.trade/docs/connect/v3/orders/
- Kite rate limits: https://kite.trade/docs/connect/v3/exceptions/
- Kite instruments and quotes: https://kite.trade/docs/connect/v3/market-quotes/
- Kite WebSocket: https://kite.trade/docs/connect/v3/websocket/
- Kite plans FAQ: https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/kite-connect-api-faqs
- Zerodha static IP: https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/static-ip
- Angel One SmartAPI Python SDK: https://github.com/angel-one/smartapi-python
- Angel One SmartAPI changes from 1 Apr 2026: https://www.angelone.in/news/market-updates/what-s-changing-in-angel-one-s-smartapi-access-from-april-1-2026
- Dhan v2: https://dhanhq.co/docs/v2/ and https://dhanhq.co/docs/v2/authentication/
- Upstox authentication: https://upstox.com/developer/api-documentation/authentication/
- Upstox v3 place order: https://upstox.com/developer/api-documentation/v3/place-order/
- Upstox rate limits: https://upstox.com/developer/api-documentation/rate-limiting/
- Upstox static IP APIs: https://upstox.com/developer/api-documentation/announcements/static-ip-apis/
- Fyers on the April 2026 rules: https://support.fyers.in/portal/en/kb/articles/what-are-the-new-sebi-rules-for-retail-algo-trading-from-april-01-2026
- TradingView NSE option ticker format: https://in.tradingview.com/support/solutions/43000480528

## Not confirmed from primary text

- Exact SEBI milestone dates before April 2026 and the black-box and white-box
  definitions (taken from broker summaries; the circular PDFs could not be
  text-extracted).
- Angel One's full enum lists and official rate-limit table; Dhan segment
  enums and index security IDs; Upstox instrument-key formats for equities
  and indices.
- Current NSE freeze quantities and any lot-size revision after the January
  2026 contracts. Read both at runtime from the exchange and broker files.
- Whether an exchange iceberg order counts as one order or as each slice towards the 10 orders/second threshold (Zerodha forum replies say one; not confirmed in the circular).
