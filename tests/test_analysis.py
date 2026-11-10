import io
import numpy as np
import pytest
from astropy.io import fits
from astropy.coordinates import SkyCoord
from fastapi.testclient import TestClient
from backend.analysis import aligned_products,group_frames,stack_products,combine_images,pixel_solid_angles,aperture_measure,motion_fit,output_grid
from backend.cloud import validate_prefix
import backend.main as main


def native_fixture():
    wcs,n,scale=output_grid(133,-7,4)
    data=np.full((n,n),10.,dtype='f4');data[n//2,n//2]+=10
    flags=np.zeros_like(data,dtype='u4');flags[n//2,n//2]=1<<21
    yy,xx=np.mgrid[:n,:n]
    return fits.HDUList([fits.PrimaryHDU(),fits.ImageHDU(data,header=wcs.to_header(),name='IMAGE'),fits.ImageHDU(flags,name='FLAGS'),fits.ImageHDU(np.full_like(data,4),name='VARIANCE'),fits.ImageHDU(1.+.001*xx,name='WAVELENGTH')])


def test_variance_weighted_stack_and_missing_pixels():
    p1=dict(value=np.array([[2.,np.nan],[2.,np.nan]]),variance=np.array([[1.,np.nan],[1.,np.nan]]))
    p2=dict(value=np.array([[10.,6.],[np.nan,np.nan]]),variance=np.array([[4.,4.],[np.nan,np.nan]]))
    stack=stack_products([p1,p2])
    assert stack['value'][0,0]==pytest.approx(3.6)
    assert stack['variance'][0,0]==pytest.approx(.8)
    assert stack['value'][0,1]==6
    assert np.isnan(stack['value'][1,1])
    assert stack['count'].tolist()==[[2,1],[1,0]]


def test_registered_variance_and_wavelength_survive_mask():
    hdus=native_fixture();hdus['FLAGS'].data[10,10]=1
    p=aligned_products(hdus,133,-7,4)
    assert np.isnan(p['value'][10,10])
    assert np.isfinite(p['wavelength'][10,10])  # wavelength geometry is independent of pixel quality
    assert p['variance'][20,20]==pytest.approx(4,rel=1e-5)


def test_grouping_never_mixes_detector_or_unknown_wavelength():
    frames=[dict(index=i,status='ready',detector=d,band=f'D{d}',wavelength_um=w) for i,(d,w) in enumerate([(1,1.01),(1,1.02),(2,1.01),(1,None)])]
    groups=group_frames(frames)
    assert sorted(len(g['frames']) for g in groups)==[1,1,2]
    assert not next(g for g in groups if g['wavelength_min_um'] is None)['stackable']


def test_signed_difference_propagates_missingness():
    a=np.array([[2.,np.nan]]);b=np.array([[5.,3.]])
    result=combine_images(a,b,'subtract')
    assert result[0,0]==-3 and np.isnan(result[0,1])
    with pytest.raises(ValueError):combine_images(a,b,'multiply')


def test_native_aperture_flux_and_per_pixel_wavelength():
    hdus=native_fixture();wcs=__import__('astropy.wcs',fromlist=['WCS']).WCS(hdus['IMAGE'].header)
    n=hdus['IMAGE'].shape[0];pos=wcs.pixel_to_world(n//2,n//2)
    result=aperture_measure(hdus,pos,18.45)
    area=pixel_solid_angles(wcs,hdus['IMAGE'].shape)
    assert result['status']=='ok'
    assert result['background_mjy_sr']==pytest.approx(10)
    assert result['flux_ujy']==pytest.approx(10*area[n//2,n//2]*1e12,rel=1e-6)
    assert result['error_ujy']>0
    assert result['wavelength_um']==pytest.approx(1+.001*(n//2),rel=1e-4)
    hdus['FLAGS'].data[n//2,n//2]=1
    assert aperture_measure(hdus,pos,18.45)['status']=='missing'


def test_manual_track_has_expected_angular_speed():
    job=dict(ra=359.999,dec=20.,fov=8,frames=[dict(status='ready',mjd=60000,detector=6),dict(status='ready',mjd=60365.25,detector=6)])
    result=motion_fit(job,[dict(frame=0,x=.5,y=.5),dict(frame=1,x=.55,y=.5)])
    assert result['motion_arcsec_per_year']==pytest.approx(24,abs=.005)
    assert result['east_arcsec_per_year']<0
    assert result['provenance']=='computed'
    job['frames'][1]['mjd']=60000.001
    with pytest.raises(ValueError,match='one day'):motion_fit(job,[dict(frame=0,x=.5,y=.5),dict(frame=1,x=.55,y=.5)])

@pytest.mark.parametrize('prefix',['../qr3/level2/','qr3/../../secret','https://evil/','qr3/dark/','qr9/level2/'])
def test_archive_path_validation(prefix):
    with pytest.raises(ValueError):validate_prefix(prefix)


def test_analysis_api_endpoints(tmp_path,monkeypatch):
    import backend.analysis as analysis
    import backend.routes_analysis as routes
    monkeypatch.setattr(analysis,'CACHE',tmp_path);monkeypatch.setattr(routes,'CACHE',tmp_path)
    hdus=native_fixture();products=aligned_products(hdus,133,-7,4)
    frames=[]
    for i in range(2):
        identity=str(i);np.savez_compressed(tmp_path/(identity+'.npz'),**products);hdus.writeto(tmp_path/(identity+'.fits'))
        frames.append(dict(id=identity,index=i,cache_id=identity,status='ready',mjd=60000+i*365.25,detector=1,band='SPHEREx-D1',wavelength_um=1.02))
    main.JOBS['analysis-test']=dict(id='analysis-test',ra=133.,dec=-7.,fov=4,frames=frames,status='complete')
    client=TestClient(main.app)
    groups=client.get('/api/jobs/analysis-test/groups').json()['groups']
    result=client.get('/api/jobs/analysis-test/computed',params=dict(mode='stack',group=groups[0]['id']))
    assert result.status_code==200 and result.json()['provenance']=='computed'
    assert result.json()['image'].startswith('data:image/png;base64,')
    result=client.get('/api/jobs/analysis-test/computed',params=dict(mode='subtract',a=0,b=1))
    assert result.status_code==200 and result.json()['display']['black']<0
    assert client.post('/api/jobs/analysis-test/track',json=dict(points=[dict(frame=0,x=.5,y=.5),dict(frame=1,x=.55,y=.5)])).status_code==200
    bad=client.post('/api/jobs/analysis-test/track',json=dict(points=[dict(frame=0,frame_id='wrong',x=.5,y=.5),dict(frame=1,x=.55,y=.5)]))
    assert bad.status_code==422
    spec=client.get('/api/jobs/analysis-test/spectrum',params=dict(x=.5,y=.5)).json()
    assert spec['provenance']=='computed' and len(spec['points'])==2
    assert all(p['status']=='ok' for p in spec['points'])
    del main.JOBS['analysis-test']
