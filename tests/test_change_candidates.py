import numpy as np
from backend.quicklook import change_masks
def product(source=False):
    a=np.zeros((17,17));v=np.ones_like(a)
    if source:a[8,8]=12;a[8,9]=7;a[9,8]=6
    return dict(value=a,variance=v)
def test_appearance_and_disappearance():
    on,off=product(True),product(False)
    forward=change_masks(on,off);reverse=change_masks(off,on)
    assert forward['appearance'].sum()>=2 and reverse['disappearance'].sum()>=2
    assert not forward['disappearance'].any() and not reverse['appearance'].any()
def test_masked_counterpart_is_unknown():
    on,off=product(True),product(False);off['value'][7:11,7:11]=np.nan
    assert not change_masks(off,on)['disappearance'].any()
    assert not change_masks(on,off)['appearance'].any()
def test_unchanged_source_is_not_red():
    a=product(True)
    assert not change_masks(a,a)['red'].any()

def test_pixel_wavelength_mismatch_is_not_a_change():
    on,off=product(True),product(False)
    on['wavelength']=np.full((17,17),2.0)
    off['wavelength']=np.full((17,17),2.1)
    assert not change_masks(on,off)['red'].any()
    off['wavelength'][:]=2.01
    assert change_masks(on,off)['appearance'].any()

def test_single_pixel_outlier_is_not_a_source():
    on,off=product(False),product(False)
    on['value'][8,8]=100
    assert not change_masks(on,off)['red'].any()
