"""Data layer for the Liquidity Engine backtester (Python replica of LiquidityEngine_P4.pine).

Source: github.com/ejtraderLabs/historical-data  (m15 CSVs, MT5 server time).
Server time = New York time + 7h in both US summer and winter (the broker follows NY close: the daily break is
00:00-01:00 server, the week reopens Monday 01:00 server = Sunday 18:00 NY).  Prices are stored multiplied by
100 (XAUUSD), 1e5 (EURUSD, GBPUSD) or 1e3 (USDJPY): one unit is one tick, which matches syminfo.mintick.
"""
import numpy as np
import pandas as pd

SCALE = {"XAUUSD": 100, "EURUSD": 1e5, "GBPUSD": 1e5, "USDJPY": 1e3}


class Data:
    pass


def load(path, max_bars=None, start=None, end=None):
    df = pd.read_csv(path, parse_dates=["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    d = Data()
    d.srv = df["Date"].values.astype("datetime64[m]")
    ny = (df["Date"] - pd.Timedelta(hours=7))
    d.ny = ny
    if start is not None or end is not None:
        m = np.ones(len(df), bool)
        if start is not None:
            m &= (ny >= pd.Timestamp(start)).values
        if end is not None:
            m &= (ny < pd.Timestamp(end)).values
        df = df[m].reset_index(drop=True)
        ny = ny[m].reset_index(drop=True)
    if max_bars:
        df = df.iloc[:max_bars].reset_index(drop=True)
        ny = ny.iloc[:max_bars].reset_index(drop=True)
    d.n = len(df)
    d.O = df["open"].values.astype(float).tolist()
    d.H = df["high"].values.astype(float).tolist()
    d.L = df["low"].values.astype(float).tolist()
    d.C = df["close"].values.astype(float).tolist()
    d.ny = ny
    d.min_of_day = (ny.dt.hour * 60 + ny.dt.minute).values.tolist()
    d.nydate = ny.dt.date.values
    srv = df["Date"]
    d.srvdate = srv.dt.date.values            # broker day = NY 17:00 → 17:00
    d.dow = ny.dt.dayofweek.values.tolist()
    d.srv_hour = srv.dt.hour.values.tolist()
    d.ts = srv.values
    d.year = ny.dt.year.values.tolist()
    return d


def atr14(H, L, C):
    n = len(C)
    out = [None] * n
    tr = [H[0] - L[0]] + [max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])) for i in range(1, n)]
    if n < 14:
        return out
    a = sum(tr[:14]) / 14.0
    out[13] = a
    for i in range(14, n):
        a = (a * 13 + tr[i]) / 14.0
        out[i] = a
    return out


