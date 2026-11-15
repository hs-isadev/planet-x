"""Native detector inspection and external ephemerides for loaded SPHEREx frames."""
import csv
import io
import math
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor

import httpx
import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from PIL import Image

from .analysis import sky_at_click, wavelength_map
from .archive import CACHE, CONFIG, output_grid
from .time_science import native_centroid, projected

# SPHEREx Explanatory Supplement, Level 2 pixel flag table.
FLAG_NAMES = {
    0: 'TRANSIENT', 1: 'OVERFLOW', 2: 'SUR_ERROR', 6: 'NONFUNC',
    7: 'DICHROIC', 9: 'MISSING_DATA', 10: 'HOT', 11: 'COLD',
    12: 'FULLSAMPLE', 14: 'PHANMISS', 15: 'NONLINEAR', 17: 'PERSIST',
    19: 'OUTLIER', 20: 'CROSSTALK', 21: 'SOURCE', 22: 'GHOST',
    23: 'GHOST_FPA', 24: 'GHOST_EXT', 25: 'STREAK', 26: 'BLOOM',
    27: 'SNOWBALL', 28: 'HALO', 29: 'SATELLITE_HALO',
}
HORIZONS_URL = 'https://ssd.jpl.nasa.gov/api/horizons.api'
SPACECRAFT = '500@-163182'
GEOCENTER = '500@399'
TRACK_LIMIT = 72


def native_path(frame):
    path = CACHE/(frame['cache_id']+'.fits')
    if not path.is_file():
        raise FileNotFoundError('Native FITS is no longer in the cache. Reload the exposure to inspect detector pixels.')
    return path


def finite(value):
    return float(value) if np.isfinite(value) else None


def inspect_pixel(field, frame, x, y):
    sky = sky_at_click(field, x, y)
    with fits.open(native_path(frame), memmap=False) as hdus:
        image = hdus['IMAGE']
        dx, dy = map(float, WCS(image.header).celestial.world_to_pixel(sky))
        result = dict(ra=float(sky.ra.deg), dec=float(sky.dec.deg), exposure_id=frame['id'])
        if not (math.isfinite(dx) and math.isfinite(dy)):
            return dict(result, inside=False)
        px, py = math.floor(dx+.5), math.floor(dy+.5)
        if not (0 <= px < image.shape[1] and 0 <= py < image.shape[0]):
            return dict(result, inside=False)
        flags = int(hdus['FLAGS'].data[py, px])
        value = finite(image.data[py, px])
        variance = finite(hdus['VARIANCE'].data[py, px])
        wave = wavelength_map(hdus, np.array([px]), np.array([py]))[0]
        names = [FLAG_NAMES.get(bit, f'BIT_{bit}') for bit in range(32) if flags & (1 << bit)]
        return dict(result, inside=True, pixel_x=px, pixel_y=py, value=value,
                    sigma=math.sqrt(variance) if variance is not None and variance > 0 else None,
                    unit=image.header.get('BUNIT', frame.get('unit', 'MJy/sr')),
                    wavelength_um=finite(wave), flags=flags, flag_names=names,
                    usable=flags in CONFIG['accepted_pixel_flags'] and value is not None
                           and variance is not None and variance > 0)


def render_flag_mask(field, frame):
    out, size, _ = output_grid(field['ra'], field['dec'], field['fov'])
    yy, xx = np.mgrid[:size, :size]
    with fits.open(native_path(frame), memmap=False) as hdus:
        flags = hdus['FLAGS'].data
        source = WCS(hdus['IMAGE'].header).celestial
        x, y = source.world_to_pixel_values(*out.pixel_to_world_values(xx, yy))
        x = np.floor(np.nan_to_num(x, nan=-1, posinf=-1, neginf=-1)+.5)
        y = np.floor(np.nan_to_num(y, nan=-1, posinf=-1, neginf=-1)+.5)
        inside = (x>=0)&(x<flags.shape[1])&(y>=0)&(y<flags.shape[0])
        native = flags[y.clip(0, flags.shape[0]-1).astype(int), x.clip(0, flags.shape[1]-1).astype(int)]
        mask = inside & ~np.isin(native, CONFIG['accepted_pixel_flags'])
    rgba = np.zeros((size, size, 4), dtype=np.uint8)
    rgba[mask] = (245, 74, 100, 150)
    output = io.BytesIO()
    Image.fromarray(rgba[::-1]).save(output, format='PNG')
    return output.getvalue()


