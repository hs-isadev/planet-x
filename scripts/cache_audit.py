"""Inspect preserved real exposures without downloading or changing science data."""
import sys, json
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.archive import CACHE, ROOT, key_for

def cached_jobs():
    presets=json.loads((CACHE/'presets.json').read_text())
    metadata={}
    for p in CACHE.glob('*.npz'):
        try:
            m=json.loads(p.with_suffix('.json').read_text())
            query=parse_qs(urlsplit(m['cutout_url']).query)
            center=[float(v) for v in query['center'][0].rstrip('d').split(',')]
            metadata.setdefault(urlsplit(m['cutout_url']).path,[]).append((p.stem,m,center))
        except (ValueError,KeyError,FileNotFoundError):continue
    jobs={}
    for preset in presets:
        rows=[]
        for path in CACHE.glob('query-*.json'):
            try:
                candidates=json.loads(path.read_text())
                if not candidates or not isinstance(candidates,list) or 'url' not in candidates[0]:continue
                matched=[]
                for f in candidates:
                    for cid,m,center in metadata.get(urlsplit(f['url']).path,[]):
                        if abs(center[0]-preset['ra'])<1e-7 and abs(center[1]-preset['dec'])<1e-7:
                            matched.append((f,cid,m));break
                if len(matched)>len(rows):rows=matched;manifest=candidates
            except (ValueError,KeyError):continue
        if not rows:continue
        width=rows[0][2]['width'];scale=rows[0][2]['scale_arcsec'];fov=round(width*scale/60,9)
        frames=[]
        for f,cid,m in rows:
            if abs(m['width']*m['scale_arcsec']/60-fov)>1e-6:continue
            frames.append(dict(f,**m,cache_id=cid,status='ready',index=next(i for i,r in enumerate(manifest) if r['id']==f['id']),ra=preset['ra'],dec=preset['dec'],fov=fov))
        jobs[preset['id']]=dict(ra=preset['ra'],dec=preset['dec'],fov=fov,frames=frames,discovered=len(manifest))
    return jobs

if __name__=='__main__':
    from backend.time_science import target_for,prediction,centroid
    from backend.analysis import aperture_measure,group_frames
    from astropy.io import fits
    result={}
    for name,job in cached_jobs().items():
        row=target_for(job);measurements=[];centroids=[]
        for f in job['frames']:
            native=CACHE/(f['cache_id']+'.fits')
            if not native.exists():continue
            pos=prediction(row,f['mjd'])
            with fits.open(native,memmap=False) as h:
                for radius in (18.45,12.3):
                    m=aperture_measure(h,pos,radius)
                    measurements.append(dict(frame=f['index'],radius=radius,wave=f['wavelength_um'],det=f['detector'],**m))
            if name=='barnard':
                try:centroids.append(dict(frame=f['index'],mjd=f['mjd'],det=f['detector'],wave=f['wavelength_um'],**centroid(f,job,pos)))
                except ValueError:pass
        result[name]=dict(cached=len(job['frames']),discovered=job['discovered'],fov=job['fov'],valid_apertures=[m for m in measurements if m['status']=='ok'],centroids=centroids)
        print(name,'cached',len(job['frames']),'apertures',len(result[name]['valid_apertures']),'centroids',len(centroids),flush=True)
    (ROOT/'docs/cache-audit.json').write_text(json.dumps(result,indent=2))
