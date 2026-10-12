# Scratch Monte Carlo with the drawdown ladder, from the portfolio and risk review (report 23).
import numpy as np
rng=np.random.default_rng(11)
D=250; Y=2; N=8000
corr=np.array([[1,-0.2,0.0,0.2],[-0.2,1,-0.1,0.3],[0.0,-0.1,1,0.0],[0.2,0.3,0.0,1]])
L=np.linalg.cholesky(corr)
def run(RA,muA,others=True,policy='none',llm=0.06,df=4,label=''):
    trA=2.5*D
    mu=np.array([trA*muA*RA, 0.03 if others else 0, 0.015 if others else 0, 0.03 if others else 0])/D
    sd=np.array([2.47*RA*np.sqrt(D),0.039,0.035,0.05])/np.sqrt(D)
    fixed=llm/D
    res=[];mdds=[]
    for i in range(N):
        z=rng.standard_normal((D*Y,4))@L.T
        w=np.sqrt(rng.chisquare(df,(D*Y,1))/df); z=z/w*np.sqrt((df-2)/df)
        r=mu+sd*z
        eq=1.0;peak=1.0;mdd=0;eq1=None
        for t in range(D*Y):
            dd=1-eq/peak
            if policy=='ladder':
                s=1.0 if dd<.05 else .75 if dd<.10 else .5 if dd<.15 else .35 if dd<.20 else .25 if dd<.25 else 0
            elif policy=='gz':  # risk proportional to cushion above 25% floor of running max, x1.6 capped at 1
                s=min(1.0,max(0.0,1.6*(0.25-dd)/0.25))
            else: s=1.0 if dd<.25 else 0
            if s==0: break
            eq*= 1+ s*r[t].sum() - fixed
            peak=max(peak,eq); mdd=max(mdd,1-eq/peak)
            if t==D-1: eq1=eq
        if eq1 is None: eq1=eq
        res.append(eq1-1); mdds.append(mdd)
    res=np.array(res); mdds=np.array(mdds)
    print(f"{label:44s} {policy:6s} mean1y {res.mean()*100:5.1f}% P(yr<0) {np.mean(res<0)*100:3.0f}% medMDD2y {np.median(mdds)*100:4.1f}% P(MDD>=20%) {np.mean(mdds>=.2)*100:4.1f}% P(hit25%) {np.mean(mdds>=.2499)*100:4.1f}%")
for pol in ['none','ladder','gz']:
    run(0.0025,0.10,True,pol,label='COMBO A0.25 edge+0.10')
    run(0.0025,0.0,True,pol,label='COMBO A0.25 edge0, others base')
    run(0.005,0.0,True,pol,label='COMBO A0.5 edge0, others base')
    run(0.005,0.10,True,pol,label='COMBO A0.5 edge+0.10')
