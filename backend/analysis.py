"""Computed quicklook analysis of observed SPHEREx data. Never source detection."""
import io
import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from scipy.stats import linregress
from .archive import CONFIG, CACHE, output_grid, ensure_frame_files


def wavelength_map(hdus, xx=None, yy=None):
    image=hdus['IMAGE']
    if xx is None: yy,xx=np.mgrid[:image.shape[0],:image.shape[1]]
    if 'WAVELENGTH' in hdus:
        # Cloud cutout materialized from the original per-pixel WCS-WAVE.
        from scipy.ndimage import map_coordinates
        return map_coordinates(hdus['WAVELENGTH'].data.astype(float),[yy,xx],order=1,mode='constant',cval=np.nan,prefilter=False)
    try:
        spectral=WCS(image.header,fobj=hdus,key='W');spectral.sip=None
        wave,_=spectral.pixel_to_world(xx,yy)
        return np.asarray(wave.to_value(u.um),dtype=float)
    except (ValueError,KeyError,TypeError,AttributeError):
        return np.full(np.shape(xx),np.nan)


def aligned_products(hdus,ra,dec,fov):
    data=hdus['IMAGE'].data.astype(float)
    variance=hdus['VARIANCE'].data.astype(float)
    flags=hdus['FLAGS'].data.astype(np.uint32)
    good=np.isfinite(data)&np.isfinite(variance)&(variance>0)&np.isin(flags,CONFIG['accepted_pixel_flags'])
    out,n,_=output_grid(ra,dec,fov);yy,xx=np.mgrid[:n,:n]
    lon,lat=out.pixel_to_world_values(xx,yy)
    source=WCS(hdus['IMAGE'].header).celestial;sx,sy=source.world_to_pixel_values(lon,lat)
    sx=np.nan_to_num(sx,nan=-10000);sy=np.nan_to_num(sy,nan=-10000)
    x0=np.floor(sx).astype(int);y0=np.floor(sy).astype(int)
    dx=sx-x0;dy=sy-y0
    value=np.zeros((n,n));var=np.zeros((n,n));coverage=np.zeros((n,n));wave=np.zeros((n,n));wave_valid=np.ones((n,n),bool)
    native_wave=wavelength_map(hdus)
    for ox,oy,w in [(0,0,(1-dx)*(1-dy)),(1,0,dx*(1-dy)),(0,1,(1-dx)*dy),(1,1,dx*dy)]:
        x=x0+ox;y=y0+oy;inside=(x>=0)&(x<data.shape[1])&(y>=0)&(y<data.shape[0])
        xc=np.clip(x,0,data.shape[1]-1);yc=np.clip(y,0,data.shape[0]-1)
        ok=inside&good[yc,xc]
        coverage+=w*ok
        value+=w*np.where(ok,data[yc,xc],0)
        var+=w*w*np.where(ok,variance[yc,xc],0)  # independent native samples; correct bilinear variance
        nw=native_wave[yc,xc];wave+=w*np.nan_to_num(nw);wave_valid&=(w<1e-8)|(inside&np.isfinite(nw))
    accepted=coverage>=.999999
    value[~accepted]=np.nan;var[~accepted]=np.nan;wave[~wave_valid]=np.nan
    return dict(value=value.astype('f4'),variance=var.astype('f4'),wavelength=wave.astype('f4'))


def group_frames(frames,width=.025):
    groups={}
    for f in frames:
        if f.get('status')!='ready':continue
        wave=f.get('wavelength_um');det=f.get('detector')
        bucket=int(np.floor(wave/width)) if wave is not None else None
        key=f'D{det}:'+str(bucket) if bucket is not None else f'D{det}:unknown'
        group=groups.setdefault(key,dict(id=key,detector=det,band=f.get('band'),wavelength_min_um=round(bucket*width,6) if bucket is not None else None,wavelength_max_um=round((bucket+1)*width,6) if bucket is not None else None,frames=[],stackable=bucket is not None))
        group['frames'].append(f['index'])
    return sorted(groups.values(),key=lambda g:(g['detector'] or 0,g['wavelength_min_um'] or 0))