def observation_time(frame):
    file = CACHE/(frame['cache_id']+'.fits')
    if file.is_file():
        try:
            with fits.open(file, memmap=False) as hdus:
                for header in (hdus['IMAGE'].header, hdus[0].header):
                    if 'MJD-AVG' in header:
                        scale = str(header.get('TIMESYS', 'UTC')).lower()
                        return float(Time(header['MJD-AVG'], format='mjd', scale=scale).utc.mjd), 'midpoint'
        except (OSError, ValueError, KeyError):
            pass
    return float(frame['mjd']), 'archive timestamp'


@lru_cache(maxsize=64)
def horizons_positions(command, center, dates):
    params = dict(COMMAND=command, CENTER=center, MAKE_EPHEM='YES', EPHEM_TYPE='OBSERVER',
                  TIME_TYPE='UT', TLIST_TYPE='MJD', QUANTITIES='1', ANG_FORMAT='DEG',
                  CAL_FORMAT='JD', CSV_FORMAT='YES', EXTRA_PREC='YES')
    query = {key: f"'{value}'" for key, value in params.items()}
    query.update(format='json', TLIST=' '.join(f"'{date:.8f}'" for date in dates))
    response = httpx.get(HORIZONS_URL, params=query, timeout=httpx.Timeout(9, connect=4))
    response.raise_for_status()
    body = response.json()
    table = body.get('result', '')
    name = next((line.split(':', 1)[1].split('{')[0].strip() for line in table.splitlines()
                 if line.startswith('Target body name:')), command)
    if '$$SOE' not in table or '$$EOE' not in table:
        message = str(body.get('error') or table).lower()
        if 'multiple' in message or 'matches' in message:
            raise ValueError('Horizons found multiple targets. Use an asteroid number or comet designation.')
        if 'cannot find' in message or 'no matches' in message:
            raise ValueError('Horizons could not identify that object. Try its asteroid number or comet designation.')
        return name, None
    rows = list(csv.reader(table.split('$$SOE',1)[1].split('$$EOE',1)[0].strip().splitlines()))
    parsed = [(float(row[0])-2400000.5, float(row[3]), float(row[4]))
              for row in rows if len(row)>4 and row[3].strip() and row[4].strip()]
    values = tuple(next(((ra,dec) for epoch,ra,dec in parsed if abs(epoch-date)<1e-6),None)
                   for date in dates)
    return name, values if any(values) else None


def moving_track(field, frames, designation):
    designation = designation.strip()
    if not designation or not all(c.isascii() and (c.isalnum() or c in ' /-._()') for c in designation):
        raise ValueError('Enter an asteroid number, asteroid name or comet designation.')
    if designation.isdecimal():
        command = designation+';'
    elif designation.upper().split('/')[0].endswith('P') and designation.upper().split('/')[0][:-1].isdigit():
        command = 'DES='+designation.upper().split('/')[0]+';CAP;NOFRAG'
    else:
        command = designation
    count = len(frames)
    if count > TRACK_LIMIT:
        frames = [frames[int(i)] for i in np.linspace(0, count-1, TRACK_LIMIT)]
    epochs = [(frame, *observation_time(frame)) for frame in frames]
    dates = tuple(sorted({round(date, 8) for _, date, _ in epochs}))
    name, values = horizons_positions(command, SPACECRAFT, dates)
    center = SPACECRAFT
    if values is None or any(point is None for point in values):
        center = GEOCENTER
        name, values = horizons_positions(command, center, dates)
    if not values:
        raise ValueError('Horizons returned no positions for these exposures.')
    coordinates = dict(zip(dates, values))
    rows = measure_track(field, epochs, lambda date: coordinates[round(date, 8)])
    return dict(name=name, observer='SPHEREx spacecraft' if center==SPACECRAFT else 'Earth geocenter',
                observer_code=center, source=HORIZONS_URL, available=count, evaluated=len(rows), points=rows)


