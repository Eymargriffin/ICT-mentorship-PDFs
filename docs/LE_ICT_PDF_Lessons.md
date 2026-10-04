# What the ICT PDFs say, and what the engine does about it

Source: the study PDFs in `Eymargriffin/database` (119 files; about 60 have extractable text, the rest are image-only
Notion exports and slide decks). Read: Silver Bullet, Timeframe Alignment (Silky, OTE Trader), Stacked PD Arrays,
Intraday / Daily Bias (TTrades), Daily Profile Guide vol. 1–3, Weekly Profiles, High-Probability Conditions,
Candle Body Closures, MSS vs CISD, MSS vs Liquidity Grab, Unicorn, Venom, Macro, Judas Swing, Turtle Soup, IPDA,
Position Sizing, the ICT 2024 Mentorship lecture notes, and the RektProof Breaker and Range/MSB lessons.

## Rules the notes agree on

| Rule | Where | In the engine |
|---|---|---|
| HTF decides, LTF only executes: 1D → 1H → 5m, or 1W → 4H → 15m. "HTF key level → LTF MMXM". | Silky, OTE Trader | Decision gate; **new:** `HTF PD array engaged` (the raid extreme sits inside a same-direction HTF POI) is a scored component and an optional gate |
| A reversal "lacking ≥ H1 PDA engagement" is an unfavourable profile. | Daily Profile Guide, negative condition | Same — `Raid must engage an HTF PD array` |
| Raids are of external liquidity: PDH / PDL, session highs and lows, relative equal highs / lows. Internal consolidation is low probability. | High-Probability Conditions, 2024 lectures 1–2 | **New:** key levels start raids on their own (`Key levels start raids`); equal highs / lows count as liquidity at once (`eqSig`) |
| Silver Bullet frame: the previous hourly candle's high / low (the 09:00 candle) frames the 10:00–11:00 reversal. | TTrades Silver Bullet, Intraday Bias | **New:** prior-hour H/L captured at the window start, a raid level and a target |
| Venom / pre-market: the 08:00–09:30 range is the reference; after 09:30 price runs one side, then reverses. | Venom Model | **New:** `Pre-market range` level (raid and target) |
| Silver Bullet zones: 03:00–04:00, 10:00–11:00, 14:00–15:00 NY. | Macro PDF | **New:** optional second window |
| MSS = displacement with full-bodied candles through structure (+ FVG); a failure to displace is a liquidity grab. A stop raid before the MSS is preferred. | MSS vs Liquidity Grab | Already how `f_energy` works |
| Minimum target: about 15 handles on NQ, 5 on ES — it does not have to reach the final draw. | 2024 lecture 10 | `Min target distance (× ATR)` |
| Stop just beyond the array (breaker high + 2 points); precise stops from the BPR / OB on the 1m. | 2024 lecture 2, 12 | **New:** `Stop beyond: Entry array` (engine) and `FVG candles` (Silver Bullet) |
| Take partials at each short-term high and **do not move the stop** ("running down equity"). | 2024 lecture 13 | **Changed:** breakeven after TP1 is now off by default |
| CPI / NFP / FOMC mornings are not tradeable; best setups come after, at the 10:00 Silver Bullet. | 2024 lectures 1, 7; High-Probability | **New:** stand-aside date list (Pine has no news calendar) |
| Mondays are skipped except on NFP week; Tue–Thu carries the clean expansion; Friday retraces 20–30%. | Weekly Profiles, 2024 lecture 6 | `Trading days` filter (unchanged, default any day) |
| Best breaker entry: an iFVG or FVG overlapping the breaker (Unicorn). The first FVG before the stop hunt, once inverted, is the change in state of delivery. | Unicorn, Hydra, 2024 lecture 2 | Already grade A+ and the iFVG logic |
| Range trades: two swing points define the range; sweep one edge, MSB, enter at the S/D that led to the break, **take profit at the untapped opposite side of the range**. | RektProof lesson 7 | Target is the nearest untaken liquidity (`f_sbTarget`) |
| No trade when both a bullish and a bearish story are easy to paint. | 2024 lecture 7 | Not automated; the decision gate's veto is the closest thing |

## Not used (and why)

* **NDOG / NWOG and the opening-range gap** (a strong draw on liquidity in the 2024 lectures): needs session-gap
  tracking; not built. Next candidate.
* **Weekly profile by day of week and the news calendar:** cannot be derived from candles alone.
* **Position sizing / partial rules:** `Account size`, `Risk %` and `Partial at TP1` already follow the notes.
* **TPO profiling, supply and demand chapters:** image-only PDFs, not read.

None of these rules has been tested on price data in this repository; the data sources a backtest needs
(Dukascopy, Yahoo, Binance) were blocked in the session that wrote this.
