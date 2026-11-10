"""Enlarged fixed-field inspection; no source shifting or artificial motion."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import backend
from astropy import log;log.setLevel('ERROR')
import numpy as np
from PIL import Image,ImageDraw
from backend.archive import ROOT,CACHE,fetch_frame
out=ROOT/'docs/data-proof';rows=json.loads((out/'wise-d6-frames.json').read_text());stacks=[]
for label,test in [('May 2025',lambda p:p['mjd']<60820),('Apr-May 2026',lambda p:p['mjd']>61100)]:
 frames=[p for p in rows if 4.8<=p['wavelength_um']<=5.0 and test(p)]
 arrays=[]
 for f in frames:
  if not (CACHE/(f['cache_id']+'.npz')).exists():f['cache_id'],_=fetch_frame(f,133.79512916666667,-7.245147222222222,8)
  with np.load(CACHE/(f['cache_id']+'.npz')) as p:arrays.append({k:p[k].copy() for k in ['value','variance']})
 values=np.array([a['value'] for a in arrays]);var=np.array([a['variance'] for a in arrays]);ok=np.isfinite(values)&np.isfinite(var)&(var>0);weights=np.where(ok,1/np.where(ok,var,1),0);den=weights.sum(0);a=np.divide((np.nan_to_num(values)*weights).sum(0),den,out=np.full_like(den,np.nan),where=den>0)
 stacks.append((label,len(frames),a[32:50,51:69]))
lo,hi=np.nanpercentile(stacks[0][2],[10,99.5]);images=[]
for label,count,patch in stacks:
 v=np.arcsinh(5*np.clip((patch-lo)/(hi-lo),0,1))/np.arcsinh(5);im=Image.fromarray(np.flipud(np.nan_to_num(v)*255).astype('uint8')).convert('RGB').resize((360,360),Image.Resampling.NEAREST);canvas=Image.new('RGB',(360,450),'#080b10');canvas.paste(im,(0,0));d=ImageDraw.Draw(canvas);d.text((10,371),label+' / '+str(count)+' real D6 exposures',fill='white');d.text((10,391),'COMPUTED weighted stack / 4.8-5.0 um',fill='#c7d0db');d.text((10,411),'Fixed sky crop, fixed stretch; no pixel shifts',fill='#c7d0db');d.text((10,431),'Tentative source: first epoch is marginal',fill='#c7d0db');images.append(canvas)
images[0].save(out/'wise-tentative-motion.gif',save_all=True,append_images=images[1:],duration=900,loop=0)
images[0].save(out/'wise-candidate-2025.png');images[1].save(out/'wise-candidate-2026.png')
print('Exported two computed epoch stacks from actual observed pixels.',flush=True)