def measure_track(field, epochs, locate):
    rows = []
    for frame, date, method in epochs:
        pair = locate(date)
        row = dict(exposure_id=frame['id'], date=frame['date'], mjd_utc=date, time_source=method,
                   prediction=None, measured=None, offset_arcsec=None, status='missing prediction')
        rows.append(row)
        if pair is None:
            continue
        sky = SkyCoord(*pair, unit='deg')
        pixel = projected(field, sky)
        if not all(math.isfinite(v) for v in pixel.values()) or not all(0 <= v <= 1 for v in pixel.values()):
            row.update(status='outside field', prediction=dict(ra=pair[0], dec=pair[1]))
            continue
        row.update(prediction=dict(ra=pair[0], dec=pair[1], **pixel), status='prediction only')
        try:
            measured = track_centroid(native_path(frame), field, sky)
        except (OSError, ValueError, KeyError, np.linalg.LinAlgError) as exc:
            row['measurement_note'] = str(exc)
            continue
        measured_sky = SkyCoord(measured['ra'], measured['dec'], unit='deg')
        offset = float(sky.separation(measured_sky).arcsec)
        row.update(measured=measured, offset_arcsec=offset, status='measured',
                   agreement=offset <= max(3.075, 3*measured['centroid_error_arcsec']))
    previous = None
    for row in sorted(rows, key=lambda p:p['mjd_utc']):
        if not row['measured']:
            continue
        point = SkyCoord(row['measured']['ra'],row['measured']['dec'],unit='deg')
        if previous:
            previous_point, previous_row = previous
            hours = (row['mjd_utc']-previous_row['mjd_utc'])*24
            if hours>0:
                shift = float(previous_point.separation(point).arcsec)
                row['motion'] = dict(from_exposure_id=previous_row['exposure_id'],hours=hours,
                                     displacement_arcsec=shift, speed_arcsec_per_hour=shift/hours,
                                     position_angle_deg=float(previous_point.position_angle(point).deg),
                                     nominal_shift_error_arcsec=math.hypot(previous_row['measured']['centroid_error_arcsec'],
                                                                          row['measured']['centroid_error_arcsec']))
        previous = point,row
    return rows


def clicked_track(field, frames, marks):
    by_id = {f['id']: f for f in field['frames'] if f['status']=='ready'}
    if any(m.frame_id not in by_id for m in marks):
        raise ValueError('A marked exposure is unavailable. Clear and mark the source again.')
    seeds = sorted(((observation_time(by_id[m.frame_id])[0], sky_at_click(field, m.x, m.y))
                    for m in marks), key=lambda seed: seed[0])
    first, start = seeds[0]
    last, end = seeds[-1]
    if len(seeds)>1 and first==last:
        raise ValueError('Pick anchors from two different observation times.')
    east, north = start.spherical_offsets_to(end)
    epochs = [(frame,*observation_time(frame)) for frame in frames]
    if len(seeds)>1:
        epochs = [e for e in epochs if first <= e[1] <= last]
    count = len(epochs)
    if count > TRACK_LIMIT:
        epochs = [epochs[int(i)] for i in np.linspace(0, count-1, TRACK_LIMIT)]

    def locate(date):
        fraction = (date-first)/(last-first) if last!=first else 0
        sky = start.spherical_offsets_by(fraction*east, fraction*north)
        return float(sky.ra.deg),float(sky.dec.deg)

    rows = measure_track(field, epochs, locate)
    return dict(name='Clicked source', observer='Two-click guide' if last!=first else 'Fixed sky search guide',
                source='Clicked SPHEREx frames', available=count, evaluated=len(rows), points=rows)


def skybot_matches(sky, mjd):
    response = httpx.get('https://ssp.imcce.fr/webservices/skybot/api/conesearch.php',
                        params={'-ep':f'{mjd+2400000.5:.7f}', '-ra':f'{sky.ra.deg:.7f}',
                                '-dec':f'{sky.dec.deg:.7f}', '-rd':'0.01', '-mime':'json',
                                '-output':'object', '-loc':'500', '-from':'planet-x'},
                        timeout=httpx.Timeout(11,connect=4))
    response.raise_for_status()
    rows = response.json() if response.text.strip() else []
    if not isinstance(rows,list):
        raise ValueError('Unexpected SkyBoT response')
    matches = []
    for row in rows:
        name = str(row.get('Name','')).strip()
        number = str(row.get('Num','')).strip()
        if name:
            matches.append(dict(name=name, kind='Solar System object', source='IMCCE SkyBoT (geocenter)',
                                separation_arcsec=float(row['d (arcsec)']),
                                designation=number if number.isdecimal() else name))
    return matches


