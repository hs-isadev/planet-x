import requests,json,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
r=requests.get('http://127.0.0.1:8000/api/space',params=dict(scope='nearby',radius_pc=10,include_simbad=True),timeout=150)
print('SPACE',r.status_code,flush=True)
if r.ok:
 d=r.json();(R/'docs/nearby-live-validation.json').write_text(json.dumps(d,indent=2));print('Known',len(d['objects']),'unknown',len(d['unknown']),'fallback',d['fallback_count'],'named',[x['name'] for x in d['objects'][:10]],'notes',d['notes'][:2],flush=True)
else:print(r.text,flush=True)
