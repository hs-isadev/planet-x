"""Record current real-cache evidence without any external network operation."""
import sys,json,hashlib,base64,warnings
from pathlib import Path
warnings.filterwarnings('ignore')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.cache_audit import cached_jobs
from backend.archive import ROOT,CACHE
from backend.time_science import analyze_available,lightcurve_analysis
from backend.catalogs import catalog_overlay
from backend.companions import planets_for
from backend import main
import numpy as np

report=dict(validation='Synchronous handlers and preserved real observations; ASGI, browser and fresh network access are not verified.',targets={},motion=None,lightcurves={})
jobs=cached_jobs()
for name,job in jobs.items():
    f=job['frames'][0];raw=CACHE/(f['cache_id']+'.npy');a=np.load(raw,allow_pickle=False)
    before=hashlib.sha256(raw.read_bytes()).hexdigest();lo,hi=np.nanpercentile(a,[1,99.7])
    main.JOBS['cached-release-check']=dict(job,frames=[dict(f,index=0)],contrast=dict(black=float(lo),white=float(max(hi,lo+1e-6))))
    response=main.frame_png('cached-release-check',0,cmap='gray',stretch='asinh')
    assert response.body.startswith(b'\x89PNG') and response.media_type=='image/png'
    assert hashlib.sha256(raw.read_bytes()).hexdigest()==before
    assert f['provenance']=='observed' and f['url'].startswith('https://irsa.ipac.caltech.edu/ibe/data/spherex/')
    assert all(a['mjd']<=b['mjd'] for a,b in zip(job['frames'],job['frames'][1:]))
    report['targets'][name]=dict(cached=len(job['frames']),discovered=job['discovered'],rendered_png_bytes=len(response.body),fov=job['fov'],first_date=f['date'],url=f['url'],raw_unchanged=True)
    print(name,'real PNG rendered, source array unchanged',flush=True)
try:
    motion=analyze_available(jobs['barnard']);image=motion.pop('image');(ROOT/'docs/review-barnard-difference.png').write_bytes(base64.b64decode(image.split(',',1)[1]));report['motion']=motion
except ValueError as e:
    report['motion']=dict(error=str(e))
    (ROOT/'docs/review-barnard-difference.png').unlink(missing_ok=True)
for name in ('rw','rdraconis'):
    try:report['lightcurves'][name]=lightcurve_analysis(jobs[name])
    except ValueError as e:report['lightcurves'][name]=dict(error=str(e))
# Call only the exact cached catalog footprint, never a new remote query.
wise=jobs['wise'];radius=wise['fov']/60/np.sqrt(2)+120/3600
for kind in ('gaia','wise'):
    try:
        overlay=catalog_overlay(wise,0,kind)
        report[kind+'_overlay']=dict(markers=len(overlay['markers']),motion_applied=sum(r['motion_applied'] for r in overlay['markers']),notes=overlay['notes'])
    except Exception as e:report[kind+'_overlay']=dict(error=str(e))
planets=planets_for(269.4520769586187,4.693364966576667,"Barnard's Star")
assert len(planets)==4
report['barnard_planets']=planets
main.JOBS.pop('cached-release-check',None)
(ROOT/'docs/revision-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k in ('gaia_overlay','wise_overlay')}),flush=True)
print('Wrote docs/revision-validation.json',flush=True)
