"""Bounded, source-centered comparison using released IRSA calibrations."""
from pathlib import Path
from threading import BoundedSemaphore, Lock
from time import monotonic
from uuid import uuid4

import numpy as np
import requests
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import correlate, maximum_filter, map_coordinates
from scipy.optimize import least_squares

from .archive import CACHE, CONFIG, output_grid, same_calibration_release

WAVE_VERSION = {"qr2": "cal-wcs-v4-2025-254", "qr3": "cal-swcs-v5-2026-191", "dr1": "cal-swcs-v5-2026-191"}
CALIBRATION_LOCK = Lock()
COMPARISON_SLOTS = BoundedSemaphore(2)


def calibration_key(release, detector, kind):
    if release not in WAVE_VERSION or detector not in range(1, 7):
        raise ValueError("Calibration is unavailable for this detector or release.")
    if kind == "spectral_wcs":
        version = WAVE_VERSION[release]
    elif kind == "epsf":
        if release == "qr2":
            release = "qr3"
        version = "cal-epsf-v2-2026-191" if detector == 3 else "cal-epsf-v1-2026-191"
    else:
        raise ValueError("Unknown calibration product.")
    return f"{release}/{kind}/{version}/{detector}/{kind}_D{detector}_spx_{version}.fits"


def calibration_file(key):
    directory = CACHE / "calibration"
    directory.mkdir(exist_ok=True)
    path = directory / Path(key).name
    url = CONFIG["cloud_origin"].rstrip("/") + "/" + key
    if path.is_file():
        return path, url
    if not CALIBRATION_LOCK.acquire(timeout=2):
        raise ValueError("A calibration file is downloading. Retry shortly.")
    temporary = directory / (path.name + "." + uuid4().hex + ".part")
    try:
        if path.is_file():
            return path, url
        start = monotonic()
        with requests.get(url, stream=True, timeout=(5, 8)) as response:
            response.raise_for_status()
            size = 0
            with temporary.open("wb") as out:
                for block in response.iter_content(256 * 1024):
                    size += len(block)
                    if size > 40_000_000 or monotonic() - start > 20:
                        raise ValueError("Calibration download exceeded the size or time limit.")
                    out.write(block)
        with fits.open(temporary, memmap=False) as hdus:
            hdus.verify("exception")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
        CALIBRATION_LOCK.release()
    return path, url


def detector_offsets(header):
    if header.get("DETCOORD") != "sky":
        raise ValueError("The cutout detector orientation cannot be verified.")
    offsets = 1 - np.array([header["CRPIX1A"], header["CRPIX2A"]], dtype=float)
    if not np.isfinite(offsets).all() or not np.allclose(offsets, np.round(offsets), atol=1e-6):
        raise ValueError("Original detector pixel offsets are unavailable.")
    return offsets


def native_wavelengths(hdus, wave, band):
    offsets = detector_offsets(hdus["IMAGE"].header)
    x0,y0 = map(int,np.round(offsets))
    shape = hdus["IMAGE"].shape
    iy,ix = np.indices(shape)
    ix += x0
    iy += y0
    inside = (ix >= 0) & (iy >= 0) & (ix < wave.shape[1]) & (iy < wave.shape[0])
    center = np.full(shape,np.nan)
    width = center.copy()
    center[inside] = wave[iy[inside],ix[inside]]
    width[inside] = band[iy[inside],ix[inside]]
    return center,width


def cached_aperture_calibration(hdus, frame):
    """Use locally available released calibration without starting a download."""
    try:
        key = calibration_key(frame.get("release"), frame.get("detector"), "spectral_wcs")
        path = CACHE / "calibration" / Path(key).name
        if not path.is_file() or int(hdus["IMAGE"].header["DETECTOR"]) != frame["detector"]:
            return None, None
        with fits.open(path) as ch:
            wave,band = ch["CWAVE"].data,ch["CBAND"].data
            if wave.shape != (2040,2040) or band.shape != wave.shape:
                return None, None
            return native_wavelengths(hdus,wave,band), CONFIG["cloud_origin"].rstrip("/") + "/" + key
    except (OSError, KeyError, ValueError):
        return None, None


