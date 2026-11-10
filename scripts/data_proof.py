"""Live WISE 0855 proof. Never substitutes a different field or adds motion."""
import sys, json, traceback, argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import backend
from astropy import log
log.setLevel('ERROR')
import requests, pyvo, numpy as np
from PIL import Image
from backend.archive import CONFIG, CACHE, discover, fetch_frame, atomic_json
OUT=Path(__file__).resolve().parents[1]/'docs/data-proof'
OUT.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--fov',type=float,default=8);args=parser.parse_args()
ra,dec=133.79512916666667,-7.245147222222222
report={'target':'WISE 0855','ra':ra,'dec':dec,'frames_returned':0,'motion_confirmed':False,'fov_arcmin':args.fov,'errors':[]}
session=requests.Session()
original=session.request
session.request=lambda *a,**kw:original(*a,**dict({'timeout':20},**kw))
try:
    service=pyvo.dal.TAPService(CONFIG['tap_endpoint'],session=session)
    schema=service.search("SELECT table_name, column_name, datatype FROM TAP_SCHEMA.columns WHERE table_name IN ('spherex.artifact','spherex.plane')",maxrec=2000).to_table()
    report['schema']=[{k:str(r[k]) for k in schema.colnames} for r in schema]
    required={'spherex.artifact':{'uri','planeid'},'spherex.plane':{'planeid','poly','time_bounds_lower','energy_bandpassname'}}
    for table,cols in required.items():
        got={str(r['column_name']) for r in schema if str(r['table_name'])==table}
        if not cols<=got: raise RuntimeError('Required documented columns not found in live service: '+table)
    atomic_json(CACHE/'verified-spherex-schema.json',report['schema'])
    rows=discover(ra,dec)
    report['archive_rows']=len(rows)
    atomic_json(OUT/'report.json',report)
    print(f'Archive rows: {len(rows)}',flush=True)
    priority=[r for r in rows if r['detector']==6]
    order=priority[::max(1,len(priority)//8)]+priority[-2:]+rows
    seen=set()
    for i,row in enumerate(order):
        if row['id'] in seen:continue
        seen.add(row['id'])
        try:
            identity,meta=fetch_frame(row,ra,dec,args.fov)
            values=np.load(CACHE/(identity+'.npy'))
            report.setdefault('frames',[]).append(dict(row,**meta,cache_id=identity))
            np.save(OUT/f'{row["mjd"]:.6f}-{row["id"]}.npy',values)
            report['frames_returned']=len(report['frames'])
            report['frames'].sort(key=lambda f:f['mjd'])
            atomic_json(OUT/'report.json',report)
            print(f'{len(report["frames"])} frames ready; D{row["detector"]} {row["date"]} {meta.get("wavelength_um")}',flush=True)
        except Exception as exc: report['errors'].append(type(exc).__name__+': '+str(exc)[:300])
    frames=report.get('frames',[])
    report['frames_returned']=len(frames)
    if frames:
        arrays=[np.load(OUT/f'{f["mjd"]:.6f}-{f["id"]}.npy') for f in frames]
        lo,hi=np.nanpercentile(arrays[0],[1,99.7])
        for i,a in enumerate(arrays):
            v=np.arcsinh(10*np.clip((a-lo)/(hi-lo),0,1))/np.arcsinh(10)
            Image.fromarray(np.flipud(np.nan_to_num(v)*255).astype('uint8')).save(OUT/f'{i:04d}.png')
        report['note']='Inspect same-detector, similar-wavelength epochs. No motion claim without a securely identified source and meaningful time baseline.'
except Exception as exc:
    report['errors'].append(type(exc).__name__+': '+str(exc)[:800])
    report['note']='Archive discovery unavailable from this runtime. Zero WISE 0855 frames retrieved; motion is unverified. Run this script on a network that can reach IRSA TAP.'
atomic_json(OUT/'report.json',report)
print(json.dumps(report,indent=2),flush=True)
sys.exit(0 if report['frames_returned'] else 2)
