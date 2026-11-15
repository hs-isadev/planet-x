import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from backend.time_science import target_for,prediction,projected

def test_native_centroid_fits_unmasked_wings_without_forcing_prediction(tmp_path):
    from astropy.io import fits
    from backend.archive import output_grid
    from backend.time_science import native_centroid
    job=dict(ra=133.,dec=-7.,fov=4)
    w,n,scale=output_grid(**job);yy,xx=np.mgrid[:n,:n];px,py=(n-1)/2,(n-1)/2
    truex,truey=px+.8,py-.6
    values=3.+.01*(xx-px)+80*np.exp(-.5*(((xx-truex)/1.3)**2+((yy-truey)/.9)**2))
    flags=np.zeros((n,n),dtype='u4');flags[(xx-truex)**2+(yy-truey)**2<2.5]=1
    path=tmp_path/'masked-test-fixture.fits'
    fits.HDUList([fits.PrimaryHDU(),fits.ImageHDU(values,header=w.to_header(),name='IMAGE'),fits.ImageHDU(np.ones_like(values),name='VARIANCE'),fits.ImageHDU(flags,name='FLAGS')]).writeto(path)
    fit=native_centroid(path,job,w.pixel_to_world(px,py));found=w.world_to_pixel(SkyCoord(fit['ra'],fit['dec'],unit='deg'))
    assert found[0]==pytest.approx(truex,abs=.03) and found[1]==pytest.approx(truey,abs=.03)
    assert fit['native_valid_pixels']>45 and fit['snr']>8

def test_catalog_prediction_preserves_expected_motion_and_projects_into_barnard_field():
    job=dict(ra=269.4520769586187,dec=4.693364966576667,fov=12)
    row=target_for(job)
    a=prediction(row,60902.864715,False)
    b=prediction(row,60902.864715+365.25,False)
    catalog=np.hypot(float(row['pmra']),float(row['pmdec']))/1000
    assert a.separation(b).arcsec==pytest.approx(catalog,rel=.001)
    point=projected(job,a)
    assert 0<point['x']<1 and 0<point['y']<1
    with_parallax=prediction(row,60902.864715)
    assert with_parallax.separation(a).arcsec<1
    assert np.isfinite(with_parallax.ra.deg+with_parallax.dec.deg)

def test_unrelated_coordinate_is_not_identified_as_a_preset():
    with pytest.raises(ValueError,match='not centered'):
        target_for(dict(ra=12,dec=-30,fov=8))
