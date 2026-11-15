"""Motion study: same-wavelength visit stacks, measured-versus-expected astrometry with field-star
checks, a rule-based verdict per target, and a WISE/NEOWISE + SPHEREx time-lapse at 4.6 µm.

Everything is computed from FITS files already in the bundle and written as static JSON + PNG under
web/assets/motion-study/<field>/, so the deployed site does no heavy work.

Run (from the project root):
    python -m backend.observation_lab_core.motion_study            # all study targets
    python -m backend.observation_lab_core.motion_study barnard    # one target
    python -m backend.observation_lab_core.motion_study vesta      # a tracked body (tiles from scripts/fetch_track.py)
    python -m backend.observation_lab_core.motion_study barnard --sky-only   # just add/refresh the tiled sky view

Method in brief
- Frames are grouped into visits (SPHEREx passes over a spot about every six months; a gap of more than
  20 days starts a new visit). WISE/NEOWISE frames are grouped the same way.
- Stacks: each frame is resampled onto one north-up 3″/px grid, its median sky removed, and the frames of a
  visit whose wavelength at the field centre falls in a narrow window are median-combined. Comparing only
  like wavelengths avoids SPHEREx's colour-by-position effect masquerading as motion.
- Astrometry: the target is fitted (2-D Gaussian) in every frame near its catalog-predicted place, in that
  frame's own pixels and WCS. Saturated targets are located from the centroid of their saturated core.
  Bright unsaturated field stars are measured the same way and matched across frames; each frame's median
  field-star offset is removed (relative astrometry), and the field stars themselves are then tested for
  spurious motion (a null test).
- Fit: east/north offsets versus time are fitted with a straight line plus the catalog parallax, per mission
  and combined; uncertainties are inflated by sqrt(reduced chi²) when the scatter exceeds the error bars.
- Verdict: one of six outcomes, each with the rule and numbers that produced it.
"""
import json
import math
import os
import pickle
import sys
import time
import warnings
from pathlib import Path

import numpy as np
from astropy.coordinates import get_body_barycentric
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS, FITSFixedWarning
from PIL import Image
from scipy.ndimage import gaussian_filter, label, map_coordinates, maximum_filter
from scipy.optimize import least_squares

warnings.simplefilter('ignore', FITSFixedWarning)
warnings.simplefilter('ignore', RuntimeWarning)

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / 'backend/data/spherex-seed'
SUPPLEMENTAL = ROOT / 'backend/data/supplemental-epochs'
OUT = ROOT / 'web/assets/motion-study'
GRID_SCALE = 3.0            # arcsec per display pixel
GRID_SIZE = 200             # 10 arcmin display field
VISIT_GAP_DAYS = 20
J2000 = 51544.5
SAT_BITS = (1 << 1) | (1 << 15)           # near saturation, nonlinear response
BAD_BITS = sum(1 << b for b in (2, 6, 7, 9, 10, 11, 17, 26, 27, 28, 29))
BANDS = [
    ('4.6', '4.6 µm · same as WISE W2', 4.6, .22),
    ('3.4', '3.4 µm · same as WISE W1', 3.4, .18),
    ('2.2', '2.2 µm · K band', 2.2, .12),
    ('1.25', '1.25 µm · J band', 1.25, .08),
]

# Catalog astrometry (ICRS, epoch J2000). The first three come from the bundled supplemental series files
# (SIMBAD). Proxima: Gaia DR3 via SIMBAD. RW Aur and R Dra have no bundled proper motion; both are distant
# (well over 100 pc), so their motion is a few mas/yr at most and is treated as negligible here.
TARGETS = {
    'barnard': dict(name='Barnard’s Star', kind='nearby red dwarf', expect='motion'),
    'epsilon-indi': dict(name='Epsilon Indi B', kind='nearby brown-dwarf pair', expect='motion'),
    'wise-0855': dict(name='WISE 0855−0714', kind='coldest known brown dwarf', expect='motion'),
    'proxima-centauri': dict(name='Proxima Centauri', kind='nearest star', expect='motion',
                             catalog=dict(ra=217.42895219, dec=-62.67948975, pmra_mas_yr=-3781.741,
                                          pmdec_mas_yr=769.465, parallax_mas=768.067,
                                          source='Gaia DR3 (via SIMBAD), epoch J2000')),
    'rw-aur': dict(name='RW Aurigae', kind='young variable star with a disk', expect='brightness',
                   catalog=dict(ra=76.956525, dec=30.4014389, pmra_mas_yr=0.0, pmdec_mas_yr=0.0,
                                parallax_mas=0.0, assumed=True,
                                source='Field position; proper motion assumed negligible (distant star)')),
    'r-dra': dict(name='R Draconis', kind='Mira variable (pulsating red giant)', expect='brightness',
                  catalog=dict(ra=248.1676125, dec=66.7549806, pmra_mas_yr=0.0, pmdec_mas_yr=0.0,
                               parallax_mas=0.0, assumed=True,
                               source='Field position; proper motion assumed negligible (distant star)')),
}


# ---------------------------------------------------------------------------------------------------------
# geometry

def display_grid(ra, dec):
    grid = WCS(naxis=2)
    grid.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    grid.wcs.crval = [ra, dec]
    grid.wcs.crpix = [(GRID_SIZE + 1) / 2] * 2
    grid.wcs.cdelt = [-GRID_SCALE / 3600, GRID_SCALE / 3600]
    return grid


def earth_xyz(mjd):
    p = get_body_barycentric('earth', Time(mjd, format='mjd', scale='tdb'))
    return np.array([p.x.to_value('AU'), p.y.to_value('AU'), p.z.to_value('AU')])


def expected(cat, mjd):
    """Catalog position at a date (linear proper motion + parallax as seen from Earth/SPHEREx)."""
    ra0, dec0 = math.radians(cat['ra']), math.radians(cat['dec'])
    years = (mjd - J2000) / 365.25
    east = cat['pmra_mas_yr'] * years / 1000.0
    north = cat['pmdec_mas_yr'] * years / 1000.0
    plx = cat.get('parallax_mas', 0.0) / 1000.0
    if plx:
        x, y, z = earth_xyz(mjd)
        east += plx * (x * math.sin(ra0) - y * math.cos(ra0))
        north += plx * (x * math.cos(ra0) * math.sin(dec0) + y * math.sin(ra0) * math.sin(dec0) - z * math.cos(dec0))
    dec = cat['dec'] + north / 3600.0
    ra = cat['ra'] + east / 3600.0 / math.cos(math.radians(dec))
    return ra, dec, east, north


def offsets(cat, ra, dec):
    """East/north offsets in arcsec of (ra, dec) from the catalog J2000 position."""
    east = (ra - cat['ra'] + 540) % 360 - 180
    return east * 3600.0 * math.cos(math.radians(cat['dec'])), (dec - cat['dec']) * 3600.0


def resample(data, wcs, grid, white=None):
    ys, xs = np.mgrid[0:GRID_SIZE, 0:GRID_SIZE]
    sky = grid.pixel_to_world_values(xs.ravel(), ys.ravel())
    px, py = wcs.world_to_pixel_values(*sky)
    good = np.isfinite(data)
    filled = np.where(good, data, 0.0)
    value = map_coordinates(filled, [py, px], order=1, mode='constant', cval=np.nan)
    weight = map_coordinates(good.astype(float), [py, px], order=1, mode='constant', cval=0.0)
    out = np.where(weight > .6, value / np.maximum(weight, 1e-6), np.nan)
    out = out.ravel()
    if white is not None and white.any():
        # Saturated cores are kept as +inf so they draw white rather than black.
        core = map_coordinates(white.astype(float), [py, px], order=0, mode='constant', cval=0.0) > .5
        out[core] = np.inf
    return out.reshape(GRID_SIZE, GRID_SIZE)


# ---------------------------------------------------------------------------------------------------------
# measurement

def robust_sigma(values):
    values = values[np.isfinite(values)]
    if values.size < 10:
        return np.nan
    return 1.4826 * np.median(np.abs(values - np.median(values)))