def simbad_matches(sky, mjd):
    ra, dec = sky.ra.deg, sky.dec.deg
    cone = f"CIRCLE('ICRS',{ra:.7f},{dec:.7f},"
    query = ("SELECT TOP 500 main_id,ra,dec,pmra,pmdec,otype FROM basic "
             f"WHERE 1=CONTAINS(POINT('ICRS',ra,dec),{cone}0.10)) "
             f"AND (1=CONTAINS(POINT('ICRS',ra,dec),{cone}0.01)) OR pmra*pmra+pmdec*pmdec>90000)")
    response = httpx.get('https://simbad.harvard.edu/simbad/sim-tap/sync',
                        params={'request':'doQuery','lang':'adql','format':'json','query':query},
                        timeout=httpx.Timeout(9,connect=4))
    response.raise_for_status()
    matches = []
    years = (mjd-51544.5)/365.25
    for name, lon, lat, pmra, pmdec, kind in response.json()['data']:
        if lon is None or lat is None or str(kind).startswith('Pl'):
            continue
        ref = SkyCoord(lon,lat,unit='deg')
        pos = ref.spherical_offsets_by((pmra or 0)*years*u.mas,(pmdec or 0)*years*u.mas)
        matches.append(dict(name=' '.join(name.split()), kind=kind, source='SIMBAD',
                            separation_arcsec=float(pos.separation(sky).arcsec), designation=None))
    return matches


def identify_click(field, frame, x, y):
    sky = sky_at_click(field,x,y)
    centered = False
    try:
        found = track_centroid(native_path(frame), field, sky)
        sky = SkyCoord(found['ra'],found['dec'],unit='deg')
        centered = True
    except (OSError, ValueError, KeyError,np.linalg.LinAlgError):
        pass
    mjd, origin = observation_time(frame)
    threshold = 6.15 if centered else 12.3
    matches, unavailable = [], []
    with ThreadPoolExecutor(2) as pool:
        lookup = {name: pool.submit(fn,sky,mjd) for name,fn in
                  [('SkyBoT',skybot_matches),('SIMBAD',simbad_matches)]}
        for name, task in lookup.items():
            try:
                matches.extend(task.result())
            except (httpx.HTTPError,ValueError,TypeError,KeyError):
                unavailable.append(name)
    nearby = sorted((p for p in matches if p['separation_arcsec']<=threshold),
                    key=lambda p:p['separation_arcsec'])
    return dict(matches=nearby[:4], unavailable=unavailable, centroided=centered,
                tolerance_arcsec=threshold, time_source=origin)


