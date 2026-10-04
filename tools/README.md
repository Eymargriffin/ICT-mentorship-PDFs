# Liquidity Engine backtest lab (Python)

A Python replica of the Silver Bullet model in `LiquidityEngine_P4.pine`, plus the studies behind
`docs/LE_Backtest_Results.md`.  It is **not** bar-for-bar identical to TradingView: different data feed, 15m bars,
no Liquidity-Engine breaker / order-block / iFVG entries (only the Silver Bullet FVG entry), HTF POIs from
resampled candles.

## Data
`git clone --depth 1 --filter=blob:none https://github.com/ejtraderLabs/historical-data` then check out
`XAUUSD/XAUUSDm15.csv`, `EURUSD/EURUSDm15.csv`, `GBPUSD/GBPUSDm15.csv`, `USDJPY/USDJPYm15.csv`
(MT5 server time = New York + 7 h; prices are scaled ×100 / ×1e5 / ×1e3, one unit = one tick).
Set `ROOT` in `le_run.py`.  To test US100 or anything else, drop in a CSV with `Date,open,high,low,close,tick_volume`
(server time = NY + 7 h) and add the symbol to `COST`.

## Files
* `le_data.py`   loader, ATR, HTF candles, bias / order-flow / POI series, 1H & 4H resampling, null-data generator
* `le_engine.py` swings, key levels, raid → MSS state machine, FVG inventory, decision score, Silver Bullet plan, fills
* `le_run.py`    summaries; `python3 le_run.py XAUUSD 40000`
* `le_lab.py`    cached runs and result tables;  `exp1.py` = the Silver Bullet variant grid
* `turtle.py`    turtle-soup study: trade the raid itself at 15m / 1H / 4H
