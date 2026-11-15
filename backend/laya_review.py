"""Experimental LOCAL Laya Vision review of genuine algorithm-proposed image regions."""
import json,sys,subprocess,threading,queue,time,io,base64,atexit,os,signal
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
from PIL import Image,ImageDraw
from scipy.ndimage import label
from fastapi import HTTPException
from .archive import ROOT,CACHE,key_for,atomic_json,fetch_frame
from .analysis import load_products
from .quicklook import standardized,change_masks,comparable
LOCK=threading.Lock();REVIEWS={};PROC=None;LINES=queue.Queue()
LAST_SUCCESS_AT=None
PYTHON=ROOT/'runtime/laya-venv'/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
def installed():
    return PYTHON.exists() and (ROOT/'runtime/laya-model-revision.json').exists() and (ROOT/'runtime/laya-venv/Lib/site-packages/laya').exists() if sys.platform=='win32' else PYTHON.exists() and (ROOT/'runtime/laya-model-revision.json').exists()
class ReviewCancelled(RuntimeError):
    pass

def availability():
    required = [PYTHON, ROOT/'runtime/laya-model-revision.json', ROOT/'runtime/laya-model/vlm_agent_config.json', ROOT/'runtime/laya-model/model.safetensors', ROOT/'runtime/laya-model/backbone/config.json']
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    return dict(installed=installed() and not missing, missing=missing,
                inference_verified=LAST_SUCCESS_AT is not None, last_success_at=LAST_SUCCESS_AT, worker_running=PROC is not None and PROC.poll() is None,
                note='Installed files do not prove successful inference. See a completed review receipt and runtime/laya-worker.log.')

