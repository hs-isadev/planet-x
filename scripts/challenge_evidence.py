"""Inspectable real-epoch panels and conservative residual counts, not discoveries."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image,ImageDraw
from backend.archive import ROOT,CACHE
from backend.analysis import load_products
from backend.quicklook import comparable,change_masks
out=ROOT/'docs/challenge-evidence';out.mkdir(exist_ok=True);report=[]
for path in sorted((ROOT/'docs').glob('challenge-*-manifest.json')):
    job=json.loads(path.read_text());name=path.stem.removeprefix('challenge-').removesuffix('-manifest')
    ready=[f for f in job['frames'] if f.get('status')=='ready' and (CACHE/(f['cache_id']+'.npz')).exists()]
    pairs=[(min(a.get('valid_fraction',1),b.get('valid_fraction',1))>=.5,b['mjd']-a['mjd'],a,b) for a in ready for b in ready if b['mjd']>a['mjd'] and comparable(a,b)]
    row=dict(target=name,loaded=len(ready),discovered=len(job['frames']))
    if not pairs:row['status']='No compatible loaded epoch pair';report.append(row);continue
    _,span,a,b=max(pairs,key=lambda p:p[:2]);pa,pb=load_products(a),load_products(b);mask=change_masks(pb,pa)
    hashes={f['cache_id']:hashlib.sha256((CACHE/(f['cache_id']+'.npz')).read_bytes()).hexdigest() for f in (a,b)}
    valid=np.concatenate([p['value'][np.isfinite(p['value'])] for p in (pa,pb)]);lo,hi=np.percentile(valid,[1,99.5])
    def draw(p):
        v=p['value'];norm=np.arcsinh(5*np.clip((np.nan_to_num(v,nan=lo)-lo)/max(hi-lo,1e-12),0,1))/np.arcsinh(5)
        return np.repeat((norm*255).astype('u1')[...,None],3,axis=2)
    ia,ib=draw(pa),draw(pb);red=ib.copy();red[mask['red']]=[245,65,67]
    canvas=Image.new('RGB',(1080,445),'#080b10');d=ImageDraw.Draw(canvas)
    for k,(im,label) in enumerate([(ia,a['date'][:10]),(ib,b['date'][:10]),(red,'Significant residual candidates')]):
        canvas.paste(Image.fromarray(np.flipud(im)).resize((360,360),Image.Resampling.NEAREST),(360*k,30));d.text((360*k+12,9),label,fill='white')
    d.text((12,397),f"{name}: {span:.1f} days; D{a['detector']}; {a['wavelength_um']:.3f} / {b['wavelength_um']:.3f} um; shared stretch",fill='white')
    d.text((12,420),'Real observed input. Red is NOT confirmed motion; PSF and registration residuals remain possible.',fill='#d9b66f');canvas.save(out/(name+'.png'))
    assert all(hashlib.sha256((CACHE/(cid+'.npz')).read_bytes()).hexdigest()==h for cid,h in hashes.items())
    row.update(status='observed comparison rendered',dates=[a['date'],b['date']],baseline_days=span,detector=a['detector'],wavelengths_um=[a['wavelength_um'],b['wavelength_um']],red_pixels=int(mask['red'].sum()),spectrally_comparable_pixels=int(mask['comparable'].sum()),raw_unchanged=True,confirmed_motion=False)
    report.append(row);print(row,flush=True)
(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
