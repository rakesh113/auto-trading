# Scratch cost model from the LLM cost/latency research (report 14). Run from this folder: python llm_cost_profiles.py
import sys; sys.path.insert(0,'.')
exec(open('llm_cost_model.py').read().split("W = 4.3")[0].replace("for k,v in U.items()","for k,v in []"))
W=4.3
profile('LEAN v2', [
 ('plan_sonnet',1),('refresh_haiku',1),('rank_haiku',30),('triage',300),('mat_haiku',10),
 ('dec_sonnet',50),('dec_haiku',50),('dec_haiku_chart',50),('mgmt_sonnet',8),('mgmt_haiku',25),
 ('rev_trade_haiku',10),('eod_sonnet',1),
 ('pw_sonnet', prefix_writes('sonnet')),('pw_haiku', prefix_writes('haiku')),
], monthly_extra=U['weekly_opus']*W)
profile('TARGET v2', [
 ('plan_opus',1),('refresh_sonnet',1),('rank_haiku',30),('triage',400),('mat_sonnet',6),('mat_haiku',10),
 ('dec_sonnet',60),('dec_haiku',60),('dec_haiku_chart',60),('dec_sonnet_chart',20),('dec_luna',20),('mgmt_sonnet',15),('mgmt_haiku',20),
 ('rev_trade_haiku',12),('eod_sonnet',1),
 ('pw_sonnet', prefix_writes('sonnet')),('pw_haiku', prefix_writes('haiku')),
], monthly_extra=U['weekly_opus']*W)
profile('STRETCH v2', [
 ('plan_opus',1),('refresh_sonnet',1),('rank_haiku',40),('triage',400),('mat_sonnet',10),('mat_haiku',10),
 ('dec_sonnet',80),('dec_haiku',80),('dec_haiku_chart',80),('dec_sonnet_chart',40),('dec_luna',80),('dec_opus',5),('sc_haiku',30),
 ('mgmt_sonnet',35),('mgmt_haiku',10),
 ('rev_trade_haiku',12),('eod_opus',1),
 ('pw_sonnet', prefix_writes('sonnet')),('pw_haiku', prefix_writes('haiku')),('pw_opus', prefix_writes('opus',3)),
], monthly_extra=U['weekly_opus']*W)
