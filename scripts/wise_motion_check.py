"""Inspect real D6 epochs. Catalog predictions only locate the source, never move pixels."""
import sys,json,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import backend
from astropy import log;log.setLevel('ERROR')
import numpy as np,astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time
from PIL import Image,ImageDraw
from backend.archive import discover,fetch_frame,CACHE,ROOT,output_grid,atomic_json
from backend.simbad_client import query_names
from scipy.optimize import least_squares
out=ROOT/'docs/data-proof';report={'motion_confirmed':False,'notes':[]}
try:
 table,server=query_names(['WISE J085510.83-071442.5'],['pmra','pmdec'])
 table.write(out/'wise-simbad.ecsv',overwrite=True);r=table[0];print(table,flush=True)
 target=SkyCoord(float(r['ra'])*u.deg,float(r['dec'])*u.deg,pm_ra_cosdec=float(r['pmra'])*u.mas/u.yr,pm_dec=float(r['pmdec'])*u.mas/u.yr,obstime=Time('J2000'))
 report['catalog']={k:str(r[k]) for k in table.colnames};report['catalog_source']=server
 ra,dec=133.79512916666667,-7.245147222222222
 rows=[r for r in discover(ra,dec) if r['detector']==6]
 products=[]
 for row in rows:
  identity,meta=fetch_frame(row,ra,dec,8)
  products.append(dict(row,**meta,cache_id=identity))
  print('D6 ready',len(products),len(rows),row['date'],meta.get('wavelength_um'),flush=True)
  atomic_json(out/'wise-d6-frames.json',products)
 grid,n,scale=output_grid(ra,dec,8)
 mid=target.apply_space_motion(new_obstime=Time(np.mean([r['mjd'] for r in rows]),format='mjd'));cx,cy=grid.world_to_pixel(mid)
 report['predicted_midpoint_pixel']=[float(cx),float(cy)]
 report['note']='Catalog proper motion is used only to identify a fixed search region. Pixel arrays are not shifted to the predicted moving-source positions.'
 # Restrict to comparable long wavelengths; never combine six different detector arrays.
 products=[p for p in products if p.get('wavelength_um') and 4.8<=p['wavelength_um']<=5.0]
 epochs=[('2025 May',[p for p in products if p['mjd']<60820]),('2026 Apr-May',[p for p in products if p['mjd']>61100])]
 canvas=Image.new('RGB',(1000,560),'#080b10');draw=ImageDraw.Draw(canvas);measurements=[]
 for k,(name,frames) in enumerate(epochs):
  if not frames:continue
  arrays=[np.load(CACHE/(f['cache_id']+'.npz')) for f in frames]
  values=np.array([a['value'] for a in arrays]);var=np.array([a['variance'] for a in arrays]);valid=np.isfinite(values)&np.isfinite(var)&(var>0);weights=np.where(valid,1/np.where(valid,var,1),0);den=weights.sum(0);image=np.divide((np.nan_to_num(values)*weights).sum(0),den,out=np.full_like(den,np.nan),where=den>0)
  variance=np.divide(1,den,out=np.full_like(den,np.nan),where=den>0)
  x0,x1=max(0,int(cx)-6),min(n,int(cx)+7);y0,y1=max(0,int(cy)-6),min(n,int(cy)+7);patch=image[y0:y1,x0:x1];vp=variance[y0:y1,x0:x1];yy,xx=np.mgrid[y0:y1,x0:x1];ok=np.isfinite(patch)&np.isfinite(vp)&(vp>0)
  def model(p):
   amp,x,y,sigma,b=p;return b+amp*np.exp(-((xx-x)**2+(yy-y)**2)/(2*sigma**2))
  fit=least_squares(lambda p:((model(p)-patch)/np.sqrt(vp))[ok],x0=[float(np.nanmax(patch)-np.nanmedian(patch)),float(cx),float(cy),.8,float(np.nanmedian(patch))],bounds=([0,cx-3,cy-3,.4,-np.inf],[np.inf,cx+3,cy+3,2,np.inf]))
  cov=np.linalg.pinv(fit.jac.T@fit.jac);amp,x,y,sigma,b=fit.x;snr=float(amp/np.sqrt(max(cov[0,0],1e-30)));date=float(np.mean([p['mjd'] for p in frames]));measurement=dict(epoch=name,count=len(frames),mjd=date,x=float(x),y=float(y),nominal_x_error=float(np.sqrt(cov[1,1])),snr=snr,wavelength_range_um=[4.8,5.0]);measurements.append(measurement)
  lo,hi=np.nanpercentile(image,[15,99.3]);norm=np.arcsinh(5*np.clip((image-lo)/(hi-lo),0,1))/np.arcsinh(5);im=Image.fromarray(np.flipud(np.nan_to_num(norm)*255).astype('uint8')).convert('RGB').resize((480,480),Image.Resampling.NEAREST);canvas.paste(im,(k*500,0));draw.text((k*500+10,490),name+' / '+str(len(frames))+' real D6 images, 4.8-5.0 um',fill='white');draw.text((k*500+10,510),'Computed weighted stack; no moving-source shift',fill='white');px=(cx+.5)/n*480;py=(n-.5-cy)/n*480;draw.rectangle((k*500+px-38,py-38,k*500+px+38,py+38),outline='#e4bd84',width=1)
 canvas.save(out/'wise-epoch-stacks.png');report['measurements']=measurements
 if len(measurements)==2:
  a,b=measurements;baseline=(b['mjd']-a['mjd'])/365.25;dx=(b['x']-a['x'])*scale;dy=(b['y']-a['y'])*scale;error=np.hypot(a['nominal_x_error'],b['nominal_x_error'])*scale
  report.update(observed_offset_arcsec=[dx,dy],nominal_x_offset_error_arcsec=float(error),baseline_years=baseline,motion_confirmed=bool(a['snr']>=5 and b['snr']>=5 and dx>3*error and 3<dx/baseline<14 and abs(dy/baseline)<5))
  report['notes'].append('Exploratory Gaussian centroids in fixed sky region; noise correlation, calibration and PSF systematics are omitted. Broad 4.8–5.0 µm stack is for motion inspection, not a calibrated spectral bin.')
except Exception as e:report['error']=type(e).__name__+': '+str(e);traceback.print_exc()
atomic_json(out/'motion-report.json',report);print(json.dumps(report,indent=2),flush=True)
