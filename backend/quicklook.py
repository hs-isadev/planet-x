"""Explicitly computed noise-suppressed quicklooks. Original arrays remain unchanged."""
import numpy as np
from scipy.ndimage import median_filter,label
from .analysis import load_products

def standardized(product):
    a=np.asarray(product['value'],float);v=np.asarray(product['variance'],float)
    valid=np.isfinite(a)&np.isfinite(v)&(v>0)
    if valid.sum()<9:raise ValueError('Too few unmasked pixels for background estimation.')
    center=float(np.median(a[valid]));mad=float(1.4826*np.median(np.abs(a[valid]-center)))
    # Clip sources before estimating a smoothly varying local background. Filled mask values
    # contribute only to the background model; they are never displayed or used as observations.
    noise=max(mad,float(np.median(np.sqrt(v[valid]))),1e-9)
    filled=np.where(valid,np.clip(a,center-3*noise,center+3*noise),center)
    size=max(3,min(21,(min(a.shape)//3)|1));background=median_filter(filled,size=size,mode='nearest')
    residual=a-background
    rms=float(1.4826*np.median(np.abs(residual[valid]-np.median(residual[valid]))))
    variance=np.maximum(v,rms*rms)
    snr=np.divide(residual,np.sqrt(variance),out=np.full(a.shape,np.nan),where=valid)
    return residual,variance,snr,valid

def comparable(a,b):
    wa,wb=a.get('wavelength_um'),b.get('wavelength_um')
    return a.get('detector')==b.get('detector') and wa is not None and wb is not None and abs(wa-wb)<=.025 and abs(a['mjd']-b['mjd'])>=1

def enhanced_rgba(frame,reference=None):
    a,va,snr,valid=standardized(load_products(frame))
    # The same 2.5..12 signal-to-noise mapping is applied to every frame.
    intensity=np.arcsinh(3*np.clip((np.nan_to_num(snr)-2.5)/9.5,0,1))/np.arcsinh(3)
    rgba=np.zeros((*a.shape,4),np.uint8);rgba[...,:3]=(intensity[...,None]*232).astype('u1');rgba[...,3]=valid.astype('u1')*255
    if reference is not None:
        if not comparable(frame,reference):raise ValueError('Change overlay requires the same detector, wavelength within 0.025 µm, and dates at least one day apart.')
        keep=change_masks(load_products(frame),load_products(reference))['red']
        rgba[keep,0]=245;rgba[keep,1]=65;rgba[keep,2]=67
    return rgba

def change_masks(current,reference):
    """Residual + high-confidence appearance/disappearance quicklook candidates."""
    from scipy.ndimage import maximum_filter,binary_dilation
    a,va,sa,ma=standardized(current);b,vb,sb,mb=standardized(reference)
    good=ma&mb
    # LVF wavelengths vary across each exposure. Matching only the field-center
    # wavelength can paint real spectral differences red elsewhere in the image.
    if 'wavelength' in current and 'wavelength' in reference:
        wa=np.asarray(current['wavelength']);wb=np.asarray(reference['wavelength'])
        good &= np.isfinite(wa)&np.isfinite(wb)&(np.abs(wa-wb)<=.025)
    significance=np.divide(a-b,np.sqrt(va+vb),out=np.zeros(a.shape),where=good)
    # Require a source-like high-S/N peak, a faint counterpart and a significant
    # signed residual. Missing/flagged counterpart pixels never mean disappearance.
    appearing_seed=good&(sa>=5)&(sb<2)&(significance>=3.5)
    disappearing_seed=good&(sb>=5)&(sa<2)&(significance<=-3.5)
    appear=binary_dilation(appearing_seed)&good&(sa>=3)&(significance>=2.5)
    disappear=binary_dilation(disappearing_seed)&good&(sb>=3)&(significance<=-2.5)
    def islands(mask):
        regions,_=label(mask);counts=np.bincount(regions.ravel());counts[0]=0
        return mask&(counts[regions]>=2)
    appear=islands(appear);disappear=islands(disappear)
    residual=islands(good&(np.abs(significance)>=4)&((sa>=3)|(sb>=3)))
    return dict(appearance=appear,disappearance=disappear,residual=residual,red=appear|disappear|residual,comparable=good,significance=significance)