def gaussian_fit(img, var, x0, y0, half=3):
    """Fit amp·exp(-r²/2s²)+b on a (2·half+1)² window. Returns x, y, σx, σy, flux, snr or None."""
    h, w = img.shape
    ix, iy = int(round(x0)), int(round(y0))
    if ix - half < 0 or iy - half < 0 or ix + half >= w or iy + half >= h:
        return None
    sub = img[iy - half:iy + half + 1, ix - half:ix + half + 1]
    sv = var[iy - half:iy + half + 1, ix - half:ix + half + 1] if var is not None else None
    good = np.isfinite(sub)
    if sv is not None:
        good &= np.isfinite(sv) & (sv > 0)
    if good.sum() < 12:
        return None
    yy, xx = np.mgrid[iy - half:iy + half + 1, ix - half:ix + half + 1]
    bkg0 = np.nanmedian(sub[~(np.hypot(xx - x0, yy - y0) < 1.5)]) if np.isfinite(sub).sum() > 20 else np.nanmin(sub)
    amp0 = max(np.nanmax(sub) - bkg0, 1e-6)
    weights = 1 / np.sqrt(sv[good]) if sv is not None else np.ones(good.sum()) / max(robust_sigma(sub), 1e-6)

    def model(p):
        a, x, y, s, b = p
        return a * np.exp(-((xx[good] - x) ** 2 + (yy[good] - y) ** 2) / (2 * s * s)) + b

    try:
        res = least_squares(lambda p: (model(p) - sub[good]) * weights, [amp0, x0, y0, .9, bkg0],
                            bounds=([0, x0 - 2.5, y0 - 2.5, .45, -np.inf], [np.inf, x0 + 2.5, y0 + 2.5, 3.0, np.inf]))
    except ValueError:
        return None
    a, x, y, s, b = res.x
    try:
        cov = np.linalg.inv(res.jac.T @ res.jac) * max(1.0, 2 * res.cost / max(1, good.sum() - 5))
        ex, ey = math.sqrt(cov[1, 1]), math.sqrt(cov[2, 2])
    except np.linalg.LinAlgError:
        return None
    flux = a * 2 * math.pi * s * s
    noise = math.sqrt(np.nansum(sv[good])) if sv is not None else robust_sigma(sub) * math.sqrt(good.sum())
    snr = flux / noise if noise > 0 else 0.0
    if not all(map(math.isfinite, (x, y, ex, ey))):
        return None
    return dict(x=float(x), y=float(y), ex=float(ex), ey=float(ey), flux=float(flux), snr=float(snr), sigma=float(s))


def saturated_core(sat_mask, x0, y0, radius):
    """Centroid of the saturated core nearest (x0, y0), or None."""
    h, w = sat_mask.shape
    yy, xx = np.mgrid[0:h, 0:w]
    near = np.hypot(xx - x0, yy - y0) <= radius
    mask = near & sat_mask
    if mask.sum() < 2:
        return None
    labels, n = label(mask)
    best, size = None, 0
    for k in range(1, n + 1):
        s = (labels == k).sum()
        if s > size:
            best, size = k, s
    ys, xs = np.nonzero(labels == best)
    if size < 2:
        return None
    err = max(.25, .6 / math.sqrt(size))
    return dict(x=float(xs.mean()), y=float(ys.mean()), ex=err, ey=err, flux=np.nan, snr=np.nan, sigma=np.nan,
                saturated=True, core_pixels=int(size))


def wing_flux(img, sat_mask, x, y, unit):
    """Mean surface brightness in an annulus of 1.5-3.5 SPHEREx pixels around (x, y), ignoring saturated and bad
    pixels. For a fixed PSF the wings scale with total brightness, so this still tracks a saturated star."""
    h, w = img.shape
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(xx - x, yy - y) / unit
    ring = (r >= 1.5) & (r <= 3.5) & np.isfinite(img) & ~sat_mask
    if ring.sum() < 8:
        return None
    return float(np.mean(img[ring]))


def find_stars(img, flags, avoid_xy, avoid_r, max_stars=40):
    sigma = robust_sigma(img)
    if not np.isfinite(sigma) or sigma <= 0:
        return []
    sm = gaussian_filter(np.nan_to_num(img - np.nanmedian(img)), .8)
    peaks = (sm == maximum_filter(sm, size=5)) & (sm > 8 * sigma)
    ys, xs = np.nonzero(peaks)
    order = np.argsort(-sm[ys, xs])
    out = []
    for i in order[:max_stars * 3]:
        x, y = float(xs[i]), float(ys[i])
        if math.hypot(x - avoid_xy[0], y - avoid_xy[1]) < avoid_r:
            continue
        if x < 4 or y < 4 or x > img.shape[1] - 5 or y > img.shape[0] - 5:
            continue
        if flags is not None:
            win = flags[int(y) - 1:int(y) + 2, int(x) - 1:int(x) + 2]
            if (win & (SAT_BITS | BAD_BITS)).any():
                continue
        out.append((x, y))
        if len(out) >= max_stars:
            break
    return out


def measure_frame(path, cat, mjd, mission, grid, search_arcsec):
    """Target + field stars in one frame. Returns dict with sky positions (deg) and the display stack image."""
    with fits.open(path, memmap=False) as hdus:
        if mission == 'SPHEREx':
            img = hdus['IMAGE'].data.astype(float)
            var = hdus['VARIANCE'].data.astype(float)
            flags = hdus['FLAGS'].data.astype(np.int64)
            wcs = WCS(hdus['IMAGE'].header).celestial
            sat_mask = (flags & SAT_BITS) != 0
            img[((flags & BAD_BITS) != 0) & ~sat_mask] = np.nan
        else:
            img = hdus[0].data.astype(float)
            var, flags = None, None
            wcs = WCS(hdus[0].header).celestial
            sat_mask = ~np.isfinite(img)
    scale = abs(wcs.proj_plane_pixel_scales()[0].to_value('arcsec'))
    ra_p, dec_p, _, _ = expected(cat, mjd)
    x0, y0 = wcs.world_to_pixel_values(ra_p, dec_p)
    x0, y0 = float(x0), float(y0)
    sky_level = np.nanmedian(img)
    work = img - sky_level
    radius = search_arcsec / scale
    result = dict(scale=scale, target=None)
    if 4 < x0 < img.shape[1] - 5 and 4 < y0 < img.shape[0] - 5:
        core = saturated_core(sat_mask, x0, y0, max(2.0, radius))
        if core:
            target = core
        else:
            sm = gaussian_filter(np.nan_to_num(work), .7)
            yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
            near = np.hypot(xx - x0, yy - y0) <= radius
            if near.any():
                k = np.argmax(np.where(near, sm, -np.inf))
                py, px = np.unravel_index(k, sm.shape)
                target = gaussian_fit(work, var, px, py)
            else:
                target = None
        if target:
            target['wing'] = wing_flux(work, sat_mask, target['x'], target['y'], 6.15 / scale)
            if not target.get('saturated'):
                # even one near-saturated / nonlinear pixel in the core makes the fitted flux unreliable
                yy2, xx2 = np.mgrid[0:img.shape[0], 0:img.shape[1]]
                core = np.hypot(xx2 - target['x'], yy2 - target['y']) <= 1.6 * 6.15 / scale
                target['nonlinear'] = bool((sat_mask & core).any())
            ra, dec = wcs.pixel_to_world_values(target['x'], target['y'])
            target.update(ra=float(ra), dec=float(dec), ex_as=target['ex'] * scale, ey_as=target['ey'] * scale)
            result['target'] = target
    stars = []
    for sx, sy in find_stars(work, flags, (x0, y0), 30.0 / scale):
        fit = gaussian_fit(work, var, sx, sy)
        if fit and fit['snr'] > 15 and .5 < fit['sigma'] < 2.5:
            ra, dec = wcs.pixel_to_world_values(fit['x'], fit['y'])
            stars.append(dict(ra=float(ra), dec=float(dec), e=max(fit['ex'], fit['ey']) * scale, flux=fit['flux']))
    result['stars'] = stars
    result['image'] = resample(work, wcs, grid, sat_mask)
    result['noise'] = robust_sigma(work)
    return result


# ---------------------------------------------------------------------------------------------------------
# relative astrometry and fitting

def match_field_stars(frames, tol_arcsec=3.0):
    """Cluster field-star detections across frames; return per-frame shifts (deg) and the star clusters."""
    refs = []          # [ra, dec, [(frame_index, star), ...]]
    for fi, frame in enumerate(frames):
        for star in frame['stars']:
            best, bd = None, tol_arcsec
            for ref in refs:
                d = math.hypot((star['ra'] - ref[0]) * math.cos(math.radians(star['dec'])), star['dec'] - ref[1]) * 3600
                if d < bd:
                    best, bd = ref, d
            if best is None:
                refs.append([star['ra'], star['dec'], [(fi, star)]])
            else:
                best[2].append((fi, star))
    refs = [r for r in refs if len(r[2]) >= max(3, .12 * len(frames))]
    shift = [(0.0, 0.0)] * len(frames)
    members = [[] for _ in frames]
    for r in refs:
        for fi, s in r[2]:
            members[fi].append((r, s))
    for _ in range(3):
        for r in refs:
            r[0] = float(np.median([s['ra'] - shift[fi][0] for fi, s in r[2]]))
            r[1] = float(np.median([s['dec'] - shift[fi][1] for fi, s in r[2]]))
        new = []
        for fi in range(len(frames)):
            if len(members[fi]) >= 3:
                new.append((float(np.median([s['ra'] - r[0] for r, s in members[fi]])),
                            float(np.median([s['dec'] - r[1] for r, s in members[fi]]))))
            else:
                new.append((0.0, 0.0))
        shift = new
    out = []
    for fi in range(len(frames)):
        m = members[fi]
        if len(m) >= 3:
            cosd = math.cos(math.radians(frames[fi]['dec_ref']))
            de = np.array([(s['ra'] - r[0] - shift[fi][0]) * 3600 * cosd for r, s in m])
            dn = np.array([(s['dec'] - r[1] - shift[fi][1]) * 3600 for r, s in m])
            scatter = math.sqrt((np.mean(de ** 2) + np.mean(dn ** 2)) / 2)
            out.append((shift[fi][0], shift[fi][1], float(scatter / math.sqrt(len(m))), len(m)))
        else:
            out.append((0.0, 0.0, float('nan'), len(m)))
    return out, refs


