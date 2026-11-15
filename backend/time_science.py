"""Catalog-guided quicklook time analysis; no image is synthesized."""
import base64
import json
import threading
import uuid
import warnings
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord, get_body_barycentric
from astropy.time import Time
from astropy.io import fits
from scipy.optimize import least_squares
from fastapi import HTTPException, Query
from .archive import ROOT, CACHE, fetch_frame, output_grid, ensure_frame_files
from .analysis import load_products, render_computed, aperture_measure, sky_at_click, group_frames

TASKS={}
LOCK=threading.Lock()

def target_for(job):
    records=json.loads((ROOT/'web/assets/target-system-records.json').read_text())['rows']
    center=SkyCoord(job['ra']*u.deg,job['dec']*u.deg)
    candidates=[(center.separation(SkyCoord(float(r['ra'])*u.deg,float(r['dec'])*u.deg)).arcsec,r) for r in records]
    distance,row=min(candidates,key=lambda p:p[0])
    if distance>max(60,job['fov']*30):raise ValueError('This field is not centered on one of the five catalog targets. Click a source for aperture analysis.')
    return row

def prediction(row,mjd,parallax=True):
    source=SkyCoord(ra=float(row['ra'])*u.deg,dec=float(row['dec'])*u.deg,pm_ra_cosdec=float(row['pmra'])*u.mas/u.yr,pm_dec=float(row['pmdec'])*u.mas/u.yr,obstime=Time(2000.,format='jyear'))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore');moved=source.apply_space_motion(new_obstime=Time(mjd,format='mjd'))
    pos=SkyCoord(moved.ra,moved.dec)
    # Geometric annual parallax relative to the barycenter. Aberration is not applied to ICRS image WCS.
    plx=float(row.get('plx_value') or 0)
    if parallax and plx>0:
        unit=pos.cartesian.xyz.value
        earth=get_body_barycentric('earth',Time(mjd,format='mjd')).xyz.to_value(u.au)
        vector=unit*(1000/plx*206264.806247)-earth
        pos=SkyCoord(x=vector[0],y=vector[1],z=vector[2],representation_type='cartesian',frame='icrs').spherical
        return SkyCoord(pos.lon,pos.lat,frame='icrs')
    return SkyCoord(pos.ra,pos.dec)

def projected(job,pos):
    w,n,scale=output_grid(job['ra'],job['dec'],job['fov'])
    x,y=w.world_to_pixel(pos)
    return dict(x=float((x+.5)/n),y=float(1-(y+.5)/n))

def centroid(frame,job,pos):
    native=CACHE/(frame['cache_id']+'.fits')
    if native.exists():return native_centroid(native,job,pos)
    p=load_products(frame);a=p['value'].astype(float);v=p['variance'].astype(float)
    w,n,scale=output_grid(job['ra'],job['dec'],job['fov']);px,py=w.world_to_pixel(pos)
    yy,xx=np.mgrid[:n,:n];region=(xx-px)**2+(yy-py)**2<4.5**2
    good=region&np.isfinite(a)&np.isfinite(v)&(v>0)
    if good.sum()<35:raise ValueError('Predicted source neighborhood is masked or clipped.')
    x=xx[good];y=yy[good];z=a[good];err=np.sqrt(v[good])
    bg=float(np.median(z));amp=float(np.max(z)-bg)
    fit=least_squares(lambda q:(q[0]+q[1]*np.exp(-((x-q[2])**2+(y-q[3])**2)/(2*q[4]**2))-z)/err,
                      [bg,max(amp,1e-5),float(px),float(py),1.],
                      bounds=([-np.inf,0,px-2,py-2,.45],[np.inf,np.inf,px+2,py+2,2.5]))
    q=fit.x;chi=float(np.sum(fit.fun**2)/max(1,len(z)-5))
    cov=np.linalg.pinv(fit.jac.T@fit.jac)*max(1,chi)
    snr=float(q[1]/max(np.sqrt(max(0,cov[1,1])),1e-12))
    if snr<8 or abs(q[2]-px)>1.95 or abs(q[3]-py)>1.95 or q[4]>2.45 or chi>10:
        raise ValueError('Source fit fails S/N, confusion, PSF, or goodness-of-fit criteria; no reliable motion measurement.')
    sky=w.pixel_to_world(q[2],q[3])
    return dict(ra=float(sky.ra.deg),dec=float(sky.dec.deg),x=float((q[2]+.5)/n),y=float(1-(q[3]+.5)/n),snr=snr,reduced_chi2=chi,
                centroid_error_arcsec=float(scale*max(.2,np.sqrt(max(cov[2,2],cov[3,3],0)))))


