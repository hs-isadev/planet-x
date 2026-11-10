import os,time
from backend import archive

def test_disk_budget_evicts_whole_old_exposure_groups(tmp_path,monkeypatch):
    monkeypatch.setattr(archive,'CACHE',tmp_path)
    monkeypatch.setitem(archive.CONFIG,'cache_max_bytes',35)
    old,new='a'*24,'b'*24
    for identity,age in [(old,100),(new,0)]:
        for ext in ('.npy','.npz','.fits'):
            p=tmp_path/(identity+ext);p.write_bytes(b'0123456789');stamp=time.time()-age;os.utime(p,(stamp,stamp))
    archive.prune_cache(protected={new})
    assert not any((tmp_path/(old+ext)).exists() for ext in ('.npy','.npz','.fits'))
    assert all((tmp_path/(new+ext)).exists() for ext in ('.npy','.npz','.fits'))

def test_missing_cached_observation_is_retrieved_not_replaced(tmp_path,monkeypatch):
    monkeypatch.setattr(archive,'CACHE',tmp_path);calls=[]
    def fetch(row,ra,dec,fov):calls.append((row['id'],ra,dec,fov));return 'new',{'provenance':'observed'}
    monkeypatch.setattr(archive,'fetch_frame',fetch)
    frame={'id':'real-archive-row','cache_id':'expired','url':'https://irsa.ipac.caltech.edu/ibe/data/spherex/qr3/level2/example.fits'}
    archive.ensure_frame_files(frame,dict(ra=1,dec=2,fov=8))
    assert calls==[('real-archive-row',1,2,8)] and frame['cache_id']=='new'
    assert frame['provenance']=='observed'


def test_prefetch_pause_and_resume_preserve_real_manifest(tmp_path,monkeypatch):
    import numpy as np
    from backend import main
    monkeypatch.setattr(main,'CACHE',tmp_path)
    rows=[dict(id=str(i),url='test-only',mjd=60000+i,date='test-only',band='SPHEREx-D6',detector=6) for i in range(4)]
    monkeypatch.setattr(main,'discover',lambda *args:rows)
    job=dict(ra=1,dec=2,fov=8,frames=[],contrast=None,status='querying')
    calls=[]
    def fetch(frame,*args):
        calls.append(frame['id']);np.save(tmp_path/(frame['id']+'.npy'),np.arange(256,dtype='f4').reshape(16,16))
        if len(calls)==1:job['prefetch_paused']=True
        return frame['id'],dict(unit='MJy/sr')
    monkeypatch.setattr(main,'fetch_frame',fetch)
    main.run_job(job)
    assert job['status']=='paused' and len(job['frames'])==4 and len(calls)==1
    contrast=dict(job['contrast']);job['prefetch_paused']=False
    main.run_job(job,resume=True)
    assert job['status']=='complete' and len(calls)==4
    assert [f['mjd'] for f in job['frames']]==[60000,60001,60002,60003]
    assert all(f['status']=='ready' for f in job['frames']) and job['contrast']==contrast


def test_equivalent_float_catalog_query_reuses_genuine_cache(tmp_path,monkeypatch):
    from backend import catalogs
    import json
    monkeypatch.setattr(catalogs,'CACHE',tmp_path)
    q1="SELECT TOP 1001 ra,dec FROM gaiadr3.gaia_source WHERE 1=CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',133.79512916666664,-7.245147222222222,0.127614237491)) ORDER BY phot_g_mean_mag ASC"
    q2=q1.replace('133.79512916666664','133.79512916666667')
    payload={'rows':[{'id':'test-fixture-only','ra':133.79,'dec':-7.24}],'query':q1,'limit':1000,'truncated':False}
    (tmp_path/('gaia-'+catalogs.key_for(q1)+'.json')).write_text(json.dumps(payload))
    assert catalogs.cached_gaia_query(q2)==payload
    assert catalogs.cached_gaia_query(q2.replace('133.79512916666667','134.79512916666667')) is None