def wls_line(t, y, e):
    w = 1 / np.square(e)
    S, Sx, Sy, Sxx, Sxy = w.sum(), (w * t).sum(), (w * y).sum(), (w * t * t).sum(), (w * t * y).sum()
    D = S * Sxx - Sx * Sx
    if D <= 0:
        return None
    b = (S * Sxy - Sx * Sy) / D
    a = (Sy - b * Sx) / S
    chi2 = float((w * (y - a - b * t) ** 2).sum())
    dof = max(1, len(t) - 2)
    inflate = math.sqrt(max(1.0, chi2 / dof))
    return dict(a=float(a), b=float(b), eb=float(math.sqrt(S / D)) * inflate, chi2_red=chi2 / dof)


def fit_motion(points, cat):
    """points: dicts with mjd, east, north, err (arcsec). Parallax removed using the catalog value."""
    if len(points) < 2:
        return None
    t = np.array([(p['mjd'] - J2000) / 365.25 for p in points])
    if np.ptp(t) < 30 / 365.25:
        return None
    e = np.array([max(p['err'], .05) for p in points])
    east = np.array([p['east'] - p['plx_east'] for p in points])
    north = np.array([p['north'] - p['plx_north'] for p in points])
    tm = float(t.mean())
    fe, fn = wls_line(t - tm, east, e), wls_line(t - tm, north, e)
    if not fe or not fn:
        return None
    pm_ra, pm_dec = fe['b'] * 1000, fn['b'] * 1000
    err_ra, err_dec = fe['eb'] * 1000, fn['eb'] * 1000
    return dict(pmra_mas_yr=round(pm_ra, 1), pmdec_mas_yr=round(pm_dec, 1), pmra_err=round(err_ra, 1),
                pmdec_err=round(err_dec, 1), chi2_red=round((fe['chi2_red'] + fn['chi2_red']) / 2, 2),
                n=len(points), baseline_yr=round(float(np.ptp(t)), 2),
                total_mas_yr=round(math.hypot(pm_ra, pm_dec), 1),
                total_err=round(math.hypot(pm_ra * err_ra, pm_dec * err_dec) / max(math.hypot(pm_ra, pm_dec), 1e-9), 1))


# ---------------------------------------------------------------------------------------------------------
# images

def tidy_saturation(a, lo, hi):
    """White for real saturated cores, never for stray bad pixels: small +inf specks become background, and NaN
    holes enclosed by bright pixels (a saturated core that every exposure lost) become white."""
    a = a.copy()
    inf = np.isinf(a) & (a > 0)
    labels, n = label(inf)
    for k in range(1, n + 1):
        part = labels == k
        if part.sum() < 6:
            a[part] = lo
    holes, n = label(np.isnan(a))
    h, w = a.shape
    bright = lo + .5 * (hi - lo)
    for k in range(1, n + 1):
        part = holes == k
        ys, xs = np.nonzero(part)
        if part.sum() > 400 or ys.min() == 0 or xs.min() == 0 or ys.max() == h - 1 or xs.max() == w - 1:
            continue
        ring = maximum_filter(part, size=3) & ~part
        around = a[ring]
        around = np.where(np.isinf(around), hi, around)
        if np.isfinite(around).any() and np.nanmean(around) > bright:
            a[part] = np.inf
    return a


def png(path, array, lo, hi, mode='gray'):
    a = tidy_saturation(np.array(array, dtype=float), lo, hi) if mode == 'gray' else np.array(array, dtype=float)
    inf = np.isinf(a) & (a > 0)
    if mode == 'gray':
        v = np.arcsinh((a - lo) / max(hi - lo, 1e-9) * 10) / np.arcsinh(10)
        v = np.clip(np.nan_to_num(v, nan=0.0), 0, 1)
        v[inf] = 1.0
        rgb = np.repeat((v * 255).astype(np.uint8)[..., None], 3, axis=2)
    else:  # diverging: blue = fainter / gone, orange = brighter / new
        v = np.clip(np.nan_to_num(a / max(hi, 1e-9)), -1, 1)
        v[inf] = 0
        rgb = np.zeros(a.shape + (3,), dtype=np.uint8)
        pos, neg = np.clip(v, 0, 1), np.clip(-v, 0, 1)
        rgb[..., 0] = (14 + 241 * pos + 30 * neg).clip(0, 255)
        rgb[..., 1] = (16 + 140 * pos + 120 * neg).clip(0, 255)
        rgb[..., 2] = (22 + 40 * pos + 233 * neg).clip(0, 255)
    Image.fromarray(rgb[::-1]).save(path, optimize=True)


def snr_image(stack):
    sigma = robust_sigma(stack[np.isfinite(stack)])
    return stack / sigma if sigma and np.isfinite(sigma) else stack


# ---------------------------------------------------------------------------------------------------------
# inputs

def spherex_frames(field):
    index = SEED / 'featured-views' / f'{field}.json'
    if not index.is_file():
        return [], None
    session = json.loads(index.read_text(encoding='utf-8'))['session']
    manifest = json.loads((SEED / session / 'manifest.json').read_text(encoding='utf-8'))
    frames = []
    for f in manifest['frames']:
        path = SEED / Path(f['fits_url']).name
        if path.is_file() and f.get('wavelength'):
            frames.append(dict(path=path, mjd=f['mjd'], date=f['timestamp'], wavelength=float(f['wavelength']),
                               detector=f['detector'], id=f['id'], mission='SPHEREx'))
    return frames, manifest['options']


def wise_frames(field):
    series = SUPPLEMENTAL / field / 'series.json'
    if not series.is_file():
        return [], None
    data = json.loads(series.read_text(encoding='utf-8'))
    frames = []
    for s in data['series']:
        if s['band'] != 'W2':
            continue
        for f in s['frames'] + s.get('extra', []):
            path = SUPPLEMENTAL / field / Path(f['fits']).name
            if path.is_file():
                frames.append(dict(path=path, mjd=f['mjd'], date=f['date_utc'], wavelength=4.6, id=f['id'],
                                   mission=s['mission'], detector=None))
    return frames, data


def visits_of(frames):
    frames = sorted(frames, key=lambda f: f['mjd'])
    groups, current = [], []
    for f in frames:
        if current and f['mjd'] - current[-1]['mjd'] > VISIT_GAP_DAYS:
            groups.append(current)
            current = []
        current.append(f)
    if current:
        groups.append(current)
    return groups


# ---------------------------------------------------------------------------------------------------------
# main study

def catalog_for(field):
    """Catalog astrometry and the display-field centre of a star target: (cat, (ra, dec))."""
    meta = TARGETS[field]
    try:
        _, options = spherex_frames(field)
    except OSError:          # SPHEREx bundle not on this machine: fall back to the WISE series centre
        options = None
    _, series = wise_frames(field)
    cat = dict(meta.get('catalog') or {})
    if not cat and series:
        c = series['catalog']
        cat = dict(ra=c['ra'], dec=c['dec'], pmra_mas_yr=c['pmra_mas_yr'], pmdec_mas_yr=c['pmdec_mas_yr'],
                   parallax_mas=c.get('parallax_mas') or 0.0, source=c.get('source', 'SIMBAD'), name=c.get('name'))
    if not cat:
        raise ValueError(f'No catalog astrometry for {field}.')
    if options:
        center = (options['ra'], options['dec'])
    elif series:
        center = (series['center']['ra'], series['center']['dec'])
    else:
        center = (cat['ra'], cat['dec'])
    return cat, center


