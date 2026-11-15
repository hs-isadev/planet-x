import base64
import json
import threading
import time
import uuid
import numpy as np
from astropy.io import fits
from astropy.time import Time
from fastapi import HTTPException, Query, Request, Response
import httpx
from .observation_tools import clicked_track, epsf_measure, identify_click, inspect_pixel, moving_track, render_flag_mask
from pydantic import BaseModel, Field
from typing import Literal
from requests.exceptions import RequestException
from .archive import CONFIG,CACHE,atomic_json,key_for,prune_cache,ensure_frame_files
from .cloud import list_archive,first_exposure,cloud_cutout
from .analysis import group_frames,load_products,stack_products,combine_images,render_computed,sky_at_click,motion_fit,aperture_measure

class CloudOpen(BaseModel):
    key:str|None=Field(default=None,max_length=350)
    fov:float=Field(default=8,ge=2,le=20)
    append_to:str|None=Field(default=None,max_length=40)

class Mark(BaseModel):
    frame:int=Field(ge=0)
    x:float=Field(ge=0,le=1)
    y:float=Field(ge=0,le=1)
    frame_id:str|None=Field(default=None,max_length=64)

class Track(BaseModel):
    points:list[Mark]=Field(min_length=2,max_length=100)


class EphemerisTrack(BaseModel):
    designation: str = Field(default='', max_length=60)
    anchors: list[Mark] = Field(default_factory=list, max_length=2)
    group: str = Field(default='all', max_length=32)


