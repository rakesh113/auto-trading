# Scratch cost model from the LLM cost/latency research (report 14).
# USD per MTok: in, cw5, cw1h, cr, out
P = {
 'haiku':  (0.10, 0.125, 0.20, 0.01, 0.50),
 'sonnet': (2.0, 2.5, 4.0, 0.10, 10.0),
 'opus':   (4.0, 5.0, 8.0, 0.20, 20.0),
 'luna':   (0.20, 0.20, 0.20, 0.02, 1.20),   # GPT-5.6 Luna (L-M), cache read assumed 0.1x
 'dsflash':(0.30, 0.30, 0.30, 0.006, 1.20),  # DeepSeek v4.1 Flash OR main listing (M)
}
FX = 95*1.055   # Rs per list USD incl. OpenRouter 5.5% credit fee
DAYS = 21
def call(m, unc=0, cr=0, cw1h=0, cw5=0, out=0, img=0):
    i,w5,w1,r,o = P[m]
    return ((unc+img)*i + cw5*w5 + cw1h*w1 + cr*r + out*o)/1e6
def img_tokens(w,h):
    import math; return math.ceil(w/28)*math.ceil(h/28)
CHART = img_tokens(1000,700)   # 900
PREFIX = 6000   # shared static prefix: system+playbook+tactics+schema
def prefix_writes(m, n=7): return call(m, cw1h=PREFIX)*n   # 1h TTL refresh ~7x/day/model

# unit costs
U = {}
U['plan_opus']   = call('opus',  unc=36000, img=9*CHART, out=14000)
U['plan_sonnet'] = call('sonnet',unc=36000, img=9*CHART, out=12000)
U['refresh_sonnet']=call('sonnet',unc=9000, out=2500)
U['refresh_haiku'] = call('haiku', unc=9000, out=2000)
U['rank_haiku']  = call('haiku', unc=1500, out=150)            # x30 candidates
U['triage']      = call('haiku', cr=2500, unc=1200, out=150)
U['mat_sonnet']  = call('sonnet',unc=6000, out=2000)
U['mat_haiku']   = call('haiku', unc=6000, out=1200)
U['dec_sonnet']  = call('sonnet',cr=PREFIX, unc=3000, out=850)
U['dec_sonnet_chart'] = call('sonnet',cr=PREFIX, unc=3000, img=CHART, out=900)
U['dec_haiku']   = call('haiku', cr=PREFIX, unc=3000, out=400)
U['dec_haiku_chart'] = call('haiku', cr=PREFIX, unc=3000, img=CHART, out=400)
U['dec_opus']    = call('opus',  cr=PREFIX, unc=3500, img=CHART, out=1500)
U['sc_haiku']=call('haiku', cr=PREFIX, unc=3000, out=400)
U['dec_luna']    = call('luna',  cr=PREFIX, unc=3000, out=600)
U['dec_ds']      = call('dsflash',cr=PREFIX, unc=3000, out=600)
U['mgmt_sonnet'] = call('sonnet',cr=PREFIX, unc=2000, out=550)
U['mgmt_haiku']  = call('haiku', cr=PREFIX, unc=2000, out=300)
U['rev_trade_haiku'] = call('haiku', unc=8000, out=1500)
U['rev_trade_sonnet']= call('sonnet', unc=8000, out=1500)
U['eod_sonnet']  = call('sonnet',unc=30000, out=5000)
U['eod_opus']    = call('opus',  unc=30000, out=6000)
U['weekly_opus'] = call('opus',  unc=80000, out=16000)
for k,v in U.items(): print(f"{k:18s} ${v:.5f}  Rs {v*FX:.3f}")
print('chart tokens', CHART, img_tokens(1092,1092), img_tokens(1456,816), img_tokens(1280,720), img_tokens(800,500))

def profile(name, daily, monthly_extra=0.0, contingency=0.15):
    d = sum(U[k]*n if k in U else n for k,n in daily)
    m = d*DAYS + monthly_extra
    tot = m*(1+contingency)
    print(f"\n== {name}: ${d:.3f}/day, ${m:.1f}/mo, +{int(contingency*100)}% cont = ${tot:.1f} = Rs {tot*FX:,.0f}/mo")
    for k,n in daily:
        c = (U[k]*n if k in U else n)
        print(f"   {k:18s} x{n if k in U else '-':>4}  ${c:.3f}/day  Rs {c*DAYS*FX:,.0f}/mo")
    print(f"   monthly extra ${monthly_extra:.2f} Rs {monthly_extra*FX:,.0f}")
    return tot*FX

W = 4.3
lean = profile('LEAN', [
 ('plan_sonnet',1),('refresh_haiku',1),('rank_haiku',30),('triage',300),('mat_haiku',10),
 ('dec_sonnet',40),('dec_haiku',40),('mgmt_haiku',30),
 ('rev_trade_haiku',10),('eod_sonnet',1),
 ('pw_sonnet', prefix_writes('sonnet')),('pw_haiku', prefix_writes('haiku')),
], monthly_extra=U['weekly_opus']*W)

target = profile('TARGET', [
 ('plan_opus',1),('refresh_sonnet',1),('rank_haiku',30),('triage',400),('mat_sonnet',6),('mat_haiku',10),
 ('dec_sonnet',60),('dec_haiku',60),('dec_sonnet_chart',20),('mgmt_sonnet',15),('mgmt_haiku',20),
 ('rev_trade_haiku',12),('eod_sonnet',1),
 ('pw_sonnet', prefix_writes('sonnet')),('pw_haiku', prefix_writes('haiku')),
], monthly_extra=U['weekly_opus']*W)

stretch = profile('STRETCH', [
 ('plan_opus',1),('refresh_sonnet',1),('rank_haiku',40),('triage',400),('mat_sonnet',12),('mat_haiku',10),
 ('dec_sonnet',80),('dec_haiku',80),('dec_sonnet_chart',80),('dec_luna',80),('dec_opus',8),('dec_haiku',2*16),
 ('mgmt_sonnet',40),
 ('rev_trade_sonnet',12),('eod_opus',1),
 ('pw_sonnet', prefix_writes('sonnet')),('pw_haiku', prefix_writes('haiku')),('pw_opus', prefix_writes('opus',3)),
], monthly_extra=U['weekly_opus']*W)

# paired arm marginal costs per month at 60 moments/day
print('\nPaired-arm marginal Rs/month @60 moments/day:')
for k in ['dec_haiku','dec_haiku_chart','dec_sonnet','dec_sonnet_chart','dec_luna','dec_ds','dec_opus']:
    for frac in (1.0,0.33):
        print(f"  {k:18s} frac {frac:.2f}: Rs {U[k]*60*frac*DAYS*FX:,.0f}")