def study(field, log=print):
    meta = TARGETS[field]
    sx_frames, options = spherex_frames(field)
    w_frames, series = wise_frames(field)
    cat, center = catalog_for(field)
    grid = display_grid(*center)
    out = OUT / field
    (out / 'img').mkdir(parents=True, exist_ok=True)
    for old in (out / 'img').glob('*.png'):
        old.unlink()
    started = time.monotonic()

    cache_root = os.environ.get('MOTION_STUDY_CACHE')
    budget = float(os.environ.get('MOTION_STUDY_BUDGET', 'inf'))

    def measure_all(frames, mission, search):
        done = []
        cache = Path(cache_root) / field if cache_root else None
        if cache:
            cache.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(frames):
            key = cache / f"v3-{f['path'].name}-{f['mjd']:.5f}.pkl" if cache else None
            if key and key.is_file():
                m = pickle.loads(key.read_bytes())
            else:
                if time.monotonic() - started > budget:
                    raise TimeoutError(f'{field}: time budget reached at {mission} frame {i}; run again to resume.')
                try:
                    m = measure_frame(f['path'], cat, f['mjd'], mission, grid, search)
                except Exception as error:  # a corrupt file must not stop the study
                    log(f'  skip {f["id"]}: {error}')
                    continue
                if key:
                    key.write_bytes(pickle.dumps(m))
            m.update(f)
            m['dec_ref'] = cat['dec']
            done.append(m)
            if i and i % 50 == 0:
                log(f'  {mission}: {i}/{len(frames)} frames ({time.monotonic() - started:.0f}s)')
        return done

    log(f'{field}: {len(sx_frames)} SPHEREx frames, {len(w_frames)} WISE/NEOWISE W2 frames')
    sx = measure_all(sx_frames, 'SPHEREx', 15.0)
    wi = measure_all(w_frames, 'WISE', 10.0)

    # relative astrometry per mission
    refs_by = {}
    for name, frames in (('sx', sx), ('wi', wi)):
        refs_by[name] = []
        if not frames:
            continue
        shifts, refs = match_field_stars(frames)
        for f, (dra, ddec, err, n) in zip(frames, shifts):
            f['shift'] = (dra, ddec)
            f['shift_err'] = err
            f['ref_stars'] = n
        refs_by[name] = refs
    sx_refs, wi_refs = refs_by['sx'], refs_by['wi']

    def corrected_points(frames):
        pts = []
        for f in frames:
            t = f.get('target')
            if not t:
                continue
            dra, ddec = f.get('shift', (0.0, 0.0))
            ra, dec = t['ra'] - dra, t['dec'] - ddec
            east, north = offsets(cat, ra, dec)
            _, _, pe, pn = expected(cat, f['mjd'])
            _, _, me, mn = expected(dict(cat, parallax_mas=0.0), f['mjd'])
            floor = f.get('shift_err')
            if floor is None or not math.isfinite(floor):
                floor = .5 * f['scale']       # no field stars to align on: assume half a pixel of WCS error
            err = math.hypot(math.hypot(t['ex_as'], t['ey_as']) / math.sqrt(2), floor)
            pts.append(dict(mjd=f['mjd'], date=f['date'], mission=f['mission'], east=east, north=north,
                            err=err, plx_east=pe - me, plx_north=pn - mn, exp_east=pe, exp_north=pn,
                            saturated=bool(t.get('saturated')), snr=t.get('snr'), wavelength=f['wavelength'],
                            id=f['id']))
        return pts

    sx_pts, wi_pts = corrected_points(sx), corrected_points(wi)

    def visit_points(pts, frames_by_visit):
        result = []
        for visit in frames_by_visit:
            ids = {f['id'] for f in visit}
            vp = [p for p in pts if p['id'] in ids and (p['saturated'] or (p['snr'] or 0) >= 5)]
            if len(vp) < 1:
                continue
            e = np.array([max(p['err'], .05) for p in vp])
            w = 1 / e ** 2
            east = float((w * [p['east'] for p in vp]).sum() / w.sum())
            north = float((w * [p['north'] for p in vp]).sum() / w.sum())
            # standard error from scatter, never smaller than the formal error
            if len(vp) >= 3:
                sc = math.hypot(np.std([p['east'] for p in vp]), np.std([p['north'] for p in vp])) / math.sqrt(2) / math.sqrt(len(vp) - 1)
            else:
                sc = 0
            err = max(float(1 / math.sqrt(w.sum())), sc)
            mjd = float(np.mean([p['mjd'] for p in vp]))
            _, _, pe, pn = expected(cat, mjd)
            _, _, me, mn = expected(dict(cat, parallax_mas=0.0), mjd)
            result.append(dict(mjd=mjd, date=Time(mjd, format='mjd').isot[:10], mission=vp[0]['mission'],
                               east=round(east, 3), north=round(north, 3), err=round(err, 3), frames=len(vp),
                               plx_east=pe - me, plx_north=pn - mn, exp_east=round(pe, 3), exp_north=round(pn, 3),
                               saturated=sum(p['saturated'] for p in vp)))
        return result

    sx_visits, wi_visits = visits_of(sx), visits_of(wi)
    sx_vp, wi_vp = visit_points(sx_pts, sx_visits), visit_points(wi_pts, wi_visits)
    fits_ = dict(spherex=fit_motion(sx_vp, cat) if len(sx_vp) >= 2 else fit_motion(sx_pts, cat),
                 wise=fit_motion(wi_vp, cat), combined=fit_motion(sx_vp + wi_vp, cat))

    # field-star null test: stars should not move measurably over the SPHEREx baseline
    def null_test(frames, refs):
        tested = static = 0
        motions = []
        for r in refs:
            pts = []
            for fi, s in r[2]:
                f = frames[fi]
                dra, ddec = f.get('shift', (0.0, 0.0))
                east = ((s['ra'] - dra) - r[0]) * 3600 * math.cos(math.radians(r[1]))
                north = ((s['dec'] - ddec) - r[1]) * 3600
                pts.append(dict(mjd=f['mjd'], east=east, north=north, err=max(s['e'], .05), plx_east=0, plx_north=0))
            fit = fit_motion(pts, cat)
            if not fit:
                continue
            tested += 1
            sig = math.hypot(fit['pmra_mas_yr'] / max(fit['pmra_err'], 1e-6), fit['pmdec_mas_yr'] / max(fit['pmdec_err'], 1e-6)) / math.sqrt(2)
            if sig < 3:
                static += 1
            motions.append(fit['total_mas_yr'])
        return dict(tested=tested, static=static, fraction=round(static / tested, 3) if tested else None,
                    median_spurious_mas_yr=round(float(np.median(motions)), 1) if motions else None)

    field_stars = dict(spherex=null_test(sx, sx_refs) if sx else None, wise=null_test(wi, wi_refs) if wi else None)

    # brightness at fixed wavelength (SPHEREx), relative to field stars of the same frames
    brightness = brightness_test(sx, sx_visits, sx_refs)

    # stacks
    bands_out, visits_out, diffs = [], [], {}
    stacks = {}
    for key, label_, centre, half in BANDS:
        for vi, visit in enumerate(sx_visits):
            imgs = np.array([f['image'] for f in visit if abs(f['wavelength'] - centre) <= half])
            if not len(imgs):
                continue
            stacks[(key, vi)] = (np.nanmedian(np.where(np.isinf(imgs), np.nan, imgs), axis=0),
                                 np.mean(np.isinf(imgs), axis=0) > .5, len(imgs),
                                 float(np.mean([f['wavelength'] for f in visit if abs(f['wavelength'] - centre) <= half])))
    for key, label_, centre, half in BANDS:
        present = [vi for vi in range(len(sx_visits)) if (key, vi) in stacks]
        if not present:
            continue
        values = np.concatenate([stacks[(key, vi)][0][np.isfinite(stacks[(key, vi)][0])] for vi in present])
        sigma = robust_sigma(values)
        lo, hi = -1.5 * sigma, float(np.percentile(values, 99.7))
        bands_out.append(dict(key=key, label=label_, center_um=centre, visits=len(present)))
        for vi in present:
            stack, sat, n, wl = stacks[(key, vi)]
            draw = stack.copy()
            draw[sat] = np.inf
            name = f'sx-{key}-{vi}.png'
            png(out / 'img' / name, draw, lo, hi)
            stacks[(key, vi)] = stacks[(key, vi)] + (name,)
        if len(present) >= 2:
            first, last = stacks[(key, present[0])][0], stacks[(key, present[-1])][0]
            diff = last - first
            name = f'sx-{key}-diff.png'
            png(out / 'img' / name, diff, 0, 6 * sigma, mode='diverging')
            diffs[key] = name
    for vi, visit in enumerate(sx_visits):
        entry = dict(index=vi, mission='SPHEREx', first=visit[0]['date'][:10], last=visit[-1]['date'][:10],
                     mjd=float(np.mean([f['mjd'] for f in visit])), frames=len(visit), stacks={})
        for key, *_ in BANDS:
            if (key, vi) in stacks and len(stacks[(key, vi)]) == 5:
                _, _, n, wl, name = stacks[(key, vi)]
                entry['stacks'][key] = dict(png=name, frames=n, wavelength_um=round(wl, 3))
        visits_out.append(entry)

    # long-baseline time-lapse at 4.6 µm: WISE/NEOWISE W2 visit stacks + SPHEREx 4.6 µm visit stacks
    timelapse = []
    snr_stacks = []
    for vi, visit in enumerate(wi_visits):
        imgs = np.array([f['image'] for f in visit])
        stack = np.nanmedian(np.where(np.isinf(imgs), np.nan, imgs), axis=0)
        sat = np.mean(np.isinf(imgs), axis=0) > .5     # saturated in most exposures, not a stray flagged pixel
        snr_stacks.append(('WISE', visit, snr_image(stack), sat))
    for vi, visit in enumerate(sx_visits):
        if ('4.6', vi) in stacks:
            stack, sat, n, wl = stacks[('4.6', vi)][:4]
            sel = [f for f in visit if abs(f['wavelength'] - 4.6) <= .22]
            snr_stacks.append(('SPHEREx', sel, snr_image(stack), sat))
    for i, (mission, visit, image, sat) in enumerate(sorted(snr_stacks, key=lambda s: s[1][0]['mjd'])):
        draw = image.copy()
        draw[sat] = np.inf
        name = f'tl-{i:02d}.png'
        png(out / 'img' / name, draw, -1.5, 60)
        mjd = float(np.mean([f['mjd'] for f in visit]))
        ra_e, dec_e, _, _ = expected(cat, mjd)
        ex, ey = grid.world_to_pixel_values(ra_e, dec_e)
        pts = (wi_vp if mission == 'WISE' else sx_vp)
        match = min(pts, key=lambda p: abs(p['mjd'] - mjd)) if pts else None
        measured = None
        if match and abs(match['mjd'] - mjd) < VISIT_GAP_DAYS:
            ra_m = cat['ra'] + match['east'] / 3600 / math.cos(math.radians(cat['dec']))
            dec_m = cat['dec'] + match['north'] / 3600
            mx, my = grid.world_to_pixel_values(ra_m, dec_m)
            measured = dict(x=round(float(mx), 2), y=round(float(GRID_SIZE - 1 - my), 2), err_px=round(match['err'] / GRID_SCALE, 2))
        mission_name = visit[0]['mission'] if mission == 'WISE' else 'SPHEREx'
        timelapse.append(dict(png=name, mission=mission_name, band='W2 4.6 µm' if mission == 'WISE' else 'SPHEREx 4.6 µm',
                              date=Time(mjd, format='mjd').isot[:10], mjd=round(mjd, 3), frames=len(visit),
                              expected=dict(x=round(float(ex), 2), y=round(float(GRID_SIZE - 1 - ey), 2)),
                              measured=measured))

    verdict = decide(meta, cat, fits_, sx_vp, wi_vp, brightness, field_stars)
    track = []
    if sx_vp or wi_vp:
        t0 = min(p['mjd'] for p in sx_vp + wi_vp) - 60
        t1 = max(p['mjd'] for p in sx_vp + wi_vp) + 60
        for t in np.linspace(t0, t1, 240):
            _, _, e_, n_ = expected(cat, t)
            track.append([round(float(t), 2), round(e_, 3), round(n_, 3)])

    result = dict(
        field=field, name=meta['name'], kind=meta['kind'], expect=meta['expect'],
        generated_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        grid=dict(size=GRID_SIZE, scale_arcsec=GRID_SCALE, center=list(center), north='up', east='left'),
        catalog=dict(ra=cat['ra'], dec=cat['dec'], pmra_mas_yr=cat['pmra_mas_yr'], pmdec_mas_yr=cat['pmdec_mas_yr'],
                     parallax_mas=cat.get('parallax_mas', 0.0), assumed=bool(cat.get('assumed')), source=cat.get('source')),
        counts=dict(spherex_frames=len(sx), spherex_visits=len(sx_visits), wise_frames=len(wi), wise_visits=len(wi_visits),
                    spherex_target_measured=len(sx_pts), wise_target_measured=len(wi_pts)),
        bands=bands_out, visits=visits_out, differences=diffs, timelapse=timelapse,
        astrometry=dict(points=[_clean(p) for p in sx_vp + wi_vp],
                        frames=[[round(p['mjd'], 3), round(p['east'], 2), round(p['north'], 2), round(p['err'], 2), p['mission'][0], int(p['saturated'])] for p in sx_pts + wi_pts],
                        track=track, fits=fits_),
        field_stars=field_stars, brightness=brightness, verdict=verdict,
        limits=limits_for(meta, cat, fits_, field_stars, sx_pts, wi_pts),
        credits=[
            'SPHEREx spectral images: NASA/JPL-Caltech/IPAC, NASA/IPAC Infrared Science Archive (IRSA).',
            'WISE and NEOWISE-R single exposures: NASA/JPL-Caltech/UCLA, IRSA.',
            f'Catalog astrometry: {cat.get("source")}.',
        ],
        runtime_s=round(time.monotonic() - started, 1),
    )
    (out / 'study.json').write_text(json.dumps(result, separators=(',', ':')), encoding='utf-8')
    log(f'{field}: done in {result["runtime_s"]}s · verdict: {verdict["title"]}')
    return result