def install_analysis_routes(app,jobs,guard,clients):
    def job_for(identity):
        if identity not in jobs:raise HTTPException(404,'Session expired. Load this field again.')
        return jobs[identity]
    def ready_frame(job,index):
        if index<0 or index>=len(job['frames']):raise ValueError('Unknown frame.')
        f=job['frames'][index]
        if f['status']!='ready':raise ValueError('This frame is not available yet.')
        return f
    def throttle_client(request,kind,limit):
        client=(request.client.host if request.client else 'unknown')+kind;now=time.monotonic()
        with guard:
            hits=[t for t in clients.get(client,[]) if now-t<60]
            if len(hits)>=limit:raise HTTPException(429,'Please allow current requests to finish before retrying.')
            clients[client]=hits+[now]

    @app.get('/api/archive')
    def archive(request:Request,prefix:str='qr3/level2/',cursor:str|None=None):
        throttle_client(request,'archive-list',100)
        try:return list_archive(prefix,cursor)
        except ValueError as exc:raise HTTPException(422,str(exc))
        except Exception:raise HTTPException(503,'The public cloud archive did not respond. Please retry.')

    @app.post('/api/archive/open',status_code=202)
    def open_archive(body:CloudOpen,request:Request):
        throttle_client(request,'archive-open',10)
        if body.append_to:
            target=job_for(body.append_to)
            if target.get('source')!='cloud' or target['status'] not in ('complete','error') or not target['frames']:raise HTTPException(422,'Wait for a cloud field to finish before adding a frame.')
            if len(target['frames'])>=200:raise HTTPException(422,'A manual archive sequence is limited to 200 selected exposures.')
            if not body.key:raise HTTPException(422,'Select a real exposure to append.')
            with guard:target['status']='fetching'
            def append():
                try:
                    _,meta=cloud_cutout(body.key,target['fov'],center=(target['ra'],target['dec']))
                    with guard:
                        if not any(f.get('source_key')==body.key for f in target['frames']):
                            meta['index']=len(target['frames']);target['frames'].append(meta)
                            target['frames'].sort(key=lambda f:(f['mjd'],f['id']))
                            for i,f in enumerate(target['frames']):f['index']=i
                        target['status']='complete';target['message']='Selected real archive exposures registered on the same field; this is not a complete coordinate search.'
                except Exception as exc:
                    with guard:target['status']='complete';target['append_error']='Could not add the selected exposure: '+str(exc)
            threading.Thread(target=append,daemon=True).start()
            return {'id':target['id']}
        with guard:
            active=[j for j in jobs.values() if j['status'] in ('querying','fetching')]
            if not active:
                for old_id in list(jobs):
                    if time.monotonic()-jobs[old_id]['created']>CONFIG['query_ttl_seconds']:del jobs[old_id]
                if not jobs:prune_cache()
            for existing in jobs.values():
                if existing.get('cloud_key')==body.key and existing.get('fov')==body.fov and existing.get('source')=='cloud' and existing['status']!='error':return {'id':existing['id']}
            if len(active)>=CONFIG['max_active_jobs']:raise HTTPException(429,'The observatory is busy. Please retry shortly.')
            identity=uuid.uuid4().hex
            job=dict(id=identity,ra=0.,dec=0.,fov=body.fov,created=time.monotonic(),status='querying',frames=[],contrast=None,source='cloud',cloud_key=body.key,title='Released archive exposure',message='Opening an actual released exposure from the public cloud archive.',discovery_scope='Manually selected archive exposure; not complete coordinate coverage.')
            jobs[identity]=job
        def load():
            try:
                key=body.key or first_exposure()
                _,meta=cloud_cutout(key,body.fov)
                data=np.load(CACHE/(meta['cache_id']+'.npy'),allow_pickle=False);lo,hi=np.nanpercentile(data,[1,99.7]);hi=max(float(hi),float(lo)+1e-8)
                with guard:job.update(ra=meta['ra'],dec=meta['dec'],frames=[meta],status='complete',contrast=dict(black=float(lo),white=hi,reference_frame=0,unit=meta['unit']),title='Archive field · '+meta['band'],message='Observed SPHEREx exposure loaded from the official public mirror. Choose a coordinate search for a full time sequence.')
            except Exception as exc:
                with guard:job.update(status='error',message='The selected cloud exposure could not be read. No substitute data are shown.',detail=type(exc).__name__)
        threading.Thread(target=load,daemon=True).start()
        return {'id':identity}

    @app.get('/api/resolve')
    def resolve(request:Request,name:str=Query(min_length=1,max_length=100)):
        throttle_client(request,'resolve',10)
        cache=CACHE/('resolve-'+key_for(name.casefold())+'.json')
        if cache.exists():return json.loads(cache.read_text())
        try:
            from .simbad_client import query_names
            table,server=query_names([name])
            if table is None or len(table)!=1:raise ValueError('No unique SIMBAD match. Enter RA/Dec or refine the object name.')
            row=table[0];ra=float(row['ra']);dec=float(row['dec'])
            if not np.isfinite(ra+dec):raise ValueError('No usable catalog coordinates for this object.')
            result=dict(name=str(row['main_id']),ra=ra,dec=dec,provenance='catalog',source='SIMBAD via astroquery; position not propagated')
            atomic_json(cache,result);return result
        except ValueError as exc:raise HTTPException(422,str(exc))
        except Exception:raise HTTPException(503,'SIMBAD name resolution is unavailable. Use RA/Dec or open a released cloud exposure.')

    @app.get('/api/jobs/{identity}/groups')
    def groups(identity:str,width:float=Query(default=.025,ge=.005,le=.2)):
        with guard:return {'groups':group_frames(job_for(identity)['frames'],width),'bin_width_um':width,'provenance':'computed'}

    @app.get('/api/jobs/{identity}/computed')
    def computed(identity:str,mode:str,group:str|None=None,a:int=0,b:int=1,width:float=Query(default=.025,ge=.005,le=.2)):
        job=job_for(identity)
        try:
            if mode=='stack':
                matches=[g for g in group_frames(job['frames'],width) if g['id']==group]
                if not matches or not matches[0]['stackable']:raise ValueError('Select a detector/wavelength group with known wavelengths.')
                indices=matches[0]['frames']
                if len(indices)<2:raise ValueError('Need at least two usable frames in the same detector and wavelength bin.')
                if len(indices)>500:raise ValueError('Select a narrower wavelength bin to stack at most 500 frames.')
                products=[load_products(ready_frame(job,i)) for i in indices];result=stack_products(products)
                image,display=render_computed(result['value']);coverage=float(np.isfinite(result['value']).mean())
                note='Inverse-variance mean of registered observations. Moving sources can blur. Resampling covariance and calibration systematics are not included.'
            elif mode in ('add','subtract'):
                fa,fb=ready_frame(job,a),ready_frame(job,b)
                if fa.get('detector')!=fb.get('detector'):raise ValueError('Image arithmetic requires the same detector.')
                wa,wb=fa.get('wavelength_um'),fb.get('wavelength_um')
                if wa is None or wb is None or abs(wa-wb)>width:raise ValueError('Choose images with known center wavelengths within the selected bin width.')
                if a==b:raise ValueError('Select two different frames.')
                pa,pb=load_products(fa),load_products(fb);value=combine_images(pa['value'],pb['value'],mode)
                image,display=render_computed(value,diverging=mode=='subtract');indices=[a,b];coverage=float(np.isfinite(value).mean())
                note='Computed '+('A − B' if mode=='subtract' else 'A + B')+'. No photometric matching, background fitting or PSF matching is applied. Residuals are not detections.'
            else:raise ValueError('Unknown computed image mode.')
            return dict(image='data:image/png;base64,'+base64.b64encode(image).decode(),display=display,provenance='computed',mode=mode,frames=indices,valid_fraction=coverage,note=note)
        except (ValueError,FileNotFoundError) as exc:raise HTTPException(422,str(exc))

    @app.post('/api/jobs/{identity}/track')
    def track(identity:str,body:Track):
        job=job_for(identity)
        try:
            if any(p.frame>=len(job['frames']) for p in body.points):raise ValueError('Unknown frame in manual marks.')
            if any(p.frame_id and job['frames'][p.frame]['id']!=p.frame_id for p in body.points):raise ValueError('Frame order changed while loading. Clear marks and mark the source again.')
            return motion_fit(job,[p.model_dump() for p in body.points])
        except ValueError as exc:raise HTTPException(422,str(exc))

    def inspection_frame(identity, exposure):
        job = job_for(identity)
        frame = next((f for f in job['frames'] if f['id']==exposure and f['status']=='ready'), None)
        if frame is None:
            raise HTTPException(404, 'Select a loaded exposure.')
        return job, frame

    @app.get('/api/jobs/{identity}/pixels/{exposure}')
    def pixels(identity: str, exposure: str, request: Request, x: float=Query(ge=0, le=1), y: float=Query(ge=0, le=1)):
        throttle_client(request, 'pixels', 60)
        job, frame = inspection_frame(identity, exposure)
        try:
            return inspect_pixel(job, frame, x, y)
        except (OSError, ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get('/api/jobs/{identity}/identify/{exposure}')
    def identify(identity: str, exposure: str, request: Request, x: float=Query(ge=0,le=1), y: float=Query(ge=0,le=1)):
        throttle_client(request, 'identify', 12)
        job, frame = inspection_frame(identity, exposure)
        return identify_click(job, frame, x, y)

    @app.get('/api/jobs/{identity}/flags/{exposure}.png')
    def flag_mask(identity: str, exposure: str, request: Request):
        throttle_client(request, 'flag-mask', 45)
        job, frame = inspection_frame(identity, exposure)
        try:
            return Response(render_flag_mask(job, frame), media_type='image/png',
                            headers={'Cache-Control':'private, max-age=3600'})
        except (OSError, ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post('/api/jobs/{identity}/ephemeris')
    def ephemeris(identity: str, body: EphemerisTrack, request: Request):
        throttle_client(request, 'ephemeris', 5)
        job = job_for(identity)
        frames = sorted((dict(f) for f in job['frames'] if f['status']=='ready'),
                        key=lambda f: (f['mjd'], f['id']))
        if body.group in {f'D{i}' for i in range(1,7)}:
            frames = [f for f in frames if f['detector']==int(body.group[1:])]
        elif body.group != 'all':
            group = next((g for g in group_frames(frames) if g['id']==body.group), None)
            frames = [f for f in frames if group and f['index'] in group['frames']]
        if not frames:
            raise HTTPException(422, 'Load a SPHEREx exposure in the selected group first.')
        try:
            if body.designation:
                return moving_track(job, frames, body.designation)
            if not body.anchors:
                raise ValueError('Enter a designation or mark one or two native positions.')
            return clicked_track(job, frames, body.anchors)
        except httpx.HTTPError as exc:
            raise HTTPException(502, 'JPL Horizons could not be reached. Retry shortly.') from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get('/api/jobs/{identity}/calibrated-pair')
    def calibrated_pair(identity: str, request: Request,
                        a: str = Query(max_length=64), b: str = Query(max_length=64),
                        x: float = Query(ge=0, le=1), y: float = Query(ge=0, le=1)):
        from .calibrated_comparison import compare_pair
        throttle_client(request, 'calibrated-pair', 12)
        with guard:
            job = job_for(identity)
            by_id = {f['id']:f for f in job['frames'] if f['status']=='ready'}
            if a == b or a not in by_id or b not in by_id:
                raise HTTPException(422, 'Select two distinct ready exposures.')
            first, second = sorted((dict(by_id[a]), dict(by_id[b])), key=lambda f: f['mjd'])
            field = {key:job[key] for key in ('ra','dec','fov')}
        return compare_pair(field, first, second, x, y, include_image=True)

    @app.get('/api/jobs/{identity}/spectrum')
    def spectrum(identity:str,request:Request,x:float=Query(ge=0,le=1),y:float=Query(ge=0,le=1),radius:float=Query(default=18.45,ge=6.15,le=45),method:Literal['aperture','epsf']='aperture'):
        from .calibrated_comparison import cached_aperture_calibration
        throttle_client(request,'spectrum',20)
        job=job_for(identity);position=sky_at_click(job,x,y);points=[]
        frames=[f for f in job['frames'] if f['status']=='ready']
        available=len(frames)
        calibration_cache={}
        if method=='epsf' and available>64:
            frames=[frames[int(i)] for i in np.linspace(0,available-1,64)]
        for frame in frames:
            calibration_url=None
            try:
                if not (CACHE/(frame["cache_id"]+".fits")).exists():
                    raise FileNotFoundError('Native FITS not cached. Reload this exposure before measuring; no display pixels substituted.')
                with fits.open(CACHE/(frame['cache_id']+'.fits'),memmap=False) as hdus:
                    if method=='epsf':
                        key=(frame.get('release'),frame.get('detector'))
                        measurement=epsf_measure(hdus,frame,position,calibration_cache.setdefault(key,{}))
                        calibration_url=measurement.pop('calibration_url',None)
                    else:
                        calibration,calibration_url=cached_aperture_calibration(hdus,frame)
                        measurement=aperture_measure(hdus,position,radius,calibration)
            except (ValueError,KeyError,OSError,RequestException) as exc:measurement=dict(status='missing',reason=str(exc))
            measurement.pop('wavelength_calibration',None)
            points.append(dict(measurement,release=frame.get('release'),frame=frame['index'],exposure_id=frame.get('id'),date=frame.get('date') or Time(frame['mjd'],format='mjd').isot+'Z',mjd=frame['mjd'],detector=frame.get('detector'),source_url=frame.get('url') or frame.get('cutout_url'),quality_flags=frame.get('source_flag_values',[]),wavelength_calibration='released CWAVE/CBAND' if calibration_url else 'approximate WCS-WAVE',calibration_url=calibration_url))
        if method=='epsf':
            return dict(provenance='computed',source_pixels='observed',method=method,available=available,
                        ra=float(position.ra.deg),dec=float(position.dec.deg),radius_arcsec=None,
                        normalized_position=[x,y],points=points,notes=['Forced measurements use released ePSF, solid-angle and spectral calibration files.','Review-flagged points are excluded from dip screening.','Errors omit calibration and confusion systematics.'])
        return dict(provenance='computed',source_pixels='observed',method=method,available=available,ra=float(position.ra.deg),dec=float(position.dec.deg),radius_arcsec=radius,normalized_position=[x,y],points=points,notes=['Quicklook aperture flux, not a calibrated or aperture-corrected source spectrum.','Native pixels and conservative flags are used; background is estimated in a local annulus. No resampled display pixels are measured.','Measurements identify which wavelength map was used. Released CWAVE/CBAND is used where cached. Other measurements use approximate WCS-WAVE.','Error bars include native variance and annulus background uncertainty; calibration and confusion systematics are omitted.','Observations are taken at different times. Variability can shape this wavelength plot.'])
