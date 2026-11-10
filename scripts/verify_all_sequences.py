"""Replay every available real frame for all five targets through the HTTP route."""
import sys,json,hashlib,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
from backend.main import app,JOBS
from backend.archive import CACHE,ROOT
from backend.quicklook import comparable,change_masks
from backend.analysis import load_products
report=[]
with TestClient(app) as client:
    for name in ('barnard','epsilon','wise','rw','rdraconis'):
        job=json.loads((ROOT/'docs'/f'challenge-{name}-manifest.json').read_text())
        frames=sorted([f for f in job['frames'] if f.get('status')=='ready' and all((CACHE/(f['cache_id']+e)).exists() for e in ('.npz','.npy'))],key=lambda f:(f['mjd'],f['index']))
        job['frames']=[dict(f,index=i) for i,f in enumerate(frames)];JOBS['sequence-verification']=job
        result=dict(target=name,discovered=len(json.loads((ROOT/'docs'/f'challenge-{name}-manifest.json').read_text())['frames']),rendered=0,compared=0,frames_with_residuals=0,no_prior_reference=0,errors=[])
        for f in job['frames']:
            try:
                candidates=[b for b in job['frames'] if comparable(f,b) and b['mjd']<f['mjd']]
                ref=max(candidates,key=lambda b:(b['mjd'],b['index'])) if candidates else None
                raw=CACHE/(f['cache_id']+'.npz');before=hashlib.sha256(raw.read_bytes()).hexdigest()
                r=client.get(f"/api/jobs/sequence-verification/frames/{f['index']}.png",params={'enhanced':'true','changes':str(bool(ref)).lower()});assert r.status_code==200,r.text
                image=np.array(Image.open(io.BytesIO(r.content)));red=(image[:,:,0]==245)&(image[:,:,1]==65)&(image[:,:,2]==67)
                assert hashlib.sha256(raw.read_bytes()).hexdigest()==before
                product=load_products(f);assert not change_masks(product,product)['red'].any()
                if ref:
                    expected=np.flipud(change_masks(product,load_products(ref))['red']);assert np.array_equal(red,expected)
                    result['compared']+=1;result['frames_with_residuals']+=int(red.any())
                else:assert not red.any();result['no_prior_reference']+=1
                result['rendered']+=1
            except Exception as e:result['errors'].append(dict(frame=f['index'],error=str(e)))
        result['scope']='All still-cached ready frames from the captured target search, not every discovered archive file.'
        result['interpretation']='Field residual candidates; neither confirmed motion nor confirmed variability of the named target.'
        report.append(result);print(json.dumps(result),flush=True)
        (ROOT/'docs/all-sequence-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
assert len(report)==5 and all(r['rendered'] and not r['errors'] for r in report)
