# Monte Carlo used by the arena evaluation research (report 16).
import numpy as np
rng = np.random.default_rng(11)
def mk(shape, p_loss):
    def draw(n, mu):
        loss = -1.0 - np.abs(rng.normal(0, 0.10, n))
        eloss = -1.0 - 0.10*np.sqrt(2/np.pi)
        wmean = (mu - p_loss*eloss)/(1-p_loss)
        win = rng.gamma(shape, wmean/shape, n)
        return np.where(rng.random(n) < p_loss, loss, win)
    return draw
profiles = {"capped(sig~1.1)": mk(8.0, 0.50), "trail(sig~1.45)": mk(1.6, 0.55)}
def maxdd(r):
    c = np.cumsum(r); peak = np.maximum.accumulate(np.concatenate([[0],c]))[1:]
    return (peak-c).max()
for name, draw in profiles.items():
    x = draw(500000, 0.15); print(name, "sigma=%.2f" % x.std(), "winrate=%.2f" % (x>0).mean())
    sig = x.std()
    for mu in [0.0, 0.15]:
        dds = [maxdd(draw(250,mu)) for _ in range(4000)]
        print(f"  mu={mu} 250 trades maxDD R: median {np.median(dds):.1f} p90 {np.percentile(dds,90):.1f} p95 {np.percentile(dds,95):.1f}")
    # SPRT with sigma estimated correctly and deff 1.4
    A=np.log(16); B=np.log(0.2/0.95); s2=sig**2*1.4; mu1=0.15
    for mu in [0.0,0.15,0.25]:
        acc=0; ns=[]
        for _ in range(3000):
            r=draw(1500,mu); llr=np.cumsum((mu1/s2)*(r-mu1/2))
            up=np.argmax(llr>=A) if (llr>=A).any() else 1500
            dn=np.argmax(llr<=B) if (llr<=B).any() else 1500
            acc += up<dn; ns.append(min(up,dn)+1)
        print(f"  SPRT mu={mu}: P(accept)={acc/3000:.2f} median n={np.median(ns):.0f} p80 n={np.percentile(ns,80):.0f}")
    # lucky book K=8 rho=.3, 60 days x 4/day; also expected best expectancy
    sims=1500; ap=0; be=[]
    for _ in range(sims):
        n=240; common=draw(n,0.0); best=-9; passed=False
        for k in range(8):
            r=np.sqrt(.3)*common+np.sqrt(.7)*draw(n,0.0)
            m=r.mean(); best=max(best,m)
            pf=r[r>0].sum()/-r[r<0].sum(); lb=m-1.2816*r.std()/np.sqrt(n)
            if m>=0.10 and pf>=1.25 and lb>0: passed=True
        ap+=passed; be.append(best)
    print(f"  8 zero-edge books, 240 trades each: P(>=1 passes gate-lite)={ap/sims:.2f}, mean best exp={np.mean(be):.3f}R")