def epsf_measure(hdus, frame, position, calibration):
    """Forced flux at a fixed coordinate using released Level 2 calibration files."""
    from scipy.ndimage import map_coordinates
    from .calibrated_comparison import calibration_file, calibration_key, detector_offsets

    image = hdus['IMAGE']
    wcs = WCS(image.header).celestial
    x, y = map(float, wcs.world_to_pixel(position))
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError('Selected position is outside this detector.')
    ix, iy = math.floor(x+.5), math.floor(y+.5)
    half = 7
    if not (half <= ix < image.shape[1]-half and half <= iy < image.shape[0]-half):
        raise ValueError('Source or background region crosses an image edge.')
    x0, y0 = map(int, detector_offsets(image.header))
    if min(ix+x0, iy+y0)<half or max(ix+x0, iy+y0)>=2040-half:
        raise ValueError('Source or background region crosses a detector edge.')
    window = np.s_[iy-half:iy+half+1, ix-half:ix+half+1]
    det_window = np.s_[iy+y0-half:iy+y0+half+1, ix+x0-half:ix+x0+half+1]
    epoch, det = frame['release'], frame['detector']
    if int(image.header['DETECTOR']) != det:
        raise ValueError('FITS detector and observation record disagree.')
    products = {}
    for kind in ('spectral_wcs','solid_angle_pixel_map','epsf'):
        products[kind] = calibration[kind] if kind in calibration else calibration_file(calibration_key(epoch,det,kind))
        calibration[kind] = products[kind]

    with fits.open(products['spectral_wcs'][0]) as spectral:
        wave = float(spectral['CWAVE'].section[iy+y0,ix+x0])
        band = float(spectral['CBAND'].section[iy+y0,ix+x0])
    if not (math.isfinite(wave) and wave>0 and math.isfinite(band) and band>0):
        raise ValueError('Released wavelength and bandpass are unavailable here.')
    with fits.open(products['solid_angle_pixel_map'][0]) as area_file:
        area_hdu = area_file['IMAGE']
        if area_hdu.header.get('BUNIT','').strip() != 'arcsec2':
            raise ValueError('Unexpected units in the solid-angle calibration.')
        conversion = np.asarray(area_hdu.section[det_window], dtype=float)*u.arcsec.to(u.rad)**2*1e12

    yy, xx = np.mgrid[iy-half:iy+half+1, ix-half:ix+half+1]
    with fits.open(products['epsf'][0]) as psf:
        hdu = psf['EPSF']
        zones = np.hypot(hdu.data['XCENTER']-x-x0, hdu.data['YCENTER']-y-y0)
        zone = int(np.argmin(zones))
        row = hdu.data[zone]
        if zones[zone] > np.hypot(row['XWIDTH'],row['YWIDTH'])/2 or int(row['NSTAR'])<3:
            raise ValueError('Released ePSF has no supported zone here.')
        template = np.asarray(row['EPSF'],dtype=float)
        if template.ndim != 2 or not np.isfinite(template).all():
            raise ValueError('Invalid released ePSF profile.')
        profile = map_coordinates(template, [
            (template.shape[0]-1)/2 + float(hdu.header['OVSMPY'])*(yy-y),
            (template.shape[1]-1)/2 + float(hdu.header['OVSMPX'])*(xx-x)
        ], order=1, mode='constant', cval=0)
    profile = np.maximum(profile,0)
    if profile.sum()<=0:
        raise ValueError('Released ePSF has no sampled support.')
    profile /= profile.sum()
    factor = u.Unit(image.header['BUNIT']).to(u.MJy/u.sr)
    data = np.asarray(image.section[window],dtype=float)*factor
    variance = np.asarray(hdus['VARIANCE'].section[window],dtype=float)*factor**2
    flags = hdus['FLAGS'].data[window]
    radial = np.hypot(xx-x, yy-y)
    usable = (np.isfinite(data)&np.isfinite(variance)&(variance>0)&np.isfinite(conversion)
              &(conversion>0)&np.isin(flags, CONFIG['accepted_pixel_flags']))
    bg = usable&(radial>=4.5)&(radial<=7)&((flags&(1<<21))==0)
    fit = usable&(radial<=3)
    fraction = float(np.sum(profile[fit]))
    if bg.sum()<15 or fit.sum()<8 or fraction<.85:
        raise ValueError('Unflagged ePSF or background coverage is insufficient.')
    background = float(np.median(data[bg]))
    scatter = float(1.4826*np.median(np.abs(data[bg]-background)))
    sigma_background_sq = np.pi/2*max(scatter**2,float(np.median(variance[bg])))/int(bg.sum())
    signal = (data[fit]-background)*conversion[fit]
    variances = variance[fit]*conversion[fit]**2
    shape = profile[fit]
    weight = shape/variances
    denom = float(np.dot(weight,shape))
    flux = float(np.dot(weight,signal)/denom)
    error = math.sqrt(1/denom+sigma_background_sq*(float(np.dot(weight,conversion[fit]))/denom)**2)
    chi = float(np.sum((signal-flux*shape)**2/variances)/max(1,len(shape)-1))
    return dict(status='ok' if chi<=3 and fraction>=.98 else 'review', flux_ujy=flux, error_ujy=error,
                wavelength_um=wave, passband_low_um=wave-band/2, passband_high_um=wave+band/2,
                valid_fraction=fraction, reduced_chi2=chi, epsf_zone=zone,
                wavelength_calibration='released CWAVE/CBAND',
                calibration_url=products['spectral_wcs'][1],
                calibration_products={kind: path[1] for kind,path in products.items()},
                reason=None if chi<=3 and fraction>=.98 else 'Low ePSF coverage or poor fit; shown for review only.')


