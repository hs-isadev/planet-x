import io
import time
import numpy as np
import pytest
from astropy.io import fits
from fastapi.testclient import TestClient
from backend.coordinates import parse_coordinates
from backend.archive import align_cutout, output_grid, discovery_query
import backend.main as main

@pytest.mark.parametrize("ra,dec,expected", [
    ("08:55:10.831", "-07:14:42.53", (133.79512916666667,-7.2451472222)),
    ("08h55m10.831s", "-07d14m42.53s", (133.79512916666667,-7.2451472222)),
    ("133.7951291667", "-7.2451472222", (133.7951291667,-7.2451472222)),
    ("0", "-90", (0,-90)), ("359.999", "90", (359.999,90)),
    ("120d", "+20d", (120,20)), ("12 00 00", "+20 00 00", (180,20))])
def test_coordinates(ra,dec,expected):
    c=parse_coordinates(ra,dec)
    assert c.ra.deg == pytest.approx(expected[0], abs=1e-7)
    assert c.dec.deg == pytest.approx(expected[1], abs=1e-7)

@pytest.mark.parametrize("ra,dec", [("360","0"),("-1","0"),("0","91"),("nan","0"),("inf","0"),("x","0"),("","0"),("25:00:00","0"),("0","-91")])
def test_invalid_coordinates(ra,dec):
    with pytest.raises(ValueError): parse_coordinates(ra,dec)


