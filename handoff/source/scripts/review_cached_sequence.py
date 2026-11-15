"""Review every available real cached WISE exposure with the installed local model.

This is explicitly a loaded subset, not the complete released archive. Missing
archive files are not replaced or downloaded by this validation command.
"""
import sys,json,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.cache_audit import cached_jobs
from backend.laya_review import installed,shutdown_worker
from backend.laya_sequence import run_sequence,sequence_identity
from backend.archive import ROOT
if not installed():raise SystemExit('Local Laya is not installed; no review result substituted.')
job=cached_jobs()['wise'];task=dict(id=sequence_identity(job),status='running',total=len(job['frames']),loaded=0,reviewed=0,batches_done=0,batches=[],tracks=[])
start=time.monotonic();worker=threading.Thread(target=run_sequence,args=(job,task));worker.start()
last=None
while worker.is_alive():
    state=(task.get('status'),task.get('loaded'),task.get('reviewed'),task.get('message'))
    if state!=last:print(state,flush=True);last=state
    worker.join(2)
task['scope']='Every available cached WISE exposure; loaded subset only, not the full release.'
task['archive_discovered']=job['discovered'];task['elapsed_seconds']=time.monotonic()-start
(ROOT/'docs/revision-laya-loaded.json').write_text(json.dumps(task,indent=2),encoding='utf-8')
print('Final:',task['status'],task.get('reviewed'),'/ cached',task['total'],'/ discovered',job['discovered'],flush=True)
shutdown_worker()
if task['status'] not in ('complete','partial'):raise SystemExit(1)
