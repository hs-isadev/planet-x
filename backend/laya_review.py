"""Experimental LOCAL Laya Vision review of genuine algorithm-proposed image regions."""
import json,sys,subprocess,threading,queue,time,io,base64,atexit
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from scipy.ndimage import label
from fastapi import HTTPException
from .archive import ROOT,CACHE,key_for,atomic_json,fetch_frame
from .analysis import load_products
from .quicklook import standardized,change_masks,comparable
LOCK=threading.Lock();REVIEWS={};PROC=None;LINES=queue.Queue()
PYTHON=ROOT/'runtime/laya-venv'/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
def installed():
    return PYTHON.exists() and (ROOT/'runtime/laya-model-revision.json').exists() and (ROOT/'runtime/laya-venv/Lib/site-packages/laya').exists() if sys.platform=='win32' else PYTHON.exists() and (ROOT/'runtime/laya-model-revision.json').exists()
def infer(file,note):
    global PROC,LINES
    if PROC is None or PROC.poll() is not None:
        LINES=queue.Queue();log=open(ROOT/'runtime/laya-worker.log','a',encoding='utf8')
        PROC=subprocess.Popen([str(PYTHON),str(ROOT/'backend/laya_worker.py')],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        stream=PROC.stdout;channel=LINES
        def reader():
            for line in stream:
                try:channel.put(json.loads(line))
                except ValueError:continue
            channel.put({'ok':False,'error':'Local Laya worker stopped. See runtime/laya-worker.log.'})
        threading.Thread(target=reader,daemon=True).start()
    PROC.stdin.write(json.dumps(dict(image=str(file),note=note))+'\n');PROC.stdin.flush()
    try:result=LINES.get(timeout=240)
    except queue.Empty:
        PROC.kill();PROC=None
        raise RuntimeError('Local Laya inference timed out; no model decision was substituted.')
    if not result.get('ok'):raise RuntimeError(result.get('error','Local Laya inference failed'))
    return result['result']
def shutdown_worker():
    global PROC
    if PROC is not None:
        try:PROC.stdin.close();PROC.wait(timeout=8)
        except Exception:
            try:PROC.kill()
            except OSError:pass
        PROC=None
atexit.register(shutdown_worker)

def gray(product):
    _,_,snr,good=standardized(product)
    v=(np.arcsinh(3*np.clip((np.nan_to_num(snr)-2.5)/9.5,0,1))/np.arcsinh(3)*232).astype('u1')
    rgb=np.repeat(v[...,None],3,axis=-1);rgb[~good]=[35,45,57]
    return rgb
def review_pair(a,b,identity):
    earlier,later=sorted([a,b],key=lambda f:f['mjd']);pa,pb=load_products(earlier),load_products(later)
    if pa['value'].shape!=pb['value'].shape:raise ValueError('Comparison grids differ.')
    masks=change_masks(pb,pa);regions,n=label(masks['red'])
    objects=[]
    for i in range(1,n+1):
        yy,xx=np.where(regions==i)
        if len(xx):objects.append((len(xx),float(xx.mean()),float(yy.mean())))
    objects.sort(reverse=True);limited=len(objects)>8;objects=objects[:8]
    ga,gb=gray(pa),gray(pb);h,w=ga.shape[:2];answers=[]
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
        accepted=choice in ['appeared or brightened','disappeared or faded','shifted position']
        answers.append(dict(x=(x+.5)/w,y=1-(y+.5)/h,radius=max(8,np.sqrt(count)*2)/w,pixels=count,choice=choice,highlight_red=accepted and count>0,answer=answer))
    return dict(status='complete',regions=answers,frame=a['index'],reference=b['index'],dates=[earlier['date'],later['date']],limited=limited,model=json.loads((ROOT/'runtime/laya-model-revision.json').read_text()),provenance='computed / experimental local AI review',message=(f'Laya reviewed {len(answers)} proposed regions' if objects[0][0] else 'Laya assessed the whole field; no localized statistical candidate')+(' (first 8 only)' if limited else ''),note='General visual model; scores are not calibrated for SPHEREx. Red rings = model favors a visible change; amber = other/uncertain. Not confirmed motion, a source identification, or a validated astronomical detection.')
def run_review(a,b,identity,file):
    try:
        with LOCK:
            result=review_pair(a,b,identity);atomic_json(file,result);REVIEWS[identity].update(result)
    except Exception as e:REVIEWS[identity].update(status='error',message=str(e))
def install_laya_routes(app,jobs,guard):
    @app.get('/api/laya/status')
    def status():
        return dict(installed=installed(),model='thaitea/laya-vision',source='https://github.com/r33drichards/laya-vision',local=True)
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
        identity='laya-'+key_for(a['cache_id']+'|'+b['cache_id']+'|'+(ROOT/'runtime/laya-model-revision.json').read_text()+'|prompt-v1')
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
