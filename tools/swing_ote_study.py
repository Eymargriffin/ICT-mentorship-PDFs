import sys; sys.path.insert(0, "/home/user/ICT-mentorship-PDFs/tools")
import numpy as np, pandas as pd
import le_data as D, le_engine as E, le_arrays as A, le_lab as L


class LegEngine(A.ArrEngine):
    """Tracks every displacement leg: depth of each retracement and whether the leg then made a new extreme."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.trk = {}
        self.cycles = []

    def inv_step(self, i):
        super().inv_step(i)
        d = self.d
        for s in (self.bull, self.bear):
            key = s.bull
            t = self.trk.get(key)
            if t is not None and (s.state < 3 or s.conf_bi != t["conf"]):
                # leg over: a close through the raid extreme = failed leg; anything else = replaced (no outcome)
                if (d.C[i] < t["ext"]) if t["bull"] else (d.C[i] > t["ext"]):
                    self.cycles.append((t["depth"], 0, t["bull"], i))
                self.trk.pop(key, None)
                t = None
            if s.state >= 3 and t is None and s.conf_bi == i:
                self.trk[key] = dict(conf=s.conf_bi, ext=s.ext, hi=s.leg_end, depth=0.0, bull=s.bull, last_fail=-1)
                continue
            if t is None:
                continue
            bull = t["bull"]
            rng = abs(t["hi"] - t["ext"])
            if rng <= 0:
                continue
            if (d.H[i] > t["hi"]) if bull else (d.L[i] < t["hi"]):
                self.cycles.append((t["depth"], 1, bull, i))
                t["hi"] = d.H[i] if bull else d.L[i]
                t["depth"] = 0.0
            else:
                dep = ((t["hi"] - d.L[i]) if bull else (d.H[i] - t["hi"])) / rng
                t["depth"] = max(t["depth"], dep)


def cond_prob(cycles, xs=(0.21, 0.38, 0.5, 0.62, 0.79, 0.9)):
    out = {}
    for x in xs:
        sel = [c for c in cycles if c[0] >= x]
        out[x] = (len(sel), (sum(c[1] for c in sel) / len(sel)) if sel else float("nan"))
    return out


def reclaim_events(d, htf, atr, cfg):
    eng = E.Engine(d, cfg, atr=atr, htf=htf)
    ev = []
    orig = eng.step
    def step(s, i):
        before = s.state
        orig(s, i)
        if before == 1 and s.state == 2:
            a = eng.atr[i]
            ev.append(dict(i=i, f16=((d.C[i + 16] - d.C[i]) if s.bull else (d.C[i] - d.C[i + 16])) / a if i + 16 < d.n else None,
                           strong=bool(getattr(s, "lvl_strong", False)), key=bool(s.liq), year=d.year[i],
                           exc=abs(s.lvl - s.ext) / a))
    eng.step = step
    eng.run()
    return ev


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "ote":
        res = {"real": [], "null1": [], "null2": []}
        for sym in ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]:
            d15, htf, atr15 = L.get(sym)
            for tag, seed in (("real", None), ("null1", 1), ("null2", 2)):
                if seed is None:
                    d, atr, h = d15, atr15, htf
                else:
                    d = D.randomize(d15, seed); atr = D.atr14(d.H, d.L, d.C); h = None
                eng = LegEngine(d, E.Cfg(useHTFPOI=False), atr=atr, htf=h); eng.run()
                res[tag] += eng.cycles
            print(sym, flush=True)
        for tag, cyc in res.items():
            cp = cond_prob(cyc)
            print(tag, "cycles", len(cyc), {k: (n, round(p, 3)) for k, (n, p) in cp.items()})
        print("random-walk expectation P(new extreme | reached depth x) = 1-x:", {x: round(1 - x, 3) for x in (0.21, 0.38, 0.5, 0.62, 0.79, 0.9)})
        # band view: cycles whose max depth falls in the band
        bands = [(0, .21), (.21, .38), (.38, .5), (.5, .62), (.62, .79), (.79, 1.0)]
        for tag, cyc in res.items():
            row = {}
            for lo, hi in bands:
                sel = [c for c in cyc if lo <= c[0] < hi]
                row[f"{lo:.2f}-{hi:.2f}"] = (len(sel), round(sum(c[1] for c in sel) / max(1, len(sel)), 3))
            print(tag, "by max-depth band (n, P(new extreme))", row)
    elif mode == "swing":
        rows = []
        for sym in ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]:
            d15, htf, atr15 = L.get(sym)
            for lab, chg in (("minExc 0", dict(minExc=0.0)), ("minExc 0.5", dict(minExc=0.5)), ("minExc 1 (default)", {}),
                              ("minExc 2", dict(minExc=2.0)), ("N=1", dict(N=1)), ("N=3", dict(N=3)), ("N=5", dict(N=5)),
                              ("eqSig off", dict(eqSig=False)), ("keyRaid off", dict(keyRaid=False))):
                cfg = E.Cfg(useHTFPOI=False, **chg)
                ev = reclaim_events(d15, htf, atr15, cfg)
                for e in ev:
                    e.update(sym=sym, variant=lab); rows.append(e)
            print(sym, flush=True)
        df = pd.DataFrame(rows)
        df.to_pickle("/tmp/claude-0/-home-user-ICT-mentorship-PDFs/6e12c3be-f18a-5486-b706-0b976b77a294/scratchpad/swing_events.pkl")
        g = df.dropna(subset=["f16"]).groupby("variant").f16.agg(["count", "mean", "std"])
        g["t"] = g["mean"] / (g["std"] / np.sqrt(g["count"]))
        print(g.round(3).to_string())
        base = df[(df.variant == "minExc 1 (default)")].dropna(subset=["f16"])
        print("strong vs weak swing (default):")
        print(base.groupby("strong").f16.agg(["count", "mean", "std"]).round(3))
        print("by excursion size of the swept swing (ATR) — larger = more significant:")
        base = base.assign(exb=pd.cut(base.exc, [0, 1, 1.5, 2.5, 4, 100]))
        print(base.groupby("exb").f16.agg(["count", "mean"]).round(3))
