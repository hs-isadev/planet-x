"""Follow any moving target across SPHEREx exposures, on fixed sky tiles that grow as it moves.

The sky around the target is cut into fixed square tiles (10′ by default). For every SPHEREx exposure that
contains the target, the script downloads one cutout per tile of the target's current "scene": while the
target stays well inside one tile that is a single tile; once it comes near an edge the neighbour is added
(2 tiles), near a corner 4, and so on up to --max-grid tiles on a side, after which a new scene starts around
it. The motion study joins the tiles into one fixed-sky mosaic, so stars stay put and the target is seen
walking from tile to tile.

Works for Solar System bodies (positions from JPL Horizons) and for stars (catalog proper motion + parallax).
A star that never leaves its home tile needs nothing extra, so --auto simply reports it and moves on; the day
its predicted track reaches the next tile, --auto downloads the new tiles without any change to this script.

    python scripts/fetch_track.py --check                  # test IRSA + Horizons access
    python scripts/fetch_track.py vesta                     # one target (preset name)
    python scripts/fetch_track.py --auto                    # every star target + Vesta, only what is needed
    python scripts/fetch_track.py --horizons 433 --name "433 Eros" --slug eros
    python scripts/fetch_track.py barnard --plan            # show the tile plan only, download nothing
    python scripts/fetch_track.py barnard --tile 0.25 --plan   # tiny tiles: see how tiling reacts to motion

Output: backend/data/tracks/<slug>/<obsid>-d<det>_t<i>_<j>s<scene>.fits.gz and track.json. Then:
    python -m backend.observation_lab_core.motion_study <slug>
Re-running keeps everything already downloaded and only fetches what is missing.
"""
import argparse
import gzip
import io
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backend  # noqa: F401  configures astropy caches before astropy imports
import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS

from backend.observation_lab_core import tiles as T

OUT_ROOT = ROOT / 'backend/data/tracks'
MISSION_START = '2025-04-01'
KEEP_HDUS = ('IMAGE', 'FLAGS', 'VARIANCE', 'WCS-WAVE')
MB_PER_CUTOUT = 0.12          # rough size of one gzipped 10′ tile cutout with the kept extensions

# Solar System presets: Horizons record numbers (a bare name can be ambiguous).
SOLAR = {
    'vesta': ('4', '4 Vesta', 'main-belt asteroid'),
    'ceres': ('1', '1 Ceres', 'dwarf planet (main belt)'),
    'pallas': ('2', '2 Pallas', 'main-belt asteroid'),
    'juno': ('3', '3 Juno', 'main-belt asteroid'),
    'hygiea': ('10', '10 Hygiea', 'main-belt asteroid'),
    'psyche': ('16', '16 Psyche', 'metal-rich main-belt asteroid'),
    'eros': ('433', '433 Eros', 'near-Earth asteroid'),
}
AUTO_SOLAR = ['vesta']


# ---------------------------------------------------------------------------------------------------------
# targets

def star_target(field):
    from backend.observation_lab_core.motion_study import TARGETS, catalog_for, expected
    cat, center = catalog_for(field)
    meta = TARGETS[field]

    def where(mjds):
        return [expected(cat, m)[:2] for m in mjds]
    return dict(slug=field, name=meta['name'], kind='catalog', where=where, anchor=center, gap_days=None,
                info=dict(catalog={k: cat[k] for k in ('ra', 'dec', 'pmra_mas_yr', 'pmdec_mas_yr', 'parallax_mas') if k in cat},
                          source=cat.get('source'), field_center=list(center)))


def custom_star(args):
    from backend.observation_lab_core.motion_study import expected
    cat = dict(ra=args.ra, dec=args.dec, pmra_mas_yr=args.pmra, pmdec_mas_yr=args.pmdec, parallax_mas=args.plx)
    return dict(slug=args.slug, name=args.name or args.slug, kind='catalog', anchor=(args.ra, args.dec), gap_days=None,
                where=lambda mjds: [expected(cat, m)[:2] for m in mjds], info=dict(catalog=cat, source='command line'))


