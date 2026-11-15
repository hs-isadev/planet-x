"""Download SPHEREx exposures that follow the asteroid Vesta along its orbit.

For every day of the mission the script asks JPL Horizons where Vesta was (as seen from SPHEREx), asks IRSA
which SPHEREx exposures contain that point during that day, then downloads a cutout of each exposure centred
on Vesta's position at the exposure's own time. Because every cutout is centred on the asteroid, the viewer
can follow it even after it has left the original 15′ field.

Output: backend/data/vesta-track/<obsid>-d<detector>.fits.gz and track.json. Then rebuild the study:
    python -m backend.observation_lab_core.motion_study vesta

    python scripts/fetch_vesta_track.py --check           # test IRSA + Horizons access only
    python scripts/fetch_vesta_track.py                    # whole mission, up to 240 exposures
    python scripts/fetch_vesta_track.py --start 2025-08-01 --end 2025-08-31 --max 400
Re-running skips exposures already saved.
"""
import argparse
import gzip
import json
import math
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backend  # noqa: F401  configures astropy caches before astropy imports
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS

from backend.archive import CACHE
from backend.observation_lab_core import ephemeris
from backend.observation_lab_core.archive import download, query_tap
from backend.observation_lab_core.server import CONFIG

OUT = ROOT / 'backend/data/vesta-track'
DESIGNATION = 'Vesta'      # Horizons resolves this to 4 Vesta (checked by ephemeris.py's self-test)
MISSION_START = '2025-04-01'
FOV_ARCMIN = 10.0


def horizons(jds):
    rows = ephemeris.fetch(DESIGNATION, jds, CACHE)['rows']
    return [(r['ra'], r['dec']) for r in rows]


def check():
    ok = True
    try:
        ra, dec = horizons([Time('2025-08-04T12:00:00').jd])[0]
        print(f'JPL Horizons: OK (Vesta at RA {ra:.3f}, Dec {dec:.3f} on 2025-08-04)')
    except Exception as error:
        ok = False
        print(f'JPL Horizons: FAILED ({error})')
    try:
        rows = query_tap(CONFIG, 222.9452745, -11.9498975, Time('2025-08-04').mjd, Time('2025-08-06').mjd)
        print(f'IRSA TAP: OK ({len(rows)} exposures cover the original Vesta field on 4-5 Aug 2025)')
    except Exception as error:
        ok = False
        print(f'IRSA TAP: FAILED ({error})')
    return ok


def discover(start, end, workers=4):
    """One TAP query per day at Vesta's mid-day position, then an exact containment check per exposure."""
    days = []
    t = Time(start).mjd
    while t < Time(end).mjd:
        days.append(t)
        t += 1
    mids = horizons([Time(d + .5, format='mjd').jd for d in days])
    found = {}

    def one(day, pos):
        for attempt in range(3):
            try:
                return day, query_tap(CONFIG, pos[0], pos[1], day, day + 1)
            except Exception as error:
                if attempt == 2:
                    print(f'  {Time(day, format="mjd").iso[:10]}: query failed ({error})')
                    return day, []
                time.sleep(2 + 3 * attempt)

    with ThreadPoolExecutor(workers) as pool:
        futures = [pool.submit(one, d, p) for d, p in zip(days, mids)]
        for i, future in enumerate(as_completed(futures), 1):
            day, rows = future.result()
            for row in rows:
                found[(row['id'], row['detector'])] = row
            if i % 30 == 0:
                print(f'  searched {i}/{len(days)} days · {len(found)} exposures so far')
    return sorted(found.values(), key=lambda r: (r['mjd'], r['detector']))


def thin(rows, limit):
    """Keep the time coverage even: at most `limit` exposures, spread over the whole period."""
    if len(rows) <= limit:
        return rows
    step = len(rows) / limit
    return [rows[int(i * step)] for i in range(limit)]


def save(row, pos):
    name = f"{row['id']}-d{row['detector']}.fits.gz"
    target = OUT / name
    if target.is_file():
        return name, 'kept'
    record = download(row, pos[0], pos[1], FOV_ARCMIN, CACHE, prefer_mirror=True)
    with fits.open(record['path'], memmap=False) as hdus:
        wcs = WCS(hdus['IMAGE'].header).celestial
        x, y = wcs.world_to_pixel_values(pos[0], pos[1])
        h, w = hdus['IMAGE'].shape
        if not (2 <= x < w - 2 and 2 <= y < h - 2):
            raise ValueError('Vesta is outside this exposure.')
    with open(record['path'], 'rb') as source, gzip.open(target, 'wb', compresslevel=6) as out:
        shutil.copyfileobj(source, out)
    return name, 'downloaded'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--start', default=MISSION_START)
    parser.add_argument('--end', default=Time.now().iso[:10])
    parser.add_argument('--max', type=int, default=240, help='most exposures to keep (spread evenly in time)')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        sys.exit(0 if check() else 2)
    OUT.mkdir(parents=True, exist_ok=True)
    print(f'Searching SPHEREx for Vesta from {args.start} to {args.end} …')
    rows = discover(args.start, args.end)
    print(f'{len(rows)} exposures contain Vesta’s daily position.')
    rows = thin(rows, args.max)
    positions = horizons([Time(r['mjd'], format='mjd').jd for r in rows])
    saved, failures = [], []
    track_path = OUT / 'track.json'
    previous = json.loads(track_path.read_text(encoding='utf-8')) if track_path.is_file() else {'frames': []}
    known = {f['file']: f for f in previous['frames']}
    with ThreadPoolExecutor(3) as pool:
        futures = {pool.submit(save, r, p): (r, p) for r, p in zip(rows, positions)}
        for i, future in enumerate(as_completed(futures), 1):
            row, pos = futures[future]
            try:
                name, how = future.result()
                known[name] = dict(file=name, id=row['id'], detector=row['detector'], mjd=row['mjd'],
                                   date=Time(row['mjd'], format='mjd').isot + 'Z', release=row['release'],
                                   source=row['source'], vesta_ra=pos[0], vesta_dec=pos[1])
                saved.append(name)
            except Exception as error:
                failures.append(f"{row['id']} D{row['detector']}: {error}")
            if i % 20 == 0:
                print(f'  {i}/{len(rows)} processed · {len(saved)} saved · {len(failures)} failed')
    frames = sorted(known.values(), key=lambda f: f['mjd'])
    track_path.write_text(json.dumps(dict(
        object='4 Vesta', ephemeris='JPL Horizons (observer: SPHEREx where available)', fov_arcmin=FOV_ARCMIN,
        generated_utc=Time.now().isot + 'Z', frames=frames), indent=1), encoding='utf-8')
    print(f'Done: {len(frames)} Vesta exposures saved in {OUT.relative_to(ROOT)} ({len(failures)} failed).')
    for line in failures[:10]:
        print('  ' + line)
    print('Next: python -m backend.observation_lab_core.motion_study vesta')


if __name__ == '__main__':
    main()