# ───────── higher-timeframe series (built from the 15m bars) ─────────
def htf_groups(d, kind):
    """Return (key list per bar) so that consecutive bars with the same key form one HTF candle."""
    if kind == "60":
        return [(d.srvdate[i], d.srv_hour[i]) for i in range(d.n)]
    if kind == "240":
        return [(d.srvdate[i], d.srv_hour[i] // 4) for i in range(d.n)]
    if kind == "D":
        return [d.srvdate[i] for i in range(d.n)]
    if kind == "W":
        iso = pd.Series(d.srvdate).map(lambda x: pd.Timestamp(x).isocalendar()[:2]).values
        return list(iso)
    raise ValueError(kind)


def build_htf(d, kind):
    keys = htf_groups(d, kind)
    idx = [0] * d.n
    o, h, l, c = [], [], [], []
    last = None
    t = -1
    for i in range(d.n):
        if keys[i] != last:
            last = keys[i]
            t += 1
            o.append(d.O[i]); h.append(d.H[i]); l.append(d.L[i]); c.append(d.C[i])
        else:
            h[t] = max(h[t], d.H[i]); l[t] = min(l[t], d.L[i]); c[t] = d.C[i]
        idx[i] = t
    return idx, o, h, l, c


def pivots(H, L, n=2):
    """pivot high / low confirmed at bar t for the candidate at t-n (left strict, right allows equals)."""
    N = len(H)
    ph = [None] * N
    pl = [None] * N
    for t in range(2 * n, N):
        c = t - n
        okh = True
        okl = True
        for k in range(0, n):
            if H[t - k] > H[c]:
                okh = False
            if L[t - k] < L[c]:
                okl = False
        for k in range(n + 1, 2 * n + 1):
            if H[t - k] >= H[c]:
                okh = False
            if L[t - k] <= L[c]:
                okl = False
        if okh:
            ph[t] = H[c]
        if okl:
            pl[t] = L[c]
    return ph, pl


def flow_series(o, h, l, c):
    """f_flow(): +1 after the last close above a swing high, −1 after the last close below a swing low (value at t-1)."""
    ph, pl = pivots(h, l, 2)
    lastH = lastL = None
    dir_ = 0
    raw = []
    for t in range(len(c)):
        if ph[t] is not None:
            lastH = ph[t]
        if pl[t] is not None:
            lastL = pl[t]
        if lastH is not None and c[t] > lastH:
            dir_ = 1
            lastH = None
        elif lastL is not None and c[t] < lastL:
            dir_ = -1
            lastL = None
        raw.append(dir_)
    return [None] + raw[:-1]        # dir[1]


def bias_series(o, h, l, c):
    """f_bias(): returns code[1], dol[1], eq[1] per HTF candle."""
    ph, pl = pivots(h, l, 2)
    sh, sl = [], []
    lastH = lastL = None
    codes, dols, eqs = [], [], []
    for t in range(len(c)):
        if ph[t] is not None:
            sh.append(ph[t]); lastH = ph[t]
        if pl[t] is not None:
            sl.append(pl[t]); lastL = pl[t]
        sh = [v for v in sh if not (h[t] > v)]
        sl = [v for v in sl if not (l[t] < v)]
        sh = sh[-30:]; sl = sl[-30:]
        up = None
        dn = None
        for v in sh:
            if v > c[t] and (up is None or v < up):
                up = v
        for v in sl:
            if v < c[t] and (dn is None or v > dn):
                dn = v
        code = 0
        dol = None
        if t >= 1:
            if c[t] > h[t - 1]:
                code = 2; dol = up
            elif c[t] < l[t - 1]:
                code = -2; dol = dn
            elif l[t] < l[t - 1] and h[t] <= h[t - 1]:
                code = 1; dol = h[t - 1]
            elif h[t] > h[t - 1] and l[t] >= l[t - 1]:
                code = -1; dol = l[t - 1]
        eq = None if lastH is None or lastL is None else (lastH + lastL) / 2
        codes.append(code); dols.append(dol); eqs.append(eq)
    sh_ = lambda a: [None] + a[:-1]
    return sh_(codes), sh_(dols), sh_(eqs)


def htf_zones_series(o, h, l, c, inv_pct=70):
    """f_htfZones(): the three nearest live bullish / bearish POIs of the PREVIOUS closed candle."""
    ph, pl = pivots(h, l, 2)
    bull, bear = [], []          # (top, bot, kill)
    lastPH = lastPL = None
    snaps = []
    fr = inv_pct / 100.0
    for t in range(len(c)):
        if ph[t] is not None:
            lastPH = ph[t]
        if pl[t] is not None:
            lastPL = pl[t]
        if t >= 2:
            if l[t] > h[t - 2] and l[t - 1] <= h[t - 2] and h[t - 1] >= l[t]:
                bull.append((l[t], h[t - 2], h[t - 2]))
            if h[t] < l[t - 2] and h[t - 1] >= l[t - 2] and l[t - 1] <= h[t]:
                bear.append((l[t - 2], h[t], l[t - 2]))
        if lastPH is not None and c[t] > lastPH:
            k = 0
            while k < 20 and t - k >= 0 and c[t - k] >= o[t - k]:
                k += 1
            top = bot = None
            cnt = 0
            while k < 40 and cnt < 6 and t - k >= 0 and c[t - k] < o[t - k]:
                top = o[t - k] if top is None else max(top, o[t - k])
                bot = c[t - k] if bot is None else min(bot, c[t - k])
                k += 1; cnt += 1
            if cnt > 0:
                bull.append((top, bot, top - fr * (top - bot)))
            lastPH = None
        if lastPL is not None and c[t] < lastPL:
            k = 0
            while k < 20 and t - k >= 0 and c[t - k] <= o[t - k]:
                k += 1
            top = bot = None
            cnt = 0
            while k < 40 and cnt < 6 and t - k >= 0 and c[t - k] > o[t - k]:
                top = c[t - k] if top is None else max(top, c[t - k])
                bot = o[t - k] if bot is None else min(bot, o[t - k])
                k += 1; cnt += 1
            if cnt > 0:
                bear.append((top, bot, bot + fr * (top - bot)))
            lastPL = None
        bull = [z for z in bull if not (c[t] < z[2])][-40:]
        bear = [z for z in bear if not (c[t] > z[2])][-40:]

        def near3(zs):
            def dist(z):
                return c[t] - z[0] if c[t] > z[0] else (z[1] - c[t] if c[t] < z[1] else 0.0)
            return [(z[0], z[1]) for z in sorted(zs, key=dist)[:3]]
        snaps.append((near3(bull), near3(bear)))
    return [None] + snaps[:-1]


def resample(d, minutes):
    """Aggregate the 15m Data into 60 / 240 minute bars (same fields; tfmin attribute for the engine)."""
    import pandas as pd
    keys = htf_groups(d, "60" if minutes == 60 else "240")
    o, h, l, c, first = [], [], [], [], []
    last = None
    for i in range(d.n):
        if keys[i] != last:
            last = keys[i]
            o.append(d.O[i]); h.append(d.H[i]); l.append(d.L[i]); c.append(d.C[i]); first.append(i)
        else:
            h[-1] = max(h[-1], d.H[i]); l[-1] = min(l[-1], d.L[i]); c[-1] = d.C[i]
    r = Data()
    r.n = len(c)
    r.O, r.H, r.L, r.C = o, h, l, c
    r.ny = d.ny.iloc[first].reset_index(drop=True)
    r.min_of_day = [d.min_of_day[i] for i in first]
    r.nydate = d.nydate[first]
    r.srvdate = d.srvdate[first]
    r.dow = [d.dow[i] for i in first]
    r.srv_hour = [d.srv_hour[i] for i in first]
    r.ts = d.ts[first]
    r.year = [d.year[i] for i in first]
    r.tfmin = minutes
    return r


def randomize(d, seed=1):
    """Null data set: every candle keeps its shape and its time stamp, but its direction is flipped at random
    (reflected around its open) and the path is re-chained.  No serial structure is left, so any 'edge' is an artifact."""
    import random
    rnd = random.Random(seed)
    r = Data()
    for k, v in d.__dict__.items():
        setattr(r, k, v)
    O, H, L, C = [], [], [], []
    px = d.O[0]
    for i in range(d.n):
        s = 1 if rnd.random() < 0.5 else -1
        o0 = d.O[i]
        gap = (d.O[i] - d.C[i - 1]) if i > 0 else 0.0
        o = px + s * gap * 0           # no overnight gap structure
        dc = s * (d.C[i] - o0); dh = s * (d.H[i] - o0); dl = s * (d.L[i] - o0)
        c_ = o + dc
        h_ = o + max(dh, dl); l_ = o + min(dh, dl)
        O.append(o); H.append(h_); L.append(l_); C.append(c_)
        px = c_
    r.O, r.H, r.L, r.C = O, H, L, C
    return r