def native_centroid(path,job,pos):
    """Fit only valid native pixels, including unsaturated PSF wings.

    The source center is free inside a catalog-guided search window. Masked
    core pixels are never filled, and the catalog displacement is not fitted.
    """
    from astropy.wcs import WCS
    with fits.open(path,memmap=False) as h:
        a=h['IMAGE'].data.astype(float);v=h['VARIANCE'].data.astype(float);flags=h['FLAGS'].data
        w=WCS(h['IMAGE'].header).celestial
        from .archive import CONFIG
        px,py=w.world_to_pixel(pos);yy,xx=np.mgrid[:a.shape[0],:a.shape[1]]
        good=((xx-px)**2+(yy-py)**2<7**2)&np.isfinite(a)&np.isfinite(v)&(v>0)&np.isin(flags,CONFIG['accepted_pixel_flags'])
        if good.sum()<45:raise ValueError('Native PSF neighborhood has too few unflagged pixels for astrometry.')
        x,y,z,err=xx[good]-px,yy[good]-py,a[good],np.sqrt(v[good])
        if sum(np.any((x*signx>0)&(y*signy>0)) for signx,signy in [(1,1),(1,-1),(-1,1),(-1,-1)])<4:
            raise ValueError('Native PSF wings do not surround the source; centroid is unconstrained.')
        bg=float(np.median(z));amp=max(float(np.max(z)-bg),1e-6)
        def model(q):
            dx=x-q[2];dy=y-q[3];c=np.cos(q[6]);s=np.sin(q[6]);rx=c*dx+s*dy;ry=-s*dx+c*dy
            return q[0]+q[7]*x+q[8]*y+q[1]*np.exp(-.5*((rx/q[4])**2+(ry/q[5])**2))
        fit=least_squares(lambda q:(model(q)-z)/err,[bg,amp,0,0,1.1,1.1,0,0,0],
            bounds=([-np.inf,0,-2,-2,.45,.45,-np.pi,-np.inf,-np.inf],[np.inf,np.inf,2,2,3.2,3.2,np.pi,np.inf,np.inf]),max_nfev=600)
        q=fit.x;chi=float(np.sum(fit.fun**2)/max(1,len(z)-9));cov=np.linalg.pinv(fit.jac.T@fit.jac)*max(1,chi)
        snr=float(q[1]/max(np.sqrt(max(0,cov[1,1])),1e-12))
        if not fit.success or snr<8 or max(abs(q[2]),abs(q[3]))>1.95 or max(q[4:6])>3.15 or chi>10:
            raise ValueError(f'Native PSF fit rejected (S/N {snr:.1f}, reduced chi-square {chi:.1f}); no reliable centroid.')
        sky=w.pixel_to_world(px+q[2],py+q[3]);project=projected(job,sky)
        scale=float(np.sqrt(abs(np.linalg.det(w.pixel_scale_matrix)))*3600)
        return dict(ra=float(sky.ra.deg),dec=float(sky.dec.deg),**project,snr=snr,reduced_chi2=chi,
                    native_valid_pixels=int(good.sum()),method='Elliptical Gaussian plus planar background on unflagged native pixels; masked cores excluded',
                    centroid_error_arcsec=float(scale*max(.2,np.sqrt(max(cov[2,2],cov[3,3],0)))))

def motion_analysis(job,task):
    row=target_for(job)
    if 'Barnard' not in row['main_id']:raise ValueError('The automatic motion proof is restricted to Barnard’s Star. Other fields support manual motion marks.')
    task.update(message='Reading wavelength metadata for every released exposure to select the widest comparable baseline.',total=len(job['frames']),checked=0)
    def load(f):
        if task.get('cancelled'):return
        if f.get('status')!='ready':
            try:
                key,meta=fetch_frame(f,job['ra'],job['dec'],job['fov'])
                with LOCK:f.update(meta,cache_id=key,status='ready',ra=job['ra'],dec=job['dec'],fov=job['fov'])
            except Exception as e:f.update(status='error',error='Real cutout unavailable',detail=type(e).__name__)
        with LOCK:task['checked']+=1
    ordered=[]
    rows=list(job['frames'])
    for i in range((len(rows)+1)//2):
        ordered.append(rows[i])
        if len(rows)-1-i!=i:ordered.append(rows[-1-i])
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(load,ordered))
    if task.get('cancelled'):raise ValueError('Motion check cancelled. Downloaded observations remain cached.')
    return analyze_available(job,full=True)