def native_inputs(hdus, wave, band):
    header = hdus["IMAGE"].header
    offsets = detector_offsets(header)
    a = hdus["IMAGE"].data.astype(float)
    v = hdus["VARIANCE"].data.astype(float)
    zodi = hdus["ZODI"].data.astype(float)
    flags = hdus["FLAGS"].data
    if str(header.get("BUNIT", "")).replace(" ", "") != "MJy/sr":
        raise ValueError("Brightness units do not match the comparison calibration.")
    wc,bw = native_wavelengths(hdus,wave,band)
    good = (np.isfinite(a) & np.isfinite(v) & (v > 0) & np.isfinite(zodi)
            & np.isfinite(wc) & (wc > 0) & np.isfinite(bw) & (bw > 0)
            & np.isin(flags, CONFIG["accepted_pixel_flags"]))
    return dict(value=a-zodi, error=np.sqrt(np.maximum(0, v)), low=wc-bw/2,
                high=wc+bw/2, width=bw, good=good), WCS(header).celestial, offsets


def reproject(product, x, y):
    """Bilinear values, worst-case correlated errors, intersected passbands."""
    finite = np.isfinite(x) & np.isfinite(y)
    x = np.where(finite, x, -2.)
    y = np.where(finite, y, -2.)
    xi, yi = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x-xi, y-yi
    h, w = product["value"].shape
    out = dict(value=np.zeros(x.shape), error=np.zeros(x.shape), width=np.zeros(x.shape),
               low=np.full(x.shape, -np.inf), high=np.full(x.shape, np.inf), good=finite.copy())
    for dx, dy, weight in ((0,0,(1-fx)*(1-fy)), (1,0,fx*(1-fy)), (0,1,(1-fx)*fy), (1,1,fx*fy)):
        px, py = xi+dx, yi+dy
        idx = (np.clip(py,0,h-1), np.clip(px,0,w-1))
        use = weight > 1e-8
        ok = use & (px>=0) & (px<w) & (py>=0) & (py<h) & product["good"][idx]
        out["good"] &= ~use | ok
        for name in ("value", "error"):
            out[name] += weight*np.where(ok,product[name][idx],0)
        out["low"] = np.maximum(out["low"], np.where(ok,product["low"][idx],-np.inf))
        out["high"] = np.minimum(out["high"], np.where(ok,product["high"][idx],np.inf))
        out["width"] = np.maximum(out["width"],np.where(ok,product["width"][idx],0))
    return out


def sky_kernel(table, source, offsets, grid, x, y):
    # The ePSF table uses detector sky-oriented, zero-based pixel coordinates.
    ref_x, ref_y = source.world_to_pixel(grid.pixel_to_world(x,y))
    distance = np.hypot(table["XCENTER"]-ref_x-offsets[0], table["YCENTER"]-ref_y-offsets[1])
    zone = int(np.argmin(distance))
    row = table[zone]
    if distance[zone] > np.hypot(row["XWIDTH"],row["YWIDTH"])/2 or row["NSTAR"] < 3:
        raise ValueError("No sampled ePSF zone covers the selected source.")
    model = np.asarray(row["EPSF"], dtype=float).reshape(33,33)
    if not np.isfinite(model).all() or np.max(model) <= 0:
        raise ValueError("The released ePSF zone is invalid.")
    yy, xx = np.mgrid[-4:5,-4:5]
    sx,sy = source.world_to_pixel(grid.pixel_to_world(x+xx,y+yy))
    kernel = map_coordinates(model, [16+5*(sy-ref_y),16+5*(sx-ref_x)], order=1, mode="constant", cval=0)
    # Very weak and negative wings are excluded from this local smoothing model.
    kernel = np.where(kernel > np.max(kernel)*.003,kernel,0.)
    if kernel.sum() <= 0 or np.count_nonzero(kernel) < 3:
        raise ValueError("The ePSF is undersampled on this comparison grid.")
    kernel /= kernel.sum()
    cx,cy = float(np.sum(xx*kernel)),float(np.sum(yy*kernel))
    return kernel, dict(zone=zone, stars=int(row["NSTAR"]), shift=[cx,cy])


