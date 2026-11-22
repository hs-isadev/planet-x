"""Local SPHEREx prototype server. Run with Python, then open its printed URL."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import time
import traceback
from urllib.parse import parse_qs, urlencode, urlparse
import uuid

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
DEPS = WORKSPACE / 'work' / 'deps'
if DEPS.exists():
    sys.path.insert(0, str(DEPS))

import numpy as np
import requests
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.io.votable import parse_single_table
from astropy.time import Time
from astropy.wcs import WCS
from PIL import Image
from .science import (PIPELINE, FLAG_SOURCE, fits_metadata, grid_for, inspect_pixel,
                     prepare_frame, render_frames, request_options)
from .archive import query as archive_query, download as archive_download, reduction_priority, write_json
from backend.archive import CACHE as PLANET_CACHE, LOW_MEMORY, ROOT as PLANET_ROOT
from backend.example_field import prepare_starter, prepared_starter
from .featured_views import (ALTERNATE_FRAME_LIMIT, CACHE, INDEX, PRESET_FOV, cache_path, catalog_field,
                             default_preset, fields, historical_rows, locate, motion_examples, observing_days,
                             sample_frames, view_entry)
from .science import FrameBuffer

DATA = ROOT
LOCAL = PLANET_ROOT / 'nasaSpace-main/outputs/spherex-viewer'
CACHE.mkdir(parents=True, exist_ok=True)
REGISTRY = CACHE / 'imports.json'
LOCK = threading.RLock()
ACTIVE_JOBS = 1 if LOW_MEMORY else 3
FINISHED_JOBS = 4 if LOW_MEMORY else 32
# Observations fetched per live request. Each request returns everything fetched so far, and the viewer asks for
# the next batch by itself, so this only sets how often the picture refreshes, not how many dates can load.
LIVE_BATCH_SIZE = max(4, int(os.environ.get('SPHEREX_LIVE_BATCH', 60)))
BATCH_SECONDS = max(20.0, float(os.environ.get('SPHEREX_BATCH_SECONDS', 60)))
POOL = ThreadPoolExecutor(max_workers=ACTIVE_JOBS)
JOBS = {}
CONFIG = json.loads((ROOT / 'archive-config.json').read_text())
LIBRARY = json.loads((DATA / 'data' / 'collection.json').read_text())
DETECTORS = json.loads((DATA / 'data' / 'detectors.js').read_text().split('=', 1)[1].strip().rstrip(';'))
RECORDS = []
FEATURED = CACHE / 'featured-library.json'
SESSION_INDEX = CACHE / 'session-index.json'
FEATURED_STAMP = None
SESSIONS = json.loads(SESSION_INDEX.read_text()) if SESSION_INDEX.exists() else {}
VIEW_INDEX = CACHE / 'view-index'
VIEW_INDEX.mkdir(exist_ok=True)
CACHE_LIMIT = float(os.environ.get('SPHEREX_CACHE_GB', 2)) * 1e9
TARGET_SESSIONS = {
    'vesta': 'e73b15d70f48408b9b7932aee4bb2c59',
    'barnard': 'd1fa8853f3c340c8822a3a48e80ba444',
    'epsilon-indi': '4d9dd1c752e84d27946cad613ad1c1f4',
    'wise-0855': '7a66c2411dd440758a1336a839d8bde7',
    'rw-aur': 'daccb2b332db4c15867d0027796672a3',
    'r-dra': '4ac83d693bac4c97968f8326d99f485c',
}


def atomic_json(path, data):
    write_json(path, data)


def initialize():
    for field in LIBRARY['fields']:
        prepared = {}
        native_cache = PLANET_CACHE
        for frame in field['frames']:
            native = LOCAL / frame['fits']
            if not native.is_file():
                if not prepared:
                    try:
                        starter = prepared_starter(field['key'])
                        if not starter and PLANET_CACHE != PLANET_ROOT / 'cache':
                            native_cache = PLANET_ROOT / 'cache'
                            starter = prepared_starter(field['key'], native_cache)
                        if not starter and field['key'] == 'vesta':
                            native_cache = PLANET_CACHE
                            starter = prepare_starter('vesta')
                        if not starter:
                            break
                        prepared = {r['url']:r for r in starter['frames'] if r['status']=='ready'}
                    except (OSError,ValueError):
                        break
                ready = prepared.get(frame['source'])
                if not ready:
                    continue
                native = native_cache / (ready['cache_id']+'.fits')
            if not native.is_file():
                continue
            try:
                meta = fits_metadata(native)
            except (OSError, ValueError, KeyError):
                continue
            meta.update(path=str(native), release=frame['release'], source=frame['source'],
                        field_key=field['key'], field_name=field['name'],
                        provenance='Official IRSA archived exposure',
                        fits_url='/api/original/'+meta['sha256'], context=[])
            if frame.get('marker'):
                grid,size = grid_for(dict(ra=field['ra'],dec=field['dec'],fov=15))
                sky=grid.pixel_to_world(frame['marker'][0]*size-.5,(1-frame['marker'][1])*size-.5)
                meta['marker_sky']=[float(sky.ra.deg),float(sky.dec.deg)]
            with LOCK:
                RECORDS.append(meta)



def refresh_featured():
    """Pick up a background sync without requiring a server restart."""
    global FEATURED_STAMP
    with LOCK:
        stamp = FEATURED.stat().st_mtime_ns if FEATURED.exists() else None
        if stamp != FEATURED_STAMP:
            catalog = json.loads(FEATURED.read_text()) if stamp is not None else {'records': []}
            RECORDS[:] = [r for r in RECORDS if not r.get('featured_cache')]
            for record in catalog['records']:
                if record.get('path') and not Path(record['path']).is_file():
                    local = CACHE / Path(record['path']).name
                    if local.is_file():
                        record['path'] = str(local)
                RECORDS.append(dict(record, featured_cache=True))
            FEATURED_STAMP = stamp


def imported_records(records):
    with LOCK:
        current = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else []
        known = {r['sha256'] for r in RECORDS}
        new = [record for record in records if record['sha256'] not in known]
        atomic_json(REGISTRY, current + new)
        RECORDS.extend(new)


def expected_sky_position(field, mjd):
    """Apply linear catalog proper motion in the same way as the viewer guide."""
    astrometry = field.get('astrometry_j2000')
    if astrometry is None:
        return SkyCoord(field['ra'], field['dec'], unit='deg')
    ra, dec, pm_ra, pm_dec = astrometry
    years = (mjd - 51544.5) / 365.25
    return SkyCoord(
        (ra + pm_ra * years / (3.6e6 * math.cos(math.radians(dec)))) % 360,
        dec + pm_dec * years / 3.6e6,
        unit='deg',
    )


def date_search_cone(field, options):
    if not field or 'astrometry_j2000' not in field:
        return options['ra'], options['dec'], .001
    start = max(Time('2025-03-11').mjd, options['start_mjd'] or 0)
    end = max(start, options['end_mjd'] or Time.now().mjd)
    center = expected_sky_position(field, (start + end) / 2)
    radius = max(center.separation(expected_sky_position(field, t)).deg for t in (start, end))
    return center.ra.deg, center.dec.deg, radius + .001


def contains_expected_position(record, field):
    with fits.open(record['path'], memmap=False) as hdus:
        image = hdus['IMAGE']
        sky = expected_sky_position(field, record['mjd'])
        x, y = WCS(image.header, naxis=2).celestial.world_to_pixel(sky)
        return (-.5 <= x < image.header['NAXIS1'] - .5
                and -.5 <= y < image.header['NAXIS2'] - .5)


def all_exposures(options):
    """True when the viewer asked for every exposure rather than one per observing date."""
    return bool(options.get('all_exposures')) or options.get('sampling') == 'all'


def fetch_archive(options, progress, archive_rows=None, preview=None, *, mirror_only=False, page=None):
    progress('Querying IRSA for SPHEREx observations…')
    new_dates = bool(page and page.get('new_dates')) and archive_rows is None
    field = catalog_field(None, options)
    if archive_rows is not None:
        rows = archive_rows
    else:
        try:
            cone = date_search_cone(field, options) if new_dates else (options['ra'], options['dec'], .001)
            args = (CONFIG, *cone, options['start_mjd'], options['end_mjd'])
            rows = archive_query(*args, latest=True) if new_dates else archive_query(*args)
        except RuntimeError:
            target = catalog_field(None, options)
            if not target or options['fov'] == PRESET_FOV and view_entry(target['key'])[1]:
                raise
            rows = historical_rows(target['key'])
            if not rows:
                _, entry = view_entry(target['key'])
                if entry:
                    rows = load_manifest(entry['session'])['frames']
            if not rows:
                raise
            rows = [dict(row, discovery_warning='Live IRSA discovery unavailable; using known released exposures.')
                    for row in rows if (options['start_mjd'] is None or row['mjd'] >= options['start_mjd'])
                    and (options['end_mjd'] is None or row['mjd'] < options['end_mjd'])]
    rows = [row for row in rows if not options['detector'] or row['detector'] == options['detector']]
    if not rows and not new_dates:
        return [], 0, []
    failures = list(dict.fromkeys(row['discovery_warning'] for row in rows if row.get('discovery_warning')))
    total = len(rows)
    preset = default_preset(field, options)
    daily = preset and not all_exposures(options)
    if new_dates:
        _, saved = view_entry(field['key']) if preset else (None, None)
        if not saved:
            raise ValueError('Open a saved field before searching for additional dates.')
        saved_days = {int(frame['mjd']) for frame in load_manifest(saved['session'])['frames']}
        page['saved_days'] = saved_days
        groups = observing_days(row for row in rows if int(row['mjd']) not in saved_days)
        alternatives = {(group[0]['id'], group[0]['detector']): group[1:2] for group in groups}
        rows = [group[0] for group in groups]
        page['candidate_dates'] = len(rows)
    # Live archive requests are paged: each request downloads one batch and the viewer keeps asking for the
    # next one until every observation (or, in one-per-date mode, every date) is loaded or the user presses Stop.
    # Paging therefore replaces the old sampled cap. Requests without a page (cache warmers) keep the sample.
    paged = archive_rows is None and page is not None
    if archive_rows is None and not preset and not paged:
        rows = sample_frames(rows)
    if paged:
        representative_count = None
        if not new_dates:
            # Every date first, then same-day extras, so even the first batches span the whole time range.
            groups = observing_days(rows)
            representatives = [group[0] for group in groups]
            representative_count = len(representatives) if daily else None
            first = sample_frames(representatives, LIVE_BATCH_SIZE)
            identities = {(row['id'], row['detector']) for row in first}
            remainder = representatives + [row for group in groups for row in group[1:]]
            rows = first + [row for row in remainder if (row['id'], row['detector']) not in identities]
        offset = page['offset']
        batch = rows[offset:offset + LIVE_BATCH_SIZE]
        deadline = time.monotonic() + BATCH_SECONDS
        records = []
        # Earlier batches are already on disk, so each request returns the whole set so far. Rows that were
        # not fetched earlier are skipped here instead of being retried (and failing again).
        for row in rows[:offset]:
            for candidate in ([row, *alternatives.get((row['id'], row['detector']), [])] if new_dates else [row]):
                try:
                    record = archive_download(candidate, options['ra'], options['dec'], options['fov'],
                                              CACHE, prefer_mirror=True, mirror_only=mirror_only, cache_only=True)
                    if new_dates and not contains_expected_position(record, field):
                        continue
                    records.append(record)
                    break
                except Exception:
                    continue
        preview_shown = False
        attempted = 0
        for row in batch:
            if attempted and time.monotonic() >= deadline:
                break
            progress(f'Downloading observation {attempted + 1} of {len(batch)} from SPHEREx')
            attempted += 1
            choices = [row, *alternatives.get((row['id'], row['detector']), [])] if new_dates else [row]
            for candidate in choices:
                try:
                    record = archive_download(candidate, options['ra'], options['dec'], options['fov'],
                                              CACHE, prefer_mirror=True, mirror_only=mirror_only)
                    if new_dates and not contains_expected_position(record, field):
                        raise ValueError('The detector does not cover the expected target position.')
                    records.append(record)
                    break
                except Exception as error:
                    failures.append(f"{candidate['id']}: {error}")
                    if time.monotonic() >= deadline:
                        break
            if preview and not preview_shown and 2 <= len(records) <= 6:
                preview_shown = preview(records, total)
        next_offset = offset + attempted
        # A one-frame-per-date view is complete once every date has its frame; later rows are same-day alternates.
        last = len(rows) if representative_count is None else representative_count
        page['next'] = next_offset if next_offset < last else None
        # This batch's immutable files and manifest are sufficient for tracking and replay.
        return records, total, failures
    if len(rows) > 4:
        first = [rows[round(i * (len(rows) - 1) / 3)] for i in range(4)]
        selected = {(row['id'], row['detector']) for row in first}
        rows = first + [row for row in rows if (row['id'], row['detector']) not in selected]
    records = []
    preview_shown = False
    progress(f'Downloading 0 of {len(rows)} observations from IRSA…')
    workers = 1 if LOW_MEMORY else 3 if archive_rows is not None else 5
    with ThreadPoolExecutor(max_workers=min(workers, len(rows))) as pool:
        pending = {pool.submit(archive_download, row, options['ra'], options['dec'], options['fov'],
                                CACHE, prefer_mirror=True, mirror_only=mirror_only): row for row in rows}
        for done, future in enumerate(as_completed(pending), 1):
            try:
                records.append(future.result())
            except Exception as error:
                failures.append(f"{pending[future]['id']}: {error}")
            if preview and not preview_shown and len(rows) > 6 and 2 <= len(records) <= 6:
                preview_shown = preview(records, total)
            progress(f'Downloading observation {done} of {len(rows)}')
    if archive_rows is None:
        imported_records(records)
    return records, total, failures


def available(record):
    if record.get('path') and Path(record['path']).is_file():
        return True
    filename = record.get('fits_url', '').removeprefix('/cache/')
    local = cache_path(filename)
    if local:
        record['path'] = str(local)
    return bool(local)


def ensure_local(record):
    """Return the record with its FITS on disk, re-fetching an evicted archive cutout."""
    if available(record):
        return record
    if not record.get('download_center'):
        raise FileNotFoundError('The original FITS is no longer cached. Reopen this sky view.')
    return archive_download(record, *record['download_center'],
                            record['requested_source_width_deg'] / 1.5 * 60, CACHE)


def fetch_cutouts(records, ra, dec, fov, progress, failures, start=None, end=None, check_cancelled=None):
    """Download cutouts around (ra, dec) for observations with no local file.

    Returns {(id, detector): record}. Index records only guarantee that an
    observation contains its own field center, so any other position is checked
    against the archive footprints first; a cutout outside the footprint fails
    slowly and then falls back to the full detector file.
    """
    def centered(record):
        center = record.get('download_center') or record.get('center') or [None, None]
        return center[0] is not None and abs(center[0]-ra) < 1e-9 and abs(center[1]-dec) < 1e-9
    if not all(centered(r) for r in records):
        progress('Checking which observations cover this position')
        try:
            coverage = archive_query(CONFIG, ra, dec, start=start, end=end)
            covering = {(r['id'], r['detector']) for r in coverage}
            records = [r for r in records if (r['id'], r['detector']) in covering]
            failures.extend(dict.fromkeys(r['discovery_warning'] for r in coverage if r.get('discovery_warning')))
        except (requests.RequestException, RuntimeError, ValueError):
            failures.append('Live IRSA coverage search is unavailable. Checking saved observations against their native coverage.')
    done = {}
    def download_one(record):
        if check_cancelled:
            check_cancelled()
        return archive_download({k: v for k, v in record.items() if k != 'featured_cache'}, ra, dec, fov, CACHE)

    with ThreadPoolExecutor(max_workers=1 if LOW_MEMORY else 6) as pool:
        futures = {pool.submit(download_one, record): record for record in records}
        for count, future in enumerate(as_completed(futures), 1):
            try:
                record = future.result()
                done[(record['id'], record['detector'])] = record
            except Exception as error:
                failures.append(f"{futures[future]['id']}: {error}")
            progress(f'Fetching observation {count} of {len(records)} from the NASA archive')
    imported_records(list(done.values()))
    return done


def trim_cache():
    """Delete re-fetchable cutouts, then rendered views, oldest first, above the size cap.

    Bundled examples live outside CACHE. User imports have no sidecar and are kept.
    The most recently opened view is kept even when it alone exceeds the cap.
    """
    with LOCK:
        if any(job['status'] == 'running' for job in JOBS.values()):
            return  # another job may be reading these files
        items = []
        for path in CACHE.iterdir():
            if path.suffix == '.fits' and path.with_suffix('.record.json').exists():
                items.append((path.stat().st_mtime, path.stat().st_size, path))
            elif path.is_dir() and re.fullmatch('[a-f0-9]{32}', path.name):
                items.append((path.stat().st_mtime, sum(f.stat().st_size for f in path.iterdir()), path))
        total = sum(size for _, size, _ in items)
        on_screen = max((item for item in items if item[2].is_dir()), default=(0, 0, None))[2]
        # The open view's own cutouts stay too: tracking and spectra read them
        keep = set()
        try:
            keep = {CACHE / f['fits_url'].removeprefix('/cache/')
                    for f in json.loads((on_screen / 'manifest.json').read_text())['frames']}
        except (OSError, TypeError, ValueError, KeyError):
            pass
        for index_path in (CACHE / INDEX).glob('*.json'):
            try:
                view = json.loads(index_path.read_text(encoding='utf-8'))
                directory = CACHE / view['session']
                keep.add(directory)
                manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
                keep.update(CACHE / f['fits_url'].removeprefix('/cache/') for f in manifest['frames'])
                keep.update(CACHE / f['fits_url'].removeprefix('/cache/')
                            for f in manifest.get('excluded_frames', []) if f.get('fits_url'))
            except (OSError, ValueError, KeyError):
                continue
        total -= sum(size for _, size, path in items if path in keep)
        # shortcut: cutouts are evicted by download age, not last use; touch them on read if re-fetching gets noticeable
        for _, size, path in sorted(items, key=lambda item: (item[2].is_dir(), item[0])):
            if total <= CACHE_LIMIT:
                break
            if path == on_screen or path in keep:
                continue
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                    path.with_suffix('.record.json').unlink(missing_ok=True)
                total -= size
            except OSError:
                pass  # still open on Windows; the next trim retries


def load_manifest(session_id):
    path = cache_path(f'{session_id}/manifest.json')
    if not path:
        raise FileNotFoundError('This sky view is no longer cached. Open it again.')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    for frame in manifest['frames']:
        if not isinstance(frame.get('context'), list):
            frame['context'] = []
    return manifest


def run_job(work, job_id, payload):
    work(job_id, payload)
    trim_cache()


def trim_finished_jobs():
    finished = [jid for jid, job in JOBS.items() if job.get('status') != 'running']
    for jid in finished[:-FINISHED_JOBS]:
        del JOBS[jid]


def cutout_covers_field(record, grid, size):
    """Check the requested square against the actual saved FITS footprint."""
    corners = grid.pixel_to_world(np.array([0, 0, size-1, size-1]),
                                  np.array([0, size-1, 0, size-1]))
    with fits.open(record['path'], memmap=False) as hdus:
        shape = hdus['IMAGE'].shape
        x, y = WCS(hdus['IMAGE'].header).celestial.world_to_pixel(corners)
    return bool(np.all(np.isfinite(x)) and np.all(np.isfinite(y))
                and np.all((x >= 0) & (x < shape[1]))
                and np.all((y >= 0) & (y < shape[0])))


def wider_cutout(record, options):
    expanded = archive_download(record, options['ra'], options['dec'], options['fov'], CACHE)
    imported_records([expanded])
    return expanded


def session_key(options, records):
    identities = sorted((r['id'], r['detector'], r['sha256'], r.get('marker_sky')) for r in records)
    return hashlib.sha256(json.dumps([PIPELINE, options, identities], sort_keys=True).encode()).hexdigest()


def mosaic_frames(options, grid, size, grid_sky, progress):
    """Prepare real DR1 coadd channels for an explicitly requested mosaic."""
    from . import mosaic
    frames = []
    for path in mosaic.build_channels(options, CACHE, progress):
        record = mosaic.channel_record(fits_metadata(path), path, options)
        imported_records([record])
        frame = prepare_frame(record, options, grid, size, grid_sky=grid_sky)
        if frame and frame[2]['coverage'] >= 50:
            frames.append(frame)
    return frames


def write_previews(session_id, prepared, metadata):
    directory = CACHE / session_id
    directory.mkdir(exist_ok=True)
    stretch = render_frames(prepared, directory) if prepared else None
    for frame in metadata:
        index = frame['index']
        frame.update(preview=f'/cache/{session_id}/{index}.png',
                     quality_overlay=f'/cache/{session_id}/{index}-quality.png')
    return directory, stretch


def publish_live_preview(job_id, options, records, total):
    grid, size = grid_for(options)
    prepared = []
    for record in sorted(records, key=lambda row: (row['mjd'], row['detector'], row['id'])):
        try:
            frame = prepare_frame(record, options, grid, size)
        except (OSError, ValueError, KeyError):
            continue
        if frame and frame[2]['center_inside'] and frame[2]['coverage'] > 0:
            prepared.append(frame)
    metadata = [frame[2] for frame in prepared]
    daily = default_preset(catalog_field(None, options), options) and not all_exposures(options)
    if daily:
        chosen = {(day[0]['id'], day[0]['detector']) for day in observing_days(metadata)}
        prepared = [frame for frame in prepared if (frame[2]['id'], frame[2]['detector']) in chosen]
        metadata = [frame[2] for frame in prepared]
    if not metadata or len({frame['unit'] for frame in metadata}) > 1:
        return False
    identity = uuid.uuid4().hex
    directory, stretch = write_previews(identity, prepared, metadata)
    manifest = dict(id=identity, options=options, size=size, frames=metadata, stretch=stretch,
                    created_utc=Time.now().isot+'Z', archive_matches=total, failures=[],
                    mosaic=False, partial=True, daily_sequence=daily)
    atomic_json(directory / 'manifest.json', manifest)
    with LOCK:
        JOBS[job_id]['preview'] = manifest
    return True


def cached_featured_session(field, options, job_id):
    _, entry = view_entry(field['key'])
    if entry is None:
        return None
    manifest = load_manifest(entry['session'])
    manifest.update(snapshot_complete=entry['complete'], snapshot=True)
    frames = [f for f in manifest['frames'] if
              (not options['detector'] or f['detector'] == options['detector']) and
              (options['start_mjd'] is None or f['mjd'] >= options['start_mjd']) and
              (options['end_mjd'] is None or f['mjd'] < options['end_mjd'])]
    if not frames:
        return None
    preset = default_preset(field, options)
    every = options.get('all_exposures', False)
    daily = preset and not every
    available = len(frames)
    date_count = len(observing_days(frames))
    limited = not preset and not every and available > ALTERNATE_FRAME_LIMIT
    example = motion_examples().get(field['key'])
    matched_example = {point['sha256'] for point in example['points']} if example else set()
    if daily:
        frames = [next((frame for frame in day if frame['sha256'] in matched_example), day[0])
                  for day in observing_days(frames)]
        job_id = hashlib.sha256(f"daily-v2:{manifest['id']}".encode()).hexdigest()[:32]
    elif every:
        frames = sorted(frames, key=lambda f: (f['mjd'], f['detector'], f['id']))
        if preset:
            job_id = hashlib.sha256(f"all-v1:{manifest['id']}".encode()).hexdigest()[:32]
    else:
        frames = sample_frames(frames)
    path = CACHE / job_id
    path.mkdir(exist_ok=True)
    manifest.update(id=job_id, options=options, frames=[dict(frame, index=i) for i, frame in enumerate(frames)],
                    archive_matches=manifest['archive_matches'] if daily else None, matched_frames=available,
                    date_count=date_count, exposure_count=available,
                    excluded_frames=[], limited=limited, daily_sequence=daily)
    if preset:
        manifest.update(saved_exposures=available, saved_dates=date_count)
        spectrum = f"assets/spectra/{field['key']}-{entry['session']}.json"
        if (PLANET_ROOT / 'web' / spectrum).is_file():
            manifest['preset_spectrum'] = '/' + spectrum
    if example:
        by_hash = {frame['sha256']: index for index, frame in enumerate(frames)}
        if matched_example.issubset(by_hash):
            manifest['motion_example'] = dict(example, indices=[by_hash[point['sha256']] for point in example['points']])
    if not (path / 'manifest.json').is_file():
        atomic_json(path / 'manifest.json', manifest)
    return manifest


def create_session(job_id, payload, *, archive_rows=None, cached_records=None):
    def progress(message):
        with LOCK:
            JOBS[job_id]['stage'] = message

    def finish(manifest, stage):
        with LOCK:
            JOBS[job_id].pop('preview', None)
            JOBS[job_id].update(status='complete', stage=stage, result=manifest)

    archive_requested = payload.get('source') == 'archive'
    preparing_cache = archive_rows is not None or cached_records is not None
    offline = cached_records is not None and archive_rows is None
    buffer = None
    try:
        options = request_options(payload)
        field_key = payload.get('field')
        field = locate(None if field_key == 'custom' else field_key, options)
        if not preparing_cache and not archive_requested and field:
            snapshot = cached_featured_session(field, options, job_id)
            if snapshot:
                return finish(snapshot, 'Ready from cache')
            archive_requested = True
        if not preparing_cache:
            refresh_featured()
        progress('Reading calibrated FITS data')
        archive_total = None
        new_dates = archive_requested and payload.get('new_dates') is True
        page = {'offset': int(payload.get('archive_offset', 0)), 'next': None, 'new_dates': new_dates}
        archive_error = None
        failures = []
        records = cached_records
        snapshot = None
        if archive_requested and (archive_rows is not None or cached_records is None):
            try:
                if field and not preparing_cache:
                    snapshot = cached_featured_session(field, options, job_id)
                    if snapshot:
                        with LOCK:
                            JOBS[job_id]['preview'] = snapshot

                def preview(available_records, total):
                    try:
                        return publish_live_preview(job_id, options, available_records, total)
                    except (OSError, ValueError):
                        return False

                records, archive_total, failures = fetch_archive(
                    options, progress, archive_rows, preview if archive_rows is None and not new_dates else None,
                    mirror_only=payload.get('mirror_only', False), page=page)
                if new_dates:
                    records = [record for record in records if int(record['mjd']) not in page['saved_days']]
                if cached_records:
                    records.extend(cached_records)
                if not records and failures and not preparing_cache and field and not new_dates:
                    snapshot = cached_featured_session(field, options, job_id)
                    if snapshot:
                        snapshot.update(archive_error=failures[0], failures=failures,
                                        next_archive_offset=page['next'])
                        return finish(snapshot, 'Live observations unavailable; showing saved FITS')
            except Exception as error:
                if archive_rows is not None:
                    raise
                archive_error = str(error)
                failures.append(f'Live IRSA archive search unavailable ({error}). Showing locally saved observations instead.')
                snapshot = cached_featured_session(field, options, job_id) if field else None
                if snapshot:
                    if new_dates:
                        snapshot['new_dates_search'] = True
                    snapshot.update(archive_error=archive_error, failures=failures)
                    return finish(snapshot, 'IRSA unavailable · showing cached observations')
        if records is None:
            with LOCK:
                records = list(RECORDS)
        search_center = SkyCoord(options['ra'], options['dec'], unit='deg')
        search_radius = options['fov'] / 60 / 2 * 2**.5
        records = [r for r in records if (not options['detector'] or r['detector'] == options['detector'])
                   and r.get('field_key') != 'dr1-mosaic'
                   and (options['start_mjd'] is None or r['mjd'] >= options['start_mjd'])
                   and (options['end_mjd'] is None or r['mjd'] < options['end_mjd'])
                   and search_center.separation(SkyCoord(*r['center'], unit='deg')).deg
                   <= r['radius_deg'] + search_radius]
        dedup = {}
        for record in sorted(records, key=reduction_priority, reverse=True):
            dedup.setdefault((record['id'], record['detector']), record)
        matched = len(dedup)
        limited = False
        preset = default_preset(catalog_field(None, options), options)
        daily = not preparing_cache and preset and not all_exposures(options)
        live_paged = archive_requested and archive_rows is None and not archive_error
        if not preparing_cache and not preset and not live_paged:
            limited = max(matched, archive_total or 0) > ALTERNATE_FRAME_LIMIT
            ordered = sorted(dedup.values(), key=lambda r: (r['mjd'], r['detector'], r['id']))
            dedup = {(r['id'], r['detector']): r for r in sample_frames(ordered)}
        key = session_key(options, list(dedup.values()))
        if not archive_requested or archive_error:
            path = VIEW_INDEX / f'{key}.json'
            cached_id = json.loads(path.read_text(encoding='utf-8'))['session'] if path.is_file() else SESSIONS.get(key)
            if cached_id and (CACHE / cached_id / 'manifest.json').is_file():
                manifest = load_manifest(cached_id)
                if manifest['frames']:
                    os.utime(CACHE / cached_id)
                    if archive_error:
                        manifest.update(archive_error=archive_error, failures=failures + manifest['failures'])
                    return finish(manifest, 'Ready from local cache')
            if not archive_requested and not options['start'] and not options['end']:
                for item in LIBRARY['fields']:
                    sid = TARGET_SESSIONS.get(item['key'])
                    if (sid and options['detector'] == item['frames'][0]['detector']
                            and abs(options['ra'] - item['ra']) < .02 and abs(options['dec'] - item['dec']) < .02
                            and (CACHE / sid / 'manifest.json').is_file()):
                        manifest = load_manifest(sid)
                        if manifest['options']['fov'] == options['fov']:
                            return finish(manifest, 'Ready from local cache')
        grid, size = grid_for(options)
        yy, xx = np.indices((size, size))
        grid_sky = grid.pixel_to_world(xx, yy)
        if matched * size**2 > 2_000_000:
            buffer = FrameBuffer(CACHE)
        prepared = buffer if buffer is not None else []
        excluded = []
        wider_views = 0
        missing = [r for r in dedup.values() if not available(r) and r.get('source')]
        fetch_failures = []
        if missing:
            dedup.update(fetch_cutouts(missing, options['ra'], options['dec'], options['fov'], progress,
                                       fetch_failures, options['start_mjd'], options['end_mjd']))
            failures.extend(fetch_failures)
        candidates = sorted((r for r in dedup.values() if available(r)), key=lambda r: (r['mjd'], r['detector'], r['id']))
        for index, record in enumerate(candidates):
            try:
                padded = (record.get('download_center') == [options['ra'], options['dec']]
                          and record.get('requested_source_width_deg', 0) >= options['fov']/60*1.5 - 1e-8)
                if not offline and not padded and not cutout_covers_field(record, grid, size) and record.get('source'):
                    progress(f"Fetching a wider image for {record['timestamp'][:10]}")
                    record = wider_cutout(record, options)
                    dedup[(record['id'], record['detector'])] = record
                    wider_views += 1
                if len(candidates) > 1:
                    progress(f"Aligning FITS frame {index+1} of {len(candidates)}")
                frame = prepare_frame(record, options, grid, size, grid_sky=grid_sky)
                if not frame:
                    continue
                meta = frame[2]
                if not meta['center_inside'] or meta['coverage'] <= 0 or (
                        options['detector'] and (meta['footprint_coverage'] < 99 or meta['coverage'] < 80)):
                    excluded.append({
                        'id': record['id'], 'timestamp': record['timestamp'],
                        'detector': record['detector'], 'release': record['release'],
                        'coverage': meta['coverage'], 'footprint_coverage': meta['footprint_coverage'],
                        'source': record.get('source'), 'fits_url': record['fits_url'],
                        'reason': ('The detector did not cover this full field. Try a smaller field.'
                                   if meta['footprint_coverage'] < 99 or not meta['center_inside'] else
                                   'Too many brightness values are missing or invalid.'),
                    })
                else:
                    prepared.append(frame)
            except Exception as error:
                failures.append(f"{record['id']}: {error}")
        mosaic_used = False
        mosaic_mode = payload.get('mosaic', 'auto')
        if archive_requested and options['detector'] and mosaic_mode is not False and not prepared and (
                mosaic_mode == 'force' or not excluded):
            try:
                prepared = mosaic_frames(options, grid, size, grid_sky, progress)
                mosaic_used = bool(prepared)
            except Exception as error:
                failures.append(f'SPHEREx DR1 all-sky mosaic unavailable ({error}).')
        frames = prepared.metadata if isinstance(prepared, FrameBuffer) else [frame[2] for frame in prepared]
        if new_dates and not frames and snapshot:
            candidates = page.get('candidate_dates', 0)
            note = (
                'The archive listed additional dates, but this batch returned no usable frames.'
                if candidates else 'The available archive search found no additional dates for this field.'
            )
            if failures and not candidates:
                note = 'Archive discovery was incomplete. The available results had no additional dates.'
            snapshot.update(new_dates_search=True, coverage_note=note, next_archive_offset=page['next'],
                            failures=failures)
            return finish(snapshot, 'Showing saved observations')
        if len({frame['unit'] for frame in frames}) > 1:
            raise ValueError('These images have different units and cannot share a display scale.')
        progress('Rendering aligned frames with a shared brightness scale')
        directory, stretch = write_previews(job_id, prepared, frames)
        manifest = {
            'id': job_id, 'pipeline': PIPELINE, 'created_utc': Time.now().isot+'Z',
            'options': options, 'size': size, 'frames': frames, 'stretch': stretch,
            'archive_matches': archive_total, 'limited': limited and not mosaic_used, 'matched_frames': matched, 'failures': failures,
            'wider_views': wider_views, 'excluded_frames': excluded, 'archive_error': archive_error,
            'coverage_policy': {'minimum_footprint_percent': 99 if options['detector'] else 0,
                                'minimum_valid_pixels_percent': 80 if options['detector'] else 0},
            'mosaic': mosaic_used,
            'daily_sequence': daily,
            'next_archive_offset': page['next'],
            'new_dates_search': new_dates,
            'candidate_dates': page.get('candidate_dates'),
            'mosaic_note': ('DR1 mosaic channels stack many dates. Motion and time variability cannot be measured from them.'
                            if mosaic_used else ''),
            'empty_reason': ('' if frames else archive_error or (
                'No complete frames cover this selection. Try a smaller field or another detector.'
                if excluded else 'No dated SPHEREx observations were available for this sky field.')),
            'flag_source': FLAG_SOURCE, 'science_status': 'Visual inspection; native pixel readouts',
            'notes': ['All dates use the same ICRS sky grid and display scale.',
                      'Wavelengths are approximate WCS-WAVE values at the requested center.',
                      'Source movement and brightness fits require further calibration and validation.'],
        }
        if daily:
            selected = [day[0] for day in observing_days(frames)]
            manifest['frames'] = [dict(frame, index=i) for i, frame in enumerate(selected)]
        atomic_json(directory / 'manifest.json', manifest)
        if not preparing_cache and frames and not (fetch_failures or archive_error or mosaic_used):
            with LOCK:
                for view_key in {key, session_key(options, list(dedup.values()))}:
                    SESSIONS[view_key] = job_id
                    atomic_json(VIEW_INDEX / f'{view_key}.json', {'session': job_id})
        finish(manifest, 'Ready')
    except Exception as error:
        traceback.print_exc()
        with LOCK:
            JOBS[job_id].pop('preview', None)
            JOBS[job_id].update(status='failed', stage=str(error))
    finally:
        if buffer is not None:
            buffer.close()


class SpectrumCancelled(Exception):
    pass


def create_spectrum(job_id, payload):
    def check_cancelled():
        with LOCK:
            if JOBS[job_id].get('_cancel_requested'):
                raise SpectrumCancelled()

    try:
        check_cancelled()
        from .spectroscopy import extract
        session_id = str(payload.get('session',''))
        if not re.fullmatch('[a-f0-9]{32}', session_id):
            raise ValueError('Open a sky view before measuring its light.')
        manifest=load_manifest(session_id)
        frame=manifest['frames'][int(payload.get('frame',0))]
        x,y=float(payload.get('x',.5)),float(payload.get('y',.5))
        if not (0<=x<1 and 0<=y<1):
            raise ValueError('Select a point inside the sky image.')
        grid,size=grid_for(manifest['options'])
        sky=grid.pixel_to_world(x*size-.5,(1-y)*size-.5)
        scope=payload.get('scope','near')
        start,end=manifest['options']['start_mjd'],manifest['options']['end_mjd']
        if scope=='near':
            start,end=frame['mjd']-7,frame['mjd']+7
        elif scope=='all':
            start,end=None,None
        elif scope!='dates':
            raise ValueError('Unknown measurement time range.')
        refresh_featured()
        with LOCK:
            records=list(RECORDS)
        records.extend(dict(f, path=str(cache_path(f['fits_url'].removeprefix('/cache/')) or ''))
                       for f in manifest['frames'] if f.get('fits_url', '').startswith('/cache/'))
        def progress(message):
            check_cancelled()
            with LOCK:
                JOBS[job_id].update(stage=message)
        def resolve(chosen):
            check_cancelled()
            missing=[r for r in chosen.values() if not available(r) and r.get('source')]
            if missing:
                chosen.update(fetch_cutouts(missing,float(sky.ra.deg),float(sky.dec.deg),5,progress,[],start,end,
                                            check_cancelled=check_cancelled))
        track_points = payload.get('track_points')
        follow = bool(payload.get('follow_track') and track_points)
        result = extract(records, sky.ra.deg, sky.dec.deg, CACHE, progress, start, end,
                         float(payload.get('redshift',0)), resolve,
                         track_points=track_points if follow else None,
                         track_object=payload.get('track_object') if follow else None)
        result['scope']=scope
        with LOCK:
            check_cancelled()
            JOBS[job_id].update(status='complete',stage='Light measurements ready',result=result)
    except SpectrumCancelled:
        with LOCK:
            JOBS[job_id].update(status='cancelled',stage='Light measurement cancelled.')
    except Exception as error:
        traceback.print_exc()
        with LOCK:
            JOBS[job_id].update(status='failed',stage=str(error))


def create_track(job_id, payload):
    try:
        from .tracking import track
        sid=str(payload.get('session',''))
        if not re.fullmatch('[a-f0-9]{32}',sid): raise ValueError('Open a sky view first.')
        manifest=load_manifest(sid)
        frames = manifest['frames']
        reference_index = int(payload.get('frame', 0))
        if not 0 <= reference_index < len(frames):
            raise ValueError('Choose a valid reference frame.')
        reference = frames[reference_index]
        wave = reference.get('wavelength')
        eligible = [
            i for i, frame in enumerate(frames)
            if frame['detector'] == reference['detector'] and (
                i == reference_index or payload.get('object') or
                (frame['release'] == reference['release']
                 and wave is not None and frame.get('wavelength') is not None
                 and abs(frame['wavelength'] - wave) <= .05))
        ]
        if len({int(frames[i]['mjd']) for i in eligible}) < 2 and not payload.get('object'):
            raise ValueError('This source needs matching wavelengths on at least two observing dates. Try Motion pair or another reference frame.')
        payload = dict(payload, frame=eligible.index(reference_index))
        anchor = payload.get('anchor2')
        if isinstance(anchor, dict):
            anchor_index = int(anchor['frame'])
            if anchor_index not in eligible:
                raise ValueError('Choose a second anchor with a matching detector and wavelength.')
            payload['anchor2'] = dict(anchor, frame=eligible.index(anchor_index))
        manifest = dict(manifest, frames=[frames[i] for i in eligible])
        refresh_featured()
        with LOCK: lookup={r['sha256']:r for r in RECORDS}
        # Files the cache trim removed are fetched again from IRSA; say so, or the job looks frozen
        evicted=sum(1 for f in manifest['frames'] if f['sha256'] in lookup and not available(lookup[f['sha256']]))
        fetched=[0]
        if evicted:
            with LOCK: JOBS[job_id].update(stage=f'Downloading {evicted} observations again from the NASA archive (the cache had removed them)')
        def local_path(frame):
            rec=lookup.get(frame['sha256'])
            if rec and available(rec): return rec['path']
            if rec:
                path=ensure_local(rec)['path']
                with LOCK:
                    fetched[0]+=1
                    JOBS[job_id].update(stage=f'Downloading observation {fetched[0]} of {evicted} again from the NASA archive')
                return path
            filename = frame['fits_url'].removeprefix('/cache/')
            path = cache_path(filename)
            if not path:
                raise ValueError('Original FITS unavailable')
            return str(path)
        def progress(message):
            with LOCK: JOBS[job_id].update(stage=message)
        # A cold cache can mean minutes of downloads, so count them through the same job stage
        frames=manifest['frames']
        cold=lambda frame:(rec:=lookup.get(frame['sha256'])) is not None and not available(rec)
        missing=sum(map(cold,frames))
        progress(f'Downloading frames 0 / {missing} ({len(frames)-missing} already cached)' if missing
                 else f'All {len(frames)} frames already cached')
        fetched=[0]
        def fetch(frame):
            download=cold(frame)
            path=local_path(frame)
            if download:
                with LOCK: fetched[0]+=1; done=fetched[0]
                progress(f'Downloading frames {min(done,missing)} / {missing}')
            return path
        with ThreadPoolExecutor(max_workers=1 if LOW_MEMORY else 6) as pool:
            paths=list(pool.map(fetch,frames))
        result=track(manifest,paths,payload,CACHE,progress)
        result['reference_index'] = reference_index
        for point in result['points']:
            point['index'] = eligible[point['index']]
        for segment in result['segments']:
            segment['from_index'] = eligible[segment['from_index']]
            segment['to_index'] = eligible[segment['to_index']]
        with LOCK: JOBS[job_id].update(status='complete',stage='Track ready',result=result)
    except Exception as error:
        from .ephemeris import EphemerisError
        if not isinstance(error,EphemerisError): traceback.print_exc()
        with LOCK: JOBS[job_id].update(status='failed',stage=str(error))


def library_payload():
    refresh_featured()
    result = []
    with LOCK:
        for field in fields():
            _, snapshot = view_entry(field['key'])
            identity = field['key']
            common = {key: value for key, value in field.items() if key != 'frames'}
            common.update(detector=3 if identity == 'vesta' else 0, fov=PRESET_FOV)
            if snapshot:
                result.append(dict(common, frames=snapshot['loaded'], dates=snapshot.get('dates'),
                                   detectors=snapshot['detectors'],
                                   thumbnail=snapshot['thumbnail'], complete=snapshot['complete'],
                                   discovered=snapshot['discovered']))
                continue
            found = {(r['id'], r['detector']): r for r in RECORDS if r['field_key'] == identity}
            sid = TARGET_SESSIONS.get(identity)
            thumb = f'/cache/{sid}/0.png' if sid and (CACHE / sid / '0.png').is_file() else None
            if not thumb and field['frames'] and (LOCAL / field['frames'][0]['png']).is_file():
                thumb = '/' + field['frames'][0]['png']
            result.append(dict(common, frames=len(found), thumbnail=thumb, complete=False,
                               detectors={str(d): sum(r['detector']==d for r in found.values()) for d in range(1,7)}))
        imports = [{'ra': r['center'][0], 'dec': r['center'][1], 'detector': r['detector'],
                    'id': r['id'], 'release': r['release']} for r in RECORDS if r['field_key'] in ('imported', 'archive')]
    sync = next((json.loads(path.read_text(encoding='utf-8')) for path in
                 (CACHE / 'warmup-status.json', CACHE / 'sync-status.json') if path.is_file()), None)
    return {'fields': result, 'imports': imports, 'config': CONFIG, 'pipeline': PIPELINE, 'sync': sync}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def json_response(self, data, status=200):
        content = json.dumps(data, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(content)

    def end_headers(self):
        # Page code changes between visits, so browsers must revalidate it. Frame images never change.
        if not self.path.startswith(('/api/', '/cache/', '/data/')):
            self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def translate_path(self, path):
        clean = urlparse(path).path
        if clean.startswith('/api/original/'):
            digest=clean.rsplit('/',1)[-1]
            with LOCK:
                row=next((r for r in RECORDS if r.get('sha256')==digest),None)
            return row['path'] if row else str(ROOT/'_missing')
        if any(part.startswith('.') for part in clean.split('/')):
            return str(ROOT / '_missing')  # never serve .env or other dotfiles
        for prefix, directory in (('/cache/', CACHE), ('/data/', LOCAL/'data')):
            if clean.startswith(prefix):
                relative = clean[len(prefix):]
                if prefix == '/cache/':
                    return str(cache_path(relative) or ROOT / '_missing')
                target = (directory / relative).resolve()
                if not target.is_relative_to(directory.resolve()):
                    return str(ROOT / '_missing')
                return str(target)
        return super().translate_path(path)

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == '/api/library':
                return self.json_response(library_payload())
            if parsed.path.startswith('/api/jobs/'):
                job_id = parsed.path.rsplit('/', 1)[1]
                with LOCK:
                    saved = JOBS.get(job_id)
                    job = {key: value for key, value in saved.items() if not key.startswith('_')} if saved else None
                return self.json_response(job or {'error': 'Job not found'}, 200 if job else 404)
            if parsed.path in ('/api/pixel', '/api/identify'):
                args = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                session = args['session']
                if not re.fullmatch('[a-f0-9]{32}', session):
                    raise ValueError('Invalid session ID.')
                manifest = load_manifest(session)
                frame = manifest['frames'][int(args['frame'])]
                with LOCK:
                    record = next((r for r in RECORDS if r['sha256'] == frame['sha256']), None)
                if record is None:
                    filename = frame['fits_url'].removeprefix('/cache/')
                    if not re.fullmatch(r'[a-f0-9]{64}\.fits', filename):
                        raise ValueError('The original source is no longer in this library.')
                    record = dict(frame, path=str(cache_path(filename) or CACHE / filename))
                x, y = float(args['x']), float(args['y'])
                if parsed.path == '/api/pixel':
                    return self.json_response(inspect_pixel(ensure_local(record), manifest['options'], x, y))
                if not (0 <= x < 1 and 0 <= y < 1):
                    raise ValueError('Click inside the image.')
                from .tracking import name_source
                grid, size = grid_for(manifest['options'])
                guess = grid.pixel_to_world(x * size - 0.5, (1 - y) * size - 0.5)  # same click-to-sky mapping as tracking.track
                return self.json_response(name_source(ensure_local(record)['path'], guess, float(frame['mjd']), CACHE))
            return super().do_GET()
        except (ValueError, KeyError, IndexError, StopIteration, FileNotFoundError) as error:
            return self.json_response({'error': str(error)}, 400)

    def do_POST(self):
        try:
            # The local service only accepts writes from its own origin or CLI clients.
            origin = self.headers.get('Origin')
            # Compare hosts only: behind an HTTPS tunnel the page origin is https, the local hop http.
            if origin and urlparse(origin).netloc != self.headers.get('Host'):
                return self.json_response({'error': 'Origin not allowed'}, 403)
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= 85_000_000:
                raise ValueError('Request must contain data and fit within 85 MB.')
            payload = self.rfile.read(size)
            if self.path == '/api/import':
                return self.json_response({'error': 'File import is disabled in Planet X.'}, 403)
            if self.path == '/api/jobs':
                options = json.loads(payload)
                normalized = request_options(options)
                offset = int(options.get('archive_offset', 0))
                if not 0 <= offset <= 20000:
                    raise ValueError('Invalid archive batch offset.')
                job_key = json.dumps({'source': options.get('source', 'saved'),
                                      'mosaic': options.get('mosaic', 'auto'), 'archive_offset': offset,
                                      'new_dates': options.get('new_dates') is True,
                                      **normalized}, sort_keys=True)
                with LOCK:
                    trim_finished_jobs()
                    existing = next((jid for jid, job in JOBS.items()
                                     if job.get('status') == 'running' and job.get('job_key') == job_key), None)
                    if existing:
                        return self.json_response({'id': existing}, 202)
                    if sum(job['status'] == 'running' and not job.get('warmup') for job in JOBS.values()) >= ACTIVE_JOBS:
                        return self.json_response({'error': 'The archive worker is busy. Try again shortly.'}, 429)
                    job_id = uuid.uuid4().hex
                    JOBS[job_id] = {'status': 'running', 'stage': 'Preparing request', 'id': job_id, 'job_key': job_key}
                POOL.submit(run_job, create_session, job_id, options)
                return self.json_response({'id': job_id}, 202)
            if self.path == '/api/spectrum/cancel':
                options = json.loads(payload)
                if not isinstance(options, dict):
                    raise ValueError('Expected a cancellation request.')
                with LOCK:
                    job = JOBS.get(str(options.get('id','')), {})
                    waiters = job.get('_waiters')
                    waiter = str(options.get('waiter',''))
                    if job.get('status') == 'running' and waiters and waiter in waiters:
                        waiters.remove(waiter)
                        if not waiters:
                            job['_cancel_requested'] = True
                return self.json_response({'ok': True})
            if self.path in ('/api/spectrum','/api/track'):
                options=json.loads(payload)
                if not isinstance(options, dict):
                    raise ValueError('Expected a measurement request.')
                job_key=json.dumps([self.path, options], sort_keys=True)
                waiter = uuid.uuid4().hex if self.path == '/api/spectrum' else None
                with LOCK:
                    trim_finished_jobs()
                    existing=next((jid for jid, job in JOBS.items()
                                   if job['status']=='running' and not job.get('_cancel_requested')
                                   and job.get('job_key')==job_key), None)
                    if existing:
                        if waiter:
                            JOBS[existing]['_waiters'].add(waiter)
                        return self.json_response({'id':existing,'waiter':waiter},202)
                    if sum(job['status']=='running' and not job.get('warmup') for job in JOBS.values())>=ACTIVE_JOBS:
                        return self.json_response({'error':'The archive worker is busy. Try again shortly.'},429)
                    job_id=uuid.uuid4().hex
                    JOBS[job_id]={'status':'running','stage':'Preparing star tracking' if self.path=='/api/track' else 'Preparing light measurements','id':job_id,'job_key':job_key}
                    if waiter:
                        JOBS[job_id]['_waiters'] = {waiter}
                POOL.submit(run_job,create_track if self.path=='/api/track' else create_spectrum,job_id,options)
                return self.json_response({'id':job_id,'waiter':waiter},202)
            return self.json_response({'error': 'Unknown endpoint'}, 404)
        except (ValueError, TypeError, KeyError) as error:
            return self.json_response({'error': str(error)}, 400)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    initialize()
    # The page loads ~17 files at once; through the tunnel they arrive together, and the default backlog of 5 refuses some.
    ThreadingHTTPServer.request_queue_size = 64
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'SPHEREx prototype ready at http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