def load_products(frame):
    file=CACHE/(frame['cache_id']+'.npz')
    if not file.exists():
        if frame.get('ra') is None:raise ValueError('Analysis products are missing. Reload this field to rebuild them.')
        ensure_frame_files(frame,analysis=True)
        file=CACHE/(frame['cache_id']+'.npz')
    with np.load(file,allow_pickle=False) as p:return {name:p[name].copy() for name in p.files}


def stack_products(products):
    values=np.stack([p['value'] for p in products]);variances=np.stack([p['variance'] for p in products])
    good=np.isfinite(values)&np.isfinite(variances)&(variances>0)
    weights=np.divide(1.,variances,out=np.zeros_like(variances,dtype=float),where=good)
    total=weights.sum(axis=0);count=good.sum(axis=0)
    mean=np.divide((np.where(good,values,0)*weights).sum(axis=0),total,out=np.full(total.shape,np.nan),where=total>0)
    variance=np.divide(1.,total,out=np.full(total.shape,np.nan),where=total>0)
    # No missing pixel is fabricated; a valid sample from another real exposure can fill coverage.
    return dict(value=mean,variance=variance,count=count)


def combine_images(a,b,mode):
    if a.shape!=b.shape:raise ValueError('Images must share the same sky grid.')
    if mode not in ('subtract','add'):raise ValueError('Choose add or subtract.')
    return a-b if mode=='subtract' else a+b


def render_computed(values,diverging=False):
    from matplotlib import colormaps
    from PIL import Image
    valid=np.isfinite(values)
    if not valid.any():raise ValueError('No shared usable pixels in this result.')
    if diverging:
        limit=float(np.nanpercentile(np.abs(values),99.5)) or 1
        lo,hi=-limit,limit;norm=np.clip((values-lo)/(hi-lo),0,1);cmap='coolwarm'
    else:
        lo,hi=np.nanpercentile(values,[1,99.7]);hi=max(hi,lo+1e-8)
        norm=np.arcsinh(10*np.clip((values-lo)/(hi-lo),0,1))/np.arcsinh(10);cmap='inferno'
    rgba=(colormaps[cmap](np.nan_to_num(norm))*255).astype('u1');rgba[...,3]=valid.astype('u1')*255
    buffer=io.BytesIO();Image.fromarray(np.flipud(rgba)).save(buffer,format='PNG')
    return buffer.getvalue(),dict(black=float(lo),white=float(hi),unit='MJy/sr',colormap=cmap,stretch='linear' if diverging else 'asinh')


def sky_at_click(job,x,y):
    wcs,n,scale=output_grid(job['ra'],job['dec'],job['fov'])
    # UI fractions run left→right, top→bottom. Pixel centers use the half-pixel convention.
    xp=x*n-.5;yp=(1-y)*n-.5
    return wcs.pixel_to_world(xp,yp)


def motion_fit(job,points):
    if len(points)<2:raise ValueError('Mark the same source in at least two different epochs.')
    unique={p['frame']:p for p in points}
    if len(unique)<2:raise ValueError('Use at least two different frames.')
    points=list(unique.values());frames=[job['frames'][p['frame']] for p in points]
    if any(f['status']!='ready' for f in frames):raise ValueError('Tracking requires available frames.')
    if len({f.get('detector') for f in frames})!=1:raise ValueError('Track within one detector to reduce wavelength-dependent confusion.')
    times=np.array([f['mjd'] for f in frames]);years=(times-times.min())/365.25
    if np.ptp(years)<1/365.25:raise ValueError('Need epochs separated by at least one day.')
    skies=SkyCoord([sky_at_click(job,p['x'],p['y']) for p in points])
    origin=skies[0];east,north=origin.spherical_offsets_to(skies)
    ex=east.arcsec;ny=north.arcsec;rx=linregress(years,ex);ry=linregress(years,ny)
    speed=float(np.hypot(rx.slope,ry.slope));_,_,scale=output_grid(job['ra'],job['dec'],job['fov'])
    # Nominal one-display-pixel mark error, not measured centroid/astrometric uncertainty.
    nominal=float(scale/np.sqrt(np.sum((years-years.mean())**2)))
    return dict(provenance='computed',method='Unweighted linear fit to manual marks in a tangent frame',motion_arcsec_per_year=speed,east_arcsec_per_year=float(rx.slope),north_arcsec_per_year=float(ry.slope),baseline_days=float(np.ptp(times)),nominal_component_error_arcsec_per_year=nominal,points=[dict(p,ra=float(s.ra.deg),dec=float(s.dec.deg),mjd=f['mjd']) for p,s,f in zip(points,skies,frames)],notes=['Manual marks are not source identification or a validated proper-motion solution.','Nominal error assumes one display-pixel marking error; it omits systematics, parallax, PSF and wavelength effects.'])


