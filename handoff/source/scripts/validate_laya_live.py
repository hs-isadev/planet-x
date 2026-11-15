import sys,json,runpy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));import backend
from backend.laya_review import review_pair,REVIEWS,installed
print('Laya installation detected',installed(),flush=True)
proof=runpy.run_path(str(ROOT/'scripts/validate_exploration.py'))
a,b=proof['pair'];a=dict(a,index=0);b=dict(b,index=1);identity='laya-live-smoke';REVIEWS[identity]={'status':'running'}
result=review_pair(a,b,identity)
(ROOT/'docs/laya-live-validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result),flush=True)
