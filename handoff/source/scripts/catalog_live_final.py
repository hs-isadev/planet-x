import requests,time,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
for _ in range(90):
 try:
  if requests.get('http://127.0.0.1:8000/api/health',timeout=1).ok:break
 except requests.RequestException:pass
 time.sleep(.5)
s=requests.post('http://127.0.0.1:8000/api/search',json={'ra':'133.79512916666664','dec':'-7.245147222222222','fov':8},timeout=15).json();identity=s['id']
for _ in range(180):
 d=requests.get('http://127.0.0.1:8000/api/jobs/'+identity,timeout=10).json()
 if d.get('ready'):break
 time.sleep(1)
index=next(f['index'] for f in d['frames'] if f['status']=='ready');report={'job':identity,'frame':index}
for catalog in ['gaia','wise']:
 try:
  response=requests.get(f'http://127.0.0.1:8000/api/jobs/{identity}/catalog',params={'frame':index,'catalog':catalog},timeout=150)
  result=response.json();report[catalog]={'status':response.status_code,'markers':len(result.get('markers',[])),'notes':result.get('notes',result.get('detail'))};print(catalog,report[catalog],flush=True)
 except Exception as e:report[catalog]={'error':str(e)};print(catalog,str(e),flush=True)
(R/'docs/catalog-overlay-live-validation.json').write_text(json.dumps(report,indent=2))