def track_centroid(path, field, sky):
    try:
        measured = native_centroid(path, field, sky)
        return measured
    except ValueError as exc:
        try:
            return wing_centroid(path,field,sky)
        except ValueError:
            raise exc from None


def wing_centroid(path, field, sky):
    from scipy.optimize import least_squares
    with fits.open(path,memmap=False) as hdus:
        image = hdus['IMAGE']
        wcs = WCS(image.header).celestial
        x, y = map(float,wcs.world_to_pixel(sky))
        ix, iy = math.floor(x+.5), math.floor(y+.5)
        if not (8<=ix<image.shape[1]-8 and 8<=iy<image.shape[0]-8):
            raise ValueError('Insufficient detector coverage.')
        sl = np.s_[iy-8:iy+9,ix-8:ix+9]
        b = np.asarray(image.data[sl],dtype=float)
        var = np.asarray(hdus['VARIANCE'].data[sl],dtype=float)
        flags = hdus['FLAGS'].data[sl].astype(np.uint32)
    dy,dx = np.mgrid[iy-8:iy+9,ix-8:ix+9]
    dx,dy = dx-x,dy-y
    rr = np.hypot(dx,dy)
    # A wing fit is reserved for a flagged core. Unflagged faint sources must pass the native fit.
    if not np.any((rr<2.2)&((flags&np.uint32((1<<0)|(1<<1)|(1<<6)|(1<<26)))!=0)):
        raise ValueError('No flagged core to justify a wing fit.')
    usable = np.isin(flags,CONFIG['accepted_pixel_flags'])&np.isfinite(b)&np.isfinite(var)&(var>0)
    background = usable&(rr>=6.5)
    fit_mask = usable&(rr<6)
    if background.sum()<14 or fit_mask.sum()<20:
        raise ValueError('Too few clean wing or background pixels.')
    baseline = np.median(b[background])
    empirical = max(.02,1.4826*np.median(np.abs(b[background]-baseline)))
    px,py,z = dx[fit_mask],dy[fit_mask],b[fit_mask]
    peak = float(np.max(z-baseline))
    if peak<7*empirical:
        raise ValueError('No bright wing signal.')
    # A separate fractional model error guards against overconfident Gaussian wing fits.
    sigma = np.sqrt(np.maximum(var[fit_mask],empirical**2)+(.13*np.maximum(z-baseline,0))**2)
    weights=np.maximum(z-baseline-3*empirical,0)
    seed_x,seed_y = np.clip([np.average(px,weights=weights),np.average(py,weights=weights)],-1.5,1.5)

    def residual(p):
        amplitude, cx, cy, width, level = p
        profile = np.exp(-((px-cx)**2+(py-cy)**2)/(2*width**2))
        return (level+amplitude*profile-z)/sigma

    result = least_squares(residual,[peak*2,seed_x,seed_y,1.5,baseline],
                           bounds=([0,-2.5,-2.5,.65,-np.inf],[np.inf,2.5,2.5,4,np.inf]),
                           loss='soft_l1',f_scale=1.5,max_nfev=180)
    amp,cx,cy,width,level = result.x
    coverage = sum(np.any(((px-cx)*a>0)&((py-cy)*b>0)&(z-level>3*empirical))
                   for a in (-1,1) for b in (-1,1))
    chi = float(np.dot(result.fun,result.fun)/max(1,len(z)-5))
    if not result.success or coverage<3 or max(abs(cx),abs(cy))>2.35 or width>3.8 or chi>22:
        raise ValueError('Wing fit is too weak or asymmetric to report a position.')
    cov = np.linalg.pinv(result.jac.T@result.jac)*max(1,chi)
    fit_sky = wcs.pixel_to_world(x+cx,y+cy)
    scale = float(np.sqrt(abs(np.linalg.det(wcs.pixel_scale_matrix)))*3600)
    return dict(ra=float(fit_sky.ra.deg),dec=float(fit_sky.dec.deg),**projected(field,fit_sky),
                centroid_error_arcsec=max(.8,scale*math.sqrt(max(0,cov[1,1],cov[2,2]))),reduced_chi2=chi,
                method='Robust Gaussian fit to clean native PSF wings around a flagged core.')
