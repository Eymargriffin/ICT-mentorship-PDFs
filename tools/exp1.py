import sys; sys.path.insert(0,'.')
import le_lab as L, le_engine as E, le_run as R
SYMS=["XAUUSD","EURUSD","GBPUSD","USDJPY"]
variants = {
 "A SB default": {},
 "B no filters (open,liq,dec off)": dict(openOn=False,sbLiq=False,decOn=False),
 "C B + no MSS req": dict(openOn=False,sbLiq=False,decOn=False,sbMss=False),
 "D C + disp off": dict(openOn=False,sbLiq=False,decOn=False,sbMss=False,sbDisp=0.0),
 "E D + wide window 08:30-11:00": dict(openOn=False,sbLiq=False,decOn=False,sbMss=False,sbDisp=0.0,sbWin=((8*60+30,150),)),
 "F E + London+NY windows": dict(openOn=False,sbLiq=False,decOn=False,sbMss=False,sbDisp=0.0,sbWin=((2*60,180),(8*60+30,150))),
 "G F + perDay 3": dict(openOn=False,sbLiq=False,decOn=False,sbMss=False,sbDisp=0.0,sbWin=((2*60,180),(8*60+30,150)),sbPerDay=3),
}
allrows=[]
for name,chg in variants.items():
    pooled=[]
    for sym in SYMS:
        eng,trs=L.go(sym,**chg)
        pooled+=trs
        allrows.append(L.row(f"{name[:20]:20} {sym}",trs))
    allrows.append(L.row(f"{name[:20]:20} POOLED",pooled))
L.table(allrows)
