import sys,json,time,traceback,requests
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import backend
from astropy import log;log.setLevel('ERROR')
from backend.main import presets
from backend.archive import discover,fetch_frame,ROOT,atomic_json
report=[]
for p in presets():
 r={'name':p['name'],'coordinate_source':p.get('coordinate_source')}
 try:
  if p.get('ra') is None:raise RuntimeError(p.get('error','Coordinates missing.'))
  rows=discover(p['ra'],p['dec']);r['archive_count']=len(rows);r['first_date']=rows[0]['date'] if rows else None;r['last_date']=rows[-1]['date'] if rows else None;r['frames']=[]
  for row in rows[:2]:
   cache_id,meta=fetch_frame(row,p['ra'],p['dec'],8)
   r['frames'].append({'id':row['id'],'cache_id':cache_id,'mjd':row['mjd'],'detector':row['detector'],'valid_fraction':meta['valid_fraction'],'wavelength_um':meta['wavelength_um']})
  r['pass']=len(r['frames'])==2
 except Exception as e:r.update(error=type(e).__name__+': '+str(e),**{'pass':False});traceback.print_exc()
 report.append(r);atomic_json(ROOT/'docs/preset-live-validation.json',report);print(json.dumps(r),flush=True)
