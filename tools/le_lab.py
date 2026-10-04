import sys, time, copy, json
sys.path.insert(0, "/home/user/ICT-mentorship-PDFs/tools")
import le_data as D, le_engine as E, le_run as R

CACHE = {}


def get(sym):
    if sym not in CACHE:
        d = R.load(sym)
        base = E.Cfg()
        eng0 = E.Engine(d, base)          # builds the HTF feeds once
        CACHE[sym] = (d, eng0.htf, eng0.atr)
    return CACHE[sym]


def go(sym, **chg):
    d, htf, atr = get(sym)
    cfg = E.Cfg(**chg)
    cfg.costPts = R.COST[sym] if "costPts" not in chg else chg["costPts"]
    if cfg.useHTFPOI and "zD" not in htf:
        raise RuntimeError("HTF POIs missing")
    eng = E.Engine(d, cfg, atr=atr, htf=htf)
    trs = eng.run()
    return eng, trs


def split(trs, y0, y1):
    return [t for t in trs if y0 <= t["year"] <= y1]


def row(label, trs):
    s = R.summarize(trs, label)
    return s


def table(rows):
    print(f'{"label":38} {"n":>5} {"win%":>5} {"avgR":>7} {"totR":>7} {"PF":>5} {"maxDD":>6}')
    for s in rows:
        if s["n"] == 0:
            print(f'{s["label"]:38} {0:>5}')
        else:
            print(f'{s["label"]:38} {s["n"]:>5} {s["win"]:>5} {s["avgR"]:>7} {s["totR"]:>7} {str(s["pf"]):>5} {s["dd"]:>6}')
