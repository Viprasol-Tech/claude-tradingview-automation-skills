---
name: tradingview-charts
description: Put TradingView charts in your own app correctly - Lightweight Charts v5 (Apache-2.0; addSeries(CandlestickSeries), setData vs update, UTCTimestamp in seconds, no time-zone support, createSeriesMarkers, panes, autoSize, the required TradingView attribution) and the Advanced Charts / Charting Library Datafeed API (onReady, resolveSymbol, getBars, subscribeBars, millisecond bar times vs second ranges, noData, LibrarySymbolInfo session/timezone/pricescale, the UDF adapter). Use when building a trading dashboard or broker front end with TradingView charts, migrating Lightweight Charts v4 to v5, or debugging shifted, missing, duplicated or frozen bars.
---

# TradingView charts in your own app

Two libraries, very different terms. Facts checked November 2026 against the
official docs (links in `reference.md`).

| | Lightweight Charts | Advanced Charts (Charting Library) |
|---|---|---|
| Licence | Apache-2.0, open source on GitHub | free only with visible TradingView attribution, in a public (not private, not paywalled) product; obtained from TradingView, not npm |
| Scope | fast canvas charts: candles, lines, areas, histograms, markers, panes | the full TradingView chart: drawing tools, 100+ indicators, layouts |
| Data | you push arrays | you implement the Datafeed API (or the UDF HTTP adapter) |
| Trading UI | none | none; order ticket, DOM and account manager are in the separate **Trading Platform** product (commercial) |

## Lightweight Charts v5

```js
import { createChart, CandlestickSeries, HistogramSeries, createSeriesMarkers } from 'lightweight-charts';

const chart = createChart(document.getElementById('chart'), {
  autoSize: true,                       // follows the container via ResizeObserver
  layout: { attributionLogo: true },    // keeps the required TradingView link on the chart
});
const candles = chart.addSeries(CandlestickSeries, { upColor: '#26a69a', downColor: '#ef5350' });
const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' } }, 1); // pane 1

candles.setData(history);              // once: ascending time, no duplicates
socket.onmessage = (e) => candles.update(toBar(JSON.parse(e.data))); // live: same time = replace, newer = append
const markers = createSeriesMarkers(candles, [{ time: t, position: 'belowBar', shape: 'arrowUp', color: '#26a69a', text: 'BUY' }]);
chart.timeScale().fitContent();
```

Rules that cause most bugs:

- **Time is UTC seconds** (`UTCTimestamp`), or a `'YYYY-MM-DD'` string, or
  `{year, month, day}`. Passing milliseconds puts bars in the year 50000.
- **No time-zone support.** The chart shows UTC. To show IST, add
  `19800` seconds to each intraday timestamp before passing it (do not shift
  daily business-day data).
- **Ascending order, unique times.** `setData` throws or draws garbage
  otherwise; sort and de-duplicate server output first.
- **`update()` for live ticks**, not `setData()` (which re-processes the whole
  array). `update` can only change the last bar or append a newer one.
- A series cannot change type; remove it and add a new one.
- v4 to v5: `addCandlestickSeries(o)` becomes `addSeries(CandlestickSeries, o)`;
  `series.setMarkers()` becomes `createSeriesMarkers(series, markers)`; the
  `watermark` option becomes `createTextWatermark(pane, {lines})`; CommonJS
  builds are gone (ES2020 ESM, plus the standalone UMD build exposing
  `LightweightCharts.*`).
- **Attribution is a licence condition**: keep `attributionLogo`, or add the
  NOTICE text and a link to tradingview.com on a public page of your app.
- Call `chart.remove()` when the component unmounts (React `useEffect`
  cleanup), or every re-render leaks a canvas.

## Advanced Charts Datafeed API

```js
const datafeed = {
  onReady: (cb) => setTimeout(() => cb({ supported_resolutions: ['1', '5', '15', '60', '1D'] })),
  searchSymbols: (input, exchange, type, onResult) => onResult(search(input)),
  resolveSymbol: (name, onResolved, onError) => setTimeout(() => onResolved({
    name: 'RELIANCE', ticker: 'NSE:RELIANCE', description: 'Reliance Industries', type: 'stock',
    exchange: 'NSE', listed_exchange: 'NSE', timezone: 'Asia/Kolkata', session: '0915-1530',
    minmov: 10, pricescale: 100,                 // tick = minmov / pricescale = 0.10; use the exchange's current tick size
    has_intraday: true, supported_resolutions: ['1', '5', '15', '60', '1D'], volume_precision: 0,
    data_status: 'streaming',
  })),
  getBars: async (symbolInfo, resolution, { from, to, countBack, firstDataRequest }, onHistory, onError) => {
    const bars = await fetchBars(symbolInfo.ticker, resolution, from, to, countBack); // from/to in SECONDS
    onHistory(bars.map(b => ({ time: b.t * 1000, open: b.o, high: b.h, low: b.l, close: b.c, volume: b.v })),
              { noData: bars.length === 0 });   // bar time in MILLISECONDS
  },
  subscribeBars: (symbolInfo, resolution, onTick, guid) => live.subscribe(guid, symbolInfo, resolution, onTick),
  unsubscribeBars: (guid) => live.unsubscribe(guid),
};
```

Rules:

- **Bar `time` is milliseconds; `from`/`to` are seconds.** `from` is inclusive,
  `to` exclusive, and `countBack` wins over the range: return at least that
  many bars ending before `to` when you have them.
- Daily and higher bars use 00:00 UTC of the trading day.
- Bars ascending, at least 2 when data exists; return `noData: true` when there
  is no older history (optionally `nextTime` in ms), or the chart keeps asking.
- `subscribeBars` updates only the latest bar or appends a new one; send full
  OHLCV each time. To fix history, call `resetCache()` then
  `chart.resetData()`.
- Call callbacks asynchronously (`setTimeout`); calling them synchronously
  inside the same request can cause "Maximum call stack size exceeded".
- `unsubscribeBars` arrives a few seconds after a symbol or resolution change;
  do not assume it is immediate.
- **Symbol info**: `timezone` is an IANA name (`Asia/Kolkata`,
  `America/New_York`, `Etc/UTC` for forex and crypto); `session` like
  `0915-1530`, `24x7`, or several sessions comma-separated with day suffixes
  (`:23456`, 1 = Sunday). A wrong timezone or session shifts or hides bars.
  `pricescale = 10^decimals`.
- The **UDF adapter** (`Datafeeds.UDFCompatibleDatafeed`) speaks HTTP JSON
  (`/config`, `/symbols`, `/search`, `/history`, `/time`). `/history` returns
  `{s, t, o, h, l, c, v}` with times in **seconds**. It has no streaming; write
  a custom datafeed for real-time data.

## Choosing

- A bot dashboard, a P&L chart, a signal overlay: **Lightweight Charts**.
- A public broker or exchange front end where users draw and add indicators:
  **Advanced Charts**, after checking the licence fits (public, attributed).
- Order entry from the chart: Trading Platform licence, or Lightweight Charts
  with your own order ticket.
