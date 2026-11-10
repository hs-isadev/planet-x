"""End-to-end real localhost/IRSA checks. Never manufactures a detection."""
import sys,json,time
from pathlib import Path
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.archive import ROOT
base='http://127.0.0.1:8000';report=[]
presets=requests.get(base+'/api/presets',timeout=15).json()
for p in presets:
    result=dict(name=p['name'],pass_render=False)
    try:
        r=requests.post(base+'/api/search',json=dict(ra=str(p['ra']),dec=str(p['dec']),fov=12 if p['id']=='barnard' else 8),timeout=20);r.raise_for_status();identity=r.json()['id']
        deadline=time.monotonic()+100;pair=None
        while time.monotonic()<deadline:
            r=requests.get(base+'/api/jobs/'+identity,timeout=15);r.raise_for_status();job=r.json()
            ready=[f for f in job['frames'] if f.get('status')=='ready' and f.get('wavelength_um') is not None]
            pairs=[(b['mjd']-a['mjd'],a,b) for a in ready for b in ready if b['mjd']-a['mjd']>=1 and a['detector']==b['detector'] and abs(a['wavelength_um']-b['wavelength_um'])<=.025]
            if pairs:pair=max(pairs,key=lambda x:x[0]);break
            if job['status'] in ('error','empty','complete'):break
            time.sleep(2)
        result.update(discovered=len(job['frames']),ready=len(ready),chronological=all(a['mjd']<=b['mjd'] for a,b in zip(job['frames'],job['frames'][1:])))
        selected=pair[1:] if pair else ready[:1]
        for f in selected:
            r=requests.get(base+f"/api/jobs/{identity}/frames/{f['index']}.png",params={'cmap':'gray'},timeout=30);r.raise_for_status();assert r.content.startswith(b'\x89PNG')
        result['pass_render']=bool(selected)
        if pair:result.update(comparable_baseline_days=pair[0],dates=[f['date'] for f in selected],detector=selected[0]['detector'],wavelengths=[f['wavelength_um'] for f in selected])
        else:result['comparison_status']='No comparable date pair loaded in the validation window.'
        (ROOT/'docs'/('challenge-'+p['id']+'-manifest.json')).write_text(json.dumps(job),encoding='utf-8')
        # This verification owns the search; leave data available, stop extra downloads.
        requests.post(base+'/api/jobs/'+identity+'/pause',timeout=15)
    except Exception as e:result['error']=str(e)
    report.append(result);(ROOT/'docs/challenge-http-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)