def horizons_target(designation, name, slug, kind='Solar System body'):
    from backend.archive import CACHE
    from backend.observation_lab_core import ephemeris

    def where(mjds):
        out = []
        for i in range(0, len(mjds), 300):          # keep each Horizons request a sensible size
            chunk = [Time(m, format='mjd').jd for m in mjds[i:i + 300]]
            out += [(r['ra'], r['dec']) for r in ephemeris.fetch(designation + ';', chunk, CACHE, timeout=(30, 60))['rows']]
        return out
    return dict(slug=slug, name=name, kind='horizons', where=where, anchor=None, gap_days=5.0,
                info=dict(horizons=designation, body=kind))


def resolve(name, args):
    from backend.observation_lab_core.motion_study import TARGETS
    if name in SOLAR:
        d, n, k = SOLAR[name]
        return horizons_target(d, n, name, k)
    if name in TARGETS:
        return star_target(name)
    raise SystemExit(f'Unknown target "{name}". Presets: {", ".join(list(TARGETS) + list(SOLAR))}; '
                     'or use --horizons / --ra --dec.')


# ---------------------------------------------------------------------------------------------------------
# archive

def check():
    from backend.observation_lab_core.archive import query_tap
    from backend.observation_lab_core.server import CONFIG
    ok = True
    try:
        ra, dec = horizons_target('4', '4 Vesta', 'vesta')['where']([Time('2025-08-04T12:00:00').mjd])[0]
        print(f'JPL Horizons: OK (Vesta at RA {ra:.3f}, Dec {dec:.3f} on 2025-08-04)')
    except Exception as error:
        ok = False
        print(f'JPL Horizons: FAILED ({error})')
    try:
        rows = query_tap(CONFIG, 222.9452745, -11.9498975, Time('2025-08-04').mjd, Time('2025-08-06').mjd)
        print(f'IRSA TAP: OK ({len(rows)} exposures on 4-5 Aug 2025 at the original Vesta field)')
    except Exception as error:
        ok = False
        print(f'IRSA TAP: FAILED ({error})')
    return ok


def tap(ra, dec, start, end, radius_deg=0):
    from backend.observation_lab_core.archive import query_sia, query_tap
    from backend.observation_lab_core.server import CONFIG
    for attempt in range(3):
        try:
            return query_tap(CONFIG, ra, dec, start, end, radius_deg=radius_deg)
        except Exception as error:
            if attempt == 0:
                try:
                    return query_sia(CONFIG, ra, dec, max(radius_deg, .001), start, end, timeout=(25, 50))
                except Exception as sia_error:
                    print(f'  SIA fallback unavailable: {sia_error}', flush=True)
            if attempt == 2:
                raise RuntimeError(f'Incomplete discovery for {Time(start, format="mjd").iso[:10]}') from error
            time.sleep(2 + 3 * attempt)


def discover(target, start, end, workers=4):
    """Exposures whose footprint contains the target. Moving bodies: one query per day at that day's position.
    Stars: one query per 30 days at the predicted position (they move far less than a pixel in that time)."""
    step = 1.0 if target['kind'] == 'horizons' else 30.0
    windows = []
    t = start
    while t < end:
        windows.append((t, min(t + step, end)))
        t += step
    mids = target['where']([(a + b) / 2 for a, b in windows])
    radii = [0.0] * len(windows)
    if windows and target['kind'] == 'horizons':
        edges = target['where']([a for a, _ in windows] + [windows[-1][1]])
        for i, mid in enumerate(mids):
            # Include footprints crossed before or after noon. The FITS WCS and
            # the exposure-time ephemeris are checked when building the trail.
            radii[i] = (1 + max(T.separation_arcmin(*mid, *edge) for edge in edges[i:i+2])) / 60
    found = {}
    with ThreadPoolExecutor(workers) as pool:
        futures = [pool.submit(tap, p[0], p[1], a, b, radius) for (a, b), p, radius in zip(windows, mids, radii)]
        for i, future in enumerate(as_completed(futures), 1):
            for row in future.result():
                found[(row['id'], row['detector'])] = row
            if i % 30 == 0:
                print(f'  searched {i}/{len(windows)} windows · {len(found)} exposures so far')
    return sorted(found.values(), key=lambda r: (r['mjd'], r['detector']))


