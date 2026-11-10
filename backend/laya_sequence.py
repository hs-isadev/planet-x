"""Full-sequence local AI review. Every discovered frame has explicit coverage."""
import json,threading,time
import numpy as np
from PIL import Image,ImageDraw
from scipy.ndimage import maximum_filter
from fastapi import HTTPException
from .archive import CACHE,fetch_frame,key_for,atomic_json
from .analysis import load_products
from .quicklook import standardized
from .laya_review import installed,infer,LOCK
from .motion_tracks import fit_track,temporal_batches,reject_common_motion
TASKS={}
def sequence_identity(job):
    return 'laya-seq-'+key_for(str(float(job['ra']))+'|'+str(float(job['dec']))+'|'+str(float(job['fov']))+'|'+ '|'.join(f['id'] for f in job['frames'])+'|contact-v4-native-wavelength-independent-epochs')
def filter_decisions(result):
    for batch in result.get('batches',[]):
        batch.setdefault('raw_model_choice',batch['choice'])
        if len(batch['frames'])<2:batch['choice']='uncertain'
    for track in result.get('tracks',[]):
        ids={p['frame'] for p in track['points']}
        track['model_supported']=any(b['group']==track['group'] and b['choice']=='shifted position' and len(ids.intersection(b['frames']))>=2 for b in result.get('batches',[]))
    count=sum(t['model_supported'] for t in result.get('tracks',[]))
    result['supported_motion_candidates']=count
    result['message']=f"Laya reviewed {result['reviewed']} / {result['total']} real frames. {count} model-supported motion candidates; {len(result.get('tracks',[]))} deterministic peak associations are not confirmed detections."
    result['note']='Every successfully loaded exposure was reviewed, with earliest/latest context in long groups. Candidate tracks require four independent nights, >=30 days, >=5-sigma fitted velocity, low scatter and leave-one-out consistency. Batch-level VQA support requires at least two points from that track in the reviewed panel; it is not individual-source identification. Original arrays and masks are unchanged. Faint motion can be rejected; zero candidates does not prove no motion.'
    return result