def smooth(product, kernel):
    footprint = kernel > 0
    from scipy.ndimage import maximum_filter, minimum_filter
    good = correlate(product["good"].astype(float), footprint.astype(float), mode="constant", cval=0) == footprint.sum()
    return dict(
        value=correlate(np.where(product["good"],product["value"],0),kernel,mode="constant",cval=0),
        error=correlate(np.where(product["good"],product["error"],0),kernel,mode="constant",cval=0),
        low=maximum_filter(np.where(product["good"],product["low"],-np.inf),footprint=footprint,mode="constant",cval=-np.inf),
        high=minimum_filter(np.where(product["good"],product["high"],np.inf),footprint=footprint,mode="constant",cval=np.inf),
        width=maximum_filter(np.where(product["good"],product["width"],0),footprint=footprint,mode="constant",cval=0),
        good=good)


def common_band(a,b):
    known = a["good"] & b["good"] & (a["width"]>0) & (b["width"]>0)
    overlap = np.minimum(a["high"],b["high"])-np.maximum(a["low"],b["low"])
    return known & (overlap >= .80*np.maximum(a["width"],b["width"]))


def star_fit(p,x,y):
    """Local source fit, with an error bound that allows correlated samples."""
    ix, iy = int(round(x)), int(round(y))
    if ix<3 or iy<3 or ix+4>p["value"].shape[1] or iy+4>p["value"].shape[0]:
        return None
    window = np.s_[iy-3:iy+4, ix-3:ix+4]
    usable = p["good"][window]
    # Missing outer pixels carry zero weight. The core and enough of the halo must be observed.
    if usable.sum()<30 or not usable[2:5,2:5].all():
        return None
    z = p["value"][window][usable]
    err = p["error"][window][usable]
    yy,xx = np.mgrid[-3:4,-3:4]
    bg = float(np.median(z))
    amp = float(np.max(z)-bg)
    if amp < 8*float(np.median(err)):
        return None
    def residual(q):
        return (q[0]+q[1]*np.exp(-.5*((xx[usable]-q[2])**2/q[4]**2+(yy[usable]-q[3])**2/q[5]**2))-z)/err
    fit = least_squares(residual, [bg,amp,x-ix,y-iy,1,1],
                        bounds=([-np.inf,0,-1.5,-1.5,.45,.45],[np.inf,np.inf,1.5,1.5,2.4,2.4]),max_nfev=70)
    q = fit.x
    chi = float(np.mean(fit.fun**2))
    if not fit.success or chi>6 or np.any(np.abs(q[2:4])>1.4) or np.any(q[4:]>2.3):
        return None
    # L1 of each row bounds the local linear fit error under arbitrary correlation.
    uncertainty = np.sum(np.abs(np.linalg.pinv(fit.jac)[2:4]),axis=1)*max(1,np.sqrt(chi))
    return dict(position=np.array([ix+q[2],iy+q[3]]), error=uncertainty,
                shape=q[4:6], flux=float(q[1]*q[4]*q[5]))


def field_stars(a,b,x,y):
    good = common_band(a,b)
    image = np.where(good,a["value"],-np.inf)
    threshold = np.median(image[good]) if good.any() else np.inf
    peaks = good & (image == maximum_filter(image,size=7)) & (image > threshold+8*a["error"])
    yy,xx = np.nonzero(peaks)
    order = np.argsort(image[yy,xx])[::-1][:40]
    a,b = dict(a,good=good),dict(b,good=good)
    matches = []
    for k in order:
        px,py = xx[k],yy[k]
        if np.hypot(px-x,py-y)<9 or np.hypot(px-x,py-y)>28:
            continue
        sa,sb = star_fit(a,px,py),star_fit(b,px,py)
        if sa is None or sb is None or np.linalg.norm(sb["position"]-sa["position"])>1.3:
            continue
        ratio = sb["flux"]/sa["flux"]
        if .7 <= ratio <= 1.3:
            matches.append((sa,sb))
    return matches