def shutdown_worker():
    global PROC, LINES
    proc, PROC = PROC, None
    LINES = queue.Queue()
    if proc is not None:
        try:
            if sys.platform == 'win32':
                # A venv python.exe is a launcher with a child interpreter on Windows.
                subprocess.run([str(Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32/taskkill.exe'),
                    '/PID', str(proc.pid), '/T', '/F'], stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        for stream in (proc.stdin, proc.stdout):
            try:
                stream.close()
            except (OSError, AttributeError):
                pass

atexit.register(shutdown_worker)

def infer(file, note, cancelled=lambda: False, progress=lambda stage: None, timeout=240):
    # Caller owns LOCK. A killed worker's queue is discarded; late results cannot
    # be attributed to the next request. Requests also carry an explicit ID.
    global PROC, LINES, LAST_SUCCESS_AT
    import uuid
    if cancelled():
        raise ReviewCancelled('Review cancelled before inference.')
    if PROC is None or PROC.poll() is not None:
        LINES = queue.Queue()
        with open(ROOT/'runtime/laya-worker.log', 'a', encoding='utf8') as log:
            PROC = subprocess.Popen([str(PYTHON), str(ROOT/'backend/laya_worker.py')], cwd=ROOT,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1,
                start_new_session=sys.platform != 'win32',
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        stream, channel = PROC.stdout, LINES
        def reader():
            for line in stream:
                try:
                    channel.put(json.loads(line))
                except ValueError:
                    continue
            channel.put({'ok': False, 'error': 'Local Laya worker stopped. See runtime/laya-worker.log.'})
        threading.Thread(target=reader, daemon=True).start()
    request_id = uuid.uuid4().hex
    deadline = time.monotonic() + timeout
    try:
        progress('starting_model')
        PROC.stdin.write(json.dumps(dict(request_id=request_id, image=str(file), note=note))+'\n')
        PROC.stdin.flush()
        while True:
            if cancelled():
                raise ReviewCancelled('Review cancelled; local inference process terminated.')
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f'Local Laya exceeded {timeout}s. Worker terminated; completed crops retained. Resume to retry. See runtime/laya-worker.log.')
            try:
                result = LINES.get(timeout=min(.25, remaining))
            except queue.Empty:
                continue
            if result.get('request_id') not in (None, request_id):
                continue
            if 'stage' in result:
                progress(result['stage'])
                continue
            if not result.get('ok'):
                raise RuntimeError(result.get('error', 'Local Laya inference failed'))
            LAST_SUCCESS_AT = datetime.now(timezone.utc).isoformat()
            return result['result']
    except Exception:
        shutdown_worker()
        raise

def gray(product):
    _,_,snr,good=standardized(product)
    normalized=(np.arcsinh(np.nan_to_num(snr)/2)+np.arcsinh(2.5))/(np.arcsinh(10)+np.arcsinh(2.5))
    v=(np.clip(normalized,0,1)*235).astype('u1')
    rgb=np.repeat(v[...,None],3,axis=-1);rgb[~good]=[35,45,57]
    return rgb
def review_pair(a,b,identity):
    earlier,later=sorted([a,b],key=lambda f:f['mjd']);pa,pb=load_products(earlier),load_products(later)
    if pa['value'].shape!=pb['value'].shape:raise ValueError('Comparison grids differ.')
    masks=change_masks(pb,pa)
    if masks['comparable'].sum()<9:
        raise ValueError('Fewer than nine usable pixels share a preliminary wavelength match. Comparison unassessed.')
    regions,n=label(masks['red'])
    objects=[]
    for i in range(1,n+1):
        yy,xx=np.where(regions==i)
        if len(xx):objects.append((len(xx),float(xx.mean()),float(yy.mean())))
    objects.sort(reverse=True);limited=len(objects)>8;objects=objects[:8]
    ga,gb=gray(pa),gray(pb);h,w=ga.shape[:2];answers=[]
    ga[~masks['comparable']]=gb[~masks['comparable']]=[35,45,57]
    if not objects:objects=[(0,(w-1)/2,(h-1)/2)]
    for index,(count,x,y) in enumerate(objects):
        x0=max(0,min(w-16,int(x)-8));y0=max(0,min(h-16,int(y)-8));x1=min(w,x0+16);y1=min(h,y0+16)
        if count==0:x0,y0,x1,y1=0,0,w,h
        left=Image.fromarray(np.flipud(ga[y0:y1,x0:x1])).resize((256,256),Image.Resampling.NEAREST)
        right=Image.fromarray(np.flipud(gb[y0:y1,x0:x1])).resize((256,256),Image.Resampling.NEAREST)
        image=Image.new('RGB',(528,288),'#10151c');image.paste(left,(0,24));image.paste(right,(272,24));draw=ImageDraw.Draw(image)
        draw.text((8,5),'A '+earlier['date'][:10],fill='white');draw.text((280,5),'B '+later['date'][:10],fill='white')
        # Passive brackets locate the actual candidate; they add no science pixels.
        cx=(x-x0+.5)/(x1-x0)*256;cy=(y1-y-.5)/(y1-y0)*256+24
        for shift in (0,272):draw.ellipse((shift+cx-20,cy-20,shift+cx+20,cy+20),outline='#98a5b5',width=1)
        file=CACHE/(identity+f'-crop-{index}.png');image.save(file)
        note=f'Registered SPHEREx infrared observations, not visible-light photographs. Central proposed region: {count} residual pixels. Detector {a["detector"]}; wavelengths {earlier["wavelength_um"]:.3f} and {later["wavelength_um"]:.3f} microns. No PSF matching. Gray-blue means masked data. These astronomy images are outside the general model validation domain.'
        REVIEWS[identity]['message']=f'Laya reviewing candidate {index+1} of {len(objects)} locally'
        result=infer(file,note);answer=result.get('answers',{}).get('change',{})
        choice=answer.get('choice','uncertain')
        if not isinstance(choice,str):choice=str(choice)
        answers.append(dict(x=(x+.5)/w,y=1-(y+.5)/h,radius=max(8,np.sqrt(count)*2)/w,pixels=count,choice=choice,assessment='uncertain'))
    return dict(status='complete',regions=answers,frame=a['index'],reference=b['index'],dates=[earlier['date'],later['date']],limited=limited,model=json.loads((ROOT/'runtime/laya-model-revision.json').read_text()),provenance='computed / experimental local AI review',message=(f'Laya reviewed {len(answers)} proposed regions' if objects[0][0] else 'Laya assessed the whole field; no localized statistical candidate')+(' (first 8 only)' if limited else ''),note='General visual model; scores are not calibrated for SPHEREx. Amber rings mark model-reviewed regions. Interpretation remains uncertain pending wavelength calibration, registration and PSF validation.')
def run_review(a,b,identity,file):
    try:
        with LOCK:
            result=review_pair(a,b,identity);atomic_json(file,result);REVIEWS[identity].update(result)
    except Exception as e:REVIEWS[identity].update(status='error',message=str(e))
def install_laya_routes(app,jobs,guard):
    @app.get('/api/laya/status')
    def status():
        return dict(**availability(),model='thaitea/laya-vision',source='https://github.com/r33drichards/laya-vision',local=True)
    @app.post('/api/jobs/{jobid}/laya')
    def start(jobid:str,frame:int):
        if not installed():raise HTTPException(503,'Laya Vision is not installed or its checkpoint download has not completed.')
        with guard:
            if jobid not in jobs:raise HTTPException(404,'Observation session expired.')
            frames=jobs[jobid]['frames']
            if not 0<=frame<len(frames) or frames[frame]['status']!='ready':raise HTTPException(422,'Select a loaded observed frame.')
            a=dict(frames[frame]);others=[f for f in frames if f.get('status')=='ready' and comparable(a,f)]
            if not others:
                if sum(r['status']=='running' for r in REVIEWS.values())>=2:raise HTTPException(429,'Local Laya is preparing other reviews. Please retry after one finishes.')
                identity='laya-prepare-'+key_for(jobid+'|'+str(frame))
                if identity in REVIEWS and REVIEWS[identity]['status']=='running':return REVIEWS[identity]
                REVIEWS[identity]=dict(id=identity,status='running',frame=frame,message='Finding and loading a compatible real observation for Laya…')
                def prepare():
                    try:
                        job=jobs[jobid]
                        candidates=[f for f in frames if f.get('detector')==a.get('detector') and abs(f['mjd']-a['mjd'])>=1]
                        candidates.sort(key=lambda f:(0 if f.get('wavelength_um') is not None and abs(f['wavelength_um']-a['wavelength_um'])<=.025 else 1,-abs(f['mjd']-a['mjd'])))
                        for candidate in candidates[:24]:
                            if candidate.get('status')!='ready':
                                REVIEWS[identity]['message']='Loading compatible reference candidate '+str(candidate['index']+1)+' from IRSA…'
                                try:
                                    cache_id,meta=fetch_frame(candidate,job['ra'],job['dec'],job['fov'])
                                    with guard:candidate.update(meta,cache_id=cache_id,status='ready',ra=job['ra'],dec=job['dec'],fov=job['fov'])
                                except Exception:continue
                            if comparable(a,candidate):
                                run_review(a,dict(candidate),identity,CACHE/(identity+'.json'));return
                        available=[f for f in frames if f.get('status')=='ready']
                        pair=next(((x,y) for x in available for y in available if comparable(x,y)),None)
                        if pair:
                            run_review(dict(pair[0]),dict(pair[1]),identity,CACHE/(identity+'.json'));return
                        raise ValueError('No compatible comparison could be fetched after checking 24 candidate exposures. This field or release may not supply a usable repeated bandpass; no AI result was invented.')
                    except Exception as exc:REVIEWS[identity].update(status='error',message=str(exc))
                threading.Thread(target=prepare,daemon=True).start()
                return REVIEWS[identity]
            b=dict(max(others,key=lambda f:abs(f['mjd']-a['mjd'])))
        identity='laya-'+key_for(a['cache_id']+'|'+b['cache_id']+'|'+(ROOT/'runtime/laya-model-revision.json').read_text()+'|prompt-v2-compatibility')
        file=CACHE/(identity+'.json')
        if file.exists():
            result=json.loads(file.read_text());REVIEWS[identity]=dict(result,id=identity);return REVIEWS[identity]
        if identity in REVIEWS and REVIEWS[identity]['status']!='error':return REVIEWS[identity]
        if sum(r['status']=='running' for r in REVIEWS.values())>=2:raise HTTPException(429,'Local Laya is busy. Retry after this review finishes.')
        for key in list(REVIEWS):
            if len(REVIEWS)>32 and REVIEWS[key]['status']!='running':REVIEWS.pop(key)
        REVIEWS[identity]=dict(id=identity,status='running',frame=frame,message='Loading local Laya Vision; observed image remains available.')
        threading.Thread(target=run_review,args=(a,b,identity,file),daemon=True).start()
        return REVIEWS[identity]
    @app.get('/api/laya/reviews/{identity}')
    def poll(identity:str):
        if identity not in REVIEWS:raise HTTPException(404,'Review session expired; run the review again.')
        return REVIEWS[identity]
