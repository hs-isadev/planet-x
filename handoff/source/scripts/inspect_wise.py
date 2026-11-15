import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import backend,numpy as np
from PIL import Image,ImageDraw
from backend.archive import CACHE
R=Path(__file__).resolve().parents[1];r=json.loads((R/'docs/data-proof/report.json').read_text());frames=[f for f in r.get('frames',[]) if f['detector']==6]
frames=sorted(frames,key=lambda f:f['mjd']);frames=frames[::max(1,len(frames)//12)]
canvas=Image.new('RGB',(4*300,3*330),'#080b10');draw=ImageDraw.Draw(canvas)
for i,f in enumerate(frames[:12]):
 a=np.load(CACHE/(f['cache_id']+'.npy'));lo,hi=np.nanpercentile(a,[10,95]);v=np.arcsinh(5*np.clip((a-lo)/(hi-lo),0,1))/np.arcsinh(5);im=Image.fromarray(np.flipud(np.nan_to_num(v)*255).astype('uint8')).convert('RGB').resize((290,290),Image.Resampling.NEAREST);x=i%4*300;y=i//4*330;canvas.paste(im,(x,y));draw.text((x+4,y+295),f['date'][:10]+' '+str(round(f['wavelength_um'],3))+' um',fill='white')
canvas.save(R/'docs/data-proof/contact-sheet.png');print('D6 frames',len([f for f in r['frames'] if f['detector']==6]),'total ready',r['frames_returned'])
