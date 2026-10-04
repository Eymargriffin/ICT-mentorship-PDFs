# Measured results — 10 years, gold and three FX majors

**Short version: on this data the raid / MSS / Silver Bullet rules show a small real structure (about +0.05 R per trade
better than random candles) and no tradable edge after costs. The extra filters from the ICT PDFs did not change that.**

## What was tested

* **Data:** `ejtraderLabs/historical-data`, 15-minute candles, XAUUSD, EURUSD, GBPUSD, USDJPY, 2012–2022
  (230,400 bars each). Not US100. Broker server time = New York + 7 h (checked against the daily break and the
  Sunday reopen). 1H and 4H candles are built from the 15m bars.
* **Engine:** a Python replica of the Pine Silver Bullet model (`tools/`). Same order of operations bar by bar, only
  closed candles, HTF values from the previous closed HTF candle. It is **not** the Pine code: no breaker / order-block /
  iFVG entries, a different data feed, 15m bars (Silver Bullet is meant for 1m–5m).
* **Costs:** round trip 35 ticks gold ($0.35), 12 ticks EURUSD / USDJPY (1.2 pip), 15 ticks GBPUSD. Gross = no cost.
* **Split:** in-sample 2012–2017, out-of-sample 2018–2022. Parameters were not tuned; the Pine defaults were run as they are.
* **Null test:** the same engine on candles whose direction is flipped at random (shape and time stamps kept). Any
  "edge" found there is an artifact of the simulator.

## Results

### Silver Bullet, four instruments pooled (n = trades)

| Variant | n | win % | avg R gross | avg R net | PF net |
|---|---:|---:|---:|---:|---:|
| As in Pine (open filter, key liquidity, score ≥ 3, MSS) | 42 | 35.7 | +0.117 | **+0.059** | 1.11 |
| Filters off | 154 | 29.9 | +0.029 | −0.024 | 0.95 |
| Filters off, no MSS, no displacement | 690 | 27.5 | −0.023 | −0.087 | 0.84 |
| …plus NY 08:30–11:00 window | 1,757 | 29.5 | +0.032 | −0.040 | 0.93 |

The Pine defaults: 20 trades in-sample (+0.091 R net), 22 out-of-sample (+0.031 R). That is about four trades a year across
four instruments, far below three or four a week, and 42 trades cannot be told apart from zero.

### Does any decision-score component predict the outcome? No.

3,711 simulated trades (wide windows, filters off), grouped by each component, in-sample versus out-of-sample:
daily bias, weekly bias, 1H and 4H order flow, midnight-open side, premium / discount, key liquidity, HTF-array
engagement, ★ backing, session, direction, weekday, R:R, stop size, total score. No component keeps the same sign and
size in both halves. Where a pattern shows up in one half, it flips in the other (for example the 02:00 hour is
−0.64 R in-sample and +0.63 R out-of-sample). The midnight-open filter the header calls the one that "held up" did
**not** help here: the wrong side did slightly better in both halves (small sample).

### Where the (small) structure is

| Event | n | forward move in the reversal direction |
|---|---:|---|
| Raid reclaimed (close back inside the swept level) | 33,619 | **+0.063 ATR after 16 bars** (t = 3.4); +0.051 after 32 (t = 1.8); +0.024 after 64 |
| …after the MSS is also confirmed | 10,932 | −0.03 … +0.09 ATR, every horizon within ±1.6 t — nothing |

The reversal after a stop run is real but small, and it is over by the time the MSS and the FVG retest are confirmed.
The MSS rule therefore adds latency, not information.

### Trading the raid itself ("turtle soup": enter after the reclaim, stop beyond the extreme, 2 R, one trade at a time)

| Timeframe | trades | avg R gross | avg R net of costs | same rules on random candles (net) |
|---|---:|---:|---:|---:|
| 15m | 26,155 | ≈ +0.05 vs random | −0.148 | −0.197 |
| 1H | 8,213 | +0.023 | −0.065 | — |
| 4H | 2,681 | +0.020 | −0.028 | — |

Real data beat the random-candle null by about 0.05 R per trade at 15m (very significant over 26k trades) and by about
the same margin on Silver Bullet (−0.04 vs −0.10 R). Costs are 0.10–0.20 R on 15m and shrink with the timeframe,
because the stop is wider; at 4H the result is about breakeven. Filtering by level type, daily / weekly bias, 1H order
flow or killzone gave no sub-group that is positive in both halves.

## What this means

1. **More filters do not create an edge that the core signal lacks.** The PDF rules (HTF engagement, session-matched
   levels, tighter stops) were added; none of the measurable components predicts anything in this data.
2. **Costs decide the outcome.** The raid effect is worth about +0.05 R before costs. On 15m, gold and FX costs are 2–4
   times that. The same idea gets closer to breakeven on 1H–4H with wide stops.
3. **Frequency.** Three or four trades a week through the Silver Bullet window is not available from these rules on
   15m bars; where frequency was raised, expectancy fell below zero.
4. **Not tested:** US100 / NQ; 1m–5m bars (where the Silver Bullet lives); the Liquidity Engine breaker / iFVG / order-block
   entries; news-day exclusions; ICT's discretionary multi-timeframe reading, which candles alone do not capture.