def run_sequence(job,task):
    groups={};failed=[]
    try:
        for f in sorted(job['frames'],key=lambda f:f['mjd']):
            if task.get('cancelled'):task.update(status='cancelled');return
            task['message']=f"Loading real frame {task['loaded']+len(failed)+1} of {task['total']}"
            try:
                if f.get('status')!='ready':
                    cid,meta=fetch_frame(f,job['ra'],job['dec'],job['fov']);f.update(meta,cache_id=cid,status='ready',ra=job['ra'],dec=job['dec'],fov=job['fov'])
                p=load_products(f);_,_,snr,valid=standardized(p)
                wave=f.get('wavelength_um')
                if wave is None:raise ValueError('Missing wavelength')
                key=f"D{f['detector']}:{int(wave/.025)}"
                groups.setdefault(key,[]).append((dict(f,_wavelength_map=p.get('wavelength')),snr,valid))
                task['loaded']+=1
            except Exception as e:failed.append(dict(frame=f['index'],reason=str(e)))
        batches=[];tracks=[];common_rejected=0
        work=sum(len(temporal_batches(g)) for g in groups.values());task['batches_total']=work
        reviewed=set()
        for key,group in groups.items():
            group.sort(key=lambda v:v[0]['mjd'])
            group_tracks=[]
            # Persistent high-S/N peaks, linked locally in registered sky coordinates.
            detections=[]
            for f,snr,valid in group:
                peaks=valid&(snr>=5)&(snr==maximum_filter(np.nan_to_num(snr,nan=-1e9),size=3))
                yy,xx=np.where(peaks);order=np.argsort(snr[yy,xx])[::-1]
                for j in order[:100]:
                    x,y=int(xx[j]),int(yy[j]);candidates=[t for t in detections if t['points'][-1]['frame']!=f['index'] and np.hypot(t['points'][-1]['x']-x,t['points'][-1]['y']-y)<=3]
                    t=min(candidates,key=lambda t:np.hypot(t['points'][-1]['x']-x,t['points'][-1]['y']-y)) if candidates else {'group':key,'points':[]}
                    if not candidates:detections.append(t)
                    wave=f['_wavelength_map'][y,x] if f.get('_wavelength_map') is not None else np.nan
                    t['points'].append(dict(frame=f['index'],mjd=f['mjd'],x=x,y=y,snr=float(snr[y,x]),wavelength_um=float(wave) if np.isfinite(wave) else None))
            for t in detections:
                fit=fit_track(t['points'])
                if fit:
                    group_tracks.append(dict(t,**fit,arcsec_per_year=float(np.linalg.norm(fit['velocity_pixels_per_year'])*group[0][0]['scale_arcsec']),note='Computed peak association; confusion, PSF changes and calibration can mimic motion.'))
            group_tracks,rejected=reject_common_motion(group_tracks);common_rejected+=rejected;tracks.extend(group_tracks)
            task['common_mode_rejected']=common_rejected
            for chunk in temporal_batches(group):
                if task.get('cancelled'):task.update(status='cancelled');return
                chunk=sorted(chunk,key=lambda v:v[0]['mjd']);sheet=Image.new('RGB',(512,288),'#10151c');draw=ImageDraw.Draw(sheet)
                for index,(f,snr,valid) in enumerate(chunk):
                    v=(np.arcsinh(3*np.clip((np.nan_to_num(snr)-2.5)/9.5,0,1))/np.arcsinh(3)*232).astype('u1')
                    rgb=np.repeat(v[...,None],3,axis=-1);rgb[~valid]=[35,45,57]
                    image=Image.fromarray(np.flipud(rgb)).resize((128,128),Image.Resampling.NEAREST)
                    x=(index%4)*128;y=(index//4)*144;sheet.paste(image,(x,y+16));draw.text((x+3,y+2),f"{index+1} {f['date'][:10]}",fill='white')
                file=CACHE/(task['id']+f'-{len(batches)}.png');sheet.save(file)
                task['message']=f"Laya reviewing temporal batch {len(batches)+1} of {work}; {task['loaded']} real frames loaded"
                note=f"Chronological SPHEREx infrared sequence {key}, left to right then next row. {len(chunk)} actual exposures, dates labeled. Same detector and wavelength bin <=0.025 microns. Gray-blue pixels are masked/unknown. Follow repeated sources throughout all panels; distinguish coherent movement from one-frame noise. All images share 2.5-12 sigma display. General model not calibrated for astronomy."
                with LOCK:result=infer(file,note)
                answer=result.get('answers',{}).get('change',{})
                batches.append(dict(group=key,frames=[f['index'] for f,_,_ in chunk],choice=answer.get('choice','uncertain'),answer=answer))
                reviewed.update(f['id'] for f,_,_ in chunk)
                task['reviewed']=len(reviewed);task['batches_done']=len(batches);task['batches']=list(batches);task['tracks']=list(tracks)
        result=dict(status='complete' if not failed else 'partial',id=task['id'],total=task['total'],loaded=task['loaded'],reviewed=task['reviewed'],failed=failed,batches=batches,tracks=tracks,message=f"Reviewed {task['reviewed']} of {task['total']} real frames with Laya; {len(tracks)} computed motion-track candidates.",note='All loaded frames were included. Single-image-model temporal contact sheets and pixel association are experimental, not confirmed detections. Noise filtering may remove faint true sources; original arrays are unchanged.')
        result['common_mode_rejected']=common_rejected
        result=filter_decisions(result)
        task.update(result);atomic_json(CACHE/(task['id']+'.json'),result)
    except Exception as e:task.update(status='error',message=str(e))
def install_sequence_routes(app,jobs,guard):
    @app.post('/api/jobs/{jobid}/laya-sequence')
    def start(jobid:str):
        if not installed():raise HTTPException(503,'Local Laya is not installed.')
        with guard:
            if jobid not in jobs:raise HTTPException(404,'Observation session expired')
            job=jobs[jobid]
            if not job['frames']:raise HTTPException(425,'Wait for archive discovery.')
        identity=sequence_identity(job)
        receipt=CACHE/(identity+'.json')
        if receipt.exists():
            saved=json.loads(receipt.read_text())
            if saved.get('status')=='complete':
                TASKS[identity]=filter_decisions(saved)
                return TASKS[identity]
        if identity in TASKS and TASKS[identity]['status']=='running':return TASKS[identity]
        if any(t['status']=='running' for t in TASKS.values()):raise HTTPException(429,'A sequence review is already running. Cancel it or wait.')
        task=dict(id=identity,status='running',total=len(job['frames']),loaded=0,reviewed=0,batches_done=0,batches=[],tracks=[],message='Preparing full-sequence local review')
        TASKS[identity]=task;threading.Thread(target=run_sequence,args=(job,task),daemon=True).start();return task
    @app.get('/api/laya/sequence/{identity}')
    def poll(identity:str):
        if identity not in TASKS:raise HTTPException(404,'Sequence review expired')
        return TASKS[identity]
    @app.post('/api/laya/sequence/{identity}/cancel')
    def cancel(identity:str):
        if identity in TASKS:TASKS[identity]['cancelled']=True
        return {'cancelled':True}