def thin(rows, limit, keep):
    """At most `limit` exposures, spread evenly in time; exposures already downloaded are always kept."""
    kept = [r for r in rows if (r['id'], r['detector']) in keep]
    fresh = [r for r in rows if (r['id'], r['detector']) not in keep]
    room = max(0, limit - len(kept))
    if len(fresh) > room:
        step = len(fresh) / room if room else 0
        fresh = [fresh[int(i * step)] for i in range(room)]
    return sorted(kept + fresh, key=lambda r: (r['mjd'], r['detector']))


def save_tile(row, centre, tile_arcmin, path):
    """Download one cutout centred on a tile, keep only the extensions the study needs, gzip it."""
    from backend.archive import CACHE
    from backend.observation_lab_core.archive import download
    if path.is_file():
        return 'kept'
    record = download(row, centre[0], centre[1], tile_arcmin, CACHE, prefer_mirror=True)
    with fits.open(record['path'], memmap=False) as hdus:
        img = hdus['IMAGE'].data
        wcs = WCS(hdus['IMAGE'].header).celestial
        x, y = wcs.world_to_pixel_values(*centre)
        h, w = img.shape
        if not (0 <= x < w and 0 <= y < h) or np.isfinite(img).mean() < .15:
            raise LookupError('tile is off this exposure')
        keep = fits.HDUList([fits.PrimaryHDU(header=hdus[0].header)] + [hdus[n].copy() for n in KEEP_HDUS if n in hdus])
        buffer = io.BytesIO()
        keep.writeto(buffer)
    with gzip.open(path, 'wb', compresslevel=6) as out:
        out.write(buffer.getvalue())
    return 'downloaded'


# ---------------------------------------------------------------------------------------------------------
# planning

def plan_scenes(target, points, args, anchor):
    return T.build_scenes(points, args.tile, args.margin, args.max_grid, target['gap_days'], anchor)


def describe(scenes):
    sizes = {}
    for s in scenes:
        nx, ny = T.box_dims(s['box'])
        sizes[f'{nx}×{ny}'] = sizes.get(f'{nx}×{ny}', 0) + 1
    return ', '.join(f'{n} scene{"s" if n > 1 else ""} of {k} tiles' for k, n in sorted(sizes.items()))


def predicted_check(target, args, start, end):
    """Offline look at the predicted track: which tiles would it touch? (Stars only; no network needed.)"""
    mjds = list(np.arange(start, end, 10.0)) + [end]
    pos = target['where'](mjds)
    points = [dict(mjd=m, ra=p[0], dec=p[1]) for m, p in zip(mjds, pos)]
    scenes = plan_scenes(target, points, args, target['anchor'])
    moved = T.separation_arcmin(pos[0][0], pos[0][1], pos[-1][0], pos[-1][1])
    off = T.separation_arcmin(pos[-1][0], pos[-1][1], *target['anchor'])
    return scenes, moved, off