## Caveats

* t-statistics on overlapping events are inflated; the many slices scanned give some false positives by chance, which is
  why only slices with the same sign in both halves were treated as candidates.
* Events were simulated with conservative same-candle ordering (stop before target, fills need a trade-through).
* The Python replica can differ from TradingView in small ways. Treat the numbers as evidence about the idea, not as a
  statement about the exact indicator on your chart.

## Reproduce

See `tools/README.md`. `python3 tools/exp1.py` (variant grid), `python3 tools/turtle.py` (turtle-soup study).

---

# Do the swing and PD-array building blocks behave as ICT says? (second study)

Same data and replica, now testing the pieces the script is built from, each against random candles (direction of every
candle flipped at random, two seeds). A building block is "solid" if it behaves differently from random candles in the
direction ICT claims.

## Swings and raids

Drift after a raid is reclaimed (move in the reversal direction after 16 bars, ATR units; about 33k events):

| Setting | events | mean drift | t |
|---|---:|---:|---:|
| Defaults (pivot N=2, min excursion 1 ATR) | 33,618 | +0.063 | 3.4 |
| min excursion 0 / 0.5 / 2 ATR | 36,047 / 35,934 / 27,142 | +0.052 / +0.052 / +0.060 | 2.9 / 2.9 / 2.9 |
| pivot N = 1 / 3 / 5 | 37,066 / 30,798 / 26,807 | +0.051 / +0.056 / +0.049 | 2.9 / 2.9 / 2.4 |
| equal highs-lows rule off | 33,517 | +0.066 | 3.6 |
| key levels start raids off | 32,970 | +0.066 | 3.5 |

* The swing detector's parameters hardly matter: every setting gives the same small reversal drift. None is better than the defaults.
* **Strong vs weak swings:** sweeps of *strong* swings reverse at least as well (+0.074 ATR, n = 27,364) as sweeps of *weak* ones
  (+0.012, n = 6,254; not significantly different). The script's "weak = liquidity, strong = protected" idea has no support here,
  and the "Weak only" raid option would throw away most events.
* Raids of swings that had run 1–2.5 ATR away before being swept reverse a little more (+0.09–0.11) than those under 1 ATR (+0.05).

## PD arrays: first tap of a zone

For each zone, the first time price returns into it. Success = price rises 1 ATR beyond the zone (mirror for bearish) before a
candle CLOSES through the invalidation line, within 48 bars. Real vs random candles, same zone depth:

| Array | first taps (real) | success real | success random | difference | 16-bar drift real / random (ATR) |
|---|---:|---:|---:|---:|---|
| Order block | 95,873 | 60.5 % | 58.2 % | **+2.3 pts** | −0.065 / +0.004 |
| Breaker | 76,192 | 56.2 % | 54.7 % | **+1.5 pts** | −0.016 / +0.032 |
| FVG | 87,680 | 59.6 % | 58.7 % | +0.9 pts | +0.042 / +0.003 |
| iFVG (inverted FVG) | 107,429 | 51.8 % | 53.2 % | **−1.4 pts** | +0.005 / +0.012 |

* Order blocks and breakers are respected slightly more than random levels (large samples, so the difference is real),
  FVGs barely, **inverted FVGs not at all** — they do slightly worse than random.
* Most of the "success" rate is geometry (how deep the invalidation line is), not the array: it runs from 48 % for shallow
  zones to 85–90 % for deep ones in both real and random data.
* The edge is a couple of percentage points; at a 0.6 ATR stop and a 1 ATR target that is about +0.03 to +0.04 R per trade
  before costs.

## The OTE / premium-discount idea

After a displacement leg, how often does price make a new extreme (rather than closing back through the raid extreme)
once it has retraced to a given depth?

| Retracement depth reached | real data | random candles |
|---|---:|---:|
| 21 % | 83.7 % | 83.0 / 83.3 % |
| 38 % | 72.1 % | 71.5 / 71.6 % |
| 50 % (equilibrium) | 61.8 % | 61.3 / 61.9 % |
| **62 %** (start of OTE) | **50.4 %** | 50.4 / 50.4 % |
| **79 %** (end of OTE) | **35.5 %** | 35.3 / 34.9 % |
| 90 % | 26.8 % | 26.7 / 25.9 % |

(81,303 legs on real data, about 104,000 on each random set.) Real candles and random candles are indistinguishable at every
depth, including the 62–79 % band. **The 62–79 % zone is not special in this data**: there is no extra bounce there.
In the script, requiring the entry array to sit inside the OTE therefore cuts the number of trades without improving them.

## What this says about the script's logic

| Block | Verdict from the data |
|---|---|
| Pivot swings, significance, equal-level rule | Fine, but not sensitive: any sensible setting gives the same weak signal. |
| Strong / weak grading | No support; weak swings are not the better liquidity. |
| Raid → reclaim | Real but small (+0.06 ATR after 16 bars). |
| MSS + displacement | Adds no information after the reclaim (see the first study). |
| Order block, breaker | Small genuine reaction (+1.5 to +2.3 points over random). |
| FVG | Barely distinguishable from random. |
| iFVG | No reaction; slightly worse than random. |
| OTE 62–79 % / premium-discount | No effect. |
