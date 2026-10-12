# Scratch Monte Carlo from the portfolio and risk review (report 23).
import numpy as np
rng=np.random.default_rng(7)
D=250; Y=2; N=20000
def sim(mu_ann, sd_ann, corr, label, df=4):
    mu=np.array(mu_ann)/D; sd=np.array(sd_ann)/np.sqrt(D)
    C=np.array(corr); L=np.linalg.cholesky(C)
    k=len(mu)
    z=rng.standard_normal((N,D*Y,k))@L.T
    # student-t scaling (common shock -> fat tails, crash correlation)
    w=np.sqrt(rng.chisquare(df,(N,D*Y,1))/df)
    z=z/w*np.sqrt((df-2)/df)
    r=(mu+sd*z).sum(-1)
    eq=np.cumprod(1+r,axis=1)
    peak=np.maximum.accumulate(eq,axis=1)
    dd=1-eq/peak
    mdd=dd.max(1)
    ann=eq[:,D-1]-1
    port_sd=r.std(1).mean()*np.sqrt(D)
    print(f"{label:38s} mean1y {np.mean(ann)*100:5.1f}%  p10 {np.percentile(ann,10)*100:6.1f}%  P(yr<0) {np.mean(ann<0)*100:4.0f}%  vol {port_sd*100:4.1f}%  medMDD2y {np.median(mdd)*100:4.1f}%  P(MDD>=15%) {np.mean(mdd>=.15)*100:4.1f}%  P(MDD>=25%) {np.mean(mdd>=.25)*100:4.1f}%")
# single intraday sleeve
for R,label in [(0.0025,'A only R=0.25%'),(0.005,'A only R=0.5%')]:
    for mu_tr,lab2 in [(0.10,'edge+0.10R'),(0.0,'edge 0'),(-0.05,'edge-0.05R')]:
        tr=2.5*D; daily_sdR=2.47
        mu=tr*mu_tr*R - 0.084  # LLM 84k/yr
        sd=daily_sdR*R*np.sqrt(D)
        sim([mu],[sd],[[1]],f"{label} {lab2}")
# combined: A, B iron fly, C MCX trend, D event swing
corr=[[1,-0.2,0.0,0.2],[-0.2,1,-0.1,0.3],[0.0,-0.1,1,0.0],[0.2,0.3,0.0,1]]
def comb(RA,muA,label,B=(0.03,0.039),Cc=(0.015,0.035),Dd=(0.03,0.05),llm=0.06):
    trA=2.5*D
    mA=trA*muA*RA - llm; sA=2.47*RA*np.sqrt(D)
    sim([mA,B[0],Cc[0],Dd[0]],[sA,B[1],Cc[1],Dd[1]],corr,label)
comb(0.0025,0.10,'COMBO A0.25% edge+0.10 others base')
comb(0.0025,0.0,'COMBO A0.25% edge0 others base')
comb(0.0025,0.0,'COMBO A0.25% edge0 others zero',B=(0,0.039),Cc=(0,0.035),Dd=(0,0.05))
comb(0.005,0.10,'COMBO A0.5% edge+0.10 others base')
comb(0.005,0.0,'COMBO A0.5% edge0 others base')
comb(0.0035,0.10,'COMBO A0.35% edge+0.10, D x2',Dd=(0.06,0.10))
