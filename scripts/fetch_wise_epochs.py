"""Rebuild the WISE/NEOWISE supplemental epochs bundle for preset fields.

Discovery (IRSA IBE search) -> cutout download (IRSA IBE) -> validation -> north-up previews -> series.json.
Writes backend/data/supplemental-epochs/<field>/. Real archive pixels only; the target marker is a
catalog proper-motion prediction, never a measurement.

    .venv/Scripts/python.exe -X utf8 scripts/fetch_wise_epochs.py --field wise-0855 --field barnard
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
from io import BytesIO
import json
from pathlib import Path
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backend  # noqa: F401  configures astropy caches before astropy imports
import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.io import ascii, fits
from astropy.time import Time
from astropy.wcs import WCS, FITSFixedWarning
from PIL import Image
from scipy.ndimage import map_coordinates
from backend.observation_lab_core.archive import _irsa
from backend.simbad_client import query_names

warnings.simplefilter('ignore', FITSFixedWarning)
OUT = ROOT / 'backend/data/supplemental-epochs'
IBE = 'https://irsa.ipac.caltech.edu/ibe'
# (release slug, mission, IBE table path). Same telescope and W1/W2 detectors in every phase.
TABLES = [('allsky', 'WISE', 'wise/allsky/4band_p1bm_frm'),
          ('cryo_3band', 'WISE', 'wise/cryo_3band/3band_p1bm_frm'),
          ('postcryo', 'WISE', 'wise/postcryo/2band_p1bm_frm'),
          ('neowiser', 'NEOWISE-R', 'wise/neowiser/p1bm_frm')]
SIMBAD = {'wise-0855': 'WISE J085510.83-071442.5', 'barnard': 'Barnard star', 'epsilon-indi': 'eps Ind B',
          'rw-aur': 'RW Aur', 'r-dra': 'R Dra'}
BANDS = {1: (3.4, 6.1), 2: (4.6, 6.4)}  # wavelength um, PSF FWHM arcsec
SCALE = 2.75  # arcsec/pixel, WISE L1b
SATURATED_BITS = sum(1 << b for b in range(10, 19))  # msk bits 10-18: saturated in sample read 1-9 (Expl. Suppl. IV.4.a)
PER_DATE = {'barnard': 1}  # saturated in every frame: extra exposures add size, not information
AP, ANN = 2.0, (5.0, 9.0)  # aperture / sky annulus radii in native pixels


def preset(key):
    fields = json.loads((ROOT / 'backend/observation_lab_core/data/collection.json').read_text(encoding='utf-8'))['fields']
    field = next(f for f in fields if f['key'] == key)
    return SkyCoord(field['ra'] * u.deg, field['dec'] * u.deg)


def catalog(key):
    table, server = query_names([SIMBAD[key]], ['pmra', 'pmdec', 'plx_value'])
    row = table[0]
    info = dict(name=str(row['main_id']), ra=float(row['ra']), dec=float(row['dec']), pmra_mas_yr=float(row['pmra']),
                pmdec_mas_yr=float(row['pmdec']), parallax_mas=float(row['plx_value']), epoch='J2000',
                source=f'SIMBAD ({server})')
    coord = SkyCoord(info['ra'] * u.deg, info['dec'] * u.deg, pm_ra_cosdec=info['pmra_mas_yr'] * u.mas / u.yr,
                     pm_dec=info['pmdec_mas_yr'] * u.mas / u.yr, obstime=Time('J2000'))
    return info, lambda mjd: coord.apply_space_motion(new_obstime=Time(mjd, format='mjd'))


def discover(center, failures):
    rows = []
    for release, mission, table in TABLES:
        try:
            text = _irsa('GET', f'{IBE}/search/{table}', params={'POS': f'{center.ra.deg},{center.dec.deg}'}, timeout=120).text
            result = ascii.read(text, format='ipac') if 'RowsRetrieved = 0' not in text else []
        except Exception as error:  # record and continue with the other phases
            failures['discovery'].append(f'{table}: {type(error).__name__}: {error}')
            continue
        for r in result:
            if int(r['band']) not in BANDS:
                continue
            scan, frame, band = str(r['scan_id']), int(r['frame_num']), int(r['band'])
            source = f'{IBE}/data/{table}/{r["scangrp"]}/{scan}/{frame:03d}/{scan}{frame:03d}-w{band}-int-1b.fits'
            rows.append(dict(id=f'{release}-{scan}{frame:03d}-w{band}', release=release, mission=mission, band=band,
                             scan_id=scan, frame_num=frame, mjd=float(r['mjd_obs']),
                             date_utc=str(r['date_obs']).replace(' ', 'T')[:19] + 'Z', source_url=source,
                             **{k: None if np.ma.is_masked(r[k]) else cast(r[k]) for k, cast in
                                (('qual_frame', int), ('qual_scan', int), ('moon_sep', float), ('saa_sep', float))}))
    return rows


CACHE = None  # optional --cache folder of raw IRSA responses, so an interrupted run resumes without refetching


def cutout(url, center, size):
    params = {'center': f'{center.ra.deg:.7f},{center.dec.deg:.7f}', 'size': f'{size}arcsec'}
    cached = CACHE and CACHE / (url.split('/data/wise/')[1].split('.fits')[0].replace('/', '_') + f'-{size}.fits.gz')
    if cached and cached.is_file():
        return cached.read_bytes()
    data = _irsa('GET', url, attempts=5, params=params, timeout=120).content
    data = data if data[:2] == b'\x1f\x8b' else gzip.compress(data)
    fits.open(BytesIO(gzip.decompress(data)))[0].header  # raises on an HTML error page or truncated body
    if cached:
        cached.write_bytes(data)
    return data


def measure(row, center, size, predict):
    """Download one cutout and its mask; return (row with quality, native HDU, mask) or raise ValueError(stage: reason)."""
    try:
        raw = cutout(row['source_url'], center, size)
        msk = cutout(row['source_url'].replace('-int-1b.fits', '-msk-1b.fits.gz'), center, size)
        hdu = fits.open(BytesIO(gzip.decompress(raw)))[0]
        mask = fits.open(BytesIO(gzip.decompress(msk)))[0].data.astype(np.int64)
    except Exception as error:
        raise ValueError(f'download: {type(error).__name__}: {str(error)[:120]}') from None
    image, wcs = hdu.data.astype(float), WCS(hdu.header)
    if not wcs.has_celestial or image.ndim != 2 or mask.shape != image.shape:
        raise ValueError('coverage: missing celestial WCS or mask shape mismatch')
    x, y = wcs.world_to_pixel(predict(row['mjd']))
    ny, nx = image.shape
    if not (4 <= x <= nx - 5 and 4 <= y <= ny - 5):
        raise ValueError(f'coverage: predicted target at pixel ({x:.0f},{y:.0f}) outside {nx}x{ny} cutout (frame edge)')
    finite = np.isfinite(image).mean()
    if finite < .8:
        raise ValueError(f'coverage: only {finite:.0%} finite pixels')
    yy, xx = np.mgrid[:ny, :nx]
    r = np.hypot(xx - x, yy - y)
    ap, ann = r <= AP, (r >= ANN[0]) & (r <= ANN[1]) & np.isfinite(image)
    sky = np.median(image[ann])
    sigma = 1.4826 * np.median(np.abs(image[ann] - sky))
    snr = float(np.nansum(image[ap] - sky) / (sigma * np.sqrt(ap.sum() * (1 + ap.sum() / ann.sum()))))
    saturated = bool((mask[r <= AP] & SATURATED_BITS).any())
    row = dict(row, quality=dict(qual_frame=row.pop('qual_frame'), qual_scan=row.pop('qual_scan'),
                                 moon_sep=row.pop('moon_sep'), saa_sep=row.pop('saa_sep'),
                                 target_finite=bool(np.isfinite(image[ap]).all()),
                                 target_saturated=saturated,  # a saturated core makes aperture SNR meaningless
                                 snr_at_target=round(snr, 2) if np.isfinite(snr) and not saturated else None,
                                 finite_fraction=round(float(finite), 3)))
    return row, raw, hdu, mask


def resample(hdu, mask, grid, n):
    """North-up, east-left resampling onto the shared preset grid (bilinear; mask nearest)."""
    yy, xx = np.mgrid[:n, :n]
    sx, sy = WCS(hdu.header).world_to_pixel(grid.pixel_to_world(xx, yy))
    image = map_coordinates(hdu.data.astype(float), [sy, sx], order=1, cval=np.nan)
    saturated = map_coordinates(mask & SATURATED_BITS, [sy, sx], order=0, cval=0) > 0
    return image, saturated


def build(key, per_date, margin):
    center = preset(key)
    star, predict = catalog(key)
    failures = dict(discovery=[], download=[], coverage=[])
    rows = discover(center, failures)
    if not rows:
        raise SystemExit(f'{key}: no WISE frames discovered: {failures}')
    mjds = np.array([r['mjd'] for r in rows])
    offset = max(center.separation(predict(m)).arcsec for m in (mjds.min(), mjds.max()))
    size = int(min(600, max(240, np.ceil(2 * (offset + margin) / 30) * 30)))
    groups = {}
    for r in sorted(rows, key=lambda r: (-(r['qual_frame'] or 0), -(r['moon_sep'] or 0))):
        groups.setdefault((r['mission'], r['band'], r['date_utc'][:10]), []).append(r)

    def run(candidates):
        done = []
        for row in candidates[:per_date + 2]:  # a couple of spares if an exposure fails coverage
            try:
                done.append(measure(dict(row), center, size, predict))
            except ValueError as error:
                stage, reason = str(error).split(': ', 1)
                failures[stage].append(f"{row['id']}: {reason}")
            if len(done) == per_date:
                break
        return done

    with ThreadPoolExecutor(3) as pool:  # polite: at most 3 concurrent IRSA requests
        results = dict(zip(groups, pool.map(run, groups.values())))
    attempted = sum(len(v) for v in results.values()) + len(failures['download']) + len(failures['coverage'])
    downloaded = attempted - len(failures['download'])

    folder = OUT / key
    folder.mkdir(parents=True, exist_ok=True)
    n = int(round(size / SCALE))
    grid = WCS(naxis=2)
    grid.wcs.ctype, grid.wcs.crval = ['RA---TAN', 'DEC--TAN'], [center.ra.deg, center.dec.deg]
    grid.wcs.crpix, grid.wcs.cdelt = [(n + 1) / 2, (n + 1) / 2], [-SCALE / 3600, SCALE / 3600]
    series, written = [], {'series.json'}
    for mission in ('WISE', 'NEOWISE-R'):
        for band in BANDS:
            dates = sorted((d, v) for (m, b, d), v in results.items() if m == mission and b == band and v)
            if not dates:
                continue
            frames, extra, pixels = [], [], []
            for _, done in dates:
                done.sort(key=lambda d: (-(d[0]['quality']['qual_frame'] or 0), d[0]['quality']['target_saturated'],
                                         not d[0]['quality']['target_finite'], -(d[0]['quality']['snr_at_target'] or -99)))
                for rank, (row, raw, hdu, mask) in enumerate(done):
                    image, saturated = resample(hdu, mask, grid, n)
                    sky = np.nanmedian(image)
                    pixels.append((row, raw, image - sky, saturated, rank == 0))
            # One display stretch for the whole series: per-frame median sky removed, shared limits.
            noise = np.median([1.4826 * np.nanmedian(np.abs(p[2])) for p in pixels])
            high = np.median([np.nanpercentile(p[2], 99.7) for p in pixels])
            for row, raw, image, saturated, default in pixels:
                stem = row['id']
                (folder / f'{stem}.fits.gz').write_bytes(raw)
                level = np.clip((image + 2 * noise) / (high + 2 * noise), 0, 1)
                level = np.arcsinh(10 * level) / np.arcsinh(10)
                level = np.where(np.isfinite(image), level, np.where(saturated, 1.0, 0.0))
                Image.fromarray((np.flipud(level) * 255).astype('uint8')).save(folder / f'{stem}.png', optimize=True)
                written |= {f'{stem}.fits.gz', f'{stem}.png'}
                tx, ty = grid.world_to_pixel(predict(row['mjd']))
                inside = 0 <= tx + .5 <= n and 0 <= ty + .5 <= n
                frame = dict(id=stem, mission=row['mission'], date_utc=row['date_utc'], mjd=round(row['mjd'], 6),
                             epoch_start=None, epoch_end=None,
                             preview=f'/observation-lab/supplemental/{key}/{stem}.png',
                             fits=f'/observation-lab/supplemental/{key}/{stem}.fits.gz',
                             source_url=row['source_url'], release=row['release'], scan_id=row['scan_id'],
                             frame_num=row['frame_num'], quality=row['quality'],
                             expected_target_xy=[round((float(tx) + .5) / n, 4), round(1 - (float(ty) + .5) / n, 4)] if inside else None)
                (frames if default else extra).append(frame)
            frames.sort(key=lambda f: f['mjd'])
            extra.sort(key=lambda f: f['mjd'])
            wavelength, fwhm = BANDS[band]
            sat = sum(f['quality']['target_saturated'] for f in frames)
            snrs = [f['quality']['snr_at_target'] for f in frames if f['quality']['snr_at_target'] is not None]
            notes = [f'Different telescope, PSF (~{fwhm}") and band than SPHEREx; not directly comparable pixel-for-pixel.',
                     'Previews are resampled north-up/east-left onto one grid centred on the preset field; FITS are the native '
                     'IRSA Level 1b cutouts (detector orientation, original WCS).',
                     "Every preview uses the same display stretch after subtracting that frame's median sky. "
                     'Unmeasurable (NaN) pixels flagged saturated are drawn white, other NaN pixels black.',
                     f"Target marker is predicted from catalog proper motion ({star['source']}, J2000); parallax "
                     f"({star['parallax_mas']:.0f} mas) ignored. Prediction only, not a measured position.",
                     f'Target aperture ({AP:.0f} px radius) SNR in default frames: median {np.median(snrs):.1f}, '
                     f'range {min(snrs):.1f}-{max(snrs):.1f}; saturated at target in {sat}/{len(frames)}.' if snrs else
                     f'Target saturated (msk bits 10-18 within {AP:.0f} px) in {sat}/{len(frames)} default frames; '
                     'aperture SNR not meaningful.']
            if mission == 'WISE':
                notes.append('2010 WISE cryogenic/post-cryogenic phases; same telescope and detectors as NEOWISE-R.')
            series.append(dict(id=f"{'neowise' if mission == 'NEOWISE-R' else 'wise'}-w{band}", mission=mission,
                               product='Level 1b single exposure', band=f'W{band}', wavelength_um=wavelength,
                               pixel_scale_arcsec=SCALE, distinct_dates=len(frames),
                               first_date=frames[0]['date_utc'][:10], last_date=frames[-1]['date_utc'][:10],
                               notes=notes, frames=frames, extra=extra))
    for stale in folder.iterdir():
        if stale.name not in written:
            stale.unlink()
    valid = sum(len(s['frames']) + len(s['extra']) for s in series)
    payload = dict(field=key, generated_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                   center=dict(ra=center.ra.deg, dec=center.dec.deg), cutout_arcsec=size, catalog=star, series=series,
                   discovery=dict(matched=len(rows), attempted=attempted, downloaded=downloaded, valid=valid,
                                  per_date_limit=per_date, failures=failures,
                                  method='IRSA IBE search POS=<preset centre> over WISE all-sky, 3-band, post-cryo and '
                                         'NEOWISE-R L1b frame tables; up to per_date_limit best-quality exposures '
                                         'downloaded per band and UTC date.'))
    (folder / 'series.json').write_text(json.dumps(payload, indent=1, allow_nan=False), encoding='utf-8')
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--field', action='append', required=True, choices=sorted(SIMBAD))
    parser.add_argument('--per-date', type=int, help='exposures kept per band and UTC date (1 default + extras; default 2, barnard 1)')
    parser.add_argument('--margin', type=float, default=45, help='arcsec kept around the predicted track')
    parser.add_argument('--cache', type=Path, help='folder for raw IRSA cutouts (resume without refetching)')
    args = parser.parse_args()
    if args.cache:
        args.cache.mkdir(parents=True, exist_ok=True)
        CACHE = args.cache
    for key in args.field:
        p = build(key, args.per_date or PER_DATE.get(key, 2), args.margin)
        d = p['discovery']
        print(key, f"cutout {p['cutout_arcsec']}\"", {k: d[k] for k in ('matched', 'attempted', 'downloaded', 'valid')},
              {k: len(v) for k, v in d['failures'].items()}, flush=True)
        for s in p['series']:
            print(' ', s['id'], s['distinct_dates'], 'dates', s['first_date'], '->', s['last_date'], 'extra', len(s['extra']),
                  '|', s['notes'][4], flush=True)
