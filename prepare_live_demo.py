"""Prepare two real released exposures for the browser analysis checks."""
import backend,requests,time,json
from backend.archive import CACHE,ROOT
from backend.analysis import aperture_measure,sky_at_click
from astropy.io import fits
base='http://127.0.0.1:8000'
def wait(identity):
 for _ in range(180):
  job=requests.get(base+'/api/jobs/'+identity,timeout=10).json()
  if job['status'] not in ('querying','fetching'):return job
  time.sleep(1)
 raise RuntimeError('Timed out')
response=requests.post(base+'/api/archive/open',json={'key':None,'fov':8},timeout=10);response.raise_for_status();identity=response.json()['id'];job=wait(identity)
assert job['status']=='complete',job
key=job['frames'][0]['source_key'].replace('_0001_1D1_','_0001_2D1_')
# Verify the second key exists in a real bucket listing; never infer a nonexistent URL.
listing=requests.get(base+'/api/archive',params={'prefix':key.rsplit('/',1)[0]+'/'},timeout=20).json()
assert key in [f['key'] for f in listing['files']]
response=requests.post(base+'/api/archive/open',json={'key':key,'fov':8,'append_to':identity},timeout=10);response.raise_for_status();job=wait(identity)
print(json.dumps({'id':identity,'status':job['status'],'frames':len(job['frames']),'append_error':job.get('append_error'),'metadata':[{k:f.get(k) for k in ['mjd','wavelength_um','valid_fraction','source_key']} for f in job['frames']]},indent=2),flush=True)
assert len(job['frames'])==2,job.get('append_error')
groups=requests.get(base+f'/api/jobs/{identity}/groups',timeout=10).json()
print('GROUPS',json.dumps(groups),flush=True)
for mode in ['subtract','add']:
 r=requests.get(base+f'/api/jobs/{identity}/computed',params={'mode':mode,'a':0,'b':1},timeout=20)
 print(mode,r.status_code, str(r.json().get('display',r.json()))[:300],flush=True)
 assert r.status_code==200
 (ROOT/'docs'/f'live-{mode}.png').write_bytes(__import__('base64').b64decode(r.json()['image'].split(',')[1]))
for group in groups['groups']:
 if len(group['frames'])>=2:
  r=requests.get(base+f'/api/jobs/{identity}/computed',params={'mode':'stack','group':group['id']},timeout=20);r.raise_for_status();print('STACK',r.json()['display'],flush=True)
  (ROOT/'docs'/'live-stack.png').write_bytes(__import__('base64').b64decode(r.json()['image'].split(',')[1]))
  break
# Find a usable real native aperture without declaring it to be a named source.
frame=job['frames'][0]
with fits.open(CACHE/(frame['cache_id']+'.fits')) as h:
 found=None
 for y in [.3,.4,.5,.6,.7]:
  for x in [.3,.4,.5,.6,.7]:
   m=aperture_measure(h,sky_at_click(job,x,y),18.45)
   if m['status']=='ok':found=(x,y,m);break
  if found:break
 if found:print('SPECTRUM_POSITION',json.dumps(found),flush=True)
 else:print('NO COMPLETE APERTURE FOUND IN SCANNED POSITIONS',flush=True)
(ROOT/'docs'/'live-analysis-results.json').write_text(json.dumps({'job':identity,'frames':len(job['frames']),'keys':[f['source_key'] for f in job['frames']],'groups':groups,'aperture_position':found[:2] if found else None},indent=2))
