"""PD-array and swing studies: does the logic behave as the ICT concepts claim, compared with random candles?"""
import sys; sys.path.insert(0, "/home/user/ICT-mentorship-PDFs/tools")
import numpy as np, pandas as pd
import le_data as D, le_engine as E, le_run as R, le_lab as L


class Zx:
    __slots__ = ("kind", "bull", "top", "bot", "l70", "left_bi", "born_bi", "departed", "tapped", "dead", "used", "tap_i")

    def __init__(self, kind, bull, top, bot, with70, left_bi, born_bi, inv_pct=70):
        self.kind = kind; self.bull = bull; self.top = top; self.bot = bot; self.left_bi = left_bi; self.born_bi = born_bi
        self.l70 = None
        if with70:
            fr = inv_pct / 100.0
            self.l70 = top - fr * (top - bot) if bull else bot + fr * (top - bot)
        self.departed = False; self.tapped = False; self.dead = False; self.used = False; self.tap_i = None

    @property
    def inval(self):
        return self.l70 if self.l70 is not None else (self.bot if self.bull else self.top)


class ArrEngine(E.Engine):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.zx = []
        self.brk = []
        self.ob_org = {True: -1, False: -1}
        self.taps = []          # observations: first tap of each zone
        self.legs_obs = []

    # swings that closed beyond (structure break)
    def update_swings(self, arr, is_high, i):
        r = super().update_swings(arr, is_high, i)
        d = self.d
        for s in arr:
            if s.sig and not s.broken and i > s.bi and ((d.C[i] > s.px) if is_high else (d.C[i] < s.px)):
                s.broken = True
                self.brk.append((s, is_high))
        return r

    def f_origin(self, bull, from_bi, i):
        d = self.d
        span = min(i - from_bi, 300)
        e = d.L[i] if bull else d.H[i]
        eb = i
        for k in range(0, span + 1):
            v = d.L[i - k] if bull else d.H[i - k]
            if (v < e) if bull else (v > e):
                e = v; eb = i - k
        return e, eb

    def f_run(self, up_close, from_bi, seek, min_bi, max_len, i):
        d = self.d
        k0 = i - from_bi
        kmx = min(i - min_bi, 480)
        st = -1
        if 0 <= k0 <= kmx:
            for j in range(seek + 1):
                kk = k0 + j
                if kk > kmx:
                    break
                c, o = d.C[i - kk], d.O[i - kk]
                if (c > o) if up_close else (c < o):
                    st = kk; break
        if st < 0:
            return 0, 0, None, None
        k = st
        t = max(d.O[i - k], d.C[i - k]); b = min(d.O[i - k], d.C[i - k])
        while k + 1 <= kmx and k + 1 - st < max_len:
            c, o = d.C[i - k - 1], d.O[i - k - 1]
            if not ((c > o) if up_close else (c < o)):
                break
            k += 1
            t = max(t, max(o, c)); b = min(b, min(o, c))
        return i - k, i - st, t, b

    def on_break(self, sw, bull, i):
        d = self.d
        e, eb = self.f_origin(bull, sw.bi, i)
        if eb != self.ob_org[bull]:
            fu = 0
            for k in range(i - eb, -1, -1):
                c, o = d.C[i - k], d.O[i - k]
                if (c > o) if bull else (c < o):
                    fu = i - k; break
            if fu > 0:
                o0, o1, ot, ob = self.f_run(not bull, fu - 1, 3, sw.bi, 1, i)
                if o0 > 0:
                    self.zx.insert(0, Zx("OB", bull, ot, ob, True, o0, i))
                    self.ob_org[bull] = eb
        a = None
        for o in (self.lows if bull else self.highs):
            if o.sig and o.bi < sw.bi:
                a = o; break
        if a is not None and eb > sw.bi and ((e < a.px) if bull else (e > a.px)):
            b0, b1, bt, bb = self.f_run(bull, sw.bi, 6, a.bi, 1, i)
            if b0 > 0:
                self.zx.insert(0, Zx("BB", bull, bt, bb, True, b0, i))

    def inv_step(self, i):
        super().inv_step(i)
        d = self.d
        a = self.atr[i]
        # new FVGs (study copy)
        mg = self.c.fvgMin * a
        if self.is_fvg(d.H, d.L, True, i) and d.L[i] - d.H[i - 2] >= mg:
            self.zx.insert(0, Zx("FVG", True, d.L[i], d.H[i - 2], False, i - 2, i))
        if self.is_fvg(d.H, d.L, False, i) and d.L[i - 2] - d.H[i] >= mg:
            self.zx.insert(0, Zx("FVG", False, d.L[i - 2], d.H[i], False, i - 2, i))
        keep = []
        flips = []
        for z in self.zx:
            if not z.dead:
                if not z.departed:
                    z.departed = (d.L[i] > z.top) if z.bull else (d.H[i] < z.bot)
                elif not z.tapped and ((d.L[i] <= z.top) if z.bull else (d.H[i] >= z.bot)):
                    z.tapped = True; z.tap_i = i
                    self.taps.append((z.kind, z.bull, i, z.top, z.bot, z.inval, a, z.born_bi))
                if (d.C[i] < z.inval) if z.bull else (d.C[i] > z.inval):
                    z.dead = True
            h = z.top - z.bot
            spent = z.kind in ("BB", "OB") and z.tapped and ((d.L[i] > z.top + h) if z.bull else (d.H[i] < z.bot - h))
            bal = z.kind == "FVG" and not z.dead and ((d.L[i] <= z.bot) if z.bull else (d.H[i] >= z.top))
            if spent or bal:
                z.used = True
            if z.dead or i - z.born_bi > 400:
                if z.dead and z.kind == "FVG":
                    nz = Zx("iFVG", not z.bull, z.top, z.bot, False, z.left_bi, i)
                    nz.departed = True
                    flips.append(nz)
                continue
            keep.append(z)
        self.zx = flips + keep
        self.zx = self.zx[:200]
        # process the structure breaks of this bar (same place as in the Pine main block)
        for sw, is_high in self.brk:
            self.on_break(sw, is_high, i)
        self.brk = []


def label_taps(d, atr, taps, horizon=48, tgt_atr=1.0):
    """Outcome of each first tap: did price rise tgt ATR above the zone (bull) before CLOSING through the invalidation?"""
    out = []
    n = d.n
    for kind, bull, i, top, bot, inval, a, born in taps:
        res = None
        for j in range(i, min(n, i + horizon)):
            if (d.C[j] < inval) if bull else (d.C[j] > inval):
                res = 0; break
            if (d.H[j] >= top + tgt_atr * a) if bull else (d.L[j] <= bot - tgt_atr * a):
                res = 1; break
        f16 = None
        if i + 16 < n:
            f16 = ((d.C[i + 16] - d.C[i]) if bull else (d.C[i] - d.C[i + 16])) / a
        depth = (top - inval) / a if bull else (inval - bot) / a
        out.append(dict(kind=kind, bull=bull, i=i, res=res, f16=f16, depth=depth, height=(top - bot) / a, age=i - born, year=d.year[i]))
    return out
