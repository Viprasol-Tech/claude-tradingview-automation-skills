# Sources (checked November 2026)

- `WebRequest()`: https://www.mql5.com/en/docs/network/webrequest
- `SocketCreate()` and the network functions: https://www.mql5.com/en/docs/network/socketcreate
- Python `MetaTrader5` package (Windows x64 wheels, Python 3.6-3.14): https://pypi.org/project/MetaTrader5/
- `order_send` in Python: https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py
- Trade server return codes: https://www.mql5.com/en/docs/constants/errorswarnings/enum_trade_return_codes
- Exchange signing and precision: see claude-crypto-bot-skills
  (`exchange-api-auth`, `order-precision`) for the per-exchange sources.

MetaQuotes does not document broker symbol suffixes; they are set by each
broker. Resolve them at runtime as described in the skill.
