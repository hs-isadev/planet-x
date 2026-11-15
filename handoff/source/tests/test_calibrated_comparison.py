"""Controlled source fits use synthetic data only inside this test module."""
import numpy as np

from backend.calibrated_comparison import assess_matched_pair, reproject


def field(dx=0.,dy=0.,target_x=0.,target_amplitude=4.,width=1.):
    yy,xx = np.mgrid[:65,:65]
    image = np.full(xx.shape,.2)
    positions = [(14,18),(30,12),(49,15),(12,38),(52,34),(48,50),(22,50)]
    for x,y in positions:
        image += 4/width**2*np.exp(-((xx-x-dx)**2+(yy-y-dy)**2)/(2*width**2))
    image += target_amplitude/width**2*np.exp(-((xx-32-dx-target_x)**2+(yy-32-dy)**2)/(2*width**2))
    return dict(value=image,error=np.full(image.shape,.03),good=np.ones(image.shape,bool),
                low=np.full(image.shape,3.45),high=np.full(image.shape,3.55),
                width=np.full(image.shape,.10))


def compare(a,b):
    return assess_matched_pair(a,b,(32.,32.),dict(status='unassessed',checks={}),scale=6.15,grid_size=65)


def test_source_motion_after_independent_registration():
    result = compare(field(),field(dx=.25,dy=-.23,target_x=.75))
    assert result['status']=='measured'
    assert result['checks']['held_out_stars']>=2
    assert np.allclose(result['displacement_arcsec'],[-.75*6.15,0],atol=.15)
    assert np.all(np.asarray(result['component_error_arcsec'])>=.1*6.15)


def test_brightness_change_does_not_shift_source():
    result = compare(field(),field(dx=.25,dy=-.23,target_amplitude=2.))
    assert result['status']=='measured'
    assert np.linalg.norm(result['displacement_arcsec'])<.15


def test_psf_and_wavelength_failures_abstain():
    a = field()
    result = compare(a,field(width=1.35))
    assert result['status']=='unassessed'
    assert result['checks']['held_out_psf_fraction']>.20
    b = field()
    b['low'] += .045
    b['high'] += .045
    assert not compare(a,b)['checks']['source_band_overlap']


def test_interpolation_retains_error_bound_and_invalid_mask():
    a = field()
    a['good'][0,0] = False
    result = reproject(a,np.array([[.5,1.5]]),np.array([[.5,.5]]))
    assert result['good'].tolist()==[[False,True]]
    assert np.isclose(result['error'][0,1],.03)
