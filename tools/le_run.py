import sys, time, math, json
sys.path.insert(0, "/home/user/ICT-mentorship-PDFs/tools")
import le_data as D
import le_engine as E

ROOT = "/home/user/ejtraderLabs-historical-data"
COST = {"XAUUSD": 35.0, "EURUSD": 12.0, "GBPUSD": 15.0, "USDJPY": 12.0}   # round trip, in ticks (price × scale)


def load(sym, **kw):
    d = D.load(f"{ROOT}/{sym}/{sym}m15.csv", **kw)
    return d


def summarize(trs, label=""):
    n = len(trs)
    if n == 0:
        return dict(label=label, n=0)
    rs = [t["r"] for t in trs]
    w = sum(1 for r in rs if r > 0)
    gw = sum(r for r in rs if r > 0); gl = -sum(r for r in rs if r < 0)
    eq = 0; peak = 0; dd = 0
    for r in rs:
        eq += r; peak = max(peak, eq); dd = max(dd, peak - eq)
    return dict(label=label, n=n, win=round(100 * w / n, 1), avgR=round(sum(rs) / n, 3), totR=round(sum(rs), 1),
                pf=round(gw / gl, 2) if gl > 0 else None, dd=round(dd, 1))


def by(trs, key):
    out = {}
    for t in trs:
        out.setdefault(key(t), []).append(t)
    return {k: summarize(v) for k, v in sorted(out.items())}


def run(sym, cfg, d=None, htf=None, **kw):
    d = d or load(sym, **kw)
    eng = E.Engine(d, cfg, htf=htf)
    t = time.time()
    trs = eng.run()
    return eng, trs, time.time() - t


if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
    nb = int(sys.argv[2]) if len(sys.argv) > 2 else 40000
    cfg = E.Cfg(costPts=0.0, tick=1.0)
    d = load(sym, max_bars=nb)
    eng, trs, secs = run(sym, cfg, d=d)
    print(sym, "bars", d.n, "secs", round(secs, 1))
    print(summarize(trs, "gross"))
    print("funnel", eng.funnel)
    print("skips", eng.skips)
    print("by year", by(trs, lambda t: t["year"]))
