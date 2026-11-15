"""Synthetic fixtures only; no test observations are served by the application."""
import copy
import numpy as np
import pytest
from backend import laya_sequence as seq
from backend.laya_review import ReviewCancelled

def frames():
    return [dict(id=str(i), index=i, date='2026-01-0'+str(i+1), mjd=61000.+i*2,
        detector=1, release='qr3', wavelength_um=1., url='https://example.invalid/test',
        status='ready' if i<2 else 'pending') for i in range(3)]

def task():
    return dict(id='test', status='running', total=3, loaded=0, reviewed=0, failed=[],
        batches=[], coverage={}, assignments={}, tracks=[], cancelled=False)

def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(seq, 'CACHE', tmp_path)
    p=dict(value=np.zeros((17,17)), variance=np.ones((17,17)), wavelength=np.ones((17,17)))
    monkeypatch.setattr(seq, 'load_products', lambda f:copy.deepcopy(p))
    return dict(frames=frames(), status='fetching')

def test_reviews_before_archive_finishes_and_counts_unique_exposures(monkeypatch,tmp_path):
    job=setup(monkeypatch,tmp_path);t=task();calls=[]
    def infer(*args,**kwargs):
        calls.append(job['frames'][2]['status'])
        job['frames'][2]['status']='ready';job['status']='complete'
        return {'answers':{'change':{'choice':'uncertain'}}}
    monkeypatch.setattr(seq,'infer',infer)
    seq.run_sequence(job,t)
    assert calls[0]=='pending'
    assert t['reviewed']==3 and len(set(t['reviewed_ids']))==3
    assert t['scientifically_comparable']==0
    assert len({b['key'] for b in t['batches']})==len(t['batches'])

def test_cancel_resume_keeps_completed_crops_without_double_counting(monkeypatch,tmp_path):
    job=setup(monkeypatch,tmp_path);job['frames'][2]['status']='ready';job['status']='complete'
    t=task();calls=[]
    def infer(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:raise ReviewCancelled('test cancellation')
        return {'answers':{'change':{'choice':'uncertain'}}}
    monkeypatch.setattr(seq,'infer',infer);seq.run_sequence(job,t)
    assert t['status']=='cancelled' and len(t['batches'])==1
    prior=t['batches'][0]['key'];t.update(cancelled=False,status='running')
    seq.run_sequence(job,t)
    assert t['reviewed']==3
    assert sum(b['key']==prior for b in t['batches'])==1

def test_missing_wavelength_never_becomes_reviewed(monkeypatch,tmp_path):
    job=setup(monkeypatch,tmp_path);job['frames']=job['frames'][:2];job['status']='complete';t=task()
    monkeypatch.setattr(seq,'load_products',lambda f:dict(value=np.zeros((17,17)),variance=np.ones((17,17))))
    monkeypatch.setattr(seq,'infer',lambda *a,**k:pytest.fail('must not infer incompatible data'))
    seq.run_sequence(job,t)
    assert t['reviewed']==0 and t['review_compatible']==0 and t['status']=='partial'

def test_crops_overlap_and_cover_edges_without_thresholding():
    boxes=seq.tiles((79,79));cover=np.zeros((79,79),int)
    for x0,y0,x1,y1 in boxes:cover[y0:y1,x0:x1]+=1
    assert cover.min()>=1 and cover.max()>1
    p=dict(value=np.zeros((17,17)),variance=np.ones((17,17)),wavelength=np.ones((17,17)))
    p['value'][8,8]=1.0;p['value'][8,9]=2.0
    image=np.asarray(seq.crop_sheet([(frames()[0],p),(frames()[1],p)],(0,0,17,17),np.ones((17,17),bool)))
    assert np.unique(image[32:,:,0]).size==3  # below-2.5 sigma samples remain distinct

@pytest.mark.parametrize('mutate',[
 lambda f:f.update(detector=2),
 lambda f:f.update(mjd=61000.2),
 lambda f:f.update(release='qr2'),
])
def test_incompatible_pairs_are_explicitly_unassessed(monkeypatch,tmp_path,mutate):
 job=setup(monkeypatch,tmp_path);job['frames']=job['frames'][:2];job['status']='complete';mutate(job['frames'][1]);t=task()
 monkeypatch.setattr(seq,'infer',lambda *a,**k:pytest.fail('must not review incompatible dates or bands'))
 seq.run_sequence(job,t)
 assert t['status']=='partial' and t['reviewed']==0 and t['unassessed']==2

def test_masked_pixels_do_not_get_a_false_negative_review(monkeypatch,tmp_path):
 job=setup(monkeypatch,tmp_path);job['frames']=job['frames'][:2];job['status']='complete';t=task()
 monkeypatch.setattr(seq,'load_products',lambda f:dict(value=np.full((17,17),np.nan),variance=np.ones((17,17)),wavelength=np.ones((17,17))))
 monkeypatch.setattr(seq,'infer',lambda *a,**k:pytest.fail('must not infer masked data'))
 seq.run_sequence(job,t)
 assert t['reviewed']==0 and t['status']=='partial'

def test_model_timeout_preserves_receipts_and_resume_deduplicates(monkeypatch,tmp_path):
 job=setup(monkeypatch,tmp_path);job['frames'][2]['status']='ready';job['status']='complete';t=task();count=0
 def model(*a,**k):
  nonlocal count
  count+=1
  if count==2:raise TimeoutError('bounded model timeout')
  return {'answers':{'change':{'choice':'uncertain'}}}
 monkeypatch.setattr(seq,'infer',model);seq.run_sequence(job,t)
 assert t['status']=='error' and len(t['batches'])==1 and t['failed_count']==1
 completed=t['batches'][0]['key'];t.update(status='running',cancelled=False)
 seq.run_sequence(job,t)
 assert t['reviewed']==3 and sum(b['key']==completed for b in t['batches'])==1

def test_malformed_model_answer_is_not_counted(monkeypatch,tmp_path):
 job=setup(monkeypatch,tmp_path);job['status']='paused';t=task()
 monkeypatch.setattr(seq,'infer',lambda *a,**k:{'answers':{}})
 seq.run_sequence(job,t)
 assert t['status']=='error' and t['reviewed']==0 and not t['batches']

def test_bad_input_and_paused_downloads_do_not_hang(monkeypatch,tmp_path):
 job=setup(monkeypatch,tmp_path);job['status']='paused';t=task()
 monkeypatch.setattr(seq,'load_products',lambda f:(_ for _ in ()).throw(ValueError('missing native arrays')))
 seq.run_sequence(job,t)
 assert t['status']=='paused' and t['failed_count']==2 and t['reviewed']==0