def analyze_available(job,full=False):
    row=target_for(job)
    ready=sorted([f for f in job['frames'] if f.get('status')=='ready' and f.get('wavelength_um') is not None],key=lambda f:f['mjd'])
    # Compare wavelengths at the predicted source, not at the field center.
    # This matters for a high-proper-motion source far from its J2000 position.
    w,n,_=output_grid(job['ra'],job['dec'],job['fov']);local=[]
    for f in ready:
        try:
            px,py=w.world_to_pixel(prediction(row,f['mjd']));x,y=int(round(float(px))),int(round(float(py)))
            wave=load_products(f)['wavelength'][y,x] if 0<=x<n and 0<=y<n else np.nan
            if np.isfinite(wave):local.append(dict(f,target_wavelength_um=float(wave)))
        except (ValueError,OSError,KeyError):continue
    pairs=[(b['mjd']-a['mjd'],a,b) for i,a in enumerate(local) for b in local[i+1:]
           if a['detector']==b['detector'] and abs(a['target_wavelength_um']-b['target_wavelength_um'])<=.025 and b['mjd']-a['mjd']>=30]
    if not pairs:raise ValueError('No comparable same-detector pair at least 30 days apart.')
    baseline,a,b=max(pairs,key=lambda p:p[0])
    widest=baseline
    # A masked widest pair is still reported. Search all narrower comparable
    # pairs for a usable measurement instead of treating the first failure as
    # evidence that no astrometry is possible in the sequence.
    fits_by_id={};rejected={};measurement=None
    for span,first,last in sorted(pairs,key=lambda p:p[0],reverse=True):
        for f in (first,last):
            if f['id'] in fits_by_id or f['id'] in rejected:continue
            try:fits_by_id[f['id']]=centroid(f,job,prediction(row,f['mjd']))
            except (ValueError,OSError,KeyError) as e:rejected[f['id']]=str(e)
        if first['id'] in fits_by_id and last['id'] in fits_by_id:
            baseline,a,b=span,first,last
            measurement=(fits_by_id[a['id']],fits_by_id[b['id']]);break
    pa,pb=prediction(row,a['mjd']),prediction(row,b['mjd'])
    image,display=render_computed(load_products(b)['value']-load_products(a)['value'],diverging=True)
    result=dict(provenance='computed',catalog='SIMBAD via astroquery',catalog_bibcode=row['pm_bibcode'],catalog_epoch='J2000.0',
                catalog_motion_arcsec_per_year=float(np.hypot(float(row['pmra']),float(row['pmdec']))/1000),
                baseline_days=baseline,frames=[a['index'],b['index']],dates=[a['date'],b['date']],detector=a['detector'],
                wavelengths_um=[a['target_wavelength_um'],b['target_wavelength_um']],wavelength_sampling='Native wavelength map at predicted source; nearest registered pixel',predictions=[dict(projected(job,p),frame=f['index'],mjd=f['mjd']) for p,f in [(pa,a),(pb,b)]],
                image='data:image/png;base64,'+base64.b64encode(image).decode(),display=display,
                available=len(ready),discovered=job.get('discovered',len(job['frames'])),widest_comparable_baseline_days=widest,
                rejected_centroid_count=len(rejected),full_manifest_attempted=full,
                measured_motion_arcsec_per_year=None,measurement_status='unverified',
                note=('Widest baseline among available same-detector exposures within 0.025 µm. '+('All discovered files were attempted. ' if full else 'Loaded subset only; this is not the widest-baseline archive proof. ')+'Difference B − A is unscaled, without PSF matching. Prediction includes proper motion and geometric annual parallax; radial velocity and perspective acceleration are omitted. Gaussian centroids require S/N ≥8 and fit-quality checks. Error includes a 0.2-pixel component floor; no field-star astrometric registration or calibration-systematic correction.'))
    try:
        if measurement is None:raise ValueError('No comparable pair has two reliable unflagged PSF fits. '+next(iter(rejected.values()),'Native pixels are unavailable.'))
        ca,cb=measurement
        sa=SkyCoord(ca['ra']*u.deg,ca['dec']*u.deg);sb=SkyCoord(cb['ra']*u.deg,cb['dec']*u.deg)
        east,north=sa.spherical_offsets_to(sb)
        # Remove the predicted annual-parallax displacement before quoting proper motion.
        na,nb=prediction(row,a['mjd'],False),prediction(row,b['mjd'],False)
        pe,pn=pa.spherical_offsets_to(pb);ne,nn=na.spherical_offsets_to(nb)
        dx=east.arcsec-(pe.arcsec-ne.arcsec);dy=north.arcsec-(pn.arcsec-nn.arcsec)
        result.update(measured_motion_arcsec_per_year=float(np.hypot(dx,dy)/(baseline/365.25)),
                      error_arcsec_per_year=float(np.hypot(ca['centroid_error_arcsec'],cb['centroid_error_arcsec'])/(baseline/365.25)),
                      measured_shift_arcsec=float(sa.separation(sb).arcsec),centroids=[ca,cb],measurement_status='quicklook')
    except ValueError as e:result['measurement_reason']=str(e)
    result['note']+=' Widest comparable available span: '+f'{widest:.3f}'+' days. '
    if baseline<widest:result['note']+='Displayed pair is the widest pair with accepted centroids, shorter than the widest available pair. '
    return result