def assess_matched_pair(aa, bb, center, evidence, *, scale, grid_size, grid_offset=(0,0), include_image=False):
    local_x,local_y = center
    left,bottom = grid_offset
    n = grid_size

    def unassessed(reason):
        return dict(evidence,reason=reason)

    good = common_band(aa,bb)
    nearest=(int(np.clip(round(local_y),0,good.shape[0]-1)),int(np.clip(round(local_x),0,good.shape[1]-1)))
    evidence["checks"].update(overlap_pixels=int(good.sum()),
                              source_band_overlap=bool(good[nearest]))
    if not good[nearest]:
        return unassessed("The source is masked or its calibrated passbands lack 80% overlap after matching.")
    matches = field_stars(aa,bb,local_x,local_y)
    evidence["checks"]["reference_stars"] = len(matches)
    if len(matches)<5:
        return unassessed("At least five nearby unmasked reference stars are needed to fit and independently check registration and PSF matching.")
    offsets = np.array([v["position"]-u["position"] for u,v in matches])
    # Interleave by rank so checks use different stars with comparable S/N.
    shift = np.median(offsets[::2],axis=0)
    holdout = offsets[1::2]-shift
    reg = float(np.max(np.linalg.norm(holdout,axis=1)))
    psf = float(max(np.max(np.abs(u["shape"]-v["shape"])/np.maximum(u["shape"],v["shape"]))
                    for u,v in matches[1::2]))
    evidence["checks"].update(held_out_stars=len(holdout), registration_shift_px=shift.tolist(),
                              held_out_registration_px=reg,held_out_psf_fraction=psf)
    if reg>.35 or psf>.20:
        return unassessed("Held-out stars failed the local registration or PSF check.")

    # Apply the measured reference-star translation before making a difference.
    by, bx = np.indices(aa["value"].shape,dtype=float)
    shifted = reproject(bb,bx+shift[0],by+shift[1])
    shared = common_band(aa,shifted)
    if shared.sum() < 49:
        return unassessed("Too few common calibrated pixels remain after registration.")
    raw_difference = shifted["value"]-aa["value"]
    background = float(np.median(raw_difference[shared]))
    scatter = float(1.4826*np.median(np.abs(raw_difference[shared]-background)))
    difference = np.where(shared,raw_difference-background,np.nan)
    evidence["checks"].update(registered_overlap_pixels=int(shared.sum()),
                              residual_background_mjysr=background,residual_mad_mjysr=scatter)
    if include_image:
        from base64 import b64encode
        from .analysis import render_computed
        png,display = render_computed(difference,diverging=True)
        evidence["difference"] = dict(image="data:image/png;base64,"+b64encode(png).decode(),
                                      display=display, grid_offset_px=[left,bottom],
                                      description="Later minus earlier after local ePSF matching, registration, ZODI and median residual background subtraction.")

    # Keep source fits inside the same valid spectral neighborhood.
    masked_a = dict(aa,good=good)
    masked_b = dict(bb,good=good)
    sa,sb = star_fit(masked_a,local_x,local_y),star_fit(masked_b,local_x+shift[0],local_y+shift[1])
    if sa is None or sb is None:
        return unassessed("The candidate has no reliable unmasked center in both observations.")
    delta = sb["position"]-sa["position"]-shift
    error = np.sqrt(sa["error"]**2+sb["error"]**2+max(.1,reg)**2)
    # The display grid runs east-left and north-up.
    evidence.update(status="measured", reason="Both source centers and the held-out field checks passed.",
                    displacement_arcsec=(delta*scale*np.array([-1,1])).tolist(),component_error_arcsec=(error*scale).tolist(),
                    significance=float(np.linalg.norm(delta/error)),
                    centers=[dict(x=float((u["position"][0]+left+.5)/n),y=float(1-(u["position"][1]+bottom+.5)/n))
                             for u in (sa,sb)])
    return evidence


