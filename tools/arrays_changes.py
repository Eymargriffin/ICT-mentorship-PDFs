"""Tests the ICT-doctrine changes on the array reactions: edge = (success rate on real data) - (success on random candles),
compared inside invalidation-depth bins so geometry cancels out."""
import sys; sys.path.insert(0, "/home/user/ICT-mentorship-PDFs/tools")
import numpy as np, pandas as pd
import le_data as D, le_engine as E, le_arrays as A, le_lab as L


class Eng2(A.ArrEngine):
    def __init__(self, *a, ob_inv=70, ob_gate=False, **k):
        super().__init__(*a, **k)
        self.ob_inv = ob_inv; self.ob_gate = ob_gate
        self.all_taps = []

    def raid_near(self, bull, eb):
        pool = self.lows if bull else self.highs
        for sw in pool:
            if sw.sig and sw.taken and eb - 2 <= sw.taken_bi <= eb + 2:
                return True
        side = "Ltk" if bull else "Htk"
        for nm in ("pd", "as", "ln", "pm", "hr"):
            if eb - 2 <= self.lv[nm][side] <= eb + 2:
                return True
        return False

    def on_break(self, sw, bull, i):
        before = len(self.zx)
        super().on_break(sw, bull, i)
        # post-process: re-set the OB invalidation line, drop ungated OBs
        new = self.zx[:len(self.zx) - before] if len(self.zx) > before else []
        for z in list(self.zx[:max(0, len(self.zx) - before) or 3]):
            pass
        for z in self.zx[:3]:
            if z.kind == "OB" and z.born_bi == i:
                fr = self.ob_inv / 100.0
                z.l70 = z.top - fr * (z.top - z.bot) if z.bull else z.bot + fr * (z.top - z.bot)
                if self.ob_gate and not self.raid_near(bull, i - 0 if False else self._eb):
                    z.dead = True

    def f_origin(self, bull, from_bi, i):
        e, eb = super().f_origin(bull, from_bi, i)
        self._eb = eb
        return e, eb

    def inv_step(self, i):
        # second and later touches: record every re-entry once the zone has been left again
        super().inv_step(i)
        d = self.d
        a = self.atr[i]
        for z in self.zx:
            if z.tapped and z.tap_i is not None and z.tap_i != i and not z.dead:
                away = (d.L[i] > z.top) if z.bull else (d.H[i] < z.bot)
                if away:
                    z.tapped = False      # left again; the next entry is a 2nd touch
                    z.used = z.used
                    z.tap_i = -1
                    self._second.add(id(z)) if hasattr(self, "_second") else None


def edge(df_real, df_null, col="res"):
    out = []
    for kind, g in df_real.groupby("kind"):
        gn = df_null[df_null.kind == kind]
        tot = 0.0; n = 0
        for b, gb in g.groupby("db", observed=True):
            gnb = gn[gn.db == b]
            if len(gnb) < 200 or len(gb) < 200:
                continue
            tot += (gb[col].dropna().mean() - gnb[col].dropna().mean()) * len(gb); n += len(gb)
        out.append((kind, n, round(100 * tot / n, 2) if n else None))
    return out


def run(variant, **kw):
    rows = []
    for sym in ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]:
        d15, htf, atr15 = L.get(sym)
        for tag, seed in (("real", None), ("null", 1)):
            if seed is None:
                d, atr, h = d15, atr15, htf
            else:
                d = D.randomize(d15, seed); atr = D.atr14(d.H, d.L, d.C); h = None
            eng = Eng2(d, E.Cfg(useHTFPOI=False), atr=atr, htf=h, **kw)
            eng.run()
            for r in A.label_taps(d, atr, eng.taps):
                r["src"] = tag; rows.append(r)
    df = pd.DataFrame(rows)
    df["db"] = pd.cut(df.depth, [0, 0.3, 0.6, 1.0, 2.0, 100])
    return df[df.src == "real"], df[df.src == "null"]


if __name__ == "__main__":
    for lab, kw in (("OB invalidation 70% (old)", dict(ob_inv=70)),
                    ("OB invalidation 50% (ICT mean threshold)", dict(ob_inv=50)),
                    ("OB 50% + must follow a liquidity run", dict(ob_inv=50, ob_gate=True))):
        r, n = run(lab, **kw)
        print(lab); print("  edge over random candles, points of success rate, by array:", edge(r, n)); sys.stdout.flush()
