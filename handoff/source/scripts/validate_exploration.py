import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import backend
import numpy as np
from PIL import Image
from backend.archive import ROOT,CACHE
from backend.quicklook import enhanced_rgba,load_products,comparable,standardized
from backend.exploration import journey_context
earth=json.loads((ROOT/'web/assets/surface-earth.json').read_text())
assert earth['n']**2==len(earth['heights_m']) and np.isfinite(earth['heights_m']).all()
assert min(earth['heights_m'])>3000 and max(earth['heights_m'])<4300
c=journey_context(ra=37.95456067,dec=89.26410897,distance_pc=132)
assert c['constellation']=='Ursa Minor' and abs(np.linalg.norm(c['direction_ecliptic'])-1)<1e-8
frames=json.loads((ROOT/'docs/data-proof/wise-d6-frames.json').read_text())
ready=[f for f in frames if (CACHE/(f['cache_id']+'.npz')).exists()]
if not any(comparable(a,b) for a in ready for b in ready):
    # Match genuine alternate-FOV/release cache products by immutable exposure ID,
    # sky center and grid. Observation dates remain those in the real manifest.
    from urllib.parse import urlsplit,parse_qs
    ready=[]
    for product in CACHE.glob('*.npz'):
        metadata=product.with_suffix('.json')
        if not metadata.exists():continue
        try:
            meta=json.loads(metadata.read_text());url=meta.get('cutout_url','');center=parse_qs(urlsplit(url).query).get('center',[''])[0].rstrip('d').split(',')
            if len(center)!=2 or abs(float(center[0])-133.79512916666667)>1e-7 or abs(float(center[1])+7.245147222222222)>1e-7:continue
            frame=next((f for f in frames if f['observation'] in url),None)
            if frame:ready.append({**frame,**meta,'cache_id':product.stem,'wavelength_um':meta['wavelength_um']})
        except (ValueError,KeyError):continue
pair=next(((a,b) for a in ready for b in ready if comparable(a,b) and a.get('width')==b.get('width') and a.get('scale_arcsec')==b.get('scale_arcsec')),None)
assert pair,'Real comparable SPHEREx analysis products required for this focused validation'
a,b=pair;before=load_products(a);img=enhanced_rgba(a,b);after=load_products(a)
assert np.array_equal(before['value'],after['value'],equal_nan=True)
assert (img[...,3]>0).sum()==(np.isfinite(before['value'])&np.isfinite(before['variance'])&(before['variance']>0)).sum()
Image.fromarray(np.flipud(img)).resize((632,632),Image.Resampling.NEAREST).save(ROOT/'docs/data-proof/wise-computed-residual.png')
report=dict(measured_terrain_samples=len(earth['heights_m']),terrain_elevation_m=[min(earth['heights_m']),max(earth['heights_m'])],constellation=c['constellation'],real_frames_available=len(ready),reference_dates=[a['date'],b['date']],red_residual_pixels=int(((img[...,0]==245)&(img[...,1]==65)).sum()),raw_arrays_unchanged=True,mask_preserved=True,note='Red residuals are computed candidates, not confirmed moving sources. Similar bandpasses, not a PSF-matched subtraction.')
(ROOT/'docs/exploration-validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
