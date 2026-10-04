"""Turtle-soup study: trade the liquidity raid itself (ICT 2016: sell above an old high / buy below an old low).
Entry at the open after the candle that CLOSES back inside the swept level, stop beyond the raid extreme,
target N R, time stop.  One position at a time per symbol.  Costs in ticks, as in le_run.COST."""
import sys; sys.path.insert(0, "/home/user/ICT-mentorship-PDFs/tools")
import numpy as np, pandas as pd
import le_data as D, le_engine as E, le_run as R, le_lab as L


def events_for(d, htf, atr, cfg):
    eng = E.Engine(d, cfg, atr=atr, htf=htf)
    ev = []
    orig = eng.step
    def step(s, i):
        before = s.state
        orig(s, i)
        if before == 1 and s.state == 2:
            a = eng.atr[i]
            aD, aW, aA, aB = eng.htf_al(s.bull, i)
            ev.append(dict(i=i, bull=s.bull, ext=s.ext, atr=a, liq=s.liq, aD=aD, aW=aW, aA=aA, aB=aB,
                           kz=eng.in_kz(d.min_of_day[i]), hour=d.min_of_day[i] // 60, year=d.year[i], sweep_age=i - s.sweep_bi))
    eng.step = step
    eng.run()
    return ev


def sim(d, ev, rmult, maxbars, cost, buf=0.1, tick=1.0):
    trs = []
    last_exit = -1
    for e in sorted(ev, key=lambda x: x["i"]):
        i = e["i"]
        if i <= last_exit or i + 1 >= d.n:
            continue
        bull = e["bull"]
        entry = d.O[i + 1]
        stop = e["ext"] - buf * e["atr"] if bull else e["ext"] + buf * e["atr"]
        risk = (entry - stop) if bull else (stop - entry)
        if risk <= 0 or risk > 6 * e["atr"]:
            continue
        tgt = entry + rmult * risk if bull else entry - rmult * risk
        r = None
        exit_j = None
        for j in range(i + 1, min(d.n, i + 1 + maxbars)):
            hit_stop = d.L[j] <= stop if bull else d.H[j] >= stop
            hit_tgt = d.H[j] >= tgt if bull else d.L[j] <= tgt
            if hit_stop:
                px = min(d.O[j], stop) if bull else max(d.O[j], stop)
                r = ((px - entry) if bull else (entry - px)) / risk
                exit_j = j; break
            if hit_tgt:
                px = max(d.O[j], tgt) if bull else min(d.O[j], tgt)
                r = ((px - entry) if bull else (entry - px)) / risk
                exit_j = j; break
        if r is None:
            j = min(d.n - 1, i + maxbars)
            r = ((d.C[j] - entry) if bull else (entry - d.C[j])) / risk
            exit_j = j
        r -= cost / risk
        last_exit = exit_j
        trs.append(dict(i=i, r=r, year=e["year"], bull=bull, liq=e["liq"], aA=e["aA"], aD=e["aD"], aW=e["aW"], kz=e["kz"], hour=e["hour"], risk_atr=risk / e["atr"]))
    return trs


if __name__ == "__main__":
    out = []
    for sym in ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]:
        d15, htf15, atr15 = L.get(sym)
        for tf in (15, 60, 240):
            if tf == 15:
                d, htf, atr = d15, htf15, atr15
            else:
                d = D.resample(d15, tf); atr = D.atr14(d.H, d.L, d.C); htf = None
            cfg = E.Cfg(useHTFPOI=False)
            eng0 = E.Engine(d, cfg, atr=atr, htf=htf)
            ev = events_for(d, eng0.htf, atr, cfg)
            for rm in (1.0, 2.0):
                for mb in (16, 48):
                    trs = sim(d, ev, rm, mb if tf == 15 else max(4, mb // (tf // 15)), R.COST[sym])
                    for t in trs:
                        t.update(sym=sym, tf=tf, rm=rm, mb=mb)
                    out += trs
            print(sym, tf, len(ev), flush=True)
    df = pd.DataFrame(out)
    df.to_pickle("/tmp/claude-0/-home-user-ICT-mentorship-PDFs/6e12c3be-f18a-5486-b706-0b976b77a294/scratchpad/turtle.pkl")
    g = df.groupby(["tf", "rm", "mb"]).r.agg(["count", "mean", lambda x: (x > 0).mean()])
    g.columns = ["n", "avgR", "win"]
    print(g.round(3))
