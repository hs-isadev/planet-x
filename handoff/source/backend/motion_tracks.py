"""Conservative temporal consistency checks for registered-image peak tracks."""
import numpy as np

def fit_track(points):
    """Keep independent epochs; reject noise, stationary peaks and poor linear fits."""
    ordered=sorted(points,key=lambda p:p['mjd']);epochs={}
    if any('wavelength_um' in p for p in ordered):
        waves=[p.get('wavelength_um') for p in ordered]
        if any(w is None or not np.isfinite(w) for w in waves) or np.ptp(waves)>.025:return None
    for p in ordered:
        # Multiple detector reads in the same night are not independent evidence
        # for a month/year-scale displacement.
        day=int(p['mjd'])
        if day not in epochs or p['snr']>epochs[day]['snr']:epochs[day]=p
    pts=sorted(epochs.values(),key=lambda p:p['mjd'])
    if len(pts)<4 or pts[-1]['mjd']-pts[0]['mjd']<30:return None
    times=np.array([p['mjd'] for p in pts]);times=(times-times[0])/365.25
    xy=np.array([[p['x'],p['y']] for p in pts],dtype=float)
    errors=np.array([max(.18,1.5/max(p['snr'],1)) for p in pts])
    design=np.column_stack([np.ones(len(times)),times]);w=1/errors**2
    covariance=np.linalg.inv(design.T@(design*w[:,None]));coef=covariance@(design.T@(xy*w[:,None]));pred=design@coef
    residual=float(np.sqrt(np.mean(np.sum((xy-pred)**2,axis=1))))
    chi=float(np.sum(np.sum((xy-pred)**2,axis=1)*w)/max(1,2*len(pts)-4))
    velocity=coef[1];speed=float(np.linalg.norm(velocity));speed_error=float(np.sqrt(covariance[1,1])*np.sqrt(max(1,chi)))
    shift=speed*np.ptp(times)
    if shift<.8 or speed<5*speed_error or residual>.55 or chi>4:return None
    # A transient or a swapped association must not determine the result.
    for j in range(len(pts)):
        keep=np.arange(len(pts))!=j
        slope=np.linalg.lstsq(design[keep],xy[keep],rcond=None)[0][1]
        if np.linalg.norm(slope-velocity)>.4*speed:return None
    return dict(points=ordered,independent_epochs=len(pts),displacement_pixels=shift,
                residual_pixels=residual,reduced_chi2=chi,velocity_pixels_per_year=velocity.tolist(),
                speed_error_pixels_per_year=speed_error,baseline_days=float(np.ptp(times)*365.25))

def temporal_batches(group,size=8):
    """Every exposure plus both endpoint references; no single-frame tail."""
    if len(group)<=size:return [group]
    # Six new frames per contact sheet and fixed earliest/latest context.
    return [[group[0],*group[start:start+size-2],group[-1]] for start in range(1,len(group)-1,size-2)]

def reject_common_motion(tracks):
    """Flag coherent field translations separately from isolated source motion."""
    if len(tracks)<5:return tracks,0
    velocities=np.array([t['velocity_pixels_per_year'] for t in tracks])
    median=np.median(velocities,axis=0)
    distance=np.linalg.norm(velocities-median,axis=1)
    tolerance=np.array([max(.3,3*t['speed_error_pixels_per_year']) for t in tracks])
    common=distance<tolerance
    if common.sum()<max(5,len(tracks)*.6):return tracks,0
    return [t for t,remove in zip(tracks,common) if not remove],int(common.sum())
