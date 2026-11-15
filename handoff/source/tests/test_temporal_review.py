import numpy as np
from backend.motion_tracks import fit_track,temporal_batches,reject_common_motion
from backend.laya_sequence import filter_decisions

def points(x):
    return [dict(frame=i,mjd=60000+i*30,x=float(v),y=10.,snr=20.) for i,v in enumerate(x)]

def test_coherent_independent_motion_survives_but_noise_and_stationary_do_not():
    fit=fit_track(points([10,10.5,11,11.5,12,12.5]))
    assert fit and fit['independent_epochs']==6 and fit['displacement_pixels']>2
    assert fit_track(points([10,10.05,9.98,10.04,10,10.02])) is None
    assert fit_track(points([10,12,10,12,9,12])) is None
    assert fit_track([dict(p,mjd=60000+i*.01) for i,p in enumerate(points(range(6)))]) is None

def test_all_frames_reviewed_with_endpoint_context_and_no_singleton_tail():
    group=list(range(25));batches=temporal_batches(group)
    assert set().union(*(set(b) for b in batches))==set(group)
    assert all(len(b)<=8 and len(b)>2 and b[0]==0 and b[-1]==24 for b in batches)
    assert temporal_batches([1])==[[1]]

def test_model_support_requires_track_overlap_not_just_same_group():
    result=dict(reviewed=10,total=10,batches=[dict(group='D1:40',frames=[1,2,3],choice='shifted position')],tracks=[dict(group='D1:40',points=[dict(frame=7),dict(frame=8)]),dict(group='D1:40',points=[dict(frame=1),dict(frame=2)])])
    r=filter_decisions(result)
    assert r['supported_motion_candidates']==1
    assert [t['model_supported'] for t in r['tracks']]==[False,True]

def test_field_wide_translation_is_not_labeled_isolated_source_motion():
    field=[dict(velocity_pixels_per_year=[2.+i*.01,1.],speed_error_pixels_per_year=.1) for i in range(8)]
    out,rejected=reject_common_motion(field+[dict(velocity_pixels_per_year=[-4,0],speed_error_pixels_per_year=.1)])
    assert rejected==8 and len(out)==1

def test_motion_track_rejects_local_wavelength_changes_even_in_same_frame_group():
    track=points([10,10.5,11,11.5,12,12.5])
    assert fit_track([dict(p,wavelength_um=1.02) for p in track])
    assert fit_track([dict(p,wavelength_um=1.02+i*.02) for i,p in enumerate(track)]) is None