def run(target, args):
    out = OUT_ROOT / target['slug']
    track_path = out / 'track.json'
    previous = json.loads(track_path.read_text(encoding='utf-8')) if track_path.is_file() else None
    start, end = Time(args.start).mjd, Time(args.end).mjd
    if previous and previous.get('tile_arcmin') != args.tile:
        print(f'  note: keeping the existing {previous["tile_arcmin"]}′ tiles for {target["slug"]} (delete {track_path} to change)')
        args.tile, args.margin = previous['tile_arcmin'], previous['margin_arcmin']

    if target['kind'] == 'catalog':
        scenes, moved, off = predicted_check(target, args, start, end)
        boxes = {tuple(s['box']) for s in scenes}
        single = boxes == {(0, 0, 0, 0)}
        print(f'{target["name"]}: predicted to move {moved * 60:.1f}″ between {args.start} and {args.end}; '
              f'ends {off:.2f}′ from the field centre (tile half-width {args.tile / 2:.2f}′, edge margin {args.margin}′).')
        if single and not args.force:
            print('  stays inside its home tile, which the regular SPHEREx bundle already covers: nothing to download.')
            return None
        print(f'  track crosses tile edges: {describe(scenes)}.')
        if args.plan:
            return None
    elif args.plan:
        mjds = list(np.arange(start, end, 1.0))
        pos = target['where'](mjds)
        scenes = plan_scenes(target, [dict(mjd=m, ra=p[0], dec=p[1]) for m, p in zip(mjds, pos)], args, None)
        print(f'{target["name"]}: daily ephemeris track → {describe(scenes)} (before matching to SPHEREx exposures).')
        return None

    print(f'Searching SPHEREx for {target["name"]} from {args.start} to {args.end} …')
    rows = discover(target, start, end, workers=args.workers)
    old = {(e['id'], e['detector']): e for e in (previous or {}).get('exposures', [])}
    for key, e in old.items():                     # keep earlier finds even if outside this run's dates
        if not any((r['id'], r['detector']) == key for r in rows):
            rows.append(dict(id=e['id'], detector=e['detector'], mjd=e['mjd'], release=e.get('release'),
                             source=e['source'], collection=e.get('collection')))
    rows.sort(key=lambda r: (r['mjd'], r['detector']))
    print(f'{len(rows)} exposures contain {target["name"]}.')
    if not rows:
        return None
    rows = thin(rows, args.max, set(old))
    pos = target['where']([r['mjd'] for r in rows])
    points = [dict(mjd=r['mjd'], ra=p[0], dec=p[1]) for r, p in zip(rows, pos)]
    scenes = plan_scenes(target, points, args, target['anchor'])
    jobs = []
    for si, s in enumerate(scenes):
        tiling = T.Tiling(s['anchor'][0], s['anchor'][1], args.tile, args.margin)
        for idx in s['members']:
            r = rows[idx]
            for i, j in T.box_tiles(s['box']):
                name = f"{r['id']}-d{r['detector']}_t{T.tile_key(i, j)}s{si}.fits.gz"
                jobs.append((idx, si, (i, j), tiling.centre(i, j), name))
    todo = [j for j in jobs if not (out / j[4]).is_file()]
    print(f'Plan: {len(rows)} exposures, {describe(scenes)} → {len(jobs)} tile cutouts '
          f'({len(todo)} to download, about {len(todo) * MB_PER_CUTOUT:.0f} MB).')
    if args.plan:
        return None
    out.mkdir(parents=True, exist_ok=True)
    have, failures = {}, []
    with ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(save_tile, rows[j[0]], j[3], args.tile, out / j[4]): j for j in jobs}
        for n, future in enumerate(as_completed(futures), 1):
            idx, si, ij, centre, name = futures[future]
            try:
                future.result()
                have.setdefault(idx, {})[T.tile_key(*ij)] = name
            except LookupError:
                pass                                   # tile falls off the edge of this exposure
            except Exception as error:
                failures.append(f"{rows[idx]['id']} D{rows[idx]['detector']} tile {T.tile_key(*ij)}: {error}")
            if n % 40 == 0:
                print(f'  {n}/{len(jobs)} tiles processed · {len(failures)} failed')

    exposures = []
    for idx, r in enumerate(rows):
        if idx not in have:
            continue
        si = next(k for k, s in enumerate(scenes) if idx in s['members'])
        exposures.append(dict(id=r['id'], detector=r['detector'], mjd=r['mjd'], date=Time(r['mjd'], format='mjd').isot + 'Z',
                              release=r.get('release'), source=r['source'], collection=r.get('collection'),
                              target_ra=points[idx]['ra'], target_dec=points[idx]['dec'], scene=si, tiles=have[idx]))
    track = dict(version=2, slug=target['slug'], object=target['name'], kind=target['kind'], **target['info'],
                 tile_arcmin=args.tile, margin_arcmin=args.margin, max_grid=args.max_grid,
                 scenes=[dict(index=k, anchor=list(s['anchor']), box=s['box'],
                              tiles={T.tile_key(i, j): list(T.Tiling(s['anchor'][0], s['anchor'][1], args.tile).centre(i, j))
                                     for i, j in T.box_tiles(s['box'])}) for k, s in enumerate(scenes)],
                 exposures=exposures, generated_utc=Time.now().isot + 'Z')
    track_path.write_text(json.dumps(track, indent=1), encoding='utf-8')
    referenced = {n for e in exposures for n in e['tiles'].values()}
    stray = [p for p in out.glob('*_t*s*.fits.gz') if p.name not in referenced]
    print(f'Done: {len(exposures)} exposures, {len(referenced)} tile files in {out.relative_to(ROOT)} ({len(failures)} failed).')
    for line in failures[:10]:
        print('  ' + line)
    if stray:
        print(f'  {len(stray)} older tile files are no longer used (scene layout changed); --prune removes them.')
        if args.prune:
            for p in stray:
                p.unlink()
    print(f'Next: python -m backend.observation_lab_core.motion_study {target["slug"]}')
    return track


