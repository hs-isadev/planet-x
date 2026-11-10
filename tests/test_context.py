import io
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from backend.catalogs import propagate_gaia,catalog_overlay
from backend.catalogs import propagate_wise
import backend.main as main

def test_wise_uses_unique_gaia_astrometry_not_apparent_allwise_motion():
    from astropy.time import Time
    from backend.catalogs import wise_gaia_context
    epoch=float(Time(55400.,format='mjd').jyear)
    row=dict(ra=199.9999,dec=0.,ra_pm=200.,dec_pm=0.,pmra=90000.,pmdec=90000.)
    gaia=dict(id='known-gaia',ra=200.,dec=0.,pmra=1000.,pmdec=0.,ref_epoch=epoch,ruwe=1.)
    mjd=55400.+365.25*10
    context=wise_gaia_context([gaia],mjd)
    updated=propagate_wise(row,mjd,context)
    assert updated['motion_applied']
    assert updated['ra']==pytest.approx(200+10/3600,abs=1e-7)
    assert updated['dec']==pytest.approx(0,abs=1e-7)
    assert updated['gaia_source_id']=='known-gaia'
    assert not propagate_wise(row,mjd)['motion_applied']
    assert not propagate_wise(dict(row,pmcode='1Y008'),mjd,context)['motion_applied']
    ambiguous=wise_gaia_context([gaia,dict(gaia,id='other')],mjd)
    assert not propagate_wise(row,mjd,ambiguous)['motion_applied']
    assert row['ra']==199.9999


def test_gaia_propagates_to_image_date_and_preserves_missing_motion():
    row=dict(id='123',ra=359.999,dec=0.,pmra=1000.,pmdec=0.,ref_epoch=2016.)
    from astropy.time import Time
    updated=propagate_gaia(row,float(Time(2026.,format='jyear').mjd))
    assert updated['motion_applied'] and updated['ra']==pytest.approx((359.999+10/3600)%360,abs=1e-6)
    missing=dict(row,pmra=None)
    assert not propagate_gaia(missing,60000)['motion_applied']
    assert row['ra']==359.999


def test_catalog_markers_project_onto_registered_image(monkeypatch):
    import backend.catalogs as catalogs
    monkeypatch.setattr(catalogs,'gaia_rows',lambda *a,**k:dict(rows=[dict(id='1',ra=133.,dec=-7.,ref_epoch=2016.,pmra=0.,pmdec=0.,catalog='Gaia DR3')],truncated=False))
    job=dict(ra=133.,dec=-7.,fov=8,frames=[dict(mjd=60000)])
    result=catalog_overlay(job,0,'gaia')
    assert len(result['markers'])==1
    assert result['markers'][0]['x']==pytest.approx(.5,abs=1e-8)
    assert result['markers'][0]['y']==pytest.approx(.5,abs=1e-8)
    assert result['provenance']=='catalog'


def test_observed_gif_export_has_real_rendered_frames(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'CACHE',tmp_path)
    frames=[]
    for i in range(2):
        arr=np.zeros((16,16),dtype='f4');arr[7,7+i]=10;np.save(tmp_path/(str(i)+'.npy'),arr)
        frames.append(dict(index=i,cache_id=str(i),status='ready',date=f'2025-0{i+1}-01T00:00:00Z',band='TEST FIXTURE'))
    main.JOBS['gif-test']=dict(frames=frames,contrast=dict(black=0.,white=10.))
    r=TestClient(main.app).get('/api/jobs/gif-test/export.gif')
    assert r.status_code==200 and r.content.startswith(b'GIF89a')
    image=Image.open(io.BytesIO(r.content))
    assert image.n_frames==2 and image.size==(320,366)
    assert b'Observed SPHEREx' in image.info['comment']
    del main.JOBS['gif-test']
