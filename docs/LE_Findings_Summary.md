# Liquidity Engine — findings in one page

Data: 10 years of 15-minute candles (gold, EURUSD, GBPUSD, USDJPY, 2012–2022), Python replica of the script. Not US100,
not 1m–5m, not bar-for-bar identical to TradingView. Details and tables: `LE_Backtest_Results.md`. The ICT rules the
script was checked against: `LE_ICT_PDF_Lessons.md`. Code: `tools/`.

## Bottom line
No tradable edge after costs. The rules show a small real structure (about +0.05 R per trade better than random candles),
smaller than 15m trading costs. About breakeven on 4H.

## Measured
* Raid reclaimed → price drifts +0.06 ATR in the reversal direction over 16 bars (t = 3.4, 33,619 events).
* After the MSS is confirmed → no drift (within ±1.6 t at every horizon, 10,932 events). The MSS rule adds delay, not information.
* Silver Bullet as in the Pine defaults: 42 trades in 10 years across four instruments, +0.06 R net — not distinguishable
  from zero, and about four trades a year instead of three or four a week.
* Loosening the rules for more trades: −0.04 to −0.09 R per trade.
* Decision-score components (daily / weekly bias, 1H / 4H order flow, midnight open, premium-discount, key liquidity,
  HTF-array engagement, session, weekday): none keeps its pattern in both 2012–2017 and 2018–2022.
* OTE 62–79 % and premium / discount: no effect. After a retracement to any depth, the chance the leg continues is the same
  on real and random candles (50.4 % vs 50.4 % at 62 %).
* PD arrays, first touch vs random candles: order block +2.3 points, breaker +1.5, FVG +0.9, inverted FVG −1.4. Requiring the
  order block to follow a liquidity run: +1.5 points.
* Swings: pivot size, excursion threshold and the equal-level rule do not matter; strong swings reverse at least as well as weak.

## Code defects found and fixed
Silver Bullet judged only the first FVG per raid; an MSS candle that also swept deeper liquidity was discarded; breakeven
used the planned entry instead of the fill; FVG volume could evict breakers / order blocks; the midnight-open filter used
a stale reference.

## What the ICT PDFs add
ICT's own framing: a "couple of trades a week", stops just beyond the array, partials without moving the stop, no
CPI / NFP / FOMC mornings, breaker = up-close candle at the high between two lows. The script's arrays were moved closer to
this (order-block mean threshold, order blocks and FVGs as entries, CE for gaps, first-touch only). Effect on results:
small; only the order-block changes were measured.

## Not done
US100 / NQ and 1m–5m data; the Liquidity Engine breaker / order-block entries as full backtests; the six latest array
changes as full trade results; compiling the Pine in TradingView (the TradingView MCP host is blocked in this environment).

## What could still give better results
Test on US100 or tick-level data; trade only wide-stop higher-timeframe versions where costs are a small share of the
risk; or use the script as a marking tool alongside discretionary judgement.