def main():
    from backend.observation_lab_core.motion_study import TARGETS
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('targets', nargs='*', help=f'preset names: {", ".join(list(TARGETS) + list(SOLAR))}')
    parser.add_argument('--auto', action='store_true', help='every star target plus ' + ', '.join(AUTO_SOLAR))
    parser.add_argument('--horizons', help='any Horizons designation, e.g. 433 or "2024 YR4"')
    parser.add_argument('--ra', type=float); parser.add_argument('--dec', type=float)
    parser.add_argument('--pmra', type=float, default=0.0, help='mas/yr (with --ra/--dec)')
    parser.add_argument('--pmdec', type=float, default=0.0, help='mas/yr')
    parser.add_argument('--plx', type=float, default=0.0, help='parallax, mas')
    parser.add_argument('--name'); parser.add_argument('--slug')
    parser.add_argument('--start', default=MISSION_START)
    parser.add_argument('--end', default=Time.now().iso[:10])
    parser.add_argument('--tile', type=float, default=10.0, help='tile size, arcmin (default 10)')
    parser.add_argument('--margin', type=float, default=1.5, help='add the neighbour tile when this close to an edge, arcmin')
    parser.add_argument('--max-grid', type=int, default=3, help='largest scene, tiles per side (default 3 → up to 3×3)')
    parser.add_argument('--max', type=int, default=150, help='most exposures per target (spread evenly in time)')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--plan', action='store_true', help='show the tile plan, download nothing')
    parser.add_argument('--force', action='store_true', help='download even if a star never leaves its home tile')
    parser.add_argument('--prune', action='store_true', help='delete tile files the new layout no longer uses')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    args.margin = min(args.margin, args.tile / 2)
    if args.check:
        sys.exit(0 if check() else 2)
    targets = []
    if args.horizons:
        slug = args.slug or ''.join(c if c.isalnum() else '-' for c in args.horizons.lower()).strip('-')
        targets.append(horizons_target(args.horizons, args.name or args.horizons, slug))
    if args.ra is not None and args.dec is not None:
        if not args.slug:
            raise SystemExit('--slug is required with --ra/--dec')
        targets.append(custom_star(args))
    names = list(args.targets)
    if args.auto:
        names += [k for k in TARGETS if k not in names] + [k for k in AUTO_SOLAR if k not in names]
    targets += [resolve(n, args) for n in names]
    if not targets:
        parser.print_help()
        return
    built = []
    for target in targets:
        try:
            if run(target, args):
                built.append(target['slug'])
        except Exception as error:
            print(f'{target["slug"]}: failed ({error})')
    if built:
        print('\nRebuild the studies: python -m backend.observation_lab_core.motion_study ' + ' '.join(built))


if __name__ == '__main__':
    main()
