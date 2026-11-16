"""Prepare dated SPHEREx cutouts and previews before someone opens a field."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from threading import Lock
import time
import uuid

from filelock import FileLock, Timeout

from . import server
from .archive import query, write_json
from .featured_views import (BUNDLE, CACHE, INVENTORIES, PRESET_FOV, bundle_view, combined_rows,
                             field_inventory, fields, observing_days, sample_frames, save_entry,
                             view_entry)
from backend.cloud import CONFIG as CLOUD_CONFIG

LOG = logging.getLogger(__name__)


def cached_cutouts(roots):
    """Find genuine same-grid cutouts left by successful or interrupted downloads."""
    default_width = PRESET_FOV / 60 * 1.5
    centers = {}
    for root in roots:
        for receipt in root.glob('*.record.json'):
            path = receipt.with_name(receipt.name.removesuffix('.record.json') + '.fits')
            try:
                row = json.loads(receipt.read_bytes())
                origin = row['download_url'].split('?', 1)[0]
                if origin.startswith(CLOUD_CONFIG['cloud_origin']):
                    origin = 'https://irsa.ipac.caltech.edu/ibe/data/spherex/' + origin.removeprefix(
                        CLOUD_CONFIG['cloud_origin'])
                if (not origin.startswith('https://irsa.ipac.caltech.edu/ibe/data/spherex/')
                        or not origin.endswith('.fits')
                        or row['requested_source_width_deg'] != default_width
                        or path.stat().st_size != row['file_bytes']):
                    continue
                release = origin.split('/spherex/', 1)[1].split('/', 1)[0]
                row.update(source=origin, release=release.upper(), collection='spherex_' + release,
                           path=str(path), fits_url=f'/cache/{path.name}')
                centers.setdefault(tuple(row['download_center']), []).append(row)
            except (KeyError, OSError, ValueError):
                continue
    return centers


def refresh(fields_to_warm=None, force=False, bundle=False, offline=False, reuse_cache=(),
            daily_only=False, mirror_only=False):
    targets = [f for f in fields() if f['key'] != 'vesta'
               and (not fields_to_warm or f['key'] in fields_to_warm)]
    if not targets or fields_to_warm and set(fields_to_warm) != {f['key'] for f in targets}:
        raise ValueError('Select preset or catalog field keys from /observation-lab/api/library.')
    progress_file = CACHE / 'warmup-status.json'
    state = dict(status='Preparing SPHEREx cache', completed=0, total=len(targets), fields={})
    progress_lock = Lock()
    cached = cached_cutouts((BUNDLE, CACHE, *reuse_cache)) if offline else {}

    def publish(key, message, result=None, done=False):
        with progress_lock:
            state.update(status=message, updated=datetime.now(timezone.utc).isoformat())
            if result is not None:
                state['fields'][key] = result
            state['completed'] += int(done)
            write_json(progress_file, state)

    def field_views(group):
        for field in group:
            key = field['key']
            full = bool(field['frames'] or bundle)
            base, entry = view_entry(key)
            if not offline and not force and entry:
                age = time.time() - datetime.fromisoformat(entry['updated'].replace('Z', '+00:00')).timestamp()
                if age < 86400 and (entry['complete'] or not full and not entry['failures']):
                    publish(key, 'Cached ' + field['name'], entry, True)
                    continue
            publish(key, 'Preparing ' + field['name'])
            try:
                if bundle and base == CACHE and entry and not offline:
                    bundle_view(field, entry)
                known = field_inventory(field)
                inventory = CACHE / f'{key}-inventory.json'
                local = None
                if offline:
                    local = cached.get((field['ra'], field['dec']), [])
                    if not local:
                        continue
                    rows = combined_rows(known, local)
                elif mirror_only:
                    rows = known
                elif not force and inventory.is_file() and time.time() - inventory.stat().st_mtime < 86400:
                    rows = json.loads(inventory.read_text(encoding='utf-8'))
                else:
                    try:
                        rows = query(server.CONFIG, field['ra'], field['dec'], latest=full)
                    except (RuntimeError, ValueError):
                        if not known:
                            raise
                        rows = []
                    partial = not rows or any(row.get('discovery_warning') for row in rows)
                    if known:
                        rows = combined_rows(known, rows)
                    if partial and known:
                        for row in rows:
                            row['discovery_warning'] = 'Live discovery incomplete; using indexed exposures via AWS.'
                    elif rows:
                        write_json(inventory, rows)
                    if bundle and rows:
                        INVENTORIES.mkdir(exist_ok=True)
                        write_json(INVENTORIES / inventory.name, rows)
                requested = rows if full else sample_frames(rows, 4)
                if not requested:
                    raise ValueError('The archive returned no observations covering this position.')
                days = observing_days(requested)
                first = [day[0] for day in days]
                remaining = [row for day in days for row in day[1:]]
                stages = [requested] if offline else [first]
                if not offline and remaining and not daily_only:
                    stages.append(first + remaining)
                if offline and entry and entry.get('dates') is not None and entry['loaded'] >= len(combined_rows([], local)):
                    publish(key, 'Cached ' + field['name'], entry, True)
                    continue
                previous_frames = server.load_manifest(entry['session'])['frames'] if entry and not offline else []
                for selected in stages:
                    job = uuid.uuid4().hex
                    options = dict(ra=field['ra'], dec=field['dec'], fov=PRESET_FOV,
                                   detector=0, source='archive', mosaic=False, field=key, mirror_only=mirror_only)
                    with server.LOCK:
                        server.JOBS[job] = {'status': 'running', 'stage': 'Warming cache', 'id': job, 'warmup': True}
                    try:
                        if offline:
                            server.create_session(job, options, cached_records=local)
                        else:
                            server.create_session(job, options, archive_rows=selected,
                                                  cached_records=previous_frames)
                    finally:
                        with server.LOCK:
                            result = server.JOBS.pop(job)
                    manifest = result.get('result')
                    if not manifest or not manifest['frames']:
                        raise RuntimeError(result.get('stage') if not manifest else
                                           '; '.join(manifest['failures'][:2]) or 'No usable frames')
                    manifest['archive_matches'] = len(rows)
                    complete = not offline and len(selected) == len(rows) and not manifest['failures']
                    write_json(CACHE / job / 'manifest.json', manifest)
                    save_entry(CACHE, field, manifest, complete)
                    if bundle:
                        _, saved = view_entry(key, (CACHE,))
                        bundle_view(field, saved, cutout_sources={row['fits_url']: Path(row['path'])
                                                                  for row in local or []})
                    _, entry = view_entry(key)
                    report = dict(entry or {}, requested=len(selected), discovered=len(rows),
                                  failures=len(manifest['failures']), last_error=next(iter(manifest['failures']), None))
                    publish(key, 'Prepared ' + field['name'], report,
                            selected is stages[-1] and not manifest['failures'])
                    LOG.info('%s: %s ready, %s discovered, %s errors', key, len(manifest['frames']), len(rows),
                             len(manifest['failures']))
            except Exception as error:
                LOG.warning('SPHEREx warmup %s: %s', key, error)
                publish(key, 'Could not finish ' + field['name'], dict(entry or {}, error=str(error)))
            server.trim_cache()

    try:
        with FileLock(str(CACHE / 'warmup.lock'), timeout=0):
            # Give the long challenge sequences dedicated capacity while nearby/bright
            # fields warm independently.
            core = [f for f in targets if f['frames']]
            stars = [f for f in targets if not f['frames']]
            with ThreadPoolExecutor(max_workers=5 if bundle else 3) as pool:
                list(pool.map(field_views, ([field] for field in core)))
            # Finish the presets before starting other fields in distance order.
            field_views(stars)
            status = 'SPHEREx cache ready' if state['completed'] == state['total'] else 'Will retry incomplete SPHEREx fields'
            publish(None, status)
    except Timeout:
        state['status'] = 'The SPHEREx cache is already warming.'
        LOG.info(state['status'])
    return state


def run_forever():
    while True:
        try:
            status = refresh()
            delay = 3600 if status['completed'] == status['total'] else 900
        except Exception:
            LOG.exception('SPHEREx cache refresh failed')
            delay = 900
        time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--field', action='append', help='Only warm this catalog or preset key. Repeat to select several.')
    parser.add_argument('--bundle', action='store_true', help='Save preset and catalog FITS and previews into the deploy image.')
    parser.add_argument('--offline', action='store_true', help='Recover all verified cutouts from existing local files.')
    parser.add_argument('--daily-only', action='store_true', help='Fetch a representative exposure per UTC date first.')
    parser.add_argument('--mirror-only', action='store_true', help='Use saved exposure indexes and fetch from AWS without calling IRSA.')
    parser.add_argument('--reuse-cache', action='append', type=Path, default=[], help='Additional local Lab cache for offline recovery.')
    parser.add_argument('--force', action='store_true', help='Rediscover the archive even when the cache is current.')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    result = refresh(args.field, force=args.force, bundle=args.bundle, offline=args.offline,
                     reuse_cache=[path.resolve() for path in args.reuse_cache], daily_only=args.daily_only,
                     mirror_only=args.mirror_only)
    print(f"{result['status']} ({result['completed']}/{result['total']} fields)")
    return 0 if result['completed'] == result['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
