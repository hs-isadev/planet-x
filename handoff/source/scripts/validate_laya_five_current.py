"""Bounded live model check on preserved real SPHEREx temporal crops."""
import json,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.laya_review import infer,LOCK,availability,shutdown_worker
from backend.archive import CACHE,ROOT
prior=json.loads((ROOT/'docs/pipeline-five-laya.json').read_text(encoding='utf-8'))
report={'scope':'One preserved real temporal crop per science target; not whole-archive coverage or proof of scientific detection.','availability':availability(),'results':[]}
try:
 for target in prior['targets']:
  receipt=json.loads((CACHE/(target['review_id']+'.json')).read_text())
  batch=next(b for b in receipt['batches'] if (CACHE/(receipt['id']+'-'+b['key']+'.png')).exists())
  file=CACHE/(receipt['id']+'-'+batch['key']+'.png');start=time.monotonic()
  with LOCK:
   result=infer(file,'Preserved real SPHEREx temporal crop, target '+target['name']+'. Dates '+str(batch['dates'])+'. Compare visual change only; not calibrated motion detection.',progress=lambda stage:print(target['name'],stage,flush=True))
  choice=result.get('answers',{}).get('change',{}).get('choice')
  if not isinstance(choice,str):raise RuntimeError('Invalid actual model response')
  report['results'].append({'target':target['name'],'dates':batch['dates'],'exposure_ids':batch['exposure_ids'],'crop':batch['crop'],'choice':choice,'seconds':round(time.monotonic()-start,2)})
  (ROOT/'docs/laya-five-current.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
  print('COMPLETE',target['name'],choice,flush=True)
finally:shutdown_worker()
