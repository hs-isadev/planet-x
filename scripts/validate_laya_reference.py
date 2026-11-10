import sys,runpy,time,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));import backend
from fastapi.testclient import TestClient
from backend.main import app,JOBS
proof=runpy.run_path(str(ROOT/'scripts/validate_exploration.py'))
a,b=proof['pair'];a=dict(a,index=0,status='ready');b=dict(b,index=1,status='pending')
JOBS['automatic-reference-check']=dict(frames=[a,b],ra=133.79512916666667,dec=-7.245147222222222,fov=8)
client=TestClient(app);r=client.post('/api/jobs/automatic-reference-check/laya?frame=0')
assert r.status_code==200,r.text
result=r.json();print('START',result,flush=True)
for _ in range(220):
 result=client.get('/api/laya/reviews/'+result['id']).json()
 if result['status']!='running':break
 time.sleep(1)
assert result['status']=='complete',result
assert b['status']=='ready'
(ROOT/'docs/laya-auto-reference-validation.json').write_text(json.dumps(result,indent=2))
print('PASS automatic real reference load and Laya review',result['dates'],flush=True)
