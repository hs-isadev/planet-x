"""Actual HTTP/model validation; never supplies mock images or model results."""
import json,time,urllib.request
from pathlib import Path
BASE='http://127.0.0.1:8000'
def api(path,post=False):
    req=urllib.request.Request(BASE+path,method='POST' if post else 'GET')
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
report={'targets':[],'scope':'Real loaded subset, bounded integration run; pending archive exposures remain unreviewed.'}
start=time.monotonic()
while True:
    try:
        targets=json.loads(Path('docs/pipeline-browser.json').read_text(encoding='utf8'))['targets']
        if len(targets)==5:break
    except (OSError,ValueError):pass
    if time.monotonic()-start>300:raise RuntimeError('Five-target browser run did not finish')
    time.sleep(1)
for target in targets:
    jid=target['jobId'];job=api('/api/jobs/'+jid)
    r=api('/api/jobs/'+jid+'/laya-sequence',True);rid=r['id'];initial=len(r.get('batches',[]));events=[];start=time.monotonic()
    while r['status']=='running':
        event={k:r.get(k) for k in ['status','stage','loaded','prepared','reviewed','batches_done','last_progress_at','message']}
        if not events or event['stage']!=events[-1]['stage'] or event['reviewed']!=events[-1]['reviewed']:
            events.append(event);print(target['name'],json.dumps(event),flush=True)
        if r.get('reviewed',0)>=2 and r.get('batches_done',0)>=initial+4:break
        if time.monotonic()-start>250:break
        time.sleep(.5);r=api('/api/laya/sequence/'+rid)
    if r['status']=='running':
        at=time.monotonic();api('/api/laya/sequence/'+rid+'/cancel',True)
        while r['status']=='running' and time.monotonic()-at<15:
            time.sleep(.25);r=api('/api/laya/sequence/'+rid)
        cancellation_seconds=round(time.monotonic()-at,2)
    else:cancellation_seconds=None
    job=api('/api/jobs/'+jid)
    result=dict(name=target['name'],job_id=jid,review_id=rid,discovered=len(job['frames']),loaded=job['ready'],
        prepared=r.get('prepared'),reviewed=r.get('reviewed'),pending=job.get('pending'),failed_downloads=job['failed'],
        review_compatible=r.get('review_compatible'),scientifically_comparable=r.get('scientifically_comparable'),
        status=r['status'],stage=r.get('stage'),message=r.get('message'),failed=r.get('failed'),
        batches_done=r.get('batches_done'),unique_batch_keys=len({b['key'] for b in r.get('batches',[])}),
        cancellation_seconds=cancellation_seconds,events=events)
    report['targets'].append(result);Path('docs/pipeline-five-laya.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print('RESULT',json.dumps(result),flush=True)
