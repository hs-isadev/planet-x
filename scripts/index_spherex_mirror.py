"""Build an offline discovery index from locally saved SPHEREx mirror originals."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.archive import ROOT, atomic_json
from backend.cloud import mirror_key
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS

ORIGIN = 'https://irsa.ipac.caltech.edu/ibe/data/spherex/'
INDEX = ROOT / 'backend/data/mirror-footprints.json'


def footprint(root, path):
    key = path.relative_to(root).as_posix()
    if mirror_key(ORIGIN + key) is None:
        return None
    with fits.open(path, memmap=True) as hdus:
        header = hdus['IMAGE'].header
        wcs = WCS(header).celestial
        xmax, ymax = header['NAXIS1'] - .5, header['NAXIS2'] - .5
        cx, cy = (xmax - .5) / 2, (ymax - .5) / 2
        center = wcs.pixel_to_world(cx, cy)
        edge = wcs.pixel_to_world([-.5, cx, xmax, xmax, xmax, cx, -.5, -.5],
                                  [-.5, -.5, -.5, cy, ymax, ymax, ymax, cy])
        radius = float(center.separation(edge).deg.max()) + .005
        mjd = float(Time(header['DATE-OBS'], scale='utc').mjd)
        return [key, round(mjd, 8), round(float(center.ra.deg), 7),
                round(float(center.dec.deg), 7), round(radius, 7)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('originals', type=Path)
    args = parser.parse_args()
    originals = args.originals.resolve()
    paths = sorted(originals.rglob('*.fits'))
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = [row for row in pool.map(lambda path: footprint(originals, path), paths) if row]
    if not rows:
        raise SystemExit('No released SPHEREx originals were found.')
    atomic_json(INDEX, rows)
    print(f'Indexed {len(rows)} SPHEREx exposure footprints.')


if __name__ == '__main__':
    main()