def curve_group(job,g,row=None,x=None,y=None):
    frames={f['index']:f for f in job['frames']};points=[]
    for i in g['frames']:
        f=frames[i]
        try:
            file=CACHE/(f['cache_id']+'.fits')
            if not file.is_file():raise FileNotFoundError('Native FITS is not cached.')
            pos=prediction(row,f['mjd']) if row else sky_at_click(job,x,y)
            with fits.open(file,memmap=False) as hdus:m=aperture_measure(hdus,pos,18.45)
            points.append(dict(m,frame=i,mjd=f['mjd'],date=f['date']))
        except (ValueError,OSError,KeyError):points.append(dict(status='missing',frame=i,mjd=f['mjd'],reason='Native aperture unavailable.'))
    if sum(p['status']=='ok' for p in points)>=2:return points,'native aperture'
    # Use exactly the same unflagged sky pixels in every exposure. This reports
    # an aperture brightness index, never a reconstructed saturated total flux.
    try:
        if not all((CACHE/(frames[i]['cache_id']+'.npz')).is_file() for i in g['frames']):
            return points,'native aperture'
        products=[load_products(frames[i]) for i in g['frames']]
        w,n,scale=output_grid(job['ra'],job['dec'],job['fov'])
        positions=[prediction(row,frames[i]['mjd']) if row else sky_at_click(job,x,y) for i in g['frames']]
        centers=np.array([w.world_to_pixel(p) for p in positions])
        if np.max(np.ptp(centers,axis=0))>.2:return points,'native aperture'
        px,py=centers.mean(axis=0);yy,xx=np.mgrid[:n,:n];r=np.hypot(xx-px,yy-py)*scale
        aperture=r<=18.45;annulus=(r>=33.21)&(r<=51.66)
        common=np.logical_and.reduce([np.isfinite(p['value'])&np.isfinite(p['variance'])&(p['variance']>0) for p in products])
        waves=[p.get('wavelength') for p in products]
        if any(w is None for w in waves):return points,'native aperture'
        wavelengths=np.stack(waves)
        common &= np.isfinite(wavelengths).all(axis=0) & (np.ptp(wavelengths,axis=0)<=.025)
        use=aperture&common
        if use.sum()<10 or use.sum()<aperture.sum()*.3:return points,'native aperture'
        area=(np.deg2rad(scale/3600)**2)*1e12
        out=[]
        for i,p in zip(g['frames'],products):
            valid=annulus&np.isfinite(p['value'])&np.isfinite(p['variance'])
            if valid.sum()<20:return points,'native aperture'
            bg=float(np.median(p['value'][valid]));scatter=1.4826*np.median(np.abs(p['value'][valid]-bg))
            flux=float(np.sum(p['value'][use]-bg)*area)
            error=float(np.sqrt(np.sum(p['variance'][use])+np.pi/2*scatter**2/valid.sum()*use.sum()**2)*area)
            f=frames[i];out.append(dict(status='ok',frame=i,mjd=f['mjd'],date=f['date'],flux_ujy=flux,error_ujy=error,
                valid_fraction=float(use.sum()/aperture.sum()),aperture_pixels=int(use.sum()),measurement='common unflagged aperture brightness; not total source flux'))
        return out,'common unflagged aperture brightness index'
    except (ValueError,OSError,KeyError):return points,'native aperture'


