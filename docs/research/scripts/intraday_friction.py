# Scratch friction calculator from the intraday and scalping review (report 24).
fees=3.55  # bps variable round trip cash MIS
brk_order=30*1.18  # Upstox Plus per executed order incl GST
def fr(stop,R,spread,slip_in,slip_out,orders):
    N=R/(stop/1e4)
    cost=(fees+spread+slip_in+slip_out)*N/1e4 + orders*brk_order
    return cost/R, N
print("design gate model: spread2, slip1/1, 2 orders")
for R in (2500,5000):
  for s in (40,45,60,80,100):
    f,N=fr(s,R,2,1,1,2); print(R,s,round(N/1e5,2),"L",round(f,3))
print("realistic: spread3, entry slip1.5; loser stop slip5 (2 orders) ; winner target slip1.5 (3 orders, one partial)")
for R in (2500,5000):
  for s in (45,60,80,100):
    fl,N=fr(s,R,3,1.5,5,2); fw,_=fr(s,R,3,1.5,1.5,3)
    # 3-outcome: p_win, p_scratch, p_loss ; breakeven avg gross winner
    for pw,ps,pl in ((0.40,0.20,0.40),(0.35,0.25,0.40)):
        # net = pw*(W-fw) + ps*(-fw) + pl*(-(1+fl))
        W_be=(ps*fw+pl*(1+fl))/pw + fw
        W_15=(0.15+ps*fw+pl*(1+fl))/pw + fw
        print(R,s,round(N/1e5,2),"L loser",round(fl,3),"winner",round(fw,3),(pw,ps,pl),"W_be",round(W_be,2),"W_for+0.15",round(W_15,2))
# 2-outcome breakeven win rate
print("2-outcome breakeven p = (1+fl)/(W+1+fl-fw)")
for s,R in ((45,2500),(60,2500),(45,5000),(80,5000)):
    fl,_=fr(s,R,3,1.5,5,2); fw,_=fr(s,R,3,1.5,1.5,3)
    for W in (1.2,1.5,2.0):
        p=(1+fl)/(W-fw+1+fl); print(s,R,W,round(p,3))
# scalp at R=2500, 45bps stop, 5min sigma check
import math
for atr in (1.5,2.0,3.0,4.5):
    sd=atr/1.25  # daily sigma %
    s5=sd/math.sqrt(75)*100; s10=sd/math.sqrt(37.5)*100
    print("ATR%",atr,"5m sigma bps",round(s5,1),"10m sigma bps",round(s10,1),"90bps target in sigmas(10m)",round(90/s10,2))
# options friction per R: Nifty ATM 150 premium, 2 lots of 65, stop 15 pts premium
lots=2; q=65*lots; prem=150; stop=15
R=q*stop
fee= 2*20*1.18 + 0.0015*prem*q + 0.0003553*prem*q*2*1.18 + 0.00003*prem*q
spread=0.1*q; slip=0.1*q*2
print("opt R",R,"fees",round(fee),"friction R",round((fee+spread+slip)/R,3))