def fixture_mef():
    wcs,n,scale=output_grid(133.7951291667,-7.2451472222,4)
    arr=np.ones((n,n),dtype=np.float32)
    arr[n//2,n//2]=100
    flags=np.full((n,n),2097152,dtype=np.int32)
    flags[5:9,5:9]=1  # deliberately bad region
    return fits.HDUList([fits.PrimaryHDU(),fits.ImageHDU(arr,header=wcs.to_header(),name="IMAGE"),fits.ImageHDU(flags,name="FLAGS"),fits.ImageHDU(np.ones_like(arr),name="VARIANCE")])


def test_alignment_and_mask():
    values,meta=align_cutout(fixture_mef(),133.7951291667,-7.2451472222,4)
    assert np.isnan(values[6,6])
    assert np.nanmax(values)>99
    assert 0<meta['valid_fraction']<1
    wcs,n,scale=output_grid(133.7951291667,-7.2451472222,4)
    ra_right,_=wcs.pixel_to_world_values(n/2+1,n/2)
    ra_left,_=wcs.pixel_to_world_values(n/2-1,n/2)
    assert ra_right<ra_left  # east left, stable world grid


def test_documented_query():
    query=discovery_query(133,-7)
    assert 'spherex.artifact' in query and 'spherex.plane' in query
    assert "CONTAINS(POINT('ICRS', 133.0, -7.0), p.poly)" in query
    assert 'ORDER BY p.time_bounds_lower' in query


def test_job_pipeline_and_png(tmp_path,monkeypatch):
    """Synthetic fixture is test-only. Never served by the production application."""
    main.JOBS.clear();main.CLIENTS.clear()
    monkeypatch.setattr(main,'CACHE',tmp_path)
    monkeypatch.setattr(main,'prune_cache',lambda:None)
    rows=[dict(id=str(i),url='https://irsa.ipac.caltech.edu/example.fits',mjd=60000+i,date='2023-02-25T00:00:00Z',band='SPHEREx-D6',detector=6,release='qr3',observation=str(i)) for i in range(3)]
    monkeypatch.setattr(main,'discover',lambda ra,dec:rows)
    def fetch(row,ra,dec,fov):
        arr=np.ones((16,16),dtype=np.float32);arr[8,8]=10;arr[0,0]=np.nan
        np.save(tmp_path/(row['id']+'.npy'),arr)
        return row['id'],dict(valid_fraction=.99,unit='MJy/sr',width=16,height=16,wavelength_um=4.7)
    monkeypatch.setattr(main,'fetch_frame',fetch)
    client=TestClient(main.app)
    response=client.post('/api/search',json=dict(ra='133',dec='-7',fov=8))
    assert response.status_code==202
    job_id=response.json()['id']
    for _ in range(100):
        result=client.get('/api/jobs/'+job_id).json()
        if result['status']=='complete':break
        time.sleep(.01)
    assert result['ready']==3
    assert [f['mjd'] for f in result['frames']]==[60000,60001,60002]
    assert result['contrast']['reference_frame']==0
    for cmap in ['infrared','inferno','magma','viridis','gray']:
        for stretch in ['linear','sqrt','log','asinh']:
            r=client.get(f'/api/jobs/{job_id}/frames/0.png?cmap={cmap}&stretch={stretch}')
            assert r.status_code==200 and r.content.startswith(b'\x89PNG')
    from PIL import Image
    pixels=np.array(Image.open(io.BytesIO(r.content)))
    assert pixels[-1,0,3]==0  # missing pixel transparent; north-up rendered from lower origin
    assert client.get(f'/api/jobs/{job_id}/frames/0.png?black=5&white=1').status_code==422
    assert client.get(f'/api/jobs/{job_id}/frames/99.png').status_code==404
    assert client.post('/api/search',json=dict(ra='bad',dec='0')).status_code==422
    assert client.post('/api/search',json=dict(ra='0',dec='0',fov=100)).status_code==422
    main.JOBS.clear();main.CLIENTS.clear()


def test_archive_failure_is_explicit(monkeypatch):
    main.JOBS.clear();main.CLIENTS.clear()
    monkeypatch.setattr(main,'prune_cache',lambda:None)
    def fail(*args):raise ConnectionError('offline')
    monkeypatch.setattr(main,'discover',fail)
    client=TestClient(main.app)
    identity=client.post('/api/search',json=dict(ra='0',dec='0')).json()['id']
    for _ in range(100):
        result=client.get('/api/jobs/'+identity).json()
        if result['status']=='error':break
        time.sleep(.01)
    assert result['status']=='error' and result['frames']==[]
    assert 'No substitute images' in result['message']
    main.JOBS.clear();main.CLIENTS.clear()


def test_discovery_prefers_newest_release_and_caches(tmp_path,monkeypatch):
    import backend.archive as archive
    from astropy.table import Table
    table=Table(rows=[
        ('ibe/data/spherex/qr2/level2/level2_obs1D6_spx_v20.fits',60001.,'SPHEREx-D6'),
        ('ibe/data/spherex/qr3/level2/level2_obs1D6_spx_v25.fits',60001.,'SPHEREx-D6'),
        ('ibe/data/spherex/qr3/level2/level2_obs2D6_spx_v25.fits',60000.,'SPHEREx-D6')
    ],names=['uri','time_bounds_lower','energy_bandpassname'])
    calls=[]
    class Result:
        def to_table(self):return table
    class Service:
        def __init__(self,*args,**kwargs):pass
        def search(self,*args,**kwargs):calls.append(1);return Result()
    monkeypatch.setattr(archive,'CACHE',tmp_path)
    monkeypatch.setattr(archive,'throttle',lambda:None)
    monkeypatch.setattr(archive,'verify_service_schema',lambda session:None)
    monkeypatch.setattr(archive.pyvo.dal,'TAPService',Service)
    first=archive.discover(133,-7)
    second=archive.discover(133,-7)
    assert len(first)==2 and all(r['release']=='qr3' for r in first)
    assert [r['mjd'] for r in first]==[60000,60001]
    assert first==second and len(calls)==1


def test_simbad_input_mapping_and_missing_coordinates(tmp_path,monkeypatch):
    from astropy.table import Table, MaskedColumn
    names=[p['simbad'] for p in main.PRESETS if 'simbad' in p]
    table=Table({'user_specified_id':[n.ljust(30) for n in names],'ra':MaskedColumn([1.,2.,3.,4.],mask=[0,1,0,0]),'dec':[1.,2.,3.,4.]})
    class Catalog:
        def query_objects(self,query):assert query==names;return table
    monkeypatch.setattr(main,'CACHE',tmp_path)
    import backend.simbad_client as simbad_client
    monkeypatch.setattr(simbad_client,'query_names',lambda query:(Catalog().query_objects(query),'test-only-mirror'))
    result=main.presets()
    assert result[0]['ra']==1
    assert 'ra' not in result[1] and 'error' in result[1]
    assert result[2]['ra']==pytest.approx(133.7951291667)
    assert result[3]['ra']==3 and result[4]['ra']==4
