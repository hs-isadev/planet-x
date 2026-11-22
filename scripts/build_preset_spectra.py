"""Build plot-ready data from bundled observations and locally available IRSA calibrations."""
import argparse
import json
from pathlib import Path
from time import perf_counter

from backend.observation_lab_core import calibrations, spectroscopy
from backend.observation_lab_core.featured_views import BUNDLE, ROOT, fields, view_entry
from backend.observation_lab_core.server import expected_sky_position


def build(field, products):
    _, entry = view_entry(field['key'], (BUNDLE,))
    if entry is None:
        return
    session = entry['session']
    manifest = json.loads((BUNDLE / session / 'manifest.json').read_text(encoding='utf-8'))
    started = perf_counter()
    points, seen = [], set()
    for frame in manifest['frames']:
        release = frame['release'].split('_')[0].lower()
        detector = frame['detector']
        identity = (frame['id'], detector, release)
        if identity in seen:
            continue
        psf_release = 'dr1' if release == 'dr1' else 'qr3'
        keys = [f'{release}/spectral_wcs/D{detector}', f'{release}/solid_angle_pixel_map/D{detector}',
                f'{psf_release}/epsf/D{detector}']
        if not all(key in products for key in keys):
            continue
        path = BUNDLE / Path(frame['fits_url']).name
        if not path.is_file():
            continue
        seen.add(identity)
        sky = expected_sky_position(field, frame['mjd'])
        measurement = spectroscopy.measurement(dict(frame, path=str(path)), sky)
        measurement['aperture_ra'] = float(sky.ra.deg)
        measurement['aperture_dec'] = float(sky.dec.deg)
        points.append(measurement)
    plotted = [point for point in points if 'flux' in point]
    if len({round(point['wavelength'], 3) for point in plotted}) < 3:
        print(f"{field['key']}: insufficient calibrated wavelength samples ({len(plotted)} points)", flush=True)
        return
    coverage = ', '.join(f'{release.upper()} D{detector}'
                         for release, detector in sorted({(p['release'].split('_')[0], p['detector']) for p in plotted}))
    result = dict(field=field['key'], source_session=session, method=spectroscopy.METHOD,
                  ra=field['ra'], dec=field['dec'], redshift=0, unit='microJy',
                  points=points, candidates=spectroscopy.feature_candidates(points, 0),
                  references=spectroscopy.REFERENCES, coverage=coverage,
                  notes=['Measurements use bundled real SPHEREx observations with complete local calibration products.',
                         'Catalog proper motion is applied where available. Neighboring sources are not jointly fitted.',
                         'Reference bands indicate candidate features only. Observations may come from different dates.'])
    output = ROOT / 'web/assets/spectra'
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f"{field['key']}-{session}.json"
    destination.write_text(json.dumps(result, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    print(f"{field['key']}: {len(plotted)} plot points, {coverage}, {destination.stat().st_size} B, "
          f"{1000*(perf_counter()-started):.0f} ms extraction", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fields', nargs='+')
    parser.add_argument('--calibrations', type=Path, default=calibrations.CACHE)
    args = parser.parse_args()
    calibrations.CACHE = args.calibrations
    index = json.loads((args.calibrations / 'index.json').read_text(encoding='utf-8'))['products']
    products = {key for key, product in index.items()
                if (args.calibrations / f"{product['release']}-{Path(product['url']).name}").is_file()}
    available = {field['key']: field for field in fields()}
    for key in args.fields:
        build(available[key], products)


if __name__ == '__main__':
    main()