def compare_pair(job, a, b, x, y, include_image=False):
    """Return measured evidence or an explicit unassessed result."""
    inputs = [dict(id=f["id"], frame=f["index"], date=f["date"], mjd=f["mjd"],
                   detector=f["detector"], url=f.get("url") or f.get("cutout_url")) for f in (a,b)]
    evidence = dict(status="unassessed", exposures=inputs, method="native CWAVE/CBAND, local released ePSFs and field-star checks",
                    calibration_sources=[], checks={},
                    limits=["Band overlap uses published central wavelengths and bandwidths as intervals.",
                            "Local ePSF resampling and reference-star fits approximate the image response.",
                            "Statistical errors do not cover every calibration systematic. Two dates alone leave source identity and motion uncertain."])
    def unassessed(reason):
        return dict(evidence,reason=reason)
    if not same_calibration_release(a["release"], b["release"]) or a["detector"] != b["detector"] or abs(a["mjd"]-b["mjd"])<1:
        return unassessed("Choose calibration-compatible exposures from the same detector on dates at least one day apart.")
    paths = [CACHE / (f["cache_id"]+".fits") for f in (a,b)]
    if not all(path.is_file() for path in paths):
        return unassessed("Native FITS was evicted for at least one exposure. Reopen that archive exposure to restore its original data.")
    if not COMPARISON_SLOTS.acquire(blocking=False):
        return unassessed("Two comparisons are already running. Try again shortly.")
    try:
        grid,n,scale = output_grid(job["ra"],job["dec"],job["fov"])
        px,py = x*n-.5,(1-y)*n-.5
        # Limit the comparison to the neighborhood where one ePSF zone is plausible.
        left,bottom = max(0,int(px)-32),max(0,int(py)-32)
        yy,xx = np.mgrid[bottom:min(n,bottom+65),left:min(n,left+65)]
        local_x,local_y = px-left,py-bottom
        world = grid.pixel_to_world(xx,yy)
        wave_path,wurl = calibration_file(calibration_key(a["release"],a["detector"],"spectral_wcs"))
        epsf_path,purl = calibration_file(calibration_key(a["release"],a["detector"],"epsf"))
        evidence["calibration_sources"] = [wurl,purl]
        products,kernels,zones = [],[],[]
        with fits.open(wave_path) as wh, fits.open(epsf_path) as ph:
            wave,band = wh["CWAVE"].data,wh["CBAND"].data
            if wave.shape != (2040,2040) or band.shape != wave.shape:
                raise ValueError("Unexpected released spectral calibration grid.")
            for path in paths:
                with fits.open(path,memmap=False) as h:
                    if int(h["IMAGE"].header["DETECTOR"]) != a["detector"]:
                        raise ValueError("The FITS detector differs from the archive record.")
                    product,source,offsets = native_inputs(h,wave,band)
                    kernel,zone = sky_kernel(ph["EPSF"].data,source,offsets,grid,px,py)
                    sx,sy = source.world_to_pixel(world)
                    products.append(reproject(product,sx,sy))
                    kernels.append(kernel)
                    zones.append(zone)
        # Match PSFs by cross-correlating each image with the other's reflected kernel.
        aa,bb = smooth(products[0],kernels[1][::-1,::-1]),smooth(products[1],kernels[0][::-1,::-1])
        evidence["checks"]["epsf_zones"] = zones
        return assess_matched_pair(aa,bb,(local_x,local_y),evidence,scale=scale,grid_size=n,
                                   grid_offset=(left,bottom),include_image=include_image)
    except (ValueError, KeyError, OSError, requests.RequestException) as exc:
        return unassessed(str(exc))
    finally:
        COMPARISON_SLOTS.release()