def lightcurve_analysis(job,x=None,y=None,group=None):
    row=target_for(job) if x is None else None
    groups=[g for g in group_frames(job['frames']) if len(g['frames'])>=2 and g['stackable'] and (not group or g['id']==group)]
    if not groups:raise ValueError('Load repeated exposures in one 0.025 micrometer detector/wavelength group. No cross-band curve is substituted.')
    frames={f['index']:f for f in job['frames']};results=[]
    for g in groups:
        points,method=curve_group(job,g,row,x,y);good=[p for p in points if p['status']=='ok']
        span=np.ptp([p['mjd'] for p in good]) if len(good)>1 else 0
        results.append((len(good)>=2,span,len(good),g,points,method))
    _,_,_,g,points,method=max(results,key=lambda r:r[:3]);good=[p for p in points if p['status']=='ok'];chi=None
    if len(good)>=2:
        flux=np.array([p['flux_ujy'] for p in good]);err=np.array([p['error_ujy'] for p in good]);mean=np.average(flux,weights=1/err**2)
        chi=float(np.sum(((flux-mean)/err)**2)/(len(flux)-1))
    return dict(provenance='computed',source_pixels='observed',group=g,points=points,reduced_chi2_constant=chi,
        measurement_method=method,groups_checked=len(results),loaded=sum(f.get('status')=='ready' for f in job['frames']),discovered=job.get('discovered',len(job['frames'])),
        note='Same detector and 0.025 micrometer wavelength group; statistical errors only. '+('A fixed common footprint of unflagged registered pixels excludes masked cores in every epoch; values are a brightness index, not total source flux. ' if method.startswith('common') else 'Cached native 18.45 arcsec aperture with local background. Missing native data are reported. ')+'No masked values are filled or interpolated. PSF, calibration, crowding and residual wavelength effects can mimic variability; this curve alone does not establish intrinsic stellar variability.')

def install_time_routes(app,jobs,guard):
    @app.get('/api/jobs/{identity}/predicted-target')
    def predicted(identity:str):
        if identity not in jobs:raise HTTPException(404,'Session expired.')
        job=jobs[identity]
        try:
            row=target_for(job)
            frames=[f for f in job['frames'] if f.get('status')=='ready']
            positions=prediction(row,np.array([f['mjd'] for f in frames])) if frames else []
            return dict(provenance='catalog / computed',name=row['main_id'],motion_arcsec_per_year=float(np.hypot(float(row['pmra']),float(row['pmdec']))/1000),
                        points=[dict(projected(job,p),frame=f['index']) for f,p in zip(frames,positions)],
                        note='SIMBAD J2000 position, proper motion and geometric annual parallax; not a source detection.')
        except ValueError as e:raise HTTPException(422,str(e))

    @app.get('/api/jobs/{identity}/motion-loaded')
    def loaded_motion(identity:str):
        if identity not in jobs:raise HTTPException(404,'Session expired.')
        try:return analyze_available(jobs[identity],full=False)
        except ValueError as e:raise HTTPException(422,str(e))

    @app.post('/api/jobs/{identity}/motion-proof',status_code=202)
    def proof(identity:str):
        if identity not in jobs:raise HTTPException(404,'Session expired.')
        job=jobs[identity]
        try:target_for(job)
        except ValueError as e:raise HTTPException(422,str(e))
        with LOCK:
            for t in TASKS.values():
                if t['job']==identity:return t
            if any(t['status']=='running' for t in TASKS.values()):raise HTTPException(429,'A motion check is already running.')
            t=dict(id=uuid.uuid4().hex,job=identity,status='running',message='Starting catalog-guided analysis.')
            TASKS[t['id']]=t
        def work():
            try:t.update(result=motion_analysis(job,t),status='complete',message='Real-data comparison ready.')
            except Exception as e:t.update(status='error',message=str(e))
        threading.Thread(target=work,daemon=True).start()
        return t

    @app.post('/api/motion-proof/{identity}/cancel')
    def cancel_proof(identity:str):
        if identity in TASKS:TASKS[identity]['cancelled']=True
        return {'cancelled':True}

    @app.get('/api/motion-proof/{identity}')
    def proof_status(identity:str):
        if identity not in TASKS:raise HTTPException(404,'Motion check not found.')
        return TASKS[identity]

    @app.get('/api/jobs/{identity}/lightcurve')
    def lightcurve(identity:str,x:float|None=Query(default=None,ge=0,le=1),y:float|None=Query(default=None,ge=0,le=1),group:str|None=None):
        if identity not in jobs:raise HTTPException(404,'Session expired.')
        job=jobs[identity]
        if (x is None)!=(y is None):raise HTTPException(422,'Supply both x and y.')
        try:return lightcurve_analysis(job,x,y,group)
        except ValueError as e:raise HTTPException(422,str(e))
