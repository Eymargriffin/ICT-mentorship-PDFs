"""Python replica of LiquidityEngine_P4.pine — Silver Bullet model (the Pine default) on 15m bars.

It mirrors the Pine order of operations bar by bar:  session levels → swing update → key-level hits → setup step →
setup start → FVG inventory → pivots → plan step → Silver Bullet arming → day-close withdrawal.
Not bar-for-bar identical to TradingView (different data feed, no Liquidity-Engine entries, no iFVG / breaker /
order-block inventory), but the same rules.  Everything is causal: bar i only uses bars <= i, HTF values are the
previous closed HTF candle, as with request.security(..., lookahead_on) on [1]-shifted series.
"""
from dataclasses import dataclass, field
import math
import le_data as D


@dataclass
class Cfg:
    # swings
    N: int = 2
    G: int = 2
    minExc: float = 1.0
    keepN: int = 60
    raidMode: str = "All significant"
    eqSig: bool = True
    eqTol: float = 0.1
    # raid / MSS
    K: int = 2
    M: int = 24
    grace: int = 2
    dispATR: float = 1.2
    refMode: str = "Highest since swept swing"
    dispAtBrk: bool = False
    fvgMin: float = 0.15
    keyRaid: bool = True
    # plan
    stopBuf: float = 0.1
    fillBars: int = 16
    fillTicks: int = 1
    minRR: float = 2.0
    partPct: int = 50
    tp1R: float = 1.0
    beAfter: bool = False
    runR: float = 2.0
    costPts: float = 0.0
    tick: float = 1.0
    openOn: bool = True
    liqReq: bool = False
    # silver bullet
    sbWin: tuple = ((10 * 60, 60),)          # list of (start minute NY, length)
    sbPerDay: int = 1
    sbLookMin: int = 180
    sbMss: bool = True
    sbDisp: float = 1.0
    sbEntry: str = "FVG edge"               # or "FVG midpoint"
    sbStop: str = "Raid extreme"            # or "FVG candles"
    sbTarget: str = "Key liquidity"         # or "Fixed R"
    sbMinATR: float = 2.0
    sbLiq: bool = True
    sbCancelEnd: bool = True
    sbEngReq: bool = False
    # decision engine
    decOn: bool = True
    decMin: int = 3
    decVeto: int = 3
    decFlip: bool = True
    wDay: int = 2
    wWk: int = 1
    wFlA: int = 1
    wFlB: int = 2
    wOpn: int = 1
    wPD: int = 1
    wStar: int = 1
    wLiq: int = 1
    wKz: int = 1
    wEng: int = 2
    useHTFPOI: bool = True
    # time filters
    biasMode: str = "Off"                   # Off | ICT daily bias
    dayFilter: str = "Any day"              # Any day | Tue-Thu | Mon-Wed
    noBias: str = "Trade both ways"
    killzones: tuple = ((2 * 60, 180), (8 * 60 + 30, 150))   # London, NY AM (used for the kz score term)


# ───────── helpers ─────────
def inwin(mod, w0, ln, tfmin=15):
    d = (mod - w0) % 1440
    return d < (ln if ln else 1440) or (1440 - d) % 1440 < tfmin


class Swing:
    __slots__ = ("bi", "px", "wm", "is_high", "atr_at", "ext", "graded", "strong", "sig", "taken", "taken_bi", "was_raid", "broken")

    def __init__(self, bi, px, wm, is_high, atr_at):
        self.bi = bi; self.px = px; self.wm = wm; self.is_high = is_high; self.atr_at = atr_at; self.ext = px
        self.graded = False; self.strong = True; self.sig = False; self.taken = False; self.taken_bi = 0; self.was_raid = False; self.broken = False


class Setup:
    def __init__(self, bull):
        self.bull = bull
        self.state = 0
        self.lvl = self.ext = self.ref = self.leg_end = None
        self.lvl_bi = self.sweep_bi = self.ext_bi = self.ref_bi = self.mss_bi = self.pend_bi = self.leg_end_bi = 0
        self.disp_max = 0.0
        self.liq = ""
        self.liq_bi = 0
        self.mid_open = None
        self.conf_bi = 0
        self.day_no = 0


class Zone:
    __slots__ = ("bull", "top", "bot", "left_bi", "born_bi", "used", "dead")

    def __init__(self, bull, top, bot, left_bi, born_bi):
        self.bull = bull; self.top = top; self.bot = bot; self.left_bi = left_bi; self.born_bi = born_bi
        self.used = False; self.dead = False


class Plan:
    def __init__(self):
        self.state = 0           # 0 none · 1 armed · 2 filled · 3 target · 4 stopped · 5 cancelled · 6 skipped
        self.bull = True
        self.why = ""
        self.entry = self.stop = self.tp1 = self.tp2 = self.run = None
        self.rr = None
        self.kill = None
        self.built_bi = 0
        self.fill_px = None
        self.tp1_px = None
        self.exit_px = None
        self.fill_bi = 0
        self.fill_i = 0
        self.sl_now = None
        self.tp1_hit = False
        self.score = None
        self.mss = -1
        self.close_bi = 0
        self.day_no = 0
        self.run_txt = ""
        self.raid_bi = 0
        self.fill_in_kz = False
        self.arm_i = 0
        self.dtxt = ""