def _clean(p):
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in p.items() if k not in ('plx_east', 'plx_north')}


def _window_amplitudes(samples, sample_err):
    """samples: [(window, time_bin, value)] -> [(window, amplitude_mag, bins, significance)] for windows with 2+ bins."""
    windows = {}
    for wl, tb, value in samples:
        if value and value > 0:
            windows.setdefault(wl, {}).setdefault(tb, []).append(value)
    out = []
    for wl, per_bin in windows.items():
        if len(per_bin) < 2:
            continue
        means = np.array([float(np.median(v)) for v in per_bin.values()])
        errs = np.array([sample_err * abs(float(np.median(v))) / math.sqrt(len(v)) for v in per_bin.values()])
        hi, lo = int(np.argmax(means)), int(np.argmin(means))
        significance = (means[hi] - means[lo]) / max(math.hypot(errs[hi], errs[lo]), 1e-12)
        out.append((wl, 2.5 * math.log10(means.max() / means.min()), len(means), float(significance)))
    return out


def brightness_test(frames, visits, refs, bin_days=10.0):
    """Ensemble differential photometry: every frame gets a zero point from the field stars it shares with the
    others (each star compared with its own median at that wavelength), the target is divided by that zero point,
    and its brightness is compared between 10-day bins at matching wavelengths. The field stars go through the
    same measurement, which sets the noise floor a real change has to beat."""
    if not frames or not refs:
        return dict(tested=False, reason='Needs field stars to calibrate against.')
    window = lambda f: round(f['wavelength'] / .1) * .1
    time_bin = lambda f: int(f['mjd'] // bin_days)
    medians = {}
    for ci, r in enumerate(refs):
        for fi, star in r[2]:
            medians.setdefault((ci, window(frames[fi])), []).append(star['flux'])
    medians = {k: float(np.median(v)) for k, v in medians.items()}
    per_frame = {}
    for ci, r in enumerate(refs):
        for fi, star in r[2]:
            m = medians[(ci, window(frames[fi]))]
            if m > 0 and star['flux'] > 0:
                per_frame.setdefault(fi, []).append((ci, star['flux'] / m))
    zp = {fi: float(np.median([v for _, v in vals])) for fi, vals in per_frame.items() if len(vals) >= 3}
    if len(zp) < 6:
        return dict(tested=False, reason='Too few frames share three or more field stars.')
    # scatter of a single calibrated field-star measurement, i.e. the photometric noise per sample
    resid = [v / zp[fi] for fi, vals in per_frame.items() if fi in zp for _, v in vals]
    sample_err = max(.02, 1.4826 * float(np.median(np.abs(np.array(resid) - 1))))
    measured = [(fi, f) for fi, f in enumerate(frames) if f.get('target') and fi in zp]
    saturated = sum(bool(f['target'].get('saturated')) for _, f in measured)
    # One method per target: mixing fitted fluxes with wing fluxes would fake a brightness change.
    clean = sum(1 for _, f in measured if not (f['target'].get('saturated') or f['target'].get('nonlinear')) and (f['target'].get('snr') or 0) > 20)
    # Prefer fitted fluxes from the wavelengths where the star is not saturated; fall back to wings only if needed.
    use_wings = bool(measured) and clean < 10 and saturated / len(measured) > .2
    method = 'PSF wings (the core is saturated)' if use_wings else 'PSF fit (unsaturated frames, S/N > 20)'
    target_samples = []
    for fi, f in measured:
        t = f['target']
        if use_wings:
            value = t.get('wing')
        else:
            value = t['flux'] if not (t.get('saturated') or t.get('nonlinear')) and (t.get('snr') or 0) > 20 else None
        if value and value > 0:
            target_samples.append((window(f), time_bin(f), value / zp[fi]))
    target = _window_amplitudes(target_samples, sample_err)
    star_amps = []
    for ci, r in enumerate(refs):
        samples = [(window(frames[fi]), time_bin(frames[fi]), star['flux'] / zp[fi]) for fi, star in r[2] if fi in zp]
        amps = _window_amplitudes(samples, sample_err)
        if amps:
            star_amps.append(float(np.median([a[1] for a in amps])))
    if not target:
        return dict(tested=False, reason='No matching-wavelength target measurements in two or more 10-day bins.')
    amp = float(np.median([a[1] for a in target]))
    significance = float(np.median([a[3] for a in target]))
    floor = float(np.percentile(star_amps, 90)) if len(star_amps) >= 5 else None
    threshold = max(.2, 2 * floor) if floor is not None else .4
    if use_wings:
        threshold = max(threshold, .6)   # wing photometry of a saturated star is far less precise than a fit
    variable = amp > threshold and significance > 5
    return dict(tested=True, windows=len(target), median_amplitude_mag=round(amp, 3), method=method,
                significance=round(significance, 1), sample_noise=round(sample_err, 3),
                field_star_floor_mag=round(floor, 3) if floor is not None else None, field_stars=len(star_amps),
                threshold_mag=round(threshold, 3), variable=variable,
                rule=('Variable if the target’s median brightness change between 10-day bins (same 0.1 µm wavelength window, '
                      'calibrated on the field stars) exceeds the larger of 0.2 mag and twice the 90th-percentile change of the '
                      'field stars (0.4 mag when fewer than five can be tested; at least 0.6 mag when only the PSF wings of a '
                      'saturated star can be used), and is over 5σ.'),
                examples=[dict(wavelength_um=round(a[0], 1), amplitude_mag=round(a[1], 3), bins=a[2], sigma=round(a[3], 1))
                          for a in sorted(target, key=lambda x: -x[1])[:6]])


def decide(meta, cat, fits_, sx_vp, wi_vp, brightness, field_stars):
    pm_cat = math.hypot(cat['pmra_mas_yr'], cat['pmdec_mas_yr'])
    best = fits_.get('combined') or fits_.get('spherex') or fits_.get('wise')
    n_points = len(sx_vp) + len(wi_vp)
    if best is None or n_points < 3:
        return dict(code='not-measurable', title='Not measurable',
                    summary='Too few clean position measurements (the target is saturated, too faint, or off the frames).',
                    rule='Needs at least three visit positions spanning 30+ days.', numbers=dict(visit_points=n_points))
    pm = best['total_mas_yr']
    err = math.hypot(best['pmra_err'], best['pmdec_err']) / math.sqrt(2)
    significant = pm / max(err, 1e-6) > 3
    diff = math.hypot(best['pmra_mas_yr'] - cat['pmra_mas_yr'], best['pmdec_mas_yr'] - cat['pmdec_mas_yr'])
    consistent = diff / max(err, 1e-6) < 3
    predicted_shift = pm_cat * best['baseline_yr'] / 1000
    pos_err = float(np.median([p['err'] for p in sx_vp + wi_vp]))
    numbers = dict(measured_mas_yr=pm, error_mas_yr=round(err, 1), catalog_mas_yr=round(pm_cat, 1),
                   difference_mas_yr=round(diff, 1), baseline_yr=best['baseline_yr'], predicted_shift_arcsec=round(predicted_shift, 2),
                   typical_position_error_arcsec=round(pos_err, 2), points=best['n'])
    variable = brightness.get('tested') and brightness.get('variable')
    wings_only = brightness.get('tested') and 'wings' in brightness.get('method', '')
    if meta['expect'] == 'brightness' and wings_only and not variable:
        return dict(code='saturated', title='Too bright for a reliable brightness test',
                    summary=(f"The star saturates SPHEREx at most wavelengths, so only its PSF wings can be measured; the change seen "
                             f"({brightness['median_amplitude_mag']:.2f} mag) is within what wing photometry fakes on other bright stars. "
                             f"Position: {pm:.0f} ± {err:.0f} mas/yr, consistent with staying put."),
                    rule='Brightness target whose core is saturated in more than 20 % of frames with fewer than 10 clean fits; wing-photometry changes below 0.6 mag are not trusted.',
                    numbers=dict(numbers, median_amplitude_mag=brightness['median_amplitude_mag'], threshold_mag=brightness['threshold_mag']))
    if variable and not (significant and pm_cat > 100):
        return dict(code='brightness', title='Changes in brightness, not position',
                    summary=f"The position stays put within the errors, but the brightness changes by about {brightness['median_amplitude_mag']:.2f} mag between observing dates at matching wavelengths.",
                    rule=brightness['rule'] + ' Motion not significant at 3σ.', numbers=dict(numbers, **{k: brightness[k] for k in ('median_amplitude_mag', 'threshold_mag')}))
    if predicted_shift < 3 * pos_err and not significant:
        return dict(code='too-small', title='Expected motion too small for this baseline',
                    summary=f'The catalog predicts a shift of {predicted_shift:.2f}″ over {best["baseline_yr"]:.1f} years, below three times the typical position error ({pos_err:.2f}″).',
                    rule='Predicted shift over the measured baseline < 3 × median position error, and no significant measured motion.', numbers=numbers)
    if significant and consistent:
        return dict(code='as-predicted', title='Moves as predicted',
                    summary=f'Measured {pm:.0f} ± {err:.0f} mas/yr against the catalog {pm_cat:.0f} mas/yr: the difference ({diff:.0f} mas/yr) is within 3σ.',
                    rule='Measured motion > 3σ from zero and within 3σ of the catalog proper motion.', numbers=numbers)
    if significant:
        return dict(code='differs', title='Moves, but not as predicted',
                    summary=f'Measured {pm:.0f} ± {err:.0f} mas/yr against the catalog {pm_cat:.0f} mas/yr: off by {diff:.0f} mas/yr (> 3σ). Check for blending, saturation or a mismatched source.',
                    rule='Measured motion > 3σ from zero but more than 3σ from the catalog proper motion.', numbers=numbers)
    if pm_cat < 3 * err:
        return dict(code='static', title='Stays put, as expected',
                    summary=f'No significant motion ({pm:.0f} ± {err:.0f} mas/yr), consistent with a catalog motion of {pm_cat:.0f} mas/yr.',
                    rule='Measured motion < 3σ from zero, and the catalog motion is also below 3σ of the measurement error.', numbers=numbers)
    return dict(code='not-detected', title='Expected motion not detected',
                summary=f'The catalog predicts {pm_cat:.0f} mas/yr, but the measurement ({pm:.0f} ± {err:.0f} mas/yr) is not significant.',
                rule='Measured motion < 3σ from zero although the catalog predicts a detectable shift.', numbers=numbers)


def limits_for(meta, cat, fits_, field_stars, sx_pts, wi_pts):
    out = [
        'Positions are measured near the catalog prediction (within 15″ for SPHEREx, 10″ for WISE); a different source closer to the prediction would be picked instead.',
        'Relative astrometry: each frame is aligned on its own field stars, which assumes those stars barely move. The field-star null test checks this.',
        'WISE/NEOWISE and SPHEREx are different telescopes with similar resolution at 4.6 µm (about 6″); their positions are combined after each is aligned on field stars.',
        'Error bars are inflated by √(reduced χ²) when the scatter is larger than the formal errors, but systematic offsets between missions are not modelled.',
    ]
    if any(p['saturated'] for p in sx_pts + wi_pts):
        n = sum(p['saturated'] for p in sx_pts + wi_pts)
        out.append(f'{n} frame positions come from a saturated core (centroid of saturated pixels), which is less precise than a fit.')
    if cat.get('assumed'):
        out.append('No catalog proper motion is bundled for this star; it is treated as negligible (a distant star).')
    fs = field_stars.get('spherex')
    if fs and fs.get('tested'):
        out.append(f"Field-star null test (SPHEREx): {fs['static']} of {fs['tested']} field stars show no significant motion, as expected for distant stars.")
    return out


# JPL Horizons position (observer SPHEREx) for the first bundled exposure, as recorded in ephemeris.py's self-test.
VESTA_KNOWN = {60891.461818273: (222.866226866, -11.907544792)}
VESTA_BUNDLED = ROOT / 'backend/data/vesta'
VESTA_TRACK = ROOT / 'backend/data/vesta-track'          # older single-cutout downloads (fetch_vesta_track.py)
TRACKS = ROOT / 'backend/data/tracks'                    # tiled downloads (scripts/fetch_track.py)


def load_track(slug):
    path = TRACKS / slug / 'track.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def track_exposures(slug):
    """Every exposure of a tracked target: [{mjd, date, id, detector, predicted, files: [(path, tile)], scene}].
    Tiled downloads carry a scene index (one fixed box of tiles); older single cutouts have scene None."""
    found = {}
    if slug == 'vesta':
        manifest = VESTA_BUNDLED / 'manifest.json'
        if manifest.is_file():
            for f in json.loads(manifest.read_text(encoding='utf-8'))['frames']:
                path = VESTA_BUNDLED / f['file']
                with fits.open(path, memmap=False) as hdus:
                    h = hdus['IMAGE'].header
                    mjd = float(h.get('MJD-AVG') or Time(f['date'].rstrip('Z')).mjd)
                    found[(str(h['OBSID']), int(h['DETECTOR']))] = dict(
                        path=path, files=[(path, None)], scene=None, mjd=mjd, date=Time(mjd, format='mjd').isot + 'Z',
                        id=str(h['OBSID']), detector=int(h['DETECTOR']),
                        predicted=next((v for k, v in VESTA_KNOWN.items() if abs(k - mjd) < 1e-6), None))
        legacy = VESTA_TRACK / 'track.json'
        if legacy.is_file():
            for f in json.loads(legacy.read_text(encoding='utf-8'))['frames']:
                path = VESTA_TRACK / f['file']
                if path.is_file():
                    found[(f['id'], f['detector'])] = dict(path=path, files=[(path, None)], scene=None, mjd=f['mjd'], date=f['date'],
                                                           id=f['id'], detector=f['detector'], predicted=(f['vesta_ra'], f['vesta_dec']))
    track = load_track(slug)
    for e in (track or {}).get('exposures', []):
        files = [(TRACKS / slug / name, key) for key, name in sorted(e['tiles'].items()) if (TRACKS / slug / name).is_file()]
        if files:
            found[(e['id'], e['detector'])] = dict(path=files[0][0], files=files, scene=e['scene'], mjd=e['mjd'], date=e['date'],
                                                   id=e['id'], detector=e['detector'], predicted=(e['target_ra'], e['target_dec']))
    return sorted(found.values(), key=lambda f: f['mjd']), track


def vesta_frames():
    return track_exposures('vesta')[0]


def grid_at(ra, dec, scale, size):
    g = WCS(naxis=2)
    g.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    g.wcs.crval = [ra, dec]
    g.wcs.crpix = [(size + 1) / 2] * 2
    g.wcs.cdelt = [-scale / 3600, scale / 3600]
    return g


def resample_to(data, wcs, grid, size):
    ys, xs = np.mgrid[0:size, 0:size]
    sky = grid.pixel_to_world_values(xs.ravel(), ys.ravel())
    px, py = wcs.world_to_pixel_values(*sky)
    good = np.isfinite(data)
    value = map_coordinates(np.where(good, data, 0.0), [py, px], order=1, mode='constant', cval=np.nan)
    weight = map_coordinates(good.astype(float), [py, px], order=1, mode='constant', cval=0.0)
    return np.where(weight > .6, value / np.maximum(weight, 1e-6), np.nan).reshape(size, size)


def load_parts(f):
    """All tile cutouts of one exposure, with one shared sky level so the tiles join without seams."""
    parts = []
    for path, key in f['files']:
        with fits.open(path, memmap=False) as hdus:
            img = hdus['IMAGE'].data.astype(np.float32)
            flags = hdus['FLAGS'].data.astype(np.int64)
            wcs = WCS(hdus['IMAGE'].header).celestial
        sat = (flags & SAT_BITS) != 0
        img[((flags & BAD_BITS) != 0) & ~sat] = np.nan
        parts.append(dict(img=img, sat=sat, wcs=wcs, tile=key, scale=abs(wcs.proj_plane_pixel_scales()[0].to_value('arcsec'))))
    values = np.concatenate([p['img'][np.isfinite(p['img'])].ravel() for p in parts]) if parts else np.array([])
    bg = float(np.median(values)) if values.size else 0.0
    for p in parts:
        p['work'] = p['img'] - bg
    return parts


def mosaic(parts, grid, size):
    acc = np.zeros((size, size)); n = np.zeros((size, size))
    for p in parts:
        r = resample_to(p['work'], p['wcs'], grid, size)
        ok = np.isfinite(r)
        acc[ok] += r[ok]; n[ok] += 1
    return np.where(n > 0, acc / np.maximum(n, 1), np.nan)


def measure_parts(parts, predicted):
    """Locate the target in the tile that holds its predicted position (or the brightest source, without one)."""
    best = None
    for p in parts:
        h, w = p['work'].shape
        if predicted:
            x0, y0 = (float(v) for v in p['wcs'].world_to_pixel_values(*predicted))
            if not (3 <= x0 < w - 3 and 3 <= y0 < h - 3):
                continue
            d = math.hypot(x0 - w / 2, y0 - h / 2)
            if best is None or d < best[0]:
                best = (d, p, x0, y0, 30 / p['scale'])
        elif best is None:
            sm = gaussian_filter(np.nan_to_num(p['work']), 1.0)
            y0, x0 = (float(v) for v in np.unravel_index(np.argmax(np.where(np.isfinite(p['work']), sm, -np.inf)), sm.shape))
            best = (0, p, x0, y0, 4)
    if not best:
        return None
    _, p, x0, y0, radius = best
    target = saturated_core(p['sat'], x0, y0, radius) or gaussian_fit(p['work'], None, x0, y0)
    if not target:
        return None
    ra, dec = (float(v) for v in p['wcs'].pixel_to_world_values(target['x'], target['y']))
    return dict(ra=ra, dec=dec, err=max(target['ex'], target['ey']) * p['scale'], saturated=bool(target.get('saturated')))


def _sky_scenes(measured, track):
    """Fixed-sky scenes: one per tiled scene (a box of tiles), plus visit groups for older single cutouts."""
    from . import tiles as T
    scenes = []
    tiled = {}
    for f in measured:
        if f['scene'] is not None and track:
            tiled.setdefault(f['scene'], []).append(f)
    for k, members in tiled.items():
        sc = track['scenes'][k]
        size_t = track['tile_arcmin']
        tiling = T.Tiling(sc['anchor'][0], sc['anchor'][1], size_t)
        box = sc['box']
        nx, ny = T.box_dims(box)
        cra, cdec = T.from_plane((box[0] + box[1]) / 2 * size_t, (box[2] + box[3]) / 2 * size_t, *sc['anchor'])
        side = max(nx, ny) * size_t * 60
        size = int(min(600, max(360, round(side / 3))))
        grid = grid_at(cra, cdec, side / size, size)
        outlines = []
        for i, j in T.box_tiles(box):
            xs, ys = zip(*(grid.world_to_pixel_values(*c) for c in tiling.corners(i, j)))
            outlines.append(dict(key=T.tile_key(i, j), x0=round(float(min(xs)), 1), x1=round(float(max(xs)), 1),
                                 y0=round(float(size - 1 - max(ys)), 1), y1=round(float(size - 1 - min(ys)), 1)))
        scenes.append(dict(members=members, grid=grid, size=size, scale=side / size, tiles=outlines, layout=f'{nx}×{ny}'))
    groups, current = [], []
    for f in [f for f in measured if f['scene'] is None or not track]:
        if current and f['mjd'] - current[-1]['mjd'] > 5:
            groups.append(current); current = []
        current.append(f)
    if current:
        groups.append(current)
    for group in groups:
        ras = np.array([f['ra'] for f in group]); decs = np.array([f['dec'] for f in group])
        cra = float(np.degrees(np.arctan2(np.mean(np.sin(np.radians(ras))), np.mean(np.cos(np.radians(ras))))) % 360)
        cdec = float(decs.mean())
        extent = max(float(np.max(np.hypot((ras - cra) * math.cos(math.radians(cdec)), decs - cdec))) * 3600 * 2 + 900, 900)
        scenes.append(dict(members=group, grid=grid_at(cra, cdec, extent / 360, 360), size=360, scale=extent / 360, tiles=None, layout=None))
    scenes.sort(key=lambda s: s['members'][0]['mjd'])
    return scenes


def build_track(slug, out, follow=True, log=print):
    """Measure a tracked target in every exposure and draw the follow and fixed-sky (tile mosaic) images."""
    frames, track = track_exposures(slug)
    measured, noises, highs = [], [], []
    for f in frames:
        parts = load_parts(f)
        m = measure_parts(parts, f['predicted'])
        if not m:
            log(f'  {slug}: target not found in {f["id"]} D{f["detector"]}')
            continue
        f.update(m)
        work = np.concatenate([p['work'][np.isfinite(p['work'])].ravel() for p in parts])
        noises.append(robust_sigma(work)); highs.append(float(np.percentile(work, 99.7)))
        measured.append(f)
    if not measured:
        raise ValueError(f'No {slug} exposures could be measured.')
    noise, hi = float(np.nanmedian(noises)), float(np.nanmedian(highs))
    scenes = _sky_scenes(measured, track)
    follow_frames, sky, path = [], [], []
    for vi, sc in enumerate(scenes):
        g_sky, size = sc['grid'], sc['size']
        trail = [[round(float(x), 1), round(float(size - 1 - y), 1)] for x, y in
                 (g_sky.world_to_pixel_values(o['ra'], o['dec']) for o in sc['members'])]
        for f in sc['members']:
            i = len(path)
            parts = load_parts(f)
            date = f['date'][:19].replace('T', ' ') + ' UTC'
            if follow:
                g = grid_at(f['ra'], f['dec'], GRID_SCALE, GRID_SIZE)
                name = f'follow-{i:03d}.png'
                png(out / 'img' / name, mosaic(parts, g, GRID_SIZE), -1.5 * noise, hi)
                exp = None
                if f['predicted']:
                    ex, ey = g.world_to_pixel_values(*f['predicted'])
                    exp = dict(x=round(float(ex), 2), y=round(float(GRID_SIZE - 1 - ey), 2))
                c = (GRID_SIZE - 1) / 2
                follow_frames.append(dict(png=name, mission='SPHEREx', date=date, mjd=round(f['mjd'], 5), frames=1,
                                          detector=f['detector'], expected=exp, measured=dict(x=c, y=c, err_px=round(f['err'] / GRID_SCALE, 2))))
            name = f'sky-{i:03d}.png'
            png(out / 'img' / name, mosaic(parts, g_sky, size), -1.5 * noise, hi)
            mx, my = g_sky.world_to_pixel_values(f['ra'], f['dec'])
            exp = None
            if f['predicted']:
                ex, ey = g_sky.world_to_pixel_values(*f['predicted'])
                exp = dict(x=round(float(ex), 2), y=round(float(size - 1 - ey), 2))
            sky.append(dict(png=name, visit=vi, size=size, scale_arcsec=round(sc['scale'], 2), date=date, mjd=round(f['mjd'], 5),
                            detector=f['detector'], measured=dict(x=round(float(mx), 2), y=round(float(size - 1 - my), 2),
                                                                  err_px=round(f['err'] / sc['scale'], 2)),
                            expected=exp, trail=trail, tiles=sc['tiles'], layout=sc['layout'],
                            have=[p['tile'] for p in parts if p['tile']]))
            residual = None
            if f['predicted']:
                pra, pdec = f['predicted']
                residual = [round(((f['ra'] - pra + 540) % 360 - 180) * 3600 * math.cos(math.radians(pdec)), 2),
                            round((f['dec'] - pdec) * 3600, 2)]
            path.append(dict(mjd=round(f['mjd'], 5), date=f['date'], ra=round(f['ra'], 6), dec=round(f['dec'], 6),
                             err=round(f['err'], 2), visit=vi, residual=residual,
                             predicted=[round(f['predicted'][0], 6), round(f['predicted'][1], 6)] if f['predicted'] else None))
    return dict(follow=follow_frames, sky=sky, path=path, scenes=len(scenes), track=track,
                tiles=dict(tile_arcmin=track['tile_arcmin'], layouts=sorted({s['layout'] for s in scenes if s['layout']})) if track else None)


SOLAR_NAMES = {'vesta': ('4 Vesta', 'main-belt asteroid')}


def track_study(slug, log=print):
    out = OUT / slug
    (out / 'img').mkdir(parents=True, exist_ok=True)
    for old in (out / 'img').glob('*.png'):
        old.unlink()
    built = build_track(slug, out, follow=True, log=log)
    track, path = built['track'], built['path']
    name, kind = SOLAR_NAMES.get(slug, (slug, 'Solar System body'))
    if track:
        name, kind = track.get('object') or name, track.get('body') or kind
    speeds = []
    for a, b in zip(path, path[1:]):
        if a['visit'] == b['visit'] and b['mjd'] > a['mjd']:
            d = math.hypot(((b['ra'] - a['ra'] + 540) % 360 - 180) * math.cos(math.radians(a['dec'])), b['dec'] - a['dec']) * 3600
            speeds.append(d / ((b['mjd'] - a['mjd']) * 24))
    res = [p['residual'] for p in path if p['residual']]
    rms = math.sqrt(np.mean([r[0] ** 2 + r[1] ** 2 for r in res])) if res else None
    speed = round(float(np.median(speeds)), 1) if speeds else None
    if len(res) >= 3:
        good = rms < 12
        verdict = dict(code='as-predicted' if good else 'differs', title='Follows its JPL orbit' if good else 'Off its JPL orbit',
                       summary=f'Across {len(res)} exposures {name} sits {rms:.1f}″ (rms) from where JPL Horizons predicts, about {rms / 6.15:.1f} SPHEREx pixels.'
                               + (f' It crosses {built["scenes"]} fixed-sky scenes of up to {built["tiles"]["layouts"][-1]} tiles.' if built['tiles'] and built['tiles']['layouts'] else ''),
                       rule='Follows its orbit if the rms difference between the measured and JPL-predicted positions is under 12″ (two SPHEREx pixels).',
                       numbers=dict(exposures=len(path), rms_arcsec=round(rms, 2), speed_arcsec_per_hr=speed))
    else:
        verdict = dict(code='as-predicted', title='Moves across the sky',
                       summary=((f'Measured directly in the images, {name} moves about {speed:.0f}″ per hour '
                                 f'({speed * 24 / 60:.1f}′ per day) against the background stars.') if speeds else 'Too few exposures to measure its motion.')
                                + (f' Where a JPL position is available it agrees to {rms:.1f}″ ({rms / 6.15:.1f} SPHEREx pixels).' if rms is not None else ''),
                       rule='Speed from the measured position in consecutive exposures of the same visit. Run scripts/fetch_track.py to add more exposures and JPL predictions.',
                       numbers=dict(exposures=len(path), speed_arcsec_per_hr=speed, rms_arcsec=round(rms, 2) if rms is not None else None))
    tile_note = (f'The fixed-sky view is built from {built["tiles"]["tile_arcmin"]:g}′ sky tiles: one tile while the target is well inside it, '
                 'the neighbour once it nears an edge (four at a corner), growing up to the scene limit before a new scene starts.') if built['tiles'] else \
                'Run scripts/fetch_track.py to download tiled data so the fixed-sky view can follow it across neighbouring tiles.'
    result = dict(field=slug, name=name, kind=kind, expect='track', mode='track',
                  generated_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  grid=dict(size=GRID_SIZE, scale_arcsec=GRID_SCALE, center=None, north='up', east='left'),
                  counts=dict(spherex_frames=len(path), spherex_visits=built['scenes'], wise_frames=0, wise_visits=0),
                  timelapse=built['follow'], sky=built['sky'], tiles=built['tiles'], path=path, verdict=verdict, bands=[], visits=[],
                  differences={}, astrometry=dict(points=[], frames=[], track=[], fits={}), field_stars={},
                  brightness={'tested': False, 'reason': 'Not tested for a Solar System body.'},
                  limits=['Without a JPL position the target is taken to be the brightest source in each exposure.',
                          'Each “follow” image is centred on the measured position, so the background stars stream past.',
                          tile_note,
                          'Different exposures are taken at different wavelengths (SPHEREx sees a different colour at each detector position).'],
                  credits=['SPHEREx spectral images: NASA/JPL-Caltech/IPAC, NASA/IPAC Infrared Science Archive (IRSA).',
                           'Ephemeris (where shown): JPL Horizons, Solar System Dynamics Group.'])
    (out / 'study.json').write_text(json.dumps(result, separators=(',', ':')), encoding='utf-8')
    log(f'{slug}: {len(path)} exposures in {built["scenes"]} scenes · {verdict["title"]}')
    write_index()
    return result


def vesta_study(log=print):
    return track_study('vesta', log)


def attach_sky(field, log=print):
    """Add the tiled fixed-sky view to a star's existing study (only when scripts/fetch_track.py found it crossing tiles)."""
    out = OUT / field
    study_path = out / 'study.json'
    if not load_track(field) or not study_path.is_file():
        return None
    for old in (out / 'img').glob('sky-*.png'):
        old.unlink()
    built = build_track(field, out, follow=False, log=log)
    result = json.loads(study_path.read_text(encoding='utf-8'))
    result['sky'], result['tiles'] = built['sky'], built['tiles']
    study_path.write_text(json.dumps(result, separators=(',', ':')), encoding='utf-8')
    log(f'{field}: fixed-sky tiles added · {len(built["sky"])} exposures in {built["scenes"]} scenes')
    return result


def write_index():
    """List every generated study so the viewer can offer targets beyond the built-in ones."""
    items = []
    for p in sorted(OUT.glob('*/study.json')):
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
            items.append(dict(field=d['field'], name=d['name'], kind=d.get('kind'), mode=d.get('mode', 'motion'),
                              tiled=bool(d.get('tiles'))))
        except (OSError, ValueError, KeyError):
            continue
    (OUT / 'index.json').write_text(json.dumps(dict(studies=items), separators=(',', ':')), encoding='utf-8')


def main(argv):
    sky_only = '--sky-only' in argv
    argv = [a for a in argv if a != '--sky-only']
    fields = argv or list(TARGETS) + ['vesta'] + sorted(p.name for p in TRACKS.glob('*') if (p / 'track.json').is_file()
                                                          and p.name not in TARGETS and p.name != 'vesta')
    for field in fields:
        if field in TARGETS:
            if not sky_only:
                study(field)
            attach_sky(field)
        else:
            track_study(field)
    write_index()


if __name__ == '__main__':
    main(sys.argv[1:])