def pixel_solid_angles(wcs,shape):
    yy,xx=np.mgrid[:shape[0],:shape[1]]
    vectors=[]
    for dx,dy in [(-.5,-.5),(.5,-.5),(.5,.5),(-.5,.5)]:
        lon,lat=wcs.pixel_to_world_values(xx+dx,yy+dy);a=np.deg2rad(lon);d=np.deg2rad(lat)
        vectors.append(np.stack([np.cos(d)*np.cos(a),np.cos(d)*np.sin(a),np.sin(d)],axis=-1))
    def triangle(a,b,c):
        num=np.abs(np.sum(a*np.cross(b,c),axis=-1));den=1+(a*b).sum(-1)+(b*c).sum(-1)+(c*a).sum(-1)
        return 2*np.arctan2(num,den)
    a,b,c,d=vectors
    return triangle(a,b,c)+triangle(a,c,d)


def aperture_measure(hdus,position,radius_arcsec):
    data=hdus['IMAGE'].data.astype(float);variance=hdus['VARIANCE'].data.astype(float);flags=hdus['FLAGS'].data.astype(np.uint32)
    wcs=WCS(hdus['IMAGE'].header).celestial;yy,xx=np.mgrid[:data.shape[0],:data.shape[1]]
    sky=wcs.pixel_to_world(xx,yy);sep=sky.separation(position).arcsec
    aperture=sep<=radius_arcsec;annulus=(sep>=radius_arcsec*1.8)&(sep<=radius_arcsec*2.8)
    good=np.isfinite(data)&np.isfinite(variance)&(variance>0)&np.isin(flags,CONFIG['accepted_pixel_flags'])
    if not aperture.any():return dict(status='missing',reason='Aperture does not intersect this exposure.')
    coverage=float((good&aperture).sum()/aperture.sum())
    background_good=good&((flags & (1 << 21))==0)
    if coverage<1 or np.any(aperture[[0,-1],:]) or np.any(aperture[:,[0,-1]]) or (annulus&background_good).sum()<20:
        return dict(status='missing',reason='Aperture is masked, clipped, or lacks a usable background annulus.',valid_fraction=coverage)
    unit=u.Unit(hdus['IMAGE'].header.get('BUNIT','MJy/sr'));factor=(1*unit).to_value(u.MJy/u.sr)
    data*=factor;variance*=factor*factor
    area=pixel_solid_angles(wcs,data.shape)*1e12  # MJy/sr × sr → microJy
    background=float(np.median(data[annulus&background_good]))
    background_sigma=1.4826*np.median(np.abs(data[annulus&background_good]-background))
    bkgvar=np.pi/2*background_sigma**2/(annulus&background_good).sum()
    flux=float(np.sum((data[aperture]-background)*area[aperture]))
    error=float(np.sqrt(np.sum(variance[aperture]*area[aperture]**2)+bkgvar*np.sum(area[aperture])**2))
    wave=wavelength_map(hdus);known=aperture&np.isfinite(wave)
    if known.sum()!=aperture.sum():return dict(status='missing',reason='Per-pixel wavelength is unavailable.',valid_fraction=coverage)
    wavelength=float(np.average(wave[known],weights=area[known]))
    return dict(status='ok',flux_ujy=flux,error_ujy=error,wavelength_um=wavelength,wavelength_min_um=float(wave[known].min()),wavelength_max_um=float(wave[known].max()),valid_fraction=coverage,aperture_pixels=int(aperture.sum()),aperture_flags=[int(v) for v in np.unique(flags[aperture])],background_mjy_sr=background)