class Engine:
    def __init__(self, d, cfg, atr=None, htf=None, verbose=False):
        self.d = d
        self.c = cfg
        self.n = d.n
        self.atr = atr or D.atr14(d.H, d.L, d.C)
        self.highs = []          # newest first
        self.lows = []
        self.bull = Setup(True)
        self.bear = Setup(False)
        self.inv = []            # FVG zones, newest first
        self.plan = Plan()
        self.trades = []
        self.funnel = {}
        self.tfmin = getattr(d, 'tfmin', 15)
        self.sb_lookB = max(1, round(cfg.sbLookMin / self.tfmin))
        self._init_levels()
        self._init_htf(htf)
        self.sb_cnt = 0
        self.sb_cnt_day = -1
        self.sb_seen = {True: -1, False: -1}
        self.day_no = 0
        self.skips = {}

    # ── HTF feeds: previous closed HTF candle, as lookahead_on with [1] ──
    def _init_htf(self, htf):
        d = self.d
        if htf is None:
            htf = {}
            for k in ("60", "240", "D", "W"):
                htf[k] = D.build_htf(d, k)
            htf["flow60"] = D.flow_series(*htf["60"][1:])
            htf["flow240"] = D.flow_series(*htf["240"][1:])
            htf["biasD"] = D.bias_series(*htf["D"][1:])
            htf["biasW"] = D.bias_series(*htf["W"][1:])
            if self.c.useHTFPOI:
                htf["zD"] = D.htf_zones_series(*htf["D"][1:])
                htf["z240"] = D.htf_zones_series(*htf["240"][1:])
            htf["h1"] = None
        self.htf = htf

    def flow(self, key, i):
        idx = self.htf[key[4:]][0][i]
        v = self.htf[key][idx]
        return 0 if v is None else v

    def bias_d(self, i):
        idx = self.htf["D"][0][i]
        code = self.htf["biasD"][0][idx]
        dol = self.htf["biasD"][1][idx]
        eq = self.htf["biasD"][2][idx]
        return code, dol, eq

    def bias_w(self, i):
        idx = self.htf["W"][0][i]
        return self.htf["biasW"][0][idx]

    def poi_backed(self, up, t, b, i):
        if not self.c.useHTFPOI:
            return False
        for key, kk in (("zD", "D"), ("z240", "240")):
            idx = self.htf[kk][0][i]
            snap = self.htf[key][idx]
            if snap is None:
                continue
            zs = snap[0] if up else snap[1]
            for (zt, zb) in zs:
                if zt >= b and zb <= t:
                    return True
        return False

    # ── session / key levels ──
    def _init_levels(self):
        self.mid_open = None
        self.day_hi = self.day_lo = None
        self.day_hi_bi = self.day_lo_bi = 0
        self.pdH = self.pdL = None
        self.pdHbi = self.pdLbi = 0
        self.lv = {}
        for nm in ("pd", "as", "ln", "pm", "hr"):
            self.lv[nm] = dict(H=None, L=None, Hok=False, Lok=False, Htk=-1, Ltk=-1, Hbi=0, Lbi=0)
        self.aHi = self.aLo = self.lHi = self.lLo = self.pHi = self.pLo = None
        self.aHiBi = self.aLoBi = self.lHiBi = self.lLoBi = self.pHiBi = self.pLoBi = 0
        self.prev_in = {"asia": False, "lon": False, "pre": False, "sb": False}

    def liq_tag(self, bull, from_bi, i):
        pool = self.lows if bull else self.highs
        tk = sorted(s.px for s in pool if s.sig and s.taken and s.taken_bi >= from_bi)
        eq = False
        a = self.atr[i]
        for k in range(1, len(tk)):
            if tk[k] - tk[k - 1] <= self.c.eqTol * a:
                eq = True
                break
        side = "L" if bull else "H"
        tags = []
        for nm, lab in (("pd", "PD"), ("as", "Asia "), ("ln", "London "), ("pm", "Pre "), ("hr", "Hr ")):
            if self.lv[nm][side + "tk"] >= from_bi:
                tags.append(lab + side)
        return ("EQL " if (eq and bull) else "EQH " if eq else "") + " ".join(tags)

    # ── swings ──
    def is_pivot(self, i, is_high):
        N = self.c.N
        if i < 2 * N:
            return False
        H, L = self.d.H, self.d.L
        cnd = H[i - N] if is_high else L[i - N]
        for k in range(N):
            if (H[i - k] > cnd) if is_high else (L[i - k] < cnd):
                return False
        for k in range(N + 1, 2 * N + 1):
            if (H[i - k] >= cnd) if is_high else (L[i - k] <= cnd):
                return False
        return True

    def new_swing(self, i, is_high):
        d, c, N = self.d, self.c, self.c.N
        px = d.H[i - N] if is_high else d.L[i - N]
        bt = max(d.O[i - N], d.C[i - N]) if is_high else min(d.O[i - N], d.C[i - N])
        a = self.atr[i - N] if self.atr[i - N] is not None else self.atr[i]
        s = Swing(i - N, px, (px + bt) / 2, is_high, a)
        for k in range(N):
            if (d.C[i - k] > s.wm) if is_high else (d.C[i - k] < s.wm):
                s.strong = False
            s.ext = min(s.ext, d.L[i - k]) if is_high else max(s.ext, d.H[i - k])
        s.graded = i >= s.bi + N + c.G
        s.sig = abs(s.px - s.ext) >= c.minExc * s.atr_at
        pool = self.highs if is_high else self.lows
        for o in pool:
            if o.taken and o.sig and s.bi - 5 <= o.taken_bi <= s.bi and ((o.px < s.px) if is_high else (o.px > s.px)):
                s.was_raid = True
                break
        if c.eqSig:
            twin = False
            for o in pool:
                if not o.taken and abs(o.px - s.px) <= c.eqTol * s.atr_at:
                    twin = True
                    o.sig = True
            if twin:
                s.sig = True
        return s

    def update_swings(self, arr, is_high, i):
        d, c, N = self.d, self.c, self.c.N
        hp = None; hb = 0; hs = False
        for idx in range(len(arr) - 1, -1, -1):
            s = arr[idx]
            if s.taken:
                continue
            if not s.graded:
                if (d.C[i] > s.wm) if is_high else (d.C[i] < s.wm):
                    s.strong = False
                if i >= s.bi + N + c.G:
                    s.graded = True
            hit = (d.H[i] > s.px) if is_high else (d.L[i] < s.px)
            if not hit:
                s.ext = min(s.ext, d.L[i]) if is_high else max(s.ext, d.H[i])
                if not s.sig and abs(s.px - s.ext) >= c.minExc * s.atr_at:
                    s.sig = True
            else:
                s.taken = True
                s.taken_bi = i
                elig = c.raidMode == "All significant" or (s.graded and not s.strong)
                if s.sig and elig and (hp is None or ((s.px > hp) if is_high else (s.px < hp))):
                    hp = s.px; hb = s.bi; hs = s.graded and s.strong
                if not s.sig:
                    arr.pop(idx)
        return hp, hb, hs

    def cap(self, arr):
        while len(arr) > self.c.keepN:
            victim = len(arr) - 1
            for j in range(len(arr) - 1, -1, -1):
                if arr[j].taken:
                    victim = j
                    break
            arr.pop(victim)

    # ── FVG inventory ──
    @staticmethod
    def is_fvg(H, L, bull, i):
        if i < 2:
            return False
        if bull:
            return L[i] > H[i - 2] and L[i - 1] <= H[i - 2] and H[i - 1] >= L[i]
        return H[i] < L[i - 2] and H[i - 1] >= L[i - 2] and L[i - 1] <= H[i]

    def inv_step(self, i):
        d, c = self.d, self.c
        a = self.atr[i]
        if a is None:
            return
        min_gap = c.fvgMin * a
        if self.is_fvg(d.H, d.L, True, i) and d.L[i] - d.H[i - 2] >= min_gap:
            self.inv.insert(0, Zone(True, d.L[i], d.H[i - 2], i - 2, i))
        if self.is_fvg(d.H, d.L, False, i) and d.L[i - 2] - d.H[i] >= min_gap:
            self.inv.insert(0, Zone(False, d.L[i - 2], d.H[i], i - 2, i))
        keep = []
        for z in self.inv:
            lim = z.bot if z.bull else z.top
            if (d.C[i] < lim) if z.bull else (d.C[i] > lim):
                z.dead = True
            bal = (not z.dead) and ((d.L[i] <= z.bot) if z.bull else (d.H[i] >= z.top))
            if bal:
                z.used = True
            if z.dead or (i - z.born_bi > 400):
                continue
            keep.append(z)
        self.inv = keep[:120]

    # ── setups ──
    def energy(self, bull, from_bi, brk_bi, i):
        d, c = self.d, self.c
        span = min(i - from_bi, 300)
        lim = min(span, i - brk_bi + 2) if c.dispAtBrk else span
        ok = False
        best = 0.0
        for k in range(0, lim + 1):
            j = i - k
            if j < 0:
                break
            body = abs(d.C[j] - d.O[j])
            rng = d.H[j] - d.L[j]
            a = self.atr[j] if self.atr[j] is not None else self.atr[i]
            dir_ok = (d.C[j] > d.O[j]) if bull else (d.C[j] < d.O[j])
            if dir_ok and rng > 0 and a > 0:
                best = max(best, body / a)
                if body >= c.dispATR * a and body >= 0.6 * rng:
                    ok = True
            if k + 2 <= span and k + 1 <= lim and j - 2 >= 0:
                gap = (d.L[j] - d.H[j - 2]) if bull else (d.L[j - 2] - d.H[j])
                if self.is_fvg(d.H, d.L, bull, j) and gap >= c.fvgMin * a:
                    ok = True
        return ok, best

    def bump(self, k):
        self.funnel[k] = self.funnel.get(k, 0) + 1

    def start(self, s, px, bi, from_key, i):
        d, c = self.d, self.c
        s.state = 0
        last_sw = bi
        pool = self.highs if s.bull else self.lows
        for sw in pool:
            if sw.sig and sw.bi > bi and sw.bi < i:
                last_sw = sw.bi
                break
        from_bi = last_sw if (c.refMode == "Last swing before the raid" or from_key) else bi
        r = None; rb = 0
        span = min(i - from_bi, 300)
        if span >= 1:
            for k in range(1, span + 1):
                v = d.H[i - k] if s.bull else d.L[i - k]
                if r is None or (v > r if s.bull else v < r):
                    r = v; rb = i - k
        if r is None:
            return
        self.bump("raid")
        s.state = 1
        s.lvl = px; s.lvl_bi = bi
        s.sweep_bi = i
        s.ext = d.L[i] if s.bull else d.H[i]
        s.ext_bi = i
        s.ref = r; s.ref_bi = rb
        s.mss_bi = 0; s.pend_bi = 0; s.leg_end = None; s.disp_max = 0.0
        s.liq_bi = max(rb, last_sw)
        s.liq = self.liq_tag(s.bull, s.liq_bi, i)
        s.mid_open = self.mid_open
        s.conf_bi = 0
        if (d.C[i] > px) if s.bull else (d.C[i] < px):
            s.state = 2

    def confirm(self, s, best, i):
        d = self.d
        mb = s.pend_bi if s.pend_bi > 0 else i
        le = d.H[i] if s.bull else d.L[i]
        le_bi = i
        k_end = min(i - min(s.ext_bi + 1, mb), 300)
        for k in range(1, k_end + 1):
            v = d.H[i - k] if s.bull else d.L[i - k]
            if (v > le) if s.bull else (v < le):
                le = v; le_bi = i - k
        self.bump("mss")
        s.state = 3
        s.mss_bi = mb
        s.conf_bi = i
        s.day_no = self.day_no
        s.leg_end = le; s.leg_end_bi = le_bi
        s.disp_max = best
        s.mid_open = self.mid_open
        opp = self.bear if s.bull else self.bull
        if opp.state >= 3:
            opp.state = 0

    def step(self, s, i):
        d, c = self.d, self.c
        bull = s.bull
        if s.state in (1, 2):
            if (d.L[i] < s.ext) if bull else (d.H[i] > s.ext):
                s.ext = d.L[i] if bull else d.H[i]
                s.ext_bi = i
                s.liq = self.liq_tag(bull, s.liq_bi, i)
        if s.state == 1:
            if (d.C[i] > s.lvl) if bull else (d.C[i] < s.lvl):
                s.state = 2
            elif i - s.sweep_bi >= c.K:
                s.state = 0; self.bump("void_reclaim")
        elif s.state == 2:
            if s.pend_bi > 0:
                ok, best = self.energy(bull, s.ext_bi, s.pend_bi, i)
                if ok:
                    self.confirm(s, best, i)
                elif (d.C[i] < s.ref) if bull else (d.C[i] > s.ref):
                    s.state = 0; self.bump("void_nodisp")
                elif i - s.pend_bi >= c.grace:
                    s.state = 0; self.bump("void_nodisp")
            elif (d.C[i] < s.lvl) if bull else (d.C[i] > s.lvl):
                s.state = 1
                s.sweep_bi = i
            elif (d.C[i] > s.ref) if bull else (d.C[i] < s.ref):
                ok, best = self.energy(bull, s.ext_bi, i, i)
                if ok:
                    self.confirm(s, best, i)
                elif c.grace > 0:
                    s.pend_bi = i
                else:
                    s.state = 0; self.bump("void_nodisp")
            elif i - s.ext_bi > c.M:
                s.state = 0; self.bump("void_time")
        elif s.state >= 3:
            if (d.C[i] < s.ext) if bull else (d.C[i] > s.ext):
                s.state = 0; self.bump("void_leg")
            elif i - s.mss_bi > 300:
                s.state = 0
            else:
                if (d.H[i] > s.leg_end) if bull else (d.L[i] < s.leg_end):
                    s.leg_end = d.H[i] if bull else d.L[i]
                    s.leg_end_bi = i

    # ── decision engine ──
    def htf_al(self, bull, i):
        dsg = 1 if bull else -1
        code, _, _ = self.bias_d(i)
        dDir = 0 if code is None else (1 if code > 0 else -1 if code < 0 else 0)
        wc = self.bias_w(i)
        wDir = 0 if wc is None else (1 if wc > 0 else -1 if wc < 0 else 0)
        fa = self.flow("flow60", i)
        fb = self.flow("flow240", i)
        al = lambda x: 0 if x == 0 else (1 if x == dsg else -1)
        return al(dDir), al(wDir), al(fa), al(fb)

    def htf_score(self, bull, i):
        c = self.c
        aD, aW, aA, aB = self.htf_al(bull, i)
        return c.wDay * aD + c.wWk * aW + c.wFlA * aA + c.wFlB * aB

    def engaged(self, bull, a, i):
        at = self.atr[i]
        return self.poi_backed(bull, a.ext + 0.3 * at, a.ext - 0.3 * at, i)

    def decide(self, bull, entry, a, star, kz, eng, i):
        c = self.c
        aD, aW, aA, aB = self.htf_al(bull, i)
        if a.mid_open is None:
            aO = 0
        elif bull:
            aO = 1 if a.ext < a.mid_open else -1
        else:
            aO = 1 if a.ext > a.mid_open else -1
        _, _, dEq = self.bias_d(i)
        if dEq is None:
            aP = 0
        elif bull:
            aP = 1 if entry < dEq else -1
        else:
            aP = 1 if entry > dEq else -1
        aS = 1 if star else 0
        aL = 1 if a.liq != "" else 0
        aK = 1 if kz else 0
        aE = 1 if eng else 0
        htf = c.wDay * aD + c.wWk * aW + c.wFlA * aA + c.wFlB * aB
        ctx = c.wOpn * aO + c.wPD * aP + c.wStar * aS + c.wLiq * aL + c.wKz * aK + c.wEng * aE
        self.last_comps = dict(aD=aD, aW=aW, aA=aA, aB=aB, aO=aO, aP=aP, aS=aS, aL=aL, aE=aE)
        return htf, ctx

    # ── Silver Bullet ──
    def in_sb(self, mod):
        return any(inwin(mod, w0, ln, self.tfmin) for (w0, ln) in self.c.sbWin)

    def sb_target(self, bull, entry, min_dist, i):
        t = None
        pool = self.highs if bull else self.lows
        for sw in pool:
            if sw.sig and not sw.taken and ((sw.px >= entry + min_dist) if bull else (sw.px <= entry - min_dist)):
                if t is None or ((sw.px < t) if bull else (sw.px > t)):
                    t = sw.px
        side = "H" if bull else "L"
        for nm in ("pd", "as", "ln", "pm", "hr"):
            lv = self.lv[nm]
            val = lv[side]
            ok = lv[side + "ok"]
            if ok and val is not None and ((val >= entry + min_dist) if bull else (val <= entry - min_dist)):
                if t is None or ((val < t) if bull else (val > t)):
                    t = val
        return t

    def sb_zone(self, bull, s, seen, i):
        d = self.d
        for z in reversed(self.inv):          # oldest first
            if z.bull == bull and not z.dead and not z.used and z.born_bi > seen and z.left_bi >= s.ext_bi \
                    and i - z.born_bi <= self.sb_lookB and ((z.bot > s.ext) if bull else (z.top < s.ext)):
                k = i - z.born_bi
                if k + 1 < 400 and self.in_sb(d.min_of_day[i - k]):
                    body = abs(d.C[i - k - 1] - d.O[i - k - 1])
                    a = self.atr[i - k - 1] if self.atr[i - k - 1] is not None else self.atr[i]
                    if self.c.sbDisp <= 0 or body >= self.c.sbDisp * a:
                        return z
        return None

    def day_ok(self, i):
        dow = self.d.dow[i]
        f = self.c.dayFilter
        return f == "Any day" or (f == "Tue-Thu" and 1 <= dow <= 3) or (f == "Mon-Wed" and 0 <= dow <= 2)

    def sb_build(self, a, z, i):
        d, c = self.d, self.c
        bull = a.bull
        p = Plan()
        p.bull = bull; p.mss = i; p.built_bi = i; p.day_no = self.day_no; p.arm_i = i
        p.kill = z.bot if bull else z.top
        p.entry = (z.top + z.bot) / 2 if c.sbEntry == "FVG midpoint" else (z.top if bull else z.bot)
        k0 = i - z.born_bi
        anchor = a.ext
        if c.sbStop == "FVG candles":
            anchor = d.L[i - k0] if bull else d.H[i - k0]
            for j in range(k0, k0 + 3):
                anchor = min(anchor, d.L[i - j]) if bull else max(anchor, d.H[i - j])
        at = self.atr[i]
        p.stop = anchor - c.stopBuf * at if bull else anchor + c.stopBuf * at
        p.sl_now = p.stop
        risk = abs(p.entry - p.stop)
        star = self.poi_backed(bull, z.top, z.bot, i)
        eng = self.engaged(bull, a, i)
        dHtf, dCtx = self.decide(bull, p.entry, a, star, True, eng, i)
        p.score = dHtf + dCtx
        p.feat = dict(self.last_comps)
        p.feat.update(htf=dHtf, ctx=dCtx, liq=a.liq, risk_atr=risk / at, disp=a.disp_max, hour=d.min_of_day[i] // 60,
                      fdow=d.dow[i], gap_bars=i - a.ext_bi, mss_age=i - a.mss_bi, raid_age=i - a.sweep_bi,
                      key_raid=bool(a.liq))
        min_dist = max(c.sbMinATR * at, c.minRR * risk)
        tq = self.sb_target(bull, p.entry, min_dist, i)
        fixed_t = p.entry + c.runR * risk if bull else p.entry - c.runR * risk
        liq_mode = c.sbTarget == "Key liquidity"
        p.run = tq if liq_mode else fixed_t
        p.tp2 = tq
        p.rr = abs(p.run - p.entry) / risk if (risk > 0 and p.run is not None) else None
        t1 = p.entry + c.tp1R * risk if bull else p.entry - c.tp1R * risk
        p.tp1 = t1 if (p.run is not None and ((t1 < p.run) if bull else (t1 > p.run))) else None
        code, _, _ = self.bias_d(i)
        dDir = 0 if code is None else (1 if code > 0 else -1 if code < 0 else 0)
        wc = self.bias_w(i)
        wDir = 0 if wc is None else (1 if wc > 0 else -1 if wc < 0 else 0)
        ictDir = dDir if dDir != 0 else wDir
        why = None
        if not (risk > 0):
            why = "R:R no valid stop"
        elif c.biasMode == "ICT daily bias" and ictDir == (-1 if bull else 1):
            why = "bias against"
        elif c.biasMode == "ICT daily bias" and ictDir == 0 and c.noBias == "Stand aside":
            why = "no bias"
        elif not self.day_ok(i):
            why = "day filter"
        elif c.openOn and a.mid_open is not None and ((a.ext >= a.mid_open) if bull else (a.ext <= a.mid_open)):
            why = "midnight open"
        elif c.sbLiq and a.liq == "":
            why = "no key liquidity"
        elif c.sbEngReq and not eng:
            why = "HTF PD array not engaged"
        elif c.decOn and dHtf <= -c.decVeto:
            why = "decision veto"
        elif c.decOn and p.score < c.decMin:
            why = "decision score"
        elif p.run is None or (not liq_mode and c.runR < c.minRR):
            why = "R:R no target"
        if why:
            p.state = 6
            p.why = why
        else:
            p.state = 1
        return p

    # ── plan lifecycle ──
    def plan_r(self, p):
        c = self.c
        risk = abs(p.entry - p.stop)
        dv = 1.0 if p.bull else -1.0
        fp = p.entry if p.fill_px is None else p.fill_px
        t1 = p.tp1 if p.tp1_px is None else p.tp1_px
        ex = p.exit_px if p.exit_px is not None else (p.run if p.state == 3 else p.sl_now)
        part = c.partPct / 100.0 if p.tp1_hit else 0.0
        r1 = dv * (t1 - fp) / risk if (risk > 0 and p.tp1_hit) else 0.0
        rex = dv * (ex - fp) / risk if risk > 0 else 0.0
        cost = c.costPts / risk if risk > 0 else 0.0
        return part * r1 + (1 - part) * rex - cost

    def plan_step(self, i, day_start, week_start):
        d, c = self.d, self.c
        p = self.plan
        bull = p.bull
        if p.state == 1:
            thru = c.fillTicks * c.tick
            if day_start and i > p.built_bi:
                p.state = 5; p.why = "expired at day close"
            elif week_start and i > p.built_bi:
                p.state = 5; p.why = "weekend"
            elif i > p.built_bi and ((d.L[i] <= p.entry - thru) if bull else (d.H[i] >= p.entry + thru)):
                p.state = 2
                p.fill_bi = i
                p.fill_i = i
                p.fill_in_kz = self.in_kz(d.min_of_day[i])
                p.fill_px = min(d.O[i], p.entry) if bull else max(d.O[i], p.entry)
                if (d.L[i] <= p.sl_now) if bull else (d.H[i] >= p.sl_now):
                    p.state = 4; p.why = "stopped on fill candle"
                    p.exit_px = min(d.O[i], p.sl_now) if bull else max(d.O[i], p.sl_now)
                    p.close_bi = i
            elif c.decOn and c.decFlip and self.htf_score(bull, i) <= -c.decVeto:
                p.state = 5; p.why = "HTF flipped"
            elif (d.C[i] < p.kill) if bull else (d.C[i] > p.kill):
                p.state = 5; p.why = "array violated"
            elif (p.tp2 is not None) and ((d.H[i] >= p.tp2) if bull else (d.L[i] <= p.tp2)):
                p.state = 5; p.why = "target before fill"
            elif i - p.built_bi > c.fillBars:
                p.state = 5; p.why = "timeout"
        elif p.state == 2:
            if (d.L[i] <= p.sl_now) if bull else (d.H[i] >= p.sl_now):
                p.state = 4
                p.why = "BE" if p.tp1_hit else "stopped"
                p.exit_px = min(d.O[i], p.sl_now) if bull else max(d.O[i], p.sl_now)
                p.close_bi = i
            elif i > p.fill_bi:
                if not p.tp1_hit and p.tp1 is not None and c.partPct > 0:
                    if (d.H[i] >= p.tp1) if bull else (d.L[i] <= p.tp1):
                        p.tp1_hit = True
                        p.tp1_px = max(d.O[i], p.tp1) if bull else min(d.O[i], p.tp1)
                        if c.beAfter:
                            p.sl_now = p.fill_px if p.fill_px is not None else p.entry
                if (d.H[i] >= p.run) if bull else (d.L[i] <= p.run):
                    p.state = 3
                    p.exit_px = max(d.O[i], p.run) if bull else min(d.O[i], p.run)
                    p.close_bi = i

    def in_kz(self, mod):
        return any(inwin(mod, w0, ln, self.tfmin) for (w0, ln) in self.c.killzones)

    def record(self, p, i):
        r = self.plan_r(p)
        d = self.d
        self.trades.append(dict(
            arm_i=p.arm_i, fill_i=p.fill_i, close_i=i, bull=p.bull, score=p.score, r=r, outcome="target" if p.state == 3 else p.why,
            tp1=p.tp1_hit, entry=p.entry, stop=p.stop, run=p.run, year=d.year[p.fill_i], risk=abs(p.entry - p.stop),
            fill_kz=p.fill_in_kz, dow=d.dow[p.fill_i], ny=str(d.ny.iloc[p.fill_i]), rr=p.rr, **getattr(p, "feat", {})))

    # ── the main loop ──
    def run(self, progress=False):
        d, c = self.d, self.c
        n = self.n
        prev_srvdate = None
        prev_nydate = None
        for i in range(n):
            a = self.atr[i]
            mod = d.min_of_day[i]
            srvdate = d.srvdate[i]
            new_day = prev_srvdate is not None and srvdate != prev_srvdate
            new_ny_day = prev_nydate is not None and d.nydate[i] != prev_nydate
            day_end = (i + 1 < n and d.srvdate[i + 1] != srvdate)
            week_end = (i + 1 < n and (d.ts[i + 1] - d.ts[i]) > 24 * 3600 * 10 ** 9)  # >24h gap after this bar
            week_start = (i > 0 and (d.ts[i] - d.ts[i - 1]) > 24 * 3600 * 10 ** 9)
            prev_srvdate = srvdate
            prev_nydate = d.nydate[i]
            if a is None:
                continue
            if new_ny_day:
                self.mid_open = d.O[i]
            if new_day:
                self.day_no += 1
                self.lv["pd"]["Hok"] = True
                self.lv["pd"]["Lok"] = True
                self.pdHbi = self.day_hi_bi
                self.pdLbi = self.day_lo_bi
                if self.day_hi is not None:
                    self.pdH = self.day_hi
                    self.pdL = self.day_lo
                self.lv["pd"]["H"] = self.pdH
                self.lv["pd"]["L"] = self.pdL
                self.lv["pd"]["Hbi"] = self.pdHbi
                self.lv["pd"]["Lbi"] = self.pdLbi
                self.day_hi = d.H[i]; self.day_lo = d.L[i]; self.day_hi_bi = self.day_lo_bi = i
            else:
                if self.day_hi is None or d.H[i] > self.day_hi:
                    self.day_hi = d.H[i]; self.day_hi_bi = i
                if self.day_lo is None or d.L[i] < self.day_lo:
                    self.day_lo = d.L[i]; self.day_lo_bi = i
            self.sessions(i, mod)
            hH, hB, hS = self.update_swings(self.highs, True, i)
            lH, lB, lS = self.update_swings(self.lows, False, i)
            # key levels taken on this candle
            lRaid, lRaidBi, lKey = lH, lB, False
            hRaid, hRaidBi, hKey = hH, hB, False
            if c.keyRaid:
                kLo = self.key_hit(True, i)
                kHi = self.key_hit(False, i)
                if kLo[0] is not None and (lRaid is None or kLo[0] < lRaid):
                    lRaid, lRaidBi, lKey = kLo[0], kLo[1], True
                if kHi[0] is not None and (hRaid is None or kHi[0] > hRaid):
                    hRaid, hRaidBi, hKey = kHi[0], kHi[1], True
            bull_ext0 = self.bull.ext
            bear_ext0 = self.bear.ext
            self.step(self.bull, i)
            self.step(self.bear, i)
            if lRaid is not None and (self.bull.state == 0 or (lRaid < bull_ext0 and self.bull.conf_bi != i)):
                self.start(self.bull, lRaid, lRaidBi, lKey, i); self.bull.lvl_strong = (lS and not lKey)
            if hRaid is not None and (self.bear.state == 0 or (hRaid > bear_ext0 and self.bear.conf_bi != i)):
                self.start(self.bear, hRaid, hRaidBi, hKey, i); self.bear.lvl_strong = (hS and not hKey)
            self.inv_step(i)
            if self.is_pivot(i, True):
                self.highs.insert(0, self.new_swing(i, True))
            if self.is_pivot(i, False):
                self.lows.insert(0, self.new_swing(i, False))
            self.cap(self.highs); self.cap(self.lows)
            # plan lifecycle
            self.plan_step(i, new_day, week_start)
            p = self.plan
            if p.state in (3, 4) and p.close_bi == i and not getattr(p, "counted", False):
                p.counted = True
                self.record(p, i)
            if p.state == 5 and getattr(p, "cancel_i", -1) != i and not getattr(p, "tallied", False):
                p.tallied = True
            # Silver Bullet arming
            if self.sb_cnt_day != self.day_no:
                self.sb_cnt = 0
                self.sb_cnt_day = self.day_no
            next_in = i + 1 < n and self.in_sb(d.min_of_day[i + 1])
            if p.state == 1 and c.sbCancelEnd and not next_in:
                p.state = 5; p.why = "window closed"
            win_now = self.in_sb(mod) and (not c.sbCancelEnd or next_in)
            close_now = day_end
            if win_now and self.sb_cnt < c.sbPerDay and p.state not in (1, 2) and not close_now:
                bull_first = self.htf_score(True, i) >= self.htf_score(False, i)
                armed = False
                for side in (0, 1):
                    dir_bull = (side == 0) == bull_first
                    sb = self.bull if dir_bull else self.bear
                    if not armed and sb.state >= (3 if c.sbMss else 2) and i - sb.ext_bi <= self.sb_lookB:
                        z = self.sb_zone(dir_bull, sb, self.sb_seen[dir_bull], i)
                        if z is not None:
                            self.sb_seen[dir_bull] = z.born_bi
                            np_ = self.sb_build(sb, z, i)
                            if np_.state != 1:
                                self.skips[np_.why] = self.skips.get(np_.why, 0) + 1
                            self.plan = np_
                            if np_.state == 1:
                                self.sb_cnt += 1
                                armed = True
            p = self.plan
            if p.state == 1 and close_now:
                p.state = 5; p.why = "day close"
        return self.trades

    # ── session / key-level bookkeeping (same order as the Pine main block) ──
    def sessions(self, i, mod):
        d, c = self.d, self.c
        lv = self.lv
        in_asia = inwin(mod, 20 * 60, 240, self.tfmin)
        in_lon = inwin(mod, 2 * 60, 180, self.tfmin)
        in_pre = inwin(mod, 8 * 60, 90, self.tfmin)
        in_sb = self.in_sb(mod)
        H, L = d.H[i], d.L[i]
        pv = self.prev_in
        if in_asia:
            if not pv["asia"] or H > self.aHi:
                self.aHiBi = i
            if not pv["asia"] or L < self.aLo:
                self.aLoBi = i
            self.aHi = max(self.aHi, H) if pv["asia"] else H
            self.aLo = min(self.aLo, L) if pv["asia"] else L
        elif pv["asia"]:
            lv["as"].update(H=self.aHi, L=self.aLo, Hbi=self.aHiBi, Lbi=self.aLoBi, Hok=True, Lok=True)
        if in_lon:
            if not pv["lon"] or H > self.lHi:
                self.lHiBi = i
            if not pv["lon"] or L < self.lLo:
                self.lLoBi = i
            self.lHi = max(self.lHi, H) if pv["lon"] else H
            self.lLo = min(self.lLo, L) if pv["lon"] else L
        elif pv["lon"]:
            lv["ln"].update(H=self.lHi, L=self.lLo, Hbi=self.lHiBi, Lbi=self.lLoBi, Hok=True, Lok=True)
        if in_pre:
            if not pv["pre"] or H > self.pHi:
                self.pHiBi = i
            if not pv["pre"] or L < self.pLo:
                self.pLoBi = i
            self.pHi = max(self.pHi, H) if pv["pre"] else H
            self.pLo = min(self.pLo, L) if pv["pre"] else L
        elif pv["pre"]:
            lv["pm"].update(H=self.pHi, L=self.pLo, Hbi=self.pHiBi, Lbi=self.pLoBi, Hok=True, Lok=True)
        nb = max(1, 60 // self.tfmin)
        if in_sb and not pv["sb"] and i >= nb:
            hh = max(d.H[i - nb:i]); ll = min(d.L[i - nb:i])
            lv["hr"].update(H=hh, L=ll, Hbi=i, Lbi=i, Hok=True, Lok=True)
        self.prev_in = {"asia": in_asia, "lon": in_lon, "pre": in_pre, "sb": in_sb}
        for nm in ("pm", "hr", "pd", "as", "ln"):
            e = lv[nm]
            if e["Lok"] and e["L"] is not None and L < e["L"]:
                e["Lok"] = False; e["Ltk"] = i
            if e["Hok"] and e["H"] is not None and H > e["H"]:
                e["Hok"] = False; e["Htk"] = i

    def key_hit(self, low_side, i):
        px = None
        bi = 0
        side = "L" if low_side else "H"
        for nm in ("pd", "as", "ln", "pm", "hr"):
            e = self.lv[nm]
            if e[side + "tk"] == i and e[side + "bi"] > 0 and e[side] is not None:
                v = e[side]
                if px is None or (v < px if low_side else v > px):
                    px = v; bi = e[side + "bi"]
        return px, bi
