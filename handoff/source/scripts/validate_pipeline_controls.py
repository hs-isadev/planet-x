"""Offline diagnostic experiments. Synthetic injections NEVER enter the viewer cache."""
import json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import backend
import numpy as np
from backend.archive import CACHE
from backend.quicklook import change_masks
rng=np.random.default_rng(20261111)
products=[]
for path in sorted(CACHE.glob('*.npz')):
    try:
        with np.load(path,allow_pickle=False) as z:
            p={k:z[k].copy() for k in z.files}
        good=np.isfinite(p['value']) & np.isfinite(p['variance']) & (p['variance']>0) & np.isfinite(p['wavelength'])
        if good.mean()>.8 and min(good.shape)>=30:
            products.append((path.stem,p,good))
        if len(products)==12:break
    except (OSError,ValueError,KeyError):pass
if not products:raise RuntimeError('No genuine registered cache products available; no synthetic replacement field generated.')
controls=[]
for cid,p,good in products:
    r=change_masks(p,p)
    controls.append(dict(cache_id=cid,valid_pixels=int(good.sum()),flagged_pixels=int(r['red'].sum())))
# Registration and PSF stress tests on the same real exposure. No object is moved.
from scipy.ndimage import shift, gaussian_filter
stress=[]
for cid, original, good in products:
    for kind, transform in [
        ('registration_shift_0.65px', lambda a: shift(a,(0,.65),order=1,mode='constant',cval=0,prefilter=False)),
        ('psf_blur_sigma_0.8px', lambda a: gaussian_filter(a,.8,mode='constant',cval=0))]:
        support=transform(good.astype(float))>=.999
        comparison=dict(original)
        comparison['value']=np.where(support,transform(np.where(good,original['value'],0)),np.nan)
        measured=change_masks(comparison,original)
        stress.append(dict(cache_id=cid,kind=kind,eligible_pixels=int(measured['comparable'].sum()),
            red_pixels=int(measured['red'].sum())))
if '--stress-only' in sys.argv:
    path=Path('docs/pipeline-controls.json')
    report=json.loads(path.read_text())
    report['registration_psf_stress']=stress
    path.write_text(json.dumps(report,indent=2))
    print(json.dumps(stress,indent=2))
    sys.exit(0)
results=[]
for kind in ['stationary_control','variable','moving']:
    for amplitude in [3,5,8,12]:
        recovered=0;trials=0;outside_pixels=0;tested_pixels=0
        for cid,original,good in products:
            h,w=good.shape;yy,xx=np.mgrid[:h,:w]
            from scipy.ndimage import binary_erosion
            interior=binary_erosion(good,structure=np.ones((13,13)))
            locations=np.argwhere(interior)
            if not len(locations):continue
            for attempt in range(10):
                y,x=locations[int(rng.integers(len(locations)))]
                if x<7 or y<7 or x>w-8 or y>h-8 or not good[y-6:y+7,x-6:x+7].all():continue
                a={k:v.copy() for k,v in original.items()};b={k:v.copy() for k,v in original.items()}
                sigma=np.sqrt(original['variance'])
                # Independent additional noise; variance updated, source array untouched.
                for p in (a,b):
                    p['value']=p['value']+rng.normal(size=(h,w))*sigma
                    p['variance']=2*p['variance']
                scale=float(np.sqrt(2*original['variance'][y,x]))
                gauss=lambda cx:amplitude*scale*np.exp(-((xx-cx)**2+(yy-y)**2)/(2*1.0**2))
                a['value']+=gauss(x)
                if kind=='stationary_control':b['value']+=gauss(x)
                elif kind=='moving':b['value']+=gauss(x+2)
                # Variable is appearance/disappearance, not motion.
                result=change_masks(b,a)['red']
                region=((xx-x)**2+(yy-y)**2<=16)|((xx-x-2)**2+(yy-y)**2<=16)
                recovered+=int(result[region].any());trials+=1
                outside_pixels+=int((result&~region&good).sum());tested_pixels+=int((good&~region).sum())
        results.append(dict(kind=kind,peak_snr=amplitude,trials=trials,flagged_trials=recovered,
            recovery_rate=None if kind=='stationary_control' else recovered/max(1,trials),
            false_positive_trial_rate=recovered/max(1,trials) if kind=='stationary_control' else None,
            outside_injection_flagged_pixel_rate=outside_pixels/max(1,tested_pixels)))
report=dict(seed=20261111,real_products=len(products),unchanged_real_controls=controls,synthetic_injections=results,registration_psf_stress=stress,
    limitations=['These test arrays never enter cache or public observation manifests.',
        'Injection recovery measures residual highlighting, NOT reliable motion classification or Laya accuracy.',
        'Unchanged real-exposure copies test identity; they are not independent observations.',
        'Injected Gaussian PSF sigma=1 registered pixel; 2-pixel motion is easier than subpixel proper motion.',
        'Real background plus independent extra noise is a controlled experiment, not a full instrument simulator.',
        'No catalog-certified stable multi-epoch field or astronomical Laya ground-truth set; empirical astronomical false-positive rate remains unvalidated.'])
Path('docs/pipeline-controls.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
